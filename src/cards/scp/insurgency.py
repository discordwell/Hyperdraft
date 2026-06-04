"""SCP: SECURE / CONTAIN / SUBVERT — Chaos Insurgency card pool (the "Runner" side).

The Insurgency builds a rig of breakers + econ, infiltrates the Foundation's cells, and
frees/steals anomalies to bank Liberation points (primary win) or push the shared Total
Breach to catastrophe (secondary win). Nothing self-destructs — every point is taken by
acting on the Foundation. Card types: OPERATIVE (breaker), TOOL (persistent), EVENT
(one-shot), IDENTITY.

The run itself is the Infiltrate *action* (engine verb), not a card; events here feed it
(econ, breach, intel) rather than triggering runs, so AP accounting stays honest. Every
card is exercised by tests/test_scp_cards.py (the effect gate).
"""

from __future__ import annotations

from src.engine import scp
from src.engine.scp import make_operative, make_tool, make_event, make_identity


# ===========================================================================
# Effect closures
# ===========================================================================
def _gain_cells_event(n):
    def _f(game, pid):
        return scp.add_credits(game.state, pid, n)
    return _f


def _draw_event(n):
    def _f(game, pid):
        return scp.draw_cards(game, pid, n)
    return _f


def _mill_foundation(n):
    def _f(game, pid):
        fid = scp.foundation_id(game.state)
        return scp.mill(game, fid, n) if fid else []
    return _f


def _data_heist(game, pid):
    fid = scp.foundation_id(game.state)
    events = scp.mill(game, fid, 2) if fid else []
    events.extend(scp.draw_cards(game, pid, 1))
    return events


def _leak_to_press(game, pid):
    return scp.add_breach(game, 2)


def _anonymous_tip(game, pid):
    events = scp.add_breach(game, 1)
    events.extend(scp.draw_cards(game, pid, 1))
    return events


def _wetwork(game, pid):
    return scp.add_breach(game, 3)


# --- tool abilities / installs ---
def _tool_gain_cells(n):
    def _f(game, pid, obj, target):
        return scp.add_credits(game.state, pid, n)
    return _f


def _tool_draw(n):
    def _f(game, pid, obj, target):
        return scp.draw_cards(game, pid, n)
    return _f


def _stolen_credentials_install(game, pid, obj):
    return scp.add_credits(game.state, pid, 2)


# --- identity passives ---
def _black_queen_passive(game, pid, obj):
    # Black Queen Cell: the steal-engine identity. A well-funded cell that turns every
    # liberation into extra Liberation — makes the steal-tempo axis a real win path.
    r = scp.ensure_scp_state(game.state, pid)
    r["free_bonus_lib"] = 1
    return scp.add_credits(game.state, pid, 2)


def _sarkic_passive(game, pid, obj):
    # Sarkic Cult: the breach-doctrine identity. A doomsday flesh-cult that wants the anomalies
    # LOOSE — it doesn't steal for points, it floods the shared Total Breach clock. Every breach
    # event hits +1 (Leak/Wetwork/Anonymous Tip), turning the secondary "unleash" axis into this
    # deck's *primary* win path (no borrowed liberation engine). Modest econ so it still funds runs.
    r = scp.ensure_scp_state(game.state, pid)
    r["breach_event_bonus"] = 1
    return scp.add_credits(game.state, pid, 1)


def _black_lodge_passive(game, pid, obj):
    # Black Lodge Cell: the denial-doctrine identity. Doesn't steal anomalies for points or flood
    # the breach clock — it *destroys the Foundation's containment material* (mills their deck,
    # frees what's on the board) so they can never reach Containment 6 → win by Foundation collapse.
    # Every mill effect trashes +1 (Sabotage/Data Heist/Research), accelerating the supply kill.
    r = scp.ensure_scp_state(game.state, pid)
    r["mill_bonus"] = 1
    return scp.add_credits(game.state, pid, 1)


# ===========================================================================
# OPERATIVES (breakers) — breaks · power / boost
# ===========================================================================
INFILTRATOR = make_operative(
    "Field Infiltrator", "barrier", 2, boost=1, cost=1,
    text="Breaks Barriers. Power 2; +1 power per 1 Cell.")
MASTER_INFILTRATOR = make_operative(
    "Master Infiltrator", "barrier", 3, boost=1, cost=2,
    text="Breaks Barriers. Power 3; +1 power per 1 Cell.")

