#!/usr/bin/env bash
#
# Domain-scoped CI pre-flight. Mirrors .github/workflows/ci.yml but runs only
# the tests relevant to one game/domain, plus an always-on check for untracked
# files imported by tracked code.
#
# Usage:
#   scripts/ci_quick.sh                # full (matches GitHub CI)
#   scripts/ci_quick.sh finance        # finance backend + tsc if frontend touched
#   scripts/ci_quick.sh depths         # depths + SUBS
#   scripts/ci_quick.sh minecraft
#   scripts/ci_quick.sh pokemon | yugioh | hearthstone | mtg | deckbuilder
#
# Skills should pass their game name explicitly. If shared engine/server code
# is touched, the script auto-escalates to 'full' regardless of the argument.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

DOMAIN="${1:-full}"

# ---------- 1. Untracked files imported by tracked code (always) ----------
# Domain-scoped pytest doesn't import every module, so a tracked file that
# imports a brand-new untracked file will silently pass locally and explode
# in CI. This check closes that gap.
echo "==> Checking untracked-but-imported files..."
bad=0
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    case "$f" in
        *.py)
            # src/server/services/game_registry.py -> src.server.services.game_registry
            module="${f%.py}"
            module="${module//\//.}"
            if git grep -qE "(^|[^.])(from|import)[[:space:]]+${module}([[:space:]]|\.|\$)" -- 'src' 'tests' 'scripts' 2>/dev/null; then
                echo "  FAIL  $f imported by tracked code as '$module' but not tracked"
                bad=1
            fi
            ;;
        *.ts|*.tsx)
            stem=$(basename "${f%.*}")
            if git grep -qE "from[[:space:]]+['\"][^'\"]*/${stem}['\"]" -- 'frontend/src' 2>/dev/null; then
                echo "  FAIL  $f imported by tracked code as '.../${stem}' but not tracked"
                bad=1
            fi
            ;;
    esac
done < <(git ls-files --others --exclude-standard -- 'src/' 'frontend/src/' 'tests/' 'scripts/')
if [[ $bad -eq 1 ]]; then
    echo
    echo "Run 'git add' on the flagged files (or remove the imports) before pushing."
    exit 1
fi
echo "    OK"

# ---------- 2. Auto-escalate to 'full' if shared infra changed ----------
shared_changed=0
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    case "$f" in
        src/engine/game.py|src/engine/pipeline/*|src/engine/state.py|\
        src/engine/events.py|src/engine/interceptors.py|\
        src/engine/interceptor_helpers.py|src/engine/turn.py|\
        src/engine/mana.py|src/engine/combat.py|src/engine/casting_costs.py|\
        src/engine/cost_query.py|src/engine/cast_permission.py|\
        src/decks/deck.py|src/decks/__init__.py|\
        src/server/main.py|src/server/services/game_registry.py|\
        src/server/services/deck_storage.py|\
        src/server/routes/match.py|src/server/routes/deckbuilder.py|\
        requirements-server.txt|requirements.txt|pytest.ini)
            shared_changed=1
            ;;
    esac
done < <({ git diff --name-only HEAD; git diff --name-only --cached; git ls-files --others --exclude-standard; } | sort -u)

if [[ "$DOMAIN" != "full" && $shared_changed -eq 1 ]]; then
    echo "==> Shared infra changed — escalating from '$DOMAIN' to 'full'."
    DOMAIN="full"
fi

# ---------- 3. Backend tests ----------
echo "==> Backend tests ($DOMAIN)..."
export PYTHONPATH=.
case "$DOMAIN" in
    full)
        pytest -q
        ;;
    finance)
        pytest -q tests/test_finance*.py
        ;;
    minecraft)
        pytest -q tests/test_minecraft*.py
        ;;
    depths)
        pytest -q tests/test_depths*.py tests/test_subs.py
        ;;
    pokemon)
        pytest -q tests/test_pokemon*.py
        ;;
    yugioh)
        pytest -q tests/test_yugioh*.py
        ;;
    hearthstone)
        pytest -q tests/hearthstone tests/test_hearthstone*.py
        ;;
    deckbuilder)
        pytest -q tests/test_deckbuilder*.py
        ;;
    mtg)
        pytest -q \
            --ignore-glob='tests/test_finance*' \
            --ignore-glob='tests/test_minecraft*' \
            --ignore-glob='tests/test_depths*' \
            --ignore-glob='tests/test_subs.py' \
            --ignore-glob='tests/test_pokemon*' \
            --ignore-glob='tests/test_yugioh*' \
            --ignore-glob='tests/test_hearthstone*' \
            --ignore=tests/hearthstone
        ;;
    *)
        echo "  WARN  unknown domain '$DOMAIN' — falling through to 'full'." >&2
        echo "  (Known: full finance minecraft depths pokemon yugioh hearthstone mtg deckbuilder.)" >&2
        echo "  (To scope a new engine, add a case to scripts/ci_quick.sh.)" >&2
        pytest -q
        ;;
esac

# ---------- 4. Frontend (only if frontend touched) ----------
if [[ -n "$(git status --porcelain -- frontend/ 2>/dev/null)" ]]; then
    echo "==> Frontend touched — running tsc + vite build..."
    (cd frontend && npm run build > /tmp/ci_quick_fe.log 2>&1) || {
        echo "Frontend build failed:"
        cat /tmp/ci_quick_fe.log
        exit 1
    }
    echo "    OK"
else
    echo "==> Frontend untouched — skipping tsc."
fi

echo
echo "ci_quick: $DOMAIN passed."
