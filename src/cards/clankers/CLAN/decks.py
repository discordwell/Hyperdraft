"""CLAN — Tournament starter decks (4 decks × 60 cards).

Each deck is a pinnacle of its archetype, built from the 150-card CLAN set
(plus its anchored Core). Decks are tested by `scripts/play/clan_tournament.py`
which discovers `CLAN_*` labels from ``CLAN_STARTER_DECKS``.

Archetypes
==========

1. CLAN_forge (brick / FORGE-Δ)
   Plan: Few enormous robots. Heavy chassis with stacked add-ons + modular
   weapons. Reclaim parts to keep scrap pool full so Tungsten Walker plays
   for free. Big Swing as a finisher.

2. CLAN_ethos (control / ETHOS-7)
   Plan: Transient-heavy spell-slinger. Bulwark Frame as a 1-2 chassis wall
   that absorbs damage while Heuristic Loop chains draws and Reroute Power
   burns the opposing Core. Recursive Observatory + Compute Trickle ramp.

3. CLAN_mirth (swarm / MIRTHBOT-1)
   Plan: Flood the floor with 1-2 Compute chassis + Self-Mobile weapons that
   don't need a host. Synchronize lord lights up at 2+ Synchronize chassis,
   compounded by Iron Cluster + Affinity Coil. On-attach payoffs (Wired
   Toolkit, Curiosity Routine) fire constantly because the deck attaches a
   lot of cheap parts.

4. CLAN_bulwark (artillery / BULWARK-9)
   Plan: Stack armor add-ons on Vault Chassis. Survive every combat, accumulate
   scrap, and ride Burnout Protocol's doubled deathclock damage to victory.
   Containment Baffle taxes opposing attackers; Repair Subroutine recycles
   armor.
"""

from __future__ import annotations

from src.engine.types import CardDefinition

# -----------------------------------------------------------------------------
# Imports — explicit, one card each, so the deck contents are easy to inspect.
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
# CLAN_forge — FORGE-Δ brick deck (60 cards)
# =============================================================================
# Plan: 27 Chassis (heavy bias), 16 Weapons, 10 Add-Ons (reclaim-heavy),
# 5 Transients, 2 Structures. Wants T4 Heavy Assembly into T5 Modular Railgun +
# Sacrificial Plating. Tungsten Walker plays nearly free off Reclaim scrap.
#
# Composition: 27 / 16 / 10 / 5 / 2 = 60.

