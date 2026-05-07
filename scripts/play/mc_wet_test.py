"""
Interactive MC wet-test harness.

Usage:
    # Start a game (me=P1 vs AI=P2 with passive_econ on raider deck)
    PYTHONPATH=. python scripts/play/mc_wet_test.py start \\
        --my-deck raider --ai-deck raider --ai-bias passive_econ

    # Inspect state
    python scripts/play/mc_wet_test.py state

    # Take actions (any number, in any order, until end_turn)
    python scripts/play/mc_wet_test.py mine 0          # mine biome 0 with avatar
    python scripts/play/mc_wet_test.py play "Bed" 1 0  # play Bed at grid (x=1, y=0)
    python scripts/play/mc_wet_test.py play "Steve's Helper"   # mob, no cell
    python scripts/play/mc_wet_test.py worker_mine <worker_id> 2  # tap a worker, mine biome 2
    python scripts/play/mc_wet_test.py attack <attacker_id> 0    # attack column 0
    python scripts/play/mc_wet_test.py avatar_attack 0           # avatar attacks column 0

    # End my turn (also runs AI's full turn)
    python scripts/play/mc_wet_test.py end_turn

    # Game state is persisted in /tmp/mc_wet_test_state.pkl between commands.
"""

from __future__ import annotations

import argparse
import asyncio
import dill as pickle  # dill handles closures (card_def has local fns)
import sys
from typing import Any

STATE_PATH = "/tmp/mc_wet_test_state.pkl"


def _save(payload: dict[str, Any]) -> None:
    with open(STATE_PATH, "wb") as fh:
        pickle.dump(payload, fh)


def _load() -> dict[str, Any]:
    with open(STATE_PATH, "rb") as fh:
        return pickle.load(fh)


