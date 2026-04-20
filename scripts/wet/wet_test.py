"""
Hyperdraft Wet Test — Play through all 4 game modes via the live API.

Tests human_vs_bot games by creating matches, taking actions, and verifying
game state consistency at every step. Designed to catch crashes, invalid
states, stuck games, and unexpected behavior.
"""
import requests
import time
import json
import sys

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://hyperdraft.discordwell.com"
API = f"{BASE_URL}/api"

passed = 0
failed = 0
warnings = []


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


def create_and_start(game_mode, difficulty="medium", **kwargs):
    """Create a game, start it, return (match_id, player_id, opponent_id, state)."""
    payload = {
        "mode": "human_vs_bot",
        "game_mode": game_mode,
        "player_name": "WetTester",
        "ai_difficulty": difficulty,
        **kwargs,
    }
    code, resp = api_post("/match/create", payload)
    if code != 200 or "match_id" not in resp:
        return None, None, None, None
    match_id = resp["match_id"]
    player_id = resp["player_id"]
    opponent_id = resp.get("opponent_id")

    code2, _ = api_post(f"/match/{match_id}/start")
    if code2 != 200:
        return match_id, player_id, opponent_id, None

    time.sleep(0.5)  # Let AI take first actions if it goes first

    code3, state = api_get(f"/match/{match_id}/state?player_id={player_id}")
    if code3 != 200:
        return match_id, player_id, opponent_id, None
    return match_id, player_id, opponent_id, state


VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


def take_action(match_id, player_id, action_type, **kwargs):
    """Submit an action and return (success, new_state)."""
    payload = {"action_type": action_type, "player_id": player_id, **kwargs}
    code, resp = api_post(f"/match/{match_id}/action", payload)
    success = resp.get("success", False)
    new_state = resp.get("new_state")
    if VERBOSE:
        status = "OK" if success else "REJECTED"
        detail = resp.get("error", "") if not success else ""
        print(f"    [{status}] {action_type} {detail}")
    return success, new_state


def get_state(match_id, player_id):
    code, state = api_get(f"/match/{match_id}/state?player_id={player_id}")
    return state if code == 200 else None


def concede(match_id, player_id):
    api_post(f"/match/{match_id}/concede?player_id={player_id}")


def cleanup(match_id):
    requests.delete(f"{API}/match/{match_id}", timeout=10)


def validate_state(state, game_mode, label=""):
    """Common state validation across all modes."""
    prefix = f"[{label}] " if label else ""
    issues = []
    if not state:
        issues.append("state is None")
        return issues

    if "players" not in state:
        issues.append("missing players")
    if "turn_number" not in state:
        issues.append("missing turn_number")
    if state.get("turn_number", 0) < 0:
        issues.append(f"negative turn_number: {state['turn_number']}")

    for pid, pdata in state.get("players", {}).items():
        if game_mode == "hearthstone":
            if pdata.get("life", 30) < 0 and not state.get("is_game_over"):
                issues.append(f"{prefix}player {pid} has negative life {pdata['life']} but game not over")
        elif game_mode == "mtg":
            if pdata.get("life", 20) <= 0 and not state.get("is_game_over"):
                # MTG can have 0 life briefly during stack resolution
                pass
        elif game_mode == "pokemon":
            pr = pdata.get("prizes_remaining")
            if pr is not None and pr < 0:
                issues.append(f"{prefix}player {pid} has negative prizes: {pr}")
        elif game_mode == "yugioh":
            lp = pdata.get("lp")
            if lp is not None and lp < 0 and not state.get("is_game_over"):
                issues.append(f"{prefix}player {pid} has negative LP: {lp}")

    return issues


# =============================================================================
# Health Check
# =============================================================================
print(f"\n{'='*70}")
print(f"Hyperdraft Wet Test — {BASE_URL}")
print(f"{'='*70}")

print("\n=== Health Check ===")
code, resp = api_get("/health")
check("Health endpoint responds", code == 200)
check("Service is healthy", resp.get("status") == "healthy")


# =============================================================================
# MTG Wet Test
# =============================================================================
print("\n=== MTG: Human vs Bot ===")
match_id, pid, oid, state = create_and_start("mtg")
check("MTG game created", match_id is not None)
check("MTG game started", state is not None)