def build_clan_forge() -> tuple[CardDefinition, list[CardDefinition]]:
    """FORGE-Δ brick: few but enormous robots, stacked with parts."""
    deck: list[CardDefinition] = [
        # --- Chassis (27) ---
        # Heavy hitters (Key cards from §3.1)
        HEAVY_ASSEMBLY, HEAVY_ASSEMBLY, HEAVY_ASSEMBLY, HEAVY_ASSEMBLY,   # 4× the platform
        IRONCLAD_FOREMAN, IRONCLAD_FOREMAN, IRONCLAD_FOREMAN, IRONCLAD_FOREMAN,  # 4× T4 enabler
        TUNGSTEN_WALKER, TUNGSTEN_WALKER, TUNGSTEN_WALKER,                 # 3× scrap-discount big body
        SMELTER_FRAME, SMELTER_FRAME, SMELTER_FRAME,                       # 3× weapon-attach grows integrity
        IRON_SPIRE, IRON_SPIRE, IRON_SPIRE,                                # 3× ETB chassis-cheat
        FOUNDRYMAN, FOUNDRYMAN,                                            # 2× attached-weapon buff
        PLANT_FOREMAN, PLANT_FOREMAN,                                      # 2× draw on big chassis ETB
        CARBON_STEEL_DRUDGE, CARBON_STEEL_DRUDGE,                          # 2× tank
        APEX_HULK, APEX_HULK,                                              # 2× late-game closer
        SALVAGER_SEVEN, SALVAGER_SEVEN,                                    # 2× scrap-fueled recursion

        # --- Weapons (16) ---
        MODULAR_RAILGUN, MODULAR_RAILGUN, MODULAR_RAILGUN, MODULAR_RAILGUN,   # 4× the cannon
        BUZZSAW_MK_III, BUZZSAW_MK_III, BUZZSAW_MK_III,                       # 3× efficient +4 power
        FORGE_CANNON, FORGE_CANNON,                                           # 2× +5/+1 integrity bonus
        APEX_COILGUN, APEX_COILGUN,                                           # 2× modular finisher
        BOLT_DRIVER_MK_II, BOLT_DRIVER_MK_II,                                 # 2× efficient mid
        ANVIL_DRONE,                                                          # 1× combat damage boost
        SALVAGE_CLEAVER,                                                      # 1× kill-credit scrap
        HEAVY_SPIKE,                                                          # 1× reclaim 2

        # --- Add-Ons (10) ---
        SACRIFICIAL_PLATING, SACRIFICIAL_PLATING, SACRIFICIAL_PLATING, SACRIFICIAL_PLATING,  # 4× backstop (Key card)
        TUNGSTEN_CARAPACE, TUNGSTEN_CARAPACE,                                 # 2× +1/+4 armor 3
        REACTOR_SHELL, REACTOR_SHELL,                                         # 2× +1/+4 scrap-ready
        LUGNUT_CRADLE,                                                        # 1× +1 integ per weapon
        FOUNDRY_BRACER,                                                       # 1× +1 power on attack

        # --- Transients (5) ---
        FORGE_STOKE, FORGE_STOKE, FORGE_STOKE,                                # 3× scrap ramp
        BIG_SWING, BIG_SWING,                                                 # 2× non-combat finisher

        # --- Structures (2) ---
        COMPOUNDING_BUTTRESS,                                                 # 1× +1 power lord (Key card)
        HEAVY_FORGE,                                                          # 1× weapons -1 cost
    ]
    assert len(deck) == 60, f"CLAN_forge: {len(deck)}"
    return (FORGE_DELTA, deck)


# =============================================================================
# CLAN_ethos — ETHOS-7 control deck (60 cards)
# =============================================================================
# Plan: 14 Chassis (small wall presence), 10 Weapons (Transient-synergy bias),
# 10 Add-Ons (armor backbone), 22 Transients (the engine), 4 Structures.
# Wants 1-2 Bulwark Frames stacked with Containment Lattice + Logic Buffer
# while Heuristic Loop chains draws and Reroute Power burns the opposing Core.
#
# Composition: 14 / 10 / 10 / 22 / 4 = 60.

