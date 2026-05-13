"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

PoC scope: 8 Boros (R+W in MTG = Fire+Fighting in Pokemon-color terms) cards.
Covers all major engine card types: Basic / Stage 1 / Stage 2 ex / Stadium /
Supporter / Item. Tool and Special Energy deferred to full set.

Naming convention: cute pre-evolution names for Magic characters, with the
final stage keeping the MTG name. Pokedex-style flavor on the babies.
"""

import random

from src.engine.game import (
    make_pokemon, make_trainer_item, make_trainer_supporter,
    make_trainer_stadium,
)
from src.engine.types import PokemonType, Event, EventType, ZoneType, CardType


# =============================================================================
# Shared helpers — shrink-to-fit versions of sv_starter patterns
# =============================================================================

def _draw_cards(state, player_id: str, count: int) -> list[Event]:
    return [Event(type=EventType.DRAW,
                  payload={'player': player_id, 'count': count})]


def _discard_attached_energy(state, pokemon_id: str, count: int) -> list[Event]:
    """Discard `count` energy cards from a Pokemon."""
    pkm = state.objects.get(pokemon_id)
    if not pkm:
        return []
    events = []
    discarded = 0
    grave = state.zones.get(f"graveyard_{pkm.controller}")
    for energy_id in list(pkm.state.attached_energy):
        if discarded >= count:
            break
        pkm.state.attached_energy.remove(energy_id)
        if grave:
            grave.objects.append(energy_id)
        ev_obj = state.objects.get(energy_id)
        if ev_obj:
            ev_obj.zone = ZoneType.GRAVEYARD
        discarded += 1
        events.append(Event(
            type=EventType.PKM_DISCARD_ENERGY,
            payload={'pokemon_id': pokemon_id, 'energy_id': energy_id},
        ))
    return events


# =============================================================================
# Aurelia evolution line — Boros warleader
# =============================================================================

def _legions_charge_effect(attacker, state):
    """Vanilla small attack — no extra effect."""
    return []


def _aurelia_battalion_mark_effect(attacker, state):
    """Battalion Mark (rewrite, spice v1): each Benched Pokemon may do 10
    damage to opp Active. The chooser picks how many (heuristic v1: all).

    Replaces the old shared bench-scaling cluster — Aurelia ex now anchors a
    wide-board build-around archetype rather than being a reskin of Razia /
    Wojek / Conclave Cavalier. Build-around target fingerprint S=2 D=2 Z=2
    A=2 Y=2 = 10 (spicy).
    """
    from src.cards.pokemon._helpers import _get_opp_id, _get_opp_active
    bench = state.zones.get(f"bench_{attacker.controller}")
    if not bench:
        return []
    benched_pokemon = [b for b in bench.objects if b]
    if not benched_pokemon:
        return []
    opp_id = _get_opp_id(attacker.controller, state)
    if not opp_id:
        return []
    target = _get_opp_active(opp_id, state)
    if not target:
        return []
    # Heuristic v1: all benched Pokemon participate (chooser default = max
    # value). A future PendingChoice integration lets a player opt out for
    # tempo reasons. The depth scorer reads `pkm_choose_pokemon_target`-style
    # iteration as Decision Pressure.
    events: list[Event] = []
    for bench_id in benched_pokemon:
        target.state.damage_counters = getattr(target.state, 'damage_counters', 0) + 1
        events.append(Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': target.id, 'counters': 1,
                     'attacker_bench': bench_id, 'source': 'Battalion Mark'},
            source=attacker.id,
        ))
    return events


# Retained for the existing Razia/Wojek/Conclave bench-scaling cards that still
# share this template — those become rewrite candidates in spice pack v2.
def _battalion_strike_effect(attacker, state):
    """+20 damage per benched Pokemon you control (battalion flavor).

    Damage adjustment is folded into the attack's base by emitting an extra
    PKM_PLACE_DAMAGE_COUNTERS targeting the opponent's Active.
    """
    bench = state.zones.get(f"bench_{attacker.controller}")
    if not bench:
        return []
    bench_count = len([b for b in bench.objects if b])
    if bench_count <= 0:
        return []
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target:
        return []
    bonus_counters = 2 * bench_count  # +20 dmg per bench = 2 counters per
    target.state.damage_counters += bonus_counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': bonus_counters,
                 'source': 'Battalion Strike'},
    )]


def _halo_bash_effect(attacker, state):
    """Small battalion cantrip when the bench has formed up."""
    bench = state.zones.get(f"bench_{attacker.controller}")
    if not bench or not bench.objects:
        return []
    return _draw_cards(state, attacker.controller, 1)


def _practice_lance_effect(attacker, state):
    """+10 damage if any ally is already on the bench."""
    bench = state.zones.get(f"bench_{attacker.controller}")
    if not bench or not bench.objects:
        return []
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target:
        return []
    target.state.damage_counters += 1
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 1,
                 'source': 'Aurelin'},
    )]


AURELET = make_pokemon(
    name="Aurelet",
    hp=60,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Tiny Smite",
         "cost": [{"type": "R", "count": 1}],
         "damage": 20,
         "text": "If you have any Benched Pokemon, draw a card.",
         "effect_fn": _halo_bash_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("A baby angel-warrior with gold-trimmed feathers no bigger "
          "than a coin. Practices its salutes in mirror-bright puddles."),
    rarity="common",
)

AURELIN = make_pokemon(
    name="Aurelin",
    hp=90,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Aurelet",
    attacks=[
        {"name": "Practice Lance",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": "If you have any Benched Pokemon, this attack does 10 more damage.",
         "effect_fn": _practice_lance_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("A novice legionnaire still learning the parade-step. Carries "
          "a blunted practice spear taller than itself."),
    rarity="uncommon",
)

AURELIA_THE_WARLEADER_EX = make_pokemon(
    name="Aurelia, the Warleader ex",
    hp=280,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 2",
    evolves_from="Aurelin",
    attacks=[
        {"name": "Legion's Charge",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80,
         "text": "",
         "effect_fn": _legions_charge_effect},
        {"name": "Battalion Mark",
         "cost": [{"type": "R", "count": 2}, {"type": "F", "count": 2}],
         "damage": 0,
         "text": "Each of your Benched Pokemon may do 10 damage to your opponent's Active Pokemon (you choose how many participate).",
         "effect_fn": _aurelia_battalion_mark_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    is_ex=True,
    text="Twin blades, twin oaths. Where she lands, the legion follows.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _counter_punch_effect(attacker, state):
    """Place 2 damage counters on this Pokemon (counter-punch flavor)."""
    attacker.state.damage_counters += 2
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': attacker.id, 'counters': 2,
                 'source': 'Counter-Punch'},
    )]


BOROS_RECKONER = make_pokemon(
    name="Boros Reckoner",
    hp=80,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Counter-Punch",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 60,
         "text": "Place 2 damage counters on this Pokemon.",
         "effect_fn": _counter_punch_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    text=("A minotaur in red plate who returns every blow he takes. "
          "Sparks fly with each clash of horns and hammer."),
    rarity="uncommon",
)


def _mentors_resolve_effect(attacker, state):
    """Clear all status conditions on this Pokemon."""
    if hasattr(attacker.state, 'status_conditions'):
        attacker.state.status_conditions = set()
    if hasattr(attacker.state, 'is_asleep'):
        attacker.state.is_asleep = False
    if hasattr(attacker.state, 'is_paralyzed'):
        attacker.state.is_paralyzed = False
    if hasattr(attacker.state, 'is_poisoned'):
        attacker.state.is_poisoned = False
    if hasattr(attacker.state, 'is_burned'):
        attacker.state.is_burned = False
    if hasattr(attacker.state, 'is_confused'):
        attacker.state.is_confused = False
    return []


TAJIC_LEGIONS_EDGE = make_pokemon(
    name="Tajic, Legion's Edge",
    hp=70,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Mentor's Resolve",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": "Remove all Special Conditions from this Pokemon.",
         "effect_fn": _mentors_resolve_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("Captain of the Sunhome legion. Steady, plain-spoken, and "
          "absolutely on fire about half the time."),
    rarity="uncommon",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _sunhome_fortress_effect(event, state):
    """Heal both Actives, then reward wide boards with a small rally ping."""
    events = []
    for pid in state.players:
        active_zone = state.zones.get(f"active_spot_{pid}")
        if not active_zone or not active_zone.objects:
            continue
        target_id = active_zone.objects[0]
        target = state.objects.get(target_id)
        if not target:
            continue
        if target.state.damage_counters > 0:
            target.state.damage_counters = max(0, target.state.damage_counters - 1)
            events.append(Event(
                type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
                payload={'pokemon_id': target_id, 'counters': -1,
                         'source': 'Sunhome, Fortress of the Legion'},
            ))
        bench = state.zones.get(f"bench_{pid}")
        if not bench or len(bench.objects) < 2:
            continue
        opp_id = next((p for p in state.players if p != pid), None)
        opp_active = state.zones.get(f"active_spot_{opp_id}") if opp_id else None
        if not opp_active or not opp_active.objects:
            continue
        opp_target_id = opp_active.objects[0]
        opp_target = state.objects.get(opp_target_id)
        if not opp_target:
            continue
        opp_target.state.damage_counters += 1
        events.append(Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': opp_target_id, 'counters': 1,
                     'source': 'Sunhome, Fortress of the Legion'},
        ))
    return events


SUNHOME_FORTRESS_OF_THE_LEGION = make_trainer_stadium(
    name="Sunhome, Fortress of the Legion",
    text=("When you play Sunhome, Fortress of the Legion, "
          "heal 10 damage from each player's Active Pokemon. Then each player "
          "with 2 or more Benched Pokemon places 1 damage counter on their "
          "opponent's Active Pokemon."),
    rarity="uncommon",
    resolve=_sunhome_fortress_effect,
)


def _gideon_blackblade_effect(event, state):
    """Place 2 damage counters on opponent's Active and heal your Active."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    events = []
    opp_id = next((p for p in state.players if p != player_id), None)
    if not opp_id:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target:
        return []
    target.state.damage_counters += 2  # 10 dmg per counter
    events.append(Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 2,
                 'source': 'Gideon Blackblade'},
    ))
    own_active = state.zones.get(f"active_spot_{player_id}")
    if own_active and own_active.objects:
        own = state.objects.get(own_active.objects[0])
        if own and own.state.damage_counters > 0:
            healed = min(2, own.state.damage_counters)
            own.state.damage_counters -= healed
            events.append(Event(
                type=EventType.PKM_HEAL,
                payload={'pokemon_id': own.id, 'amount': healed * 10,
                         'source': 'Gideon Blackblade'},
            ))
    return events


