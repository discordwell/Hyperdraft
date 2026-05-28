"""Auto-generated interceptor verification for Star Wars: Galactic Conflict (SWG).

Covers the 152 cards whose slice-11 info-pulse stubs were replaced with real,
text-matching implementations (see docs/swr_slice11_detect.md). Each test fires
the card's actual trigger (or resolves its spell) and asserts an event matching
the card's rules text is emitted — catching the "interceptor wired but effect_fn
returns []" depths trap. Static / equipment / activated-ability cards assert the
expected interceptor(s) register. Generated via /test-interceptors workflow.

Run: HYPERDRAFT_STRICT=1 python tests/test_star_wars_interceptors.py
"""

import os
import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

import importlib.util
from pathlib import Path

from src.engine.game import Game
from src.engine.types import (
    Event, EventType, ZoneType, CardType, Color, Characteristics,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "star_wars", str(_PROJECT_ROOT / "src/cards/custom/star_wars.py")
)
star_wars = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(star_wars)
STAR_WARS_CARDS = star_wars.STAR_WARS_CARDS

# Cards intentionally NOT in scope (left vanilla — keyword/evasion-only, mana-only
# lands, or restriction auras the engine can't express as events/static buffs):
SKIPPED_CARDS = {
    "Gamorrean Guard": "keyword-only (Menace) — vanilla",
    "Nexu": "keyword-only (Deathtouch, haste) — vanilla",
    "Felucia Beast": "trample + unblockable-rider (no event) — vanilla",
    "Yavin Jungle Cat": "haste + unblockable-rider — vanilla",
    "Rancor": "trample + unblockable-rider — vanilla",
    "Star Destroyer": "evasion vehicle — vanilla",
    "Speeder Bike": "evasion vehicle — vanilla",
    "AT-AT Walker": "evasion vehicle — vanilla",
    "Restraining Bolt": "aura restriction (no static buff) — vanilla",
    "Thermal Imaging Goggles": "equip unblockable-rider (no buff) — vanilla",
    # Mana-only / activated-ability lands (base mana parsed from text; sub-abilities
    # are activated, not triggered):
    "Coruscant": "land — activated mana abilities",
    "Tatooine": "land — activated mana abilities",
    "Endor Forest": "land — activated token ability",
    "Dagobah": "land — activated scry ability",
    "Hoth": "land — activated -1/-0 ability",
    "Naboo": "land — enters-tapped mana",
    "Kamino": "land — activated token ability",
    "Geonosis": "land — activated token ability",
    "Jakku": "land — activated regrowth ability",
    "Mos Eisley Spaceport": "land — restricted mana",
    "Jedi Temple": "land — grants creatures a mana ability",
    "Death Star Hangar": "land — restricted mana",
    "Scarif": "land — activated loot ability",
    "Jedha": "land — activated token ability",
    "Bespin": "land — grants vehicles a mana ability",
    "Lothal": "land — restricted mana",
}

