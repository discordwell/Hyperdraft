"""Effect gate for the scp card pool — every card is fired through the engine.

This is the scp equivalent of /test-interceptors: that harness only understands MTG-style
interceptor cards, so it can't see the scp effect-callback model. Instead we exercise each
card's actual effect through the real verbs (play/advance/contain/infiltrate/activate) and
assert the observable result moved — a card-level census against the "born dead" failure
mode (CLAUDE.md: a card isn't done until its effect actually fires).

Plus deck-legality checks (40 cards, Foundation anomaly density ≥ 18) and a full-setup smoke.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python3 -m pytest tests/test_scp_cards.py -q
"""

import pytest

from src.engine.game import Game
from src.engine import scp
from src.engine.types import ZoneType
from src.cards.scp import foundation as F
from src.cards.scp import insurgency as I
from src.cards.scp import decks as D


# --------------------------------------------------------------------------- helpers
def _setup():
    g = Game(mode="scp")
    f = g.add_player("Foundation")
    i = g.add_player("Insurgency")
    scp.setup_scp_player(g, f, scp.FOUNDATION)
    scp.setup_scp_player(g, i, scp.INSURGENCY)
    return g, f, i


def _hand(g, pid, cd):
    return g.create_object(name=cd.name, owner_id=pid, zone=ZoneType.HAND,
                           characteristics=cd.characteristics, card_def=cd)


def _deck_card(g, pid, cd):
    return g.create_object(name=cd.name, owner_id=pid, zone=ZoneType.LIBRARY,
                           characteristics=cd.characteristics, card_def=cd)


def _ready(g, pid, ap=20, credits=40):
    r = scp.ensure_scp_state(g.state, pid)
    r["ap"], r["credits"] = ap, credits
    return r


def _play(g, pid, cd, **kw):
    obj = _hand(g, pid, cd)
    ok, msg, _ = scp.play_card(g, pid, obj.id, **kw)
    assert ok, f"{cd.name}: {msg}"
    return obj


def _last_cell(g, pid):
    return scp.ensure_scp_state(g.state, pid)["cells"][-1]


_REAL_ANOMALIES = [c for c in F.FOUNDATION_ANOMALIES if not getattr(c, "scp_trap", False)]
_TRAPS = [c for c in F.FOUNDATION_ANOMALIES if getattr(c, "scp_trap", False)]
_id = lambda cd: cd.name  # readable parametrize ids


# =========================================================================== anomalies
@pytest.mark.parametrize("cd", _REAL_ANOMALIES, ids=_id)
def test_real_anomaly_advances_and_scores(cd):
    g, f, i = _setup()
    _ready(g, f.id)
    obj = _play(g, f.id, cd)
    threshold = int(getattr(cd, "scp_threshold"))
    for _ in range(threshold):
        _ready(g, f.id)
        ok, m, _ = scp.advance(g, f.id, obj.id)
        assert ok, m
    fr = scp.ensure_scp_state(g.state, f.id)
    _ready(g, f.id)
    before = fr["containment_points"]
    ok, m, _ = scp.contain(g, f.id, obj.id)
    assert ok, m
    assert fr["containment_points"] == before + int(getattr(cd, "scp_value"))
    assert getattr(obj.state, "scp_status") == "contained"