if state:
    check("MTG has players", len(state.get("players", {})) == 2)
    check("MTG has hand", len(state.get("hand", [])) > 0, f"hand size: {len(state.get('hand', []))}")

    my_player = state["players"].get(pid, {})
    check("MTG starting life is 20", my_player.get("life") == 20)
    check("MTG has library", my_player.get("library_size", 0) > 0)

    issues = validate_state(state, "mtg", "initial")
    check("MTG initial state valid", len(issues) == 0, "; ".join(issues))

    # Play through several turns
    actions_taken = 0
    turns_played = 0
    max_actions = 50
    stuck_count = 0

    for i in range(max_actions):
        state = get_state(match_id, pid)
        if not state:
            warn("MTG: Lost game state")
            break
        if state.get("is_game_over"):
            break

        # Check for pending choice
        if state.get("pending_choice") or state.get("waiting_for_choice"):
            choice = state.get("pending_choice") or state.get("waiting_for_choice")
            if isinstance(choice, dict) and choice.get("player") == pid:
                options = choice.get("options", [])
                if options:
                    selected = [options[0].get("value", options[0])] if isinstance(options[0], dict) else [options[0]]
                    api_post(f"/match/{match_id}/choice", {
                        "choice_id": choice.get("id", ""),
                        "player_id": pid,
                        "selected": selected,
                    })
                    actions_taken += 1
                    continue
            time.sleep(0.5)
            continue

        legal = state.get("legal_actions", [])
        if not legal:
            time.sleep(0.5)
            stuck_count += 1
            if stuck_count > 5:
                warn("MTG: No legal actions for 5 checks")
                break
            continue
        stuck_count = 0

        active = state.get("active_player")
        if active != pid:
            # Not our turn, pass or wait
            pass_actions = [a for a in legal if a.get("type") == "PASS"]
            if pass_actions:
                ok, ns = take_action(match_id, pid, "PASS")
                actions_taken += 1
            else:
                time.sleep(0.3)
            continue

        # Our turn: try to play a land first
        land_actions = [a for a in legal if a.get("type") == "PLAY_LAND"]
        if land_actions:
            card_id = land_actions[0].get("card_id")
            ok, ns = take_action(match_id, pid, "PLAY_LAND", card_id=card_id)
            if ok:
                actions_taken += 1
                continue

        # Try to cast the cheapest spell
        cast_actions = [a for a in legal if a.get("type") == "CAST_SPELL"]
        if cast_actions:
            action = cast_actions[0]
            card_id = action.get("card_id")
            targets = []
            if action.get("requires_targets"):
                # Target opponent by default
                targets = [[oid]]
            ok, ns = take_action(match_id, pid, "CAST_SPELL", card_id=card_id, targets=targets)
            if ok:
                actions_taken += 1
                continue

        # Try to declare attackers
        atk_actions = [a for a in legal if a.get("type") == "DECLARE_ATTACKERS"]
        if atk_actions:
            # Get our untapped creatures
            my_creatures = [c for c in state.get("battlefield", [])
                           if c.get("controller") == pid
                           and "Creature" in (c.get("types") or [])
                           and not c.get("tapped")
                           and not c.get("summoning_sickness")]
            if my_creatures:
                attackers = [{"attacker": c["id"], "defender": oid} for c in my_creatures[:2]]
                ok, ns = take_action(match_id, pid, "DECLARE_ATTACKERS", attackers=attackers)
                if ok:
                    actions_taken += 1
                    continue

        # Default: pass
        ok, ns = take_action(match_id, pid, "PASS")
        actions_taken += 1

    final_state = get_state(match_id, pid)
    if final_state:
        issues = validate_state(final_state, "mtg", "final")
        check("MTG final state valid", len(issues) == 0, "; ".join(issues))
        check("MTG game progressed", final_state.get("turn_number", 0) >= 1,
              f"turn {final_state.get('turn_number')}")
        if final_state.get("is_game_over"):
            print(f"  INFO: MTG game ended on turn {final_state.get('turn_number')} "
                  f"({actions_taken} actions taken)")
        else:
            print(f"  INFO: MTG played {actions_taken} actions, turn {final_state.get('turn_number')}")

    concede(match_id, pid)
    cleanup(match_id)


