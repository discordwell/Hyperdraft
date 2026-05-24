"""Activated-ability dispatcher tests for the Clankers engine.

Covers gap #1 from ``engine_gaps_clan.md``: ``clankers.activate_ability``
must read the descriptor written by ``make_weapon_activated``, pay the
declared cost (compute pool decrement and/or self-exhaust), and invoke
the descriptor's ``effect_fn``. The AI adapter must surface affordable
activations as legal actions under medium and hard tiers.

This is the regression test that catches future drift on the activated-
ability primitive. Three specific CLAN cards exercise the cost shape:
  * Recoil Mount (FORGE / BULWARK): compute=1, exhaust=True, deals 1 damage
  * Memory Buffer (ETHOS): compute=2, exhaust=True, no damage (utility)
  * Coolant Cradle (BULWARK): scrap=1 (paid inside effect_fn), exhaust=False

Run directly:
    PYTHONPATH=. python tests/test_clankers_activated_abilities.py
"""

from __future__ import annotations

import pytest

from src.engine.types import (
    Event,
    EventType,
    Player,
    Zone,
    ZoneType,
)


pytestmark = pytest.mark.smoke


def _build_minimal_clankers_game():
    """Build a two-player Clankers Game + minimal zone setup.

    Returns (game, state). Idempotent — runs ``_init_clankers_state``,
    seeds compute / workshop pools, and creates per-player zones so the
    pipeline can dispatch.
    """
    from src.engine.clankers import _init_clankers_state
    from src.engine.game import Game

    g = Game()
    g.state.players["p1"] = Player(id="p1", name="p1")
    g.state.players["p2"] = Player(id="p2", name="p2")
    per_player_zones = (
        ZoneType.HAND,
        ZoneType.COMMAND,
        ZoneType.LIBRARY,
        ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ZoneType.CLANKERS_SCRAP_HEAP,
    )
    for pid in ("p1", "p2"):
        for zt in per_player_zones:
            key = f"{zt.name.lower()}_{pid}"
            if key not in g.state.zones:
                g.state.zones[key] = Zone(type=zt, owner=pid)

    _init_clankers_state(g.state)
    for pid in ("p1", "p2"):
        g.state.clankers_workshop_integrity[pid] = 25
        g.state.clankers_compute_pool[pid] = 5
        g.state.clankers_compute_cap[pid] = 10
        g.state.clankers_scrap_pool[pid] = 3
        g.state.clankers_refill_used[pid] = False
        g.state.clankers_structures[pid] = []
        g.state.clankers_assemblies[pid] = []
    return g


def _place_card_on_floor(game, card_def, owner_id: str):
    """Create the card directly on a player's Assembly Floor with
    ``setup_interceptors`` invoked.

    Mirrors what ``play_card_from_hand`` does for the "lands as weapon"
    case — drops the object into the floor zone, calls setup, and records
    it in ``state.clankers_assemblies`` (chassis) or returns the obj
    (parts attach via attach_part separately).

    Note: ``Game.create_object`` doesn't know how to compute zone keys for
    ``CLANKERS_ASSEMBLY_FLOOR``, so we manually append the object id to
    the per-player floor zone after creation. We also seed
    ``state.clankers_assemblies`` for chassis so the AI's
    ``_controlled_chassis`` fast-path picks them up.
    """
    from src.engine.types import CardType
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    # Append to the per-player floor zone (engine doesn't auto-route
    # CLANKERS_ASSEMBLY_FLOOR in Game._get_zone_key).
    floor_key = f"clankers_assembly_floor_{owner_id}"
    floor = game.state.zones.get(floor_key)
    if floor is not None and obj.id not in floor.objects:
        floor.objects.append(obj.id)
    # If chassis, also record it in clankers_assemblies (engine tracks this).
    types = (card_def.characteristics.types if card_def.characteristics else set()) or set()
    if CardType.CLANKERS_CHASSIS in types:
        game.state.clankers_assemblies.setdefault(owner_id, []).append(obj.id)
    return obj


# ---------------------------------------------------------------------------
# Engine-level activate_ability tests
# ---------------------------------------------------------------------------

