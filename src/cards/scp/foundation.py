"""SCP: SECURE / CONTAIN / SUBVERT — Foundation card pool (the "Corp" side).

The Foundation builds hidden, defended containment cells, advances anomalies into
containment for points (primary win), and can soft-kill the Insurgency by exposing and
attritioning their rig (secondary win). Card types: ANOMALY (agenda), LAYER (ICE),
ASSET (persistent econ/utility), OPERATION (one-shot), IDENTITY.

Every card here is exercised end-to-end by tests/test_scp_cards.py (the effect gate for
this engine — /test-interceptors only understands MTG-style interceptor cards, not the
scp effect-callback model). Art/lore reuse from frontend/public/scp-art/ is wired in
Phase 5 (the frontend serializer); this module is mechanics only.

Effect-callback signatures (see src/engine/scp.py):
  on_contain(game, pid, obj)      on_free(game, insurgent_id, anomaly)
  on_access(game, insurgent_id, anomaly)   on_install(game, pid, obj)
  on_turn_start(game, pid, obj)   ability(game, pid, obj, target)
  effect(game, pid)               passive(game, pid, obj)
"""

from __future__ import annotations

from src.engine import scp
from src.engine.scp import (
    make_anomaly, make_layer, make_asset, make_operation, make_identity,
)


# ===========================================================================
# Effect closures (named for grep/fire-gate debugging)
# ===========================================================================
def _gain_funding(n):
    def _f(game, pid, obj):
        return scp.add_credits(game.state, pid, n)
    return _f


def _draw_on_contain(n):
    def _f(game, pid, obj):
        return scp.draw_cards(game, pid, n)
    return _f


def _expose_on_contain(game, pid, obj):
    # "Memetic Archive": locking it forces the Insurgency into the open.
    return scp.expose(game, 1)


def _trap_expose_and_trash(game, insurgent_id, anomaly):
    # "Cerebral Relay": a bait file — accessing it tags the cell and fries a tool.
    return scp.expose(game, 1) + scp.trash_a_tool(game)


def _trap_heavy_bite(game, insurgent_id, anomaly):
    # "Honeypot Cell": dressed up as a fat Euclid; punishes the greedy run hard.
    return scp.deal_damage(game, insurgent_id, 3)


# --- asset start-of-turn drips ---
def _turn_funding(n):
    def _f(game, pid, obj):
        return scp.add_credits(game.state, pid, n)
    return _f


# --- asset activated abilities ---
def _ability_expose(game, pid, obj, target):
    # "Mobile Task Force": trace → tag the Insurgency.
    return scp.expose(game, 1)


def _ability_draw(n):
    def _f(game, pid, obj, target):
        return scp.draw_cards(game, pid, n)
    return _f


# --- operations ---
def _op_reinforce_all(amount):
    def _f(game, pid):
        events = []
        r = scp.ensure_scp_state(game.state, pid)
        for cell in r["cells"]:
            for lid in cell["layers"]:
                layer = game.state.objects.get(lid)
                if layer is not None:
                    events.extend(scp.reinforce(game.state, layer, amount))
        for stack in r["centrals"].values():
            for lid in stack:
                layer = game.state.objects.get(lid)
                if layer is not None:
                    events.extend(scp.reinforce(game.state, layer, amount))
        return events
    return _f


def _op_redaction(game, pid):
    # If the Insurgency is exposed, fry a tool; otherwise expose them (set up next time).
    iid = scp.insurgency_id(game.state)
    ir = scp.ensure_scp_state(game.state, iid) if iid else {}
    if int(ir.get("exposed", 0)) > 0:
        return scp.trash_a_tool(game)
    return scp.expose(game, 1)


def _op_amnestics(game, pid):
    iid = scp.insurgency_id(game.state)
    return scp.deal_damage(game, iid, 1) if iid else []


def _op_draw(n):
    def _f(game, pid):
        return scp.draw_cards(game, pid, n)
    return _f


# --- identity passive ---
def _site19_passive(game, pid, obj):
    # Site-19 Command: a bigger ops room — max hand 6 instead of 5.
    scp.ensure_scp_state(game.state, pid)["max_hand"] = 6
    return []


