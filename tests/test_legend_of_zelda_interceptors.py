"""Interceptor verification for Legend of Zelda (MTG engine). See /test-interceptors.

Focus: the slice-8 retrofit dead-original-clause repair. For equipment/auras we
EQUIP a vanilla creature and assert the restored static (P/T, keywords, subtypes,
granted abilities) actually applies; for artifacts/lands we assert the original
activated ability is registered and its effect_fn emits the right event; for the
info-pulse triggers we fire the trigger and assert the claimed effect emits.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python tests/test_legend_of_zelda_interceptors.py
"""

import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.legend_of_zelda import LEGEND_OF_ZELDA_CARDS
import src.cards.custom.legend_of_zelda as ZLD

SKIPPED_CARDS = {
    # Pre-slice-8 original sorceries with no resolve (out of retrofit scope):
    "Water Temple Flood": "no resolve — pre-existing whole-card stub (2024 commit)",
    "Wisdom of Ages": "no resolve — pre-existing whole-card stub",
    "Darkness Falls": "no resolve — pre-existing whole-card stub",
    "Malice Spread": "no resolve — pre-existing whole-card stub",
    "Ganon's Wrath": "no resolve — pre-existing whole-card stub",
    "Volcanic Eruption": "no resolve — pre-existing whole-card stub",
    "Bomb Barrage": "no resolve — pre-existing whole-card stub",
    "Forest Blessing": "no resolve — pre-existing whole-card stub",
}


# ---- scaffolding ----------------------------------------------------------

def _new_game():
    g = Game()
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob")
    g.state.active_player = p1.id
    return g, p1, p2


def _put_bf(g, card_name, owner):
    """Put a card from hand onto the battlefield via the pipeline (runs setup once)."""
    cd = LEGEND_OF_ZELDA_CARDS[card_name]
    obj = g.create_object(name=card_name, owner_id=owner.id, zone=ZoneType.HAND,
                          characteristics=cd.characteristics, card_def=None)
    obj.card_def = cd
    g.emit(Event(type=EventType.ZONE_CHANGE, payload={
        'object_id': obj.id, 'from_zone': f'hand_{owner.id}',
        'to_zone': 'battlefield', 'to_zone_type': ZoneType.BATTLEFIELD}))
    return obj


def _vanilla(g, owner, name="Vanilla", power=2, toughness=2, subtypes=None):
    return g.create_object(name=name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
                           characteristics=Characteristics(types={CardType.CREATURE},
                               power=power, toughness=toughness,
                               subtypes=set(subtypes or set())), card_def=None)


def _equip(g, equipment, creature):
    g.emit(Event(type=EventType.ATTACH,
                 payload={'object_id': equipment.id, 'target_id': creature.id},
                 source=equipment.id))


def _granted_abilities(creature, equipment_id):
    abils = getattr(creature.state, 'activated_abilities', []) or []
    return [a for a in abils if getattr(a, '_granted_by', None) == equipment_id]


# ---- Equipment statics (dead-original-clause repair) ----------------------
# (name, want_power_delta, want_toughness_delta, keywords, subtypes_added)
_EQUIP_STATICS = [
    ("Kokiri Sword", 1, 1, [], set()),
    ("Bunny Hood", 1, 0, ["haste"], set()),
    ("Biggoron's Sword", 5, 0, ["trample", "cant_block"], set()),
    ("Fierce Deity Mask", 4, 4, ["double_strike"], set()),
    ("Majora's Mask", 3, 3, ["menace"], set()),
    ("Stone Mask", 0, 0, ["hexproof", "cant_attack", "cant_block"], set()),
    ("Goron Mask", 2, 2, ["trample"], {"Goron"}),
    ("Zora Mask", 1, 2, ["unblockable"], {"Zora"}),
    ("Mirror Shield", 1, 2, [], set()),
    ("Hylian Shield", 1, 3, [], set()),  # already-correct reference equipment
    ("Ancient Bow", 1, 1, [], set()),
    ("Hero's Bow", 0, 0, [], set()),
]


