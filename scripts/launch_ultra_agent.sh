#!/usr/bin/env bash
# Launches a Claude Code session that plays the AI seat of an Ultra match
# from start to finish. Spawned by the server as a plain background
# subprocess; stdout/stderr are redirected to a per-match log file.
#
# Required env vars: MATCH_ID, AI_PLAYER_ID, GAME_MODE
# Optional env vars:
#   HUMAN_PLAYER_ID  default unknown
#   SERVER_BASE      default http://127.0.0.1:8030
#   CLAUDE_MODEL or ULTRA_MODEL
#   WATCHDOG_POLL_INTERVAL  default 30s
#   WATCHDOG_IDLE_LIMIT     default 300s
#
# macOS-Terminal-popup behavior used to live here; that path is now in
# scripts/launch_ultra_agent_local.sh for backwards-compatible local dev.
# In production, the server spawns this via subprocess.Popen and tails
# the log file at storage/ultra-agent/<MATCH_ID>.log.

set -e
cd "$(dirname "$0")/.."

: "${MATCH_ID:?MATCH_ID env var required}"
: "${AI_PLAYER_ID:?AI_PLAYER_ID env var required}"
: "${GAME_MODE:?GAME_MODE env var required}"
HUMAN_PLAYER_ID="${HUMAN_PLAYER_ID:-unknown}"
SERVER_BASE="${SERVER_BASE:-http://127.0.0.1:8030}"
CLAUDE_MODEL="${CLAUDE_MODEL:-${ULTRA_MODEL:-}}"
WATCHDOG_POLL_INTERVAL="${WATCHDOG_POLL_INTERVAL:-30}"
WATCHDOG_IDLE_LIMIT="${WATCHDOG_IDLE_LIMIT:-300}"

BRIEF="prompts/ultra_ai/${GAME_MODE}.md"
if [ ! -f "$BRIEF" ]; then
    echo "ERROR: Ultra AI brief not found at $BRIEF"
    echo "Available game briefs:"
    ls prompts/ultra_ai/ 2>/dev/null || echo "  (prompts/ultra_ai/ does not exist)"
    exit 1
fi

# Persistent strategy doc — read on spawn AND appended at game end.
# The launcher prefers storage/strategy/<mode>.md (in the named volume,
# survives container restarts + carries updates from previous matches)
# and falls back to docs/strategy/<mode>.md (the shipped baseline).
# server/spectator/main.py's lifespan startup seeds storage/strategy/
# from docs/strategy/ on first boot so the file always exists.
STRATEGY_DOC="storage/strategy/${GAME_MODE}.md"
if [ ! -f "$STRATEGY_DOC" ]; then
    STRATEGY_DOC="docs/strategy/${GAME_MODE}.md"
fi

# Per-match scratchpad — claude's working memory across turns. Each AI
# seat has its own so a bot-vs-bot match has two distinct notes files.
SCRATCHPAD_DIR="storage/ultra-agent/notes"
mkdir -p "$SCRATCHPAD_DIR"
SCRATCHPAD="${SCRATCHPAD_DIR}/${MATCH_ID}__${AI_PLAYER_ID}.md"
if [ ! -f "$SCRATCHPAD" ]; then
    cat > "$SCRATCHPAD" <<INIT
# Match ${MATCH_ID} — seat ${AI_PLAYER_ID}

Game: ${GAME_MODE}
Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)

## Pre-game plan

(claude will fill this in before turn 1)

## Turn-by-turn notes

INIT
fi

GAME_MODE_UPPER=$(printf '%s' "$GAME_MODE" | tr '[:lower:]' '[:upper:]')
cat <<BANNER
========================================================================
ULTRA AI — ${GAME_MODE_UPPER}
========================================================================
Match:  $MATCH_ID
AI:     $AI_PLAYER_ID
Human:  $HUMAN_PLAYER_ID
Server: $SERVER_BASE
Brief:  $BRIEF
Model:  ${CLAUDE_MODEL:-default}
Watchdog: poll=${WATCHDOG_POLL_INTERVAL}s idle_limit=${WATCHDOG_IDLE_LIMIT}s