def _print_state(payload: dict[str, Any]) -> None:
    from src.engine import minecraft as mc
    from src.engine.types import CardType, ZoneType
    from src.engine.queries import get_power, get_toughness

    game = payload["game"]
    state = game.state
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]
    p1 = state.players[p1_id]
    p2 = state.players[p2_id]
    turn = getattr(state, "turn_number", 0)
    active = getattr(state, "active_player", None)
    day_phase = getattr(state, "minecraft_day_phase", "?")

    two_pilot = payload.get("two_pilot", False)
    if two_pilot:
        # In two-pilot mode "ME" = whoever's turn it is (the acting pilot).
        if active == p2_id:
            me_label, ai_label = "ME (P2)", "OPP (P1)"
            me_id, opp_id, opp = p2_id, p1_id, p1
            me = p2
        else:
            me_label, ai_label = "ME (P1)", "OPP (P2)"
            me_id, opp_id, opp = p1_id, p2_id, p2
            me = p1
    else:
        me_label = "ME (P1)"
        ai_label = "AI (P2)"
        me_id, opp_id, me, opp = p1_id, p2_id, p1, p2

    print("=" * 70)
    print(f"Turn {turn}  ({day_phase.upper()})  active={active!r}")
    print("=" * 70)
    if game.is_game_over():
        winner = game.get_winner()
        if winner == p1_id:
            print(">>> GAME OVER — I (P1) won! <<<")
        elif winner == p2_id:
            print(">>> GAME OVER — AI (P2) won. <<<")
        else:
            print(">>> GAME OVER — draw. <<<")
        return

    def _player_block(label, p, pid):
        materials = ", ".join(f"{m}={int(p.mc_materials.get(m,0))}" for m in mc.MATERIALS)
        print(f"\n[{label}]  HP={p.life}  has_lost={p.has_lost}")
        print(f"  materials: {materials}")
        gear = p.mc_avatar_gear or {}
        print(f"  gear: weapon={gear.get('weapon')!r:40} armor={gear.get('armor')!r}")
        biomes = state.minecraft_biomes.get(pid, [])
        for i, b in enumerate(biomes):
            yields = ", ".join(f"{k}+{v}" for k, v in (b.get("yields") or {}).items())
            mined = " (mined)" if b.get("mined") else ""
            print(f"  biome[{i}]: {b.get('name'):<25} yields=[{yields}]{mined}")
        # Grid
        grid = state.minecraft_grid.get(pid, [])
        if grid:
            print(f"  grid (3x3, y=0 back, y=2 front):")
            for y in range(3):
                row = []
                for x in range(3):
                    oid = grid[y][x] if y < len(grid) and x < len(grid[y]) else None
                    if oid:
                        obj = state.objects.get(oid)
                        if obj:
                            row.append(f"{obj.name[:14]:<14}")
                        else:
                            row.append(f"{'?':<14}")
                    else:
                        row.append(f"{'.':<14}")
                print(f"    y={y}: " + " | ".join(row))
        # Battlefield mobs (not on grid)
        bfield = state.zones.get("battlefield")
        if bfield:
            mobs_for = []
            for oid in bfield.objects:
                obj = state.objects.get(oid)
                if not obj or obj.controller != pid:
                    continue
                if obj.zone != ZoneType.BATTLEFIELD:
                    continue
                if obj.state.mc_grid_x is not None:
                    continue
                if CardType.MC_MOB not in obj.characteristics.types:
                    continue
                power = get_power(obj, state)
                tough = get_toughness(obj, state)
                damage = obj.state.damage
                tapped = "T" if obj.state.tapped or obj.state.mc_exhausted else "-"
                ss = "SS" if obj.state.summoning_sickness else "  "
                mobs_for.append(f"    [{oid[:8]}] {obj.name:<22} {power}/{tough}-{damage} {tapped}{ss}  subs={','.join(sorted(obj.characteristics.subtypes))[:30]}")
            if mobs_for:
                print(f"  battlefield mobs:")
                for line in mobs_for:
                    print(line)

    _player_block(me_label, me, me_id)
    _player_block(ai_label, opp, opp_id)

    # My hand
    print(f"\n[MY HAND]")
    hand = state.zones.get(f"hand_{me_id}")
    if hand:
        for oid in hand.objects:
            obj = state.objects.get(oid)
            if not obj or not obj.card_def:
                continue
            cost = mc._discounted_cost(state, me_id, obj) or {}
            cost_str = " ".join(f"{m[0].upper()}{v}" for m, v in cost.items() if v)
            can_pay = "OK" if mc.can_pay(state, me_id, cost) else "  "
            types = obj.characteristics.types
            type_str = (
                "MOB" if CardType.MC_MOB in types
                else "STR" if CardType.MC_STRUCTURE in types
                else "BLK" if CardType.MC_BLOCK in types
                else "TOOL" if CardType.MC_TOOL in types
                else "ACT" if CardType.MC_ACTION in types
                else "?"
            )
            pt = ""
            if CardType.MC_MOB in types:
                pt = f" {obj.characteristics.power}/{obj.characteristics.toughness}"
            elif CardType.MC_STRUCTURE in types or CardType.MC_BLOCK in types:
                pt = f"  /{obj.characteristics.toughness}"
            print(f"  {can_pay} [{oid[:8]}] {type_str:<4} {obj.name:<25}{pt:<8} cost=[{cost_str}]")

    # Day/night info
    print(f"\nDay phase: {day_phase}")
    if two_pilot:
        seat = "P2" if active == p2_id else "P1"
        print(f"\n(YOUR turn — seat={seat}. Take actions, then call `end_turn`.)")
    elif active == p2_id:
        print("\n(AI's turn next — call `end_turn` to let AI play and start your next turn,\n or wait for AI's actions to be reported.)")
    else:
        print("\n(YOUR turn. Take actions, then call `end_turn`.)")


# ---------- subcommands ----------


def _resolve_deck(name: str, decks_file: Optional[str]) -> list:
    """Resolve a deck name → list[CardDefinition] from the starter
    registry first, then a JSON file (same shape as
    scripts/play/mc_deck_tournament.py's --decks-file)."""
    from src.cards.minecraft import MINECRAFT_STARTER_DECKS, MINECRAFT_CARDS
    if name in MINECRAFT_STARTER_DECKS:
        return MINECRAFT_STARTER_DECKS[name]()
    if not decks_file:
        raise ValueError(f"Unknown deck {name!r}. Pass --decks-file PATH "
                         f"to load custom decks. Starters: {list(MINECRAFT_STARTER_DECKS)}")
    import json
    with open(decks_file) as fh:
        payload = json.load(fh)
    spec = (payload.get("decks") or {}).get(name)
    if not spec:
        raise ValueError(f"Deck {name!r} not in {decks_file} or starter registry")
    cards = []
    for cname in spec.get("cards") or []:
        if cname not in MINECRAFT_CARDS:
            raise ValueError(f"Deck {name!r} references unknown card {cname!r}")
        cards.append(MINECRAFT_CARDS[cname])
    return cards