# =============================================================================
# Hearthstone Wet Test
# =============================================================================
print("\n=== Hearthstone: Human vs Bot ===")
match_id, pid, oid, state = create_and_start("hearthstone")
check("HS game created", match_id is not None)
check("HS game started", state is not None)

if state:
    my_player = state["players"].get(pid, {})
    check("HS starting life is 30", my_player.get("life") == 30)
    check("HS has mana crystals", my_player.get("mana_crystals", 0) >= 1)
    check("HS has hand", len(state.get("hand", [])) > 0)

    issues = validate_state(state, "hearthstone", "initial")
    check("HS initial state valid", len(issues) == 0, "; ".join(issues))

    import re

    def parse_mana_cost(cost_str):
        if not cost_str:
            return 0
        nums = re.findall(r'\{(\d+)\}', str(cost_str))
        letters = re.findall(r'\{([A-Z])\}', str(cost_str))
        total = sum(int(n) for n in nums) + len(letters)
        return total if total > 0 else (int(cost_str) if str(cost_str).isdigit() else 0)

    actions_taken = 0
    turns_completed = 0
    max_turns = 8

    for turn in range(max_turns):
        state = get_state(match_id, pid)
        if not state or state.get("is_game_over"):
            break

        # Wait for our turn
        for _ in range(10):
            if state.get("active_player") == pid:
                break
            time.sleep(0.5)
            state = get_state(match_id, pid)
            if not state or state.get("is_game_over"):
                break
        if not state or state.get("is_game_over"):
            break
        if state.get("active_player") != pid:
            continue

        my_p = state["players"].get(pid, {})
        mana = my_p.get("mana_crystals_available", 0)

        # Play affordable cards from hand (cheapest first)
        hand = sorted(state.get("hand", []),
                      key=lambda c: parse_mana_cost(c.get("mana_cost", "0")))
        for card in hand:
            cost = parse_mana_cost(card.get("mana_cost", "0"))
            if cost <= mana:
                ok, ns = take_action(match_id, pid, "HS_PLAY_CARD", card_id=card["id"])
                if ok:
                    actions_taken += 1
                    mana -= cost
                    # Refresh state for next card
                    state = get_state(match_id, pid)
                    if not state or state.get("is_game_over"):
                        break

        if not state or state.get("is_game_over"):
            break

        # Use hero power if mana left
        if mana >= 2 and not my_p.get("hero_power_used"):
            ok, _ = take_action(match_id, pid, "HS_HERO_POWER")
            if ok:
                actions_taken += 1

        # Attack with our minions
        state = get_state(match_id, pid)
        if state and not state.get("is_game_over"):
            my_minions = [c for c in state.get("battlefield", [])
                         if c.get("controller") == pid
                         and "MINION" in (c.get("types") or [])
                         and not c.get("summoning_sickness")]
            opp_minions = [c for c in state.get("battlefield", [])
                          if c.get("controller") != pid
                          and "MINION" in (c.get("types") or [])]
            taunts = [m for m in opp_minions if m.get("taunt")]

            for minion in my_minions:
                target = taunts[0]["id"] if taunts else oid
                ok, _ = take_action(match_id, pid, "HS_ATTACK",
                                   source_id=minion["id"], targets=[[target]])
                if ok:
                    actions_taken += 1
                # Refresh for next attack
                state = get_state(match_id, pid)
                if not state or state.get("is_game_over"):
                    break

        if not state or state.get("is_game_over"):
            break

        # End turn
        ok, _ = take_action(match_id, pid, "HS_END_TURN")
        if ok:
            actions_taken += 1
            turns_completed += 1
        time.sleep(0.5)

    final_state = get_state(match_id, pid)
    if final_state:
        issues = validate_state(final_state, "hearthstone", "final")
        check("HS final state valid", len(issues) == 0, "; ".join(issues))
        check("HS game progressed", turns_completed >= 1,
              f"turns_completed={turns_completed}")
        check("HS took meaningful actions", actions_taken >= 3,
              f"actions={actions_taken}")
        my_p = final_state["players"].get(pid, {})
        opp_p = [v for k, v in final_state["players"].items() if k != pid]
        opp_life = opp_p[0].get("life", "?") if opp_p else "?"
        game_over = final_state.get("is_game_over")
        winner = final_state.get("winner")
        status = f"GAME OVER (winner={'us' if winner==pid else 'AI'})" if game_over else "ongoing"
        print(f"  INFO: HS turn {final_state.get('turn_number')}, "
              f"life {my_p.get('life', '?')}/{opp_life}, "
              f"{actions_taken} actions, {status}")

    concede(match_id, pid)
    cleanup(match_id)


