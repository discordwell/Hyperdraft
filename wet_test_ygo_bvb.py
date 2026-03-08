"""
YGO Bot-vs-Bot Wet Test

Runs all deck matchups, checks game state quality, detects anomalies.
"""
import requests
import time
import json
import sys

BASE = "http://localhost:8030/api"
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

OPTIMIZED_DECKS = ['goat_control', 'monarch_control', 'chain_burn', 'dragon_beatdown']
STARTER_DECKS = ['yugi', 'kaiba', 'warrior', 'spellcaster']
ALL_DECKS = OPTIMIZED_DECKS + STARTER_DECKS

passed = 0
failed = 0
warnings = []


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        if VERBOSE:
            print(f"  PASS: {label}")
    else:
        failed += 1
        print(f"  FAIL: {label} {detail}")


def warn(msg):
    warnings.append(msg)
    print(f"  WARN: {msg}")


def run_bot_game(deck1, deck2, difficulty="hard", timeout=30):
    """Start a bot game and wait for it to finish."""
    r = requests.post(f"{BASE}/bot-game/start", json={
        "mode": "yugioh",
        "bot1_deck_id": deck1,
        "bot2_deck_id": deck2,
        "bot1_difficulty": difficulty,
        "bot2_difficulty": difficulty,
        "delay_ms": 0,
    })
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text}"
    gid = r.json()["game_id"]

    # Poll until finished
    for _ in range(timeout):
        time.sleep(1)
        status = requests.get(f"{BASE}/bot-game/{gid}/status").json()
        if status["status"] == "finished":
            state = requests.get(f"{BASE}/bot-game/{gid}/state").json()
            return {
                "game_id": gid,
                "turns": status["turn"],
                "winner": status["winner"],
                "state": state,
            }, None
    return None, f"Timeout after {timeout}s (game {gid})"


print("=" * 60)
print("YGO Bot-vs-Bot Wet Test")
print("=" * 60)

# === Test 1: All optimized deck matchups ===
print("\n=== Optimized Deck Round-Robin ===")
matchup_results = []
for i, d1 in enumerate(OPTIMIZED_DECKS):
    for d2 in OPTIMIZED_DECKS[i+1:]:
        label = f"{d1} vs {d2}"
        result, err = run_bot_game(d1, d2)
        if err:
            check(label, False, err)
            continue
        check(f"{label} completed", True)
        check(f"{label} has winner", result["winner"] is not None)
        check(f"{label} turns > 0", result["turns"] > 0)

        # Check game decided (LP=0 or deck-out)
        players = result["state"].get("players", {})
        lp_values = []
        for pid, p in players.items():
            lp_values.append(p.get("lp", -1))
        has_loser = any(p.get("has_lost", False) for p in players.values())
        check(f"{label} game decided", 0 in lp_values or has_loser,
              f"LPs: {lp_values}, has_loser: {has_loser}")
        check(f"{label} winner has LP > 0",
              any(lp > 0 for lp in lp_values),
              f"LPs: {lp_values}")

        matchup_results.append({
            "matchup": label,
            "turns": result["turns"],
            "winner_lp": max(lp_values),
        })
        if VERBOSE:
            print(f"    {label}: {result['turns']} turns, LPs={lp_values}")

# === Test 2: Starter deck matchups (sample) ===
print("\n=== Starter Deck Matchups ===")
starter_matchups = [("yugi", "kaiba"), ("warrior", "spellcaster")]
for d1, d2 in starter_matchups:
    label = f"{d1} vs {d2}"
    result, err = run_bot_game(d1, d2, timeout=30)
    if err:
        check(label, False, err)
        continue
    check(f"{label} completed", True)
    check(f"{label} turns > 0", result["turns"] > 0)
    players = result["state"].get("players", {})
    lp_values = [p.get("lp", -1) for p in players.values()]
    has_loser = any(p.get("has_lost", False) for p in players.values())
    # Starter decks may end by deck-out (valid YGO win) instead of LP=0
    check(f"{label} game decided", 0 in lp_values or has_loser,
          f"LPs: {lp_values}, has_loser: {has_loser}")
    if VERBOSE:
        print(f"    {label}: {result['turns']} turns, LPs={lp_values}")

