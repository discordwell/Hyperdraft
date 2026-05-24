"""Wave-2 adversarial deck candidates.

These are NOT starter decks — they're hypothesis tests to discover the true
meta in the CLAN card pool. Used by Wave 2 of docs/sets/clan_balance_plan.md.

Six hypotheses tested:

1. CLAN_hybrid_swarm_brick — MIRTHBOT-1 + FORGE big-chassis splash + Modular
   Railgun. Does adding a finishing punch on top of swarm dominance push it
   even further than the pure swarm starter?

2. CLAN_pure_deathclock — ETHOS-7 with max Transient density (~30) + mill
   weapons. Tests whether deck-burn can outpace MIRTH's tempo.

3. CLAN_hyper_armor — BULWARK-9 with all 9 unique armor add-ons (+ 4-of's
   where allowed) on heavy chassis carriers. Tests if max armor density
   rescues BULWARK.

4. CLAN_solo_mobile_rush — Affection.exe (swarm Core) with all 9 Self-Mobile
   parts, minimal chassis filler. Tests if the engine supports a "parts as
   attackers" deck and whether it's viable.

5. CLAN_forge_artillery_hybrid — substituted for the original Modular Reroute
   hypothesis (the pool has only 2 Modular cards; cannot fill 8 slots).
   FORGE-Δ Core + FORGE big chassis + BULWARK armor stacking + BULWARK
   workshop-damage weapons. Tests if combining the #1 and #4 winrate decks'
   tools makes a deck stronger than either alone.

6. CLAN_synchronize_max — MIRTHBOT-1 with EVERY Synchronize chassis 4x where
   possible, plus all Synchronize-payoff Add-Ons + Structures. Pushes the
   keyword density above the starter to confirm whether Synchronize is the
   structural root cause of MIRTH's dominance.
"""

from __future__ import annotations

from src.engine.types import CardDefinition

