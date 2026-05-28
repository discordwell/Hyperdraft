"""Per-card interceptor verification for the Temporal Horizons custom set.

See `.claude/commands/test-interceptors.md` (the /test-interceptors skill).

The depths trap: a card's text says "deal 2 damage when this enters", its
``setup_interceptors`` registers an ETB trigger, the trigger fires — and the
effect_fn returns ``[]`` because the effect was stubbed out and never filled
in. Downstream stages (deck tournaments, AI tuning) then waste hours on
"the deck is bad" results that are really "the card does nothing".

This file fires the *correct canonical trigger* for each of the 139 wired
cards (ETB -> ZONE_CHANGE to battlefield; "when this dies" -> destroy it;
attack -> declare attacker; upkeep/end-step -> that phase; static/lord ->
assert a QUERY interceptor registered) and asserts a text-appropriate event
is emitted by the real ``game.emit`` pipeline.

Cards are classified at import time by *probing* their interceptors' filters
against candidate canonical events — this is robust against source-parse
fragility. The expected effect EventType is derived from each card's printed
``text``.
"""

import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

import re

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, InterceptorPriority,
)
from src.cards.custom.temporal_horizons import TEMPORAL_HORIZONS_CARDS

# Cards we cannot auto-fire cleanly (filters require very specific board state
# that the generic harness does not construct). They are still exercised for
# *registration* (their setup_interceptors runs without error and returns at
# least one interceptor), but we do not assert on emitted events. Each entry
# has a one-line reason so the human sees exactly what is uncovered.
SKIPPED_CARDS = {
    "Symbiotic Timeline":
        "trigger fires only when an entering creature already carries a "
        "+1/+1 or time counter; harness enters a counter-less creature.",
    "Eternal Light":
        "secondary trigger needs an entering creature with a time counter; "
        "the static +1/+1 lord half is covered by registration.",
    "Chronoblade, Forged in Time":
        "equipment: combat-attack time-counter trigger needs an equipped "
        "creature; equip statics covered by registration.",
    "Temporal Blade":
        "equipment: combat-damage trigger needs an equipped/attacking "
        "creature; equip statics covered by registration.",
    # Conditional triggers whose payoff only fires when a board condition is
    # met (combo assembled / counters depleted / equipped). The generic harness
    # cannot satisfy these, so the trigger correctly resolves to no effect; we
    # exercise registration only.
    "Crystal of Present":
        "upkeep extra-turn fires only with all three Crystals on board; "
        "harness has one. Activated scry+draw covered by registration.",
    "Sands of Time":
        "mass-reanimation fires only after the third upkeep removes the last "
        "charge counter; harness fires the first upkeep (no payoff yet).",
    "Suspended Island":
        "upkeep only removes a time counter (no spell emitted); the mana "
        "ability is granted statically while a time counter remains.",
    "Timeless Crown":
        "equipment: upkeep time-counter trigger needs an equipped creature; "
        "the +2/+2 equip static is covered by registration.",
}

# Modal ("choose one") / conditional ("if … instead") cards: any of several
# effect types is correct depending on the chosen mode / met branch, so we only
# apply the depths guard (>=1 effect emitted), not the single-type pin.
_MODAL_CONDITIONAL = {
    "Kael, Timekeeper",      # choose one: put / remove counter / draw
    "Entropy and Order",     # choose one: reanimate / destroy
    "Temporal Anchor",       # if no time-countered permanents: counter; else scry
    "Future Sight Oracle",   # look at top; gain life only if it's a creature
    "Entropy Twins",         # each opp discards; if they can't, deal 3 damage
}

REACTISH = (InterceptorPriority.REACT, InterceptorPriority.TRANSFORM,
            InterceptorPriority.PREVENT)

# The event-type each canonical trigger *rides on*. We strip ONLY this event
# (the one we emitted to fire the trigger) from the log so what remains is the
# card's effect. Note we strip per-kind, never globally — e.g. a DEATH trigger
# whose effect deals DAMAGE must keep that DAMAGE event in the effect list.
_TRIGGER_RIDE_EVENT = {
    "ETB": {"ZONE_CHANGE"},
    "DEATH": {"ZONE_CHANGE"},
    "ATTACK": {"ATTACK_DECLARED"},
    "DAMAGE": {"DAMAGE"},
    "UPKEEP": {"PHASE_START"},
    "END_STEP": {"PHASE_START"},
}