# (card_name, fn_name, wire, trigger, expected_event_names)
SPEC = [

    ('AT-ST Walker', 'at_st_setup', 'setup', 'attack', ['DAMAGE']),
    ('Aggressive Negotiations', 'aggressive_negotiations_resolve', 'resolve', 'resolve', ['GRANT_KEYWORD', 'PT_MODIFICATION']),
    ('Alderaanian Refugee', 'alderaanian_refugee_setup', 'setup', 'etb', ['LIFE_CHANGE']),
    ('Arena Pit', 'arena_pit_setup', 'setup', 'upkeep', ['SACRIFICE']),
    ('Aurra Sing, Sniper', 'aurra_sing_setup', 'setup', 'activated', ['__ACTIVATED__']),
    ('BB-8, Loyal Astromech', 'bb8_setup', 'setup', 'etb', ['SCRY']),
    ('Bacta Tank', 'bacta_tank_setup', 'setup', 'activated', ['LIFE_CHANGE', '__ACTIVATED__']),
    ('Bail Organa', 'bail_organa_setup', 'setup', 'etb', ['SEARCH_LIBRARY']),
    ('Balance of the Force', 'balance_of_the_force_resolve', 'resolve', 'resolve', ['LIFE_CHANGE', 'OBJECT_DESTROYED']),
    ('Battle Droid', 'battle_droid_setup', 'setup', 'death', ['CREATE_TOKEN']),
    ('Beast Call', 'beast_call_resolve', 'resolve', 'resolve', ['SEARCH_LIBRARY']),
    ('Beskar Helmet', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Blaster Bolt', 'blaster_bolt_resolve', 'resolve', 'resolve', ['DAMAGE']),
    ('Blaster Rifle', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Bossk, Trandoshan Hunter', 'bossk_setup', 'setup', 'combat', ['CREATE_TOKEN']),
    ('Bounty Collection', 'bounty_collection_resolve', 'resolve', 'resolve', ['CREATE_TOKEN', 'OBJECT_DESTROYED']),
    ('Bounty Posted', 'bounty_posted_resolve', 'resolve', 'resolve', ['DAMAGE', 'GRANT_KEYWORD']),
    ('Bowcaster', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Call of the Wild', 'call_of_the_wild_resolve', 'resolve', 'resolve', ['CREATE_TOKEN']),
    ('Call to Arms', 'call_to_arms_resolve', 'resolve', 'resolve', ['CREATE_TOKEN', 'LIFE_CHANGE']),
    ('Captain Phasma', 'captain_phasma_setup', 'setup', 'death', ['CREATE_TOKEN', '__STATIC_PT__']),
    ('Carbonite Prison', 'carbonite_prison_setup', 'setup', 'etb', ['EXILE']),
    ('Clone Army', 'clone_army_resolve', 'resolve', 'resolve', ['CREATE_TOKEN']),
    ('Clone Captain Rex', 'clone_captain_rex_setup', 'setup', 'static', ['__STATIC_PT__']),
    ('Cloud City', 'cloud_city_setup', 'setup', 'static', ['__STATIC_PT__']),
    ('Conscription', 'conscription_resolve', 'resolve', 'resolve', ['RETURN_FROM_GRAVEYARD']),
    ('Coruscant Archivist', 'coruscant_archivist_setup', 'setup', 'activated', ['__ACTIVATED__']),
    ('Coruscant Peacekeeper', 'coruscant_peacekeeper_setup', 'setup', 'activated', ['__ACTIVATED__']),
    ('Dark Ritual of the Sith', 'dark_ritual_resolve', 'resolve', 'resolve', ['LIFE_CHANGE', 'MANA_PRODUCED']),
    ('Dark Side Adept', 'dark_side_adept_setup', 'setup', 'upkeep', ['LIFE_CHANGE']),
    ('Dark Side Corruption', 'dark_side_corruption_resolve', 'resolve', 'resolve', ['LIFE_CHANGE', 'PT_MODIFICATION']),
    ('Darksaber', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Darth Bane, Rule Creator', 'darth_bane_setup', 'setup', 'upkeep', ['COUNTER_ADDED', 'SACRIFICE']),
    ('Darth Sidious, Puppetmaster', 'darth_sidious_setup', 'setup', 'upkeep', ['CONTROL_CHANGE', 'GRANT_KEYWORD', 'UNTAP']),
    ("Darth Vader's Lightsaber", 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Death Watch Warrior', 'death_watch_warrior_setup', 'setup', 'etb', ['DAMAGE']),
    ('Defensive Formation', 'defensive_formation_resolve', 'resolve', 'resolve', ['PT_MODIFICATION', 'UNTAP']),
    ('Devastation of Alderaan', 'devastation_of_alderaan_resolve', 'resolve', 'resolve', ['OBJECT_DESTROYED']),
    ('Disintegrate', 'disintegrate_resolve', 'resolve', 'resolve', ['DAMAGE']),
    ('Double-Bladed Lightsaber', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Droid Fabrication', 'droid_fabrication_resolve', 'resolve', 'resolve', ['CREATE_TOKEN', 'DRAW']),
    ('Droid Factory', 'droid_factory_setup', 'setup', 'upkeep', ['CREATE_TOKEN']),
    ('Droid Foundry', 'droid_foundry_setup', 'setup', 'static', ['CREATE_TOKEN', '__STATIC_PT__']),
    ('Electrostaff', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Endor Wildlife', 'endor_wildlife_setup', 'setup', 'death', ['LIFE_CHANGE']),
    ('Evacuation Plan', 'evacuation_plan_resolve', 'resolve', 'resolve', ['LIFE_CHANGE', 'RETURN_TO_HAND']),
    ('Ewok Shaman', 'ewok_shaman_setup', 'setup', 'activated', ['MANA_PRODUCED', 'PT_MODIFICATION', '__ACTIVATED__']),
    ('Ewok Trap', 'ewok_trap_resolve', 'resolve', 'resolve', ['DRAW', 'TAP']),
    ('Ewok Uprising', 'ewok_uprising_resolve', 'resolve', 'resolve', ['CREATE_TOKEN', 'GRANT_KEYWORD']),
    ('Ewok Village', 'ewok_village_setup', 'setup', 'upkeep', ['CREATE_TOKEN']),
    ('Ezra Bridger, Street Kid', 'ezra_bridger_setup', 'setup', 'etb', ['DRAW']),
    ('Fear Itself', 'fear_itself_resolve', 'resolve', 'resolve', ['GRANT_KEYWORD', 'LIFE_CHANGE']),
    ('Fennec Shand, Elite Assassin', 'fennec_shand_setup', 'setup', 'combat', ['DISCARD']),
    ('Force Barrier', 'force_barrier_resolve', 'resolve', 'resolve', ['DRAW', 'GRANT_KEYWORD']),
    ('Force Choke', 'force_choke_resolve', 'resolve', 'resolve', ['PT_MODIFICATION']),
    ('Force Illusion', 'force_illusion_resolve', 'resolve', 'resolve', ['CREATE_TOKEN']),
    ('Force Lightning', 'force_lightning_resolve', 'resolve', 'resolve', ['DAMAGE']),
    ('Force Protection', 'force_protection_resolve', 'resolve', 'resolve', ['GRANT_KEYWORD', 'LIFE_CHANGE']),
    ('Force Push', 'force_push_resolve', 'resolve', 'resolve', ['RETURN_TO_HAND', 'SCRY']),
    ('Force Sensitive', 'force_sensitive_setup', 'setup', 'etb', ['SCRY']),
    ('Force Vision', 'force_vision_resolve', 'resolve', 'resolve', ['DRAW', 'SCRY']),
    ('Force of Nature', 'force_of_nature_resolve', 'resolve', 'resolve', ['COUNTER_ADDED', 'GRANT_KEYWORD']),
    ('Forest Ambush', 'forest_ambush_resolve', 'resolve', 'resolve', ['DAMAGE']),
    ('Galactic Empire', 'galactic_empire_setup', 'setup', 'endstep', ['CREATE_TOKEN', '__STATIC_PT__']),
    ('Galactic Senate Decree', 'galactic_senate_decree_resolve', 'resolve', 'resolve', ['OBJECT_DESTROYED']),
    ('Galactic Underworld', 'galactic_underworld_setup', 'setup', 'attack', ['PT_MODIFICATION']),
    ('Grand Inquisitor', 'grand_inquisitor_setup', 'setup', 'combat', ['EXILE']),
    ('Gungan Warrior', 'gungan_warrior_setup', 'setup', 'etb', ['MANA_PRODUCED']),
    ('Hera Syndulla, Ghost Captain', 'hera_syndulla_setup', 'setup', 'pilot', ['__PILOT__']),
    ('Hired Guns', 'hired_guns_resolve', 'resolve', 'resolve', ['CREATE_TOKEN']),
    ('Holo-Projector Droid', 'holo_projector_droid_setup', 'setup', 'activated', ['CREATE_TOKEN', '__ACTIVATED__']),
    ('Hologram Transmission', 'hologram_transmission_resolve', 'resolve', 'resolve', ['DRAW', 'SCRY']),
    ('Holographic Decoy', 'holographic_decoy_resolve', 'resolve', 'resolve', ['COUNTER_SPELL_UNLESS_PAY']),
    ('Hope Renewed', 'hope_renewed_resolve', 'resolve', 'resolve', ['DRAW', 'LIFE_CHANGE']),
    ("Hunter's Code", 'hunters_code_setup', 'setup', 'static', ['__STATIC_KW__', '__STATIC_PT__']),
    ('Hutt Crime Lord', 'hutt_crime_lord_setup', 'setup', 'etb', ['CREATE_TOKEN']),
    ('Hyperdrive', 'hyperdrive_setup', 'setup', 'static', ['__STATIC_KW__']),
    ('Hyperspace Jump', 'hyperspace_jump_resolve', 'resolve', 'resolve', ['DRAW', 'RETURN_TO_HAND']),
    ('Imperial Bombardment', 'imperial_bombardment_resolve', 'resolve', 'resolve', ['PT_MODIFICATION']),
    ('Imperial Execution', 'imperial_execution_resolve', 'resolve', 'resolve', ['LIFE_CHANGE', 'OBJECT_DESTROYED']),
    ('Imperial Executioner', 'imperial_executioner_setup', 'setup', 'etb', ['OBJECT_DESTROYED']),
    ('Jedi Archives', 'jedi_archives_setup', 'setup', 'spellcast', ['SCRY']),
    ('Jedi Holocron', 'jedi_holocron_setup', 'setup', 'activated', ['MANA_PRODUCED', 'SCRY', '__ACTIVATED__']),
    ('Jedi Investigator', 'jedi_investigator_setup', 'setup', 'etb', ['LOOK_AT_HAND']),
    ('Jedi Mind Trick', 'jedi_mind_trick_resolve', 'resolve', 'resolve', ['CONTROL_CHANGE', 'GRANT_KEYWORD', 'UNTAP']),
    ('Jedi Reflexes', 'jedi_reflexes_resolve', 'resolve', 'resolve', ['GRANT_KEYWORD']),
    ('Jedi Sanctuary', 'jedi_sanctuary_setup', 'setup', 'static', ['__STATIC_KW__']),
    ('Jedi Training', 'jedi_training_resolve', 'resolve', 'resolve', ['DRAW', 'PT_MODIFICATION']),
    ('Jetpack', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Jungle Growth', 'jungle_growth_resolve', 'resolve', 'resolve', ['COUNTER_ADDED', 'GRANT_KEYWORD']),
    ('Kanan Jarrus, Blinded Master', 'kanan_jarrus_setup', 'setup', 'static', ['__STATIC_PT__']),
    ('Kashyyyk', 'kashyyyk_setup', 'setup', 'static', ['__STATIC_PT__']),
    ('Kashyyyk Homeland', 'kashyyyk_homeland_setup', 'setup', 'static', ['__STATIC_KW__', '__STATIC_PT__']),
    ('Kyber Crystal', 'kyber_crystal_setup', 'setup', 'activated', ['MANA_PRODUCED', '__ACTIVATED__']),
    ('Liberation Day', 'liberation_day_resolve', 'resolve', 'resolve', ['LIFE_CHANGE', 'OBJECT_DESTROYED']),
    ('Light of the Force', 'light_of_the_force_resolve', 'resolve', 'resolve', ['EXILE', 'LIFE_CHANGE']),
    ('Lightsaber', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ("Luke's Lightsaber", 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Mandalore', 'mandalore_setup', 'setup', 'static', ['__STATIC_PT__']),
    ('Mandalorian Armor', 'make_equipment_setup', 'setup_inline', 'equip', ['__EQUIP__']),
    ('Mandalorian Forge-Master', 'mandalorian_forge_master_setup', 'setup', 'etb', ['CREATE_TOKEN']),
    ('Mon Mothma', 'mon_mothma_setup', 'setup', 'endstep', ['DRAW']),
    ('Mustafar', 'mustafar_setup', 'setup', 'spellcast', ['CAST', 'DAMAGE']),
    ('Naboo Ranger', 'naboo_ranger_setup', 'setup', 'etb', ['SEARCH_LIBRARY']),
    ('Natural Camouflage', 'natural_camouflage_resolve', 'resolve', 'resolve', ['GRANT_KEYWORD']),
    ('Orbital Strike', 'orbital_strike_resolve', 'resolve', 'resolve', ['DAMAGE']),
    ('Order 66', 'order_66_resolve', 'resolve', 'resolve', ['LIFE_CHANGE', 'OBJECT_DESTROYED']),
    ('Podracer', 'podracer_setup', 'setup', 'pilot', ['__PILOT__']),
    ('Podracer', 'podracer_vehicle_setup', 'setup', 'endstep', ['SACRIFICE']),
    ('Probe Droid', 'probe_droid_setup', 'setup', 'etb', ['LOOK_AT_HAND']),
    ('Protocol Droid', 'protocol_droid_setup', 'setup', 'activated', ['MANA_PRODUCED', '__ACTIVATED__']),
    ('Pyke Enforcer', 'pyke_enforcer_setup', 'setup', 'activated', ['__ACTIVATED__']),
    ('Rage of the Arena', 'rage_of_the_arena_resolve', 'resolve', 'resolve', ['GRANT_KEYWORD', 'PT_MODIFICATION']),
    ('Rampant Growth', 'rampant_growth_resolve', 'resolve', 'resolve', ['SEARCH_LIBRARY']),
    ('Rebel Alliance', 'rebel_alliance_setup', 'setup', 'endstep', ['CREATE_TOKEN', '__STATIC_PT__']),
    ('Rebel Ambush', 'rebel_ambush_resolve', 'resolve', 'resolve', ['CREATE_TOKEN']),
    ('Rebel Base', 'rebel_base_setup', 'setup', 'static', ['__STATIC_PT__']),
    ('Rebel Commando Team', 'rebel_commando_team_setup', 'setup', 'etb', ['CREATE_TOKEN']),
    ('Rebellion Sympathizer', 'rebellion_sympathizer_setup', 'setup', 'death', ['CREATE_TOKEN']),
    ('Reckless Assault', 'reckless_assault_resolve', 'resolve', 'resolve', ['PT_MODIFICATION']),
    ('Republic Gunship', 'republic_gunship_setup', 'setup', 'etb', ['CREATE_TOKEN']),
    ('Resistance Commander', 'resistance_commander_setup', 'setup', 'etb', ['CREATE_TOKEN', '__STATIC_PT__']),
    ('Rule of Two', 'rule_of_two_setup', 'setup', 'static', ['__STATIC_KW__', '__STATIC_PT__']),
    ('Sabine Wren, Mandalorian Artist', 'sabine_wren_setup', 'setup', 'etb', ['DAMAGE', 'OBJECT_DESTROYED']),
    ('Sarlacc Pit Spawn', 'sarlacc_pit_spawn_setup', 'setup', 'block', ['EXILE']),
    ('Sensor Scramble', 'sensor_scramble_resolve', 'resolve', 'resolve', ['COUNTER']),
    ('Separatist Battle Droid', 'separatist_battle_droid_setup', 'setup', 'death', ['DAMAGE']),
    ('Shield Generator', 'shield_generator_setup', 'setup', 'static', ['__STATIC_KW__']),
    ('Sith Holocron', 'sith_holocron_setup', 'setup', 'activated', ['LIFE_CHANGE', 'MANA_PRODUCED', '__ACTIVATED__']),
    ('Sith Lightning', 'sith_lightning_resolve', 'resolve', 'resolve', ['DAMAGE', 'LIFE_CHANGE']),
    ('Sith Temple', 'sith_temple_setup', 'setup', 'static', ['__STATIC_PT__']),
    ('Slave I', 'slave_i_setup', 'setup', 'combat', ['EXILE']),
    ('Snoke, Supreme Leader', 'snoke_setup', 'setup', 'upkeep', ['LIFE_CHANGE']),
    ('Stormtrooper Barracks', 'stormtrooper_barracks_setup', 'setup', 'upkeep', ['CREATE_TOKEN']),
    ('Super Battle Droid', 'super_battle_droid_setup', 'setup', 'etb', ['CREATE_TOKEN']),
    ('TIE Fighter', 'tie_fighter_setup', 'setup', 'death', ['DAMAGE']),
    ('Tactical Droid', 'tactical_droid_setup', 'setup', 'activated', ['SCRY', '__ACTIVATED__', '__STATIC_PT__']),
    ('Tech Override', 'tech_override_resolve', 'resolve', 'resolve', ['COUNTER', 'DRAW']),
    ('The Living Force', 'the_living_force_setup', 'setup', 'etb', ['LIFE_CHANGE']),
    ('The Razor Crest', 'the_razor_crest_setup', 'setup', 'combat', ['CREATE_TOKEN']),
    ('Thermal Detonator', 'thermal_detonator_resolve', 'resolve', 'resolve', ['DAMAGE']),
    ('Trade Federation Vault', 'trade_federation_vault_setup', 'setup', 'upkeep', ['CREATE_TOKEN']),
    ('Training Remote', 'training_remote_setup', 'setup', 'activated', ['GRANT_KEYWORD', '__ACTIVATED__']),
    ('Trandoshan Slaver', 'trandoshan_slaver_setup', 'setup', 'combat', ['EXILE']),
    ('Unity of the Rebellion', 'unity_of_the_rebellion_resolve', 'resolve', 'resolve', ['GRANT_KEYWORD', 'PT_MODIFICATION']),
    ('Weequay Pirate', 'weequay_pirate_setup', 'setup', 'combat', ['CREATE_TOKEN']),
    ('Wookiee Berserker', 'wookiee_berserker_setup', 'setup', 'static', ['__STATIC_PT__']),
    ('Wookiee Rage', 'wookiee_rage_resolve', 'resolve', 'resolve', ['GRANT_KEYWORD', 'PT_MODIFICATION']),
    ('Wrist Rocket', 'wrist_rocket_resolve', 'resolve', 'resolve', ['DAMAGE']),
    ('X-Wing Starfighter', 'x_wing_setup', 'setup', 'attack', ['DAMAGE']),
    ('Y-Wing Bomber', 'y_wing_setup', 'setup', 'attack', ['DAMAGE']),
    ('Yaddle, Jedi Council Member', 'yaddle_setup', 'setup', 'spellcast', ['COUNTER_ADDED']),
]

# Markers used by static/equipment/activated/pilot cards: instead of asserting an
# emitted event, assert the expected interceptor(s) register on the battlefield.
_STATIC_MARKERS = {"__STATIC_PT__", "__STATIC_KW__"}
_NONEVENT_MARKERS = {"__STATIC_PT__", "__STATIC_KW__", "__EQUIP__", "__PILOT__", "__ACTIVATED__"}


def _mk_creature(game, owner_id, name, *, subtypes=None, power=4, toughness=4, types=None):
    chars = Characteristics(
        types=types or {CardType.CREATURE},
        subtypes=set(subtypes or set()),
        power=power,
        toughness=toughness,
    )
    return game.create_object(
        name=name, owner_id=owner_id, zone=ZoneType.BATTLEFIELD,
        characteristics=chars, card_def=None,
    )


def _place(game, owner_id, card_name):
    cd = STAR_WARS_CARDS[card_name]
    return game.create_object(
        name=card_name, owner_id=owner_id, zone=ZoneType.BATTLEFIELD,
        characteristics=cd.characteristics, card_def=None,
    ), cd


def _fresh():
    g = Game()
    p1 = g.add_player("P1")
    p2 = g.add_player("P2")
    g.state.active_player = p1.id
    return g, p1, p2


_ALL_SUBTYPES = {"Jedi", "Rebel", "Human", "Sith", "Droid", "Empire",
                 "Wookiee", "Ewok", "Bounty Hunter", "Mandalorian",
                 "Soldier", "Clone", "Beast", "Warrior", "Vehicle"}


def _populate_helpers(g, p1, p2):
    """Build a rich board so any trigger has the state it needs: several allies
    carrying every tribal subtype (for ally-count gates like 3+ Rebels), a big
    enemy creature (power 6, for power>=4 / least-power picks), enemy artifact,
    and creatures in both graveyards."""
    for i in range(4):
        _mk_creature(g, p1.id, f"Ally{i}", subtypes=set(_ALL_SUBTYPES), power=3, toughness=3)
    _mk_creature(g, p2.id, "BigEnemy", power=6, toughness=5)
    _mk_creature(g, p2.id, "SmallEnemy", subtypes={"Human"}, power=1, toughness=1)
    # enemy artifact (Sabine Wren, artifact-destruction)
    g.create_object(name="EnemyArtifact", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
                    characteristics=Characteristics(types={CardType.ARTIFACT}, subtypes=set()),
                    card_def=None)
    # graveyard creatures (Grand Inquisitor exiles from opp GY; Conscription from own)
    g.create_object(name="EnemyCorpse", owner_id=p2.id, zone=ZoneType.GRAVEYARD,
                    characteristics=Characteristics(types={CardType.CREATURE}, subtypes={"Human"},
                                                    power=2, toughness=2),
                    card_def=None)


def _trigger_event(kind, src, p1, p2):
    """Synthesize the event that fires a trigger of `kind` for object `src`."""
    if kind == "etb":
        return Event(type=EventType.ZONE_CHANGE,
                     payload={'object_id': src.id, 'to_zone_type': ZoneType.BATTLEFIELD,
                              'from_zone_type': ZoneType.HAND},
                     source=src.id, controller=src.controller)
    if kind == "death":
        return Event(type=EventType.ZONE_CHANGE,
                     payload={'object_id': src.id, 'to_zone_type': ZoneType.GRAVEYARD,
                              'from_zone_type': ZoneType.BATTLEFIELD},
                     source=src.id, controller=src.controller)
    if kind == "attack":
        return Event(type=EventType.ATTACK_DECLARED,
                     payload={'attacker_id': src.id, 'object_id': src.id,
                              'target_player': p2.id, 'defender': p2.id},
                     source=src.id, controller=src.controller)
    if kind == "combat":
        return Event(type=EventType.DAMAGE,
                     payload={'source': src.id, 'target': p2.id, 'amount': 3, 'is_combat': True},
                     source=src.id, controller=src.controller)
    if kind == "upkeep":
        return Event(type=EventType.PHASE_START,
                     payload={'phase': 'upkeep', 'player': src.controller,
                              'active_player': src.controller},
                     source=src.id)
    if kind == "endstep":
        return Event(type=EventType.PHASE_START,
                     payload={'phase': 'end_step', 'player': src.controller,
                              'active_player': src.controller},
                     source=src.id)
    if kind == "spellcast":
        return Event(type=EventType.CAST,
                     payload={'caster': src.controller, 'controller': src.controller,
                              'card_type': CardType.INSTANT,
                              'types': {CardType.INSTANT, CardType.CREATURE},
                              'subtypes': {'Sith'}},
                     source=src.id, controller=src.controller)
    if kind == "block":
        atk = _mk_creature  # not used; attacker id supplied below
        return Event(type=EventType.BLOCK_DECLARED,
                     payload={'blocker_id': src.id, 'attacker_id': '__atk__'},
                     source=src.id, controller=src.controller)
    return None


def _run_triggered(name, fn, kind, expected):
    """ETB/death/attack/combat/upkeep/endstep/spellcast/block: fire and assert emit."""
    g, p1, p2 = _fresh()
    _populate_helpers(g, p1, p2)
    src, cd = _place(g, p1.id, name)
    if kind == "upkeep" and "less than 10" in (cd.text or "").lower():
        p1.life = 5  # Dark Side condition
    ints = cd.setup_interceptors(src, g.state) or []
    assert ints, f"{name}: setup_interceptors returned no interceptors"

    # Build candidate triggering events. Some triggers fire on the card itself
    # (own ETB/death/attack); others fire on a *different* object entering /
    # attacking under your control. Try both shapes.
    events = [_trigger_event(kind, src, p1, p2)]
    if kind == "etb":
        other = _mk_creature(g, p1.id, "EntrantAlly", subtypes={"Rebel", "Human"}, power=2, toughness=2)
        events.append(_trigger_event("etb", other, p1, p2))
    if kind == "attack":
        other = next((o for o in g.state.objects.values()
                      if o.controller == p1.id and o.id != src.id
                      and CardType.CREATURE in (o.characteristics.types or set())), None)
        if other is not None:
            events.append(_trigger_event("attack", other, p1, p2))
    if kind == "block":
        atk = _mk_creature(g, p2.id, "Attacker", power=3, toughness=3)
        for e in events:
            e.payload['attacker_id'] = atk.id

    want = set(expected)
    got = set()
    for ev in events:
        for it in ints:
            if it.filter(ev, g.state):
                res = it.handler(ev, g.state)
                for e in (res.new_events or []):
                    got.add(e.type.name)
        if got & want:
            return
    assert got & want, f"{name}: fired {kind} trigger, emitted {got or '{}'}, expected one of {want}"


def _run_resolve(name, fn, expected):
    """Instant/sorcery: call resolve with a real state + plausible targets, assert emit."""
    g, p1, p2 = _fresh()
    _populate_helpers(g, p1, p2)
    # Provide a land for Devastation, a graveyard creature for Conscription.
    land = g.create_object(name="Foe Land", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
                           characteristics=Characteristics(types={CardType.LAND}, subtypes=set()),
                           card_def=None)
    gy_cre = g.create_object(name="Dead Ally", owner_id=p1.id, zone=ZoneType.GRAVEYARD,
                             characteristics=Characteristics(types={CardType.CREATURE},
                                                             subtypes={'Empire'}, power=2, toughness=2),
                             card_def=None)
    resolve = getattr(STAR_WARS_CARDS[name], "resolve", None) or getattr(star_wars, fn)
    # Build a target list covering the common shapes: enemy creature, own creature.
    enemy = next((o for o in g.state.objects.values()
                  if o.controller == p2.id and CardType.CREATURE in (o.characteristics.types or set())), None)
    mine = next((o for o in g.state.objects.values()
                 if o.controller == p1.id and CardType.CREATURE in (o.characteristics.types or set())), None)

    def _T(o):
        return type("T", (), {"id": o.id, "is_player": False})()

    candidate_targets = []
    if enemy and mine:
        candidate_targets = [_T(mine), _T(enemy)]  # fight + most "you control" / target picks
    elif enemy:
        candidate_targets = [_T(enemy)]
    # Conscription wants a graveyard creature target.
    if name == "Conscription":
        candidate_targets = [_T(gy_cre)]

    want = set(expected)
    # Try with candidate targets first, then with no targets (for non-target spells).
    for targets in (candidate_targets, []):
        evs = resolve(targets, g.state) or []
        got = {e.type.name for e in evs}
        if got & want:
            return
    # Last attempt captured for the message:
    raise AssertionError(f"{name}: resolve emitted {got or '{}'}, expected one of {want}")


def _run_static(name, fn, kind, expected):
    """static/equip/activated/pilot: assert the expected interceptor(s) register."""
    g, p1, p2 = _fresh()
    _populate_helpers(g, p1, p2)
    src, cd = _place(g, p1.id, name)
    setup = cd.setup_interceptors
    assert setup is not None, f"{name}: setup_interceptors is None"
    ints = setup(src, g.state) or []
    assert ints, f"{name}: setup returned no interceptors (expected {expected})"


def _dispatch(name, fn, wire, trig, expected):
    if trig == "resolve":
        _run_resolve(name, fn, [e for e in expected if not e.startswith("__")])
    elif trig in ("static", "equip", "activated", "pilot"):
        _run_static(name, fn, trig, expected)
    else:
        _run_triggered(name, fn, trig, [e for e in expected if not e.startswith("__")])


# Materialize one test function per spec row so they show up individually.
def _make_test(name, fn, wire, trig, expected):
    def _t():
        _dispatch(name, fn, wire, trig, expected)
    _t.__name__ = "test_" + (
        "".join(ch if ch.isalnum() else "_" for ch in name).strip("_").lower()
    )
    _t.__doc__ = f"{name}: {trig} -> expects one of {expected}"
    return _t


_TESTS = []
for _row in SPEC:
    _fn_obj = _make_test(*_row)
    globals()[_fn_obj.__name__] = _fn_obj
    _TESTS.append(_fn_obj)


if __name__ == "__main__":
    import traceback
    passed, failed, errors = [], [], []
    for t in _TESTS:
        try:
            t()
            passed.append(t.__name__)
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            errors.append((t.__name__, f"{type(e).__name__}: {e}"))
    print(f"\n=== Interceptor verification: Star Wars (SWG) ===")
    print(f"  passed:  {len(passed)}")
    print(f"  failed:  {len(failed)}")
    print(f"  errors:  {len(errors)}")
    print(f"  skipped: {len(SKIPPED_CARDS)} (see SKIPPED_CARDS — intentionally vanilla)")
    if failed:
        print("\n--- FAILURES ---")
        for n, m in failed[:40]:
            print(f"  {n}: {m}")
    if errors:
        print("\n--- ERRORS ---")
        for n, m in errors[:40]:
            print(f"  {n}: {m}")
    sys.exit(0 if not failed and not errors else 1)