def test_oncontain_side_effects():
    # Funding gainers
    for cd, amt in [(F.SENTIENT_LOCKBOX, 2), (F.CONTAINMENT_LEVIATHAN, 3)]:
        g, f, i = _setup()
        _ready(g, f.id)
        obj = _play(g, f.id, cd)
        for _ in range(int(getattr(cd, "scp_threshold"))):
            _ready(g, f.id)
            scp.advance(g, f.id, obj.id)
        r = _ready(g, f.id, credits=40)
        scp.contain(g, f.id, obj.id)
        assert r["credits"] == 40 + amt, f"{cd.name} on-contain Funding"
    # Draw gainers — assert the library shrank (clean of the hand confound)
    for cd in [F.SEALED_VAULT, F.REALITY_BENDER]:
        g, f, i = _setup()
        for _ in range(3):
            _deck_card(g, f.id, F.ANOMALOUS_SPECIMEN)
        _ready(g, f.id)
        obj = _play(g, f.id, cd)
        for _ in range(int(getattr(cd, "scp_threshold"))):
            _ready(g, f.id)
            scp.advance(g, f.id, obj.id)
        lib_before = len(scp.deck_ids(g.state, f.id))
        _ready(g, f.id)
        scp.contain(g, f.id, obj.id)
        assert len(scp.deck_ids(g.state, f.id)) == lib_before - 1, f"{cd.name} on-contain draw"
    # Memetic Archive — exposes on contain
    g, f, i = _setup()
    _ready(g, f.id)
    obj = _play(g, f.id, F.MEMETIC_ARCHIVE)
    for _ in range(int(getattr(F.MEMETIC_ARCHIVE, "scp_threshold"))):
        _ready(g, f.id)
        scp.advance(g, f.id, obj.id)
    _ready(g, f.id)
    scp.contain(g, f.id, obj.id)
    assert scp.ensure_scp_state(g.state, i.id)["exposed"] >= 1


@pytest.mark.parametrize("cd", [F.WORLDSPINE_WURM, F.KETER_HORROR], ids=_id)
def test_keter_breach_on_free_override(cd):
    g, f, i = _setup()
    _ready(g, f.id)
    obj = _play(g, f.id, cd)
    cell = _last_cell(g, f.id)
    fr = scp.ensure_scp_state(g.state, f.id)
    ir = _ready(g, i.id, ap=3, credits=10)
    scp.infiltrate(g, i.id, ("cell", cell["id"]))  # undefended → free
    assert ir["liberation_points"] == int(getattr(cd, "scp_value")), f"{cd.name} freed"
    assert fr["total_breach"] == 5, f"{cd.name} breach_on_free override"


@pytest.mark.parametrize("cd", _TRAPS, ids=_id)
def test_trap_springs_punishes_without_liberation(cd):
    g, f, i = _setup()
    _ready(g, f.id)
    obj = _play(g, f.id, cd)
    cell = _last_cell(g, f.id)
    # Fat hand to absorb damage + a tool for Cerebral Relay to trash.
    for _ in range(4):
        _hand(g, i.id, I.BLACK_MARKET)
    tool = _hand(g, i.id, I.STOLEN_CREDENTIALS)
    _ready(g, i.id)
    scp.play_card(g, i.id, tool.id)
    ir = _ready(g, i.id, ap=3, credits=10)
    hand_before = len(scp.hand_ids(g.state, i.id))
    exposed_before = ir["exposed"]
    rig_before = len(ir["rig"])
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 0, f"{cd.name}: a trap grants no Liberation"
    assert cell["anomaly"] is None, f"{cd.name}: trap is consumed"
    punished = (len(scp.hand_ids(g.state, i.id)) < hand_before
                or ir["exposed"] > exposed_before
                or len(ir["rig"]) < rig_before)
    assert punished, f"{cd.name}: a trap must punish on access"


# =========================================================================== layers
@pytest.mark.parametrize("cd", F.FOUNDATION_LAYERS, ids=_id)
def test_layer_subroutine_fires(cd):
    g, f, i = _setup()
    _ready(g, f.id)
    anomaly = _play(g, f.id, F.ANOMALOUS_SPECIMEN)
    cell = _last_cell(g, f.id)
    _ready(g, f.id)
    _play(g, f.id, cd, target=("cell", cell["id"]))
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["credits"] = 30  # enough to rez
    for _ in range(4):
        _hand(g, i.id, I.BLACK_MARKET)
    ir = _ready(g, i.id, ap=3, credits=0)  # no breaker, no boost
    ltype = getattr(cd, "scp_ltype")
    hand_before = len(scp.hand_ids(g.state, i.id))
    exposed_before = ir["exposed"]
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    if ltype == "barrier":
        assert ir["liberation_points"] == 0, f"{cd.name} should end the run"
        assert cell["anomaly"] == anomaly.id, f"{cd.name}: anomaly stays behind the wall"
    elif ltype == "sentry":
        assert len(scp.hand_ids(g.state, i.id)) < hand_before, f"{cd.name} should deal damage"
    else:  # sensor
        assert (ir["exposed"] > exposed_before
                or len(scp.hand_ids(g.state, i.id)) < hand_before), f"{cd.name} should expose/discard"