# -----------------------------------------------------------------------------
# Imports — pull everything we may need from the four archetype modules.
# -----------------------------------------------------------------------------
from src.cards.clankers.CLAN.clan_forge import (
    FORGE_DELTA,
    # Chassis
    HEAVY_ASSEMBLY,
    IRONCLAD_FOREMAN,
    SMELTER_FRAME,
    TUNGSTEN_WALKER,
    CARBON_STEEL_DRUDGE,
    IRON_SPIRE,
    FOUNDRYMAN,
    APEX_HULK,
    SALVAGER_SEVEN,
    PLANT_FOREMAN,
    # Weapons
    BUZZSAW_ARM,
    BUZZSAW_MK_III,
    MODULAR_RAILGUN,
    BOLT_DRIVER_MK_II,
    FORGE_CANNON,
    HEAVY_SPIKE,
    ANVIL_DRONE,
    RECOIL_MOUNT,
    SALVAGE_CLEAVER,
    APEX_COILGUN,
    # Add-Ons
    REINFORCED_PLATING,
    SACRIFICIAL_PLATING,
    THICK_HIDE,
    BULWARK_BRACE,
    TUNGSTEN_CARAPACE,
    LUGNUT_CRADLE,
    BRACE_PLATE,
    FOUNDRY_BRACER,
    REACTOR_SHELL,
    # Transients
    FORGE_STOKE,
    HAMMER_ON,
    IRON_AUDIT,
    BIG_SWING,
    # Structures
    COMPOUNDING_BUTTRESS,
    REINFORCED_BAY,
    HEAVY_FORGE,
)
from src.cards.clankers.CLAN.clan_ethos import (
    ETHOS_7,
    # Chassis
    BULWARK_FRAME,
    SUBROUTINE_CORE,
    LOOP_ENGINE,
    HEURISTIC_SENTRY,
    LONG_MEMORY_HUSK,
    RECURSIVE_SENTINEL,
    CONTAINMENT_SCRIBE,
    ENDURANCE_FRAME,
    # Weapons
    LOGIC_LANCE,
    MEMORY_BLADE,
    RECURSION_HOOK,
    SUBROUTINE_DRIVER,
    HEURISTIC_LANCE,
    DECODER_SPIKE,
    CIPHER_ROTOR,
    CONTAINMENT_LANCE,
    # Add-Ons
    CONTAINMENT_LATTICE,
    HEURISTIC_LAYER,
    LOGIC_BUFFER,
    SUBROUTINE_DAMPENER,
    RECURSIVE_TAPE,
    SOFT_CYCLE_RIDGE,
    COOLDOWN_HARNESS,
    PATIENT_FRAME,
    MEMORY_BUFFER,
    # Transients
    HEURISTIC_LOOP,
    REROUTE_POWER,
    GARBAGE_COLLECTOR,
    DIAGNOSTIC_SWEEP,
    SUBROUTINE_CASCADE,
    PATCH,
    # Structures
    RECURSIVE_OBSERVATORY,
    COMPUTE_TRICKLE,
)
from src.cards.clankers.CLAN.clan_mirth import (
    MIRTHBOT_1,
    AFFECTION_EXE,
    # Chassis
    LINKED_CRAWLER,
    SKITTERSWARM,
    SPARKBOT,
    JOYFUL_WALKER,
    WHIRRING_INITIATE,
    MAGENTA_BUZZER,
    AFFECTION_BOT,
    CROWD_MARCHER,
    TINKERLING,
    HUM_SWARM_ALPHA,
    QUICKFORGE_DRUDGE,
    CONGA_CONSTRUCTOR,
    # Weapons
    SCOUT_DRONE,
    JOYBUZZER,
    TINKERBLADE,
    HUM_LANCE,
    STINGER_PACK,
    MAGENTA_COIL,
    HELPING_CLAW,
    SPARK_WHIP,
    TICKLE_SAW,
    AFFECTION_SPIKE,
    # Add-Ons
    WIRED_TOOLKIT,
    CURIOSITY_ROUTINE,
    AFFECTION_EXE_ADD_ON,
    CHARM_MODULE,
    TINKERS_FRAME,
    JOYBUZZER_SLEEVE,
    GLEE_PLATING,
    AFFINITY_COIL,
    SPEEDLINK,
    # Transients
    JOYBOMB,
    RECALL_TO_WORKSHOP,
    SWARM_SURGE,
    # Structures
    IRON_CLUSTER,
    MASS_PRODUCTION_LINE,
    SWARM_BEACON,
)
from src.cards.clankers.CLAN.clan_bulwark import (
    BULWARK_9,
    # Chassis
    VAULT_CHASSIS,
    BASTION_FRAME,
    SENTINEL_CRANE,
    EMBANKMENT,
    CONTAINMENT_SERGEANT,
    READY_UP_ENGINEER,
    COUNTERWEIGHT_WALKER,
    MORTAR_LIEUTENANT,
    FOREMANS_WATCH,
    WORKSHOP_PROTOTYPE,
    # Weapons
    RIOT_BATON,
    CONTAINMENT_WHIP,
    RIOT_MORTAR,
    STUNNER_ARM,
    SENTINEL_CANNON,
    HEAVY_WATCHPOST,
    BURNOUT_CANNON,
    CONTAINMENT_PIKE,
    # Neutral weapons
    STANDARD_ISSUE_BLASTER,
    WORKSHOP_WRENCH,
    RIVETER_MK_I,
    SPARE_COILGUN,
    # Add-Ons
    REACTIVE_SHIELDING,
    VAULT_BRACER,
    RIOT_PLATING,
    BUNKER_CRADLE,
    COUNTERWEIGHT_SLEEVE,
    COOLANT_CRADLE,
    CONTAINMENT_LINING,
    SPOTTER_RIG,
    # Transients
    BURNOUT_PROTOCOL,
    REPAIR_SUBROUTINE,
    CONTAINMENT_RECALL,
    # Neutral Transient
    SCRAP_SALVO,
    # Structures
    CONTAINMENT_BAFFLE,
    WORKSHOP_SPRINKLER,
    # Neutral Structures
    SHARED_BUS,
    PUBLIC_TELEMETRY,
    AUXILIARY_BENCH,
)


# =============================================================================
# 1. CLAN_hybrid_swarm_brick — MIRTHBOT-1 swarm + FORGE big-chassis splash
# =============================================================================
# Hypothesis: the 86.8% MIRTH starter wins on tempo. Add a finisher punch
# (Modular Railgun + Heavy Assembly / Ironclad Foreman) so we still have the
# T1-T3 swarm but a T5+ overwhelming threat in case the opponent stabilises.
# Cuts some of MIRTH's filler Self-Mobile parts to make room.
#
# Composition: 20 Chassis (16 MIRTH swarm + 4 FORGE big) / 16 Weapons /
# 16 Add-Ons / 6 Transients / 2 Structures = 60.