def cmd_start(args) -> None:
    from src.ai.minecraft_adapter import MinecraftAIAdapter
    from src.engine.game import Game

    my_deck = _resolve_deck(args.my_deck, args.decks_file)
    ai_deck = _resolve_deck(args.ai_deck, args.decks_file)

    game = Game(mode="minecraft")
    p1 = game.add_player("ME")
    p2 = game.add_player("AI")
    game.setup_minecraft_player(p1, my_deck)
    game.setup_minecraft_player(p2, ai_deck)
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)

    # Only P2 is AI. P1 (me) is "human" — turn manager will skip AI take_turn
    # for P1 and we'll drive its actions directly.
    game.set_ai_player(p2.id)
    ai_adapter = MinecraftAIAdapter(difficulty="hard", bias=args.ai_bias)
    game.turn_manager.set_ai_handler(ai_adapter)

    asyncio.run(game.start_game())

    two_pilot = getattr(args, "two_pilot", False)
    payload = {
        "game": game,
        "p1_id": p1.id,
        "p2_id": p2.id,
        "ai_bias": args.ai_bias,
        "two_pilot": two_pilot,
        "history": [],  # log of (turn, actor, action_str)
    }
    _save(payload)
    print(f"Started game: P1={p1.id[:8]} (me, deck={args.my_deck}) vs "
          f"P2={p2.id[:8]} (AI bias={args.ai_bias}, deck={args.ai_deck})"
          f"{' [two-pilot]' if two_pilot else ''}")
    # If P2 starts, run their turn before printing state (single-pilot only)
    if not two_pilot and game.state.active_player == p2.id:
        asyncio.run(game.turn_manager.run_turn())
        payload["history"].append((game.state.turn_number, "AI", "took turn"))
        _save(payload)
    _print_state(payload)


def cmd_state(args) -> None:
    payload = _load()
    _print_state(payload)


def _find_card_in_hand(state, p1_id: str, name_or_prefix: str):
    hand = state.zones.get(f"hand_{p1_id}")
    if not hand:
        return None
    for oid in hand.objects:
        obj = state.objects.get(oid)
        if not obj:
            continue
        if obj.id.startswith(name_or_prefix) or obj.name == name_or_prefix:
            return obj
    return None


def _acting_player_id(payload: dict[str, Any]) -> str:
    """Return the player id whose actions the CLI should drive.

    In two-pilot mode the CLI follows ``state.active_player`` so each pilot
    can take actions on its own turn through the same harness. In
    single-pilot mode we always drive P1 — the AI runs autonomously inside
    ``end_turn``.
    """
    if payload.get("two_pilot"):
        active = payload["game"].state.active_player
        if active in (payload["p1_id"], payload["p2_id"]):
            return active
    return payload["p1_id"]


def cmd_mine(args) -> None:
    from src.engine import minecraft as mc
    payload = _load()
    game = payload["game"]
    actor_id = _acting_player_id(payload)
    biome_idx = int(args.biome_idx)
    ok, msg, _evs = mc.mine_biome(game, actor_id, biome_idx, avatar=True)
    print(f"mine biome[{biome_idx}] (avatar): ok={ok} msg={msg!r}")
    label = "P2" if actor_id == payload["p2_id"] else "ME"
    payload["history"].append((game.state.turn_number, label, f"avatar mine biome[{biome_idx}]"))
    _save(payload)
    if ok:
        _print_state(payload)