# =========================================================================== operatives
@pytest.mark.parametrize("cd", I.INSURGENCY_OPERATIVES, ids=_id)
def test_operative_breaks_its_layer_type(cd):
    g, f, i = _setup()
    _ready(g, f.id)
    _play(g, f.id, F.ANOMALOUS_SPECIMEN)
    cell = _last_cell(g, f.id)
    ltype = getattr(cd, "scp_breaks")
    power = int(getattr(cd, "scp_power"))
    # A matching layer at strength == power, so it breaks with zero boost — isolates matching.
    _ready(g, f.id)
    wall = scp.make_layer(f"Test {ltype} wall", ltype, power, 1)
    _play(g, f.id, wall, target=("cell", cell["id"]))
    scp.ensure_scp_state(g.state, f.id)["credits"] = 30
    _ready(g, i.id)
    _play(g, i.id, cd)
    ir = _ready(g, i.id, ap=3, credits=30)
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 2, f"{cd.name} should break {ltype} and free the anomaly"


# =========================================================================== assets
def test_assets_fire():
    for cd, amt in [(F.CONTAINMENT_BUDGET, 1), (F.BLACK_SITE_FUNDING, 2)]:
        g, f, i = _setup()
        r = _ready(g, f.id)
        _play(g, f.id, cd)
        before = r["credits"]
        scp.fire_turn_start_assets(g, f.id)
        assert r["credits"] == before + amt, f"{cd.name} start-of-turn Funding"
    # Mobile Task Force — activated trace exposes
    g, f, i = _setup()
    _ready(g, f.id)
    obj = _play(g, f.id, F.MOBILE_TASK_FORCE)
    _ready(g, f.id)
    ok, m, _ = scp.activate_ability(g, f.id, obj.id)
    assert ok, m
    assert scp.ensure_scp_state(g.state, i.id)["exposed"] >= 1
    # Site Director — activated draw (library shrinks)
    g, f, i = _setup()
    _ready(g, f.id)
    _deck_card(g, f.id, F.ANOMALOUS_SPECIMEN)
    obj = _play(g, f.id, F.SITE_DIRECTOR)
    _ready(g, f.id)
    lib_before = len(scp.deck_ids(g.state, f.id))
    ok, m, _ = scp.activate_ability(g, f.id, obj.id)
    assert ok, m
    assert len(scp.deck_ids(g.state, f.id)) == lib_before - 1


# =========================================================================== operations
def test_operations_fire():
    # Emergency Lockdown reinforces installed layers (+1 each)
    g, f, i = _setup()
    _ready(g, f.id)
    _play(g, f.id, F.ANOMALOUS_SPECIMEN)
    cell = _last_cell(g, f.id)
    _ready(g, f.id)
    layer = _play(g, f.id, F.BLAST_DOOR, target=("cell", cell["id"]))
    _ready(g, f.id)
    _play(g, f.id, F.EMERGENCY_LOCKDOWN)
    assert int(getattr(layer.state, "scp_strength_mod", 0)) == 1

    # Redaction Order without exposure → exposes
    g, f, i = _setup()
    _ready(g, f.id)
    _play(g, f.id, F.REDACTION_ORDER)
    assert scp.ensure_scp_state(g.state, i.id)["exposed"] >= 1

    # Redaction Order with exposure + a tool → trashes the tool
    g, f, i = _setup()
    ir = scp.ensure_scp_state(g.state, i.id)
    ir["exposed"] = 1
    tool = _hand(g, i.id, I.STOLEN_CREDENTIALS)
    _ready(g, i.id)
    scp.play_card(g, i.id, tool.id)
    assert tool.id in ir["rig"]
    _ready(g, f.id)
    _play(g, f.id, F.REDACTION_ORDER)
    assert tool.id not in ir["rig"]

    # Amnestics damages the Insurgency (discards a card)
    g, f, i = _setup()
    _hand(g, i.id, I.BLACK_MARKET)
    _ready(g, f.id)
    _play(g, f.id, F.AMNESTICS)
    assert len(scp.hand_ids(g.state, i.id)) == 0

    # Mandatory Audit draws 2 (library shrinks by 2)
    g, f, i = _setup()
    _ready(g, f.id)
    for _ in range(3):
        _deck_card(g, f.id, F.ANOMALOUS_SPECIMEN)
    lib_before = len(scp.deck_ids(g.state, f.id))
    _play(g, f.id, F.MANDATORY_AUDIT)
    assert len(scp.deck_ids(g.state, f.id)) == lib_before - 2


