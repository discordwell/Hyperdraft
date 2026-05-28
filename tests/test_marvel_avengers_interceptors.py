"""Interceptor verification for Marvel Avengers (slice-15 retrofit).

Fires the CORRECT trigger per each card's printed text and asserts the
expected effect event is emitted. Catches the depths trap (interceptor
wired but effect_fn returns []) and the slice-15 info-pulse contamination
(SCRY/drain emitted regardless of text). See /test-interceptors.
"""

import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

from src.engine import Game, Event, EventType, ZoneType, CardType, Color
from src.cards.custom.marvel_avengers import MARVEL_AVENGERS_CARDS as CARDS

# Cards whose printed effect the engine cannot yet express; intentionally
# left vanilla (no setup/resolve) after the slice-15 cleanup. Listed here so
# the punch list is visible rather than silently excluded.
SKIPPED_CARDS = {
    "Loki, God of Mischief": "copy target creature as Illusion token — no copy effect",
    "Taskmaster": "gains all activated abilities of opp creatures — not expressible",
    "Ebony Maw": "gain control until leaves — control-steal-with-duration n/a",
    "Magneto, Master of Magnetism": "gain control of all Equipment — control-steal n/a",
    "Rogue, Power Absorber": "gains all abilities of damaged creature — not expressible",
    "Forest Troll": "regenerate — engine has no regeneration shield",
    "Colossus, Piotr Rasputin": "indestructible while attacking/blocking — conditional kw",
    "The Thing, Ben Grimm": "indestructible while blocking — conditional kw",
    "Vibranium Rhino": "indestructible while attacking — conditional kw",
    "Corvus Glaive": "can't be destroyed by damage — static damage-immunity n/a",
    "Cosmic Convergence": "copy your 2nd spell — spell-copy n/a",
    # Activated-ability / mana-ability only (resolved via priority, no trigger):
    "Avengers Medic": "activated {T}: gain life",
    "SHIELD Tech Specialist": "activated {T}: untap artifact",
    "Pym Particle Researcher": "activated loot",
    "SHIELD Helicarrier Crew": "Defender + mana ability",
    "Destroyer Armor": "activated {R}: damage",
    "Human Torch, Johnny Storm": "activated pump/damage",
    "Ravager Engineer": "static grant of mana ability to artifacts",
    "Eye of Agamotto": "activated scry/bounce/extra-turn",
    "Tesseract": "mana + activated flicker",
    "SHIELD Helicarrier": "granted activated abilities on vehicle",
    "Genosha": "grants mana ability to Mutants",
    "Avengers Tower": "mana abilities", "Stark Tower": "mana abilities",
    "Wakanda": "mana + conditional ETB-tapped", "Knowhere": "mana abilities",
    "Xavier's School for Gifted Youngsters": "mana abilities",
    "HYDRA Base": "mana + ETB pay-life choice", "SHIELD Facility": "mana + ETB tapped",
    "Titan": "mana + activated tutor", "Vormir": "mana + activated draw",
    "Contraxia": "mana + ETB tapped", "Hala": "mana + activated token",
    "Nidavellir": "restricted mana", "Asgard": "mana + activated token",
    "Sanctum Sanctorum": "mana + activated scry",
}


def _bf(game, player, card_name):
    """Create a card in hand then move to battlefield via ZONE_CHANGE so
    interceptors register and ETB fires exactly once. Returns (obj, events)."""
    cd = CARDS[card_name]
    obj = game.create_object(name=card_name, owner_id=player.id,
                             zone=ZoneType.HAND, characteristics=cd.characteristics,
                             card_def=None)
    obj.card_def = cd
    events = game.emit(Event(type=EventType.ZONE_CHANGE, payload={
        'object_id': obj.id, 'from_zone': f'hand_{player.id}',
        'to_zone': 'battlefield', 'to_zone_type': ZoneType.BATTLEFIELD}))
    return obj, events


def _types(events):
    return {e.type for e in events}