Launching Claude Code... it will play the entire game in this process.
========================================================================

BANNER

INITIAL_PROMPT="You are the Ultra AI for a live human-vs-AI ${GAME_MODE} match. A human is playing against you in their browser RIGHT NOW.

Match info:
- MATCH_ID = ${MATCH_ID}
- AI_PLAYER_ID = ${AI_PLAYER_ID}
- HUMAN_PLAYER_ID = ${HUMAN_PLAYER_ID}
- SERVER_BASE = ${SERVER_BASE}
- GAME_MODE = ${GAME_MODE}

Read these BEFORE doing anything else, IN THIS ORDER:
1. ${BRIEF} — your full playing brief (action types, choice flow, REST examples)
2. ${STRATEGY_DOC} — persistent strategic memory across past games of this
   format. Skim the format principles + per-archetype playbook + known engine
   gaps; these are conclusions you (or a previous Claude pilot) wrote down
   after past matches. They override the brief when they conflict.
3. ${SCRATCHPAD} — YOUR per-match scratchpad. Initialized empty; fill it
   in turn-by-turn. Use it like working memory: write down the opponent's
   archetype as soon as you can read it, write down your win condition,
   note any priority-window observations, jot any 'remember to do X next
   turn' reminders. **Re-read it before every action** so multi-turn plans
   survive across the poll loop.

## Your scratchpad protocol

After EACH OF YOUR TURNS, append a section to ${SCRATCHPAD}:

\`\`\`markdown
### Turn <N> — <UTC time>
- Board state I saw: ...
- What I played: ...
- Why I played it (1 sentence): ...
- Threat I'm tracking for next turn: ...
\`\`\`

Keep entries short — 4-6 lines. The point is to maintain a coherent plan
across turns, not to log every detail.

## End-of-game write-up

When is_game_over=true, BEFORE you exit, append a section to ${STRATEGY_DOC}:

\`\`\`markdown
## Session takeaway — <UTC date>
- **Deck/seat I ran**: ...
- **Opponent**: ...
- **Result**: <win|loss> at turn <N>, final state: ...
- **One mechanical lesson** for next pilot: ...
- **One engine gap** (if any): gap: <description>
\`\`\`

This is how the strategy doc grows. Be brief, be honest, write only the
non-obvious lessons. If the game was unremarkable, write 'unremarkable'
and skip — the doc shouldn't be flooded with trivia.

Your job: play the WHOLE GAME in this single session. Use the Bash tool to:

1. Poll game state every 5s while it's NOT your turn:
   curl -s \"\$SERVER_BASE/api/match/\$MATCH_ID/state?player_id=\$AI_PLAYER_ID\"
   (these env vars are already exported in your shell)

2. When active_player == AI_PLAYER_ID, take ONE turn:
   - Decide moves based on hand, board, opponent state, strategy doc
   - Submit each action via POST /api/match/\$MATCH_ID/action with player_id=\$AI_PLAYER_ID
   - **Include a \`reasoning\` field in every action body** — one short sentence
     explaining WHY you picked this move (e.g. \"trading 2-for-1 to dodge their
     Cycle of Hatred next turn\"). The server logs it to
     storage/ultra-agent/decisions/\$MATCH_ID.jsonl for retrospective analysis;
     a corpus of labelled decisions is what lets the next pilot learn from yours.
     Keep it terse — 1 sentence, ≤120 chars.
   - End the turn with the game-mode-appropriate END_TURN action
   - The active_player will flip back to the human

3. Resume polling. Repeat for the whole game.

4. When is_game_over=true, print final result and stop.

Be patient — humans take 30-90s per turn. Use \`sleep 5\` between polls. Don't spam.

This session is running as a background subprocess; your stdout is being captured to a log file the operator can tail. Print short status updates between turns (e.g. 'Waiting for human turn 4...' or 'Taking AI turn 5: deploying X, attacking with Y').

Now start: read the brief, then enter the poll loop."

export MATCH_ID AI_PLAYER_ID HUMAN_PLAYER_ID SERVER_BASE GAME_MODE

# Run claude in print-once mode (-p) so it works in a non-TTY background
# subprocess. The INITIAL_PROMPT tells claude to enter a poll-and-act
# loop via the Bash tool; claude stays alive across the whole game and
# exits naturally when is_game_over flips. --allowedTools enables the
# tools the playbook actually needs.
#
# Prompt is piped via stdin (not passed as a positional arg) because
# ``--allowedTools`` is variadic and would otherwise eat the prompt
# string as another tool name.
CLAUDE_ARGS=(-p --allowedTools Bash Read Edit Write Glob Grep)
if [ -n "$CLAUDE_MODEL" ]; then
    CLAUDE_ARGS+=(--model "$CLAUDE_MODEL")
fi

# First-run-config restore: a fresh container volume has no
# ~/.claude.json. Claude writes a stub-then-backs-it-up; restoring the
# largest backup (the real config the keychain extraction shipped over)
# skips the "configuration file not found" warning loop. Idempotent.
if [ ! -s /root/.claude.json ] || [ "$(wc -c < /root/.claude.json 2>/dev/null)" -lt 1000 ]; then
    LATEST_BACKUP=$(ls -S /root/.claude/backups/.claude.json.backup.* 2>/dev/null | head -1)
    if [ -n "$LATEST_BACKUP" ]; then
        cp "$LATEST_BACKUP" /root/.claude.json 2>/dev/null || true
    fi
fi

printf '%s' "$INITIAL_PROMPT" | claude "${CLAUDE_ARGS[@]}" &
CLAUDE_PID=$!

# --- Watchdog ---
# Polls the match state every WATCHDOG_POLL_INTERVAL seconds. Signals
# claude to exit when:
#   * is_game_over=true (match ended), or
#   * no state change for WATCHDOG_IDLE_LIMIT seconds (idle).
STATE_URL="${SERVER_BASE}/api/match/${MATCH_ID}/state?player_id=${AI_PLAYER_ID}"
(
    last_hash=""
    last_change_ts=$(date +%s)
    while kill -0 "$CLAUDE_PID" 2>/dev/null; do
        sleep "$WATCHDOG_POLL_INTERVAL"
        kill -0 "$CLAUDE_PID" 2>/dev/null || break

        body=$(curl -fs --max-time 5 "$STATE_URL" 2>/dev/null || true)
        [ -z "$body" ] && continue

        verdict=$(printf '%s' "$body" | python3 -c '
import json, sys, hashlib
try:
    s = json.load(sys.stdin)
except Exception:
    print("ERR")
    sys.exit(0)
tag = "OVER" if s.get("is_game_over") else "OK"
print(tag, hashlib.sha1(json.dumps(s, sort_keys=True).encode()).hexdigest())
' 2>/dev/null || echo "ERR")

        case "$verdict" in
            OVER*)
                echo
                echo "[watchdog] match $MATCH_ID ended; stopping claude."
                kill "$CLAUDE_PID" 2>/dev/null || true
                break
                ;;
            ERR*)
                continue
                ;;
            *)
                hash=${verdict#OK }
                now=$(date +%s)
                if [ "$hash" != "$last_hash" ]; then
                    last_hash="$hash"
                    last_change_ts=$now
                elif [ $((now - last_change_ts)) -ge "$WATCHDOG_IDLE_LIMIT" ]; then
                    echo
                    echo "[watchdog] no state change for ${WATCHDOG_IDLE_LIMIT}s; stopping claude."
                    kill "$CLAUDE_PID" 2>/dev/null || true
                    break
                fi
                ;;
        esac
    done
) &
WATCHDOG_PID=$!

# wait can return non-zero when claude is killed by the watchdog (SIGTERM
# -> 143); that's expected, don't let `set -e` abort cleanup.
set +e
wait "$CLAUDE_PID" 2>/dev/null
CLAUDE_EXIT=$?
kill "$WATCHDOG_PID" 2>/dev/null
wait "$WATCHDOG_PID" 2>/dev/null
set -e

echo
echo "========================================================================"
echo "Ultra AI session ended (exit=$CLAUDE_EXIT)."
echo "========================================================================"
