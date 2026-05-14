# Defending against external `git reset --hard` cycles

## TL;DR

This repo runs many concurrent Claude Code worktree-agents (via the
`semaphore` command + `EnterWorktree` / `ExitWorktree` native tools).
The parent session periodically runs `git reset --hard HEAD` on the
**main repo working tree** as part of merge-wave cleanup, which silently
wipes any uncommitted changes another agent has been working on directly
in the main tree.

To make this lossless we ship two complementary safety nets:

1. `scripts/safety/wip_autobackup.sh` — a background daemon that
   snapshots the working tree to `refs/wip/auto/<branch>/<timestamp>`
   every 60 s. Auto-started by the `SessionStart` hook in
   `.claude/settings.json`.
2. `scripts/safety/git-reset-guarded.sh` — an opt-in safer reset that
   snapshots BEFORE running `git reset --hard`, leaving a recoverable
   ref in `refs/wip/manual/<branch>/<timestamp>`.

Both write to a private `refs/wip/...` namespace (no impact on branches,
tags, or remotes) and are pruned automatically.

## How the data loss happens

The semaphore workflow looks like this:

1. Parent session dispatches N worktree-agents in parallel.
2. Each agent works in `.claude/worktrees/agent-<hash>/` on a
   `worktree-agent-<hash>` branch and commits there.
3. Parent integrates by running `git merge worktree-agent-<hash>` on
   `main` in the main checkout (`/Users/discordwell/Projects/HYPERDRAFT/`).
4. After a merge wave, the parent runs `git reset --hard HEAD` to clear
   any stray uncommitted state from the main checkout before the next
   wave.

That last step wipes anything an agent was editing **in the main
checkout** rather than in its own worktree — typically scripts the user
or a non-isolated subagent has been changing in real time.

`git reflog` shows the pattern clearly:

```
535b7598 main@{2026-05-13 23:07}: commit: feat(brv): merge 4 worktrees
47a6730b HEAD@{2026-05-13 22:59}: reset: moving to HEAD          <-- WIPE
47a6730b HEAD@{2026-05-13 22:43}: commit (merge): Merge MTG ...
55e9b22b main@{2026-05-13 22:36}: merge worktree-agent-...
...
```

Concrete incident (FBN run, 2026-05-13): a Stage 4.7 agent had added
~580 LOC to `src/engine/scp.py` and friends. The work passed 18 tests,
then got wiped by a reset cycle ~30 min later. Recovery cost ~10 min
of compute and re-dispatch.

## The fix

### Auto-backup daemon (`scripts/safety/wip_autobackup.sh`)

* Started automatically at session start by the hook in
  `.claude/settings.json`.
* Singleton: only one daemon per repo (pidfile lives in
  `$(git rev-parse --git-common-dir)/wip_autobackup.pid`, shared
  across worktrees).
* Snapshots **tracked + untracked** changes by building a tree off a
  temporary index without disturbing the live index or working tree.
* Stores each snapshot as a refs/wip/auto/<branch>/<UTC-timestamp>
  ref. Keeps the last 24 per branch and drops older ones.

To start manually:

```bash
scripts/safety/wip_autobackup.sh                       # 60s loop, 24 kept
scripts/safety/wip_autobackup.sh --interval 30 --keep 50
scripts/safety/wip_autobackup.sh --once                # one snapshot, exit
```

To check what snapshots exist:

```bash
git for-each-ref refs/wip/auto/ \
  --sort=-creatordate \
  --format='%(refname) %(creatordate:iso)'
```

### Opt-in guarded reset (`scripts/safety/git-reset-guarded.sh`)

Drop-in replacement for `git reset` when you (or the parent workflow)
intentionally want a hard reset. Takes a snapshot to
`refs/wip/manual/<branch>/<timestamp>` first.

```bash
scripts/safety/git-reset-guarded.sh --hard HEAD
scripts/safety/git-reset-guarded.sh --hard HEAD~1
scripts/safety/git-reset-guarded.sh --hard origin/main
```

Aborts (exit 3) if the working tree is dirty and snapshot creation
fails. Set `GIT_RESET_GUARDED_FORCE=1` to override.

Non-destructive resets (`--soft`, `--mixed`, `--keep`, no flag) pass
straight through with no snapshot — they don't lose anything.

### Recovery procedure

If you suspect a reset wiped your work:

```bash
# List recent snapshots
git for-each-ref refs/wip/auto/ refs/wip/manual/ \
  --sort=-creatordate \
  --format='%(refname) %(creatordate:iso)' \
  | head -20

# Inspect what's in a snapshot
git show refs/wip/auto/<branch>/<ts> --stat
git ls-tree refs/wip/auto/<branch>/<ts>

# Restore a single file
git checkout refs/wip/auto/<branch>/<ts> -- path/to/file

# Restore everything (DESTRUCTIVE — overwrites current working tree)
git checkout refs/wip/auto/<branch>/<ts> -- .

# Or branch the snapshot and merge selectively
git branch recover/<ts> refs/wip/auto/<branch>/<ts>
```

## Cost / cleanup

* Each snapshot is one commit object pointing to a tree of changed
  blobs (delta-compressed, ~tens of KB typical).
* Auto-backup prunes to KEEP=24 per branch; manual snapshots never
  expire automatically.
* `git gc` will pack everything; if you want to prune snapshots,
  delete the refs first:

  ```bash
  git for-each-ref refs/wip/ --format='delete %(refname)' \
    | git update-ref --stdin
  git gc --prune=now
  ```

## Trade-offs

* **What still hurts after this fix:** A `git clean -fdx` on the main
  tree would wipe untracked files BEFORE the watcher's next tick. The
  daemon snapshots every 60 s by default, so a window of up to 60 s
  of untracked-file work is at risk. Lower `--interval` if you're
  doing volatile untracked work.
* **What's harder now:** Nothing — both safety nets are additive.
  The auto-backup daemon costs <1% CPU even at 30 s intervals.
* **Disk:** ~24 snapshots/branch * ~50 active branches ~= a few MB
  in `.git/objects/`. Negligible.

## Origin

* Failure mode documented in
  `~/.claude/projects/-Users-discordwell-Projects-HYPERDRAFT/memory/feedback_external_git_reset_wipes_working_tree.md`
* Source: the `semaphore` command's "Integration" step (run by the
  parent session) issues `git reset --hard HEAD` on the main checkout
  after merging worktree branches; the `EnterWorktree` /
  `ExitWorktree` native tools also issue per-worktree resets on
  enter/exit. The per-worktree resets are scoped to a worktree HEAD
  and do not threaten the main tree.