def test_activate_recoil_mount_pays_compute_exhausts_and_deals_damage():
    """Recoil Mount: 1 compute, exhaust self -> 1 CLANKERS_COMBAT_DAMAGE event.

    Verifies:
      - compute pool decremented by 1
      - source.state.tapped = True after activation
      - one CLANKERS_COMBAT_DAMAGE event emitted with amount=1
      - CLANKERS_ACTIVATE marker present
    """
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT
    from src.engine.clankers import activate_ability

    g = _build_minimal_clankers_game()
    state = g.state
    # Drop Recoil Mount as a solo part for p1.
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")
    # Build a target chassis on p2's floor for the damage event.
    from src.cards.clankers.CLAN.clan_forge import SALVAGER_SEVEN
    target_chassis = _place_card_on_floor(g, SALVAGER_SEVEN, "p2")

    pool_before = state.clankers_compute_pool["p1"]
    tapped_before = bool(weapon.state.tapped)

    events = activate_ability(
        state, "p1", weapon.id,
        ability_index=0,
        targets=[target_chassis.id],
    )

    assert events, "activate_ability returned no events"
    assert state.clankers_compute_pool["p1"] == pool_before - 1, (
        f"compute pool should be {pool_before - 1}, got "
        f"{state.clankers_compute_pool['p1']}"
    )
    assert weapon.state.tapped is True, (
        "exhaust_self=True should set source.state.tapped"
    )
    # Find the activation marker.
    markers = [e for e in events if e.type == EventType.CLANKERS_ACTIVATE]
    assert markers, "CLANKERS_ACTIVATE marker missing from events"
    # Find the damage event.
    damages = [e for e in events if e.type == EventType.CLANKERS_COMBAT_DAMAGE]
    assert damages, (
        f"Expected CLANKERS_COMBAT_DAMAGE, got types: "
        f"{[e.type.name for e in events]}"
    )
    assert damages[0].payload.get("amount") == 1
    assert damages[0].payload.get("defender_id") == target_chassis.id


def test_activate_memory_buffer_pays_compute_exhausts_with_utility_effect():
    """Memory Buffer: 2 compute, exhaust self -> recur a Transient from scrap.

    Verifies cost is paid even when the effect_fn returns []. (Memory
    Buffer returns [] when no Transient is in the scrap heap; cost is
    still paid because the descriptor declares it.)
    """
    from src.cards.clankers.CLAN.clan_ethos import MEMORY_BUFFER
    from src.engine.clankers import activate_ability

    g = _build_minimal_clankers_game()
    state = g.state
    add_on = _place_card_on_floor(g, MEMORY_BUFFER, "p1")

    pool_before = state.clankers_compute_pool["p1"]
    events = activate_ability(
        state, "p1", add_on.id,
        ability_index=0,
        targets=[],
    )

    assert events, "activate_ability returned no events"
    assert state.clankers_compute_pool["p1"] == pool_before - 2, (
        f"compute pool should be {pool_before - 2}, got "
        f"{state.clankers_compute_pool['p1']}"
    )
    assert add_on.state.tapped is True
    assert any(e.type == EventType.CLANKERS_ACTIVATE for e in events)


def test_activate_coolant_cradle_pays_scrap_inside_effect_fn():
    """Coolant Cradle: compute=0 descriptor, scrap=1 paid INSIDE effect_fn.

    Verifies:
      - dispatcher does NOT touch compute pool (cost spec is 0)
      - effect_fn deducts 1 scrap and readies self
      - CLANKERS_SCRAP_SPEND event emitted by effect_fn
    """
    from src.cards.clankers.CLAN.clan_bulwark import COOLANT_CRADLE
    from src.engine.clankers import activate_ability

    g = _build_minimal_clankers_game()
    state = g.state
    add_on = _place_card_on_floor(g, COOLANT_CRADLE, "p1")
    add_on.state.tapped = True  # start exhausted so "ready self" matters

    compute_before = state.clankers_compute_pool["p1"]
    scrap_before = state.clankers_scrap_pool["p1"]

    events = activate_ability(state, "p1", add_on.id, ability_index=0)

    assert events, "activate_ability returned no events"
    # Compute should be unchanged (descriptor has compute_cost=0).
    assert state.clankers_compute_pool["p1"] == compute_before
    # Scrap should be decremented by 1 (effect_fn pays it).
    assert state.clankers_scrap_pool["p1"] == scrap_before - 1, (
        f"scrap pool should be {scrap_before - 1}, got "
        f"{state.clankers_scrap_pool['p1']}"
    )
    # Source should be readied (un-tapped).
    assert add_on.state.tapped is False, (
        "Coolant Cradle effect should clear tapped"
    )
    # CLANKERS_SCRAP_SPEND should appear in the events.
    assert any(
        e.type == EventType.CLANKERS_SCRAP_SPEND for e in events
    ), f"missing scrap_spend event, got: {[e.type.name for e in events]}"


# ---------------------------------------------------------------------------
# Negative tests: insufficient cost / wrong controller / bad index
# ---------------------------------------------------------------------------

