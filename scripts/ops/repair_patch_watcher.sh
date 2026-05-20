#!/usr/bin/env bash
# Host-side auto-repair patch watcher.
#
# Polls the hyperdraft-storage Docker volume for DONE-status repair sessions
# and pushes the in-container patch to a draft PR on GitHub. Runs OUTSIDE
# the container so the GitHub PAT never enters the production image.
#
# Triggered by /etc/systemd/system/hyperdraft-repair-watcher.timer every 60s
# (see scripts/deploy/install_repair_watcher.sh).
#
# Allowed write paths are enforced HERE, not just in the claude prompt —
# prompts are advisory, watchers are enforceable. Any hunks outside the
# allow-list are dropped and the patch is marked "tainted" requiring human
# review before merge.

set -euo pipefail

CONTAINER="${HYPERDRAFT_CONTAINER:-hyperdraft-hyperdraft-1}"
VOLUME_PATH="${HYPERDRAFT_STORAGE_VOLUME:-/var/lib/docker/volumes/hyperdraft_hyperdraft-storage/_data}"
REPAIR_DIR="${VOLUME_PATH}/repair"
PAT_FILE="${HYPERDRAFT_GITHUB_PAT_FILE:-/etc/hyperdraft/github-pat}"
GITHUB_REPO="${HYPERDRAFT_REPO:-discordwell/Hyperdraft}"
LOG_TAG="repair-watcher"

# Allow-list: any patch hunk whose path matches one of these globs is kept.
# Anything else is dropped and the patch is marked tainted. Mirror the prompt
# at src/server/repair_prompt.md.
ALLOW_GLOBS=(
  "src/cards/mtg/*"
  "src/cards/hearthstone/*"
  "src/cards/pokemon/*"
  "src/cards/yugioh/*"
  "src/cards/minecraft/*"
  "src/cards/finance/*"
  "src/cards/depths/*"
  "src/cards/scp/*"
  "src/ai/*_adapter.py"
  "src/engine/pokemon_*.py"
  "src/engine/yugioh_*.py"
  "src/engine/hearthstone_*.py"
  "src/engine/minecraft_*.py"
  "src/engine/finance_*.py"
  "src/engine/depths_*.py"
  "src/engine/scp_*.py"
  "tests/auto_repair/*"
)
# Deliberately NOT included: src/cards/custom/* — the repair_prompt only
# authorizes the eight base game modes. Custom-set fixes go through the
# normal spice-pass workflow with human review.

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [${LOG_TAG}] $*"
}

# Is this changed-file path in the allow-list?
path_allowed() {
  local path="$1"
  for glob in "${ALLOW_GLOBS[@]}"; do
    # shellcheck disable=SC2053 -- glob-on-rhs is intentional
    if [[ "$path" == $glob ]]; then
      return 0
    fi
  done
  return 1
}