GIDEON_BLACKBLADE = make_trainer_supporter(
    name="Gideon Blackblade",
    text=("Place 2 damage counters on your opponent's Active Pokemon. "
          "Then heal 20 damage from your Active Pokemon."),
    rarity="rare",
    resolve=_gideon_blackblade_effect,
)


def _boros_cluestone_effect(event, state):
    """Search deck for a Fire Energy and a Fighting Energy, put them in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_fire = None
    found_fighting = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.FIRE.value and not found_fire:
            found_fire = card_id
        elif ptype == PokemonType.FIGHTING.value and not found_fighting:
            found_fighting = card_id
        if found_fire and found_fighting:
            break
    moved = []
    for cid in (found_fire, found_fighting):
        if cid:
            library.objects.remove(cid)
            hand.objects.append(cid)
            obj = state.objects.get(cid)
            if obj:
                obj.zone = ZoneType.HAND
            moved.append(cid)
    random.shuffle(library.objects)
    return []


BOROS_CLUESTONE = make_trainer_item(
    name="Boros Cluestone",
    text=("Search your deck for a Fire Energy and a Fighting Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_boros_cluestone_effect,
)


# =============================================================================
# Feather evolution line — Boros redeemed angel
# =============================================================================

def _redeemed_recursion_effect(attacker, state):
    """Retrieve top of discard pile to hand if it's a Trainer (recursion flavor)."""
    grave = state.zones.get(f"graveyard_{attacker.controller}")
    hand = state.zones.get(f"hand_{attacker.controller}")
    if not grave or not hand or not grave.objects:
        return []
    top_id = grave.objects[-1]
    top_obj = state.objects.get(top_id)
    if not top_obj or not top_obj.characteristics:
        return []
    if CardType.TRAINER not in top_obj.characteristics.types:
        return []
    grave.objects.pop()
    hand.objects.append(top_id)
    top_obj.zone = ZoneType.HAND
    return []