# ---------------------------------------------------------------------------
# text -> expected effect EventType keywords
# ---------------------------------------------------------------------------
# Each entry: (regex over card text, set of acceptable emitted EventType names).
# Order matters — first match wins. A card that emits ANY event NOT in the
# trigger set already passes the depths guard; this table additionally pins
# the effect type where the text makes it unambiguous.
# A targeted effect that pauses for a choice legitimately emits TARGET_REQUIRED
# instead of (or before) its concrete effect — accept it everywhere a target is
# implied. Rewind death-cycle effects route through VOID_ACTIVATED.
_TGT = {"TARGET_REQUIRED"}
_TEXT_EFFECT_RULES = [
    # Saga: chapters resolve through the saga lore/chapter pipeline.
    (r"as this saga enters|add a lore counter|^i —|sacrifice after iii",
     {"SAGA_CHAPTER", "SAGA_LORE_ADDED", "EXILE_TOP_PLAY", "CREATE_TOKEN",
      "EXILE", "EXTRA_TURN"}),
    # "Rewind — when this dies, exile it with N time counters" (death-cycle):
    (r"rewind\b.*time counter|exile it with (two|three|\d) time counters",
     {"VOID_ACTIVATED", "EXILE", "COUNTER_ADDED"}),
    (r"deals?\s+\d*\s*damage|deals?\s+x\s+damage",
     {"DAMAGE", "DEAL_DAMAGE"} | _TGT),
    (r"gain(s)?\s+\d*\s*life|gain life|gain 1 life|gain 2 life",
     {"LIFE_CHANGE", "LIFE_GAIN"}),
    (r"loses?\s+\d*\s*life|lose \d life",
     {"LIFE_CHANGE", "LIFE_LOSS"} | _TGT),
    (r"return.*from your graveyard to the battlefield",
     {"RETURN_FROM_GRAVEYARD", "ZONE_CHANGE"} | _TGT),
    (r"return.*from your graveyard to your hand|return.*creature card.*to your hand",
     {"RETURN_TO_HAND_FROM_GRAVEYARD", "RETURN_FROM_GRAVEYARD"} | _TGT),
    (r"return.*to (its|their) owner.?s hand|return.*to your hand",
     {"RETURN_TO_HAND", "RETURN_TO_HAND_FROM_GRAVEYARD"} | _TGT),
    (r"destroy target",
     {"OBJECT_DESTROYED", "DESTROY"} | _TGT),
    (r"create.*token|create a token|create two|create three",
     {"CREATE_TOKEN", "OBJECT_CREATED"}),
    (r"search your library.*basic land|put.*land.*onto the battlefield",
     {"SEARCH_LIBRARY", "LIBRARY_SEARCH", "LANDER_SEARCH_LAND"} | _TGT),
    # "look at the top N ... put one into hand, rest to graveyard/bottom"
    (r"look at the top (three|two|\d)|top three cards",
     {"IMPULSE_TO_GRAVEYARD", "EXILE_TOP_PLAY", "EXILE_TOP", "EXILE",
      "SCRY", "SURVEIL", "DRAW", "IMPULSE_DRAW"}),
    (r"put a time counter|put two time counters|put .* time counter",
     {"COUNTER_ADDED", "PUT_TIME_COUNTER"} | _TGT),
    (r"put .*\+1/\+1 counter|put two \+1/\+1",
     {"COUNTER_ADDED"} | _TGT),
    (r"remove a time counter",
     {"COUNTER_REMOVED", "CONTINUOUS_EFFECT", "PT_MODIFICATION",
      "TEMPORARY_BOOST"} | _TGT),
    (r"exile target spell|counter target spell",
     {"EXILE", "COUNTER_SPELL", "SPELL_COUNTERED"} | _TGT),
    (r"exile the top|exile.*card.*library",
     {"EXILE", "EXILE_TOP", "EXILE_TOP_CARD", "EXILE_FROM_TOP",
      "EXILE_TOP_PLAY", "IMPULSE_TO_GRAVEYARD",
      "SCRY", "SURVEIL", "DRAW", "IMPULSE_DRAW"}),
    (r"equip it to|equip \{",
     {"AUTO_EQUIP", "ATTACH"} | _TGT),
    (r"each player sacrifices|sacrifices a creature|they sacrifice|"
     r"each opponent sacrifices",
     {"SACRIFICE", "SACRIFICE_REQUIRED", "MAY_SACRIFICE",
      "MAY_PAY_LIFE", "OPTIONAL_SACRIFICE_FOR_EFFECT"} | _TGT),
    (r"discards?\b",
     {"DISCARD", "CONDITIONAL_DISCARD"}),
    (r"scry",
     {"SCRY"}),
    (r"mills?\b|mill ",
     {"MILL"}),
    (r"gains? hexproof|gains? indestructible|gains? (first strike|haste|"
     r"trample|vigilance|flying)|get(s)? \+\d/\+\d",
     {"TEMPORARY_BOOST", "PT_MODIFICATION", "CONTINUOUS_EFFECT",
      "GRANT_KEYWORD", "COUNTER_ADDED"} | _TGT),
    (r"untap all|untap target",
     {"UNTAP", "UNTAP_ALL", "UNTAP_TARGET"}),
    (r"take an extra turn",
     {"EXTRA_TURN", "SAGA_CHAPTER", "EXILE_TOP_PLAY"}),
]