def build_candidate_hybrid_swarm_brick() -> tuple[CardDefinition, list[CardDefinition]]:
    """MIRTHBOT-1 + FORGE chassis splash: swarm tempo with a brick finisher."""
    core = MIRTHBOT_1
    deck: list[CardDefinition] = [
        # --- Chassis (20) ---
        LINKED_CRAWLER, LINKED_CRAWLER, LINKED_CRAWLER, LINKED_CRAWLER,
        JOYFUL_WALKER, JOYFUL_WALKER, JOYFUL_WALKER, JOYFUL_WALKER,
        SPARKBOT, SPARKBOT, SPARKBOT, SPARKBOT,
        SKITTERSWARM, SKITTERSWARM, SKITTERSWARM, SKITTERSWARM,
        # FORGE splash — 4 big bodies for late-game closure
        IRONCLAD_FOREMAN, IRONCLAD_FOREMAN,
        HEAVY_ASSEMBLY, HEAVY_ASSEMBLY,

        # --- Weapons (16) ---
        SCOUT_DRONE, SCOUT_DRONE, SCOUT_DRONE, SCOUT_DRONE,
        JOYBUZZER, JOYBUZZER, JOYBUZZER,
        STINGER_PACK, STINGER_PACK, STINGER_PACK,
        # The finisher
        MODULAR_RAILGUN, MODULAR_RAILGUN, MODULAR_RAILGUN,
        HUM_LANCE, HUM_LANCE,
        BUZZSAW_MK_III,

        # --- Add-Ons (16) ---
        WIRED_TOOLKIT, WIRED_TOOLKIT, WIRED_TOOLKIT, WIRED_TOOLKIT,
        CURIOSITY_ROUTINE, CURIOSITY_ROUTINE, CURIOSITY_ROUTINE,
        AFFINITY_COIL, AFFINITY_COIL, AFFINITY_COIL,
        AFFECTION_EXE_ADD_ON, AFFECTION_EXE_ADD_ON,
        # FORGE splash add-on for armor on the big chassis
        SACRIFICIAL_PLATING, SACRIFICIAL_PLATING,
        SPEEDLINK,
        TINKERS_FRAME,

        # --- Transients (6) ---
        JOYBOMB, JOYBOMB, JOYBOMB,
        SWARM_SURGE, SWARM_SURGE, SWARM_SURGE,

        # --- Structures (2) ---
        IRON_CLUSTER,
        MASS_PRODUCTION_LINE,
    ]
    assert len(deck) == 60, f"hybrid_swarm_brick: {len(deck)}"
    return core, deck


# =============================================================================
# 2. CLAN_pure_deathclock — ETHOS-7 Transient/mill maximum
# =============================================================================
# Hypothesis: ETHOS at 25.8% is losing on tempo. Push hard the other way —
# stack Transients (~30) + mill weapons + Burnout Cannon to accelerate
# deathclock onset against the opponent. Bulwark Frame + max armor for
# survival. Use SUBROUTINE-α? No — ETHOS-7's first-Transient-cost-1-less
# is the stronger fit for high Transient density.
#
# Composition: 12 Chassis / 8 Weapons / 9 Add-Ons / 28 Transients /
# 3 Structures = 60.

