"""Auto-generated interceptor verification for Dragon Ball Z (DBZ).

See /test-interceptors. Each test fires the trigger the card's rules text
implies and asserts the matching effect EventType is emitted (or, for
static/aura/equipment/activated cards, that the setup registers >=1
interceptor). Catches the "interceptor wired but effect_fn returns []"
depths bug and slice-style info-pulse stubs.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python tests/test_dragon_ball_interceptors.py
"""

import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

from src.engine import Game, Event, EventType, ZoneType
from src.engine.stack import Target
from src.cards.custom.dragon_ball import DRAGON_BALL_CARDS


# Cards that need multi-card / non-trivial setup beyond this harness, with reasons.
SKIPPED_CARDS = {
    "Ginyu Force, Assemble!": "library tutor needs full turn/library context; resolve returns [] in isolated harness",
    "Eternal Dragon's Wish": "Dragon Ball tutor / win-con needs full battlefield+library context",
}


# --------------------------------------------------------------------------- #
# Scaffolding
# --------------------------------------------------------------------------- #

def _make_game():
    g = Game()
    p1 = g.add_player("P1")
    p2 = g.add_player("P2")
    g.state.active_player = p1.id
    return g, p1, p2


def _place(g, owner, name, zone=ZoneType.BATTLEFIELD):
    cd = DRAGON_BALL_CARDS[name]
    o = g.create_object(name=name, owner_id=owner.id, zone=zone,
                        characteristics=cd.characteristics, card_def=cd)
    o.state.summoning_sickness = False
    o.state.tapped = False
    return o, cd


def _types(events):
    return [e.type.name for e in events]


def _fire_etb(g, o):
    return g.emit(Event(type=EventType.ZONE_CHANGE,
        payload={"object_id": o.id, "to_zone_type": ZoneType.BATTLEFIELD,
                 "from_zone_type": ZoneType.HAND},
        source=o.id, controller=o.controller))


def _fire_death(g, o):
    return g.emit(Event(type=EventType.ZONE_CHANGE,
        payload={"object_id": o.id, "from_zone_type": ZoneType.BATTLEFIELD,
                 "to_zone_type": ZoneType.GRAVEYARD},
        source=o.id, controller=o.controller))


def _fire_attack(g, o):
    o.state.attacking = True
    return g.emit(Event(type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": o.id}, source=o.id, controller=o.controller))


def _fire_upkeep(g, player):
    return g.emit(Event(type=EventType.PHASE_START,
        payload={"phase": "upkeep", "player": player.id},
        source=None, controller=player.id))


def _fire_end_step(g, player):
    return g.emit(Event(type=EventType.PHASE_START,
        payload={"phase": "end_step", "player": player.id},
        source=None, controller=player.id))


def _fire_damage_dealt(g, o, victim):
    return g.emit(Event(type=EventType.DAMAGE,
        payload={"source": o.id, "target": victim.id, "amount": 3, "is_combat": True},
        source=o.id, controller=o.controller))


def _register_count(g, owner, name):
    """Run setup_interceptors directly and count returned interceptors."""
    cd = DRAGON_BALL_CARDS[name]
    o = g.create_object(name=name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
                        characteristics=cd.characteristics, card_def=None)
    itcs = cd.setup_interceptors(o, g.state) if cd.setup_interceptors else []
    return itcs


def _activated_abilities(g, owner, name):
    """Place card (running setup) and return its registered activated abilities."""
    o, _ = _place(g, owner, name)
    return list(getattr(o.state, "activated_abilities", []) or [])


def _assert_has(events, et_name, card):
    names = _types(events)
    assert et_name in names, f"{card}: expected {et_name}, got {names}"



# --------------------------------------------------------------------------- #
# Per-card tests
# --------------------------------------------------------------------------- #

def test_absorption():
    """ABSORPTION: RESOLVE_DESTROY"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Absorption"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "OBJECT_DESTROYED", "ABSORPTION")

def test_android_16():
    """ANDROID_16: DEATH"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Android 16, Gentle Giant")
    _place(g, p2, "Zarbon, Frieza's Elite")
    evs = _fire_death(g, o)
    _assert_has(evs, "DAMAGE", "ANDROID_16")

def test_android_17():
    """ANDROID_17: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Android 17, Nature's Protector")
    assert len(itcs) >= 1, f"ANDROID_17: setup registered no interceptors"

def test_android_18():
    """ANDROID_18: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Android 18, Infinite Energy")
    evs = _fire_etb(g, o)
    _assert_has(evs, "DRAW", "ANDROID_18")

def test_bardock_father_of_saiyans():
    """BARDOCK_FATHER_OF_SAIYANS: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Bardock, Father of Saiyans")
    evs = _fire_etb(g, o)
    _assert_has(evs, "SCRY", "BARDOCK_FATHER_OF_SAIYANS")

def test_beerus():
    """BEERUS: UPKEEP"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Beerus, God of Destruction")
    _place(g, p2, "Zarbon, Frieza's Elite")
    evs = _fire_upkeep(g, p1)
    _assert_has(evs, "OBJECT_DESTROYED", "BEERUS")