def _expected_effects(text: str):
    """Return the set of acceptable emitted EventType names for this text,
    or None if the text has no determinable single effect (then we only
    apply the depths guard: at least one non-trigger event)."""
    t = (text or "").lower()
    for pattern, names in _TEXT_EFFECT_RULES:
        if re.search(pattern, t):
            return names
    return None


# ---------------------------------------------------------------------------
# classification + firing
# ---------------------------------------------------------------------------
def _new_game():
    g = Game()
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob")
    g.state.active_player = p1.id
    return g, p1, p2


def _classify(name):
    """Probe a card's interceptors and return (kind, has_query, n_interceptors).

    kind in {ETB, ATTACK, DAMAGE, UPKEEP, END_STEP, DEATH, EXOTIC, STATIC}.
    """
    g, p1, p2 = _new_game()
    cd = TEMPORAL_HORIZONS_CARDS[name]
    obj = g.create_object(name=name, owner_id=p1.id,
                          zone=ZoneType.BATTLEFIELD,
                          characteristics=cd.characteristics, card_def=cd)
    ints = cd.setup_interceptors(obj, g.state)
    s = g.state

    def _matches(ev):
        for it in ints:
            if it.priority in REACTISH:
                try:
                    if it.filter(ev, s):
                        return True
                except Exception:
                    pass
        return False

    death_ev = Event(type=EventType.OBJECT_DESTROYED,
                     payload={"object_id": obj.id})

    def _death_matches():
        obj.zone = ZoneType.GRAVEYARD
        r = _matches(death_ev)
        obj.zone = ZoneType.BATTLEFIELD
        return r

    probes = [
        ("ETB", Event(type=EventType.ZONE_CHANGE,
                      payload={"object_id": obj.id,
                               "to_zone_type": ZoneType.BATTLEFIELD,
                               "from_zone": "hand"})),
        ("ATTACK", Event(type=EventType.ATTACK_DECLARED,
                         payload={"attacker_id": obj.id, "attacker": obj.id,
                                  "defender": p2.id})),
        ("DAMAGE", Event(type=EventType.DAMAGE,
                         payload={"source": obj.id, "target": p2.id,
                                  "amount": 2, "is_combat": True})),
        ("UPKEEP", Event(type=EventType.PHASE_START,
                         payload={"phase": "upkeep", "player": p1.id})),
        ("END_STEP", Event(type=EventType.PHASE_START,
                           payload={"phase": "end_step", "player": p1.id})),
    ]
    # Text-driven preference: when the printed text's primary clause is a
    # death/rewind trigger, classify as DEATH even if an incidental ATTACK or
    # ETB filter also matches (e.g. Rewind cards whose real effect is on death).
    txt = (cd.text or "").lower()
    if ("when " in txt and " dies" in txt or "rewind" in txt) and _death_matches():
        return "DEATH", InterceptorPriority.QUERY in [i.priority for i in ints], len(ints)

    kind = None
    for k, ev in probes:
        if _matches(ev):
            kind = k
            break
    if not kind:
        obj.zone = ZoneType.GRAVEYARD
        for it in ints:
            if it.priority in REACTISH:
                try:
                    if it.filter(death_ev, s):
                        kind = "DEATH"
                        break
                except Exception:
                    pass
        obj.zone = ZoneType.BATTLEFIELD
    prios = [i.priority for i in ints]
    has_query = InterceptorPriority.QUERY in prios
    has_react = any(p in REACTISH for p in prios)
    if not kind:
        kind = "STATIC" if (has_query and not has_react) else "EXOTIC"
    return kind, has_query, len(ints)