def _vanilla(game, player, name="Grunt", subtypes=None):
    """Put a plain vanilla creature on the battlefield (target/ally fodder)."""
    from src.engine import Characteristics
    ch = Characteristics(types={CardType.CREATURE},
                         subtypes=subtypes or {"Soldier"}, power=2, toughness=2)
    return game.create_object(name=name, owner_id=player.id,
                              zone=ZoneType.BATTLEFIELD, characteristics=ch, card_def=None)


# --- ETB / on-enter triggers: (card_name -> expected event type) -------------
ETB_TRIGGERS = {
    "Ravager Scout": EventType.SCRY,
    "Xandarian Pilot": EventType.SCRY,
    "Knowhere Merchant": EventType.DRAW,
    "Beast, Hank McCoy": EventType.DRAW,
    "Fire Demon": EventType.TARGET_REQUIRED,
    "Nova Prime": EventType.TARGET_REQUIRED,
    "Ronan the Accuser": EventType.TARGET_REQUIRED,
    "Winter Soldier Asset": EventType.TARGET_REQUIRED,
    "Mantis, Empath": EventType.TARGET_REQUIRED,
    "Iceman, Bobby Drake": EventType.TARGET_REQUIRED,
    "Dark Elf Warrior": EventType.TARGET_REQUIRED,
    "Wakandan War Rhino": EventType.FIGHT,
    "Savage Land Rex": EventType.FIGHT,
    "Kingpin's Enforcer": EventType.DISCARD,
    "Baron Mordo": EventType.COUNTER_SPELL_UNLESS_PAY,
    "Sakaar": EventType.CREATE_TOKEN,
}


def _make_etb_test(card_name, expected):
    def test():
        game = Game()
        p1 = game.add_player("Alice"); game.add_player("Bob")
        game.state.active_player = p1.id
        # ally fodder + a target creature so targeted/fight ETBs have material
        _vanilla(game, p1, "Ally")
        obj, events = _bf(game, p1, card_name)
        got = _types(events)
        assert expected in got, f"{card_name}: expected {expected.name}, got {[t.name for t in got]}"
    test.__name__ = "test_etb_" + card_name.split(",")[0].replace(" ", "_").replace("'", "").lower()
    test.__doc__ = f"{card_name}: ETB emits {expected.name}"
    return test


for _cn, _ev in ETB_TRIGGERS.items():
    _t = _make_etb_test(_cn, _ev)
    globals()[_t.__name__] = _t


# --- Nightcrawler: ETB bounce needs ANOTHER own creature present -------------
def test_etb_nightcrawler():
    """Nightcrawler: ETB returns another creature you control to hand (BOUNCE)."""
    game = Game()
    p1 = game.add_player("Alice"); game.add_player("Bob")
    game.state.active_player = p1.id
    _vanilla(game, p1, "Ally")
    obj, events = _bf(game, p1, "Nightcrawler")
    assert EventType.BOUNCE in _types(events), \
        f"Nightcrawler: expected BOUNCE, got {[t.name for t in _types(events)]}"


def test_etb_storm():
    """Storm: ETB taps all creatures opponents control."""
    game = Game()
    p1 = game.add_player("Alice"); p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    _vanilla(game, p2, "Foe1"); _vanilla(game, p2, "Foe2")
    obj, events = _bf(game, p1, "Storm, Weather Witch")
    taps = [e for e in events if e.type == EventType.TAP]
    assert len(taps) == 2, f"Storm: expected 2 TAP events, got {len(taps)}"


# --- Upkeep triggers ---------------------------------------------------------
UPKEEP_TRIGGERS = {
    "SHIELD Headquarters": EventType.SCRY,
    "Red Skull, HYDRA Supreme": EventType.LIFE_CHANGE,
    "Dormammu, Lord of the Dark Dimension": EventType.LIFE_CHANGE,
}


def _make_upkeep_test(card_name, expected):
    def test():
        game = Game()
        p1 = game.add_player("Alice"); game.add_player("Bob")
        game.state.active_player = p1.id
        obj, _ = _bf(game, p1, card_name)
        events = game.emit(Event(type=EventType.PHASE_START,
                                 payload={'phase': 'upkeep', 'player': p1.id},
                                 controller=p1.id))
        assert expected in _types(events), \
            f"{card_name}: expected {expected.name} on upkeep, got {[t.name for t in _types(events)]}"
    test.__name__ = "test_upkeep_" + card_name.split(",")[0].replace(" ", "_").lower()
    test.__doc__ = f"{card_name}: upkeep emits {expected.name}"
    return test


