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
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    events = []
    for _ in range(min(count, len(library.objects))):
        drawn_id = library.objects.pop(0)
        hand.objects.append(drawn_id)
        obj = state.objects.get(drawn_id)
        if obj:
            obj.zone = ZoneType.HAND
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': player_id, 'count': 1},
        ))
    return events


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


def _battalion_strike_effect(attacker, state):
    """+30 damage per benched Pokemon you control (battalion flavor).

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
    bonus_counters = 3 * bench_count  # +30 dmg per bench = 3 counters per
    target.state.damage_counters += bonus_counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': bonus_counters,
                 'source': 'Battalion Strike'},
    )]


AURELET = make_pokemon(
    name="Aurelet",
    hp=60,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Tiny Smite",
         "cost": [{"type": "R", "count": 1}],
         "damage": 20, "text": ""},
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
         "damage": 50, "text": ""},
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
        {"name": "Battalion Strike",
         "cost": [{"type": "R", "count": 2}, {"type": "F", "count": 2}],
         "damage": 200,
         "text": "This attack does 30 more damage for each Benched Pokemon you control.",
         "effect_fn": _battalion_strike_effect},
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
    """When played, heal 10 damage (1 counter) from each player's Active."""
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
    return events


SUNHOME_FORTRESS_OF_THE_LEGION = make_trainer_stadium(
    name="Sunhome, Fortress of the Legion",
    text=("When you play Sunhome, Fortress of the Legion, "
          "heal 10 damage from each player's Active Pokemon."),
    rarity="uncommon",
    resolve=_sunhome_fortress_effect,
)


def _gideon_blackblade_effect(event, state):
    """Place 3 damage counters (30 dmg) on opponent's Active."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
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
    target.state.damage_counters += 3  # 10 dmg per counter
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 3,
                 'source': 'Gideon Blackblade'},
    )]


GIDEON_BLACKBLADE = make_trainer_supporter(
    name="Gideon Blackblade",
    text="Place 3 damage counters on your opponent's Active Pokemon.",
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
    return [Event(
        type=EventType.DRAW,
        payload={'player': player_id, 'count': len(moved)},
    )]


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
    return [Event(
        type=EventType.DRAW,
        payload={'player': attacker.controller, 'count': 1},
    )]


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
         "damage": 50, "text": ""},
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


SKYKNIGHT_VANGUARD = make_pokemon(
    name="Skyknight Vanguard",
    hp=60,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Diving Lance",
         "cost": [{"type": "R", "count": 1}],
         "damage": 30, "text": ""},
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
    """60-card Boros deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        FIRE_ENERGY, FIGHTING_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH,
    )
    deck = []
    # Pokemon (16)
    deck.extend([AURELET] * 4)
    deck.extend([AURELIN] * 3)
    deck.extend([AURELIA_THE_WARLEADER_EX] * 2)
    deck.extend([FEATHLET] * 3)
    deck.extend([FEATHER_THE_REDEEMED] * 2)
    deck.extend([BOROS_RECKONER] * 2)
    # Trainers (22) — 9 guild + 13 sv_starter
    deck.extend([SUNHOME_FORTRESS_OF_THE_LEGION] * 2)
    deck.extend([GIDEON_BLACKBLADE] * 2)
    deck.extend([BOROS_CLUESTONE] * 3)
    deck.extend([BOROS_BLEND_ENERGY] * 2)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 2)
    deck.extend([POTION] * 1)
    deck.extend([SUPER_ROD] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 1)
    # Energy (22) — Boros runs both Fire and Fighting
    deck.extend([FIRE_ENERGY] * 14)
    deck.extend([FIGHTING_ENERGY] * 8)
    return deck
