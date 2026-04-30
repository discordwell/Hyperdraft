"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

PoC scope: 8 Simic (G+U in MTG = Grass+Water in Pokemon-color terms) cards.
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
# Vannifar evolution line — Simic biomancer
# =============================================================================

def _splice_jab_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


def _evolutionary_leap_effect(attacker, state):
    """Search deck for any Stage 1 or Stage 2 Pokemon and put it on top of your library."""
    library = state.zones.get(f"library_{attacker.controller}")
    if not library or not library.objects:
        return []
    found_id = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.POKEMON not in obj.characteristics.types:
            continue
        stage = getattr(obj.card_def, 'evolution_stage', None) if obj.card_def else None
        if stage in ("Stage 1", "Stage 2"):
            found_id = card_id
            break
    if not found_id:
        random.shuffle(library.objects)
        return []
    library.objects.remove(found_id)
    library.objects.insert(0, found_id)
    # Shuffle the rest beneath the top card
    top = library.objects.pop(0)
    random.shuffle(library.objects)
    library.objects.insert(0, top)
    return []


VANNET = make_pokemon(
    name="Vannet",
    hp=60,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Sticky Tongue",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("A wide-eyed slime-frog tadpole that follows lab assistants on rounds. "
          "Carries a tiny notebook it can neither read nor close."),
    rarity="common",
)