def _make_equip_static_test(name, dp, dt, kws, subs):
    def _t():
        g, p1, p2 = _new_game()
        bear = _vanilla(g, p1)
        bp, bt = get_power(bear, g.state), get_toughness(bear, g.state)
        eq = _put_bf(g, name, p1)
        _equip(g, eq, bear)
        np_, nt = get_power(bear, g.state), get_toughness(bear, g.state)
        assert np_ == bp + dp, f"{name}: power {bp}->{np_}, want +{dp}"
        assert nt == bt + dt, f"{name}: toughness {bt}->{nt}, want +{dt}"
        for kw in kws:
            assert has_ability(bear, kw, g.state), f"{name}: missing granted keyword {kw}"
        for s in subs:
            assert s in bear.characteristics.subtypes, f"{name}: missing granted subtype {s}"
    _t.__name__ = f"test_equip_static_{name.lower().replace(' ', '_').replace(chr(39), '')}"
    _t.__doc__ = f"{name}: equip applies +{dp}/+{dt} {kws} {subs}"
    return _t


for _spec in _EQUIP_STATICS:
    _fn = _make_equip_static_test(*_spec)
    globals()[_fn.__name__] = _fn


# ---- Equipment granted activated abilities --------------------------------

def test_equip_granted_heros_bow():
    """Hero's Bow grants the bearer '{T}: deal 2 to flyer'."""
    g, p1, p2 = _new_game()
    bear = _vanilla(g, p1)
    eq = _put_bf(g, "Hero's Bow", p1)
    _equip(g, eq, bear)
    assert _granted_abilities(bear, eq.id), "Hero's Bow: no granted ability on bearer"


def test_equip_granted_ancient_bow():
    """Ancient Bow grants the bearer '{T}: deal 3 to any target'."""
    g, p1, p2 = _new_game()
    bear = _vanilla(g, p1)
    eq = _put_bf(g, "Ancient Bow", p1)
    _equip(g, eq, bear)
    assert _granted_abilities(bear, eq.id), "Ancient Bow: no granted ability on bearer"


def test_equip_granted_deku_mask():
    """Deku Mask grants Plant subtype + '{T}: Add {G}'."""
    g, p1, p2 = _new_game()
    bear = _vanilla(g, p1)
    eq = _put_bf(g, "Deku Mask", p1)
    _equip(g, eq, bear)
    assert "Plant" in bear.characteristics.subtypes, "Deku Mask: missing Plant subtype"
    assert _granted_abilities(bear, eq.id), "Deku Mask: no granted mana ability on bearer"


def test_mirror_shield_reflect():
    """Mirror Shield: damage to bearer -> that source's controller loses that much life."""
    g, p1, p2 = _new_game()
    bear = _vanilla(g, p1)
    enemy = _vanilla(g, p2, name="Enemy")
    eq = _put_bf(g, "Mirror Shield", p1)
    _equip(g, eq, bear)
    before = p2.life
    g.emit(Event(type=EventType.DAMAGE,
                 payload={'target': bear.id, 'amount': 3, 'source': enemy.id}, source=enemy.id))
    assert p2.life == before - 3, f"Mirror Shield reflect: p2 {before}->{p2.life}, want -3"


# ---- Artifact + land activated abilities (dead-original-clause repair) -----
_ACTIVATED_PERMANENTS = [
    "Ocarina of Time", "Sheikah Slate", "Bomb Bag", "Fairy Bottle",
    "Magic Boomerang", "Hookshot", "Lens of Truth",
    "Hyrule Castle", "Zora's Domain (Land)", "Lake Hylia", "Shadow Temple",
    "Fire Temple", "Water Temple", "Forest Temple", "Spirit Temple",
]


