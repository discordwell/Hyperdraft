"""
Interactive Finance TCG wet-test harness.

Modeled on scripts/play/mc_wet_test.py — each subprocess invocation loads
state from a pickle file, mutates the game, saves it back. Two LLM pilots
can drive both seats by sharing the same save path.

Usage:
    # Start a two-pilot game (both seats driven by the CLI)
    python -m scripts.play.finance_wet_test start \\
        --p1-deck FINA_high_frequency --p2-deck FINA_quant --two-pilot

    # Inspect state
    python -m scripts.play.finance_wet_test state

    # Show active player's hand with prefix IDs and costs
    python -m scripts.play.finance_wet_test hand

    # Take actions (operate on whoever is active_player)
    python -m scripts.play.finance_wet_test play <card_id_prefix>
    python -m scripts.play.finance_wet_test attack <attacker_id_prefix> [<more...>]
    python -m scripts.play.finance_wet_test block <blocker_id_prefix> <attacker_id_prefix>

    # End the current turn (advances to opponent in two-pilot mode)
    python -m scripts.play.finance_wet_test end_turn

    # Resolve declared combat (two-pilot only — see "Two-pilot blocker phase")
    python -m scripts.play.finance_wet_test resolve_combat

    # Recent action log / final result
    python -m scripts.play.finance_wet_test history
    python -m scripts.play.finance_wet_test result

State is persisted in /tmp/finance_wet_test_state.pkl by default; pass
--save PATH to share between agents or scope per-test.

Two-pilot blocker phase
-----------------------
In single-pilot mode P2 is the heuristic AI, so combat is resolved
synchronously inside ``end_turn``: the AI's ``choose_blockers`` call
fires from inside ``FinanceTurnManager.run_turn`` and the harness never
needs to pause.

In two-pilot mode there is no AI, so the harness must yield control to
P2 between "P1 declared attackers" and "combat damage resolves". The
flow is:

    P1 (active):  attack <id> [<id>...]   # declare attackers
    P1 (active):  end_turn                # IF attackers were declared,
                                          # this advances phase to
                                          # SETTLEMENT, sets the flag
                                          # awaiting_blocks=True, and
                                          # STOPS before combat damage.
    P2 (defender): state                  # state shows awaiting_blocks
    P2 (defender): hand                   # works (acting_player is P2
                                          # during the block window)
    P2 (defender): block <blocker> <atk>  # records a block; in this
                                          # window the harness accepts
                                          # commands from whichever
                                          # seat owns the blockers,
                                          # NOT state.active_player.
    P2 (defender): resolve_combat         # actually runs combat damage,
                                          # finishes P1's turn, runs
                                          # PRE_MARKET+RESEARCH for P2,
                                          # and hands control back.

If P1 calls ``end_turn`` with no attackers declared, combat resolution
is a no-op and the harness advances turns directly (no block window).

Bug #23 — Block-window race condition gate
------------------------------------------
The earlier fcntl serialization (#11) prevents concurrent state writes,
but the block window has a *logical* race: the attacker can call
``resolve_combat`` (or its alias ``end_turn``) before the defender's
``block`` commands have been issued. To prevent face damage with zero
blocks, the harness now tracks a per-window flag
``blocks_committed_by_defender``:

  * The flag is set False whenever the block window opens.
  * Each successful ``block`` command from the defender flips it to True.
  * A new ``done_blocks`` (alias ``pass_blocks``) command flips it to
    True without recording any blocks (defender explicitly declines).
  * The defender calling ``resolve_combat`` themselves ALSO flips it
    True (they're saying "I'm done blocking, proceed").

While ``awaiting_blocks=True`` AND ``blocks_committed_by_defender=False``,
the harness REJECTS ``resolve_combat`` and ``end_turn`` issued by the
ATTACKER with a "Block window still open" message. The defender can
still issue these commands themselves at any time.

Typical flows now:

    Attacker:  attack <id>; end_turn          → window opens
    Defender:  block <blk> <atk>              → flag flips True
    Either:    resolve_combat                 → combat resolves

    Attacker:  attack <id>; end_turn          → window opens
    Defender:  done_blocks                    → flag flips True (no blocks)
    Either:    resolve_combat                 → all attackers through

    Attacker:  attack <id>; end_turn          → window opens
    Defender:  resolve_combat                 → declines + resolves in one step
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from typing import Any, Optional

import dill as pickle  # dill handles closures (card_def has local fns)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_STATE_PATH = "/tmp/finance_wet_test_state.pkl"


# ---------- persistence ----------
#
# bug #11: two-pilot state file-race. Concurrent `python -m scripts.play.finance_wet_test ...`
# invocations from two pilots can interleave a read with another's write,
# corrupting the perceived state mid-decision. Fix: use fcntl.flock so each
# command holds an exclusive lock around its read-modify-write window. Also
# bump a `round_id` int on every successful mutation so a pilot can detect
# state drift between their `state` print and their action attempt.

import fcntl
import os
from contextlib import contextmanager


def _lock_path(path: str) -> str:
    return path + ".lock"


@contextmanager
def _exclusive_lock(path: str):
    """Acquire an exclusive (POSIX) flock on a sidecar lock file.

    Sidecar lockfile (``<path>.lock``) is used so the lock survives
    truncation of the actual pickle, and so we can lock before the pickle
    exists yet (during ``cmd_start``).
    """
    lock_path = _lock_path(path)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _save(payload: dict[str, Any], path: str) -> None:
    """Write the payload pickle. Caller MUST hold the exclusive lock."""
    # round_id mutation telemetry — pilots can detect intervening writes.
    payload["round_id"] = int(payload.get("round_id", 0)) + 1
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as fh:
        pickle.dump(payload, fh)
    os.replace(tmp_path, path)


def _load(path: str) -> dict[str, Any]:
    """Read the payload pickle. Caller MUST hold the exclusive lock."""
    with open(path, "rb") as fh:
        return pickle.load(fh)


@contextmanager
def _session(path: str):
    """Context manager: acquire lock, load payload, save+release on exit.

    Usage::

        with _session(path) as ctx:
            payload = ctx["payload"]
            ...
            ctx["payload"] = payload   # if mutated; same object is fine
            ctx["save"] = True         # default; set False to skip save
    """
    with _exclusive_lock(path):
        payload = _load(path)
        ctx = {"payload": payload, "save": True}
        try:
            yield ctx
        finally:
            if ctx.get("save", True):
                _save(ctx["payload"], path)


# ---------- deck resolution ----------

def _resolve_deck(name: str, decks_file: str | None = None) -> list:
    """Look up a deck by name. First checks --decks-file (if given), then FINA starters."""
    if decks_file:
        import json
        from pathlib import Path
        from src.cards.finance import FINANCE_CARDS
        spec = json.loads(Path(decks_file).read_text())
        if name in spec.get("decks", {}):
            card_names = spec["decks"][name]["cards"]
            missing = [c for c in card_names if c not in FINANCE_CARDS]
            if missing:
                raise ValueError(f"Deck {name!r} references unknown cards: {missing[:3]}")
            return [FINANCE_CARDS[c] for c in card_names]
    from src.cards.finance.fina.decks import FINA_STARTER_DECKS
    if name not in FINA_STARTER_DECKS:
        avail = list(FINA_STARTER_DECKS)
        if decks_file:
            avail = list(spec.get("decks", {}).keys()) + avail
        raise ValueError(
            f"Unknown deck {name!r}. Available: {avail}"
        )
    return FINA_STARTER_DECKS[name]()


# ---------- phase progression helpers ----------

async def _run_pre_market_and_research(payload: dict[str, Any], player_id: str) -> None:
    """Untap, refill liquidity, draw 1.

    Mirrors what FinanceTurnManager.run_turn would do for the first two
    phases without entering the action loop. Called at game start for the
    starting player and after end_turn for the next active player.
    """
    from src.engine.finance_turn import FinancePhase

    game = payload["game"]
    tm = game.turn_manager

    # Bump turn pointer.
    tm.fin_turn_state.turn_number += 1
    game.state.turn_number = tm.fin_turn_state.turn_number
    tm.turn_state.turn_number = tm.fin_turn_state.turn_number

    # Set active player.
    tm.fin_turn_state.active_player_id = player_id
    game.state.active_player = player_id
    if player_id in tm.turn_order:
        tm.current_player_index = tm.turn_order.index(player_id)

    # Reset per-turn combat tracking.
    tm.fin_turn_state.attackers_declared = []
    tm.fin_turn_state.combat_blocks = {}

    # Emit TURN_START.
    await tm._emit_turn_start()

    # PRE_MARKET — untap, refill liquidity, clear summoning sickness.
    tm.fin_turn_state.phase = FinancePhase.PRE_MARKET
    await tm._run_pre_market(player_id)

    # RESEARCH — draw 1.
    tm.fin_turn_state.phase = FinancePhase.RESEARCH
    await tm._run_research(player_id)

    # Stop in TRADING_SESSION so the pilot can take actions.
    tm.fin_turn_state.phase = FinancePhase.TRADING_SESSION
    tm._emit_phase("trading_session", "start", player_id)


async def _resolve_declared_combat(payload: dict[str, Any]) -> None:
    """Run blocker declaration + combat damage using whatever is on
    fin_turn_state right now. Idempotent if no attackers were declared."""
    game = payload["game"]
    tm = game.turn_manager
    pid = tm.fin_turn_state.active_player_id

    if not (tm.fin_turn_state.attackers_declared and tm.finance_combat_manager):
        return

    opp_id = tm._get_opponent(pid)
    attackers = list(tm.fin_turn_state.attackers_declared)
    blocks = dict(tm.fin_turn_state.combat_blocks)
    # Bug #18 fix: declare_attackers once here with the FULL list so that
    # every ATTACK_DECLARED trigger sees the correct final attacker count.
    # (cmd_attack no longer calls declare_attackers to avoid partial counts.)
    await tm._invoke_combat(
        tm.finance_combat_manager,
        "declare_attackers",
        pid,
        attackers,
    )
    # Declare blockers (no-op if blocks empty).
    if blocks:
        await tm._invoke_combat(
            tm.finance_combat_manager,
            "declare_blockers",
            opp_id,
            blocks,
        )
    # Resolve combat damage.
    await tm._invoke_combat(
        tm.finance_combat_manager,
        "resolve_combat_damage",
        attackers,
        blocks,
        opp_id,
    )
    tm._check_game_over()
    # Bug #32 (iter-4): clear attackers_declared/combat_blocks immediately
    # after combat resolves, so any unexpected re-entry into combat (e.g.
    # extra-turn effects, defensive double-resolve) doesn't replay the
    # same set. _run_pre_market_and_research also clears these on the
    # next turn, but doing it here too is defensive.
    tm.fin_turn_state.attackers_declared = []
    tm.fin_turn_state.combat_blocks = {}


async def _finish_active_turn_post_combat(
    payload: dict[str, Any], settlement_already_started: bool = False
) -> None:
    """Run SETTLEMENT + MARKET_CLOSE + TURN_END + advance index for the
    active player. Assumes combat damage has already resolved (or no
    attackers were declared).

    ``settlement_already_started=True`` means SETTLEMENT/start was
    already emitted (e.g. by ``cmd_end_turn`` when opening the
    two-pilot block window) — skip re-emitting it.
    """
    from src.engine.finance_turn import FinancePhase

    game = payload["game"]
    tm = game.turn_manager
    pid = tm.fin_turn_state.active_player_id

    # PHASE_END for trading session (only if we are still in TRADING_SESSION;
    # a two-pilot end_turn that gated on attackers already advanced phase).
    if tm.fin_turn_state.phase == FinancePhase.TRADING_SESSION:
        tm._emit_phase("trading_session", "end", pid)
    if tm._is_game_over():
        await tm._emit_turn_end()
        tm._advance_turn()
        return

    # SETTLEMENT — no pilot actions in this minimal harness.
    if tm.fin_turn_state.phase != FinancePhase.SETTLEMENT:
        tm.fin_turn_state.phase = FinancePhase.SETTLEMENT
    if not settlement_already_started:
        tm._emit_phase("settlement", "start", pid)
    tm._emit_phase("settlement", "end", pid)
    tm._check_game_over()
    if tm._is_game_over():
        await tm._emit_turn_end()
        tm._advance_turn()
        return

    # MARKET_CLOSE — phase events fire leverage tick + end-of-turn sweep.
    tm.fin_turn_state.phase = FinancePhase.MARKET_CLOSE
    tm._emit_phase("market_close", "start", pid)
    # Discard down to hand limit (simple last-card discard).
    hand = tm._get_hand(pid)
    while len(hand) > 7:
        discard_id = hand[-1]
        await tm._discard_card(pid, discard_id)
        hand = tm._get_hand(pid)
    tm._sweep_eot_modifiers()
    tm._check_game_over()
    tm._emit_phase("market_close", "end", pid)

    await tm._emit_turn_end()
    tm._advance_turn()


async def _finish_turn(payload: dict[str, Any]) -> None:
    """Run the rest of the active player's turn after pilot has played.

    Resolves combat (using attackers already stored on fin_turn_state),
    runs SETTLEMENT (no further actions — pilot has no settlement-window
    here, simplest), runs MARKET_CLOSE, emits TURN_END, advances index.

    Used in single-pilot mode and as the second leg of two-pilot
    `resolve_combat` (after the block window closes).
    """
    await _resolve_declared_combat(payload)
    await _finish_active_turn_post_combat(payload)


# ---------- state printer ----------

def _print_state(payload: dict[str, Any]) -> None:
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
    phase = "?"
    tm = game.turn_manager
    if hasattr(tm, "fin_turn_state"):
        phase = tm.fin_turn_state.phase.name

    two_pilot = payload.get("two_pilot", False)
    awaiting_blocks = bool(two_pilot and payload.get("awaiting_blocks"))
    # During the blocker window the *defender* is the acting seat — they
    # are the one running `state`, `hand`, `block`, `resolve_combat`.
    if awaiting_blocks and active is not None:
        defender_id = p2_id if active == p1_id else p1_id
        acting_id = defender_id
    else:
        acting_id = active if active in (p1_id, p2_id) else p1_id

    if two_pilot:
        if acting_id == p2_id:
            me_label, opp_label = "ME (P2)", "OPP (P1)"
            me_id, opp_id, me, opp = p2_id, p1_id, p2, p1
        else:
            me_label, opp_label = "ME (P1)", "OPP (P2)"
            me_id, opp_id, me, opp = p1_id, p2_id, p1, p2
    else:
        me_label = "ME (P1)"
        opp_label = "AI (P2)"
        me_id, opp_id, me, opp = p1_id, p2_id, p1, p2

    print("=" * 70)
    print(f"Turn {turn}  ({phase})  active={active!r}")
    print("=" * 70)
    if game.is_game_over():
        winner = game.get_winner()
        if winner == p1_id:
            print(">>> GAME OVER — P1 won! <<<")
        elif winner == p2_id:
            print(">>> GAME OVER — P2 won! <<<")
        else:
            print(">>> GAME OVER — draw. <<<")
        return

    fin_trader = getattr(CardType, "FIN_TRADER", None)

    def _player_block(label: str, p, pid: str) -> None:
        liq_avail = int(getattr(p, "mana_crystals_available", 0) or 0)
        liq_max = int(getattr(p, "mana_crystals", 0) or 0)
        hand_size = len(state.zones[f"hand_{pid}"].objects) if f"hand_{pid}" in state.zones else 0
        lib_size = len(state.zones[f"library_{pid}"].objects) if f"library_{pid}" in state.zones else 0
        gy_size = len(state.zones[f"graveyard_{pid}"].objects) if f"graveyard_{pid}" in state.zones else 0
        print(f"\n[{label}]  Capital={p.life}  has_lost={p.has_lost}")
        print(f"  Liquidity: {liq_avail}/{liq_max}   "
              f"hand={hand_size}  lib={lib_size}  gy={gy_size}")
        # Battlefield Traders / Assets / Structures controlled by pid.
        bfield = state.zones.get("battlefield")
        if not bfield:
            return
        traders = []
        others = []
        for oid in bfield.objects:
            obj = state.objects.get(oid)
            if not obj or obj.controller != pid:
                continue
            if obj.zone != ZoneType.BATTLEFIELD:
                continue
            types = obj.characteristics.types
            if fin_trader is not None and fin_trader in types:
                power = get_power(obj, state) or 0
                tough = get_toughness(obj, state) or 0
                damage = obj.state.damage or 0
                tapped = "T" if obj.state.tapped else "-"
                ss = "SS" if obj.state.summoning_sickness else "  "
                attached = ""
                if getattr(obj.state, "attached_to", None):
                    attached = f" attached_to={obj.state.attached_to[:8]}"
                traders.append(
                    f"    [{oid[:8]}] {obj.name:<28} {power}/{tough}-{damage} {tapped}{ss}{attached}"
                )
            else:
                # Asset / Structure / Derivative
                tname = ", ".join(
                    sorted(t.name for t in types if t.name.startswith("FIN_"))
                ) or "?"
                attached = ""
                if getattr(obj.state, "attached_to", None):
                    attached = f" → {obj.state.attached_to[:8]}"
                others.append(f"    [{oid[:8]}] {obj.name:<28} {tname}{attached}")
        if traders:
            print(f"  Traders:")
            for line in traders:
                print(line)
        if others:
            print(f"  Other permanents:")
            for line in others:
                print(line)

    _player_block(me_label, me, me_id)
    _player_block(opp_label, opp, opp_id)

    # Combat status
    declared = getattr(tm.fin_turn_state, "attackers_declared", []) or []
    blocks = getattr(tm.fin_turn_state, "combat_blocks", {}) or {}
    if declared or blocks or awaiting_blocks:
        print(f"\n[COMBAT]")
        if awaiting_blocks:
            print(f"  awaiting_blocks=True  (defender's window — assign blocks then `resolve_combat`)")
        if declared:
            print(f"  attackers: {[a[:8] for a in declared]}")
        if blocks:
            print(f"  blocks:    {{{', '.join(f'{a[:8]}<-{b[:8]}' for a,b in blocks.items())}}}")

    # Closing hint
    if two_pilot:
        if awaiting_blocks:
            def_seat = "P2" if me_id == p2_id else "P1"
            atk_seat = "P1" if def_seat == "P2" else "P2"
            print(f"\n(BLOCK WINDOW — seat={def_seat} is defending against {atk_seat}'s attackers.")
            print(f" Use `hand`/`state` to inspect, `block <blocker_id> <attacker_id>` to assign,")
            print(f" then `resolve_combat` to fire damage and pass to {def_seat}'s turn.")
            print(f" Issuing `resolve_combat` with no blocks lets all attackers through.)")
        else:
            seat = "P2" if active == p2_id else "P1"
            print(f"\n(YOUR turn — seat={seat}, phase={phase}.")
            print(f" Use `hand` to see playable cards, then `play <id>` / `attack <id>...`,")
            print(f" then `end_turn`. After `attack` + `end_turn` the defender gets a block window.)")
    else:
        print(f"\n(YOUR turn — phase={phase}.)")


# ---------- helpers ----------

def _acting_player_id(payload: dict[str, Any]) -> str:
    """Return the player whose actions the CLI drives.

    Normally this is state.active_player. During the two-pilot blocker
    window (``awaiting_blocks=True``) the *defender* is the acting seat:
    they're the one running ``hand``, ``state``, ``block``, and finally
    ``resolve_combat`` to release the turn.
    """
    if payload.get("two_pilot"):
        game = payload["game"]
        active = game.state.active_player
        if payload.get("awaiting_blocks"):
            tm = game.turn_manager
            if tm is not None and active is not None:
                opp = tm._get_opponent(active)
                if opp:
                    return opp
        if active in (payload["p1_id"], payload["p2_id"]):
            return active
    return payload["p1_id"]


def _is_awaiting_blocks(payload: dict[str, Any]) -> bool:
    return bool(payload.get("two_pilot") and payload.get("awaiting_blocks"))


def _find_in_hand(state, player_id: str, prefix: str):
    zone = state.zones.get(f"hand_{player_id}")
    if not zone:
        return None
    for oid in zone.objects:
        obj = state.objects.get(oid)
        if obj and (obj.id.startswith(prefix) or obj.name == prefix):
            return obj
    return None


def _find_on_battlefield(state, player_id: str, prefix: str):
    bfield = state.zones.get("battlefield")
    if not bfield:
        return None
    for oid in bfield.objects:
        obj = state.objects.get(oid)
        if obj and obj.controller == player_id and obj.id.startswith(prefix):
            return obj
    return None


def _label_for(payload: dict[str, Any], player_id: str) -> str:
    return "P1" if player_id == payload["p1_id"] else "P2"


# ---------- bug #25: seat isolation helper ----------

def _check_seat(args, payload: dict[str, Any], *, allow_during_block_window: bool = False) -> bool:
    """Verify --seat matches the active player.  Returns True if OK to proceed.

    When ``allow_during_block_window=True`` the check is skipped while
    ``awaiting_blocks=True`` so that the non-active defender can issue
    ``block`` and ``resolve_combat`` commands freely.

    If ``--seat`` is omitted in single-pilot mode the legacy behaviour
    (no verification) is preserved so single-pilot tests keep working.

    Bug #31 (iter-4): in TWO-PILOT mode ``--seat`` is now REQUIRED for any
    state-mutating command. The previous "seat=None → always OK" path
    bypassed the bug-#23 attacker gate when a pilot forgot the flag,
    letting the attacker race past the defender's block window. With
    --seat required, the gate fires consistently.

    Bug #31b: support ``--expected-round-id <N>``. If given and the
    current pickle's ``round_id`` is greater (someone else wrote between
    the pilot's `state` read and this action), reject with a clear
    "state advanced" error so the pilot re-reads instead of mutating
    based on stale info.
    """
    seat = getattr(args, "seat", None)

    # Bug #31b: round-id drift detection (applies in any mode).
    expected_rid = getattr(args, "expected_round_id", None)
    if expected_rid is not None:
        actual_rid = int(payload.get("round_id", 0))
        if actual_rid != int(expected_rid):
            print(
                f"ERROR: state advanced since you read it "
                f"(your round_id={expected_rid}, current={actual_rid}). "
                f"Re-run `state` and try again."
            )
            return False

    if not payload.get("two_pilot"):
        return True                     # single-pilot legacy path

    # Bug #31: require --seat in two-pilot mode for state-mutating commands.
    if seat is None:
        print(
            "ERROR: --seat P1|P2 is required in two-pilot mode "
            "(bug #31). Re-run with `--seat P1` or `--seat P2`."
        )
        return False

    # During the block window the defender drives the harness — skip active-player check.
    if allow_during_block_window and payload.get("awaiting_blocks"):
        return True

    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]
    game  = payload["game"]
    active = game.state.active_player

    seat_player_id = p1_id if seat == "P1" else p2_id
    if seat_player_id != active:
        active_label = "P1" if active == p1_id else "P2"
        print(f"ERROR: not your turn (active: {active_label})")
        return False
    return True


# ---------- subcommands ----------

def cmd_start(args) -> None:
    from src.engine.game import Game

    decks_file = getattr(args, "decks_file", None)
    p1_deck = _resolve_deck(args.p1_deck, decks_file)
    p2_deck = _resolve_deck(args.p2_deck, decks_file)

    if args.seed is not None:
        random.seed(args.seed)

    game = Game(mode="finance")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.setup_finance_player(p1)
    game.setup_finance_player(p2)
    for cd in p1_deck:
        game.add_card_to_library(p1.id, cd)
    for cd in p2_deck:
        game.add_card_to_library(p2.id, cd)
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)

    # Turn manager / combat manager are auto-created by FinanceModeAdapter.
    tm = game.turn_manager
    if tm is None:
        raise RuntimeError(
            "FinanceTurnManager not created — check FinanceModeAdapter.create_turn_manager."
        )
    tm.set_turn_order([p1.id, p2.id])

    # Wire combat manager onto the turn manager (the manager looks for this).
    if tm.finance_combat_manager is None:
        from src.engine.finance_combat import FinanceCombatManager
        tm.finance_combat_manager = FinanceCombatManager(game.state, game.pipeline)

    two_pilot = bool(getattr(args, "two_pilot", False))
    if not two_pilot:
        # Single-pilot mode: P2 is AI. Register the medium-tier adapter.
        from src.ai.finance_adapter import FinanceAIAdapter
        tm.set_ai_handler(p2.id, FinanceAIAdapter(difficulty="medium"))
        game.set_ai_player(p2.id)

    # Start the game (deal opening hands, run mode-adapter game-start hook).
    asyncio.run(game.start_game())

    # Manually run PRE_MARKET + RESEARCH for the starting player so the pilot
    # can take actions immediately during TRADING_SESSION.
    asyncio.run(_run_pre_market_and_research(
        {"game": game, "p1_id": p1.id, "p2_id": p2.id}, p1.id
    ))

    payload = {
        "game": game,
        "p1_id": p1.id,
        "p2_id": p2.id,
        "two_pilot": two_pilot,
        "history": [],
        # Two-pilot block-window flag — set True when active player ended
        # turn with attackers declared. While True, the defender (not
        # state.active_player) drives the harness via `block ...` and
        # finally `resolve_combat`.
        "awaiting_blocks": False,
        # Bug #23: per-window flag so the attacker can't race past the
        # defender. While awaiting_blocks=True AND this is False, the
        # ATTACKER cannot resolve_combat / end_turn — only the defender
        # (or the act of blocking / done_blocks) can flip this True.
        "blocks_committed_by_defender": False,
        # bug #11: round_id increments per successful mutation, so pilots
        # can detect intervening writes between their `state` and action.
        "round_id": 0,
    }
    with _exclusive_lock(args.save):
        _save(payload, args.save)
    # Print save path clearly so both pilots can agree on the file before play begins.
    print(f"[harness] state file: {args.save}")
    print(f"Started Finance game: P1={p1.id[:8]} (deck={args.p1_deck}) "
          f"vs P2={p2.id[:8]} (deck={args.p2_deck})"
          f"{' [two-pilot]' if two_pilot else ''}")
    _print_state(payload)


def cmd_state(args) -> None:
    # bug #11: take exclusive lock to ensure read sees a fully written state.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
    # Print save path so both pilots can verify they share the same state file.
    print(f"[harness] state file: {args.save}")
    _print_state(payload)


def cmd_hand(args) -> None:
    import re
    # bug #11: take exclusive lock to ensure read sees a fully written state.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
    game = payload["game"]
    state = game.state
    pid = _acting_player_id(payload)
    player = state.players[pid]
    liq = int(getattr(player, "mana_crystals_available", 0) or 0)
    print(f"=== Hand for {_label_for(payload, pid)} (Liquidity={liq}) ===")
    zone = state.zones.get(f"hand_{pid}")
    if not zone:
        print("  (no hand zone)")
        return
    for oid in zone.objects:
        obj = state.objects.get(oid)
        if not obj or not obj.card_def:
            continue
        # Compute cost.
        cost = 0
        if obj.characteristics and obj.characteristics.mana_cost:
            nums = re.findall(r"\{(\d+)\}", obj.characteristics.mana_cost)
            cost = sum(int(n) for n in nums)
        types = obj.characteristics.types
        type_str = ",".join(
            sorted(t.name.replace("FIN_", "") for t in types if t.name.startswith("FIN_"))
        ) or "?"
        affordable = "OK" if liq >= cost else "  "
        pt = ""
        if obj.characteristics.power is not None or obj.characteristics.toughness is not None:
            pt = f" {obj.characteristics.power or 0}/{obj.characteristics.toughness or 0}"
        print(f"  {affordable} [{oid[:8]}] cost={cost}  {type_str:<20} {obj.name}{pt}")


def cmd_play(args) -> None:
    import re
    # bug #11: hold the exclusive lock for the full read-modify-write window.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
        # bug #25: reject if --seat supplied and it's not that seat's turn.
        if not _check_seat(args, payload):
            return
        game = payload["game"]
        pid = _acting_player_id(payload)
        obj = _find_in_hand(game.state, pid, args.card_id)
        if not obj:
            print(f"No card matching {args.card_id!r} in {_label_for(payload, pid)}'s hand")
            return
        # Pre-flight cost check (turn manager silently no-ops if cost > available).
        cost = 0
        if obj.characteristics and obj.characteristics.mana_cost:
            cost = sum(int(n) for n in re.findall(r"\{(\d+)\}", obj.characteristics.mana_cost))
        avail = int(getattr(game.state.players[pid], "mana_crystals_available", 0) or 0)
        if avail < cost:
            print(f"Cannot play {obj.name!r}: cost={cost} but Liquidity={avail} (need {cost-avail} more).")
            return
        targets: list[str] = []
        if args.target:
            targets = [args.target]
        events = asyncio.run(
            game.turn_manager._play_card_action(pid, obj.id, targets)
        )
        print(f"play {obj.name!r}: emitted {len(events)} events")
        payload["history"].append(
            (game.state.turn_number, _label_for(payload, pid), f"play {obj.name}")
        )
        _save(payload, args.save)
    _print_state(payload)


def cmd_attack(args) -> None:
    # bug #11: hold the exclusive lock for the full read-modify-write window.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
        # bug #25: reject if --seat supplied and it's not that seat's turn.
        if not _check_seat(args, payload):
            return
        game = payload["game"]
        state = game.state
        pid = _acting_player_id(payload)
        tm = game.turn_manager
        if tm.finance_combat_manager is None:
            print("No combat manager wired — cannot declare attackers.")
            return
        # Resolve attacker prefixes.
        full_ids: list[str] = []
        for prefix in args.attackers:
            obj = _find_on_battlefield(state, pid, prefix)
            if not obj:
                print(f"  attacker {prefix!r} not found, skipping")
                continue
            full_ids.append(obj.id)
        if not full_ids:
            print("No valid attackers — nothing declared.")
            return
        # Filter to legal attackers (untapped, no summoning sickness).
        legal = set(tm.finance_combat_manager.get_legal_attackers(pid))
        illegal_pre = [a for a in full_ids if a not in legal]
        chosen = [a for a in full_ids if a in legal]
        if not chosen:
            if illegal_pre:
                print(f"  warning: skipping illegal attackers (tapped or summoning-sick): "
                      f"{[a[:8] for a in illegal_pre]}")
            print("All requested attackers are illegal — nothing declared.")
            return
        # Bug #18 fix: do NOT call declare_attackers() here — that fires
        # ATTACK_DECLARED with a partial attacker count (count==1 for the
        # first cmd_attack call), giving the first-declared attacker an
        # unearned Alpha Strike bonus even in multi-attack.  We instead just
        # accumulate IDs here; _resolve_declared_combat calls declare_attackers
        # once with the full list so all ATTACK_DECLARED triggers see the
        # correct final count.
        already = list(tm.fin_turn_state.attackers_declared or [])
        tm.fin_turn_state.attackers_declared = already + [a for a in chosen if a not in already]
        # Bug #30: only emit the "skipping illegal" warning if at least one
        # of the declared IDs was actually skipped. Re-read the post-commit
        # attackers list and warn only on the difference between requested
        # and accepted. Fixes the stale-state misread that produced spurious
        # warnings when ALL requested attackers were accepted.
        accepted_set = set(tm.fin_turn_state.attackers_declared or [])
        actually_skipped = [a for a in full_ids if a not in accepted_set]
        if actually_skipped:
            print(f"  warning: skipping illegal attackers (tapped or summoning-sick): "
                  f"{[a[:8] for a in actually_skipped]}")
        print(f"declared attackers: {[a[:8] for a in chosen]}")
        payload["history"].append(
            (game.state.turn_number, _label_for(payload, pid),
             f"attack {[a[:8] for a in chosen]}")
        )
        _save(payload, args.save)
    _print_state(payload)


def cmd_block(args) -> None:
    """Record a blocker assignment. Combat resolves at end_turn.

    Two-pilot, block window (``awaiting_blocks=True``):
        The defender (the seat opposite ``state.active_player``) owns
        the blockers. ``_acting_player_id`` already returns the defender
        in this window, so blockers are looked up on defender's side and
        attackers on the attacker's (active_player) side.

    Single-pilot or pre-block-window two-pilot:
        Legacy behavior — the active player is recording their own
        opponent's blocker (rare, used during AI/human asymmetric flows).
    """
    # bug #11: hold the exclusive lock for the full read-modify-write window.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
        # bug #25: block/resolve_combat are allowed for the non-active defender
        # during the awaiting_blocks window; otherwise verify seat.
        if not _check_seat(args, payload, allow_during_block_window=True):
            return
        game = payload["game"]
        state = game.state
        tm = game.turn_manager
        awaiting = _is_awaiting_blocks(payload)

        if awaiting:
            # Defender's seat owns blockers; attacker is the active player.
            defender_id = _acting_player_id(payload)
            attacker_player_id = game.state.active_player
            if attacker_player_id == defender_id:
                print("  block window state inconsistent (defender == active player)")
                return
            blocker = _find_on_battlefield(state, defender_id, args.blocker_id)
            if not blocker:
                print(f"  blocker {args.blocker_id!r} not found on defender's battlefield")
                return
            attacker = _find_on_battlefield(state, attacker_player_id, args.attacker_id)
            if not attacker:
                print(f"  attacker {args.attacker_id!r} not found on attacker's battlefield")
                return
            if attacker.id not in tm.fin_turn_state.attackers_declared:
                print(f"  warning: {attacker.id[:8]} is not in declared attackers — block ignored")
                return
            # Disallow assigning the same blocker to two attackers.
            already_used_for = next(
                (atk_id for atk_id, blk_id in tm.fin_turn_state.combat_blocks.items()
                 if blk_id == blocker.id and atk_id != attacker.id),
                None,
            )
            if already_used_for:
                print(f"  blocker {blocker.name!r} already assigned to "
                      f"{already_used_for[:8]} — reassign by `resolve_combat` first or pick another.")
                return
            tm.fin_turn_state.combat_blocks[attacker.id] = blocker.id
            # Bug #23: defender has acted — flip the gate so the attacker
            # may now safely call `resolve_combat` / `end_turn`.
            payload["blocks_committed_by_defender"] = True
            print(f"recorded block: {blocker.name!r} -> {attacker.name!r}")
            payload["history"].append(
                (game.state.turn_number, _label_for(payload, defender_id),
                 f"block {blocker.name} <- {attacker.name}")
            )
            _save(payload, args.save)
            _print_state(payload)
            return

        # Legacy / single-pilot path — active player records opponent's blocker.
        pid = _acting_player_id(payload)
        opp_id = tm._get_opponent(pid)
        if opp_id is None:
            print("No opponent found.")
            return
        # Blockers belong to the opponent.
        blocker = _find_on_battlefield(state, opp_id, args.blocker_id)
        if not blocker:
            print(f"  blocker {args.blocker_id!r} not found on opponent's battlefield")
            return
        attacker = _find_on_battlefield(state, pid, args.attacker_id)
        if not attacker:
            print(f"  attacker {args.attacker_id!r} not found on active battlefield")
            return
        if attacker.id not in tm.fin_turn_state.attackers_declared:
            print(f"  warning: {attacker.id[:8]} is not in declared attackers — block ignored")
            return
        tm.fin_turn_state.combat_blocks[attacker.id] = blocker.id
        print(f"recorded block: {blocker.name!r} -> {attacker.name!r}")
        payload["history"].append(
            (game.state.turn_number, _label_for(payload, opp_id),
             f"block {blocker.name} <- {attacker.name}")
        )
        _save(payload, args.save)
    _print_state(payload)


def cmd_done_blocks(args) -> None:
    """Defender explicitly closes the block window without recording any
    further blocks (bug #23).

    The defender can use this to say "I don't want to block any of the
    declared attackers; let combat damage proceed." Sets
    ``blocks_committed_by_defender=True`` so the attacker may now safely
    issue ``resolve_combat`` / ``end_turn``.

    Existing blocks (if any were already issued via ``block``) are
    preserved — this command only signals "I'm done assigning."

    Issued by the defender. No-op outside the block window.
    """
    with _exclusive_lock(args.save):
        payload = _load(args.save)
        # Allowed for the non-active defender during the block window.
        if not _check_seat(args, payload, allow_during_block_window=True):
            return
        if not payload.get("two_pilot"):
            print("done_blocks is only meaningful in --two-pilot mode.")
            return
        if not payload.get("awaiting_blocks"):
            print("Not awaiting blocks — nothing to close. "
                  "Use `attack <id>...` then `end_turn` to enter the block window.")
            _print_state(payload)
            return
        # Defender confirms they're done.
        payload["blocks_committed_by_defender"] = True
        game = payload["game"]
        defender_id = _acting_player_id(payload)
        payload["history"].append(
            (game.state.turn_number, _label_for(payload, defender_id),
             "done_blocks (defender closed window)")
        )
        print("done_blocks: defender closed the block window. "
              "Either seat may now `resolve_combat`.")
        _save(payload, args.save)
        _print_state(payload)


def _advance_to_next_turn(payload: dict[str, Any], save_path: str) -> None:
    """After active turn finishes, hand control to the next pilot.

    Shared by ``cmd_end_turn`` (no-attackers / single-pilot path) and
    ``cmd_resolve_combat`` (two-pilot, post-block-window path).
    """
    game = payload["game"]
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]
    two_pilot = payload.get("two_pilot", False)

    # _advance_turn already bumped current_player_index. Use it to find next.
    tm = game.turn_manager
    if tm.turn_order:
        next_player = tm.turn_order[tm.current_player_index]
    else:
        # Fallback: flip from previous active.
        prev = game.state.active_player
        next_player = p2_id if prev == p1_id else p1_id

    if two_pilot:
        # Run PRE_MARKET + RESEARCH for the next player so they can act.
        asyncio.run(_run_pre_market_and_research(payload, next_player))
        payload["history"].append(
            (game.state.turn_number, _label_for(payload, next_player),
             "begin of turn (two-pilot)")
        )
        # Clear block-window flag now that we've handed off.
        payload["awaiting_blocks"] = False
        _save(payload, save_path)
        _print_state(payload)
        return

    # Single-pilot: if next is the AI, run their full turn via the turn manager,
    # then begin the human's next turn.
    if next_player == p2_id:
        asyncio.run(game.turn_manager.run_turn(player_id=p2_id))
        payload["history"].append(
            (game.state.turn_number, "P2", "AI took turn")
        )
        if game.is_game_over():
            _save(payload, save_path)
            _print_state(payload)
            return
        # Begin human's next turn.
        asyncio.run(_run_pre_market_and_research(payload, p1_id))
        payload["history"].append(
            (game.state.turn_number, "P1", "begin of turn")
        )
    else:
        # Human is next (unusual but handle gracefully).
        asyncio.run(_run_pre_market_and_research(payload, next_player))
        payload["history"].append(
            (game.state.turn_number, _label_for(payload, next_player),
             "begin of turn")
        )
    _save(payload, save_path)
    _print_state(payload)


def cmd_end_turn(args) -> None:
    """End the current turn.

    Two-pilot mode: if the active player declared attackers and we are
    not yet in the block window, advance phase to SETTLEMENT, set
    ``awaiting_blocks=True``, and STOP — the defender's pilot must run
    ``block`` then ``resolve_combat`` to release the turn.

    If a pilot accidentally calls ``end_turn`` again while
    ``awaiting_blocks=True``, treat it as ``resolve_combat`` (forgiving
    alias — Pilot B's report flagged this case).

    Otherwise (no attackers, or single-pilot mode), finish the turn and
    advance immediately.
    """
    # bug #11: peek at awaiting_blocks under lock so the forgiving-alias
    # delegate (cmd_resolve_combat) can take its own fresh lock without
    # us holding it.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
        is_alias = bool(payload.get("two_pilot") and payload.get("awaiting_blocks"))
        # Bug #23 + #31: if the attacker tries to end_turn during the block window
        # before the defender has acted, REJECT. Only the defender (or
        # blocks-committed flag flip) can release the gate.
        #
        # Bug #31 (iter-4 race recurrence): the original gate was
        # `if seat is not None and seat == attacker_seat`. A pilot who
        # forgot --seat in two-pilot mode bypassed the gate entirely and
        # raced past the defender. Now that --seat is REQUIRED in
        # two-pilot mode (enforced via _check_seat below), we can gate
        # solely on `seat == attacker_seat` knowing seat is set.
        if is_alias and not payload.get("blocks_committed_by_defender", False):
            seat = getattr(args, "seat", None)
            attacker_id = payload["game"].state.active_player
            attacker_seat = "P1" if attacker_id == payload["p1_id"] else "P2"
            if seat is None and payload.get("two_pilot"):
                # _check_seat will catch this below, but emit a specific
                # error so the pilot understands why the action was
                # rejected (gate vs seat-required).
                print(
                    "ERROR: --seat P1|P2 is required in two-pilot mode "
                    "(bug #31). Re-run with `--seat P1` or `--seat P2`."
                )
                return
            if seat == attacker_seat:
                print(
                    "ERROR: Block window still open — wait for defender to "
                    "issue `block` or `done_blocks` (or for defender to call "
                    "`resolve_combat` themselves)."
                )
                return
    if is_alias:
        print("(awaiting_blocks=True — treating `end_turn` as `resolve_combat`.)")
        cmd_resolve_combat(args)
        return

    # bug #11: hold the lock for the full RMW window of the normal end_turn path.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
        # bug #25: during end_turn the active player must match --seat (if given).
        # Block window case is handled above (delegated to resolve_combat).
        if not _check_seat(args, payload):
            return
        game = payload["game"]
        two_pilot = payload.get("two_pilot", False)
        if game.is_game_over():
            print("Game already over.")
            _print_state(payload)
            return

        if two_pilot:
            from src.engine.finance_turn import FinancePhase
            tm = game.turn_manager
            attackers = list(tm.fin_turn_state.attackers_declared or [])
            if attackers and tm.finance_combat_manager is not None:
                # Active player declared attackers — open the block window.
                pid = tm.fin_turn_state.active_player_id
                # Close TRADING_SESSION cleanly so the defender's window has a
                # well-defined phase.
                tm._emit_phase("trading_session", "end", pid)
                # Move into SETTLEMENT but DO NOT resolve combat yet.
                tm.fin_turn_state.phase = FinancePhase.SETTLEMENT
                tm._emit_phase("settlement", "start", pid)
                payload["awaiting_blocks"] = True
                # Bug #23: reset the defender-acted flag for this fresh
                # block window. Until the defender blocks / done_blocks /
                # calls resolve_combat themselves, the attacker cannot
                # advance past this gate.
                payload["blocks_committed_by_defender"] = False
                payload["history"].append(
                    (game.state.turn_number, _label_for(payload, pid),
                     f"end_turn (await blocks: {[a[:8] for a in attackers]})")
                )
                _save(payload, args.save)
                _print_state(payload)
                return

        # Finish current player's turn (combat resolution + settlement + market_close).
        asyncio.run(_finish_turn(payload))
        if game.is_game_over():
            payload["history"].append(
                (game.state.turn_number, "SYS", "game over")
            )
            _save(payload, args.save)
            _print_state(payload)
            return

        payload["awaiting_blocks"] = False
        _advance_to_next_turn(payload, args.save)


def cmd_resolve_combat(args) -> None:
    """Two-pilot only: resolve declared combat after the block window.

    Called by the defender after they've issued any ``block`` commands
    they want. Resolves combat damage, finishes the active player's
    turn (SETTLEMENT close + MARKET_CLOSE), advances to the defender's
    own PRE_MARKET + RESEARCH, and ends in TRADING_SESSION so the
    defender can take actions on their new turn.

    No-op if ``awaiting_blocks`` is False (just nudges the user toward
    ``end_turn``). Single-pilot mode does not use this command — the
    AI's blocker logic runs synchronously during ``end_turn``.
    """
    # bug #11: hold the exclusive lock for the full RMW window.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
        # bug #25: resolve_combat is issued by the defender during the block
        # window, so allow the non-active seat to call it (allow_during_block_window).
        if not _check_seat(args, payload, allow_during_block_window=True):
            return
        game = payload["game"]
        if game.is_game_over():
            print("Game already over.")
            _print_state(payload)
            return

        if not payload.get("two_pilot"):
            print("resolve_combat is only meaningful in --two-pilot mode. "
                  "In single-pilot mode use `end_turn` (AI blocks automatically).")
            return

        if not payload.get("awaiting_blocks"):
            print("Not awaiting blocks — nothing to resolve. "
                  "Use `attack <id>...` then `end_turn` to enter the block window.")
            _print_state(payload)
            return

        # Bug #23 + #31: gate the attacker. With --seat now REQUIRED in
        # two-pilot mode (enforced via _check_seat above), we know seat
        # is set if we get here in two-pilot. The bug-#31 fix closes the
        # iter-4 recurrence where a pilot who forgot --seat bypassed the
        # gate entirely. The defender CAN call resolve_combat at any
        # time (treated as "no blocks / proceed").
        if not payload.get("blocks_committed_by_defender", False):
            seat = getattr(args, "seat", None)
            attacker_id = game.state.active_player
            attacker_seat = "P1" if attacker_id == payload["p1_id"] else "P2"
            if seat == attacker_seat:
                print(
                    "ERROR: Block window still open — wait for defender to "
                    "issue `block` or `done_blocks` (or for defender to call "
                    "`resolve_combat` themselves)."
                )
                return
            # Defender (or single-pilot legacy caller) is closing the window —
            # mark the gate satisfied so any post-resolve telemetry agrees.
            payload["blocks_committed_by_defender"] = True

        # bug #24: clear awaiting_blocks immediately after resolve_combat so
        # the flag never persists if an early-return or exception fires below.
        asyncio.run(_resolve_declared_combat(payload))
        payload["awaiting_blocks"] = False          # bug #24 fix — explicit clear
        if game.is_game_over():
            payload["history"].append(
                (game.state.turn_number, "SYS", "game over (combat)")
            )
            _save(payload, args.save)
            _print_state(payload)
            return

        # Finish the active turn (post-combat phases). SETTLEMENT/start was
        # already emitted in cmd_end_turn when we opened the block window.
        asyncio.run(_finish_active_turn_post_combat(payload, settlement_already_started=True))
        if game.is_game_over():
            payload["history"].append(
                (game.state.turn_number, "SYS", "game over (post-combat)")
            )
            payload["awaiting_blocks"] = False
            _save(payload, args.save)
            _print_state(payload)
            return

        payload["history"].append(
            (game.state.turn_number, "SYS", "combat resolved (two-pilot)")
        )
        payload["awaiting_blocks"] = False
        _advance_to_next_turn(payload, args.save)


def cmd_history(args) -> None:
    # bug #11: lock the read so we don't observe a half-written pickle.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
    print("=== Action history ===")
    for turn, actor, action in payload["history"]:
        print(f"  turn {turn}  {actor:<3}  {action}")


def cmd_result(args) -> None:
    # bug #11: lock the read so we don't observe a half-written pickle.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
    game = payload["game"]
    if not game.is_game_over():
        print("in progress")
        return
    winner = game.get_winner()
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]
    if winner == p1_id:
        print("P1 won")
    elif winner == p2_id:
        print("P2 won")
    else:
        print("draw")


# ---------- choose subcommand (bug #20b) ----------

def cmd_choose(args) -> None:
    """Submit a player's pending-choice selection.

    Resolves stall in two-pilot mode where a card emits SEARCH_LIBRARY or
    similar PendingChoice (e.g. Dark Inventory Position's tutor) and the
    harness has no way to advance.

    Usage:
        finance_wet_test choose <option_index|option_id>
        finance_wet_test choose <option_index> <option_index> ...   # for multi-pick

    The option_id can be:
      - an integer (treated as offset into the current pending_choice.options list);
      - a card-id prefix (matched against object IDs in options);
      - the literal string "skip" (submits an empty selection — only valid for
        optional / may-style choices).
    """
    # bug #11: hold lock for full RMW window.
    with _exclusive_lock(args.save):
        payload = _load(args.save)
        game = payload["game"]
        choice = game.state.pending_choice
        if choice is None:
            print("No pending choice — nothing to submit.")
            _print_state(payload)
            return

        # Resolve raw option tokens to choice IDs.
        raw_options = list(args.options)
        selected: list = []
        if not raw_options or (len(raw_options) == 1 and raw_options[0] == "skip"):
            selected = []
        else:
            for token in raw_options:
                # Try integer index first.
                opt_idx = None
                try:
                    opt_idx = int(token)
                except ValueError:
                    pass
                if opt_idx is not None and 0 <= opt_idx < len(choice.options):
                    chosen = choice.options[opt_idx]
                    selected.append(
                        chosen.get("id") if isinstance(chosen, dict) else chosen
                    )
                    continue
                # Otherwise, prefix-match against option IDs.
                matched = False
                for opt in choice.options:
                    opt_id = opt.get("id") if isinstance(opt, dict) else opt
                    if isinstance(opt_id, str) and opt_id.startswith(token):
                        selected.append(opt_id)
                        matched = True
                        break
                if not matched:
                    print(f"  option {token!r} not found in pending_choice.options")
                    return

        ok, err, _events = game.submit_choice(choice.id, choice.player, selected)
        if not ok:
            print(f"  submit_choice failed: {err}")
            return

        print(f"choose: submitted {selected!r} for choice_id={choice.id}")
        payload["history"].append(
            (game.state.turn_number, _label_for(payload, choice.player),
             f"choose {selected!r}")
        )
        _save(payload, args.save)
    _print_state(payload)


# ---------- argparse ----------

def main() -> None:
    parser = argparse.ArgumentParser(description="Finance TCG wet-test harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def _add_save(p):
        p.add_argument("--save", default=DEFAULT_STATE_PATH,
                       help=f"State pickle path (default: {DEFAULT_STATE_PATH})")

    # bug #25: shared helper to add --seat to action subparsers.
    # bug #31 (iter-4): also add --expected-round-id for state-drift detection.
    def _add_seat(p):
        p.add_argument(
            "--seat", choices=["P1", "P2"], default=None,
            help="(two-pilot) Declare which seat is acting. REQUIRED in two-pilot mode "
                 "(bug #31). Action is rejected with 'not your turn' if the seat doesn't "
                 "match state.active_player_id. Omit for legacy single-pilot behaviour. "
                 "Exception: block/resolve_combat accept either seat during the "
                 "awaiting_blocks defender window.",
        )
        p.add_argument(
            "--expected-round-id", type=int, default=None,
            dest="expected_round_id",
            help="(optional) round_id you observed when you last ran `state`. "
                 "If the current state's round_id is different, the action is "
                 "rejected so you re-read state instead of mutating from stale info. "
                 "Bug #31b — closes the read/act race window.",
        )

    p_start = sub.add_parser("start", help="Start a new Finance game")
    p_start.add_argument("--p1-deck", default="FINA_high_frequency",
                         help="Starter deck name for P1 (default: FINA_high_frequency)")
    p_start.add_argument("--p2-deck", default="FINA_quant",
                         help="Starter deck name for P2 (default: FINA_quant)")
    p_start.add_argument("--two-pilot", action="store_true", default=False,
                         help="Two-pilot mode (skip AI execution; pilots drive both seats)")
    p_start.add_argument("--seed", type=int, default=None,
                         help="Random seed for deck shuffling")
    p_start.add_argument("--decks-file", default=None,
                         help="Optional JSON file with custom deck specs "
                              "(see logs/finance_candidate_decks.json shape). "
                              "Names from the file take precedence over FINA starters.")
    _add_save(p_start)
    p_start.set_defaults(fn=cmd_start)

    p_state = sub.add_parser("state", help="Print current game state")
    _add_save(p_state)
    p_state.set_defaults(fn=cmd_state)

    p_hand = sub.add_parser("hand", help="List the active player's hand")
    _add_save(p_hand)
    _add_seat(p_hand)   # bug #25 (accepted for symmetry; read-only, no enforcement)
    p_hand.set_defaults(fn=cmd_hand)

    p_play = sub.add_parser("play", help="Play a card by ID prefix")
    p_play.add_argument("card_id", help="Card ID prefix (or full name)")
    p_play.add_argument("--target", default=None, help="Optional target object ID")
    _add_save(p_play)
    _add_seat(p_play)   # bug #25
    p_play.set_defaults(fn=cmd_play)

    p_atk = sub.add_parser("attack", help="Declare attackers (variadic ID prefixes)")
    p_atk.add_argument("attackers", nargs="+", help="Attacker ID prefixes")
    _add_save(p_atk)
    _add_seat(p_atk)    # bug #25
    p_atk.set_defaults(fn=cmd_attack)

    p_blk = sub.add_parser("block", help="Assign a single blocker to an attacker")
    p_blk.add_argument("blocker_id", help="Defender's blocker ID prefix")
    p_blk.add_argument("attacker_id", help="Attacker ID prefix to block")
    _add_save(p_blk)
    _add_seat(p_blk)    # bug #25 (allowed for defender during block window)
    p_blk.set_defaults(fn=cmd_block)

    p_end = sub.add_parser("end_turn", help="End the current player's turn")
    _add_save(p_end)
    _add_seat(p_end)    # bug #25
    p_end.set_defaults(fn=cmd_end_turn)

    p_resolve = sub.add_parser(
        "resolve_combat",
        help="(two-pilot) After defender assigns blocks, resolve combat & advance",
    )
    _add_save(p_resolve)
    _add_seat(p_resolve)  # bug #25 (allowed for defender during block window)
    p_resolve.set_defaults(fn=cmd_resolve_combat)

    # Bug #23: defender's explicit "I'm done blocking" command.
    for name in ("done_blocks", "pass_blocks"):
        p_done = sub.add_parser(
            name,
            help="(two-pilot) Defender closes block window without further blocks",
        )
        _add_save(p_done)
        _add_seat(p_done)  # allowed for defender during block window
        p_done.set_defaults(fn=cmd_done_blocks)

    p_hist = sub.add_parser("history", help="Show recent action log")
    _add_save(p_hist)
    p_hist.set_defaults(fn=cmd_history)

    p_res = sub.add_parser("result", help="Show winner or 'in progress'")
    _add_save(p_res)
    p_res.set_defaults(fn=cmd_result)

    # bug #20b: choose subcommand for resolving PendingChoice (e.g. tutors).
    p_choose = sub.add_parser(
        "choose",
        help="Submit a pending choice (tutor pick, modal, etc.). Pass option index/id(s) or 'skip'.",
    )
    p_choose.add_argument(
        "options", nargs="*",
        help="Option index (0-based) or id-prefix; pass nothing or 'skip' for empty/optional choices",
    )
    _add_save(p_choose)
    p_choose.set_defaults(fn=cmd_choose)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