def test_big_bang_attack():
    """BIG_BANG_ATTACK: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Big Bang Attack"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "BIG_BANG_ATTACK")

def test_broly_legendary():
    """BROLY_LEGENDARY: ATTACK"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Broly, Legendary Super Saiyan")
    _place(g, p2, "Zarbon, Frieza's Elite")
    evs = _fire_attack(g, o)
    _assert_has(evs, "COUNTER_ADDED", "BROLY_LEGENDARY")

def test_bulma_genius_inventor():
    """BULMA_GENIUS_INVENTOR: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Bulma, Genius Inventor")
    assert len(itcs) >= 1, f"BULMA_GENIUS_INVENTOR: setup registered no interceptors"

def test_burning_attack():
    """BURNING_ATTACK: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Burning Attack"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "BURNING_ATTACK")

def test_cell_perfect_form():
    """CELL_PERFECT_FORM: DEATH_OTHER"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Cell, Perfect Form")
    ally, _ = _place(g, p1, "Zarbon, Frieza's Elite")
    evs = _fire_death(g, ally)
    _assert_has(evs, "COUNTER_ADDED", "CELL_PERFECT_FORM")

def test_death_ball():
    """DEATH_BALL: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Death Ball"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "DEATH_BALL")

def test_death_beam():
    """DEATH_BEAM: RESOLVE_DESTROY"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Death Beam"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "OBJECT_DESTROYED", "DEATH_BEAM")

def test_dende():
    """DENDE: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Dende, Young Healer")
    assert len(itcs) >= 1, f"DENDE: setup registered no interceptors"

def test_destructo_disc():
    """DESTRUCTO_DISC: RESOLVE_DESTROY"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Destructo Disc"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "OBJECT_DESTROYED", "DESTRUCTO_DISC")

def test_dr_brief():
    """DR_BRIEF: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Dr. Brief, Capsule Corp Founder")
    assert len(itcs) >= 1, f"DR_BRIEF: setup registered no interceptors"

def test_eraser_cannon():
    """ERASER_CANNON: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Eraser Cannon"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "ERASER_CANNON")

def test_final_flash():
    """FINAL_FLASH: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Final Flash"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "FINAL_FLASH")

def test_frieza_emperor():
    """FRIEZA_EMPEROR: DAMAGE_DEALT"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Frieza, Galactic Emperor")
    victim, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    evs = _fire_damage_dealt(g, o, victim)
    assert len(evs) > 1, f"FRIEZA_EMPEROR produced no trigger events: {_types(evs)}"

def test_frieza_force():
    """FRIEZA_FORCE: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Frieza Force")
    assert len(itcs) >= 1, f"FRIEZA_FORCE: setup registered no interceptors"

def test_future_sword():
    """FUTURE_SWORD: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Future Sword")
    assert len(itcs) >= 1, f"FUTURE_SWORD: setup registered no interceptors"

def test_future_trunks_tomorrow():
    """FUTURE_TRUNKS_TOMORROW: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Future Trunks, Tomorrow's Hope")
    evs = _fire_etb(g, o)
    _assert_has(evs, "SEARCH_LIBRARY", "FUTURE_TRUNKS_TOMORROW")

def test_galick_gun():
    """GALICK_GUN: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Galick Gun"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "GALICK_GUN")

def test_gogeta():
    """GOGETA: ATTACK"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Gogeta, Fusion Warrior")
    _place(g, p2, "Zarbon, Frieza's Elite")
    evs = _fire_attack(g, o)
    _assert_has(evs, "DAMAGE", "GOGETA")

def test_gohan_hidden_power():
    """GOHAN_HIDDEN_POWER: DEATH_OTHER"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Gohan, Hidden Power")
    ally, _ = _place(g, p1, "Zarbon, Frieza's Elite")
    evs = _fire_death(g, ally)
    _assert_has(evs, "COUNTER_ADDED", "GOHAN_HIDDEN_POWER")

def test_goku_earths_hero():
    """GOKU_EARTHS_HERO: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Goku, Earth's Hero")
    assert len(itcs) >= 1, f"GOKU_EARTHS_HERO: setup registered no interceptors"

def test_goku_pure_of_heart():
    """GOKU_PURE_OF_HEART: ATTACK"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Goku, Pure of Heart")
    _place(g, p2, "Zarbon, Frieza's Elite")
    evs = _fire_attack(g, o)
    _assert_has(evs, "COUNTER_ADDED", "GOKU_PURE_OF_HEART")

def test_goku_ultra_instinct_sign():
    """GOKU_ULTRA_INSTINCT_SIGN: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Goku, Ultra Instinct Sign")
    assert len(itcs) >= 1, f"GOKU_ULTRA_INSTINCT_SIGN: setup registered no interceptors"