def test_interrogation_scales_with_exposure_and_can_burn_out():
    # Scales with exposure: exposed 3 → 3 damage (3 cards discarded).
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, i.id)["exposed"] = 3
    for _ in range(4):
        _hand(g, i.id, I.BLACK_MARKET)
    _ready(g, f.id)
    _play(g, f.id, F.ENHANCED_INTERROGATION)
    assert len(scp.hand_ids(g.state, i.id)) == 1, "exposed 3 → 3 cards discarded"

    # Floor: even unexposed it deals the minimum 1.
    g, f, i = _setup()
    _hand(g, i.id, I.BLACK_MARKET); _hand(g, i.id, I.EXTRACTION)
    _ready(g, f.id)
    _play(g, f.id, F.ENHANCED_INTERROGATION)
    assert len(scp.hand_ids(g.state, i.id)) == 1, "minimum 1 damage even with no exposure"

    # Burnout: a tagged-out Insurgency with a thin hand gets flatlined (the soft-kill axis is live).
    g, f, i = _setup()
    ir = scp.ensure_scp_state(g.state, i.id); ir["exposed"] = 3
    _hand(g, i.id, I.BLACK_MARKET); _hand(g, i.id, I.EXTRACTION)
    _ready(g, f.id)
    _play(g, f.id, F.ENHANCED_INTERROGATION)
    assert ir.get("burned_out") is True, "3 damage vs a 2-card hand burns them out"
    assert g.state.players[i.id].has_lost
    assert not g.state.players[f.id].has_lost


# =========================================================================== tools
def test_tools_fire():
    # Black Budget — activated +3 Cells
    g, f, i = _setup()
    _ready(g, i.id)
    obj = _play(g, i.id, I.BLACK_BUDGET)
    r = _ready(g, i.id, credits=5)
    ok, m, _ = scp.activate_ability(g, i.id, obj.id)
    assert ok, m
    assert r["credits"] == 5 + 3
    # Safehouse — activated draw (1 Cell, library shrinks)
    g, f, i = _setup()
    _deck_card(g, i.id, I.BLACK_MARKET)
    _ready(g, i.id)
    obj = _play(g, i.id, I.SAFEHOUSE)
    _ready(g, i.id)
    lib_before = len(scp.deck_ids(g.state, i.id))
    ok, m, _ = scp.activate_ability(g, i.id, obj.id)
    assert ok, m
    assert len(scp.deck_ids(g.state, i.id)) == lib_before - 1
    # Stolen Credentials — on-install +2 Cells (costs 1 to play → net 5-1+2 = 6)
    g, f, i = _setup()
    r = _ready(g, i.id, credits=5)
    scp.play_card(g, i.id, _hand(g, i.id, I.STOLEN_CREDENTIALS).id)
    assert r["credits"] == 6, "Stolen Credentials: paid 1, on-install gained 2"


