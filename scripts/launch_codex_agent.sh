#!/usr/bin/env bash
# Launches a Codex CLI session that plays the AI seat of an Ultra match
# from start to finish. Spawned by the server when a match is created with
# difficulty=ultra and ultra_agent=codex.
#
# Required env vars: MATCH_ID, AI_PLAYER_ID, GAME_MODE
# Optional env vars: HUMAN_PLAYER_ID, SERVER_BASE (default http://localhost:8030)
# Optional model env vars: CODEX_MODEL or ULTRA_MODEL

set -e
cd "$(dirname "$0")/.."

: "${MATCH_ID:?MATCH_ID env var required}"
: "${AI_PLAYER_ID:?AI_PLAYER_ID env var required}"
: "${GAME_MODE:?GAME_MODE env var required}"
HUMAN_PLAYER_ID="${HUMAN_PLAYER_ID:-unknown}"
SERVER_BASE="${SERVER_BASE:-http://localhost:8030}"
CODEX_MODEL="${CODEX_MODEL:-${ULTRA_MODEL:-}}"

BRIEF="prompts/ultra_ai/${GAME_MODE}.md"
if [ ! -f "$BRIEF" ]; then
    echo "ERROR: Ultra AI brief not found at $BRIEF"
    echo "Available game briefs:"
    ls prompts/ultra_ai/ 2>/dev/null || echo "  (prompts/ultra_ai/ does not exist)"
    exit 1
fi

GAME_MODE_UPPER=$(printf '%s' "$GAME_MODE" | tr '[:lower:]' '[:upper:]')
cat <<BANNER
========================================================================
CODEX ULTRA AI — ${GAME_MODE_UPPER}
========================================================================
Match:  $MATCH_ID
AI:     $AI_PLAYER_ID
Human:  $HUMAN_PLAYER_ID
Server: $SERVER_BASE
Brief:  $BRIEF
Model:  ${CODEX_MODEL:-default}

Launching Codex CLI... it will play the entire game in this session.
========================================================================

BANNER

INITIAL_PROMPT="You are the Codex Ultra AI for a live human-vs-AI ${GAME_MODE} match. A human is playing against you in their browser RIGHT NOW.

Match info:
- MATCH_ID = ${MATCH_ID}
- AI_PLAYER_ID = ${AI_PLAYER_ID}
- HUMAN_PLAYER_ID = ${HUMAN_PLAYER_ID}
- SERVER_BASE = ${SERVER_BASE}
- GAME_MODE = ${GAME_MODE}

Read these BEFORE doing anything else:
1. ${BRIEF} — your full playing brief (action types, choice flow, REST examples)
2. docs/strategy/${GAME_MODE}.md if it exists — accumulated format wisdom

Your job: play the WHOLE GAME in this single session. Use shell commands only for live-match operations such as curl, sleep, and lightweight JSON parsing. Do not edit repository files.

1. Poll game state every 5s while it's NOT your turn:
   curl -s \"\$SERVER_BASE/api/match/\$MATCH_ID/state?player_id=\$AI_PLAYER_ID\"
   (these env vars are already exported in your shell)

2. When active_player == AI_PLAYER_ID, take ONE turn:
   - Decide moves based on hand, board, opponent state, strategy doc
   - Submit each action via POST /api/match/\$MATCH_ID/action with player_id=\$AI_PLAYER_ID
   - **Include a \`reasoning\` field in every action body** — one short sentence
     explaining WHY you picked this move. The server logs it to
     storage/ultra-agent/decisions/\$MATCH_ID.jsonl for retrospective analysis.
     Keep it terse — 1 sentence, ≤120 chars.
   - End the turn with the game-mode-appropriate END_TURN action
   - The active_player will flip back to the human

3. Resume polling. Repeat for the whole game.

4. When is_game_over=true, print final result and stop.

Be patient — humans take 30-90s per turn. Use \`sleep 5\` between polls. Don't spam.

The user can SEE this terminal. Print short status updates between turns so they know you're alive (e.g. 'Waiting for human turn 4...' or 'Taking AI turn 5: deploying X, attacking with Y').

Now start: read the brief, then enter the poll loop."

export MATCH_ID AI_PLAYER_ID HUMAN_PLAYER_ID SERVER_BASE GAME_MODE

TTY_NAME=$(tty)

CODEX_ARGS=(-C "$PWD" --sandbox danger-full-access --ask-for-approval never --no-alt-screen)
if [ -n "$CODEX_MODEL" ]; then
    CODEX_ARGS+=(--model "$CODEX_MODEL")
fi

codex "${CODEX_ARGS[@]}" "$INITIAL_PROMPT" &
CODEX_PID=$!

# --- Watchdog ---
# Polls the match state every 30s. Signals Codex to exit when:
#   * is_game_over=true (match ended), or
#   * no state change for 5 minutes (idle).
STATE_URL="${SERVER_BASE}/api/match/${MATCH_ID}/state?player_id=${AI_PLAYER_ID}"
WATCHDOG_POLL_INTERVAL=30
WATCHDOG_IDLE_LIMIT=300
(
    last_hash=""
    last_change_ts=$(date +%s)
    while kill -0 "$CODEX_PID" 2>/dev/null; do
        sleep "$WATCHDOG_POLL_INTERVAL"
        kill -0 "$CODEX_PID" 2>/dev/null || break

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
                echo "[watchdog] match $MATCH_ID ended; closing window."
                kill "$CODEX_PID" 2>/dev/null || true
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
                    echo "[watchdog] no state change for ${WATCHDOG_IDLE_LIMIT}s; closing window."
                    kill "$CODEX_PID" 2>/dev/null || true
                    break
                fi
                ;;
        esac
    done
) &
WATCHDOG_PID=$!

set +e
wait "$CODEX_PID" 2>/dev/null
CODEX_EXIT=$?
kill "$WATCHDOG_PID" 2>/dev/null
wait "$WATCHDOG_PID" 2>/dev/null
set -e

echo
echo "========================================================================"
echo "Codex Ultra AI session ended (exit=$CODEX_EXIT). Closing window in 3s..."
echo "========================================================================"
sleep 3

case "$(uname -s)" in
    Darwin)
        case "$TERM_PROGRAM" in
            iTerm.app)
                osascript <<APPLESCRIPT
tell application "iTerm"
    repeat with w in windows
        repeat with t in tabs of w
            tell current session of t
                if tty is "$TTY_NAME" then
                    tell w to close
                    return
                end if
            end tell
        end repeat
    end repeat
end tell
APPLESCRIPT
                ;;
            *)
                osascript <<APPLESCRIPT
tell application "Terminal"
    repeat with w in windows
        repeat with t in tabs of w
            if tty of t is "$TTY_NAME" then
                close w saving no
                return
            end if
        end repeat
    end repeat
end tell
APPLESCRIPT
                ;;
        esac
        ;;
    *)
        echo "(close this window when ready)"
        ;;
esac