def test_goten():
    """GOTEN: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Goten, Cheerful Saiyan")
    evs = _fire_etb(g, o)
    _assert_has(evs, "DAMAGE", "GOTEN")

def test_gotenks():
    """GOTENKS: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Gotenks, Young Fusion")
    evs = _fire_etb(g, o)
    _assert_has(evs, "OBJECT_CREATED", "GOTENKS")

def test_guru():
    """GURU: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Guru, Grand Elder")
    evs = _fire_etb(g, o)
    _assert_has(evs, "COUNTER_ADDED", "GURU")

def test_hit():
    """HIT: DAMAGE_DEALT"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Hit, The Assassin")
    victim, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    evs = _fire_damage_dealt(g, o, victim)
    _assert_has(evs, "TAP", "HIT")

def test_kamehameha():
    """KAMEHAMEHA: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Kamehameha"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "KAMEHAMEHA")

def test_kame_house_masters_refuge():
    """KAME_HOUSE_MASTERS_REFUGE: ACTIVATED"""
    g, p1, p2 = _make_game()
    aas = _activated_abilities(g, p1, "Kame House, Master's Refuge")
    assert len(aas) >= 1, f"KAME_HOUSE_MASTERS_REFUGE: setup registered no activated abilities"

def test_kid_buu():
    """KID_BUU: UPKEEP"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Kid Buu, Pure Destruction")
    evs = _fire_upkeep(g, p1)
    _assert_has(evs, "LIFE_CHANGE", "KID_BUU")

def test_kid_trunks():
    """KID_TRUNKS: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Trunks, Young Fighter")
    assert len(itcs) >= 1, f"KID_TRUNKS: setup registered no interceptors"

def test_king_kai():
    """KING_KAI: UPKEEP"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "King Kai, Martial Arts Master")
    evs = _fire_upkeep(g, p1)
    _assert_has(evs, "DRAW", "KING_KAI")

def test_king_vegeta():
    """KING_VEGETA: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "King Vegeta")
    assert len(itcs) >= 1, f"KING_VEGETA: setup registered no interceptors"

def test_ki_explosion():
    """KI_EXPLOSION: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Ki Explosion"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "KI_EXPLOSION")

def test_krillin_brave_warrior():
    """KRILLIN_BRAVE_WARRIOR: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Krillin, Brave Warrior")
    evs = _fire_etb(g, o)
    _assert_has(evs, "LIFE_CHANGE", "KRILLIN_BRAVE_WARRIOR")

def test_majin_mark():
    """MAJIN_MARK: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Majin Mark")
    assert len(itcs) >= 1, f"MAJIN_MARK: setup registered no interceptors"

def test_masenko():
    """MASENKO: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Masenko"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "MASENKO")

def test_master_roshis_training_hall():
    """MASTER_ROSHIS_TRAINING_HALL: ACTIVATED"""
    g, p1, p2 = _make_game()
    aas = _activated_abilities(g, p1, "Master Roshi's Training Hall")
    assert len(aas) >= 1, f"MASTER_ROSHIS_TRAINING_HALL: setup registered no activated abilities"

def test_nail():
    """NAIL: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Nail, Namekian Elite")
    assert len(itcs) >= 1, f"NAIL: setup registered no interceptors"

def test_namekian_child():
    """NAMEKIAN_CHILD: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Namekian Child")
    evs = _fire_etb(g, o)
    _assert_has(evs, "LIFE_CHANGE", "NAMEKIAN_CHILD")

def test_namekian_resilience():
    """NAMEKIAN_RESILIENCE: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Namekian Resilience")
    assert len(itcs) >= 1, f"NAMEKIAN_RESILIENCE: setup registered no interceptors"

def test_namek_crab():
    """NAMEK_CRAB: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Namek Crab")
    evs = _fire_etb(g, o)
    _assert_has(evs, "LIFE_CHANGE", "NAMEK_CRAB")

def test_namek_frog():
    """NAMEK_FROG: DEATH"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Namek Frog")
    _place(g, p2, "Zarbon, Frieza's Elite")
    evs = _fire_death(g, o)
    _assert_has(evs, "DRAW", "NAMEK_FROG")

def test_omega_blaster():
    """OMEGA_BLASTER: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Omega Blaster"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "OMEGA_BLASTER")

def test_piccolo_namekian_warrior():
    """PICCOLO_NAMEKIAN_WARRIOR: UPKEEP"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Piccolo, Namekian Warrior")
    evs = _fire_upkeep(g, p1)
    _assert_has(evs, "COUNTER_ADDED", "PICCOLO_NAMEKIAN_WARRIOR")