for _cn, _ev in UPKEEP_TRIGGERS.items():
    _t = _make_upkeep_test(_cn, _ev)
    globals()[_t.__name__] = _t


# --- Death trigger: Ultron Drone deals 2 damage on death --------------------
def test_death_ultron_drone():
    """Ultron Drone: dies -> deal 2 damage to any target (TARGET_REQUIRED)."""
    game = Game()
    p1 = game.add_player("Alice"); game.add_player("Bob")
    game.state.active_player = p1.id
    obj, _ = _bf(game, p1, "Ultron Drone")
    events = game.emit(Event(type=EventType.OBJECT_DESTROYED,
                             payload={'object_id': obj.id}, source=obj.id))
    assert EventType.TARGET_REQUIRED in _types(events), \
        f"Ultron Drone: expected TARGET_REQUIRED on death, got {[t.name for t in _types(events)]}"


# --- Death-watch: Baron Zemo draws when opp Avenger dies --------------------
def test_deathwatch_baron_zemo():
    """Baron Zemo: opponent's Avenger dies -> draw a card."""
    game = Game()
    p1 = game.add_player("Alice"); p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    _bf(game, p1, "Baron Zemo, Vengeful Noble")
    foe = _vanilla(game, p2, "Enemy Avenger", subtypes={"Avenger"})
    events = game.emit(Event(type=EventType.ZONE_CHANGE, payload={
        'object_id': foe.id, 'from_zone': 'battlefield', 'to_zone': f'graveyard_{p2.id}',
        'from_zone_type': ZoneType.BATTLEFIELD, 'to_zone_type': ZoneType.GRAVEYARD}))
    assert EventType.DRAW in _types(events), \
        f"Baron Zemo: expected DRAW, got {[t.name for t in _types(events)]}"


# --- Attack triggers ---------------------------------------------------------
ATTACK_TRIGGERS = {
    "The Benatar": (EventType.CREATE_TOKEN, None),
    "The Milano": (EventType.PT_MODIFICATION, "Guardian"),
    "Lady Sif, Shield Maiden": (EventType.GRANT_KEYWORD, "Warrior"),
}


def _make_attack_test(card_name, expected, ally_subtype):
    def test():
        game = Game()
        p1 = game.add_player("Alice"); game.add_player("Bob")
        game.state.active_player = p1.id
        obj, _ = _bf(game, p1, card_name)
        if ally_subtype:
            _vanilla(game, p1, "Ally", subtypes={ally_subtype})
        events = game.emit(Event(type=EventType.ATTACK_DECLARED,
                                 payload={'attacker_id': obj.id}, source=obj.id))
        assert expected in _types(events), \
            f"{card_name}: expected {expected.name} on attack, got {[t.name for t in _types(events)]}"
    test.__name__ = "test_attack_" + card_name.split(",")[0].replace(" ", "_").replace("'", "").lower()
    test.__doc__ = f"{card_name}: attack emits {expected.name}"
    return test


for _cn, (_ev, _sub) in ATTACK_TRIGGERS.items():
    _t = _make_attack_test(_cn, _ev, _sub)
    globals()[_t.__name__] = _t


# Quinjet: attack -> library search (emits a choice / search event)
def test_attack_quinjet():
    """Quinjet: attack -> search library for an Avenger (some search/choice event)."""
    game = Game()
    p1 = game.add_player("Alice"); game.add_player("Bob")
    game.state.active_player = p1.id
    # populate library so the search has material
    av = CARDS["Captain America, First Avenger"]
    game.create_object(name="Captain America, First Avenger", owner_id=p1.id,
                       zone=ZoneType.LIBRARY, characteristics=av.characteristics, card_def=None)
    obj, _ = _bf(game, p1, "Quinjet")
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': obj.id}, source=obj.id))
    # library-search opens a PendingChoice rather than emitting events
    assert game.state.pending_choice is not None, \
        "Quinjet: attack trigger did not open a library-search choice"