# =========================================================================== events
def test_insurgency_events_fire():
    # Econ: assert exact credits after = before - cost + gain
    for cd, gain in [(I.BLACK_MARKET, 2), (I.COORDINATED_STRIKE, 4)]:
        g, f, i = _setup()
        r = _ready(g, i.id, credits=10)
        cost = int(getattr(cd, "scp_cost", 0))
        _play(g, i.id, cd)
        assert r["credits"] == 10 - cost + gain, f"{cd.name} Cells"
    # Breach: total_breach is clean of cost
    for cd, amt in [(I.LEAK_TO_THE_PRESS, 2), (I.WETWORK, 3), (I.ANONYMOUS_TIP, 1)]:
        g, f, i = _setup()
        _ready(g, i.id)
        fr = scp.ensure_scp_state(g.state, f.id)
        before = fr["total_breach"]
        _play(g, i.id, cd)
        assert fr["total_breach"] == before + amt, f"{cd.name} Total Breach"
    # Draw: insurgency library shrinks by the draw count
    for cd, drew in [(I.EXTRACTION, 2), (I.ANONYMOUS_TIP, 1), (I.DATA_HEIST, 1)]:
        g, f, i = _setup()
        for _ in range(3):
            _deck_card(g, i.id, I.BLACK_MARKET)
        _ready(g, i.id)
        lib_before = len(scp.deck_ids(g.state, i.id))
        _play(g, i.id, cd)
        assert len(scp.deck_ids(g.state, i.id)) == lib_before - drew, f"{cd.name} draw"
    # Mill: foundation library shrinks
    for cd, milled in [(I.SABOTAGE, 3), (I.DATA_HEIST, 2)]:
        g, f, i = _setup()
        for _ in range(5):
            _deck_card(g, f.id, F.ANOMALOUS_SPECIMEN)
        _ready(g, i.id)
        lib_before = len(scp.deck_ids(g.state, f.id))
        _play(g, i.id, cd)
        assert len(scp.deck_ids(g.state, f.id)) == lib_before - milled, f"{cd.name} mill"


# =========================================================================== identities
def test_identities_apply_at_setup():
    g = Game(mode="scp")
    f = g.add_player("F")
    i = g.add_player("I")
    fdeck = [F.ANOMALOUS_SPECIMEN] * 12
    ideck = [I.INFILTRATOR] * 12
    scp.setup_scp_game(g, f, i, foundation_deck=fdeck, insurgency_deck=ideck,
                         foundation_identity=F.SITE_19_COMMAND,
                         insurgency_identity=I.BLACK_QUEEN_CELL)
    assert scp.ensure_scp_state(g.state, f.id)["max_hand"] == 6, "Site-19 Command"
    ir = scp.ensure_scp_state(g.state, i.id)
    assert ir["credits"] == scp.STARTING_CREDITS + 2, "Black Queen Cell starting Cells"
    assert ir["free_bonus_lib"] == 1, "Black Queen Cell steal-engine bonus"


def test_black_queen_cell_banks_bonus_liberation_per_free():
    # The steal-engine identity: each freed anomaly banks value + 1 Liberation.
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, i.id)["free_bonus_lib"] = 1  # what the identity sets
    _ready(g, f.id)
    obj = _play(g, f.id, F.ANOMALOUS_SPECIMEN)  # value 2, undefended
    cell = _last_cell(g, f.id)
    ir = _ready(g, i.id, ap=3, credits=10)
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 3, "value 2 + 1 steal-engine bonus"


def test_archetype_identities_apply_at_setup():
    # The two new archetype-aligned identities set their engine flags + econ at install.
    g = Game(mode="scp")
    f = g.add_player("F"); i = g.add_player("I")
    scp.setup_scp_game(g, f, i, foundation_deck=[F.ANOMALOUS_SPECIMEN] * 12,
                        insurgency_deck=[I.INFILTRATOR] * 12,
                        foundation_identity=F.OVERSEER_COUNCIL, insurgency_identity=I.SARKIC_CULT)
    assert scp.ensure_scp_state(g.state, f.id)["damage_bonus"] == 1, "Overseer Council damage engine"
    ir = scp.ensure_scp_state(g.state, i.id)
    assert ir["breach_event_bonus"] == 1, "Sarkic Cult breach engine"
    assert ir["credits"] == scp.STARTING_CREDITS + 1, "Sarkic Cult +1 Cell"