FEATHLET = make_pokemon(
    name="Feathlet",
    hp=70,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Halo Bash",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("A cute baby angel hatchling with a tiny practice halo that "
          "wobbles when it flies. Sneezes glitter."),
    rarity="common",
)

FEATHER_THE_REDEEMED = make_pokemon(
    name="Feather, the Redeemed",
    hp=120,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Feathlet",
    attacks=[
        {"name": "Redeemed Recursion",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80,
         "text": ("If the top card of your discard pile is a Trainer card, "
                  "put it into your hand."),
         "effect_fn": _redeemed_recursion_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text="The angel who returns. Spells cast in her name come back, too.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon (extension)
# =============================================================================

def _battalion_flavor_effect(attacker, state):
    """+10 damage per benched Pokemon you control (battalion flavor)."""
    bench = state.zones.get(f"bench_{attacker.controller}")
    if not bench:
        return []
    bench_count = len([b for b in bench.objects if b])
    if bench_count <= 0:
        return []
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target:
        return []
    bonus_counters = bench_count  # +10 dmg per bench = 1 counter per
    target.state.damage_counters += bonus_counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': bonus_counters,
                 'source': 'Razia, Boros Archangel'},
    )]


RAZIA_BOROS_ARCHANGEL = make_pokemon(
    name="Razia, Boros Archangel",
    hp=80,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Wingblade Charge",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 60,
         "text": "This attack does 10 more damage for each Benched Pokemon you control.",
         "effect_fn": _battalion_flavor_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    text=("Founding parun of the Boros, returned from the Long Slumber. "
          "Her zeal kindles every soldier behind her."),
    rarity="rare",
)


