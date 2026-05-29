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


# ---------------------------------------------------------------------------
# Anti-gaming text-match guard (added after the "slice-N median-lift" incident).
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS — read before touching the Asymmetry axis.
#
# The Asymmetry axis (and especially the "information event" sub-rule) is the
# single most score-dense signal in the rubric: emitting ONE event in the
# profile's `information_event_types` jumps the axis straight to 3, and the
# same events usually also light the State and Zone axes via the `life`
# resource-attr / library-graveyard zone touches. A card that emits SCRY /
# SURVEIL / MILL / LIFE_CHANGE therefore vaults from total 0 to ~5-8 (spicy
# tier) on event-emission ALONE.
#
# The "slice-N median-lift / spice-pass" retrofit weaponized exactly this: it
# auto-generated `_<set>_s<N>_*` stub helpers that wired hundreds of cards to
# emit generic SCRY/SURVEIL/MILL/LIFE_CHANGE "info-pulse" events REGARDLESS of
# each card's printed rules text, purely to raise `depth_v2_median`. The scorer
# credited those events because it only ever inspected what a card's effect_fn
# *emits* (via AST) and never compared it against what the card's text *says*.
# Net: ~16 custom sets shipped where cards did not do what their text claimed.
#
# THE GUARD: an info/asymmetric event only credits the Asymmetry axis when the
# card's printed `text` actually corroborates that mechanic. A "deal 3 damage"
# card whose stub emits SCRY no longer scores asymmetry=3 off the SCRY — its
# text says nothing about scry/surveil/look/mill, so the uncorroborated event
# is dropped for scoring purposes (the FeatureBag itself is untouched, so the
# code-fingerprint / reskin detection still sees the real emitted events).
#
# Conservative-by-design: the guard ONLY fires when the card has substantive
# printed text. Cards with empty/absent text (e.g. synthetic scorer-calibration
# fixtures, or genuinely text-less tokens) fall through to the legacy behavior,
# so this can never turn a real effect into a false negative — it can only
# refuse to *credit* an event the text doesn't justify. See
# `tests/test_depth_anti_gaming.py` for the regression that pins both halves.
#
# Each EventType name maps to the lowercase substrings whose presence in the
# card's text justifies crediting that event on the Asymmetry axis. Keep this
# table aligned with `engine_profiles.*_INFORMATION_EVENTS` /
# `*_ASYMMETRIC_EVENTS`; an event absent from this map is treated as "always
# corroborated" (we only gate events we have a vocabulary for, to avoid
# over-stripping engines whose text conventions we haven't catalogued).
_EVENT_TEXT_KEYWORDS: dict[str, frozenset[str]] = {
    # --- information events (the highest-value, most-gamed sub-rule) ---
    "SCRY": frozenset({"scry"}),
    "SURVEIL": frozenset({"surveil"}),
    "REVEAL": frozenset({"reveal", "look at", "reveals"}),
    "LOOK_AT_HAND": frozenset({"look at", "reveal", "hand", "discard a card"}),
    "MANIFEST_DREAD": frozenset({"manifest dread", "manifest"}),
    "DISCARD_CHOICE": frozenset({"discard"}),
    "TARGET_CHOSEN": frozenset({"target", "ward"}),
    # --- asymmetric resource events ---
    "DISCARD": frozenset({"discard"}),
    "MILL": frozenset({"mill", "into their graveyard", "from the top of",
                       "cards from the top", "puts the top"}),
    "LIFE_CHANGE": frozenset({"life", "drain", "lose", "gain", "damage"}),
    "DESTROY": frozenset({"destroy"}),
    "SACRIFICE": frozenset({"sacrifice"}),
    "EXILE": frozenset({"exile"}),
    "COUNTER_SPELL": frozenset({"counter"}),
    "REDIRECT_DAMAGE": frozenset({"redirect", "damage"}),
    "ATTACH": frozenset({"attach", "equip", "enchant"}),
    "UNATTACH": frozenset({"unattach", "unequip"}),
    # --- Pokemon information / asymmetric ---
    "PKM_REVEAL_HAND": frozenset({"reveal", "hand"}),
    "PKM_REVEAL": frozenset({"reveal", "look at"}),
    # --- HS / YGO information ---
    "DISCOVER": frozenset({"discover"}),
    "REVEAL_HAND": frozenset({"reveal", "hand"}),
    "YGO_REVEAL_HAND": frozenset({"reveal", "hand"}),
    "YGO_LOOK_AT_DECK": frozenset({"look at", "reveal", "deck"}),
}


