#!/usr/bin/env bash
# Launches a Claude Code session that plays the AI seat of an Ultra match
# from start to finish. Spawned by the server (via osascript) when a match is
# created with difficulty=ultra.
#
# Required env vars: MATCH_ID, AI_PLAYER_ID, GAME_MODE
# Optional env vars: HUMAN_PLAYER_ID, SERVER_BASE (default http://localhost:8030)

set -e
cd "$(dirname "$0")/.."

: "${MATCH_ID:?MATCH_ID env var required}"
: "${AI_PLAYER_ID:?AI_PLAYER_ID env var required}"
: "${GAME_MODE:?GAME_MODE env var required}"
HUMAN_PLAYER_ID="${HUMAN_PLAYER_ID:-unknown}"
SERVER_BASE="${SERVER_BASE:-http://localhost:8030}"

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
ULTRA AI — ${GAME_MODE_UPPER}
========================================================================
Match:  $MATCH_ID
AI:     $AI_PLAYER_ID
Human:  $HUMAN_PLAYER_ID
Server: $SERVER_BASE
Brief:  $BRIEF

Launching Claude Code... it will play the entire game in this session.
========================================================================

BANNER

INITIAL_PROMPT="You are the Ultra AI for a live human-vs-AI ${GAME_MODE} match. A human is playing against you in their browser RIGHT NOW.

Match info:
- MATCH_ID = ${MATCH_ID}
- AI_PLAYER_ID = ${AI_PLAYER_ID}
- HUMAN_PLAYER_ID = ${HUMAN_PLAYER_ID}
- SERVER_BASE = ${SERVER_BASE}
- GAME_MODE = ${GAME_MODE}

Read these BEFORE doing anything else:
1. ${BRIEF} — your full playing brief (action types, choice flow, REST examples)
2. docs/strategy/${GAME_MODE}.md if it exists — accumulated format wisdom

Your job: play the WHOLE GAME in this single session. Use the Bash tool to:

1. Poll game state every 5s while it's NOT your turn:
   curl -s \"\$SERVER_BASE/api/match/\$MATCH_ID/state?player_id=\$AI_PLAYER_ID\"
   (these env vars are already exported in your shell)

2. When active_player == AI_PLAYER_ID, take ONE turn:
   - Decide moves based on hand, board, opponent state, strategy doc
   - Submit each action via POST /api/match/\$MATCH_ID/action with player_id=\$AI_PLAYER_ID
   - End the turn with the game-mode-appropriate END_TURN action
   - The active_player will flip back to the human

3. Resume polling. Repeat for the whole game.

4. When is_game_over=true, print final result and stop.

Be patient — humans take 30-90s per turn. Use \`sleep 5\` between polls. Don't spam.

The user can SEE this terminal. Print short status updates between turns so they know you're alive (e.g. 'Waiting for human turn 4...' or 'Taking AI turn 5: deploying X, attacking with Y').

Now start: read the brief, then enter the poll loop."

export MATCH_ID AI_PLAYER_ID HUMAN_PLAYER_ID SERVER_BASE GAME_MODE

# Capture this shell's TTY so we can close the right Terminal window after.
TTY_NAME=$(tty)

# Run claude (NOT exec — we need to run cleanup after it exits).
claude "$INITIAL_PROMPT"
CLAUDE_EXIT=$?

echo
echo "========================================================================"
echo "Ultra AI session ended (exit=$CLAUDE_EXIT). Closing window in 3s..."
echo "========================================================================"
sleep 3

# Try to auto-close the terminal window. Only macOS Terminal.app and iTerm2
# are supported; on Linux/Windows the shell just exits and the terminal
# emulator decides what to do per its own settings.
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