def _make_activated_reg_test(name):
    def _t():
        g, p1, p2 = _new_game()
        obj = _put_bf(g, name, p1)
        abils = getattr(obj.state, 'activated_abilities', []) or []
        assert abils, f"{name}: original activated ability not registered (dead clause)"
    _t.__name__ = f"test_activated_reg_{name.lower().replace(' ', '_').replace('(', '').replace(')', '').replace(chr(39), '')}"
    _t.__doc__ = f"{name}: original activated/sac ability is registered"
    return _t


for _n in _ACTIVATED_PERMANENTS:
    _fn = _make_activated_reg_test(_n)
    globals()[_fn.__name__] = _fn


# ---- Direct effect_fn emission checks (artifact/land abilities) ------------

def test_bomb_bag_effect_emits_damage():
    """Bomb Bag {2},{T}: 2 damage to any target."""
    g, p1, p2 = _new_game()
    obj = _put_bf(g, "Bomb Bag", p1)
    ev = ZLD._bomb_bag_blast(obj, g.state, [p2.id])
    assert any(e.type == EventType.DAMAGE and e.payload.get('amount') == 2 for e in ev)


def test_fire_temple_effect_emits_damage():
    """Fire Temple {1}{R},{T}: 1 damage to any target."""
    g, p1, p2 = _new_game()
    obj = _put_bf(g, "Fire Temple", p1)
    ev = ZLD._fire_temple_burn(obj, g.state, [p2.id])
    assert any(e.type == EventType.DAMAGE and e.payload.get('amount') == 1 for e in ev)


def test_hyrule_castle_effect_emits_token():
    """Hyrule Castle {2},{T}: create a 1/1 Soldier token."""
    g, p1, p2 = _new_game()
    obj = _put_bf(g, "Hyrule Castle", p1)
    ev = ZLD._hyrule_castle_token(obj, g.state, [])
    assert any(e.type == EventType.CREATE_TOKEN for e in ev)


def test_lake_hylia_effect_emits_loot():
    """Lake Hylia {2},{T}: draw then discard."""
    g, p1, p2 = _new_game()
    obj = _put_bf(g, "Lake Hylia", p1)
    ev = ZLD._lake_hylia_loot(obj, g.state, [])
    assert any(e.type == EventType.DRAW for e in ev) and any(e.type == EventType.DISCARD for e in ev)


def test_fairy_bottle_effect_emits_lifegain():
    """Fairy Bottle Sacrifice: gain 5 life."""
    g, p1, p2 = _new_game()
    obj = _put_bf(g, "Fairy Bottle", p1)
    ev = ZLD._fairy_bottle_heal(obj, g.state, [])
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('amount') == 5 for e in ev)


# ---- Enters-tapped conditional lands --------------------------------------

def test_eldin_volcano_enters_tapped_no_goron():
    """Eldin Volcano enters tapped with no Goron."""
    g, p1, p2 = _new_game()
    obj = _put_bf(g, "Eldin Volcano", p1)
    assert obj.state.tapped, "Eldin Volcano: should enter tapped without a Goron"


def test_eldin_volcano_enters_untapped_with_goron():
    """Eldin Volcano enters untapped if you control a Goron."""
    g, p1, p2 = _new_game()
    _vanilla(g, p1, name="Goron", subtypes={"Goron"})
    obj = _put_bf(g, "Eldin Volcano", p1)
    assert not obj.state.tapped, "Eldin Volcano: should enter untapped with a Goron"


def test_lanayru_wetlands_enters_tapped_no_zora():
    """Lanayru Wetlands enters tapped with no Zora."""
    g, p1, p2 = _new_game()
    obj = _put_bf(g, "Lanayru Wetlands", p1)
    assert obj.state.tapped, "Lanayru Wetlands: should enter tapped without a Zora"


# ---- Nature's Fury (whole-card stub surfaced by anthem sweep) -------------