def _text_corroborates_event(card_text: str, event_name: str) -> bool:
    """True if the card's printed text justifies crediting `event_name`.

    Returns True (don't strip) when:
      - the card has no substantive printed text (can't judge — stay safe), or
      - we have no keyword vocabulary for this event (not in the gate map), or
      - any of the event's corroborating substrings appears in the text.

    Returns False (strip the credit) only when the card HAS real text AND that
    text contains none of the event's corroborating keywords — i.e. the precise
    signature of a stub emitting an event its rules text never describes.
    """
    text = (card_text or "").strip().lower()
    if not text:
        return True  # no text to contradict — legacy behavior, no false negatives
    keywords = _EVENT_TEXT_KEYWORDS.get(event_name)
    if keywords is None:
        return True  # event we don't gate — credit as before
    # Strip reminder-text parentheticals so flavor like "(Scry 1.)" still counts
    # as corroboration when the card legitimately scries.
    return any(kw in text for kw in keywords)


def _text_filtered_event_types(
    event_types: frozenset[str] | set[str], card_text: str
) -> set[str]:
    """Return the subset of `event_types` the card's text corroborates.

    Used only to gate the Asymmetry axis (the exploit target). The full,
    unfiltered `event_types` set still flows into the code-fingerprint and
    every other axis, so reskin detection and non-asymmetry scoring are
    unaffected.
    """
    return {e for e in event_types if _text_corroborates_event(card_text, e)}


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


def _score_asymmetry(
    features: FeatureBag, profile: EngineProfile, card_text: str = "",
) -> tuple[int, bool]:
    # ANTI-GAMING GUARD: only count info/asymmetric events the card's printed
    # text actually corroborates. This is the structural defense against the
    # slice-N median-lift exploit — a stub that emits SCRY/SURVEIL/MILL/
    # LIFE_CHANGE with no matching rules text gets ZERO asymmetry credit, so it
    # can no longer vault a vanilla card into the spicy tier. Cards with empty
    # text fall through unchanged (see `_text_corroborates_event`).
    credited_events = _text_filtered_event_types(features.event_types, card_text)
    info_events = credited_events & profile.information_event_types
    asym_events = credited_events & profile.asymmetric_event_types
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


def score_features(
    features: FeatureBag, profile: EngineProfile, card_text: str = "",
) -> AxisScores:
    """Apply the 5-axis rubric to a pre-collected FeatureBag.

    `card_text` is the card's printed rules text; it drives the anti-gaming
    text-match guard on the Asymmetry axis (see `_score_asymmetry`). Pass it
    whenever available (`score_card` does so automatically). Omitting it
    preserves the legacy event-only behavior — callers scoring a bare
    FeatureBag with no card in hand get the same scores as before.
    """
    if features.is_trivially_empty and not features.helpers_called:
        return AxisScores()

    s, lc_s = _score_state_coupling(features, profile)
    d, lc_d = _score_decision_pressure(features, profile)
    z, lc_z = _score_zone_movement(features, profile)
    a, lc_a = _score_asymmetry(features, profile, card_text)
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


def _card_rules_text(card_def) -> str:
    """Concatenate every printed rules-text source on a CardDefinition.

    The top-level `text` field is FLAVOR text on some engines (Pokemon/YGO),
    while the actual rules live in structured fields — `attacks[].name/text`,
    `ability.name/text`, and the YGO type descriptors. The anti-gaming guard
    must read the same surfaces `_iter_callables` pulls effects from, or it
    mis-judges those engines (e.g. a Pokemon attack "Look at your opponent's
    hand" reveals, but the flavor `text` says nothing about it). Mirrors
    `custom_set_depth_report._legacy_text_blob`.
    """
    parts: list[str] = []
    text = getattr(card_def, "text", "") or ""
    if text:
        parts.append(text)
    for atk in (getattr(card_def, "attacks", None) or []):
        if isinstance(atk, dict):
            for key in ("name", "text"):
                val = atk.get(key)
                if val:
                    parts.append(str(val))
    ability = getattr(card_def, "ability", None)
    if isinstance(ability, dict):
        for key in ("name", "text"):
            val = ability.get(key)
            if val:
                parts.append(str(val))
    for field_name in ("ygo_spell_type", "ygo_trap_type", "ygo_monster_type"):
        val = getattr(card_def, field_name, None)
        if val:
            parts.append(str(val))
    return " ".join(parts)


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
            bundle_features=profile.bundle_features,
        )
        if bag.is_trivially_empty and not bag.helpers_called:
            continue  # contributes nothing meaningful
        if merged.is_trivially_empty and not merged.helpers_called:
            merged = bag
        else:
            merged.merge(bag)
    # Pass the card's full printed rules text (flavor + attacks + ability +
    # YGO type fields) so the Asymmetry axis can refuse to credit info/
    # asymmetric events the rules text doesn't describe (anti-gaming).
    card_text = _card_rules_text(card_def)
    scores = score_features(merged, profile, card_text)
    return CardScore(
        name=getattr(card_def, "name", "<unknown>"),
        scores=scores,
        code_fingerprint=merged.code_fingerprint(),
        features=merged,
        callable_slots=tuple(slot_names),
        is_unwired=False,
    )