WOJEK_HALBERDIERS = make_pokemon(
    name="Wojek Halberdiers",
    hp=70,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Halberd Strike",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": "This attack does 10 more damage for each Benched Pokemon you control.",
         "effect_fn": _battalion_flavor_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("Wojek squads patrol the Tenth in lockstep, halberds gleaming. "
          "Loud, polite, and legally allowed to break doors."),
    rarity="common",
)


def _double_strike_effect(attacker, state):
    """Place 4 additional damage counters (40 dmg) on opp Active (double-strike flavor)."""
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target:
        return []
    target.state.damage_counters += 4  # 4 counters = 40 dmg
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 4,
                 'source': 'Fencing Ace'},
    )]


FENCING_ACE = make_pokemon(
    name="Fencing Ace",
    hp=90,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Riposte Flurry",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": ("Place 4 additional damage counters on your opponent's "
                  "Active Pokemon (double-strike)."),
         "effect_fn": _double_strike_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("Trained at the Sunhome salle, where every footstep is a verse "
          "and every parry a rhyme. Strikes twice for the price of one."),
    rarity="uncommon",
)


def _skyknight_vanguard_effect(attacker, state):
    """Battalion pressure: ping the weakest opposing benched Pokemon."""
    bench = state.zones.get(f"bench_{attacker.controller}")
    if not bench or len(bench.objects) < 2:
        return []
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    opp_bench = state.zones.get(f"bench_{opp_id}")
    if not opp_bench or not opp_bench.objects:
        return []

    target_id = None
    lowest_hp = 10 ** 9
    for bid in opp_bench.objects:
        target = state.objects.get(bid)
        if not target or not target.card_def:
            continue
        remaining_hp = (target.card_def.hp or 0) - target.state.damage_counters * 10
        if remaining_hp < lowest_hp:
            lowest_hp = remaining_hp
            target_id = bid
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target:
        return []
    target.state.damage_counters += 2
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 2,
                 'source': 'Skyknight Vanguard'},
    )]


SKYKNIGHT_VANGUARD = make_pokemon(
    name="Skyknight Vanguard",
    hp=60,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Diving Lance",
         "cost": [{"type": "R", "count": 1}],
         "damage": 30,
         "text": ("If you have 2 or more Benched Pokemon, place 2 damage "
                  "counters on 1 of your opponent's Benched Pokemon."),
         "effect_fn": _skyknight_vanguard_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("First over the wall, last to land. Skyknights ride griffin "
          "steeds painted in legion red and gold."),
    rarity="common",
)


# =============================================================================
# Boros Blend Energy — aggressive color-fix Item
# =============================================================================