def build_candidate_pure_deathclock() -> tuple[CardDefinition, list[CardDefinition]]:
    """ETHOS-7 deathclock: max Transient density + mill weapons."""
    core = ETHOS_7
    deck: list[CardDefinition] = [
        # --- Chassis (12) — tanks only ---
        BULWARK_FRAME, BULWARK_FRAME, BULWARK_FRAME, BULWARK_FRAME,
        LOOP_ENGINE, LOOP_ENGINE, LOOP_ENGINE,
        ENDURANCE_FRAME, ENDURANCE_FRAME,
        LONG_MEMORY_HUSK,
        SUBROUTINE_CORE, SUBROUTINE_CORE,

        # --- Weapons (8) — mill + Transient-synergy ---
        BURNOUT_CANNON, BURNOUT_CANNON, BURNOUT_CANNON, BURNOUT_CANNON,
        MEMORY_BLADE, MEMORY_BLADE, MEMORY_BLADE,
        DECODER_SPIKE,

        # --- Add-Ons (9) — armor backbone ---
        CONTAINMENT_LATTICE, CONTAINMENT_LATTICE, CONTAINMENT_LATTICE, CONTAINMENT_LATTICE,
        LOGIC_BUFFER, LOGIC_BUFFER, LOGIC_BUFFER,
        SOFT_CYCLE_RIDGE, SOFT_CYCLE_RIDGE,

        # --- Transients (28) — the engine ---
        HEURISTIC_LOOP, HEURISTIC_LOOP, HEURISTIC_LOOP, HEURISTIC_LOOP,
        REROUTE_POWER, REROUTE_POWER, REROUTE_POWER, REROUTE_POWER,
        GARBAGE_COLLECTOR, GARBAGE_COLLECTOR, GARBAGE_COLLECTOR, GARBAGE_COLLECTOR,
        DIAGNOSTIC_SWEEP, DIAGNOSTIC_SWEEP, DIAGNOSTIC_SWEEP, DIAGNOSTIC_SWEEP,
        SUBROUTINE_CASCADE, SUBROUTINE_CASCADE, SUBROUTINE_CASCADE,
        PATCH, PATCH, PATCH,
        SCRAP_SALVO, SCRAP_SALVO, SCRAP_SALVO, SCRAP_SALVO,
        # Burnout Protocol — doubles deathclock at the end
        BURNOUT_PROTOCOL, BURNOUT_PROTOCOL,

        # --- Structures (3) ---
        RECURSIVE_OBSERVATORY,
        COMPUTE_TRICKLE, COMPUTE_TRICKLE,
    ]
    assert len(deck) == 60, f"pure_deathclock: {len(deck)}"
    return core, deck


# =============================================================================
# 3. CLAN_hyper_armor — BULWARK-9 with maximum armor density
# =============================================================================
# Hypothesis: BULWARK at 15.7% is losing because the armor stack never sets
# up — too many filler cards. Triple down on armor: all 9 unique armor
# add-ons in the deck (4x of the affordable ones, 2-3x of the rest), with
# heavy carriers only. Trim transient count to maximize armor stacking
# probability.
#
# Composition: 15 Chassis / 8 Weapons / 28 Add-Ons / 6 Transients /
# 3 Structures = 60.

def build_candidate_hyper_armor() -> tuple[CardDefinition, list[CardDefinition]]:
    """BULWARK-9: maximum armor add-on density on heavy carriers."""
    core = BULWARK_9
    deck: list[CardDefinition] = [
        # --- Chassis (15) — heavy wall carriers ---
        VAULT_CHASSIS, VAULT_CHASSIS, VAULT_CHASSIS, VAULT_CHASSIS,
        BASTION_FRAME, BASTION_FRAME, BASTION_FRAME, BASTION_FRAME,
        SENTINEL_CRANE, SENTINEL_CRANE,
        CONTAINMENT_SERGEANT, CONTAINMENT_SERGEANT, CONTAINMENT_SERGEANT,
        FOREMANS_WATCH, FOREMANS_WATCH,

        # --- Weapons (8) — direct workshop pressure ---
        RIOT_MORTAR, RIOT_MORTAR, RIOT_MORTAR, RIOT_MORTAR,
        CONTAINMENT_WHIP, CONTAINMENT_WHIP, CONTAINMENT_WHIP,
        STUNNER_ARM,

        # --- Add-Ons (28) — every armor card in the pool ---
        REACTIVE_SHIELDING, REACTIVE_SHIELDING, REACTIVE_SHIELDING, REACTIVE_SHIELDING,  # armor 3 (BULWARK)
        BUNKER_CRADLE, BUNKER_CRADLE, BUNKER_CRADLE, BUNKER_CRADLE,                     # armor 4 (BULWARK)
        CONTAINMENT_LINING, CONTAINMENT_LINING, CONTAINMENT_LINING, CONTAINMENT_LINING, # armor 2 + bonus (BULWARK)
        RIOT_PLATING, RIOT_PLATING, RIOT_PLATING, RIOT_PLATING,                         # armor 2 thorns (BULWARK)
        CONTAINMENT_LATTICE, CONTAINMENT_LATTICE, CONTAINMENT_LATTICE,                  # armor 2 (ETHOS)
        LOGIC_BUFFER, LOGIC_BUFFER, LOGIC_BUFFER,                                       # armor 3 (ETHOS)
        TUNGSTEN_CARAPACE, TUNGSTEN_CARAPACE,                                           # armor 3 (FORGE)
        THICK_HIDE, THICK_HIDE,                                                         # armor 2 (FORGE)
        COOLANT_CRADLE, COOLANT_CRADLE,                                                 # scrap-ready

        # --- Transients (6) — the closer ---
        REPAIR_SUBROUTINE, REPAIR_SUBROUTINE, REPAIR_SUBROUTINE, REPAIR_SUBROUTINE,
        BURNOUT_PROTOCOL, BURNOUT_PROTOCOL,

        # --- Structures (3) ---
        CONTAINMENT_BAFFLE, CONTAINMENT_BAFFLE,
        WORKSHOP_SPRINKLER,
    ]
    assert len(deck) == 60, f"hyper_armor: {len(deck)}"
    return core, deck


