#!/usr/bin/env bash
# scripts/safety/wip_autobackup.sh
#
# Continuously snapshots the working tree to refs/wip/auto-<branch>-<ts>.
# Defends against external `git reset --hard` cycles that wipe uncommitted
# work during concurrent worktree-agent merges (see docs/safety/git_reset_defense.md).
#
# Usage:
#   scripts/safety/wip_autobackup.sh [--interval SECONDS] [--keep N] [--once]
#
#   --interval    How often to snapshot, in seconds. Default 60.
#   --keep        How many recent snapshots to retain per branch. Default 24.
#   --once        Take one snapshot and exit (used by SessionStart hook).
#
# Recovery (after a reset wipes your work):
#   git for-each-ref refs/wip/auto/<branch>/ --sort=-creatordate --format='%(refname) %(creatordate:iso)' | head
#   git checkout refs/wip/auto/<branch>/<timestamp> -- .   # restore tree
# or:
#   git stash apply <stash-ref>
#
# Cost: each snapshot is ~1 git object (`git stash create`), gc-able.
# Refs live in refs/wip/auto/ and are listed by `git for-each-ref`.

set -euo pipefail

INTERVAL=60
KEEP=24
ONCE=0
QUIET=${WIP_AUTOBACKUP_QUIET:-0}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval) INTERVAL="$2"; shift 2 ;;
        --keep)     KEEP="$2";     shift 2 ;;
        --once)     ONCE=1;        shift   ;;
        --quiet)    QUIET=1;       shift   ;;
        -h|--help)
            sed -n '1,30p' "$0"; exit 0
            ;;
        *) echo "wip_autobackup: unknown arg: $1" >&2; exit 2 ;;
    esac
done

log() {
    [[ "$QUIET" == "1" ]] && return 0
    printf '[wip-autobackup %s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2
}

# Must be inside a git repo
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null) || {
    log "not in a git repo, exiting"
    exit 1
}

snapshot_once() {
    local branch ts ref msg
    local has_tracked=0 has_untracked=0
    if ! git diff --quiet --cached HEAD 2>/dev/null || ! git diff --quiet HEAD 2>/dev/null; then
        has_tracked=1
    fi
    if [[ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]]; then
        has_untracked=1
    fi
    # Skip if working tree is clean (after gitignore)
    if (( has_tracked == 0 && has_untracked == 0 )); then
        return 0
    fi

    branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "detached")
    # Sanitize branch name for ref path (replace `/` with `_`)
    branch_safe=${branch//\//_}
    ts=$(date -u +%Y%m%d-%H%M%S)
    ref="refs/wip/auto/${branch_safe}/${ts}"
    msg="auto-backup of ${branch} at ${ts} UTC (pid $$)"

    # Build a snapshot commit. `git stash create` only includes tracked
    # changes — to capture untracked files too WITHOUT mutating the working
    # tree, build a tree off a temporary index.
    local snap_oid
    if (( has_untracked == 1 )); then
        local temp_index
        temp_index=$(mktemp -t wip_autobackup_idx.XXXXXX)
        # Seed temp index from current index
        if [[ -f "$(git rev-parse --git-dir)/index" ]]; then
            cp -f "$(git rev-parse --git-dir)/index" "$temp_index" 2>/dev/null || true
        fi
        local tree_oid parent_oid
        tree_oid=$(GIT_INDEX_FILE="$temp_index" bash -c '
            git add -A -- . >/dev/null 2>&1 || true
            git write-tree
        ' 2>/dev/null || true)
        rm -f "$temp_index"
        if [[ -z "$tree_oid" ]]; then
            return 0
        fi
        parent_oid=$(git rev-parse HEAD 2>/dev/null)
        snap_oid=$(printf '%s' "$msg" | git commit-tree "$tree_oid" -p "$parent_oid" 2>/dev/null || true)
    else
        snap_oid=$(git stash create "$msg" 2>/dev/null || true)
    fi
    if [[ -z "$snap_oid" ]]; then
        return 0
    fi

    git update-ref "$ref" "$snap_oid" \
        -m "wip_autobackup: $msg"
    log "snapshot -> $ref"

    # Prune older auto-backups beyond KEEP (BSD-head safe).
    local total to_drop
    total=$(git for-each-ref --format='%(refname)' "refs/wip/auto/${branch_safe}/" | wc -l | tr -d ' ')
    to_drop=$(( total - KEEP ))
    if (( to_drop > 0 )); then
        git for-each-ref --format='%(refname)' "refs/wip/auto/${branch_safe}/" \
            | sort | head -n "$to_drop" | while read -r old_ref; do
            [[ -n "$old_ref" ]] && git update-ref -d "$old_ref" || true
        done
    fi
}

if [[ "$ONCE" == "1" ]]; then
    snapshot_once
    exit 0
fi

# Singleton guard: only one daemon per repository (not per worktree).
# The pidfile lives in the common-git-dir so it's shared across worktrees.
COMMON_GIT_DIR=$(git rev-parse --git-common-dir 2>/dev/null)
PIDFILE="${COMMON_GIT_DIR}/wip_autobackup.pid"

if [[ -f "$PIDFILE" ]]; then
    existing_pid=$(cat "$PIDFILE" 2>/dev/null || true)
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
        log "already running with pid $existing_pid, exiting"
        exit 0
    fi
    # Stale pidfile — remove and continue
    rm -f "$PIDFILE"
fi
echo "$$" > "$PIDFILE"
trap 'rm -f "$PIDFILE"; log "stopping"; exit 0' INT TERM EXIT

log "starting (interval=${INTERVAL}s, keep=${KEEP}, pid=$$, branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null), pidfile=$PIDFILE)"

while true; do
    snapshot_once || true
    sleep "$INTERVAL"
done
