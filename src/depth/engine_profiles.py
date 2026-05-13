"""
Per-engine vocabulary tables used by the axis scorer.

The five-axis depth rubric is engine-neutral. The *primitives* differ by
engine (zone names, resource attrs, modal helpers, novel mechanics). Each
profile maps the universal rubric to the local vocabulary.

Profile data is derived from:
- `src/cards/interceptor_helpers.py` (MTG factory names)
- `src/engine/types.py` (EventType enum, zone enums)
- `src/cards/pokemon/**`, `src/cards/hearthstone/**`, `src/cards/yugioh/**`
  for engine-specific patterns observed in the card pools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class EngineProfile:
    """Vocabulary translation for one engine."""

    name: str

    # Zone-name prefixes that appear in `state.zones.get(f"<prefix>_{player_id}")`
    # or as ZoneType.X enum members (stored lowercase here).
    zone_names: frozenset[str]
    # Subset of zone_names that represent novel/hidden zones — touching one
    # bumps the Zone/Resource axis toward 3.
    novel_zones: frozenset[str]

    # Per-object state attributes that constitute "resources" — touching one
    # contributes to State Coupling.
    resource_attrs: frozenset[str]

    # Helper-factory names whose presence indicates the card creates a
    # player-facing choice at resolution. Drives Decision Pressure.
    modal_helpers: frozenset[str]

    # Filter factory names whose presence indicates the card pulls a specific
    # subset of cards from the deck/board — typed-synergy signal.
    filter_factories: frozenset[str]

    # Mechanic-specific helpers (room unlock, manifest, suspect, etc.). Any
    # match scores 3 on Synergy Hook (mechanic-specific) and pushes the
    # Zone/Resource axis if it touches a novel zone.
    novel_helpers: frozenset[str]

    # EventType names that, when emitted with a cross-controller target,
    # represent asymmetric resource impact (energy discard, hand discard,
    # forced switch, etc). The scorer combines event_type ∈ this set with
    # cross_controller=True to award Asymmetry 2+.
    asymmetric_event_types: frozenset[str]

    # EventType names whose payload typically conveys hidden information or
    # forces opponent decisions (forced reveal, choose-from-hidden-set, etc).
    # Pushes Asymmetry to 3.
    information_event_types: frozenset[str] = field(default_factory=frozenset)

    # Cross-module helper names that *imply* cross-controller interaction even
    # though their `!=` comparator lives in a different module the AST walker
    # doesn't descend into. Calling any of these flags `bag.cross_controller=True`
    # on behalf of the calling card. Without this, every card that delegates
    # opp-lookup to a helper (instead of inlining the `!=`) under-scores on S/A.
    cross_controller_helpers: frozenset[str] = field(default_factory=frozenset)


# ---------------------------------------------------------------------------
# MTG
# ---------------------------------------------------------------------------

_MTG_ZONES = frozenset({
    "battlefield", "library", "hand", "graveyard", "exile", "stack",
    "command", "ante",
})

_MTG_NOVEL_ZONES = frozenset({
    "exile",  # exile-and-cast, foretell, manifest
    "command",  # command zone interactions
})

_MTG_MODAL_HELPERS = frozenset({
    "create_modal_choice",
    "make_modal_etb_trigger",
    "make_modal_spell_trigger",
    "make_spree_setup",
    "create_target_choice",
    "create_may_choice",
    "create_scry_choice",
    "create_surveil_choice",
    "create_discard_choice",
    "create_sacrifice_choice",
    "create_order_choice",
    "create_hand_reveal_choice",
    "make_hand_to_battlefield_choice",
    "make_top_n_land_pick",
    "make_targeted_etb_trigger",
    "make_targeted_attack_trigger",
    "make_targeted_death_trigger",
    "make_targeted_damage_trigger",
    "make_targeted_spell_cast_trigger",
    "make_divided_damage_etb_trigger",
    "make_divided_counters_etb_trigger",
    "make_targeted_multi_effect_etb_trigger",
    "make_targeted_multi_effect_attack_trigger",
})

_MTG_FILTER_FACTORIES = frozenset({
    "other_creatures_you_control",
    "creatures_you_control",
    "creatures_with_subtype",
    "other_creatures_with_subtype",
    "count_permanents_with_subtype",
    "count_permanents_of_type",
    "count_cards_in_graveyard",
    "count_cards_in_hand",
    "count_exiled_with",
    "count_attachments",
})

_MTG_NOVEL_HELPERS = frozenset({
    "make_room_setup",  # DSK Rooms
    "make_saga_setup",  # Sagas (multi-chapter)
    "make_face_down_setup",  # Manifest / morph
    "make_manifest_etb_event",
    "make_warp_setup",  # EOE warp (cast from exile + delayed return)
    "make_web_slinging_setup",  # SPM
    "make_mayhem_setup",  # OTJ mayhem
    "make_station_creature_setup",  # EOE station
    "make_castable_from_zone",
    "make_castable_from_graveyard",
    "make_castable_from_exile",
    "make_castable_from_library_top",
    "make_counter_transfer_on_death",
    "suspect_creature",  # MKM
    "collect_evidence",  # MKM
    "becomes_creature",  # land→creature
    "threaten_creature",  # gain control
    "grant_death_trigger",
    "grant_triggered_ability",
    "make_lander_etb_trigger",
    "make_lander_death_trigger",
})

_MTG_ASYMMETRIC_EVENTS = frozenset({
    "DISCARD", "DISCARD_CHOICE", "MILL",
    "LIFE_CHANGE",  # damage-to-opponent
    "DESTROY", "SACRIFICE", "EXILE",
    "COUNTER_SPELL", "REDIRECT_DAMAGE",
    "ATTACH", "UNATTACH",
})

_MTG_INFORMATION_EVENTS = frozenset({
    "REVEAL", "SCRY", "SURVEIL", "LOOK_AT_HAND", "MANIFEST_DREAD",
    "DISCARD_CHOICE",  # opponent chooses what they discard
    "TARGET_CHOSEN",  # ward interactions
})

MTG_PROFILE = EngineProfile(
    name="mtg",
    zone_names=_MTG_ZONES,
    novel_zones=_MTG_NOVEL_ZONES,
    resource_attrs=frozenset({
        "life", "mana_pool", "counters", "loyalty",
        "power", "toughness", "tapped", "summoning_sickness",
    }),
    modal_helpers=_MTG_MODAL_HELPERS,
    filter_factories=_MTG_FILTER_FACTORIES,
    novel_helpers=_MTG_NOVEL_HELPERS,
    asymmetric_event_types=_MTG_ASYMMETRIC_EVENTS,
    information_event_types=_MTG_INFORMATION_EVENTS,
)


# ---------------------------------------------------------------------------
# Pokemon
# ---------------------------------------------------------------------------

# Pokemon-style zones use these prefixes in f"<prefix>_{player_id}" patterns.
_PKM_ZONES = frozenset({
    "active_spot", "bench", "hand", "library", "graveyard", "prize",
    "lost_zone",
})

_PKM_NOVEL_ZONES = frozenset({
    "lost_zone",  # not yet wired in BRV cards but supported by engine
    "prize",  # prize manipulation
})

_PKM_ASYMMETRIC_EVENTS = frozenset({
    "PKM_PLACE_DAMAGE_COUNTERS",  # cross-controller damage
    "PKM_DISCARD_ENERGY",  # energy denial when targeting opp
    "PKM_APPLY_STATUS",  # status condition
    "PKM_SWITCH",  # switch effect (incl. forced)
    "PKM_FORCE_SWITCH",  # Boss's-Orders-style
    "PKM_MOVE_ENERGY",  # cross-controller energy redistribution
    "PKM_PRIZE_TAX",  # asymmetric prize-take reduction
    "PKM_LOST_ZONE",  # asymmetric exile (one-way removal)
    "PKM_COST_REDUCTION",  # attack-cost change (Tool / Stadium)
    "PKM_HEAL",
})

_PKM_INFORMATION_EVENTS = frozenset({
    "PKM_REVEAL_HAND",
    "PKM_REVEAL",  # top-of-deck reveal
})

PKM_PROFILE = EngineProfile(
    name="pokemon",
    zone_names=_PKM_ZONES,
    novel_zones=_PKM_NOVEL_ZONES,
    resource_attrs=frozenset({
        "damage_counters", "attached_energy", "status_conditions",
        "is_asleep", "is_paralyzed", "is_poisoned", "is_burned", "is_confused",
        "prizes_remaining", "remaining_hp",
    }),
    # Modal-choice helpers shipped in src/cards/pokemon/_helpers.py.
    # Card effect_fns calling any of these are detected as Decision Pressure
    # by the AST scorer.
    modal_helpers=frozenset({
        "pkm_modal_choice",
        "pkm_force_opp_choose_bench",
        "pkm_choose_pokemon_target",
        "pkm_target_card_in_hand_choice",
        "pkm_choose_from_hand_n",
    }),
    # Synergy filters — count_* helpers in _helpers.py. A card whose
    # effect_fn calls any of these reads typed/archetype-specific state.
    filter_factories=frozenset({
        "count_pokemon_by_stage",
        "count_pokemon_in_play",
        "count_typed_energy_attached",
        "count_typed_energy_in_hand",
        "count_poisoned_pokemon",
        "count_pokemon_in_lost_zone",
    }),
    # Mechanic-specific helpers — touching one signals build-around
    # synergy. apply_status / remove_status come from pokemon_status.py;
    # the rest are in _helpers.py.
    novel_helpers=frozenset({
        "apply_status", "remove_status", "remove_all_status",
        "attach_tool", "remove_tool",
        "place_damage_counters",
        "pkm_move_to_lost_zone",
        "pkm_apply_prize_tax",
        "pkm_skip_evolution_stage",
        "pkm_force_switch_opp",
        "pkm_reveal_opp_hand",
        "pkm_move_energy",
        "discard_attached_energy_cross_ctrl",
    }),
    asymmetric_event_types=_PKM_ASYMMETRIC_EVENTS,
    information_event_types=_PKM_INFORMATION_EVENTS,
    # These helpers live in src/cards/pokemon/_helpers.py and encapsulate the
    # cross-controller `!= attacker.controller` comparison the AST walker
    # can't see across module boundaries.
    cross_controller_helpers=frozenset({
        "_get_opp_id",
        "_get_opp_active",
        "pkm_force_opp_choose_bench",
        "pkm_force_switch_opp",
        "pkm_reveal_opp_hand",
        "pkm_target_card_in_hand_choice",
        "pkm_apply_prize_tax",
        "discard_attached_energy_cross_ctrl",
        "pkm_move_energy",
    }),
)


# ---------------------------------------------------------------------------
# Hearthstone
# ---------------------------------------------------------------------------

HS_PROFILE = EngineProfile(
    name="hearthstone",
    zone_names=frozenset({
        "battlefield", "hand", "library", "graveyard",
    }),
    novel_zones=frozenset({
        "secret",  # secrets are face-down at the controller's side
    }),
    resource_attrs=frozenset({
        "armor", "mana", "health", "attack",
        "frozen", "stealth", "taunt", "divine_shield",
    }),
    modal_helpers=frozenset({
        # HS card implementations frequently use these for discover / choose-one
        "discover_choice", "create_choose_one_choice",
        "create_battlecry_choice", "create_deathrattle_choice",
    }),
    filter_factories=frozenset({
        "other_friendly_minions",
        "other_friendly_minions_with_subtype",
    }),
    novel_helpers=frozenset({
        "make_secret_setup",
        "make_quest_setup",
        "make_combo_trigger",
        "make_overload_payment",
        "make_silence_handler",
    }),
    asymmetric_event_types=frozenset({
        "DAMAGE", "DESTROY", "DISCARD",
        "FREEZE", "SILENCE",
    }),
    information_event_types=frozenset({
        "DISCOVER", "REVEAL_HAND",
    }),
)


# ---------------------------------------------------------------------------
# Yu-Gi-Oh
# ---------------------------------------------------------------------------

YGO_PROFILE = EngineProfile(
    name="yugioh",
    zone_names=frozenset({
        "monster_zone", "spell_trap_zone", "hand", "deck", "graveyard",
        "banished", "extra_deck", "field_spell_zone", "pendulum_zone",
    }),
    novel_zones=frozenset({
        "banished",  # banished face-down etc.
        "pendulum_zone", "extra_deck", "field_spell_zone",
    }),
    resource_attrs=frozenset({
        "life_points", "atk", "def_val", "level", "rank", "link_rating",
        "normal_summoned_this_turn", "tributes_available",
    }),
    modal_helpers=frozenset({
        # YGO cards usually inline their choice logic; few canonical helpers
        "ygo_target_choice", "ygo_modal_choice",
    }),
    filter_factories=frozenset({
        # Per-archetype filters live in the card files themselves
    }),
    novel_helpers=frozenset({
        "ygo_chain_link",
        "ygo_negate_activation",
        "ygo_special_summon_from_graveyard",
        "ygo_special_summon_from_banished",
        "ygo_xyz_summon", "ygo_synchro_summon", "ygo_link_summon",
        "ygo_pendulum_setup",
    }),
    asymmetric_event_types=frozenset({
        "YGO_DESTROY", "YGO_BANISH", "YGO_DISCARD",
        "YGO_NEGATE",
        "YGO_LIFE_CHANGE",
    }),
    information_event_types=frozenset({
        "YGO_REVEAL_HAND", "YGO_LOOK_AT_DECK",
    }),
)


# ---------------------------------------------------------------------------
# Finance / Minecraft — stubs (extend when those engines see real audits).
# ---------------------------------------------------------------------------

FINANCE_PROFILE = EngineProfile(
    name="finance",
    zone_names=frozenset({
        "battlefield", "hand", "library", "graveyard", "exile",
        "derivative_zone",
    }),
    novel_zones=frozenset({"derivative_zone"}),
    resource_attrs=frozenset({
        "capital", "leverage", "volatility", "position",
    }),
    modal_helpers=frozenset(),
    filter_factories=frozenset(),
    novel_helpers=frozenset({
        "make_derivative_setup", "make_position_audit",
        "make_volatility_trigger",
    }),
    asymmetric_event_types=frozenset({
        "FIN_LIQUIDATE", "FIN_MARGIN_CALL",
    }),
)


MINECRAFT_PROFILE = EngineProfile(
    name="minecraft",
    zone_names=frozenset({
        "battlefield", "hand", "library", "graveyard", "exile",
        "mining_zone", "build_zone",
    }),
    novel_zones=frozenset({"mining_zone", "build_zone"}),
    resource_attrs=frozenset({
        "hunger", "armor", "experience", "ore",
    }),
    modal_helpers=frozenset(),
    filter_factories=frozenset(),
    novel_helpers=frozenset({
        "make_mining_trigger", "make_crafting_recipe",
        "make_mob_spawn",
    }),
    asymmetric_event_types=frozenset({
        "MC_RAID", "MC_DROP_LOOT",
    }),
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PROFILES: dict[str, EngineProfile] = {
    "mtg": MTG_PROFILE,
    "pokemon": PKM_PROFILE,
    "hearthstone": HS_PROFILE,
    "yugioh": YGO_PROFILE,
    "finance": FINANCE_PROFILE,
    "minecraft": MINECRAFT_PROFILE,
}


def get_profile(name: str) -> EngineProfile:
    """Look up an engine profile by name (lowercased). Raises if unknown."""
    key = name.lower()
    if key not in _PROFILES:
        raise KeyError(
            f"Unknown engine profile: {name!r}. Known: {sorted(_PROFILES)}"
        )
    return _PROFILES[key]


def list_profiles() -> list[str]:
    return sorted(_PROFILES)