# === Test 3: Cross-tier matchup (optimized vs starter) ===
print("\n=== Cross-Tier Matchups ===")
cross_matchups = [("goat_control", "yugi"), ("dragon_beatdown", "kaiba")]
for d1, d2 in cross_matchups:
    label = f"{d1} vs {d2}"
    result, err = run_bot_game(d1, d2)
    if err:
        check(label, False, err)
        continue
    check(f"{label} completed", True)
    players = result["state"].get("players", {})
    lp_values = [p.get("lp", -1) for p in players.values()]
    has_loser = any(p.get("has_lost", False) for p in players.values())
    check(f"{label} game decided", 0 in lp_values or has_loser,
          f"LPs: {lp_values}, has_loser: {has_loser}")
    if VERBOSE:
        print(f"    {label}: {result['turns']} turns, LPs={lp_values}")

# === Test 4: Difficulty levels ===
print("\n=== Difficulty Levels ===")
for diff in ["easy", "medium", "hard", "ultra"]:
    label = f"goat vs dragon @ {diff}"
    result, err = run_bot_game("goat_control", "dragon_beatdown", difficulty=diff)
    if err:
        check(label, False, err)
        continue
    check(f"{label} completed", True)
    if VERBOSE:
        players = result["state"].get("players", {})
        lp_values = [p.get("lp", -1) for p in players.values()]
        print(f"    {diff}: {result['turns']} turns, LPs={lp_values}")

# === Test 5: Game state quality checks ===
print("\n=== State Quality Checks ===")
result, err = run_bot_game("monarch_control", "chain_burn")
if err:
    check("quality game started", False, err)
else:
    state = result["state"]
    players = state.get("players", {})

    # Check YGO zones exist (API returns mode-specific fields, not a flat zones dict)
    monster_zones = state.get("monster_zones", {})
    spell_trap_zones = state.get("spell_trap_zones", {})
    graveyards = state.get("graveyard", {})
    for pid in players:
        check(f"monster_zones has {pid}", pid in monster_zones,
              f"Available: {list(monster_zones.keys())}")
        check(f"spell_trap_zones has {pid}", pid in spell_trap_zones,
              f"Available: {list(spell_trap_zones.keys())}")
        check(f"graveyard has {pid}", pid in graveyards,
              f"Available: {list(graveyards.keys())}")

    # Check no negative LP
    for pid, p in players.items():
        lp = p.get("lp", 0)
        check(f"LP not negative ({p.get('name', pid)})", lp >= 0, f"LP={lp}")

    # Check turn number
    check("turn number > 0", result["turns"] > 0)
    check("turn number < 200 (no infinite loop)", result["turns"] < 200,
          f"turns={result['turns']}")

    # Check game is actually over
    has_loser = any(p.get("has_lost", False) for p in players.values())
    check("game has a loser", has_loser)

# === Test 6: Random deck selection ===
print("\n=== Random Deck Selection ===")
result, err = run_bot_game(None, None)  # Both random
if err:
    check("random decks", False, err)
else:
    check("random deck game completed", True)
    check("random deck has winner", result["winner"] is not None)

# === Test 7: Replay data ===
print("\n=== Replay Data ===")
result, err = run_bot_game("goat_control", "monarch_control")
if err:
    check("replay game", False, err)
else:
    gid = result["game_id"]
    replay = requests.get(f"{BASE}/bot-game/{gid}/replay").json()
    check("replay has frames", len(replay.get("frames", [])) > 0,
          f"frames={len(replay.get('frames', []))}")
    check("replay has winner", replay.get("winner") is not None)
    check("replay total_turns > 0", replay.get("total_turns", 0) > 0)

# === Summary ===
print("\n" + "=" * 60)
total = passed + failed
print(f"Results: {passed} passed, {failed} failed out of {total} tests")
if warnings:
    print(f"Warnings: {len(warnings)}")
    for w in warnings:
        print(f"  - {w}")
if matchup_results:
    print(f"\nMatchup Summary:")
    for m in matchup_results:
        print(f"  {m['matchup']}: {m['turns']} turns, winner LP={m['winner_lp']}")
avg_turns = sum(m["turns"] for m in matchup_results) / len(matchup_results) if matchup_results else 0
print(f"  Average turns: {avg_turns:.1f}")

if failed == 0:
    print("\nALL BOT-VS-BOT TESTS PASSED")
else:
    print(f"\n{failed} TESTS FAILED")
    sys.exit(1)
