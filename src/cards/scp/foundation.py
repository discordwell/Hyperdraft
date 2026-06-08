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


def _stabilize_on_contain(n):
    # "Euclid Subject": a stabilizing containment — locking it re-secures loose material, rolling
    # the Total Breach clock back. A second, organic answer to the breach axis woven into the core
    # contain loop (the Foundation fights breach by doing its job), distinct from the vanilla Euclid.
    def _f(game, pid, obj):
        return scp.reduce_breach(game, n)
    return _f


def _purge_on_contain(n):
    # "Keter Horror": a violent containment — subduing it lets the Foundation strike, attritioning
    # the Insurgency's hand (feeds the soft-kill). Distinct from the Worldspine Wurm breach-bomb.
    def _f(game, pid, obj):
        iid = scp.insurgency_id(game.state)
        return scp.deal_damage(game, iid, n) if iid else []
    return _f


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


def _op_interrogation(game, pid):
    # "Enhanced Interrogation": the Black-File Bait closer — damage scales with how exposed the
    # Insurgency is, so a kill deck that has tagged them out can flatline a thin hand (burnout).
    iid = scp.insurgency_id(game.state)
    if iid is None:
        return []
    ir = scp.ensure_scp_state(game.state, iid)
    return scp.deal_damage(game, iid, max(1, int(ir.get("exposed", 0))))


def _op_containment_sweep(game, pid):
    # "Containment Sweep": the Foundation's answer to the breach axis — re-secures loosed material,
    # rolling Total Breach back down. Without this the breach-rush deck races an unopposed clock.
    return scp.reduce_breach(game, 5)


def _op_recovery(game, pid):
    # "Containment Recovery": recontainment — re-secure the highest-Value anomaly from the discard
    # straight onto a cell **1 advance from locking** (advancement caps at threshold-1; the big
    # value just means "as advanced as legal"). This is load-bearing: re-securing only part-way
    # gets the anomaly re-freed before it locks (a liberation-donating treadmill — measured 22%);
    # bringing it back near-locked lets the Foundation lock it next turn, ahead of the re-free, and
    # the archetype jumps to ~49%. Fallback: draw, so it's never dead when the discard has no anomaly.
    evs = scp.recover_anomaly(game, pid, 1, advancement=99)
    return evs if evs else scp.draw_cards(game, pid, 1)


def _op_draw(n):
    def _f(game, pid):
        return scp.draw_cards(game, pid, n)
    return _f


# --- identity passives ---
def _site19_passive(game, pid, obj):
    # Site-19 Command: a bigger ops room — max hand 6 instead of 5.
    scp.ensure_scp_state(game.state, pid)["max_hand"] = 6
    return []


def _overseer_passive(game, pid, obj):
    # Overseer Council: the soft-kill identity. Once the Insurgency is tagged (exposed), every
    # Foundation punishment — Amnestics, Interrogation, Sentry hits, trap bites — deals +1. Turns
    # the tag-then-burn (burnout) axis into a real win path for the bait deck. (No hand bonus.)
    scp.ensure_scp_state(game.state, pid)["damage_bonus"] = 1
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
    text="Euclid 4/2. When contained, reduce Total Breach by 2 (re-secure loose material).",
    on_contain=_stabilize_on_contain(2))

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
    text="Keter 5/3. If freed, Total Breach +5. When contained, deal 2 damage to the Insurgency.",
    on_contain=_purge_on_contain(2))

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

ENHANCED_INTERROGATION = make_operation(
    "Enhanced Interrogation", cost=2,
    text="Deal damage to the Insurgency equal to how exposed they are (minimum 1).",
    effect=_op_interrogation)

CONTAINMENT_SWEEP = make_operation(
    "Containment Sweep", cost=2,
    text="Reduce Total Breach by 5 (re-secure loosed anomalies).",
    effect=_op_containment_sweep)

CONTAINMENT_RECOVERY = make_operation(
    # Cost 3 (not 2): near-locked re-secure is a premium effect. At 2 it improves *every* Foundation
    # deck ~+5pt — an auto-include staple that homogenizes deckbuilding and tilts the faction. The
    # extra Funding taxes a lean splash (which can't always afford it) far more than the funded
    # recontainment build-around (still a ~47% pinnacle), turning a must-run into a *choice* — good
    # tech vs mill/steal, a dead-ish cantrip vs decks that don't disrupt your anomalies.
    "Containment Recovery", cost=3,
    text="Re-secure the highest-Value anomaly from your discard onto a cell, 1 advance from "
         "locking (behind your walls where one was freed). If your discard holds none, draw a card.",
    effect=_op_recovery)


# ===========================================================================
# IDENTITY
# ===========================================================================
SITE_19_COMMAND = make_identity(
    "Site-19 Command", scp.FOUNDATION,
    text="Identity. Your maximum hand size is 6.",
    passive=_site19_passive)

OVERSEER_COUNCIL = make_identity(
    "Overseer Council", scp.FOUNDATION,
    text="Identity. While the Insurgency is exposed, your damage to them is increased by 1.",
    passive=_overseer_passive)


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
FOUNDATION_OPERATIONS = [EMERGENCY_LOCKDOWN, REDACTION_ORDER, AMNESTICS, MANDATORY_AUDIT,
                         CONTAINMENT_RECOVERY,
                         ENHANCED_INTERROGATION, CONTAINMENT_SWEEP]
FOUNDATION_IDENTITIES = [SITE_19_COMMAND, OVERSEER_COUNCIL]

FOUNDATION_CARDS = (FOUNDATION_ANOMALIES + FOUNDATION_LAYERS
                    + FOUNDATION_ASSETS + FOUNDATION_OPERATIONS + FOUNDATION_IDENTITIES)
