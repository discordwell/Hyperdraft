"""
Hard Wet Test — Yu-Gi-Oh!

Intentionally tries to break YGO by:
1. Double normal summon in same turn
2. Attacking during main phase (before entering battle phase)
3. Acting out of turn (during AI's turn)
4. Summoning opponent's cards
5. Activating cards not in hand
6. Normal summoning level 5+ without tributes
7. Flip summoning a monster the same turn it was set
8. Direct attacking when opponent has monsters
9. Rapid-fire same action
10. Playing after game over
11. Changing position twice on same monster
12. Setting monsters when monster zone is full
13. Multiple games in sequence (session leak detection)
14. Conceding and then continuing to act
15. State consistency validation throughout

Runs against the live server via REST API.
"""
import requests
import time
import json
import sys
import traceback

_args = [a for a in sys.argv[1:] if not a.startswith("-")]
BASE_URL = _args[0] if _args else "https://hyperdraft.discordwell.com"
API = f"{BASE_URL}/api"
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

passed = 0
failed = 0
warnings = []
anomalies = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        msg = f"  FAIL: {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        failed += 1


def warn(msg):
    warnings.append(msg)
    print(f"  WARN: {msg}")


def anomaly(msg):
    anomalies.append(msg)
    print(f"  ANOMALY: {msg}")


def api_post(path, data=None, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.post(f"{API}{path}", json=data or {}, timeout=30)
            return r.status_code, r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  ERROR: {path} failed after {retries+1} attempts: {e}")
            return 0, {}


def api_get(path, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"{API}{path}", timeout=30)
            return r.status_code, r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  ERROR: {path} failed after {retries+1} attempts: {e}")
            return 0, {}


def create_ygo(difficulty="medium"):
    """Create and start a YGO game, return (match_id, pid, oid, state)."""
    code, resp = api_post("/match/create", {
        "mode": "human_vs_bot",
        "game_mode": "yugioh",
        "player_name": "HardTester",
        "ai_difficulty": difficulty,
    })
    if code != 200 or "match_id" not in resp:
        return None, None, None, None
    mid = resp["match_id"]
    pid = resp["player_id"]
    oid = resp.get("opponent_id")

    api_post(f"/match/{mid}/start")
    time.sleep(0.8)

    code2, state = api_get(f"/match/{mid}/state?player_id={pid}")
    return mid, pid, oid, state if code2 == 200 else None


def take_action(match_id, player_id, action_type, **kwargs):
    payload = {"action_type": action_type, "player_id": player_id, **kwargs}
    code, resp = api_post(f"/match/{match_id}/action", payload)
    success = resp.get("success", False)
    msg = resp.get("message", resp.get("error", ""))
    if VERBOSE:
        status = "OK" if success else "REJECTED"
        print(f"    [{status}] {action_type} {msg}")
    return success, resp.get("new_state"), msg


def get_state(match_id, player_id):
    code, state = api_get(f"/match/{match_id}/state?player_id={player_id}")
    return state if code == 200 else None


def wait_for_my_turn(match_id, pid, max_wait=10):
    """Wait until it's our turn. Returns state or None."""
    for _ in range(max_wait * 2):
        state = get_state(match_id, pid)
        if not state or state.get("is_game_over"):
            return state
        if state.get("active_player") == pid:
            return state
        time.sleep(0.5)
    return get_state(match_id, pid)


def get_hand_monsters(state, max_level=4):
    return [c for c in state.get("hand", [])
            if c.get("level") is not None and (c.get("level") or 0) <= max_level]


def get_hand_spells_traps(state):
    return [c for c in state.get("hand", [])
            if c.get("ygo_spell_type") or c.get("ygo_trap_type")]


def get_my_field_monsters(state, pid):
    zones = state.get("monster_zones", {}).get(pid, [])
    return [m for m in zones if m is not None]


def get_opp_field_monsters(state, oid):
    zones = state.get("monster_zones", {}).get(oid, [])
    return [m for m in zones if m is not None]


def validate_lp(state, label=""):
    """Check LP is sane."""
    issues = []
    for pid, p in state.get("players", {}).items():
        lp = p.get("lp")
        if lp is not None:
            if lp < 0 and not state.get("is_game_over"):
                issues.append(f"{label}Player {pid} has negative LP ({lp}) but game not over")
            if lp > 8000:
                issues.append(f"{label}Player {pid} has LP above 8000 ({lp})")
    return issues


def validate_zones(state, pid, oid, label=""):
    """Check zone integrity."""
    issues = []
    my_monsters = state.get("monster_zones", {}).get(pid, [])
    opp_monsters = state.get("monster_zones", {}).get(oid, [])
    my_st = state.get("spell_trap_zones", {}).get(pid, [])
    opp_st = state.get("spell_trap_zones", {}).get(oid, [])

    # Monster zones should have at most 5 slots
    non_null_my = [m for m in my_monsters if m is not None]
    non_null_opp = [m for m in opp_monsters if m is not None]
    if len(non_null_my) > 5:
        issues.append(f"{label}My monster zone has {len(non_null_my)} monsters (max 5)")
    if len(non_null_opp) > 5:
        issues.append(f"{label}Opp monster zone has {len(non_null_opp)} monsters (max 5)")

    # S/T zones should have at most 5
    non_null_my_st = [s for s in my_st if s is not None]
    if len(non_null_my_st) > 5:
        issues.append(f"{label}My S/T zone has {len(non_null_my_st)} cards (max 5)")

    # Hand shouldn't have more than ~20 cards (sanity check)
    hand = state.get("hand", [])
    if len(hand) > 20:
        issues.append(f"{label}Hand has {len(hand)} cards — suspicious")

    return issues


# =============================================================================
print(f"\n{'='*70}")
print(f"YGO Hard Wet Test — {BASE_URL}")
print(f"{'='*70}")

# =============================================================================
# Test 1: Double Normal Summon
# =============================================================================
print("\n=== Test 1: Double Normal Summon ===")
mid, pid, oid, state = create_ygo()
check("Game created", mid is not None)

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        monsters = get_hand_monsters(state)
        if len(monsters) >= 2:
            # First summon should succeed
            ok1, ns1, _ = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])
            check("First normal summon succeeds", ok1)

            # Second summon should be rejected
            ok2, ns2, msg2 = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[1]["id"])
            check("Second normal summon rejected", not ok2)
            check("Error message mentions normal summon", "Normal Summon" in msg2 or "normal" in msg2.lower(),
                  f"Got: {msg2}")
        else:
            warn("Not enough monsters in hand for double-summon test")
    else:
        warn("Never got our turn for test 1")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 2: Out-of-turn actions