SABOTEUR = make_operative(
    "Saboteur", "sentry", 2, boost=2, cost=1,
    text="Breaks Sentries. Power 2; +1 power per 2 Cells.")
VETERAN_SABOTEUR = make_operative(
    "Veteran Saboteur", "sentry", 3, boost=1, cost=2,
    text="Breaks Sentries. Power 3; +1 power per 1 Cell.")

GHOST = make_operative(
    "Ghost", "sensor", 1, boost=1, cost=1,
    text="Breaks Sensors. Power 1; +1 power per 1 Cell.")
GHOST_IN_THE_MACHINE = make_operative(
    "Ghost in the Machine", "sensor", 2, boost=1, cost=2,
    text="Breaks Sensors. Power 2; +1 power per 1 Cell.")


# ===========================================================================
# TOOLS (persistent)
# ===========================================================================
BLACK_BUDGET = make_tool(
    "Black Budget", cost=1,
    text="1 action: gain 3 Cells.",
    ability=_tool_gain_cells(3), ability_ap=1, ability_cost=0)

SAFEHOUSE = make_tool(
    "Safehouse", cost=2,
    text="1 action, 1 Cell: draw a card.",
    ability=_tool_draw(1), ability_ap=1, ability_cost=1)

STOLEN_CREDENTIALS = make_tool(
    "Stolen Credentials", cost=1,
    text="When installed, gain 2 Cells.",
    on_install=_stolen_credentials_install)


# ===========================================================================
# EVENTS (one-shot)
# ===========================================================================
BLACK_MARKET = make_event("Black Market", cost=0,
                          text="Gain 2 Cells.", effect=_gain_cells_event(2))
COORDINATED_STRIKE = make_event("Coordinated Strike", cost=2,
                                text="Gain 4 Cells.", effect=_gain_cells_event(4))
EXTRACTION = make_event("Extraction", cost=1,
                        text="Draw 2 cards.", effect=_draw_event(2))
SABOTAGE = make_event("Sabotage", cost=1,
                      text="Trash the top 3 cards of the Foundation's deck.",
                      effect=_mill_foundation(3))
DATA_HEIST = make_event("Data Heist", cost=1,
                        text="Trash the top 2 of the Foundation's deck, then draw a card.",
                        effect=_data_heist)
LEAK_TO_THE_PRESS = make_event("Leak to the Press", cost=1,
                               text="Total Breach +2.", effect=_leak_to_press)
ANONYMOUS_TIP = make_event("Anonymous Tip", cost=1,
                           text="Total Breach +1, then draw a card.", effect=_anonymous_tip)
WETWORK = make_event("Wetwork", cost=2,
                     text="Total Breach +3.", effect=_wetwork)


# ===========================================================================
# IDENTITY
# ===========================================================================
BLACK_QUEEN_CELL = make_identity(
    "Black Queen Cell", scp.INSURGENCY,
    text="Identity. Begin with 2 extra Cells; each anomaly you free banks +1 bonus Liberation.",
    passive=_black_queen_passive)

SARKIC_CULT = make_identity(
    "Sarkic Cult", scp.INSURGENCY,
    text="Identity. Begin with 1 extra Cell; your Total Breach events add +1 Breach each.",
    passive=_sarkic_passive)

BLACK_LODGE_CELL = make_identity(
    "Black Lodge Cell", scp.INSURGENCY,
    text="Identity. Begin with 1 extra Cell; your mill effects trash +1 card each (deny the "
         "Foundation its containment supply).",
    passive=_black_lodge_passive)


# ===========================================================================
# Pool aggregates
# ===========================================================================
INSURGENCY_OPERATIVES = [
    INFILTRATOR, MASTER_INFILTRATOR, SABOTEUR, VETERAN_SABOTEUR,
    GHOST, GHOST_IN_THE_MACHINE,
]
INSURGENCY_TOOLS = [BLACK_BUDGET, SAFEHOUSE, STOLEN_CREDENTIALS]
INSURGENCY_EVENTS = [
    BLACK_MARKET, COORDINATED_STRIKE, EXTRACTION, SABOTAGE, DATA_HEIST,
    LEAK_TO_THE_PRESS, ANONYMOUS_TIP, WETWORK,
]
INSURGENCY_IDENTITIES = [BLACK_QUEEN_CELL, SARKIC_CULT, BLACK_LODGE_CELL]

INSURGENCY_CARDS = (INSURGENCY_OPERATIVES + INSURGENCY_TOOLS
                    + INSURGENCY_EVENTS + INSURGENCY_IDENTITIES)