# =============================================================================
# 4. CLAN_solo_mobile_rush — Affection.exe + all Self-Mobile parts
# =============================================================================
# Hypothesis: a "no chassis" deck where Self-Mobile parts ARE the attackers.
# Affection.exe Core (swarm; +1 integrity on first chassis per turn — also
# useful when we DO drop a 1-drop). Cheap Mirth chassis as ALSO-rans for the
# rare times we want a host. All 9 Self-Mobile cards 4x where allowed.
#
# Composition: 12 Chassis (cheap 1-2 drops) / 26 Weapons (all Self-Mobile +
# few attach payoffs) / 12 Add-Ons / 8 Transients / 2 Structures = 60.

def build_candidate_solo_mobile_rush() -> tuple[CardDefinition, list[CardDefinition]]:
    """Affection.exe rush: Self-Mobile parts as attackers, minimal chassis."""
    core = AFFECTION_EXE
    deck: list[CardDefinition] = [
        # --- Chassis (12) — cheapest swarm bodies as backup ---
        SPARKBOT, SPARKBOT, SPARKBOT, SPARKBOT,
        SKITTERSWARM, SKITTERSWARM, SKITTERSWARM, SKITTERSWARM,
        WHIRRING_INITIATE, WHIRRING_INITIATE,
        TINKERLING, TINKERLING,

        # --- Weapons (26) — every Self-Mobile + cheap attach payoffs ---
        SCOUT_DRONE, SCOUT_DRONE, SCOUT_DRONE, SCOUT_DRONE,                # +2/+1 SM
        JOYBUZZER, JOYBUZZER, JOYBUZZER, JOYBUZZER,                       # +1 SM
        STINGER_PACK, STINGER_PACK, STINGER_PACK, STINGER_PACK,           # +1 SM
        MAGENTA_COIL, MAGENTA_COIL, MAGENTA_COIL, MAGENTA_COIL,            # +3/+1 SM
        SPARK_WHIP, SPARK_WHIP, SPARK_WHIP,                                # +2 SM
        TICKLE_SAW, TICKLE_SAW, TICKLE_SAW,                                # +3 SM (1-slot)
        CIPHER_ROTOR, CIPHER_ROTOR,                                        # +3 SM (ETHOS)
        TINKERBLADE,                                                       # attach payoff (scrap)
        HELPING_CLAW,                                                      # +1/turn cheap

        # --- Add-Ons (12) — Self-Mobile + attach payoffs ---
        AFFECTION_EXE_ADD_ON, AFFECTION_EXE_ADD_ON, AFFECTION_EXE_ADD_ON, AFFECTION_EXE_ADD_ON,  # +1/+1 SM add-on
        JOYBUZZER_SLEEVE, JOYBUZZER_SLEEVE, JOYBUZZER_SLEEVE, JOYBUZZER_SLEEVE,                # +1 SM add-on
        CURIOSITY_ROUTINE, CURIOSITY_ROUTINE, CURIOSITY_ROUTINE, CURIOSITY_ROUTINE,            # SM + chain-attach

        # --- Transients (8) ---
        JOYBOMB, JOYBOMB, JOYBOMB, JOYBOMB,
        SCRAP_SALVO, SCRAP_SALVO, SCRAP_SALVO,
        FORGE_STOKE,

        # --- Structures (2) ---
        SHARED_BUS, SHARED_BUS,
    ]
    assert len(deck) == 60, f"solo_mobile_rush: {len(deck)}"
    return core, deck