# --- Combat-damage-to-player triggers ---------------------------------------
COMBAT_DMG_TRIGGERS = {
    "Ghost, Phasing Thief": EventType.DISCARD,
    "Proxima Midnight": EventType.DISCARD,
    "Abomination": EventType.COUNTER_ADDED,
}


def _make_combat_dmg_test(card_name, expected):
    def test():
        game = Game()
        p1 = game.add_player("Alice"); p2 = game.add_player("Bob")
        game.state.active_player = p1.id
        obj, _ = _bf(game, p1, card_name)
        events = game.emit(Event(type=EventType.DAMAGE, payload={
            'source': obj.id, 'target': p2.id, 'amount': 2, 'is_combat': True},
            source=obj.id))
        assert expected in _types(events), \
            f"{card_name}: expected {expected.name} on combat dmg, got {[t.name for t in _types(events)]}"
    test.__name__ = "test_combatdmg_" + card_name.split(",")[0].replace(" ", "_").replace("'", "").lower()
    test.__doc__ = f"{card_name}: combat damage to player emits {expected.name}"
    return test


for _cn, _ev in COMBAT_DMG_TRIGGERS.items():
    _t = _make_combat_dmg_test(_cn, _ev)
    globals()[_t.__name__] = _t


# --- Static lord boosts: an ally of the subtype gets +p/+t ------------------
from src.engine import get_power, get_toughness

# (enchant/anthem card, ally subtype, expected power delta, expected tough delta)
STATIC_LORDS = [
    ("Asgardian Might", "Asgardian", 2, 1),
    ("Mutant Uprising", "Mutant", 1, 1),
    ("Vibranium Mines", "Wakandan", 0, 1),
]


def _make_static_test(card_name, subtype, dp, dt):
    def test():
        game = Game()
        p1 = game.add_player("Alice"); game.add_player("Bob")
        game.state.active_player = p1.id
        ally = _vanilla(game, p1, "Ally", subtypes={subtype})
        base_p, base_t = get_power(ally, game.state), get_toughness(ally, game.state)
        _bf(game, p1, card_name)
        np, nt = get_power(ally, game.state), get_toughness(ally, game.state)
        assert (np - base_p, nt - base_t) == (dp, dt), \
            f"{card_name}: expected +{dp}/+{dt} on {subtype}, got +{np-base_p}/+{nt-base_t}"
    test.__name__ = "test_lord_" + card_name.split(",")[0].replace(" ", "_").lower()
    test.__doc__ = f"{card_name}: {subtype} ally gets +{dp}/+{dt}"
    return test


for _cn, _sub, _dp, _dt in STATIC_LORDS:
    _t = _make_static_test(_cn, _sub, _dp, _dt)
    globals()[_t.__name__] = _t


def test_lord_professor_x_grants_hexproof():
    """Professor X: other Mutants you control have hexproof."""
    from src.engine.queries import has_ability
    game = Game()
    p1 = game.add_player("Alice"); game.add_player("Bob")
    game.state.active_player = p1.id
    ally = _vanilla(game, p1, "Mutant Ally", subtypes={"Mutant"})
    _bf(game, p1, "Professor X, Charles Xavier")
    assert has_ability(ally, "hexproof", game.state), \
        "Professor X: Mutant ally did not gain hexproof"


# --- Self conditional / attacking / dynamic boosts --------------------------
def test_self_ant_swarm_dynamic():
    """Ant Swarm: +1/+1 per other Insect you control."""
    game = Game()
    p1 = game.add_player("Alice"); game.add_player("Bob")
    game.state.active_player = p1.id
    _vanilla(game, p1, "Bug A", subtypes={"Insect"})
    _vanilla(game, p1, "Bug B", subtypes={"Insect"})
    swarm, _ = _bf(game, p1, "Ant Swarm")
    base = CARDS["Ant Swarm"].characteristics.power
    assert get_power(swarm, game.state) == base + 2, \
        f"Ant Swarm: expected +2 for 2 Insects, got {get_power(swarm, game.state) - base}"