def test_natures_fury_pumps_team():
    """Nature's Fury: your creatures get +2/+2 and trample EOT."""
    g, p1, p2 = _new_game()
    _vanilla(g, p1, name="Mine")
    _vanilla(g, p2, name="Theirs")
    ev = ZLD._natures_fury_resolve([], g.state)
    pumps = [e for e in ev if e.type == EventType.PT_MODIFICATION and e.payload.get('power_mod') == 2]
    trample = [e for e in ev if e.type == EventType.GRANT_KEYWORD and e.payload.get('keyword') == 'trample']
    assert pumps, "Nature's Fury: no +2/+2 emitted"
    assert trample, "Nature's Fury: no trample grant emitted"


# ---- Info-pulse trigger sample (text-faithful slice-8A/B/C creatures) -----
# (card, trigger_kind, expected_event_type)
_INFO_PULSE = [
    ("Octorok", "etb", EventType.SCRY),                 # "scry 1 and each opp loses 1 life"
    ("Zora Warrior", "etb", EventType.SCRY),            # "scry 1; each opp loses 1 per Zora"
    ("River Zora", "attack", EventType.SCRY),           # "attacks, scry 1 and each opp -1"
    ("Goron Warrior", "attack", EventType.DAMAGE),      # "attacks, 1 dmg to each opp"
    ("Volvagia, Fire Dragon", "etb", EventType.SURVEIL),# "surveil 1 and deal 2 to each opp"
    ("Kokiri Child", "etb", EventType.SCRY),            # "scry 1; ... reveal"
    ("Gibdo", "etb", EventType.DISCARD),                # "each opp discards"
    ("Poe", "etb", EventType.LIFE_CHANGE),              # "each opp loses 1 life"
]


def _make_info_pulse_test(name, kind, want_type):
    def _t():
        g, p1, p2 = _new_game()
        obj = _put_bf(g, name, p1)
        if kind == "etb":
            events = [e for e in g.state.event_log]
        elif kind == "attack":
            events = g.emit(Event(type=EventType.ATTACK_DECLARED,
                                  payload={'attacker': obj.id, 'attacker_id': obj.id,
                                           'object_id': obj.id, 'player': p1.id}, source=obj.id))
        assert any(e.type == want_type for e in events), (
            f"{name}: expected {want_type.name} from {kind} trigger; "
            f"got {[e.type.name for e in events][:8]}")
    _t.__name__ = f"test_info_pulse_{name.lower().replace(' ', '_').replace(',', '').replace(chr(39), '')}"
    _t.__doc__ = f"{name}: {kind} trigger emits {want_type.name}"
    return _t


for _spec in _INFO_PULSE:
    _fn = _make_info_pulse_test(*_spec)
    globals()[_fn.__name__] = _fn


if __name__ == "__main__":
    import traceback
    tests = sorted([(k, v) for k, v in globals().items()
                    if k.startswith("test_") and callable(v)])
    passed, failed, errors = [], [], []
    for name, t in tests:
        try:
            t()
            passed.append(name)
        except AssertionError as e:
            failed.append((name, str(e)))
        except Exception as e:
            errors.append((name, f"{type(e).__name__}: {e}"))
            if __import__("os").environ.get("HYPERDRAFT_STRICT"):
                traceback.print_exc()
    print("\n=== Interceptor verification: Legend of Zelda ===")
    print(f"  passed:  {len(passed)}")
    print(f"  failed:  {len(failed)}")
    print(f"  errors:  {len(errors)}")
    print(f"  skipped: {len(SKIPPED_CARDS)} (see SKIPPED_CARDS)")
    if failed:
        print("\n--- FAILURES ---")
        for name, msg in failed[:30]:
            print(f"  {name}: {msg}")
    if errors:
        print("\n--- ERRORS ---")
        for name, msg in errors[:30]:
            print(f"  {name}: {msg}")
    sys.exit(0 if not failed and not errors else 1)