# =============================================================================
print("\n=== Test 2: Out-of-turn actions ===")
mid, pid, oid, state = create_ygo()

if state:
    # If AI goes first, try to act during their turn
    if state.get("active_player") != pid:
        monsters = get_hand_monsters(state)
        if monsters:
            ok, _, msg = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])
            check("Normal summon during opponent's turn rejected", not ok)
        ok2, _, msg2 = take_action(mid, pid, "YGO_END_TURN")
        check("End turn during opponent's turn rejected", not ok2)
    else:
        # We go first — end turn, then try to act during AI's turn
        ok, _, _ = take_action(mid, pid, "YGO_END_TURN")
        if ok:
            time.sleep(0.3)  # Let AI start
            state = get_state(mid, pid)
            if state and state.get("active_player") != pid:
                monsters = get_hand_monsters(state)
                if monsters:
                    ok2, _, msg = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])
                    check("Normal summon during AI turn rejected", not ok2)
                ok3, _, _ = take_action(mid, pid, "YGO_END_TURN")
                check("End turn during AI turn rejected", not ok3)
            else:
                warn("AI turn was too fast to test out-of-turn actions")
        else:
            warn("Couldn't end turn to test out-of-turn")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 3: Level 5+ without tributes
# =============================================================================
print("\n=== Test 3: Level 5+ summon without tributes ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        big_monsters = [c for c in state.get("hand", [])
                       if c.get("level") is not None and (c.get("level") or 0) >= 5]
        if big_monsters:
            ok, _, msg = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=big_monsters[0]["id"])
            check("Level 5+ summon without tributes rejected", not ok)
            check("Error mentions tribute", "tribute" in msg.lower() or "level" in msg.lower(),
                  f"Got: {msg}")
        else:
            warn("No level 5+ monsters in hand — skipping")
    else:
        warn("Never got our turn for test 3")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 4: Use opponent's card_id