def cmd_worker_mine(args) -> None:
    from src.engine import minecraft as mc
    payload = _load()
    game = payload["game"]
    actor_id = _acting_player_id(payload)
    worker_id = args.worker_id
    biome_idx = int(args.biome_idx)
    # Resolve worker_id prefix
    state = game.state
    full_worker_id = None
    bfield = state.zones.get("battlefield")
    if bfield:
        for oid in bfield.objects:
            obj = state.objects.get(oid)
            if obj and obj.controller == actor_id and obj.id.startswith(worker_id):
                full_worker_id = obj.id
                break
    if not full_worker_id:
        print(f"Worker id {worker_id!r} not found on my battlefield")
        return
    ok, msg, _evs = mc.mine_biome(game, actor_id, biome_idx, actor_id=full_worker_id)
    print(f"worker[{full_worker_id[:8]}] mine biome[{biome_idx}]: ok={ok} msg={msg!r}")
    label = "P2" if actor_id == payload["p2_id"] else "ME"
    payload["history"].append((game.state.turn_number, label, f"worker[{full_worker_id[:8]}] mine biome[{biome_idx}]"))
    _save(payload)
    if ok:
        _print_state(payload)


def cmd_play(args) -> None:
    from src.engine import minecraft as mc
    payload = _load()
    game = payload["game"]
    actor_id = _acting_player_id(payload)
    obj = _find_card_in_hand(game.state, actor_id, args.card)
    if not obj:
        print(f"Card {args.card!r} not found in hand")
        return
    cell = None
    if args.cell_x is not None and args.cell_y is not None:
        cell = {"x": int(args.cell_x), "y": int(args.cell_y)}
    target_id = args.target_id
    ok, msg, _evs = mc.play_card(game, actor_id, obj.id, cell=cell, target_id=target_id)
    print(f"play {obj.name!r}: ok={ok} msg={msg!r}")
    label = "P2" if actor_id == payload["p2_id"] else "ME"
    payload["history"].append((game.state.turn_number, label, f"play {obj.name}"))
    _save(payload)
    if ok:
        _print_state(payload)


def cmd_avatar_attack(args) -> None:
    from src.engine import minecraft as mc
    payload = _load()
    game = payload["game"]
    actor_id = _acting_player_id(payload)
    column = int(args.column)
    ok, msg, _evs = mc.avatar_attack(game, actor_id, target_column=column)
    print(f"avatar attack column[{column}]: ok={ok} msg={msg!r}")
    label = "P2" if actor_id == payload["p2_id"] else "ME"
    payload["history"].append((game.state.turn_number, label, f"avatar attack col[{column}]"))
    _save(payload)
    if ok:
        _print_state(payload)


def cmd_avatar_explore(args) -> None:
    from src.engine import minecraft as mc
    payload = _load()
    game = payload["game"]
    actor_id = _acting_player_id(payload)
    biome_idx = int(args.biome_idx)
    ok, msg, _evs = mc.explore_biome(game, actor_id, biome_idx)
    print(f"avatar explore biome[{biome_idx}]: ok={ok} msg={msg!r}")
    label = "P2" if actor_id == payload["p2_id"] else "ME"
    payload["history"].append((game.state.turn_number, label, f"avatar explore biome[{biome_idx}]"))
    _save(payload)
    if ok:
        _print_state(payload)


def cmd_attack(args) -> None:
    from src.engine import minecraft as mc
    payload = _load()
    game = payload["game"]
    actor_id = _acting_player_id(payload)
    state = game.state
    bfield = state.zones.get("battlefield")
    declarations: list[dict] = []
    for spec in args.specs:
        if ":" not in spec:
            print(f"Bad attack spec {spec!r} — expected attacker_id_prefix:column")
            continue
        prefix, col_s = spec.split(":", 1)
        column = int(col_s)
        full_id = None
        if bfield:
            for oid in bfield.objects:
                obj = state.objects.get(oid)
                if obj and obj.controller == actor_id and obj.id.startswith(prefix):
                    full_id = obj.id
                    break
        if not full_id:
            print(f"  attacker {prefix!r} not found, skipping")
            continue
        declarations.append({"attacker_id": full_id, "target_column": column})
    if not declarations:
        print("No valid attackers — nothing to declare.")
        return
    ok, msg, _evs = mc.declare_attackers(game, actor_id, declarations, auto_block=True)
    print(f"declare_attackers: ok={ok} msg={msg!r}  declarations={declarations}")
    label = "P2" if actor_id == payload["p2_id"] else "ME"
    payload["history"].append((game.state.turn_number, label, f"attack {declarations}"))
    _save(payload)
    if ok:
        _print_state(payload)