def test_saiyan_pride():
    """SAIYAN_PRIDE: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Saiyan Pride")
    assert len(itcs) >= 1, f"SAIYAN_PRIDE: setup registered no interceptors"

def test_shenron_wish_granter():
    """SHENRON_WISH_GRANTER: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Shenron, Wish Granter")
    evs = _fire_etb(g, o)
    _assert_has(evs, "SCRY", "SHENRON_WISH_GRANTER")

def test_solar_kamehameha():
    """SOLAR_KAMEHAMEHA: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Solar Kamehameha"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "SOLAR_KAMEHAMEHA")

def test_special_beam_cannon():
    """SPECIAL_BEAM_CANNON: RESOLVE_DMG"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Special Beam Cannon"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "DAMAGE", "SPECIAL_BEAM_CANNON")

def test_supernova():
    """SUPERNOVA: RESOLVE_DESTROY"""
    g, p1, p2 = _make_game()
    tgt, _ = _place(g, p2, "Zarbon, Frieza's Elite")
    cd = DRAGON_BALL_CARDS["Supernova"]
    evs = cd.resolve([[Target(tgt.id)]], g.state)
    _assert_has(evs, "OBJECT_DESTROYED", "SUPERNOVA")

def test_super_saiyan_aura():
    """SUPER_SAIYAN_AURA: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Super Saiyan Aura")
    assert len(itcs) >= 1, f"SUPER_SAIYAN_AURA: setup registered no interceptors"

def test_supreme_kai():
    """SUPREME_KAI: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Supreme Kai, Divine Watcher")
    evs = _fire_etb(g, o)
    _assert_has(evs, "ACTIVATE", "SUPREME_KAI")

def test_tien_triclops():
    """TIEN_TRICLOPS: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Tien, Triclops Warrior")
    assert len(itcs) >= 1, f"TIEN_TRICLOPS: setup registered no interceptors"

def test_trunks_sword_of_future():
    """TRUNKS_SWORD_OF_FUTURE: ETB"""
    g, p1, p2 = _make_game()
    o, _ = _place(g, p1, "Trunks, Sword of the Future")
    evs = _fire_etb(g, o)
    _assert_has(evs, "SEARCH_LIBRARY", "TRUNKS_SWORD_OF_FUTURE")

def test_vegeta_saiyan_prince():
    """VEGETA_SAIYAN_PRINCE: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Vegeta, Saiyan Prince")
    assert len(itcs) >= 1, f"VEGETA_SAIYAN_PRINCE: setup registered no interceptors"

def test_vegito():
    """VEGITO: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Vegito, Ultimate Fusion")
    assert len(itcs) >= 1, f"VEGITO: setup registered no interceptors"

def test_videl_hero_in_training():
    """VIDEL_HERO_IN_TRAINING: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Videl, Hero in Training")
    assert len(itcs) >= 1, f"VIDEL_HERO_IN_TRAINING: setup registered no interceptors"

def test_z_fighters_unite():
    """Z_FIGHTERS_UNITE: REGISTER"""
    g, p1, p2 = _make_game()
    itcs = _register_count(g, p1, "Z-Fighters Unite")
    assert len(itcs) >= 1, f"Z_FIGHTERS_UNITE: setup registered no interceptors"


# --------------------------------------------------------------------------- #
# Custom-resolve spells (Phase A/B/v2 designed cards; need zone setup)
# --------------------------------------------------------------------------- #

def test_senzu_bean_reanimator():
    """SENZU_BEAN_REANIMATOR: reanimate creature from graveyard -> RETURN_FROM_GRAVEYARD"""
    g, p1, p2 = _make_game()
    dead, _ = _place(g, p1, "Krillin, Brave Warrior", zone=ZoneType.GRAVEYARD)
    cd = DRAGON_BALL_CARDS["Senzu Bean Reanimator"]
    evs = cd.resolve([dead.id], g.state)
    _assert_has(evs, "RETURN_FROM_GRAVEYARD", "SENZU_BEAN_REANIMATOR")







# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed, failed, errors = [], [], []
    for t in tests:
        try:
            t()
            passed.append(t.__name__)
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            errors.append((t.__name__, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
    print("\n=== Interceptor verification: Dragon Ball Z ===")
    print(f"  passed:  {len(passed)}")
    print(f"  failed:  {len(failed)}")
    print(f"  errors:  {len(errors)}")
    print(f"  skipped: {len(SKIPPED_CARDS)} (see SKIPPED_CARDS)")
    if failed:
        print("\n--- FAILURES ---")
        for name, msg in failed[:40]:
            print(f"  {name}: {msg}")
    if errors:
        print("\n--- ERRORS ---")
        for name, msg in errors[:40]:
            print(f"  {name}: {msg}")
    sys.exit(0 if not failed and not errors else 1)