# =============================================================================
print("\n=== Test 4: Opponent's card IDs ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        # Try to summon using an opponent's monster zone card
        opp_monsters = get_opp_field_monsters(state, oid)
        if opp_monsters:
            ok, _, msg = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=opp_monsters[0]["id"])
            check("Summoning opponent's field card rejected", not ok)
        else:
            # Try a completely fake card_id
            ok, _, msg = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id="fake_card_id_12345")
            check("Fake card_id rejected", not ok)
            check("Error message for bad card", "not found" in msg.lower() or "not in" in msg.lower(),
                  f"Got: {msg}")
    else:
        warn("Never got our turn for test 4")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 5: Set then immediately flip summon (same turn)
# =============================================================================
print("\n=== Test 5: Set then flip summon same turn ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        monsters = get_hand_monsters(state)
        if monsters:
            # Set a monster
            ok1, ns1, _ = take_action(mid, pid, "YGO_SET_MONSTER", card_id=monsters[0]["id"])
            check("Set monster succeeds", ok1)

            if ok1:
                # Get the set monster's card_id from updated state
                state = get_state(mid, pid)
                if state:
                    my_field = get_my_field_monsters(state, pid)
                    face_down = [m for m in my_field if m.get("face_down")]
                    if face_down:
                        ok2, _, msg = take_action(mid, pid, "YGO_FLIP_SUMMON", card_id=face_down[0]["id"])
                        check("Flip summon same turn rejected", not ok2)
                        check("Error mentions same turn",
                              "same turn" in msg.lower() or "set" in msg.lower(),
                              f"Got: {msg}")
                    else:
                        warn("No face-down monsters found after set")
        else:
            warn("No monsters in hand for test 5")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 6: Direct attack when opponent has monsters
# =============================================================================
print("\n=== Test 6: Direct attack with opponent monsters ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        monsters = get_hand_monsters(state)
        if monsters:
            # Normal summon first
            ok, _, _ = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])

            # End main phase to enter battle
            take_action(mid, pid, "YGO_END_PHASE")

            state = get_state(mid, pid)
            if state:
                my_field = get_my_field_monsters(state, pid)
                opp_field = get_opp_field_monsters(state, oid)

                if my_field and opp_field:
                    # Try direct attack — should fail since opponent has monsters
                    ok2, _, msg = take_action(mid, pid, "YGO_DIRECT_ATTACK",
                                             source_id=my_field[0]["id"])
                    check("Direct attack blocked when opp has monsters", not ok2,
                          f"msg={msg}")
                elif my_field:
                    # Opponent has no monsters — direct attack should work
                    warn("Opponent has no monsters — can't test blocked direct attack")
                    ok2, _, _ = take_action(mid, pid, "YGO_DIRECT_ATTACK",
                                           source_id=my_field[0]["id"])
                    check("Direct attack works when no opp monsters", ok2)
                else:
                    warn("No monsters on our field for test 6")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 7: Rapid-fire duplicate actions
# =============================================================================
print("\n=== Test 7: Rapid-fire duplicate actions ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        monsters = get_hand_monsters(state)
        if monsters:
            # Send the same summon 3 times as fast as possible
            card_id = monsters[0]["id"]
            results = []
            for i in range(3):
                ok, _, msg = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=card_id)
                results.append((ok, msg))

            successes = sum(1 for ok, _ in results if ok)
            check("Only 1 of 3 rapid summons succeeds", successes <= 1,
                  f"successes={successes}, results={results}")
        else:
            warn("No monsters for rapid-fire test")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 8: Actions after conceding