def cmd_end_turn(args) -> None:
    """End active player's turn. In single-pilot mode, also runs AI's turn.
    In two-pilot mode, just rotates active_player — no AI execution."""
    from src.engine.types import Event, EventType
    payload = _load()
    game = payload["game"]
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]
    two_pilot = payload.get("two_pilot", False)
    if game.is_game_over():
        print("Game already over.")
        _print_state(payload)
        return

    if two_pilot:
        # Rotate active player without running any AI.
        current = game.state.active_player
        next_player = p2_id if current == p1_id else p1_id
        label = "P2" if next_player == p2_id else "P1"
        asyncio.run(game.turn_manager.run_turn(player_id=next_player))
        payload["history"].append((game.state.turn_number, label, "begin of turn (two-pilot)"))
        _save(payload)
        _print_state(payload)
        return

    # Single-pilot: hand off to AI (P2), then begin P1's next turn.
    # Manually end my turn by calling turn_manager's end-of-turn flow.
    # Simplest: call run_turn for AI (P2). That advances active_player and
    # triggers the proper begin-of-turn / draw / etc. for AI.
    # Wait — we may currently be on MY turn. The turn manager won't advance
    # automatically. Let's flip state and call run_turn on the AI.
    game.state.active_player = p2_id
    asyncio.run(game.turn_manager.run_turn(player_id=p2_id))
    payload["history"].append((game.state.turn_number, "AI", "took turn"))
    if game.is_game_over():
        _save(payload)
        _print_state(payload)
        return
    # Now turn moves to me — run the begin-of-turn ourselves: draw 1, untap.
    asyncio.run(game.turn_manager.run_turn(player_id=p1_id))
    payload["history"].append((game.state.turn_number, "ME", "begin of turn (auto)"))
    _save(payload)
    _print_state(payload)


def cmd_history(args) -> None:
    payload = _load()
    print("=== Action history ===")
    for turn, actor, action in payload["history"]:
        print(f"  turn {turn}  {actor:<3}  {action}")


def cmd_result(args) -> None:
    payload = _load()
    game = payload["game"]
    if not game.is_game_over():
        print("Game still in progress.")
        return
    winner = game.get_winner()
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]
    if winner == p1_id:
        print("ME (P1) won")
    elif winner == p2_id:
        print("AI (P2) won")
    else:
        print("draw")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("--my-deck", default="raider")
    p_start.add_argument("--ai-deck", default="raider")
    p_start.add_argument("--ai-bias", default="passive_econ")
    p_start.add_argument("--decks-file", default=None,
                         help="JSON file with custom decks (same shape as deck tournament)")
    p_start.add_argument("--two-pilot", action="store_true", default=False,
                         help="Two-pilot mode: skip AI execution; both seats driven by LLM agents")
    p_start.set_defaults(fn=cmd_start)

    p_state = sub.add_parser("state")
    p_state.set_defaults(fn=cmd_state)

    p_mine = sub.add_parser("mine")
    p_mine.add_argument("biome_idx")
    p_mine.set_defaults(fn=cmd_mine)

    p_wmine = sub.add_parser("worker_mine")
    p_wmine.add_argument("worker_id")
    p_wmine.add_argument("biome_idx")
    p_wmine.set_defaults(fn=cmd_worker_mine)

    p_play = sub.add_parser("play")
    p_play.add_argument("card")
    p_play.add_argument("cell_x", nargs="?")
    p_play.add_argument("cell_y", nargs="?")
    p_play.add_argument("--target-id")
    p_play.set_defaults(fn=cmd_play)

    p_atk = sub.add_parser("attack")
    p_atk.add_argument("specs", nargs="+", help="attacker_prefix:column")
    p_atk.set_defaults(fn=cmd_attack)

    p_aatk = sub.add_parser("avatar_attack")
    p_aatk.add_argument("column")
    p_aatk.set_defaults(fn=cmd_avatar_attack)

    p_aexp = sub.add_parser("avatar_explore")
    p_aexp.add_argument("biome_idx")
    p_aexp.set_defaults(fn=cmd_avatar_explore)

    p_end = sub.add_parser("end_turn")
    p_end.set_defaults(fn=cmd_end_turn)

    p_hist = sub.add_parser("history")
    p_hist.set_defaults(fn=cmd_history)

    p_res = sub.add_parser("result")
    p_res.set_defaults(fn=cmd_result)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