# =============================================================================
# 5. CLAN_forge_artillery_hybrid — substituted for Modular Reroute
# =============================================================================
# SWAP NOTE: The original "Modular Reroute" hypothesis is infeasible — the
# CLAN pool ships only 2 Modular cards (Modular Railgun, Apex Coilgun). With
# 4x of each that maxes at 8 cards, but you can't run 8 Modular ACTIONS off
# 8 cards unless you draw them all — too thin a strategy to test.
#
# Replacement hypothesis: COMBINE the two best wave-1 decks' tools. FORGE
# (71.7%) + BULWARK (15.7%) — but it's the Hard AI playing both, and FORGE's
# brick chassis already wins games. Adding BULWARK's armor stack on top of
# FORGE chassis + BULWARK's workshop damage weapons (Riot Mortar, Burnout
# Cannon) gives you "big robots that ALSO ping the opposing Core directly."
# Tests whether the brick path improves with artillery payoff weapons.
#
# Composition: 20 Chassis (15 FORGE + 5 BULWARK) / 14 Weapons (mix) /
# 18 Add-Ons (armor heavy) / 5 Transients / 3 Structures = 60.

def build_candidate_forge_artillery_hybrid() -> tuple[CardDefinition, list[CardDefinition]]:
    """FORGE + BULWARK hybrid: big chassis with armor stack + workshop dmg."""
    core = FORGE_DELTA
    deck: list[CardDefinition] = [
        # --- Chassis (20) — FORGE heavy + BULWARK wall ---
        HEAVY_ASSEMBLY, HEAVY_ASSEMBLY, HEAVY_ASSEMBLY, HEAVY_ASSEMBLY,
        IRONCLAD_FOREMAN, IRONCLAD_FOREMAN, IRONCLAD_FOREMAN, IRONCLAD_FOREMAN,
        SMELTER_FRAME, SMELTER_FRAME, SMELTER_FRAME,
        IRON_SPIRE, IRON_SPIRE,
        APEX_HULK, APEX_HULK,
        # BULWARK splash
        VAULT_CHASSIS, VAULT_CHASSIS,
        BASTION_FRAME, BASTION_FRAME,
        SENTINEL_CRANE,

        # --- Weapons (14) — FORGE finishers + BULWARK workshop damage ---
        MODULAR_RAILGUN, MODULAR_RAILGUN, MODULAR_RAILGUN, MODULAR_RAILGUN,
        BUZZSAW_MK_III, BUZZSAW_MK_III, BUZZSAW_MK_III,
        FORGE_CANNON, FORGE_CANNON,
        # BULWARK splash — workshop damage
        RIOT_MORTAR, RIOT_MORTAR, RIOT_MORTAR,
        BURNOUT_CANNON, BURNOUT_CANNON,

        # --- Add-Ons (18) — armor backbone (FORGE + BULWARK) ---
        SACRIFICIAL_PLATING, SACRIFICIAL_PLATING, SACRIFICIAL_PLATING, SACRIFICIAL_PLATING,
        TUNGSTEN_CARAPACE, TUNGSTEN_CARAPACE, TUNGSTEN_CARAPACE,
        REACTIVE_SHIELDING, REACTIVE_SHIELDING, REACTIVE_SHIELDING,
        BUNKER_CRADLE, BUNKER_CRADLE, BUNKER_CRADLE,
        CONTAINMENT_LINING, CONTAINMENT_LINING,
        RIOT_PLATING, RIOT_PLATING,
        REACTOR_SHELL,

        # --- Transients (5) ---
        FORGE_STOKE, FORGE_STOKE, FORGE_STOKE,
        BIG_SWING,
        BURNOUT_PROTOCOL,

        # --- Structures (3) ---
        COMPOUNDING_BUTTRESS,
        CONTAINMENT_BAFFLE,
        HEAVY_FORGE,
    ]
    assert len(deck) == 60, f"forge_artillery_hybrid: {len(deck)}"
    return core, deck