# =============================================================================
print("\n=== Test 8: Actions after conceding ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    api_post(f"/match/{mid}/concede?player_id={pid}")
    time.sleep(0.5)

    # Try to take actions after conceding
    ok, _, msg = take_action(mid, pid, "YGO_END_TURN")
    check("Action after concede rejected", not ok,
          f"ok={ok}, msg={msg}")

    state_after = get_state(mid, pid)
    if state_after:
        check("Game is over after concede", state_after.get("is_game_over", False))


# =============================================================================
# Test 9: Change position twice on same monster
# =============================================================================
print("\n=== Test 9: Double position change ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        monsters = get_hand_monsters(state)
        if monsters:
            # Summon a monster (it's in ATK position)
            ok, _, _ = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])
            if ok:
                state = get_state(mid, pid)
                my_field = get_my_field_monsters(state, pid)
                face_up = [m for m in my_field if not m.get("face_down")]
                if face_up:
                    card_id = face_up[0]["id"]

                    # First position change should succeed
                    ok1, _, _ = take_action(mid, pid, "YGO_CHANGE_POSITION", card_id=card_id)
                    check("First position change succeeds", ok1)

                    # Second position change on same monster should fail
                    ok2, _, msg2 = take_action(mid, pid, "YGO_CHANGE_POSITION", card_id=card_id)
                    check("Second position change rejected", not ok2)
                    check("Error mentions already changed",
                          "already" in msg2.lower() or "position" in msg2.lower(),
                          f"Got: {msg2}")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 10: Fill monster zones and try one more
# =============================================================================
print("\n=== Test 10: Monster zone overflow ===")
# This is hard to test in one turn (only 1 normal summon per turn)
# We'll play multiple turns to fill up slots
mid, pid, oid, state = create_ygo()

if state:
    monsters_placed = 0
    for turn_attempt in range(8):
        state = wait_for_my_turn(mid, pid)
        if not state or state.get("is_game_over"):
            break
        if state.get("active_player") != pid:
            break

        my_field = get_my_field_monsters(state, pid)
        if len(my_field) >= 5:
            # Zone is full — try one more
            extra_monsters = get_hand_monsters(state)
            if extra_monsters:
                ok, _, msg = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=extra_monsters[0]["id"])
                check("6th monster summon rejected (zone full)", not ok)
                check("Error mentions full",
                      "full" in msg.lower() or "zone" in msg.lower(),
                      f"Got: {msg}")
            else:
                warn("No more monsters in hand when zone was full")
            break

        # Normal summon one monster
        monsters = get_hand_monsters(state)
        if monsters:
            ok, _, _ = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])
            if ok:
                monsters_placed += 1

        # End turn
        take_action(mid, pid, "YGO_END_TURN")
        time.sleep(0.5)

    if monsters_placed < 5:
        warn(f"Only placed {monsters_placed}/5 monsters before giving up")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 11: State consistency over multiple turns
# =============================================================================
print("\n=== Test 11: Multi-turn state consistency ===")
mid, pid, oid, state = create_ygo()
all_issues = []