VANNIFUSE = make_pokemon(
    name="Vannifuse",
    hp=90,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 1",
    evolves_from="Vannet",
    attacks=[
        {"name": "Graft Splice",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("Wears a too-big lab coat tied with kelp. Can be found at midnight "
          "splicing cuttings of any creature it meets — apologies later."),
    rarity="uncommon",
)

VANNIFAR_EVOLVED_ENIGMA_EX = make_pokemon(
    name="Vannifar, Evolved Enigma ex",
    hp=280,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 2",
    evolves_from="Vannifuse",
    attacks=[
        {"name": "Hybrid Lash",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 70,
         "text": ""},
        {"name": "Evolutionary Leap",
         "cost": [{"type": "G", "count": 2}, {"type": "W", "count": 2}],
         "damage": 190,
         "text": "Search your deck for a Stage 1 or Stage 2 Pokemon and put it on top of your deck. Then shuffle.",
         "effect_fn": _evolutionary_leap_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=2,
    is_ex=True,
    text="The Combine's prized result, all the limbs and none of the regrets.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _biomancers_gift_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


MASTER_BIOMANCER = make_pokemon(
    name="Master Biomancer",
    hp=80,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Biomancer's Gift",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": "Draw a card.",
         "effect_fn": _biomancers_gift_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("Hums to her petri dishes. Plants and skinks alike grow faster "
          "near her — even the Izzet admit they don't know why."),
    rarity="uncommon",
)


def _cascade_glimpse_effect(attacker, state):
    """Reveal top 2 of deck; if any are energy, attach 1 to your Active."""
    library = state.zones.get(f"library_{attacker.controller}")
    active_zone = state.zones.get(f"active_spot_{attacker.controller}")
    if not library or not active_zone or not active_zone.objects:
        return []
    # Peek up to 2 cards
    revealed = library.objects[:2]
    energy_id = None
    rest = []
    for cid in revealed:
        obj = state.objects.get(cid)
        if energy_id is None and obj and obj.characteristics and CardType.ENERGY in obj.characteristics.types:
            energy_id = cid
        else:
            rest.append(cid)
    if energy_id is None:
        # Nothing to attach — leave deck order intact
        return []
    # Remove the revealed slice from top and resequence
    for _ in range(len(revealed)):
        library.objects.pop(0)
    # Put non-energy revealed cards back on top in original order
    for cid in reversed(rest):
        library.objects.insert(0, cid)
    # Attach energy to Active
    active_id = active_zone.objects[0]
    active = state.objects.get(active_id)
    if active:
        active.state.attached_energy.append(energy_id)
        en_obj = state.objects.get(energy_id)
        if en_obj:
            en_obj.zone = ZoneType.BATTLEFIELD
    return [Event(
        type=EventType.PKM_ATTACH_ENERGY,
        payload={'pokemon_id': active_id, 'energy_id': energy_id, 'source': 'Coiling Oracle'},
    )]


COILING_ORACLE = make_pokemon(
    name="Coiling Oracle",
    hp=70,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Cascade Glimpse",
         "cost": [{"type": "W", "count": 1}],
         "damage": 20,
         "text": "Reveal the top 2 cards of your deck. Attach one revealed Energy to your Active Pokemon.",
         "effect_fn": _cascade_glimpse_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    text=("Half snake, half kelp-bird, all curiosity. It surfaces from "
          "research pools cradling whichever shiny mana feels luckiest."),
    rarity="common",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _novijen_heart_of_progress_effect(event, state):
    """Each player draws a card when this Stadium enters play."""
    events = []
    for pid in state.players:
        events.extend(_draw_cards(state, pid, 1))
    return events


NOVIJEN_HEART_OF_PROGRESS = make_trainer_stadium(
    name="Novijen, Heart of Progress",
    text="When you play Novijen, Heart of Progress, each player draws a card.",
    rarity="uncommon",
    resolve=_novijen_heart_of_progress_effect,
)


def _prime_speaker_zegana_effect(event, state):
    """Draw cards equal to the number of energies attached to your Active (max 4)."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    active_zone = state.zones.get(f"active_spot_{player_id}")
    if not active_zone or not active_zone.objects:
        return []
    active = state.objects.get(active_zone.objects[0])
    if not active:
        return []
    count = min(len(active.state.attached_energy), 4)
    if count <= 0:
        return []
    return _draw_cards(state, player_id, count)


PRIME_SPEAKER_ZEGANA = make_trainer_supporter(
    name="Prime Speaker Zegana",
    text=("Draw a card for each Energy attached to your Active Pokemon "
          "(maximum 4)."),
    rarity="rare",
    resolve=_prime_speaker_zegana_effect,
)


def _simic_cluestone_effect(event, state):
    """Search deck for a Grass Energy and a Water Energy, put them in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_grass = None
    found_water = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.GRASS.value and not found_grass:
            found_grass = card_id
        elif ptype == PokemonType.WATER.value and not found_water:
            found_water = card_id
        if found_grass and found_water:
            break
    moved = []
    for cid in (found_grass, found_water):
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


SIMIC_CLUESTONE = make_trainer_item(
    name="Simic Cluestone",
    text=("Search your deck for a Grass Energy and a Water Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_simic_cluestone_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_SIMIC = {
    "Vannet": VANNET,
    "Vannifuse": VANNIFUSE,
    "Vannifar, Evolved Enigma ex": VANNIFAR_EVOLVED_ENIGMA_EX,
    "Master Biomancer": MASTER_BIOMANCER,
    "Coiling Oracle": COILING_ORACLE,
    "Novijen, Heart of Progress": NOVIJEN_HEART_OF_PROGRESS,
    "Prime Speaker Zegana": PRIME_SPEAKER_ZEGANA,
    "Simic Cluestone": SIMIC_CLUESTONE,
}


def make_simic_deck() -> list:
    """60-card Simic deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        GRASS_ENERGY, WATER_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    # Pokemon (16)
    deck.extend([VANNET] * 4)
    deck.extend([VANNIFUSE] * 3)
    deck.extend([VANNIFAR_EVOLVED_ENIGMA_EX] * 2)
    deck.extend([MASTER_BIOMANCER] * 4)
    deck.extend([COILING_ORACLE] * 3)
    # Trainers (22)
    deck.extend([NOVIJEN_HEART_OF_PROGRESS] * 2)
    deck.extend([PRIME_SPEAKER_ZEGANA] * 2)
    deck.extend([SIMIC_CLUESTONE] * 3)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 1)
    deck.extend([POTION] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([IONO] * 1)
    deck.extend([BOSS_ORDERS] * 1)
    deck.extend([JUDGE] * 1)
    # Energy (22) — Simic runs both Grass and Water
    deck.extend([GRASS_ENERGY] * 14)
    deck.extend([WATER_ENERGY] * 8)
    return deck