def build_clan_ethos() -> tuple[CardDefinition, list[CardDefinition]]:
    """ETHOS-7 control: Transient density, tank chassis, deathclock pressure."""
    deck: list[CardDefinition] = [
        # --- Chassis (14) ---
        BULWARK_FRAME, BULWARK_FRAME, BULWARK_FRAME, BULWARK_FRAME,           # 4× the tank (Key card)
        LOOP_ENGINE, LOOP_ENGINE, LOOP_ENGINE,                                # 3× Transient-trigger draw
        SUBROUTINE_CORE, SUBROUTINE_CORE,                                     # 2× +1 power per Transient
        HEURISTIC_SENTRY, HEURISTIC_SENTRY,                                   # 2× cheap loot
        CONTAINMENT_SCRIBE,                                                   # 1× scry on Transient
        LONG_MEMORY_HUSK,                                                     # 1× Reclaim 2 tank
        RECURSIVE_SENTINEL,                                                   # 1× Transient-resolve power

        # --- Weapons (10) ---
        DECODER_SPIKE, DECODER_SPIKE, DECODER_SPIKE,                          # 3× first-Transient draw
        HEURISTIC_LANCE, HEURISTIC_LANCE,                                     # 2× +1 power per Transient
        LOGIC_LANCE, LOGIC_LANCE,                                             # 2× scry on attach
        CONTAINMENT_LANCE,                                                    # 1× lockout ready
        RECURSION_HOOK,                                                       # 1× death = return Transient
        MEMORY_BLADE,                                                         # 1× mill-for-Transient draw

        # --- Add-Ons (10) ---
        CONTAINMENT_LATTICE, CONTAINMENT_LATTICE, CONTAINMENT_LATTICE, CONTAINMENT_LATTICE,  # 4× the armor backbone (Key card)
        LOGIC_BUFFER, LOGIC_BUFFER, LOGIC_BUFFER,                             # 3× armor 3
        HEURISTIC_LAYER, HEURISTIC_LAYER,                                     # 2× draw on Transient
        MEMORY_BUFFER,                                                        # 1× Transient recursion

        # --- Transients (22) ---
        HEURISTIC_LOOP, HEURISTIC_LOOP, HEURISTIC_LOOP, HEURISTIC_LOOP,       # 4× the draw engine (Key card)
        REROUTE_POWER, REROUTE_POWER, REROUTE_POWER, REROUTE_POWER,           # 4× burn finisher (Key card)
        GARBAGE_COLLECTOR, GARBAGE_COLLECTOR, GARBAGE_COLLECTOR,              # 3× recursion (Key card)
        DIAGNOSTIC_SWEEP, DIAGNOSTIC_SWEEP, DIAGNOSTIC_SWEEP,                 # 3× scry 3
        PATCH, PATCH, PATCH,                                                  # 3× heal tank
        SUBROUTINE_CASCADE, SUBROUTINE_CASCADE,                               # 2× draw 3 + cost reduction
        SCRAP_SALVO, SCRAP_SALVO, SCRAP_SALVO,                                # 3× neutral burn

        # --- Structures (4) ---
        RECURSIVE_OBSERVATORY, RECURSIVE_OBSERVATORY,                         # 2× Reticulate (Key card)
        COMPUTE_TRICKLE, COMPUTE_TRICKLE,                                     # 2× Compute ramp
    ]
    assert len(deck) == 60, f"CLAN_ethos: {len(deck)}"
    return (ETHOS_7, deck)


# =============================================================================
# CLAN_mirth — MIRTHBOT-1 swarm deck (60 cards)
# =============================================================================
# Plan: 28 Chassis (cheap many), 14 Weapons (Self-Mobile bias), 10 Add-Ons,
# 6 Transients, 2 Structures. Wants T1 Sparkbot/Skitterswarm + Self-Mobile
# parts on the floor, T2 Linked Crawler #2 lighting Synchronize, T3-4 flood
# and alpha strike with Wired Toolkit / Curiosity Routine attach-payoffs.
#
# Composition: 28 / 14 / 10 / 6 / 2 = 60.