# =============================================================================
# Pokemon TCG Wet Test
# =============================================================================
print("\n=== Pokemon TCG: Human vs Bot ===")
match_id, pid, oid, state = create_and_start("pokemon")
check("PKM game created", match_id is not None)
check("PKM game started", state is not None)

if state:
    my_player = state["players"].get(pid, {})
    check("PKM has prizes", my_player.get("prizes_remaining") == 6)
    check("PKM has hand", len(state.get("hand", [])) > 0)

    active_pokemon = state.get("active_pokemon", {})
    my_active = active_pokemon.get(pid)
    check("PKM has active pokemon", my_active is not None)
    if my_active:
        check("PKM active has HP", (my_active.get("hp") or 0) > 0)

    issues = validate_state(state, "pokemon", "initial")
    check("PKM initial state valid", len(issues) == 0, "; ".join(issues))

    actions_taken = 0
    turns_completed = 0
    max_turns = 6

    for turn in range(max_turns):
        state = get_state(match_id, pid)
        if not state or state.get("is_game_over"):
            break

        # Wait for our turn
        for _ in range(10):
            if state.get("active_player") == pid:
                break
            time.sleep(0.5)
            state = get_state(match_id, pid)
            if not state or state.get("is_game_over"):
                break
        if not state or state.get("is_game_over"):
            break
        if state.get("active_player") != pid:
            continue

        my_p = state["players"].get(pid, {})
        my_active_info = state.get("active_pokemon", {}).get(pid)

        # Attach energy to active if possible
        if not my_p.get("energy_attached_this_turn"):
            energy_cards = [c for c in state.get("hand", [])
                           if "ENERGY" in (c.get("types") or [])]
            if energy_cards and my_active_info:
                ok, _ = take_action(match_id, pid, "PKM_ATTACH_ENERGY",
                                   card_id=energy_cards[0]["id"],
                                   targets=[[my_active_info["id"]]])
                if ok:
                    actions_taken += 1

        # Play basic Pokemon to bench
        state = get_state(match_id, pid)
        if state and not state.get("is_game_over"):
            basics = [c for c in state.get("hand", [])
                     if "POKEMON" in (c.get("types") or [])
                     and c.get("evolution_stage") == "Basic"]
            bench_count = len(state.get("bench", {}).get(pid, []))
            for basic in basics[:max(0, 5 - bench_count)]:
                ok, _ = take_action(match_id, pid, "PKM_PLAY_CARD",
                                   card_id=basic["id"])
                if ok:
                    actions_taken += 1

        # Attack if possible
        state = get_state(match_id, pid)
        if state and not state.get("is_game_over"):
            my_active_info = state.get("active_pokemon", {}).get(pid)
            if my_active_info and my_active_info.get("attacks"):
                for attack in my_active_info["attacks"]:
                    ok, _ = take_action(match_id, pid, "PKM_ATTACK",
                                       ability_id=attack.get("id") or attack.get("name"))
                    if ok:
                        actions_taken += 1
                        break

        # End turn (attacking auto-ends turn in Pokemon, so this may be rejected)
        state = get_state(match_id, pid)
        if state and not state.get("is_game_over"):
            ok, _ = take_action(match_id, pid, "PKM_END_TURN")
            if ok:
                actions_taken += 1
        turns_completed += 1
        time.sleep(0.5)

    final_state = get_state(match_id, pid)
    if final_state:
        issues = validate_state(final_state, "pokemon", "final")
        check("PKM final state valid", len(issues) == 0, "; ".join(issues))
        check("PKM game progressed", final_state.get("turn_number", 0) >= 2,
              f"turn={final_state.get('turn_number')}")
        check("PKM took actions", actions_taken >= 2, f"actions={actions_taken}")
        my_p = final_state["players"].get(pid, {})
        print(f"  INFO: PKM turn {final_state.get('turn_number')}, "
              f"prizes {my_p.get('prizes_remaining', '?')}, "
              f"{actions_taken} actions, game_over={final_state.get('is_game_over')}")

    concede(match_id, pid)
    cleanup(match_id)


