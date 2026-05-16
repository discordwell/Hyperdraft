# LFS Migration Runbook

Move tracked binary art (`assets/card_art/**`, `frontend/public/scp-art/**`) out of git's pack files and into Git LFS. Shrinks `.git` from ~5.5GB to a few hundred MB.

**Do not run this while `/semaphore` worktrees are active or in-flight PRs exist.** It rewrites every commit SHA on `main` and force-pushes.

---

## 0. Preconditions (verify before starting)

```bash
cd /Users/discordwell/Projects/HYPERDRAFT
git remote -v                          # origin: git@github.com:discordwell/Hyperdraft.git
git lfs version                        # 3.7+
git worktree list                      # main only — no agent-* worktrees
git status                             # clean (or known untracked-only)
gh pr list                             # empty
```

GitHub side: confirm an LFS data pack is on the account (Settings → Billing). 2.7GB upload fits the free tier headroom of one purchased pack ($5/mo = 50GB storage + 50GB egress). Without a pack, the initial push will hit the 1GB free quota and fail mid-upload.

---

## 1. Stop background safety daemon

```bash
pkill -f scripts/safety/wip_autobackup.sh
pgrep -af wip_autobackup               # should be empty
```

Comment out the `SessionStart` hook in `.claude/settings.json` for the duration so a new session doesn't re-spawn it mid-migration. Restore after step 8.

---

## 2. Insurance — full backup of .git

```bash
cp -R .git /tmp/hyperdraft-git-pre-lfs-$(date -u +%Y%m%dT%H%M%SZ)
du -sh /tmp/hyperdraft-git-pre-lfs-*
```

This is the only thing that lets you fully undo the rewrite. Keep it until soak period passes.

Also tag the current tip on the live repo:

```bash
git tag pre-lfs-migration main
git push origin pre-lfs-migration       # remote escape hatch
```

---

## 3. Clean up stale refs

The `refs/wip/auto/*` and `refs/wip/archived/*` refs all point into pre-migration history. After rewrite their parent commits no longer exist (they survive as orphans, recoverable only via direct checkout). Either:

- **Delete them** (recommended — they're stale anyway):
  ```bash
  git for-each-ref refs/wip/ --format='delete %(refname)' | git update-ref --stdin
  ```
- **Or migrate them** by passing `--refs='refs/heads/* refs/tags/* refs/wip/*'` to `lfs migrate` in step 5. Adds runtime and rarely pays off.

Before deleting, sanity-check:

```bash
git for-each-ref refs/wip/ --format='%(refname) %(objectname:short) %(contents:subject)'
```

The two we created earlier (`refs/wip/archived/agent-{a522b,ad61593}`) were verified-superseded — safe to drop.

---

## 4. Configure LFS tracking

```bash
git lfs install                                          # one-time per machine
git lfs track 'assets/card_art/**'
git lfs track 'frontend/public/scp-art/**'
git add .gitattributes
git commit -m "feat(lfs): track card art via Git LFS

Move binary art (assets/card_art, frontend/public/scp-art) to LFS
backend. Shrinks .git pack from 5.5GB. See docs/safety/lfs_migration_runbook.md."
```

This commit will get rewritten by step 5 — that's fine, it just needs to exist so `.gitattributes` is in scope when migrate runs.

---

## 5. Run the migration

```bash
git lfs migrate import \
  --include="assets/card_art/**,frontend/public/scp-art/**" \
  --everything \
  --verbose
```

What `--everything` means: rewrite **every ref** under `refs/heads/*` and `refs/tags/*`. Not just `main`. Expect ~10–30 min for 5.5GB. The terminal shows per-commit progress.

After it completes:

```bash
git lfs ls-files | wc -l               # roughly N PNGs in current tree
du -sh .git                            # should be drastically smaller
git fsck --no-dangling                 # no corruption
```

---

## 6. Verify locally before pushing

```bash
# Sample: do old commits still resolve to real PNGs?
git stash || true
git checkout pre-lfs-migration~50      # 50 commits before the escape tag
ls -la assets/card_art/scp/ | head -3  # should show real PNG sizes, not 130-byte pointers
file assets/card_art/scp/*.png | head -1  # should say "PNG image data"
git checkout main
```

If you see "ASCII text" or 130-byte files instead of PNGs, the smudge filter didn't run — usually means `git lfs install` was skipped. Re-run, then `git lfs pull`.

---

## 7. Push (point of no return)

```bash
git push --force-with-lease origin main
git push --force --tags                # the pre-lfs-migration tag
# LFS objects upload in the same command; expect 2.7GB outbound
```

`--force-with-lease` is safer than `--force` — it refuses to push if remote moved unexpectedly (e.g., someone snuck a commit in).

If push fails with `quota exceeded`: stop and add a data pack. Don't retry blindly — partial-state LFS pushes are a hassle to resume.

---

## 8. Restore daemon + verify

```bash
# Uncomment SessionStart hook in .claude/settings.json, then:
scripts/safety/wip_autobackup.sh --once --quiet
nohup scripts/safety/wip_autobackup.sh --interval 60 --keep 24 --quiet >/dev/null 2>&1 &
pgrep -af wip_autobackup
```

Open `https://github.com/discordwell/Hyperdraft/blob/main/frontend/public/scp-art/...` for a sample card — should render as an image, not download as a pointer.

---

## 9. Soak (~24h)

Things to watch:
- Does the frontend dev server still serve card art? (`frontend/public/scp-art/` should resolve via the LFS smudge in the local checkout)
- Does the backend find `assets/card_art/` files? Most code probably reads them via Python `open()`, which sees the smudged-in file, so should be transparent
- Any CI? (this repo has no CI configured per the gitStatus context, so no concern)

Keep `pre-lfs-migration` tag and `/tmp/hyperdraft-git-pre-lfs-*` backup until soak period passes.

---

## Rollback (if something breaks during soak)

```bash
# Local
rm -rf .git
cp -R /tmp/hyperdraft-git-pre-lfs-<ts> .git
git checkout .

# Remote
git push --force origin main           # pushes pre-migration main back
# The pre-lfs-migration tag already points at the same commit
```

GitHub holds LFS objects for 14 days after their last reference is removed, so a rollback within that window doesn't lose data. After 14 days they're garbage-collected and a re-migration would re-upload.

---

## Acceptable losses

- **`refs/wip/*`** (if you took option A in step 3) — gone. The recovery refs were already past their useful window since the new graph doesn't match their parent commits.
- **External commit SHA links** (Slack, Linear, old PR comments) — they 404. The `pre-lfs-migration` tag preserves the old tip for reference.
- **`Download ZIP` button on GitHub** — returns pointer files instead of real PNGs for the LFS paths. Use `git clone` for real downloads.

## What does NOT change

- Local checkouts still see full PNGs (smudge filter)
- `git clone` still pulls full PNGs by default
- Code reading the art files via `open()` / `fetch()` is unchanged
- The sparse-checkout pattern in CLAUDE.md still applies — LFS + sparse-checkout compose (sparse keeps the LFS path entirely out of agent worktrees, so they don't even fetch the pointer)