def test_self_drax_villain_boost():
    """Drax: +2/+2 while an opponent controls a Villain."""
    game = Game()
    p1 = game.add_player("Alice"); p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    _vanilla(game, p2, "Bad Guy", subtypes={"Villain"})
    drax, _ = _bf(game, p1, "Drax the Destroyer")
    base = CARDS["Drax the Destroyer"].characteristics.power
    assert get_power(drax, game.state) == base + 2, \
        f"Drax: expected +2 vs opp Villain, got {get_power(drax, game.state) - base}"


# --- Equipment: equipped creature gets the printed P/T boost ----------------
# (equipment card, expected power delta)
EQUIPMENT = {
    "Stormbreaker": 4, "Iron Man Armor Mk. L": 3, "Iron Man Armor Mk. LXXXV": 4,
    "Hulkbuster Armor": 5, "Web-Shooters": 1, "Yaka Arrow": 2,
    "Vibranium Spear": 2, "Panther Habit": 2, "Cloak of Levitation": 1,
    "Nano Gauntlet": 1,
}


def _make_equip_test(card_name, dp):
    def test():
        game = Game()
        p1 = game.add_player("Alice"); game.add_player("Bob")
        game.state.active_player = p1.id
        wearer = _vanilla(game, p1, "Bearer")
        base = get_power(wearer, game.state)
        equip, _ = _bf(game, p1, card_name)
        equip.state.attached_to = wearer.id
        assert get_power(wearer, game.state) - base == dp, \
            f"{card_name}: expected +{dp} power on bearer, got +{get_power(wearer, game.state) - base}"
    test.__name__ = "test_equip_" + card_name.split(",")[0].replace(" ", "_").replace(".", "").lower()
    test.__doc__ = f"{card_name}: equipped creature gets +{dp} power"
    return test


for _cn, _dp in EQUIPMENT.items():
    _t = _make_equip_test(_cn, _dp)
    globals()[_t.__name__] = _t


# --- Instant/Sorcery resolvers ----------------------------------------------
def _cast(game, caster, card_name, targets=None):
    return CARDS[card_name].resolve(targets or [], game.state)


def _opp_creature(game, owner):
    return _vanilla(game, owner, "Victim")


# (card, builds-targets?, expected event in resolution)
def test_resolve_repulsor_blast():
    """Repulsor Blast: 3 damage to target creature."""
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    game.state.active_player = p1.id
    v = _opp_creature(game, p2)
    evs = _cast(game, p1, "Repulsor Blast", [[type("T", (), {"id": v.id, "is_player": False})()]])
    assert EventType.DAMAGE in _types(evs), [e.type.name for e in evs]


def test_resolve_impale():
    """Impale: destroy target creature + controller loses 2."""
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    game.state.active_player = p1.id
    v = _opp_creature(game, p2)
    evs = _cast(game, p1, "Impale", [[type("T", (), {"id": v.id, "is_player": False})()]])
    got = _types(evs)
    assert EventType.OBJECT_DESTROYED in got and EventType.LIFE_CHANGE in got, [e.type.name for e in evs]


def test_resolve_cosmic_awareness():
    """Cosmic Awareness: draw cards (no board dependency)."""
    game = Game(); p1 = game.add_player("A"); game.add_player("B")
    game.state.active_player = p1.id
    evs = _cast(game, p1, "Cosmic Awareness")
    assert EventType.DRAW in _types(evs), [e.type.name for e in evs]


def test_resolve_arrow_volley_sweep():
    """Arrow Volley: 1 damage to each opp creature."""
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    game.state.active_player = p1.id
    _opp_creature(game, p2); _opp_creature(game, p2)
    evs = _cast(game, p1, "Arrow Volley")
    dmg = [e for e in evs if e.type == EventType.DAMAGE]
    assert len(dmg) == 2, f"expected 2 sweep damage events, got {len(dmg)}"