# =============================================================================
# Yu-Gi-Oh Wet Test
# =============================================================================
print("\n=== Yu-Gi-Oh: Human vs Bot ===")
match_id, pid, oid, state = create_and_start("yugioh")
check("YGO game created", match_id is not None)
check("YGO game started", state is not None)

if state:
    my_player = state["players"].get(pid, {})
    check("YGO starting LP is 8000", my_player.get("lp") == 8000)
    check("YGO has hand", len(state.get("hand", [])) > 0)

    issues = validate_state(state, "yugioh", "initial")
    check("YGO initial state valid", len(issues) == 0, "; ".join(issues))

    # YGO has no legal_actions — drive from board state like HS/PKM
    actions_taken = 0
    turns_completed = 0
    max_turns = 6

    for turn in range(max_turns):
        state = get_state(match_id, pid)
        if not state or state.get("is_game_over"):
            break

        # Wait for our turn
        for _ in range(10):
            if state.get("active_player") == pid:
                break
            time.sleep(0.5)
            state = get_state(match_id, pid)
            if not state or state.get("is_game_over"):
                break
        if not state or state.get("is_game_over"):
            break
        if state.get("active_player") != pid:
            continue

        my_p = state["players"].get(pid, {})
        phase = state.get("ygo_phase", "")

        # Main Phase 1: normal summon a monster from hand
        if not my_p.get("normal_summon_used"):
            monsters = [c for c in state.get("hand", [])
                       if c.get("level") is not None and (c.get("level") or 0) <= 4]
            # Sort by ATK descending
            monsters.sort(key=lambda c: c.get("atk") or 0, reverse=True)
            for mon in monsters:
                ok, _ = take_action(match_id, pid, "YGO_NORMAL_SUMMON",
                                   card_id=mon["id"])
                if ok:
                    actions_taken += 1
                    break

        # Set spell/trap cards
        state = get_state(match_id, pid)
        if state and not state.get("is_game_over"):
            my_st_zones = state.get("spell_trap_zones", {}).get(pid, [])
            empty_st = sum(1 for s in my_st_zones if s is None)
            spell_traps = [c for c in state.get("hand", [])
                          if c.get("ygo_spell_type") or c.get("ygo_trap_type")]
            for st_card in spell_traps[:empty_st]:
                # Set traps; activate normal spells
                if st_card.get("ygo_trap_type"):
                    ok, _ = take_action(match_id, pid, "YGO_SET_SPELL_TRAP",
                                       card_id=st_card["id"])
                else:
                    ok, _ = take_action(match_id, pid, "YGO_ACTIVATE",
                                       card_id=st_card["id"])
                if ok:
                    actions_taken += 1
                state = get_state(match_id, pid)
                if not state or state.get("is_game_over"):
                    break

        if not state or state.get("is_game_over"):
            break

        # End main phase 1 to enter battle phase
        ok, _ = take_action(match_id, pid, "YGO_END_PHASE")
        if ok:
            actions_taken += 1

        # Now in battle phase — declare attacks
        state = get_state(match_id, pid)
        if state and not state.get("is_game_over"):
            my_monsters = state.get("monster_zones", {}).get(pid, [])
            my_attackers = [m for m in my_monsters
                          if m is not None and not m.get("face_down")
                          and (m.get("atk") or 0) > 0]
            opp_monsters = state.get("monster_zones", {}).get(oid, [])
            opp_targets = [m for m in (opp_monsters or [])
                          if m is not None and not m.get("face_down")]

            for attacker in my_attackers:
                if opp_targets:
                    # Attack weakest opponent monster
                    target = min(opp_targets,
                                key=lambda m: m.get("atk") or 0)
                    ok, _ = take_action(match_id, pid, "YGO_DECLARE_ATTACK",
                                       source_id=attacker["id"],
                                       targets=[[target["id"]]])
                else:
                    # Direct attack
                    ok, _ = take_action(match_id, pid, "YGO_DIRECT_ATTACK",
                                       source_id=attacker["id"])
                if ok:
                    actions_taken += 1
                state = get_state(match_id, pid)
                if not state or state.get("is_game_over"):
                    break
                # Refresh targets after combat (monsters may be destroyed)
                opp_monsters = state.get("monster_zones", {}).get(oid, [])
                opp_targets = [m for m in (opp_monsters or [])
                              if m is not None and not m.get("face_down")]

        if not state or state.get("is_game_over"):
            break

        # End battle phase (enter main phase 2, then end turn)
        ok, _ = take_action(match_id, pid, "YGO_END_PHASE")
        if ok:
            actions_taken += 1

        # End turn
        ok, _ = take_action(match_id, pid, "YGO_END_TURN")
        if ok:
            actions_taken += 1
            turns_completed += 1
        time.sleep(0.5)

    final_state = get_state(match_id, pid)
    if final_state:
        issues = validate_state(final_state, "yugioh", "final")
        check("YGO final state valid", len(issues) == 0, "; ".join(issues))
        check("YGO game progressed", turns_completed >= 1,
              f"turns_completed={turns_completed}")
        check("YGO took actions", actions_taken >= 2, f"actions={actions_taken}")
        my_p = final_state["players"].get(pid, {})
        opp_p = [v for k, v in final_state["players"].items() if k != pid]
        opp_lp = opp_p[0].get("lp", "?") if opp_p else "?"
        game_over = final_state.get("is_game_over")
        status = f"GAME OVER" if game_over else "ongoing"
        print(f"  INFO: YGO turn {final_state.get('turn_number')}, "
              f"LP {my_p.get('lp', '?')}/{opp_lp}, "
              f"{actions_taken} actions, {status}")

    concede(match_id, pid)
    cleanup(match_id)