# =============================================================================
# 6. CLAN_synchronize_max — MIRTHBOT-1 with maximum Synchronize density
# =============================================================================
# Hypothesis: starter MIRTH at 86.8% runs 13 Synchronize chassis. Push it
# higher — 4-of EVERY Synchronize chassis (5 cards × 4 = 20) plus every
# Synchronize-payoff card (Iron Cluster x3, Affinity Coil x4, Hum-Lance x4,
# Tinker's Frame x4). Tests whether Synchronize is the structural driver
# (engine-level fix) vs. just the starter being too dense.
#
# Composition: 25 Chassis (20 Synchronize + 5 cheap) / 14 Weapons /
# 12 Add-Ons / 6 Transients / 3 Structures = 60.

def build_candidate_synchronize_max() -> tuple[CardDefinition, list[CardDefinition]]:
    """MIRTHBOT-1: maximum Synchronize chassis + every Synchronize payoff."""
    core = MIRTHBOT_1
    deck: list[CardDefinition] = [
        # --- Chassis (25) — Synchronize maxed ---
        LINKED_CRAWLER, LINKED_CRAWLER, LINKED_CRAWLER, LINKED_CRAWLER,
        JOYFUL_WALKER, JOYFUL_WALKER, JOYFUL_WALKER, JOYFUL_WALKER,
        MAGENTA_BUZZER, MAGENTA_BUZZER, MAGENTA_BUZZER, MAGENTA_BUZZER,
        CROWD_MARCHER, CROWD_MARCHER, CROWD_MARCHER, CROWD_MARCHER,
        HUM_SWARM_ALPHA, HUM_SWARM_ALPHA, HUM_SWARM_ALPHA, HUM_SWARM_ALPHA,
        # Cheap non-Sync filler to ensure 1-drops fire on T1
        SPARKBOT, SPARKBOT, SPARKBOT,
        SKITTERSWARM, SKITTERSWARM,

        # --- Weapons (14) — Synchronize-payoff bias ---
        HUM_LANCE, HUM_LANCE, HUM_LANCE, HUM_LANCE,                       # +3 if Synchronize host
        SCOUT_DRONE, SCOUT_DRONE, SCOUT_DRONE, SCOUT_DRONE,               # SM tempo
        JOYBUZZER, JOYBUZZER, JOYBUZZER,                                  # +1 SM
        STINGER_PACK, STINGER_PACK, STINGER_PACK,                         # +1 SM

        # --- Add-Ons (12) — Synchronize multipliers ---
        AFFINITY_COIL, AFFINITY_COIL, AFFINITY_COIL, AFFINITY_COIL,       # Synchronize +1 power aura
        TINKERS_FRAME, TINKERS_FRAME, TINKERS_FRAME, TINKERS_FRAME,        # +1/+2 if Synchronize host
        WIRED_TOOLKIT, WIRED_TOOLKIT, WIRED_TOOLKIT, WIRED_TOOLKIT,       # draw on attach

        # --- Transients (6) ---
        SWARM_SURGE, SWARM_SURGE, SWARM_SURGE, SWARM_SURGE,                # Synchronize-only +1/+1
        JOYBOMB, JOYBOMB,                                                  # all-chassis +1

        # --- Structures (3) ---
        IRON_CLUSTER, IRON_CLUSTER, IRON_CLUSTER,                          # Synchronize +1 integrity
    ]
    assert len(deck) == 60, f"synchronize_max: {len(deck)}"
    return core, deck


# =============================================================================
# Registry — the candidate tournament harness reads this dict
# =============================================================================

CLAN_CANDIDATE_DECKS: dict[str, callable] = {
    "CLAN_hybrid_swarm_brick":      build_candidate_hybrid_swarm_brick,
    "CLAN_pure_deathclock":         build_candidate_pure_deathclock,
    "CLAN_hyper_armor":             build_candidate_hyper_armor,
    "CLAN_solo_mobile_rush":        build_candidate_solo_mobile_rush,
    "CLAN_forge_artillery_hybrid":  build_candidate_forge_artillery_hybrid,
    "CLAN_synchronize_max":         build_candidate_synchronize_max,
}


__all__ = [
    "CLAN_CANDIDATE_DECKS",
    "build_candidate_hybrid_swarm_brick",
    "build_candidate_pure_deathclock",
    "build_candidate_hyper_armor",
    "build_candidate_solo_mobile_rush",
    "build_candidate_forge_artillery_hybrid",
    "build_candidate_synchronize_max",
]