def build_clan_mirth() -> tuple[CardDefinition, list[CardDefinition]]:
    """MIRTHBOT-1 swarm: many small chassis + Self-Mobile parts + Synchronize."""
    deck: list[CardDefinition] = [
        # --- Chassis (28) — Synchronize core + 1-drop swarm ---
        LINKED_CRAWLER, LINKED_CRAWLER, LINKED_CRAWLER, LINKED_CRAWLER,       # 4× the lord-anchor (Key card)
        SKITTERSWARM, SKITTERSWARM, SKITTERSWARM, SKITTERSWARM,               # 4× on-attach payoff (Key card)
        SPARKBOT, SPARKBOT, SPARKBOT, SPARKBOT,                               # 4× 1-Compute vanilla 2/1
        JOYFUL_WALKER, JOYFUL_WALKER, JOYFUL_WALKER, JOYFUL_WALKER,           # 4× Synchronize 2/2
        MAGENTA_BUZZER, MAGENTA_BUZZER, MAGENTA_BUZZER,                       # 3× Synchronize 3/1
        TINKERLING, TINKERLING, TINKERLING,                                   # 3× ETB attach trigger
        AFFECTION_BOT, AFFECTION_BOT,                                         # 2× scrap on attach
        WHIRRING_INITIATE, WHIRRING_INITIATE,                                 # 2× cheap loot ETB
        HUM_SWARM_ALPHA,                                                      # 1× Synchronize +1 integ aura
        CROWD_MARCHER,                                                        # 1× Synchronize scaling

        # --- Weapons (14) — Self-Mobile bias for the swarm-without-a-host plan ---
        SCOUT_DRONE, SCOUT_DRONE, SCOUT_DRONE, SCOUT_DRONE,                   # 4× the engine card (Key card)
        JOYBUZZER, JOYBUZZER, JOYBUZZER,                                      # 3× cheap Self-Mobile
        STINGER_PACK, STINGER_PACK, STINGER_PACK,                             # 3× 1-Compute Self-Mobile
        HUM_LANCE, HUM_LANCE,                                                 # 2× +3 if Synchronize host
        MAGENTA_COIL,                                                         # 1× Self-Mobile +3/+1
        SPARK_WHIP,                                                           # 1× +2 Self-Mobile

        # --- Add-Ons (10) ---
        WIRED_TOOLKIT, WIRED_TOOLKIT, WIRED_TOOLKIT, WIRED_TOOLKIT,           # 4× draw on attach (Key card)
        CURIOSITY_ROUTINE, CURIOSITY_ROUTINE, CURIOSITY_ROUTINE,              # 3× chain-attach
        AFFINITY_COIL, AFFINITY_COIL,                                         # 2× Synchronize +1 power aura
        TINKERS_FRAME,                                                        # 1× Synchronize-scaled stats

        # --- Transients (6) ---
        JOYBOMB, JOYBOMB, JOYBOMB,                                            # 3× anthem swing
        SWARM_SURGE, SWARM_SURGE, SWARM_SURGE,                                # 3× Synchronize-only anthem

        # --- Structures (2) ---
        IRON_CLUSTER,                                                         # 1× Synchronize +1 integ (Key card)
        MASS_PRODUCTION_LINE,                                                 # 1× ≤2 cost +1/+0
    ]
    assert len(deck) == 60, f"CLAN_mirth: {len(deck)}"
    return (MIRTHBOT_1, deck)


# =============================================================================
# CLAN_bulwark — BULWARK-9 artillery deck (60 cards)
# =============================================================================
# Plan: 19 Chassis (tank-heavy), 11 Weapons, 17 Add-Ons (armor stacking — the
# whole point), 6 Transients (burnout finishers), 3 Structures, 4 cards spilled
# across these. Wants Vault Chassis stacked with 3+ armor add-ons, plus
# Containment Baffle locking the opponent's attackers out. Burnout Protocol
# closes the game when libraries empty.
#
# Composition: 19 / 11 / 17 / 6 / 3 = 56 — wait, need exactly 60. We bump some
# armor counts. Final: 19 / 11 / 18 / 7 / 3 = 58 nope. Trying: 20 chassis, 11
# weapons, 19 add-ons (armor stacking), 7 transients, 3 structures = 60.
# (Add-On count above the suggested 14-20 range upper bound = 19 to drive
# the armor stacking pinnacle plan.)