_VANILLA_BEAR = "Rift Runner"  # truly vanilla creature (text == "Haste.")


def _populate_board(g, p1, p2):
    """Give each player a couple of vanilla creatures so effects that act on
    "each other creature you control" / "each opponent's creature" / count
    allies / "creatures with a time counter" have material to operate on.
    One ally carries a time counter; one creature card sits in p1's graveyard
    so "return a creature card from your graveyard" effects have a target."""
    bear = TEMPORAL_HORIZONS_CARDS.get(_VANILLA_BEAR)
    if bear is None:
        return
    made = []
    for owner in (p1, p1, p2):
        o = g.create_object(name=_VANILLA_BEAR, owner_id=owner.id,
                            zone=ZoneType.BATTLEFIELD,
                            characteristics=bear.characteristics, card_def=bear)
        made.append(o)
    # put a time counter on one ally + one opponent creature
    for o in (made[0], made[2]):
        try:
            o.state.counters["time"] = o.state.counters.get("time", 0) + 1
        except Exception:
            pass
    # a creature card in p1's graveyard for graveyard-return effects
    g.create_object(name=_VANILLA_BEAR, owner_id=p1.id,
                    zone=ZoneType.GRAVEYARD,
                    characteristics=bear.characteristics, card_def=bear)


def _emit_canonical(name, kind):
    """Fire the canonical trigger event for *kind* via the real pipeline and
    return the list of emitted EventType names with trigger events removed."""
    g, p1, p2 = _new_game()
    cd = TEMPORAL_HORIZONS_CARDS[name]
    _populate_board(g, p1, p2)
    if kind == "ETB":
        obj = g.create_object(name=name, owner_id=p1.id, zone=ZoneType.HAND,
                              characteristics=cd.characteristics, card_def=cd)
        evs = g.emit(Event(type=EventType.ZONE_CHANGE,
                           payload={"object_id": obj.id, "from_zone": "hand",
                                    "to_zone": "battlefield",
                                    "to_zone_type": ZoneType.BATTLEFIELD}))
    elif kind in ("UPKEEP", "END_STEP"):
        obj = g.create_object(name=name, owner_id=p1.id,
                              zone=ZoneType.BATTLEFIELD,
                              characteristics=cd.characteristics, card_def=cd)
        evs = g.emit(Event(type=EventType.PHASE_START,
                           payload={"phase": "upkeep" if kind == "UPKEEP"
                                    else "end_step", "player": p1.id}))
    elif kind == "ATTACK":
        obj = g.create_object(name=name, owner_id=p1.id,
                              zone=ZoneType.BATTLEFIELD,
                              characteristics=cd.characteristics, card_def=cd)
        evs = g.emit(Event(type=EventType.ATTACK_DECLARED,
                           payload={"attacker_id": obj.id, "attacker": obj.id,
                                    "defender": p2.id}))
    elif kind == "DAMAGE":
        obj = g.create_object(name=name, owner_id=p1.id,
                              zone=ZoneType.BATTLEFIELD,
                              characteristics=cd.characteristics, card_def=cd)
        evs = g.emit(Event(type=EventType.DAMAGE,
                           payload={"source": obj.id, "target": p2.id,
                                    "amount": 2, "is_combat": True}))
    elif kind == "DEATH":
        obj = g.create_object(name=name, owner_id=p1.id,
                              zone=ZoneType.BATTLEFIELD,
                              characteristics=cd.characteristics, card_def=cd)
        evs = g.emit(Event(type=EventType.ZONE_CHANGE,
                           payload={"object_id": obj.id,
                                    "from_zone_type": ZoneType.BATTLEFIELD,
                                    "to_zone_type": ZoneType.GRAVEYARD}))
    else:
        return None
    ride = _TRIGGER_RIDE_EVENT.get(kind, set())
    out, stripped = [], dict.fromkeys(ride, False)
    for e in evs:
        nm = e.type.name
        # drop exactly ONE instance of the ride event we emitted ourselves
        if nm in ride and not stripped[nm]:
            stripped[nm] = True
            continue
        out.append(nm)
    return out


