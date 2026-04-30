"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

PoC scope: 8 Izzet (R+W in Pokemon-color terms = R+U in MTG) cards.
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
# Niv-Mizzet evolution line — Izzet parun
# =============================================================================

def _synapse_spark_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


def _firemind_research_effect(attacker, state):
    events = _draw_cards(state, attacker.controller, 2)
    events.extend(_discard_attached_energy(state, attacker.id, 2))
    return events


NIVLET = make_pokemon(
    name="Nivlet",
    hp=60,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Sparkbite",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("A bookish dragonling that hatches in steam vents. "
          "Its tiny snorts already smell of ink and ozone."),
    rarity="common",
)

MIZZLING = make_pokemon(
    name="Mizzling",
    hp=90,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Nivlet",
    attacks=[
        {"name": "Voltage Coil",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("Its scales hum with ambient mana. Mizzlings are often found "
          "asleep on Izzet research notes, having read them overnight."),
    rarity="uncommon",
)

NIV_MIZZET_PARUN_EX = make_pokemon(
    name="Niv-Mizzet, Parun ex",
    hp=280,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 2",
    evolves_from="Mizzling",
    attacks=[
        {"name": "Synapse Spark",
         "cost": [{"type": "R", "count": 1}, {"type": "W", "count": 1}],
         "damage": 80,
         "text": "Draw a card.",
         "effect_fn": _synapse_spark_effect},
        {"name": "Firemind's Research",
         "cost": [{"type": "R", "count": 2}, {"type": "W", "count": 2}],
         "damage": 200,
         "text": "Draw 2 cards. Discard 2 Energy from this Pokemon.",
         "effect_fn": _firemind_research_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    is_ex=True,
    text="The Firemind itself, hatched of guildpact and lightning.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _inventors_spark_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


GOBLIN_ELECTROMANCER = make_pokemon(
    name="Goblin Electromancer",
    hp=80,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Inventor's Spark",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": "Draw a card.",
         "effect_fn": _inventors_spark_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("Will short out any device near him. The Izzet pay him "
          "in salvaged scrap and lozenges."),
    rarity="uncommon",
)


def _cantrip_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


MERCURIAL_MAGELING = make_pokemon(
    name="Mercurial Mageling",
    hp=70,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Cantrip",
         "cost": [{"type": "W", "count": 1}],
         "damage": 20,
         "text": "Draw a card.",
         "effect_fn": _cantrip_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    text=("A shape-shifting ink-blot that mimics whatever spell it overhears. "
          "Researchers keep notebooks shut around them."),
    rarity="common",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _niv_mizzets_tower_effect(event, state):
    """Each player draws a card when this Stadium enters play."""
    events = []
    for pid in state.players:
        events.extend(_draw_cards(state, pid, 1))
    return events


NIV_MIZZETS_TOWER = make_trainer_stadium(
    name="Niv-Mizzet's Tower",
    text="When you play Niv-Mizzet's Tower, each player draws a card.",
    rarity="uncommon",
    resolve=_niv_mizzets_tower_effect,
)


def _ral_storm_conduit_effect(event, state):
    """Mill the top card of your deck. If it's a Trainer, do 30 damage to opp Active."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    grave = state.zones.get(f"graveyard_{player_id}")
    if not library or not library.objects:
        return []
    top_id = library.objects.pop(0)
    top_obj = state.objects.get(top_id)
    if grave:
        grave.objects.append(top_id)
    if top_obj:
        top_obj.zone = ZoneType.GRAVEYARD
    events = []
    is_trainer = (
        top_obj
        and top_obj.characteristics
        and CardType.TRAINER in top_obj.characteristics.types
    )
    if not is_trainer:
        return events
    # Find opponent's Active and place 3 damage counters (= 30 damage)
    opp_id = next((p for p in state.players if p != player_id), None)
    if not opp_id:
        return events
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return events
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if target:
        target.state.damage_counters += 3  # 10 dmg per counter
        events.append(Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': target_id, 'counters': 3, 'source': 'Ral, Storm Conduit'},
        ))
    return events


RAL_STORM_CONDUIT = make_trainer_supporter(
    name="Ral, Storm Conduit",
    text=("Discard the top card of your deck. If it is a Trainer card, "
          "do 30 damage to your opponent's Active Pokemon."),
    rarity="rare",
    resolve=_ral_storm_conduit_effect,
)


def _izzet_signet_effect(event, state):
    """Search deck for a Fire Energy and a Water Energy, put them in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_fire = None
    found_water = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.FIRE.value and not found_fire:
            found_fire = card_id
        elif ptype == PokemonType.WATER.value and not found_water:
            found_water = card_id
        if found_fire and found_water:
            break
    moved = []
    for cid in (found_fire, found_water):
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


IZZET_SIGNET = make_trainer_item(
    name="Izzet Signet",
    text=("Search your deck for a Fire Energy and a Water Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_izzet_signet_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_IZZET = {
    "Nivlet": NIVLET,
    "Mizzling": MIZZLING,
    "Niv-Mizzet, Parun ex": NIV_MIZZET_PARUN_EX,
    "Goblin Electromancer": GOBLIN_ELECTROMANCER,
    "Mercurial Mageling": MERCURIAL_MAGELING,
    "Niv-Mizzet's Tower": NIV_MIZZETS_TOWER,
    "Ral, Storm Conduit": RAL_STORM_CONDUIT,
    "Izzet Signet": IZZET_SIGNET,
}


def make_izzet_deck() -> list:
    """60-card Izzet deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        FIRE_ENERGY, WATER_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    # Pokemon (16)
    deck.extend([NIVLET] * 4)
    deck.extend([MIZZLING] * 3)
    deck.extend([NIV_MIZZET_PARUN_EX] * 2)
    deck.extend([GOBLIN_ELECTROMANCER] * 4)
    deck.extend([MERCURIAL_MAGELING] * 3)
    # Trainers (22)
    deck.extend([NIV_MIZZETS_TOWER] * 2)
    deck.extend([RAL_STORM_CONDUIT] * 2)
    deck.extend([IZZET_SIGNET] * 3)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 1)
    deck.extend([POTION] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([IONO] * 1)
    deck.extend([BOSS_ORDERS] * 1)
    deck.extend([JUDGE] * 1)
    # Energy (22) — Izzet runs both Fire and Water
    deck.extend([FIRE_ENERGY] * 14)
    deck.extend([WATER_ENERGY] * 8)
    return deck