def test_activate_returns_empty_when_compute_insufficient():
    """If compute < descriptor.compute_cost, returns [] with no state change."""
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT
    from src.engine.clankers import activate_ability

    g = _build_minimal_clankers_game()
    state = g.state
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")
    state.clankers_compute_pool["p1"] = 0  # not enough for 1-compute ability

    tapped_before = bool(weapon.state.tapped)
    events = activate_ability(state, "p1", weapon.id, ability_index=0)

    assert events == [], (
        f"activate_ability should return [] when broke, got: "
        f"{[e.type.name for e in events]}"
    )
    assert state.clankers_compute_pool["p1"] == 0
    # Source must not have been tapped.
    assert bool(weapon.state.tapped) == tapped_before


def test_activate_returns_empty_when_already_tapped_with_exhaust_self():
    """If exhaust_self=True and source is already tapped, return []."""
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT
    from src.engine.clankers import activate_ability

    g = _build_minimal_clankers_game()
    state = g.state
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")
    weapon.state.tapped = True  # already exhausted

    pool_before = state.clankers_compute_pool["p1"]
    events = activate_ability(state, "p1", weapon.id, ability_index=0)

    assert events == []
    # Cost must not have been paid.
    assert state.clankers_compute_pool["p1"] == pool_before


def test_activate_returns_empty_for_wrong_controller():
    """Player tries to activate an opponent's ability — must return []."""
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT
    from src.engine.clankers import activate_ability

    g = _build_minimal_clankers_game()
    state = g.state
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")  # controller=p1

    pool_before = state.clankers_compute_pool["p2"]
    events = activate_ability(state, "p2", weapon.id, ability_index=0)

    assert events == []
    assert state.clankers_compute_pool["p2"] == pool_before
    assert weapon.state.tapped is False


def test_activate_returns_empty_for_bad_ability_index():
    """An out-of-range ability_index returns [] without mutating state."""
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT
    from src.engine.clankers import activate_ability

    g = _build_minimal_clankers_game()
    state = g.state
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")

    pool_before = state.clankers_compute_pool["p1"]
    events = activate_ability(state, "p1", weapon.id, ability_index=99)
    assert events == []
    assert state.clankers_compute_pool["p1"] == pool_before
    assert weapon.state.tapped is False


# ---------------------------------------------------------------------------
# Turn-manager wiring test
# ---------------------------------------------------------------------------

def test_turn_manager_routes_activate_action_to_engine():
    """The turn manager's _dispatch_activate must invoke activate_ability."""
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT, SALVAGER_SEVEN
    from src.engine import clankers as clankers_mod
    from src.engine.clankers_turn import ClankersTurnManager

    g = _build_minimal_clankers_game()
    state = g.state
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")
    target = _place_card_on_floor(g, SALVAGER_SEVEN, "p2")

    mgr = ClankersTurnManager(state)
    pool_before = state.clankers_compute_pool["p1"]
    action = {
        "action": "activate_ability",
        "source_obj_id": weapon.id,
        "ability_index": 0,
        "targets": [target.id],
    }
    events = mgr._dispatch_activate(clankers_mod, "p1", action)
    assert events, "turn manager dispatch returned empty"
    assert state.clankers_compute_pool["p1"] == pool_before - 1
    assert weapon.state.tapped is True


# ---------------------------------------------------------------------------
# AI adapter tests
# ---------------------------------------------------------------------------

def test_enumerate_activatable_abilities_walks_chassis_attached_solo_structures():
    """The enumerator must find abilities on chassis, attached parts, and
    solo parts. Affordability filters compute pool and tapped state."""
    from src.ai.clankers_adapter import ClankersAIAdapter
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT
    from src.cards.clankers.CLAN.clan_bulwark import COOLANT_CRADLE

    g = _build_minimal_clankers_game()
    state = g.state
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")
    addon = _place_card_on_floor(g, COOLANT_CRADLE, "p1")

    ai = ClankersAIAdapter("hard")
    found = ai._enumerate_activatable_abilities(state, "p1")
    src_ids = {tup[0] for tup in found}
    assert weapon.id in src_ids, "Recoil Mount ability not enumerated"
    assert addon.id in src_ids, "Coolant Cradle ability not enumerated"

    # Drop compute to 0 — Recoil Mount (compute=1) drops out; Coolant
    # Cradle (compute=0) stays.
    state.clankers_compute_pool["p1"] = 0
    found = ai._enumerate_activatable_abilities(state, "p1")
    src_ids = {tup[0] for tup in found}
    assert weapon.id not in src_ids
    assert addon.id in src_ids


