"""SCP-engine tournament adapter for the /new-set balance loop.

Round-robins SCP AI-vs-AI games across a list of deck labels and emits the
canonical extended JSON contract that ``capability_audit.py``, ``coverage.py``,
and ``balance_loop.py`` consume:

    {
      "set_summary":       { "<deck_label>": {wins, losses, winrate, ...}, ... },
      "matchup":           { "A vs B": {wins_a, wins_b, draws, ...}, ... },
      "card_scores":       { "<DECK_LABEL>::<Card>": {...}, ... },
      "ai_action_counts":  { "<ACTION_TYPE>": int, ... },
      "mechanic_triggers": { "<MECHANIC_NAME>": int, ... },
      "available_actions": [ "<ACTION_TYPE>", ... ],
      "card_errors":       { "<Card>": "trace excerpt", ... },
    }

Wraps (does not modify) ``scripts/play/scp_tournament.py``. The inner
``run_one_game`` helper is re-used; this adapter additionally:

  * Tracks per-event action counts post-hoc from ``state.event_log``
    (SCP's turn manager calls ``ai_handler.take_turn`` which performs engine
    actions directly, so action selection isn't routed through a Decision
    layer the way Depths is — log-walking is the cleanest counting strategy
    without disturbing the AI adapter).
  * Detects mechanic triggers from the same event log (SCP_FORGET →
    Antimeme, SCP_MNESTIC_ACTIVE → Mnestic Wake, SCP_COG_HAZARD_TICK →
    Cognitive Hazard, SCP_REDACT → Redact, SCP_BREACH_TICK → Breach Audit,
    etc.).
  * Computes per-card stats keyed by ``<DECK_LABEL>::<Card Name>`` by walking
    ``state.event_log`` for ZONE_CHANGE / SCP_OPEN_DOSSIER / SCP_CONTAINED /
    SCP_ARCHIVE_GAINED events plus the final battlefield scan.
  * Filters ``available_actions`` against the deck pool so the audit doesn't
    misreport deck-composition gaps as AI omissions.

# TODO(FBN): The detection map below covers MNR + SZB + core SCP mechanics.
# When Foundations Beyond (FBN) lands new mechanics whose engine plumbing
# isn't merged yet (e.g. ``Compleation Vector`` → ``scp_compleation_counters``
# bumps, ``Spark Containment`` → ``state.scp_clearance`` bumps), extend
# ``_MECHANIC_DETECTORS`` below by adding a detector function and registering
# it under the printed mechanic name. The hardcoded dict pattern keeps the
# adapter readable; a ``--mechanic-map`` flag for runtime override is
# documented in the CLI but defers to the hardcoded dict for now.

CLI:
    python -m scripts.new_set._adapters.scp_tournament_adapter \\
        --decks "FBN_phyrexian_strain:src.cards.scp.foundations_beyond.decks:make_phyrexian_strain_deck,..." \\
        --games-per-pairing 50 \\
        --set FBN \\
        --out logs/balance_fbn_round_1.json

Deck-label naming convention: each label must start with ``<SET>_`` (the value
passed to ``--set``). This is what ``balance_loop.py``'s
``domain_matches_set`` filter uses; deviating yields empty ``card_scores``
under the set's domain.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import re
import sys
import time
import traceback
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (                                       # noqa: E402
    CardDefinition, CardType, Event, EventType, ZoneType,
)
from src.engine.game import Game                                     # noqa: E402
from src.ai.scp_adapter import (                                     # noqa: E402
    SCPAIAdapter, SUPPORTED_SCP_PILOTS, validate_scp_pilot,
)
from src.cards.scp import SCP_STARTER_DECKS                          # noqa: E402

# Reuse the dispatch wrapper + winner-reason helper from the existing
# tournament so we don't reimplement them. Importing keeps single-source-of-
# -truth for SCP win condition labels.
from scripts.play.scp_tournament import (                            # noqa: E402
    _DispatchSCPAIAdapter, _winner_reason,
)


# =============================================================================
# Deck-builder resolution
# =============================================================================

DeckBuilder = Callable[[], list[CardDefinition]]


def _resolve_builder(spec: str) -> DeckBuilder:
    """Resolve a builder spec into a callable returning ``list[CardDefinition]``.

    Three forms accepted:
      1. ``module.path:func_name``      — import + attr lookup, e.g.
         ``src.cards.scp.foundations_beyond.decks:make_phyrexian_strain_deck``.
      2. ``module.path.func_name``      — last segment is the attr.
      3. ``<starter_deck_id>``          — bare key into ``SCP_STARTER_DECKS``,
         e.g. ``mnestic_reset_division``. Useful for the smoke test.
    """
    if ":" in spec:
        module_path, attr = spec.rsplit(":", 1)
    elif "." in spec and spec.split(".")[-1].startswith(("make_", "build_")):
        # Heuristic: looks like a dotted module-path ending in a builder func.
        module_path, attr = spec.rsplit(".", 1)
    elif spec in SCP_STARTER_DECKS:
        return SCP_STARTER_DECKS[spec]
    else:
        raise ValueError(
            f"Unrecognised builder spec {spec!r}; expected "
            f"'module.path:func_name' or a key in SCP_STARTER_DECKS "
            f"({sorted(SCP_STARTER_DECKS)[:6]}...)"
        )
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"could not import builder module {module_path!r}: {exc}"
        ) from exc
    if not hasattr(mod, attr):
        raise AttributeError(
            f"module {module_path!r} has no attribute {attr!r}"
        )
    builder = getattr(mod, attr)
    if not callable(builder):
        raise TypeError(f"{module_path}:{attr} is not callable")
    return builder


def _parse_decks_arg(decks_arg: str) -> dict[str, DeckBuilder]:
    """Parse ``--decks "label1:builder_spec,label2:builder_spec,..."``.

    Each entry is ``<deck_label>:<builder_spec>``; ``builder_spec`` itself may
    contain a ``:`` (module-path:func), so we split on the FIRST ``:``.
    """
    out: dict[str, DeckBuilder] = {}
    for raw in decks_arg.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if ":" not in raw:
            raise ValueError(
                f"--decks entry must be 'label:builder_spec', got {raw!r}"
            )
        label, builder_spec = raw.split(":", 1)
        label = label.strip()
        builder_spec = builder_spec.strip()
        if not label or not builder_spec:
            raise ValueError(
                f"--decks entry has empty label or spec: {raw!r}"
            )
        if label in out:
            raise ValueError(f"duplicate deck label {label!r} in --decks")
        out[label] = _resolve_builder(builder_spec)
    return out


# =============================================================================
# Action counting via event log
# =============================================================================
#
# SCP's turn manager calls ``scp_ai_handler.take_turn(player_id, state, game)``
# and the heuristic AI directly invokes ``scp.open_dossier(...)``,
# ``scp.contain_anomaly(...)``, etc. There is NO Decision-layer boundary the
# way Depths uses (DecisionTracker wraps the AI adapter and converts dataclass
# actions). The clean place to count is the post-action event log: every
# engine action emits a known SCP_* EventType.
#
# Mapping is many-to-one (one action emits multiple events) so we count the
# action's PRIMARY event type. SCP_END_TURN is implicit (no event); we count
# it from TURN_END.

# EventType -> action_type label. The labels mirror what ``legal_scp_actions``
# uses so the audit's "AI never used this legal action" detector can compare
# apples to apples.
_PRIMARY_EVENT_TO_ACTION: dict[EventType, str] = {
    EventType.SCP_OPEN_DOSSIER:        "SCP_OPEN_DOSSIER",
    EventType.SCP_REVEAL_DOSSIER:      "SCP_REVEAL_DOSSIER",
    EventType.SCP_TEST_RUN:            "SCP_RESEARCH",
    EventType.SCP_CONTAINMENT_ATTEMPT: "SCP_CONTAIN",
    EventType.SCP_ETHICS_SPENT:        "SCP_SPEND_ETHICS",
    EventType.SCP_MOOD_SHIFT:          "SCP_SHIFT_MOOD",
    EventType.SCP_CROSS_CONTAINMENT:   "SCP_CROSS_CONTAIN",
    EventType.SCP_MEMORY_HOLE:         "SCP_MEMORY_HOLE",
    EventType.SCP_PROTOCOL_APPLIED:    "SCP_APPLY_PROTOCOL",
    EventType.SCP_INCIDENT_RESOLVED:   "SCP_RESOLVE_INCIDENT",
}

# SCP_SUPPRESS shares SCP_ASSIGN_STAFF with SCP_RESEARCH and SCP_CONTAIN.
# The cleanest disambiguation is via the SCP_BREACH_TICK -1 secrecy hit (no)
# — actually, suppress_anomaly emits a single SCP_ASSIGN_STAFF with a payload
# discriminator. Inspect the payload to choose research/contain/suppress.
# The "action" key on SCP_ASSIGN_STAFF tracks it; see scp.py emit sites.

# Universe of action types we expect to see somewhere across a tournament.
# Filtered downstream against deck composition so the audit doesn't flag
# "DEMO never used Mood Shift" when no card grants briefing.
_BASE_AVAILABLE_ACTIONS = {
    "SCP_OPEN_DOSSIER",
    "SCP_FAST_TRACK",      # Variant of SCP_OPEN_DOSSIER w/ fast_track=True
    "SCP_SEAL_DOSSIER",    # Variant of SCP_OPEN_DOSSIER w/ sealed=True
    "SCP_REVEAL_DOSSIER",
    "SCP_RESEARCH",
    "SCP_CONTAIN",
    "SCP_SUPPRESS",
    "SCP_END_TURN",
}

# Conditional actions — only available when the deck/state offers them.
# Audit filter map: action_type -> predicate(deck_pool, state).
# Kept simple: rely on deck-composition signals (subtype / card_def attrs).


# =============================================================================
# Mechanic-trigger detection
# =============================================================================
#
# Each mechanic maps to a detector function that takes (state, ev) and
# returns True when this event represents one firing of the mechanic.

MechanicDetector = Callable[[Any, Event], bool]


def _detect_antimeme(state: Any, ev: Event) -> bool:
    """MNR Antimeme: anomaly removed-from-history into ``scp_forgotten``."""
    return ev.type == EventType.SCP_FORGET


def _detect_mnestic_wake(state: Any, ev: Event) -> bool:
    """MNR Mnestic Wake: personnel gained the Mnestic tag mid-game."""
    return ev.type == EventType.SCP_MNESTIC_ACTIVE


def _detect_redact(state: Any, ev: Event) -> bool:
    """MNR Redact: opponent discard + retroactive event tag."""
    return ev.type == EventType.SCP_REDACT


def _detect_cognitive_hazard(state: Any, ev: Event) -> bool:
    """MNR Cognitive Hazard: opposing-turn hand drain."""
    return ev.type == EventType.SCP_COG_HAZARD_TICK


def _detect_breach_audit(state: Any, ev: Event) -> bool:
    """Core SCP: end-of-turn breach tick from active anomalies."""
    return ev.type == EventType.SCP_BREACH_TICK


def _detect_dossier_open(state: Any, ev: Event) -> bool:
    """Core SCP: a dossier moved into the active queue (open / fast-track / seal)."""
    return ev.type == EventType.SCP_OPEN_DOSSIER


def _detect_contained(state: Any, ev: Event) -> bool:
    """Core SCP: anomaly successfully contained (Thaumiel / Quarantine pivot)."""
    return ev.type == EventType.SCP_CONTAINED


def _detect_archive_gained(state: Any, ev: Event) -> bool:
    """Core SCP: player gained archive progress (research / contain payoff)."""
    return ev.type == EventType.SCP_ARCHIVE_GAINED


def _detect_cross_containment(state: Any, ev: Event) -> bool:
    """Core SCP: contained anomaly suppresses/reframes another (combo)."""
    return ev.type == EventType.SCP_CROSS_CONTAINMENT


def _detect_audit(state: Any, ev: Event) -> bool:
    """Core SCP: cross-site audit / whistleblower interference (GOI archetype)."""
    return ev.type == EventType.SCP_AUDIT


def _detect_protocol(state: Any, ev: Event) -> bool:
    """Core SCP: protocol applied (mood shift / curiosity reframe)."""
    return ev.type == EventType.SCP_PROTOCOL_APPLIED


def _detect_goi_raid(state: Any, ev: Event) -> bool:
    """Core SCP: external GOI interference."""
    return ev.type == EventType.SCP_GOI_RAID


def _detect_memory_hole(state: Any, ev: Event) -> bool:
    """Core SCP: memory_hole — card redacted from records (MNR alt-win bridge)."""
    return ev.type == EventType.SCP_MEMORY_HOLE


def _detect_ethics_spent(state: Any, ev: Event) -> bool:
    """Core SCP: ethics debt used as a strategic resource (ETH archetype)."""
    return ev.type == EventType.SCP_ETHICS_SPENT


# Default mechanic name -> detector dict. Order is presentation-only; the
# audit consumes a dict, not a list.
_DEFAULT_MECHANIC_DETECTORS: dict[str, MechanicDetector] = {
    # MNR/SZB-era mechanics:
    "Antimeme":             _detect_antimeme,
    "Mnestic Wake":         _detect_mnestic_wake,
    "Redact":               _detect_redact,
    "Cognitive Hazard":     _detect_cognitive_hazard,
    # Core SCP mechanics (every set fires these — useful as baselines):
    "Breach Audit":         _detect_breach_audit,
    "Open Dossier":         _detect_dossier_open,
    "Contained":            _detect_contained,
    "Archive Gained":       _detect_archive_gained,
    "Cross-Containment":    _detect_cross_containment,
    "Audit / Whistleblow":  _detect_audit,
    "Protocol Applied":     _detect_protocol,
    "GOI Raid":             _detect_goi_raid,
    "Memory Hole":          _detect_memory_hole,
    "Ethics Spent":         _detect_ethics_spent,
    # TODO(FBN): add detectors for Compleation Vector, Spark Containment,
    # and any other FBN mechanics here once their engine plumbing lands.
    # Pattern:
    #   def _detect_compleation_vector(state, ev):
    #       # Could look at ev.type == EventType.SCP_COMPLEATION_TICK once added,
    #       # or scan state.scp_compleation_counters delta if no dedicated event.
    #       ...
    #   _DEFAULT_MECHANIC_DETECTORS["Compleation Vector"] = _detect_compleation_vector
}


def _load_mechanic_map(spec: str | None) -> dict[str, MechanicDetector]:
    """Load a mechanic detector map. ``spec`` is an optional
    ``module.path:DICT_NAME`` reference whose module exports a dict with the
    same shape as ``_DEFAULT_MECHANIC_DETECTORS``. The user's dict is MERGED
    on top of the defaults (entries with matching keys override).
    """
    if not spec:
        return dict(_DEFAULT_MECHANIC_DETECTORS)
    module_path, attr = spec.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    user_map = getattr(mod, attr)
    if not isinstance(user_map, dict):
        raise TypeError(f"{spec} must be a dict[str, callable]")
    merged = dict(_DEFAULT_MECHANIC_DETECTORS)
    merged.update(user_map)
    return merged


# =============================================================================
# Per-card stat collection
# =============================================================================

def _card_ref(label: str, card_def: CardDefinition) -> str:
    """Canonical key the balance loop / coverage tools consume."""
    return f"{label}::{card_def.name}"


def _zone_type_for(state: Any, value: Any) -> ZoneType | None:
    if isinstance(value, ZoneType):
        return value
    if isinstance(value, str):
        zone = state.zones.get(value)
        if zone:
            return zone.type
        try:
            return ZoneType[value.upper()]
        except Exception:
            return None
    return None


def _collect_card_stats(
    game: Game,
    p1_id: str,
    p2_id: str,
    p1_label: str,
    p2_label: str,
    deck1: list[CardDefinition],
    deck2: list[CardDefinition],
    winner_id: str | None,
) -> dict[str, dict[str, float]]:
    """Walk event log + final battlefield to compute per-card stats keyed
    ``<DECK_LABEL>::<Card Name>``.

    Fields (mirrors what ``balance_loop.py`` + ``coverage.py`` consume):
      - deck_copies        seeded from the deck list
      - drawn              ZONE_CHANGE LIBRARY→HAND
      - cast               SCP_OPEN_DOSSIER firings (HAND→PENDING/SEALED/ACTIVE)
      - in_play_at_end     final scan over state.objects @ BATTLEFIELD
      - on_winning_side    in_play_at_end AND owner == winner
      - triggers_fired     SCP_ACTIVATE_DOSSIER (pending → active) +
                           SCP_ANOMALY_REVEALED (sealed → active)
      - contained          SCP_CONTAINED (source-attributed for the contained card)
      - archive_contrib    SCP_ARCHIVE_GAINED source-attribution
      - deaths             ZONE_CHANGE BATTLEFIELD→GRAVEYARD (decay / memory hole)
    """
    state = game.state

    stats: dict[str, dict[str, float]] = defaultdict(lambda: {
        "deck_copies": 0,
        "drawn": 0,
        "cast": 0,
        "in_play_at_end": 0,
        "on_winning_side": 0,
        "triggers_fired": 0,
        "contained": 0,
        "archive_contrib": 0.0,
        "deaths": 0,
    })

    def _label_for(owner_id: str | None) -> str | None:
        if owner_id == p1_id:
            return p1_label
        if owner_id == p2_id:
            return p2_label
        return None

    def _ref_for(obj_id: str | None) -> str | None:
        if not obj_id:
            return None
        obj = state.objects.get(obj_id)
        if not obj:
            return None
        cd = getattr(obj, "card_def", None)
        if not cd:
            return None
        label = _label_for(obj.owner)
        if label is None:
            return None
        return _card_ref(label, cd)

    # 1. Seed deck_copies.
    for cd in deck1:
        stats[_card_ref(p1_label, cd)]["deck_copies"] += 1
    for cd in deck2:
        stats[_card_ref(p2_label, cd)]["deck_copies"] += 1

    drawn_seen: set[str] = set()
    cast_seen: set[str] = set()
    contained_seen: set[str] = set()
    death_seen: set[str] = set()

    # 2. Walk the event log.
    for ev in list(getattr(state, "event_log", []) or []):
        et = getattr(ev, "type", None)
        payload = getattr(ev, "payload", {}) or {}
        source_id = getattr(ev, "source", None) or payload.get("source")

        if et == EventType.ZONE_CHANGE:
            obj_id = payload.get("object_id") or payload.get("card_id")
            from_zone = (
                _zone_type_for(state, payload.get("from_zone_type"))
                or _zone_type_for(state, payload.get("from_zone"))
            )
            to_zone = (
                _zone_type_for(state, payload.get("to_zone_type"))
                or _zone_type_for(state, payload.get("to_zone"))
            )
            ref = _ref_for(obj_id)
            if not ref:
                continue
            if from_zone == ZoneType.LIBRARY and to_zone == ZoneType.HAND:
                if obj_id and obj_id not in drawn_seen:
                    drawn_seen.add(obj_id)
                    stats[ref]["drawn"] += 1
            if from_zone == ZoneType.BATTLEFIELD and to_zone == ZoneType.GRAVEYARD:
                if obj_id and obj_id not in death_seen:
                    death_seen.add(obj_id)
                    stats[ref]["deaths"] += 1

        elif et == EventType.SCP_OPEN_DOSSIER:
            obj_id = payload.get("object_id") or payload.get("card_id")
            ref = _ref_for(obj_id)
            if ref and obj_id and obj_id not in cast_seen:
                cast_seen.add(obj_id)
                stats[ref]["cast"] += 1

        elif et == EventType.SCP_ACTIVATE_DOSSIER:
            obj_id = payload.get("object_id") or payload.get("card_id")
            ref = _ref_for(obj_id)
            if ref:
                stats[ref]["triggers_fired"] += 1

        elif et == EventType.SCP_ANOMALY_REVEALED:
            obj_id = payload.get("object_id") or payload.get("card_id")
            ref = _ref_for(obj_id)
            if ref:
                stats[ref]["triggers_fired"] += 1

        elif et == EventType.SCP_CONTAINED:
            target_id = (
                payload.get("anomaly_id")
                or payload.get("object_id")
                or payload.get("target")
            )
            ref = _ref_for(target_id)
            if ref and target_id and target_id not in contained_seen:
                contained_seen.add(target_id)
                stats[ref]["contained"] += 1

        elif et == EventType.SCP_ARCHIVE_GAINED:
            # Attribute the archive gain to whatever object emitted it
            # (typically the anomaly being researched / contained).
            ref = _ref_for(source_id)
            if ref:
                amount = payload.get("amount", payload.get("archives", 0)) or 0
                stats[ref]["archive_contrib"] += float(amount)

    # 3. Final battlefield + on-winning-side scan.
    for obj_id, obj in state.objects.items():
        if not obj or not getattr(obj, "card_def", None):
            continue
        if getattr(obj, "is_token", False):
            continue
        label = _label_for(obj.owner)
        if label is None:
            continue
        ref = _card_ref(label, obj.card_def)
        if obj.zone == ZoneType.BATTLEFIELD:
            stats[ref]["in_play_at_end"] += 1
            if winner_id and obj.owner == winner_id:
                stats[ref]["on_winning_side"] += 1

    return dict(stats)


# =============================================================================
# Action counting via event log
# =============================================================================

def _collect_action_counts(state: Any) -> dict[str, int]:
    """Tally per-action-type counts from the event log post-game.

    SCP_ASSIGN_STAFF disambiguates research/contain/suppress via the
    payload's ``action`` key, set by ``scp.run_test`` /
    ``scp.contain_anomaly`` / ``scp.suppress_anomaly``. SCP_OPEN_DOSSIER
    payloads include ``fast_track`` / ``sealed`` booleans we use to
    sharpen the labels.
    """
    counts: dict[str, int] = defaultdict(int)
    for ev in list(getattr(state, "event_log", []) or []):
        et = getattr(ev, "type", None)
        payload = getattr(ev, "payload", {}) or {}

        if et == EventType.SCP_OPEN_DOSSIER:
            counts["SCP_OPEN_DOSSIER"] += 1
            if payload.get("fast_track"):
                counts["SCP_FAST_TRACK"] += 1
            if payload.get("sealed"):
                counts["SCP_SEAL_DOSSIER"] += 1
            continue

        if et == EventType.SCP_REVEAL_DOSSIER:
            counts["SCP_REVEAL_DOSSIER"] += 1
            continue

        if et == EventType.SCP_ASSIGN_STAFF:
            # The ``action`` payload field is set in scp.run_test /
            # scp.contain_anomaly / scp.suppress_anomaly; fall back to
            # inspecting follow-up events if absent.
            action = payload.get("action") or payload.get("task")
            if action == "research":
                counts["SCP_RESEARCH"] += 1
            elif action == "contain":
                counts["SCP_CONTAIN"] += 1
            elif action == "suppress":
                counts["SCP_SUPPRESS"] += 1
            else:
                # Generic — we don't double-count below.
                counts["SCP_ASSIGN_STAFF"] += 1
            continue

        # Direct mappings for the rest.
        action_label = _PRIMARY_EVENT_TO_ACTION.get(et)
        if action_label:
            counts[action_label] += 1

        if et == EventType.TURN_END:
            counts["SCP_END_TURN"] += 1

    return dict(counts)


def _collect_mechanic_triggers(
    state: Any,
    detectors: dict[str, MechanicDetector],
) -> dict[str, int]:
    """Apply each mechanic detector to every event in the log."""
    counts: dict[str, int] = {name: 0 for name in detectors}
    for ev in list(getattr(state, "event_log", []) or []):
        for name, det in detectors.items():
            try:
                if det(state, ev):
                    counts[name] += 1
            except Exception:
                # Detector blew up — don't lose the whole game; flag-zero out.
                pass
    # Strip mechanics that never fired so the JSON stays focused on what the
    # set actually exercised.
    return {k: v for k, v in counts.items() if v > 0}


# =============================================================================
# Single SCP game runner (parallels scripts/play/scp_tournament.run_one_game,
# but stays in-process so we can capture state.event_log + card_def lists for
# per-card attribution).
# =============================================================================

async def _run_one_scp_game(
    label_a: str,
    label_b: str,
    deck_a: list[CardDefinition],
    deck_b: list[CardDefinition],
    *,
    seed: int,
    max_turns: int,
    difficulty: str,
    pilot: str,
    detectors: dict[str, MechanicDetector],
) -> dict[str, Any]:
    """Run one AI-vs-AI SCP game and return the rich per-game result dict."""
    started = time.perf_counter()
    pilot = validate_scp_pilot(pilot)

    error: str | None = None
    winner_label: str | None = None
    winner_id: str | None = None
    completed = False
    turns_run = 0

    # We instantiate the Game in-process so we can inspect state.event_log
    # post-game. Mirrors scripts.play.scp_tournament.run_one_game but
    # without dataclass plumbing.
    import random
    random.seed(seed)
    game = Game(mode="scp")
    p1 = game.add_player(f"{label_a}-pilot")
    p2 = game.add_player(f"{label_b}-pilot")

    try:
        # IMPORTANT: setup_scp_player consumes the deck list (the engine
        # stores card_defs by reference); we pass a fresh list each game so
        # the builder-returned list isn't mutated for the next pairing.
        game.setup_scp_player(p1, list(deck_a))
        game.setup_scp_player(p2, list(deck_b))
        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)
        game.turn_manager.set_ai_player(p1.id)
        game.turn_manager.set_ai_player(p2.id)
        game.turn_manager.set_ai_handler(_DispatchSCPAIAdapter({
            p1.id: SCPAIAdapter(difficulty=difficulty, pilot=pilot),
            p2.id: SCPAIAdapter(difficulty=difficulty, pilot=pilot),
        }))
        await game.start_game()

        for _ in range(max_turns * 2):
            if game.is_game_over():
                break
            await game.run_turn()
            turns_run += 1
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1200:]}"

    try:
        completed = game.is_game_over()
        if completed:
            winner_id = game.get_winner()
            if winner_id == p1.id:
                winner_label = label_a
            elif winner_id == p2.id:
                winner_label = label_b
    except Exception:
        pass

    winner_reason = ""
    try:
        winner_reason = _winner_reason(game, winner_id)
    except Exception:
        winner_reason = "unknown"

    card_stats: dict[str, dict[str, float]] = {}
    action_counts: dict[str, int] = {}
    mechanic_triggers: dict[str, int] = {}
    if error is None:
        try:
            card_stats = _collect_card_stats(
                game, p1.id, p2.id, label_a, label_b,
                deck_a, deck_b, winner_id,
            )
        except Exception as exc:
            error = (error or "") + (
                f"; card_stats failed: {type(exc).__name__}: {exc}"
            )
        try:
            action_counts = _collect_action_counts(game.state)
        except Exception as exc:
            error = (error or "") + (
                f"; action_counts failed: {type(exc).__name__}: {exc}"
            )
        try:
            mechanic_triggers = _collect_mechanic_triggers(game.state, detectors)
        except Exception as exc:
            error = (error or "") + (
                f"; mechanic_triggers failed: {type(exc).__name__}: {exc}"
            )

    return {
        "p1_label": label_a,
        "p2_label": label_b,
        "winner_label": winner_label,
        "winner_id": winner_id,
        "winner_reason": winner_reason,
        "completed": completed,
        "turns": turns_run,
        "duration_s": round(time.perf_counter() - started, 3),
        "error": error,
        "card_stats": card_stats,
        "action_counts": action_counts,
        "mechanic_triggers": mechanic_triggers,
    }


# =============================================================================
# Tournament aggregation → canonical {set_summary, matchup, card_scores, ...}
# =============================================================================

# Conditional action availability — these only get added to
# available_actions when the deck pool contains cards that could enable them.
# Keeps the audit from flagging deck-composition gaps as AI omissions.

def _has_anomalies(deck_specs: dict[str, list[CardDefinition]] | None) -> bool:
    if not deck_specs:
        return False
    for deck in deck_specs.values():
        for cd in deck:
            if cd and CardType.SCP_ANOMALY in (cd.characteristics.types or set()):
                return True
    return False


def _has_red_tape(deck_specs: dict[str, list[CardDefinition]] | None) -> bool:
    if not deck_specs:
        return False
    for deck in deck_specs.values():
        for cd in deck:
            if cd and int(getattr(cd, "scp_red_tape", 0) or 0) > 0:
                return True
    return False


def _has_protocol_text(deck_specs: dict[str, list[CardDefinition]] | None) -> bool:
    if not deck_specs:
        return False
    pat = re.compile(r"\b(protocol|mood|amnestic)\b", re.IGNORECASE)
    for deck in deck_specs.values():
        for cd in deck:
            if cd and pat.search((cd.text or "")):
                return True
    return False


def _has_ethics_generator(deck_specs: dict[str, list[CardDefinition]] | None) -> bool:
    if not deck_specs:
        return False
    pat = re.compile(r"\bethics\b", re.IGNORECASE)
    for deck in deck_specs.values():
        for cd in deck:
            if cd and pat.search((cd.text or "")):
                return True
    return False


def _aggregate(
    deck_labels: list[str],
    raw_results: list[dict[str, Any]],
    *,
    deck_specs: dict[str, list[CardDefinition]] | None = None,
) -> dict[str, Any]:
    """Build the canonical extended JSON contract."""
    set_record: dict[str, dict[str, int]] = {
        d: {"wins": 0, "losses": 0, "draws": 0, "errors": 0} for d in deck_labels
    }
    matchup: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"wins_a": 0, "wins_b": 0, "draws": 0}
    )
    ai_action_counts_agg: dict[str, int] = defaultdict(int)
    mechanic_triggers_agg: dict[str, int] = defaultdict(int)
    card_errors: dict[str, str] = {}
    card_agg: dict[str, dict[str, float]] = defaultdict(lambda: {
        "games": 0,
        "deck_copies": 0,
        "drawn": 0,
        "cast": 0,
        "in_play_at_end": 0,
        "on_winning_side": 0,
        "triggers_fired": 0,
        "contained": 0,
        "archive_contrib": 0.0,
        "deaths": 0,
        "wins": 0,
        "losses": 0,
    })

    for r in raw_results:
        a, b = r["p1_label"], r["p2_label"]
        if a not in set_record:
            set_record[a] = {"wins": 0, "losses": 0, "draws": 0, "errors": 0}
        if b not in set_record:
            set_record[b] = {"wins": 0, "losses": 0, "draws": 0, "errors": 0}

        if r.get("error"):
            set_record[a]["errors"] += 1
            set_record[b]["errors"] += 1
            # Capture the per-deck-pair error so the audit can surface a
            # card_repair finding when one specific card consistently
            # crashes. The error string includes the traceback tail.
            card_errors[f"{a} vs {b}"] = str(r.get("error"))[:1200]
            continue

        ka, kb = sorted([a, b])
        m = matchup[(ka, kb)]
        winner = r.get("winner_label")
        if winner is None:
            m["draws"] += 1
            set_record[a]["draws"] += 1
            set_record[b]["draws"] += 1
        elif winner == a:
            set_record[a]["wins"] += 1
            set_record[b]["losses"] += 1
            if a == ka:
                m["wins_a"] += 1
            else:
                m["wins_b"] += 1
        elif winner == b:
            set_record[b]["wins"] += 1
            set_record[a]["losses"] += 1
            if b == ka:
                m["wins_a"] += 1
            else:
                m["wins_b"] += 1
        else:
            m["draws"] += 1
            set_record[a]["draws"] += 1
            set_record[b]["draws"] += 1

        winner_side_label = winner

        for ref, cs in (r.get("card_stats") or {}).items():
            agg = card_agg[ref]
            agg["games"] += 1
            for k, v in cs.items():
                if k in agg:
                    agg[k] += v
            # Track wins / losses per card-ref: a copy "on winning side"
            # this game contributes to wins; otherwise losses (subject to
            # actually being in play / in deck this game).
            ref_label = ref.split("::", 1)[0]
            if winner_side_label:
                if ref_label == winner_side_label:
                    agg["wins"] += 1
                else:
                    agg["losses"] += 1

        for k, v in (r.get("action_counts") or {}).items():
            ai_action_counts_agg[k] += int(v)
        for k, v in (r.get("mechanic_triggers") or {}).items():
            mechanic_triggers_agg[k] += int(v)

    # Per-deck winrate.
    set_summary: dict[str, dict[str, Any]] = {}
    for d in deck_labels:
        rec = set_record[d]
        gp = rec["wins"] + rec["losses"] + rec["draws"]
        wr = (rec["wins"] / gp) if gp else 0.0
        set_summary[d] = {**rec, "games_played": gp, "winrate": round(wr, 3)}

    # Per-card derived metrics.
    card_scores: dict[str, dict[str, float]] = {}
    for ref, agg in card_agg.items():
        games = max(int(agg["games"]), 1)
        cast_per_game = agg["cast"] / games
        copies_per_game = agg["deck_copies"] / games
        cast_per_copy = (
            (agg["cast"] / agg["deck_copies"]) if agg["deck_copies"] else 0.0
        )
        win_rate_in_play = (
            (agg["on_winning_side"] / agg["in_play_at_end"])
            if agg["in_play_at_end"] > 0 else 0.0
        )
        # `ev` here mirrors the depths/capability_audit "winrate while
        # present" expected value — same shape so capability_audit can
        # treat SCP card_scores identically.
        ev = (
            (agg["wins"] / (agg["wins"] + agg["losses"]))
            if (agg["wins"] + agg["losses"]) > 0 else 0.0
        )
        card_scores[ref] = {
            **agg,
            "cast_per_game": round(cast_per_game, 3),
            "copies_per_game": round(copies_per_game, 3),
            "cast_per_copy": round(cast_per_copy, 3),
            "win_rate_in_play": round(win_rate_in_play, 3),
            "ev": round(ev, 3),
        }

    # Universe of available action types. SCP_OPEN_DOSSIER / SCP_END_TURN are
    # always available; the conditional actions require enabling cards in
    # the deck pool.
    available_actions = set(_BASE_AVAILABLE_ACTIONS)
    if _has_anomalies(deck_specs):
        available_actions.update({"SCP_RESEARCH", "SCP_CONTAIN", "SCP_SUPPRESS"})
        available_actions.add("SCP_CROSS_CONTAIN")
    if _has_red_tape(deck_specs):
        available_actions.add("SCP_FAST_TRACK")
    if _has_protocol_text(deck_specs):
        available_actions.add("SCP_APPLY_PROTOCOL")
        available_actions.add("SCP_SHIFT_MOOD")
    if _has_ethics_generator(deck_specs):
        available_actions.add("SCP_SPEND_ETHICS")
    # Memory hole is gated on the actor having archives — assume any deck
    # with an archive-payoff card might reach it.
    available_actions.add("SCP_MEMORY_HOLE")
    available_actions.add("SCP_RESOLVE_INCIDENT")
    # Always: the AI uses these at some point in nearly every game.
    available_actions.add("SCP_REVEAL_DOSSIER")
    available_actions.add("SCP_SEAL_DOSSIER")
    # Union in anything observed (defensive — covers FBN actions not in the
    # static base set).
    available_actions.update(ai_action_counts_agg.keys())

    return {
        "set_summary": set_summary,
        "matchup": {f"{a} vs {b}": v for (a, b), v in matchup.items()},
        "card_scores": card_scores,
        "ai_action_counts": dict(ai_action_counts_agg),
        "mechanic_triggers": dict(mechanic_triggers_agg),
        "available_actions": sorted(available_actions),
        "card_errors": card_errors,
    }


# =============================================================================
# Public API: run the round-robin
# =============================================================================

async def run_scp_tournament(
    builders: dict[str, DeckBuilder],
    *,
    games_per_pairing: int = 5,
    max_turns: int = 40,
    difficulty: str = "medium",
    pilot: str = "balanced",
    seed: int = 42,
    set_code: str | None = None,
    detectors: dict[str, MechanicDetector] | None = None,
) -> dict[str, Any]:
    """Run a round-robin SCP tournament and return the extended JSON dict.

    Validates deck labels against ``--set`` (each label must start with
    ``<set_code>_``) when ``set_code`` is provided — this matches
    ``balance_loop.py``'s ``domain_matches_set`` filter.
    """
    deck_labels = list(builders.keys())
    if not deck_labels:
        raise ValueError("at least one deck builder required")
    if len(deck_labels) < 2:
        raise ValueError(
            f"need ≥ 2 deck labels for a round-robin, got: {deck_labels}"
        )

    if set_code:
        prefix = f"{set_code}_"
        bad = [d for d in deck_labels if not d.startswith(prefix)]
        if bad:
            raise ValueError(
                f"deck labels must start with {prefix!r} for set "
                f"{set_code!r}; offenders: {bad}. The /new-set deck-label "
                f"naming convention is load-bearing — balance_loop.py "
                f"filters card_scores keys by this prefix."
            )

    detectors = detectors or dict(_DEFAULT_MECHANIC_DETECTORS)
    started = time.perf_counter()
    raw_results: list[dict[str, Any]] = []
    pairings = list(combinations(deck_labels, 2))

    print(
        f"[scp-tournament] {len(deck_labels)} decks, {len(pairings)} pairings "
        f"× {games_per_pairing} games "
        f"= {len(pairings) * games_per_pairing} games total"
    )

    for label_a, label_b in pairings:
        wins_a = wins_b = draws = errors = 0
        pair_started = time.perf_counter()
        for game_idx in range(games_per_pairing):
            deck_a = builders[label_a]()
            deck_b = builders[label_b]()
            result = await _run_one_scp_game(
                label_a, label_b, deck_a, deck_b,
                seed=seed + len(raw_results),
                max_turns=max_turns,
                difficulty=difficulty,
                pilot=pilot,
                detectors=detectors,
            )
            raw_results.append(result)
            if result.get("error"):
                errors += 1
            elif result.get("winner_label") == label_a:
                wins_a += 1
            elif result.get("winner_label") == label_b:
                wins_b += 1
            else:
                draws += 1
        pair_elapsed = time.perf_counter() - pair_started
        print(
            f"  {label_a:>28s} vs {label_b:<28s}  "
            f"a={wins_a} b={wins_b} draw={draws} err={errors}  "
            f"({pair_elapsed:.1f}s)"
        )

    deck_specs_sample = {label: builders[label]() for label in deck_labels}
    aggregated = _aggregate(
        deck_labels, raw_results, deck_specs=deck_specs_sample,
    )

    aggregated["meta"] = {
        "engine": "scp",
        "set_code": set_code,
        "deck_labels": list(deck_labels),
        "games_per_pairing": games_per_pairing,
        "max_turns": max_turns,
        "difficulty": difficulty,
        "pilot": pilot,
        "seed": seed,
        "pairings": len(pairings),
        "total_games": len(raw_results),
        "errored_games": sum(1 for r in raw_results if r.get("error")),
        "completed_games": sum(1 for r in raw_results if r.get("completed")),
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    aggregated["raw_results"] = [
        {k: v for k, v in r.items() if k != "card_stats"}
        for r in raw_results
    ]
    return aggregated


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--decks", required=True,
        help=(
            "Comma-separated list of '<deck_label>:<builder_spec>'. "
            "builder_spec is 'module.path:func_name' OR a key in "
            "SCP_STARTER_DECKS. Each deck_label must start with the "
            "value passed to --set."
        ),
    )
    ap.add_argument(
        "--games-per-pairing", type=int, default=5,
        help="AI-vs-AI games per unordered deck pair (default 5).",
    )
    # Convenience alias for callers that pass --games (matches depths).
    ap.add_argument("--games", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument(
        "--max-turns", type=int, default=40,
        help="Hard cap on turns per game.",
    )
    ap.add_argument(
        "--difficulty", default="medium",
        help="SCP AI difficulty (easy/medium/hard/expert/ultra).",
    )
    ap.add_argument(
        "--pilot", default="balanced",
        help=f"SCP heuristic pilot (one of {sorted(SUPPORTED_SCP_PILOTS)}).",
    )
    ap.add_argument(
        "--set", dest="set_code", default=None,
        help=(
            "Set code, used to validate the <SET>_ prefix on every deck label "
            "(balance_loop.py filters card_scores by this)."
        ),
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--mechanic-map", default=None,
        help=(
            "Optional 'module.path:DICT_NAME' reference whose module exports a "
            "dict[str, callable]. Detectors merged on top of the defaults "
            "(matching keys override). Used to wire FBN-specific mechanics "
            "once their engine plumbing lands; default coverage is MNR + core "
            "SCP."
        ),
    )
    ap.add_argument(
        "--out", type=Path, required=True,
        help="Write tournament JSON here.",
    )
    args = ap.parse_args()

    games_per_pairing = args.games if args.games is not None else args.games_per_pairing
    pilot = validate_scp_pilot(args.pilot)
    builders = _parse_decks_arg(args.decks)
    detectors = _load_mechanic_map(args.mechanic_map)

    payload = asyncio.run(run_scp_tournament(
        builders,
        games_per_pairing=games_per_pairing,
        max_turns=args.max_turns,
        difficulty=args.difficulty,
        pilot=pilot,
        seed=args.seed,
        set_code=args.set_code,
        detectors=detectors,
    ))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8",
    )
    print(f"wrote {args.out}")
    print(f"set_summary: {json.dumps(payload['set_summary'], indent=2)}")
    print(f"ai_action_counts: {json.dumps(payload['ai_action_counts'], indent=2)}")
    print(f"mechanic_triggers: {json.dumps(payload['mechanic_triggers'], indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