def test_resolve_wakanda_forever_mass_pump():
    """Wakanda Forever: your creatures +2/+2 + indestructible."""
    game = Game(); p1 = game.add_player("A"); game.add_player("B")
    game.state.active_player = p1.id
    _vanilla(game, p1, "Hero A"); _vanilla(game, p1, "Hero B")
    evs = _cast(game, p1, "Wakanda Forever")
    got = _types(evs)
    assert EventType.PT_MODIFICATION in got and EventType.GRANT_KEYWORD in got, [e.type.name for e in evs]


def test_resolve_snap_sac_half():
    """Snap: each player sacrifices half their creatures."""
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    game.state.active_player = p1.id
    for _ in range(3):
        _opp_creature(game, p2)
    evs = _cast(game, p1, "Snap")
    assert EventType.SACRIFICE_REQUIRED in _types(evs), [e.type.name for e in evs]


def test_resolve_hulk_smash_fight():
    """Hulk Smash: your creature deals power damage to target."""
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    game.state.active_player = p1.id
    _vanilla(game, p1, "My Brawler"); v = _opp_creature(game, p2)
    evs = _cast(game, p1, "Hulk Smash", [[type("T", (), {"id": v.id, "is_player": False})()]])
    assert EventType.DAMAGE in _types(evs), [e.type.name for e in evs]


def test_resolve_widows_sting_pump():
    """Widow's Sting: target creature gets -3/-3."""
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    game.state.active_player = p1.id
    v = _opp_creature(game, p2)
    evs = _cast(game, p1, "Widow's Sting", [[type("T", (), {"id": v.id, "is_player": False})()]])
    pm = [e for e in evs if e.type == EventType.PT_MODIFICATION]
    assert pm and pm[0].payload.get('power_mod') == -3, [e.type.name for e in evs]


def test_resolve_reality_warp_exile_sweep():
    """Reality Warp: exile all artifacts/enchantments, owners draw."""
    game = Game(); p1 = game.add_player("A"); game.add_player("B")
    game.state.active_player = p1.id
    _bf(game, p1, "Stark Tower")  # a permanent that is an artifact? it's a land
    # use a real artifact:
    art = CARDS["Tesseract"]
    o = game.create_object(name="Tesseract", owner_id=p1.id, zone=ZoneType.HAND,
                           characteristics=art.characteristics, card_def=None)
    o.card_def = art
    game.emit(Event(type=EventType.ZONE_CHANGE, payload={
        'object_id': o.id, 'from_zone': f'hand_{p1.id}', 'to_zone': 'battlefield',
        'to_zone_type': ZoneType.BATTLEFIELD}))
    evs = _cast(game, p1, "Reality Warp")
    assert EventType.EXILE in _types(evs), [e.type.name for e in evs]


# --- Anti-regression: keyword-only cards must NOT carry a setup (no stubs) ---
KEYWORD_ONLY = ["Einherjar Soldier", "Nova Corps Officer", "Chitauri Charger",
                "Corvus Glaive"]


def test_keyword_only_have_no_setup():
    """Vanilla keyword-only cards must have no setup_interceptors (slice-15
    stubs gamed the test by attaching info-pulse setups to these)."""
    for nm in KEYWORD_ONLY:
        cd = CARDS[nm]
        assert getattr(cd, 'setup_interceptors', None) is None, \
            f"{nm}: keyword-only card should have NO setup_interceptors (stub regression?)"


def test_no_slice15_infopulse_stub_defs_remain():
    """The deleted slice-15 stub setups must not have been reintroduced."""
    import src.cards.custom.marvel_avengers as mod
    bad = [n for n in dir(mod)
           if n.startswith("_mvl_") and n.endswith("_setup")
           and n not in ("_mvl_groot_setup_s15",)]  # none expected
    # The retrofit defines factory makers (make_*_setup) and a few named
    # setups; none should be the old per-card info-pulse stubs.
    legacy = [n for n in bad if any(tok in n for tok in (
        "einherjar", "lady_sif", "shield_helicarrier_crew", "nova_corps",
        "ravager_scout", "chitauri_charger", "destroyer_armor"))]
    assert not legacy, f"slice-15 stub setups reappeared: {legacy}"


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
    print("\n=== Interceptor verification: Marvel Avengers ===")
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