def test_ai_hard_picks_lethal_finisher_activation():
    """Hard AI with a lethal-on-Core setup must return an activate_ability
    action targeting the finisher (not pass / not a hand play).

    Setup: p1 has a Recoil Mount in play (1 dmg ability) and p2's Core is
    at 1 workshop integrity. Recoil Mount can finish lethal. AI should
    fire it.
    """
    from src.ai.clankers_adapter import ClankersAIAdapter
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT

    g = _build_minimal_clankers_game()
    state = g.state
    # No chassis at all — so the only damage path is the activated ability.
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")
    # Empty p1 hand so the only legal action is the activation.
    # _build_minimal_clankers_game already gives empty hand.
    state.clankers_workshop_integrity["p2"] = 1  # 1 dmg = lethal

    ai = ClankersAIAdapter("hard")
    action = ai.choose_assemble_action(state, "p1")
    assert action is not None
    assert action.get("action") == "activate_ability", (
        f"hard AI did not pick activate_ability; got: {action}"
    )
    assert action.get("source_obj_id") == weapon.id


def test_ai_medium_picks_lethal_finisher_activation():
    """Same setup as the hard test, but medium tier — should still fire
    the lethal finisher (medium only activates on lethal)."""
    from src.ai.clankers_adapter import ClankersAIAdapter
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT

    g = _build_minimal_clankers_game()
    state = g.state
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")
    state.clankers_workshop_integrity["p2"] = 1

    ai = ClankersAIAdapter("medium")
    action = ai.choose_assemble_action(state, "p1")
    assert action is not None
    assert action.get("action") == "activate_ability"
    assert action.get("source_obj_id") == weapon.id


def test_ai_medium_skips_non_lethal_utility_activation():
    """Medium tier does NOT fire a utility activation when no lethal is
    available — it should fall through to a hand play (or pass)."""
    from src.ai.clankers_adapter import ClankersAIAdapter
    from src.cards.clankers.CLAN.clan_bulwark import COOLANT_CRADLE

    g = _build_minimal_clankers_game()
    state = g.state
    addon = _place_card_on_floor(g, COOLANT_CRADLE, "p1")
    addon.state.tapped = True  # so the ability would be useful
    state.clankers_workshop_integrity["p2"] = 25  # not lethal

    ai = ClankersAIAdapter("medium")
    action = ai.choose_assemble_action(state, "p1")
    # Medium should skip the activation — hand is empty so it passes.
    assert action == {"action": "pass"}, (
        f"medium tier should not activate utility abilities; got: {action}"
    )


def test_activation_mutates_state_so_repeat_call_skips_same_ability():
    """After activating, the AI's next enumerator call must NOT return the
    SAME ability (otherwise the assemble loop spins). Verifies state
    mutation (tapped + compute pool) is observable."""
    from src.ai.clankers_adapter import ClankersAIAdapter
    from src.engine.clankers import activate_ability
    from src.cards.clankers.CLAN.clan_forge import RECOIL_MOUNT

    g = _build_minimal_clankers_game()
    state = g.state
    weapon = _place_card_on_floor(g, RECOIL_MOUNT, "p1")
    state.clankers_workshop_integrity["p2"] = 1

    ai = ClankersAIAdapter("hard")
    found_before = ai._enumerate_activatable_abilities(state, "p1")
    assert any(t[0] == weapon.id for t in found_before)

    # Fire the ability.
    events = activate_ability(state, "p1", weapon.id, ability_index=0)
    assert events

    # Now the enumerator should NOT yield Recoil Mount again (it's tapped).
    found_after = ai._enumerate_activatable_abilities(state, "p1")
    assert not any(t[0] == weapon.id for t in found_after), (
        "Recoil Mount should drop out of enumeration after exhaust_self fires"
    )


if __name__ == "__main__":  # pragma: no cover - direct invocation
    test_activate_recoil_mount_pays_compute_exhausts_and_deals_damage()
    test_activate_memory_buffer_pays_compute_exhausts_with_utility_effect()
    test_activate_coolant_cradle_pays_scrap_inside_effect_fn()
    test_activate_returns_empty_when_compute_insufficient()
    test_activate_returns_empty_when_already_tapped_with_exhaust_self()
    test_activate_returns_empty_for_wrong_controller()
    test_activate_returns_empty_for_bad_ability_index()
    test_turn_manager_routes_activate_action_to_engine()
    test_enumerate_activatable_abilities_walks_chassis_attached_solo_structures()
    test_ai_hard_picks_lethal_finisher_activation()
    test_ai_medium_picks_lethal_finisher_activation()
    test_ai_medium_skips_non_lethal_utility_activation()
    test_activation_mutates_state_so_repeat_call_skips_same_ability()
    print("OK: clankers activated-ability tests passed.")