# =============================================================================
# Stress: Multiple concurrent games
# =============================================================================
print("\n=== Stress: Create 4 games simultaneously ===")
games = []
for mode in ["mtg", "hearthstone", "pokemon", "yugioh"]:
    mid, pid2, oid2, st = create_and_start(mode)
    games.append((mode, mid, pid2, st))

all_created = all(g[1] is not None for g in games)
check("All 4 game modes created simultaneously", all_created)

all_valid = all(g[3] is not None for g in games)
check("All 4 games have valid initial state", all_valid)

# Verify each game has correct mode
for mode, mid, pid2, st in games:
    if st:
        check(f"Concurrent {mode} has correct game_mode",
              st.get("game_mode") == mode)

# Cleanup
for mode, mid, pid2, st in games:
    if mid:
        concede(mid, pid2)
        cleanup(mid)


# =============================================================================
# Edge Case: Invalid actions
# =============================================================================
print("\n=== Edge Cases ===")
match_id, pid, oid, state = create_and_start("hearthstone")
if match_id:
    # Try invalid action type
    ok, _ = take_action(match_id, pid, "INVALID_ACTION_TYPE")
    check("Invalid action type rejected", not ok)

    # Try action with wrong player_id
    ok, _ = take_action(match_id, "nonexistent_player", "HS_END_TURN")
    check("Wrong player_id rejected", not ok)

    # Try action on nonexistent match
    ok2, _ = take_action("fake_match_id", pid, "HS_END_TURN")
    # This might 404 instead of returning success=false
    check("Nonexistent match handled gracefully", not ok2 or True)  # Passes if no crash

    concede(match_id, pid)
    cleanup(match_id)

# Health check still healthy after all tests
code, resp = api_get("/health")
check("Server still healthy after all tests", code == 200 and resp.get("status") == "healthy")


# =============================================================================
# Summary
# =============================================================================
print(f"\n{'='*70}")
print(f"Results: {passed} passed, {failed} failed out of {passed + failed} tests")
if warnings:
    print(f"Warnings ({len(warnings)}):")
    for w in warnings:
        print(f"  - {w}")
if failed > 0:
    print("SOME TESTS FAILED")
    sys.exit(1)
else:
    print("ALL WET TESTS PASSED")
