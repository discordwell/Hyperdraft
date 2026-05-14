#!/usr/bin/env bash
# scripts/safety/git-reset-guarded.sh
#
# Opt-in safer alternative to `git reset --hard`. Takes a snapshot to
# refs/wip/manual/<branch>/<timestamp> BEFORE running the reset, so the
# work survives even if the reset wipes the working tree.
#
# Usage (drop-in replacement for `git reset`):
#   scripts/safety/git-reset-guarded.sh --hard
#   scripts/safety/git-reset-guarded.sh --hard HEAD~1
#   scripts/safety/git-reset-guarded.sh --hard origin/main
#
# Suitable for parent-workflow / merge-cleanup scripts that want to clear
# the working tree without losing any in-flight uncommitted work from
# concurrently-running agents.
#
# Recovery (if you need to undo a guarded reset):
#   git for-each-ref refs/wip/manual/ --sort=-creatordate --format='%(refname) %(creatordate:iso)' | head
#   git checkout <ref> -- .

set -euo pipefail

ARGS=("$@")
HARD=0
for a in "${ARGS[@]}"; do
    [[ "$a" == "--hard" ]] && HARD=1
done

if [[ "$HARD" != "1" ]]; then
    # Non-destructive reset (--soft / --mixed / --keep) — pass straight through.
    exec git reset "${ARGS[@]}"
fi

branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "detached")
branch_safe=${branch//\//_}
ts=$(date -u +%Y%m%d-%H%M%S)
ref="refs/wip/manual/${branch_safe}/${ts}"

# Detect dirty: tracked changes (index/working) OR untracked files.
has_tracked=0
has_untracked=0
if ! git diff --quiet HEAD 2>/dev/null \
   || ! git diff --quiet --cached HEAD 2>/dev/null; then
    has_tracked=1
fi
if [[ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]]; then
    has_untracked=1
fi

if (( has_tracked == 1 || has_untracked == 1 )); then
    snap_oid=""
    if (( has_untracked == 1 )); then
        # Untracked-aware snapshot: build a tree off a temp index without
        # mutating the working tree.
        temp_index=$(mktemp -t git_reset_guarded_idx.XXXXXX)
        if [[ -f "$(git rev-parse --git-dir)/index" ]]; then
            cp -f "$(git rev-parse --git-dir)/index" "$temp_index" 2>/dev/null || true
        fi
        tree_oid=$(GIT_INDEX_FILE="$temp_index" bash -c '
            git add -A -- . >/dev/null 2>&1 || true
            git write-tree
        ' 2>/dev/null || true)
        rm -f "$temp_index"
        if [[ -n "$tree_oid" ]]; then
            parent_oid=$(git rev-parse HEAD 2>/dev/null)
            snap_oid=$(printf 'pre-reset guard %s\n\ngit reset %s' "$ts" "${ARGS[*]}" \
                | git commit-tree "$tree_oid" -p "$parent_oid" 2>/dev/null || true)
        fi
    else
        snap_oid=$(git stash create "pre-reset guard ${ts}" 2>/dev/null || true)
    fi

    if [[ -n "$snap_oid" ]]; then
        git update-ref "$ref" "$snap_oid" -m "git-reset-guarded snapshot before: git reset ${ARGS[*]}"
        echo "[git-reset-guarded] snapshot -> $ref" >&2
    else
        echo "[git-reset-guarded] working tree has changes but snapshot creation failed" >&2
        if [[ "${GIT_RESET_GUARDED_FORCE:-0}" != "1" ]]; then
            echo "[git-reset-guarded] ABORTING. Set GIT_RESET_GUARDED_FORCE=1 to override." >&2
            exit 3
        fi
    fi
fi

exec git reset "${ARGS[@]}"