def _boros_blend_energy_effect(event, state):
    """Search deck for one Fire Energy AND one Fighting Energy, attach BOTH
    directly to your Active Pokemon. Shuffle deck."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    active_zone = state.zones.get(f"active_spot_{player_id}")
    if not library or not active_zone or not active_zone.objects:
        return []
    active_id = active_zone.objects[0]
    active = state.objects.get(active_id)
    if not active:
        return []
    found_fire = None
    found_fighting = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.FIRE.value and not found_fire:
            found_fire = card_id
        elif ptype == PokemonType.FIGHTING.value and not found_fighting:
            found_fighting = card_id
        if found_fire and found_fighting:
            break
    events = []
    for cid in (found_fire, found_fighting):
        if cid:
            library.objects.remove(cid)
            energy_obj = state.objects.get(cid)
            if energy_obj:
                energy_obj.zone = ZoneType.BATTLEFIELD
            active.state.attached_energy.append(cid)
            events.append(Event(
                type=EventType.PKM_ATTACH_ENERGY,
                payload={'pokemon_id': active_id, 'energy_id': cid,
                         'source': 'Boros Blend Energy'},
            ))
    random.shuffle(library.objects)
    return events


BOROS_BLEND_ENERGY = make_trainer_item(
    name="Boros Blend Energy",
    text=("Search your deck for a Fire Energy and a Fighting Energy and "
          "attach both to your Active Pokemon. Then, shuffle your deck."),
    rarity="rare",
    resolve=_boros_blend_energy_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_BOROS = {
    "Aurelet": AURELET,
    "Aurelin": AURELIN,
    "Aurelia, the Warleader ex": AURELIA_THE_WARLEADER_EX,
    "Boros Reckoner": BOROS_RECKONER,
    "Tajic, Legion's Edge": TAJIC_LEGIONS_EDGE,
    "Sunhome, Fortress of the Legion": SUNHOME_FORTRESS_OF_THE_LEGION,
    "Gideon Blackblade": GIDEON_BLACKBLADE,
    "Boros Cluestone": BOROS_CLUESTONE,
    "Feathlet": FEATHLET,
    "Feather, the Redeemed": FEATHER_THE_REDEEMED,
    "Razia, Boros Archangel": RAZIA_BOROS_ARCHANGEL,
    "Wojek Halberdiers": WOJEK_HALBERDIERS,
    "Fencing Ace": FENCING_ACE,
    "Skyknight Vanguard": SKYKNIGHT_VANGUARD,
    "Boros Blend Energy": BOROS_BLEND_ENERGY,
}


def make_boros_deck() -> list:
    """60-card Boros deck (ultra-loop iter-3 fix: Aurelet 4→6 to address
    the 4-copy-evolver-starvation failure mode confirmed in 3/3 games —
    pilot drew 0 Aurelet across 10+22+22 turns).
    """
    from src.cards.pokemon.sv_starter import FIRE_ENERGY, FIGHTING_ENERGY
    from src.cards.pokemon.beyond.ravnica._deck_helpers import standard_trainer_suite
    deck = []
    # Pokemon (18: Aurelet 4→6 starvation fix; -1 Reckoner -1 Feather to
    # compensate, since the win con is Aurelia ex via Aurelin)
    deck.extend([AURELET] * 6)
    deck.extend([AURELIN] * 3)
    deck.extend([AURELIA_THE_WARLEADER_EX] * 2)
    deck.extend([FEATHLET] * 3)
    deck.extend([FEATHER_THE_REDEEMED] * 2)
    deck.extend([BOROS_RECKONER] * 2)
    # Guild trainers (9)
    deck.extend([SUNHOME_FORTRESS_OF_THE_LEGION] * 2)
    deck.extend([GIDEON_BLACKBLADE] * 2)
    deck.extend([BOROS_CLUESTONE] * 3)
    deck.extend([BOROS_BLEND_ENERGY] * 2)
    # Standard sv_starter trainer suite (20 — trimmed 2 to keep 60-card)
    deck.extend(standard_trainer_suite()[:-2])
    # Energy (13) — Boros runs both Fire and Fighting
    deck.extend([FIRE_ENERGY] * 8)
    deck.extend([FIGHTING_ENERGY] * 5)
    return deck