# ===========================================================================
# ANOMALIES (agendas) — Threshold / Value.  Safe 3/1 · Euclid 4/2 · Keter 5/3
# ===========================================================================
SENTIENT_LOCKBOX = make_anomaly(
    "SCP-2451 Sentient Lockbox", 3, 1, cost=0,
    text="Safe 3/1. When contained, gain 2 Funding.",
    on_contain=_gain_funding(2))

SEALED_VAULT = make_anomaly(
    "SCP-1190 Sealed Vault", 3, 1, cost=0,
    text="Safe 3/1. When contained, draw a card.",
    on_contain=_draw_on_contain(1))

ANOMALOUS_SPECIMEN = make_anomaly(
    "SCP-0863 Anomalous Specimen", 4, 2, cost=0,
    text="Euclid 4/2.")

EUCLID_SUBJECT = make_anomaly(
    "SCP-1004 Euclid Subject", 4, 2, cost=0,
    text="Euclid 4/2.")

REALITY_BENDER = make_anomaly(
    "SCP-3001 Reality Bender", 4, 2, cost=1,
    text="Euclid 4/2. When contained, draw a card.",
    on_contain=_draw_on_contain(1))

MEMETIC_ARCHIVE = make_anomaly(
    "SCP-2776 Memetic Archive", 4, 2, cost=1,
    text="Euclid 4/2. When contained, expose the Insurgency.",
    on_contain=_expose_on_contain)

WORLDSPINE_WURM = make_anomaly(
    "SCP-FBN-9000 Worldspine Wurm", 5, 3, cost=1, breach_on_free=5,
    text="Keter 5/3. If freed, Total Breach +5 (catastrophic if loose).")

KETER_HORROR = make_anomaly(
    "SCP-3199 Keter Horror", 5, 3, cost=1, breach_on_free=5,
    text="Keter 5/3. If freed, Total Breach +5.")

CONTAINMENT_LEVIATHAN = make_anomaly(
    "SCP-169 Containment Leviathan", 5, 3, cost=2,
    text="Keter 5/3. When contained, gain 3 Funding.",
    on_contain=_gain_funding(3))

# --- Traps (decoys: value 0; they spring on access instead of being freed) ---
RELIQUARY_OF_BAD_IDEAS = make_anomaly(
    "SCP-2998 Reliquary of Bad Ideas", 3, 0, trap=True, cost=0,
    text="TRAP. Looks advanceable; on access, deal 2 damage.")

CEREBRAL_RELAY = make_anomaly(
    "SCP-2052 Cerebral Relay", 3, 0, trap=True, cost=1,
    text="TRAP. On access, expose the Insurgency and trash one of their tools.",
    on_access=_trap_expose_and_trash)

HONEYPOT_CELL = make_anomaly(
    "SCP-4011 Honeypot Cell", 4, 0, trap=True, cost=1,
    text="TRAP. Dressed as a fat Euclid; on access, deal 3 damage.",
    on_access=_trap_heavy_bite)


# ===========================================================================
# LAYERS (ICE) — type · strength / rez.  Barrier=end_run, Sentry=neutralize, Sensor=expose
# ===========================================================================
CONTAINMENT_FIELD = make_layer("Containment Field", "barrier", 3, 2,
                               text="Barrier 3/2. End the infiltration.")
BLAST_DOOR = make_layer("Blast Door", "barrier", 4, 4,
                        text="Barrier 4/4. End the infiltration.")
REINFORCED_BULKHEAD = make_layer("Reinforced Bulkhead", "barrier", 6, 6,
                                 text="Barrier 6/6. End the infiltration.")

SNIPER_NEST = make_layer("Sniper Nest", "sentry", 2, 2,
                         text="Sentry 2/2. Neutralize 1 operative (else 1 damage).")
RESPONSE_TEAM = make_layer("MTF Response Team", "sentry", 3, 3,
                           text="Sentry 3/3. Neutralize 1 operative (else 1 damage).")
KILL_ON_SIGHT = make_layer("Kill-on-Sight Order", "sentry", 5, 5, sub="damage2",
                           text="Sentry 5/5. Deal 2 damage.")