# ---------------------------------------------------------------------------
# build per-card test functions
# ---------------------------------------------------------------------------
WIRED = [n for n, cd in TEMPORAL_HORIZONS_CARDS.items()
         if getattr(cd, "setup_interceptors", None)
         or getattr(cd, "setup_in_graveyard", None)]


def _make_test(name):
    def _test():
        cd = TEMPORAL_HORIZONS_CARDS[name]
        # registration must not raise
        g, p1, _ = _new_game()
        obj = g.create_object(name=name, owner_id=p1.id,
                              zone=ZoneType.BATTLEFIELD,
                              characteristics=cd.characteristics, card_def=cd)
        ints = cd.setup_interceptors(obj, g.state)
        assert ints, f"{name}: setup_interceptors returned no interceptors"

        if name in SKIPPED_CARDS:
            return  # registration-only

        kind, has_query, _ = _classify(name)

        if kind == "STATIC":
            assert has_query, (
                f"{name}: classified static but no QUERY interceptor "
                f"registered")
            return

        if kind == "EXOTIC":
            # Trigger fires on a non-primary event the generic harness can't
            # construct deterministically. Still require it be a REACT/
            # TRANSFORM triggered interceptor (registration sanity).
            assert any(i.priority in REACTISH for i in ints), (
                f"{name}: exotic trigger but no REACT/TRANSFORM interceptor")
            return

        effects = _emit_canonical(name, kind)
        assert effects is not None, (
            f"{name}: could not fire canonical {kind} trigger")
        assert len(effects) >= 1, (
            f"{name}: {kind} trigger fired but emitted NO effect events "
            f"(depths stub — effect_fn returns []). text={cd.text!r}")
        # Modal ("choose one") / conditional ("if you can't … instead") cards
        # legitimately resolve to one of several effect types depending on the
        # chosen mode / met branch. For those, the depths guard above is the
        # correct assertion; pinning a single EventType would be wrong.
        if name in _MODAL_CONDITIONAL:
            return
        expected = _expected_effects(cd.text)
        if expected:
            assert any(e in expected for e in effects), (
                f"{name}: {kind} trigger emitted {effects} but text implies "
                f"one of {sorted(expected)}. text={cd.text!r}")

    _test.__name__ = "test_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    _test.__doc__ = f"{name}: canonical-trigger interceptor verification"
    return _test


for _n in WIRED:
    _fn = _make_test(_n)
    globals()[_fn.__name__] = _fn


if __name__ == "__main__":
    tests = sorted((k, v) for k, v in globals().items()
                   if k.startswith("test_") and callable(v))
    passed, failed, errors = [], [], []
    for tname, t in tests:
        try:
            t()
            passed.append(tname)
        except AssertionError as e:
            failed.append((tname, str(e)))
        except Exception as e:
            errors.append((tname, f"{type(e).__name__}: {e}"))
    print("\n=== Interceptor verification: temporal_horizons ===")
    print(f"  wired cards:  {len(WIRED)}")
    print(f"  tests run:    {len(tests)}")
    print(f"  passed:       {len(passed)}")
    print(f"  failed:       {len(failed)}")
    print(f"  errors:       {len(errors)}")
    print(f"  skipped(reg-only): {len(SKIPPED_CARDS)} (see SKIPPED_CARDS)")
    if failed:
        print("\n--- FAILURES ---")
        for tname, msg in failed:
            print(f"  {tname}: {msg}")
    if errors:
        print("\n--- ERRORS ---")
        for tname, msg in errors:
            print(f"  {tname}: {msg}")
    sys.exit(0 if not failed and not errors else 1)