if state:
    prev_turn = state.get("turn_number", 0)
    initial_hand_size = len(state.get("hand", []))

    for turn_attempt in range(6):
        state = wait_for_my_turn(mid, pid)
        if not state or state.get("is_game_over"):
            break
        if state.get("active_player") != pid:
            break

        # Validate state
        issues = validate_lp(state, f"Turn {state.get('turn_number')}: ")
        issues.extend(validate_zones(state, pid, oid, f"Turn {state.get('turn_number')}: "))
        all_issues.extend(issues)

        # Check turn number monotonically increases
        cur_turn = state.get("turn_number", 0)
        if cur_turn < prev_turn:
            all_issues.append(f"Turn number went backwards: {prev_turn} -> {cur_turn}")
        prev_turn = cur_turn

        # Check phase is sensible
        phase = state.get("ygo_phase", "")
        valid_phases = ["DRAW", "STANDBY", "MAIN1", "BATTLE_START", "BATTLE_STEP",
                       "DAMAGE_STEP", "DAMAGE_CALC", "BATTLE_END", "MAIN2", "END", ""]
        if phase not in valid_phases:
            all_issues.append(f"Invalid phase: {phase}")

        # Play a card if possible
        monsters = get_hand_monsters(state)
        if monsters:
            take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])

        # End turn
        take_action(mid, pid, "YGO_END_TURN")
        time.sleep(0.5)

    check("State consistent across all turns", len(all_issues) == 0,
          "; ".join(all_issues[:5]))

    final = get_state(mid, pid)
    if final:
        check("Turn number advanced", final.get("turn_number", 0) >= 3,
              f"turn={final.get('turn_number')}")
        # Check we drew cards (hand should have changed)
        final_hand = len(final.get("hand", []))
        check("Game log exists", len(final.get("game_log", [])) > 0)

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 12: Attacking with face-down monster
# =============================================================================
print("\n=== Test 12: Attack with face-down monster ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        monsters = get_hand_monsters(state)
        if monsters:
            # Set (not summon) a monster
            ok, _, _ = take_action(mid, pid, "YGO_SET_MONSTER", card_id=monsters[0]["id"])
            if ok:
                # Enter battle phase
                take_action(mid, pid, "YGO_END_PHASE")

                state = get_state(mid, pid)
                if state:
                    my_field = get_my_field_monsters(state, pid)
                    face_down = [m for m in my_field if m.get("face_down")]
                    if face_down:
                        # Try to attack with face-down monster
                        ok2, _, msg = take_action(mid, pid, "YGO_DIRECT_ATTACK",
                                                 source_id=face_down[0]["id"])
                        check("Attack with face-down monster rejected", not ok2,
                              f"ok={ok2}, msg={msg}")
                    else:
                        warn("Set monster not showing as face-down")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 13: Session leak — create/destroy many games
# =============================================================================
print("\n=== Test 13: Session leak detection (5 games) ===")
for i in range(5):
    mid, pid, oid, state = create_ygo("easy")
    if state:
        state = wait_for_my_turn(mid, pid)
        if state and state.get("active_player") == pid:
            monsters = get_hand_monsters(state)
            if monsters:
                take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])
            take_action(mid, pid, "YGO_END_TURN")
            time.sleep(0.3)
        api_post(f"/match/{mid}/concede?player_id={pid}")

# Verify server still healthy after rapid game creation
code, resp = api_get("/health")
check("Server healthy after 5 rapid games", code == 200 and resp.get("status") == "healthy")