process_session() {
  local session_id="$1"
  local session_dir="${REPAIR_DIR}/${session_id}"
  local status_file="${session_dir}/STATUS"
  local processed_marker="${session_dir}/.pushed_to_github"

  if [[ ! -f "$status_file" ]]; then
    return 0
  fi
  if [[ -f "$processed_marker" ]]; then
    return 0  # already handled
  fi

  local first_line
  first_line="$(head -n1 "$status_file" | tr -d '\r')"
  local normalized
  normalized="$(echo "$first_line" | sed -E 's/^[#`* ]+//' | tr '[:lower:]' '[:upper:]')"

  if [[ "$normalized" != DONE* ]]; then
    return 0  # only auto-process DONE; NEED_HUMAN waits for a human
  fi

  log "session=${session_id} STATUS=DONE — capturing patch from container"

  # 1. Snapshot in-container working-tree diff against the baseline image commit.
  local patch_raw
  if ! patch_raw="$(docker exec "$CONTAINER" git -C /app diff HEAD 2>&1)"; then
    log "  ERROR: docker exec git diff failed: ${patch_raw}"
    return 0
  fi
  if [[ -z "${patch_raw// /}" ]]; then
    log "  session=${session_id}: working tree is clean — nothing to push. Marking processed."
    touch "$processed_marker"
    return 0
  fi

  # 2. Enumerate changed files; split into allowed / forbidden.
  local changed_files
  changed_files="$(docker exec "$CONTAINER" git -C /app diff --name-only HEAD || true)"
  local allowed_files=()
  local forbidden_files=()
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if path_allowed "$f"; then
      allowed_files+=("$f")
    else
      forbidden_files+=("$f")
    fi
  done <<<"$changed_files"

  local tainted=0
  if [[ ${#forbidden_files[@]} -gt 0 ]]; then
    tainted=1
    log "  session=${session_id}: TAINTED — ${#forbidden_files[@]} forbidden path(s):"
    for f in "${forbidden_files[@]}"; do
      log "    - $f"
    done
  fi

  if [[ ${#allowed_files[@]} -eq 0 ]]; then
    log "  session=${session_id}: no allowed-path changes; refusing to push."
    {
      printf '%s\n' "REJECTED (all changes outside allow-list):"
      printf '  %s\n' "${forbidden_files[@]}"
    } > "${session_dir}/.rejection_note"
    touch "$processed_marker"
    return 0
  fi

  # 3. Capture the filtered diff (allowed paths only).
  local filtered_diff
  filtered_diff="$(docker exec "$CONTAINER" git -C /app diff HEAD -- "${allowed_files[@]}" 2>&1 || true)"
  if [[ -z "${filtered_diff// /}" ]]; then
    log "  session=${session_id}: filtered diff is empty even though allowed_files=${#allowed_files[@]}; bailing."
    touch "$processed_marker"
    return 0
  fi
  echo "$filtered_diff" > "${session_dir}/patch.diff"

  # 4. Optionally push a branch to GitHub. Requires PAT_FILE + gh CLI.
  if [[ ! -r "$PAT_FILE" ]]; then
    log "  session=${session_id}: no readable PAT at ${PAT_FILE}; patch saved locally only."
    touch "$processed_marker"
    return 0
  fi
  if ! command -v gh >/dev/null 2>&1; then
    log "  session=${session_id}: gh CLI not installed; patch saved locally only."
    touch "$processed_marker"
    return 0
  fi

  local branch="auto-repair/${session_id}"
  local workdir
  workdir="$(mktemp -d)"
  trap "rm -rf '$workdir'" RETURN
  (
    cd "$workdir"
    # Use the PAT for both clone and push via gh's auth setup.
    GH_TOKEN="$(cat "$PAT_FILE")" gh auth setup-git
    GH_TOKEN="$(cat "$PAT_FILE")" git clone --depth 50 "https://github.com/${GITHUB_REPO}.git" repo
    cd repo
    git checkout -b "$branch"
    if ! git apply --whitespace=nowarn "${session_dir}/patch.diff" 2>/dev/null; then
      log "  session=${session_id}: git apply failed against clean main; saving as tainted."
      cp "${session_dir}/patch.diff" "${session_dir}/patch_failed_to_apply.diff"
      tainted=1
      # Still attempt to push the raw diff as a file-only PR for human review.
      mkdir -p auto-repair-artifacts
      cp "${session_dir}/patch.diff" "auto-repair-artifacts/${session_id}.diff"
      git add auto-repair-artifacts
    else
      git add -A
    fi
    if ! git diff --cached --quiet; then
      git -c user.email="auto-repair@hyperdraft.local" \
          -c user.name="hyperdraft auto-repair" \
          commit -m "auto-repair: ${session_id}"
      local title="auto-repair: match ${session_id}"
      [[ $tainted -eq 1 ]] && title="${title} [TAINTED — review forbidden hunks]"
      local body
      body="$(cat <<EOF
Automated draft PR from hyperdraft auto-repair watcher.

Match ID: \`${session_id}\`
Status: \`$(head -n1 "$status_file")\`
$([[ $tainted -eq 1 ]] && printf 'TAINTED: %d hunk(s) dropped; review manually before merge:\n' "${#forbidden_files[@]}" || true)
$([[ ${#forbidden_files[@]} -gt 0 ]] && printf '  - %s\n' "${forbidden_files[@]}" || true)

## STATUS body

\`\`\`
$(cat "$status_file")
\`\`\`

## Repro test

\`tests/auto_repair/${session_id}.py\` (in this diff) reproduces the original crash and turns green on the patched code.

## Verifier

\`\`\`
pytest tests/auto_repair/${session_id}.py -x --tb=short
\`\`\`
EOF
)"
      GH_TOKEN="$(cat "$PAT_FILE")" git push -u origin "$branch" --force
      GH_TOKEN="$(cat "$PAT_FILE")" gh pr create \
        --repo "$GITHUB_REPO" \
        --draft \
        --base main \
        --head "$branch" \
        --title "$title" \
        --body "$body" || log "  session=${session_id}: gh pr create failed (branch pushed; create PR manually)"
      log "  session=${session_id}: branch=${branch} pushed; PR opened"
    else
      log "  session=${session_id}: post-apply diff is empty; no PR created"
    fi
  ) >> "${session_dir}/watcher.log" 2>&1
  trap - RETURN

  touch "$processed_marker"
}

main() {
  if [[ ! -d "$REPAIR_DIR" ]]; then
    log "no repair dir at ${REPAIR_DIR} — has the container started yet?"
    exit 0
  fi
  for session_dir in "${REPAIR_DIR}"/*/; do
    [[ -d "$session_dir" ]] || continue
    local sid
    sid="$(basename "$session_dir")"
    process_session "$sid" || log "  session=${sid}: handler failed (continuing)"
  done
}

main "$@"
