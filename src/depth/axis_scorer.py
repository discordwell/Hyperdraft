"""
Map AST features (FeatureBag) to a 5-axis depth score (0-3 per axis, 0-15 total).

Axes:
    S — State Coupling: what game state does the effect READ?
    D — Decision Pressure: what does the player CHOOSE at resolution?
    Z — Zone/Resource Movement: where do things move?
    A — Asymmetry: does it create info/resource imbalance the opponent must respond to?
    Y — Synergy Hook: what does it pull into the deck?

See `/Users/discordwell/.claude/plans/async-moseying-bear.md` for the rubric definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .ast_fingerprint import FeatureBag, extract_features_from_callable
from .engine_profiles import EngineProfile


@dataclass
class AxisScores:
    """Five-axis depth score, 0-3 each."""

    state: int = 0
    decision: int = 0
    zone: int = 0
    asymmetry: int = 0
    synergy: int = 0
    # Cards where the AST scorer wasn't confident on at least one axis are
    # flagged for human review.
    low_confidence_axes: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return self.state + self.decision + self.zone + self.asymmetry + self.synergy

    @property
    def fingerprint(self) -> tuple[int, int, int, int, int]:
        """Axis fingerprint — the 5-tuple of scores. Catches shallow design space."""
        return (self.state, self.decision, self.zone, self.asymmetry, self.synergy)

    @property
    def tier(self) -> str:
        t = self.total
        if t <= 3:
            return "vanilla"
        if t <= 7:
            return "functional"
        if t <= 11:
            return "spicy"
        return "build-around"

    def axes_zero_count(self) -> int:
        return sum(1 for v in (self.state, self.decision, self.zone, self.asymmetry, self.synergy) if v == 0)


@dataclass
class CardScore:
    """Per-card scoring output."""

    name: str
    scores: AxisScores
    code_fingerprint: str
    features: FeatureBag
    # The slot(s) on the CardDefinition that contributed (setup_interceptors,
    # resolve, battlecry, attack:<name>, etc.).
    callable_slots: tuple[str, ...] = ()
    # True if this card has no effect callable at all (truly vanilla stat-line).
    is_unwired: bool = False


# ---------------------------------------------------------------------------
# Per-axis scoring rules.
# ---------------------------------------------------------------------------


def _score_state_coupling(features: FeatureBag, profile: EngineProfile) -> tuple[int, bool]:
    """Returns (score, low_confidence)."""
    state_attrs = features.state_attrs
    # Resource attrs touched (counted via helpers_called + state_attrs).
    res_hits = state_attrs & profile.resource_attrs
    zones = features.zones_accessed
    cross = features.cross_controller or features.opponent_iteration

    if not state_attrs and not zones and not res_hits:
        return 0, False

    # Count "kinds" of state observed.
    kinds = 0
    if state_attrs:
        kinds += 1
    if zones:
        kinds += 1
    if res_hits:
        kinds += 1

    if cross:
        # Reads opponent state asymmetrically.
        if kinds >= 2 or len(state_attrs) >= 3 or len(zones) >= 2:
            return 3, False  # cross-zone + cross-player
        return 2, False

    # Self-only.
    if kinds >= 3 or len(state_attrs) >= 3:
        return 2, False  # multi-state, but symmetric
    return 1, False


def _score_decision_pressure(features: FeatureBag, profile: EngineProfile) -> tuple[int, bool]:
    modals = features.modal_calls & profile.modal_helpers

    # Count modal-helper "shapes" that imply nested choice:
    # spree / modal_etb / modal_spell are 1-of-N choice helpers
    # targeted_* helpers are single-target choices
    deep_modal_names = {
        "create_modal_choice",
        "make_modal_etb_trigger",
        "make_modal_spell_trigger",
        "make_spree_setup",
        "make_hand_to_battlefield_choice",
        "create_hand_reveal_choice",
    }
    targeted_names = {
        "create_target_choice",
        "create_target_creature_choice",
        "create_discard_choice",
        "create_sacrifice_choice",
        "create_order_choice",
        "create_may_choice",
        "create_scry_choice",
        "create_surveil_choice",
        "make_targeted_etb_trigger",
        "make_targeted_attack_trigger",
        "make_targeted_death_trigger",
        "make_targeted_damage_trigger",
        "make_targeted_spell_cast_trigger",
        "make_divided_damage_etb_trigger",
        "make_divided_counters_etb_trigger",
        "make_targeted_multi_effect_etb_trigger",
        "make_targeted_multi_effect_attack_trigger",
        "make_top_n_land_pick",
        "make_library_search_etb_trigger",
    }
    deep_hits = modals & deep_modal_names
    targeted_hits = modals & targeted_names

    if deep_hits and targeted_hits:
        return 3, False  # modal + targeted = sequential / nested
    if deep_hits:
        if "make_spree_setup" in deep_hits:
            return 3, False  # spree is explicitly multi-modal
        return 2, False
    if len(targeted_hits) >= 2:
        return 2, False  # multiple independent targets
    if targeted_hits:
        return 1, False
    if modals:
        # Some modal-ish helper we recognized but didn't categorize.
        return 1, True
    # No modal helpers at all. Pokemon attacks essentially always land here.
    return 0, False


def _score_zone_movement(features: FeatureBag, profile: EngineProfile) -> tuple[int, bool]:
    zones = features.zones_accessed & profile.zone_names
    novel = features.zones_accessed & profile.novel_zones
    novel_helpers = features.novel_helper_calls & profile.novel_helpers

    if novel_helpers:
        return 3, False
    if novel:
        return 3, False
    # Zone-resource-movement scoring is strictly about how many distinct zones
    # the card's effect_fn touches. Asymmetric events (energy discard,
    # opponent discard, forced switch) score on the A axis, not Z.
    if len(zones) >= 2:
        return 2, False
    if zones:
        return 1, False
    return 0, False


def _score_asymmetry(features: FeatureBag, profile: EngineProfile) -> tuple[int, bool]:
    info_events = features.event_types & profile.information_event_types
    asym_events = features.event_types & profile.asymmetric_event_types
    cross = features.cross_controller or features.opponent_iteration

    if info_events:
        return 3, False  # information asymmetry is the strongest signal
    if cross and asym_events:
        # Resource asymmetry — energy denial, opponent discard, forced switch.
        return 2, False
    if cross:
        # Cross-controller event but only "damage to opp Active" — mild
        # asymmetry, same as a face-damage spell.
        return 1, False
    return 0, False


def _score_synergy_hook(features: FeatureBag, profile: EngineProfile) -> tuple[int, bool]:
    novel = features.novel_helper_calls & profile.novel_helpers
    filters = features.filter_factory_calls & profile.filter_factories

    if novel:
        return 3, False
    if filters:
        return 2, False
    # No filter / no novel mechanic. The card is either self-contained or
    # only generically synergistic (any creature, any spell). Without deeper
    # text parsing we can't tell; default to 0 with low confidence.
    if features.helpers_called and not features.is_trivially_empty:
        return 0, True  # might be generic-synergy, can't tell from AST
    return 0, False


# ---------------------------------------------------------------------------
# Driver.
# ---------------------------------------------------------------------------


def score_features(features: FeatureBag, profile: EngineProfile) -> AxisScores:
    """Apply the 5-axis rubric to a pre-collected FeatureBag."""
    if features.is_trivially_empty and not features.helpers_called:
        return AxisScores()

    s, lc_s = _score_state_coupling(features, profile)
    d, lc_d = _score_decision_pressure(features, profile)
    z, lc_z = _score_zone_movement(features, profile)
    a, lc_a = _score_asymmetry(features, profile)
    y, lc_y = _score_synergy_hook(features, profile)

    low = []
    if lc_s: low.append("state")
    if lc_d: low.append("decision")
    if lc_z: low.append("zone")
    if lc_a: low.append("asymmetry")
    if lc_y: low.append("synergy")
    return AxisScores(
        state=s, decision=d, zone=z, asymmetry=a, synergy=y,
        low_confidence_axes=tuple(low),
    )


def _iter_callables(card_def) -> list[tuple[str, Callable]]:
    """Yield (slot_name, callable) for every effect-bearing slot on a CardDefinition."""
    out: list[tuple[str, Callable]] = []
    for slot in (
        "setup_interceptors", "setup_in_graveyard", "setup_in_hand",
        "resolve", "battlecry", "deathrattle", "spell_effect",
        "pendulum_effect_fn", "flip_effect",
    ):
        fn = getattr(card_def, slot, None)
        if callable(fn):
            out.append((slot, fn))
    # Pokemon attacks
    for atk in (getattr(card_def, "attacks", None) or []):
        fn = atk.get("effect_fn") if isinstance(atk, dict) else None
        if callable(fn):
            out.append((f"attack:{atk.get('name', '?')}", fn))
    # Pokemon ability
    ability = getattr(card_def, "ability", None)
    if isinstance(ability, dict):
        fn = ability.get("effect_fn")
        if callable(fn):
            out.append((f"ability:{ability.get('name', '?')}", fn))
    return out


def score_card(card_def, profile: EngineProfile) -> CardScore:
    """Score one CardDefinition by collecting features from all its callable
    slots, merging them, and applying the rubric."""
    callables = _iter_callables(card_def)
    merged = FeatureBag()
    merged.is_trivially_empty = True  # neutral; .merge will flip if any non-empty
    if not callables:
        return CardScore(
            name=getattr(card_def, "name", "<unknown>"),
            scores=AxisScores(),
            code_fingerprint=merged.code_fingerprint(),
            features=merged,
            callable_slots=(),
            is_unwired=True,
        )
    slot_names: list[str] = []
    for slot, fn in callables:
        slot_names.append(slot)
        bag = extract_features_from_callable(
            fn,
            modal_helpers=profile.modal_helpers,
            filter_factories=profile.filter_factories,
            novel_helpers=profile.novel_helpers,
            cross_controller_helpers=profile.cross_controller_helpers,
            function_accepting_helpers=profile.function_accepting_helpers,
        )
        if bag.is_trivially_empty and not bag.helpers_called:
            continue  # contributes nothing meaningful
        if merged.is_trivially_empty and not merged.helpers_called:
            merged = bag
        else:
            merged.merge(bag)
    scores = score_features(merged, profile)
    return CardScore(
        name=getattr(card_def, "name", "<unknown>"),
        scores=scores,
        code_fingerprint=merged.code_fingerprint(),
        features=merged,
        callable_slots=tuple(slot_names),
        is_unwired=False,
    )