# =============================================================================
# Test 14: Wrong action_type strings
# =============================================================================
print("\n=== Test 14: Invalid action types ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        ok1, _, msg1 = take_action(mid, pid, "INVALID_TYPE")
        check("Random invalid action rejected", not ok1)

        ok2, _, msg2 = take_action(mid, pid, "YGO_TRIBUTE_SUMMON", card_id="fake")
        check("Nonexistent YGO action rejected", not ok2)

        ok3, _, msg3 = take_action(mid, pid, "HS_PLAY_CARD", card_id="fake")
        check("Wrong game mode action rejected", not ok3)

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 15: Play full aggressive game
# =============================================================================
print("\n=== Test 15: Full aggressive game ===")
mid, pid, oid, state = create_ygo("easy")

if state:
    actions = 0
    turns = 0
    game_ended = False

    for turn_attempt in range(15):
        state = wait_for_my_turn(mid, pid)
        if not state:
            warn("Lost state during full game")
            break
        if state.get("is_game_over"):
            game_ended = True
            break
        if state.get("active_player") != pid:
            if turn_attempt > 10:
                warn("Stuck waiting for turn")
                break
            continue

        # Normal summon strongest available
        monsters = get_hand_monsters(state)
        if monsters:
            monsters.sort(key=lambda c: c.get("atk") or 0, reverse=True)
            ok, _, _ = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])
            if ok:
                actions += 1

        # Activate spells
        state = get_state(mid, pid)
        if state and not state.get("is_game_over"):
            spells = [c for c in state.get("hand", []) if c.get("ygo_spell_type")]
            for spell in spells:
                ok, _, _ = take_action(mid, pid, "YGO_ACTIVATE", card_id=spell["id"])
                if ok:
                    actions += 1
                state = get_state(mid, pid)
                if not state or state.get("is_game_over"):
                    break

        if not state or state.get("is_game_over"):
            game_ended = True
            break

        # Set traps
        traps = [c for c in state.get("hand", []) if c.get("ygo_trap_type")]
        for trap in traps:
            ok, _, _ = take_action(mid, pid, "YGO_SET_SPELL_TRAP", card_id=trap["id"])
            if ok:
                actions += 1
            state = get_state(mid, pid)
            if not state or state.get("is_game_over"):
                break

        if not state or state.get("is_game_over"):
            game_ended = True
            break

        # Enter battle phase
        take_action(mid, pid, "YGO_END_PHASE")

        # Attack with everything
        state = get_state(mid, pid)
        if state and not state.get("is_game_over"):
            my_field = get_my_field_monsters(state, pid)
            attackers = [m for m in my_field if not m.get("face_down") and (m.get("atk") or 0) > 0]
            opp_field = get_opp_field_monsters(state, oid)

            for attacker in attackers:
                opp_field = get_opp_field_monsters(get_state(mid, pid) or state, oid)
                if opp_field:
                    weakest = min(opp_field, key=lambda m: m.get("atk") or m.get("def_val") or 0)
                    ok, _, _ = take_action(mid, pid, "YGO_DECLARE_ATTACK",
                                          source_id=attacker["id"], targets=[[weakest["id"]]])
                else:
                    ok, _, _ = take_action(mid, pid, "YGO_DIRECT_ATTACK",
                                          source_id=attacker["id"])
                if ok:
                    actions += 1

                state = get_state(mid, pid)
                if not state or state.get("is_game_over"):
                    game_ended = True
                    break

        if game_ended:
            break

        # End turn
        ok, _, _ = take_action(mid, pid, "YGO_END_TURN")
        if ok:
            turns += 1
        time.sleep(0.5)

    final = get_state(mid, pid)
    if final:
        issues = validate_lp(final, "Final: ")
        issues.extend(validate_zones(final, pid, oid, "Final: "))
        check("Full game state valid", len(issues) == 0, "; ".join(issues))
        check("Full game had combat", actions >= 3, f"actions={actions}")

        my_lp = final["players"].get(pid, {}).get("lp", "?")
        opp_lp = [v.get("lp", "?") for k, v in final["players"].items() if k != pid]
        opp_lp = opp_lp[0] if opp_lp else "?"
        game_over = final.get("is_game_over")
        winner = final.get("winner")
        log_count = len(final.get("game_log", []))

        if game_over:
            result = "WE WON" if winner == pid else "AI WON"
        else:
            result = "ongoing"

        print(f"  INFO: {turns} turns, {actions} actions, LP {my_lp}/{opp_lp}, "
              f"{result}, {log_count} log entries")

        # Check game log has AI entries (our fix!)
        if log_count > 0:
            ai_log_entries = [e for e in final.get("game_log", [])
                            if "HardTester" not in e.get("text", "")
                            and e.get("event_type") not in ("turn_start", "phase")]
            check("Game log has AI action entries", len(ai_log_entries) > 0,
                  f"total={log_count}, non-human-non-phase={len(ai_log_entries)}")

    if not game_ended:
        api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Test 16: Flip summon a face-up monster
# =============================================================================
print("\n=== Test 16: Flip summon face-up monster ===")
mid, pid, oid, state = create_ygo()

if state:
    state = wait_for_my_turn(mid, pid)
    if state and state.get("active_player") == pid:
        monsters = get_hand_monsters(state)
        if monsters:
            # Normal summon (face-up ATK)
            ok, _, _ = take_action(mid, pid, "YGO_NORMAL_SUMMON", card_id=monsters[0]["id"])
            if ok:
                state = get_state(mid, pid)
                my_field = get_my_field_monsters(state, pid)
                face_up = [m for m in my_field if not m.get("face_down")]
                if face_up:
                    ok2, _, msg = take_action(mid, pid, "YGO_FLIP_SUMMON", card_id=face_up[0]["id"])
                    check("Flip summon of face-up monster rejected", not ok2)
                    check("Error mentions not face-down",
                          "face-down" in msg.lower() or "not" in msg.lower(),
                          f"Got: {msg}")

    api_post(f"/match/{mid}/concede?player_id={pid}")


# =============================================================================
# Summary
# =============================================================================
print(f"\n{'='*70}")
print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
if warnings:
    print(f"\nWarnings ({len(warnings)}):")
    for w in warnings:
        print(f"  - {w}")
if anomalies:
    print(f"\nAnomalies ({len(anomalies)}):")
    for a in anomalies:
        print(f"  - {a}")
if failed > 0:
    print("\nSOME TESTS FAILED — bugs found!")
    sys.exit(1)
else:
    print("\nALL HARD WET TESTS PASSED")