def test_sarkic_cult_boosts_breach_events():
    # Breach-doctrine identity: every Total Breach event hits +1 (and ONLY breach events).
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, i.id)["breach_event_bonus"] = 1  # what the identity sets
    _ready(g, i.id)
    fr = scp.ensure_scp_state(g.state, f.id)
    before = fr["total_breach"]
    _play(g, i.id, I.LEAK_TO_THE_PRESS)        # base +2
    assert fr["total_breach"] == before + 3, "Leak +2 → +3 under Sarkic"
    _play(g, i.id, I.WETWORK)                  # base +3
    assert fr["total_breach"] == before + 3 + 4, "Wetwork +3 → +4 under Sarkic"


def test_overseer_council_boosts_damage_only_while_exposed():
    # Kill identity: +1 damage, but ONLY while the Insurgency is exposed (tag-then-burn).
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["damage_bonus"] = 1  # what the identity sets
    scp.ensure_scp_state(g.state, i.id)["exposed"] = 1
    for _ in range(4):
        _hand(g, i.id, I.BLACK_MARKET)
    _ready(g, f.id)
    _play(g, f.id, F.AMNESTICS)                 # base 1 damage
    assert len(scp.hand_ids(g.state, i.id)) == 4 - 2, "Amnestics 1 → 2 damage while exposed"

    # Not exposed → no bonus (the engine flag is set but exposure gates it).
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["damage_bonus"] = 1
    for _ in range(4):
        _hand(g, i.id, I.BLACK_MARKET)          # exposed == 0
    _ready(g, f.id)
    _play(g, f.id, F.AMNESTICS)
    assert len(scp.hand_ids(g.state, i.id)) == 4 - 1, "no bonus when not exposed"


def test_containment_sweep_rolls_back_the_breach_clock():
    # The Foundation's breach counterplay: roll Total Breach back down (clamped at 0).
    g, f, i = _setup()
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["total_breach"] = 12
    _ready(g, f.id)
    _play(g, f.id, F.CONTAINMENT_SWEEP)
    assert fr["total_breach"] == 7, "Containment Sweep reduces Total Breach by 5"
    fr["total_breach"] = 3
    _play(g, f.id, F.CONTAINMENT_SWEEP)
    assert fr["total_breach"] == 0, "Sweep clamps at 0 (no negative breach)"


# =========================================================================== decks
def test_all_decks_are_legal():
    for label, (ident, builder) in D.SCP_DECKS.items():
        deck = builder()
        assert len(deck) == D.DECK_SIZE, f"{label}: {len(deck)} cards (want {D.DECK_SIZE})"
        assert ident is not None, f"{label}: missing identity"


def test_foundation_decks_meet_anomaly_density():
    for label, (ident, builder) in D.SCP_FOUNDATION_DECKS.items():
        dens = D.anomaly_density(builder())
        assert dens >= D.MIN_ANOMALY_DENSITY, f"{label}: density {dens} < {D.MIN_ANOMALY_DENSITY}"


def test_full_deck_setup_smoke():
    g = Game(mode="scp")
    f = g.add_player("F")
    i = g.add_player("I")
    fident, fbuild = D.SCP_FOUNDATION_DECKS["SCP_site19_containment"]
    iident, ibuild = D.SCP_INSURGENCY_DECKS["SCP_black_queen_cell"]
    scp.setup_scp_game(g, f, i, foundation_deck=fbuild(), insurgency_deck=ibuild(),
                         foundation_identity=fident, insurgency_identity=iident)
    assert len(scp.hand_ids(g.state, f.id)) == 5
    assert len(scp.hand_ids(g.state, i.id)) == 5
    assert len(scp.deck_ids(g.state, f.id)) == D.DECK_SIZE - 5
    assert len(scp.deck_ids(g.state, i.id)) == D.DECK_SIZE - 5


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