def build_clan_bulwark() -> tuple[CardDefinition, list[CardDefinition]]:
    """BULWARK-9 artillery: armor stacking on huge chassis + deathclock burn."""
    deck: list[CardDefinition] = [
        # --- Chassis (20) ---
        VAULT_CHASSIS, VAULT_CHASSIS, VAULT_CHASSIS, VAULT_CHASSIS,           # 4× the wall (Key card)
        BASTION_FRAME, BASTION_FRAME, BASTION_FRAME, BASTION_FRAME,           # 4× scrap-to-preserve-armor
        CONTAINMENT_SERGEANT, CONTAINMENT_SERGEANT, CONTAINMENT_SERGEANT,     # 3× heal on exhausted-armor count
        FOREMANS_WATCH, FOREMANS_WATCH,                                       # 2× draw on exhausted-armor count
        READY_UP_ENGINEER, READY_UP_ENGINEER,                                 # 2× extra ready per turn
        SENTINEL_CRANE, SENTINEL_CRANE,                                       # 2× high-end wall
        COUNTERWEIGHT_WALKER,                                                 # 1× grows on chassis death
        MORTAR_LIEUTENANT,                                                    # 1× direct workshop damage
        EMBANKMENT,                                                           # 1× cheap +0/+5 wall

        # --- Weapons (11) ---
        RIOT_MORTAR, RIOT_MORTAR, RIOT_MORTAR,                                # 3× unblocked → 2 workshop dmg
        CONTAINMENT_WHIP, CONTAINMENT_WHIP,                                   # 2× exhaust add-on for damage
        BURNOUT_CANNON, BURNOUT_CANNON,                                       # 2× mill for deathclock
        SENTINEL_CANNON,                                                      # 1× kill → workshop heal
        STUNNER_ARM,                                                          # 1× lock opposing attacker
        HEAVY_WATCHPOST,                                                      # 1× blocker armor 2
        RIOT_BATON,                                                           # 1× +1 power on block

        # --- Add-Ons (19) — armor stacking, the whole identity ---
        REACTIVE_SHIELDING, REACTIVE_SHIELDING, REACTIVE_SHIELDING, REACTIVE_SHIELDING,  # 4× the keystone armor (Key card)
        BUNKER_CRADLE, BUNKER_CRADLE, BUNKER_CRADLE,                          # 3× armor 4
        CONTAINMENT_LINING, CONTAINMENT_LINING, CONTAINMENT_LINING,           # 3× armor 2 + exhausted-bonus
        RIOT_PLATING, RIOT_PLATING, RIOT_PLATING,                             # 3× armor 2 thorns
        COOLANT_CRADLE, COOLANT_CRADLE,                                       # 2× scrap-to-ready
        VAULT_BRACER, VAULT_BRACER,                                           # 2× vanilla +0/+3
        SPOTTER_RIG,                                                          # 1× draw on block
        COUNTERWEIGHT_SLEEVE,                                                 # 1× +1 integ on block

        # --- Transients (7) ---
        REPAIR_SUBROUTINE, REPAIR_SUBROUTINE, REPAIR_SUBROUTINE,              # 3× ready 2 add-ons (Key card)
        BURNOUT_PROTOCOL, BURNOUT_PROTOCOL,                                   # 2× double deathclock (Key card)
        CONTAINMENT_RECALL,                                                   # 1× recur destroyed add-on
        SCRAP_SALVO,                                                          # 1× neutral burn

        # --- Structures (3) ---
        CONTAINMENT_BAFFLE, CONTAINMENT_BAFFLE,                               # 2× attack tax (Key card)
        WORKSHOP_SPRINKLER,                                                   # 1× ready bonus
    ]
    assert len(deck) == 60, f"CLAN_bulwark: {len(deck)}"
    return (BULWARK_9, deck)


# =============================================================================
# Registry — tournament harness reads this dict to discover decks
# =============================================================================

CLAN_STARTER_DECKS: dict[str, callable] = {
    "CLAN_forge":   build_clan_forge,
    "CLAN_ethos":   build_clan_ethos,
    "CLAN_mirth":   build_clan_mirth,
    "CLAN_bulwark": build_clan_bulwark,
}


__all__ = [
    "CLAN_STARTER_DECKS",
    "build_clan_forge",
    "build_clan_ethos",
    "build_clan_mirth",
    "build_clan_bulwark",
]