TRIPWIRE = make_layer("Tripwire Sensor", "sensor", 1, 1,
                      text="Sensor 1/1. Expose the Insurgency.")
SURVEILLANCE_GRID = make_layer("Surveillance Grid", "sensor", 2, 2,
                               text="Sensor 2/2. Expose the Insurgency.")
AMNESTIC_MIST = make_layer("Amnestic Mist", "sensor", 3, 4, sub="discard",
                           text="Sensor 3/4. The Insurgency discards a random card.")


# ===========================================================================
# ASSETS (persistent econ / utility)
# ===========================================================================
CONTAINMENT_BUDGET = make_asset(
    "Containment Budget", cost=1,
    text="At the start of your turn, gain 1 Funding.",
    on_turn_start=_turn_funding(1))

BLACK_SITE_FUNDING = make_asset(
    "Black Site Funding", cost=3,
    text="At the start of your turn, gain 2 Funding.",
    on_turn_start=_turn_funding(2))

MOBILE_TASK_FORCE = make_asset(
    "Mobile Task Force", cost=1,
    text="1 action, 1 Funding: expose the Insurgency (trace).",
    ability=_ability_expose, ability_ap=1, ability_cost=1)

SITE_DIRECTOR = make_asset(
    "Site Director", cost=2,
    text="1 action, 1 Funding: draw a card.",
    ability=_ability_draw(1), ability_ap=1, ability_cost=1)


# ===========================================================================
# OPERATIONS (one-shot)
# ===========================================================================
EMERGENCY_LOCKDOWN = make_operation(
    "Emergency Lockdown", cost=2,
    text="Permanently reinforce all your layers (+1 strength each).",
    effect=_op_reinforce_all(1))

REDACTION_ORDER = make_operation(
    "Redaction Order", cost=1,
    text="If the Insurgency is exposed, trash one of their tools; otherwise expose them.",
    effect=_op_redaction)

AMNESTICS = make_operation(
    "Class-A Amnestics", cost=1,
    text="Deal 1 damage to the Insurgency (discard a random card).",
    effect=_op_amnestics)

MANDATORY_AUDIT = make_operation(
    "Mandatory Audit", cost=2,
    text="Draw 2 cards.",
    effect=_op_draw(2))


# ===========================================================================
# IDENTITY
# ===========================================================================
SITE_19_COMMAND = make_identity(
    "Site-19 Command", scp.FOUNDATION,
    text="Identity. Your maximum hand size is 6.",
    passive=_site19_passive)


# ===========================================================================
# Pool aggregates
# ===========================================================================
FOUNDATION_ANOMALIES = [
    SENTIENT_LOCKBOX, SEALED_VAULT, ANOMALOUS_SPECIMEN, EUCLID_SUBJECT,
    REALITY_BENDER, MEMETIC_ARCHIVE, WORLDSPINE_WURM, KETER_HORROR,
    CONTAINMENT_LEVIATHAN, RELIQUARY_OF_BAD_IDEAS, CEREBRAL_RELAY, HONEYPOT_CELL,
]
FOUNDATION_LAYERS = [
    CONTAINMENT_FIELD, BLAST_DOOR, REINFORCED_BULKHEAD,
    SNIPER_NEST, RESPONSE_TEAM, KILL_ON_SIGHT,
    TRIPWIRE, SURVEILLANCE_GRID, AMNESTIC_MIST,
]
FOUNDATION_ASSETS = [CONTAINMENT_BUDGET, BLACK_SITE_FUNDING, MOBILE_TASK_FORCE, SITE_DIRECTOR]
FOUNDATION_OPERATIONS = [EMERGENCY_LOCKDOWN, REDACTION_ORDER, AMNESTICS, MANDATORY_AUDIT]
FOUNDATION_IDENTITIES = [SITE_19_COMMAND]

FOUNDATION_CARDS = (FOUNDATION_ANOMALIES + FOUNDATION_LAYERS
                    + FOUNDATION_ASSETS + FOUNDATION_OPERATIONS + FOUNDATION_IDENTITIES)
