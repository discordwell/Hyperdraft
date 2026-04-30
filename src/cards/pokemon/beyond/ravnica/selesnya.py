"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

Selesnya guild (G/W in MTG → Grass + Fighting as the white substitute since
sv_starter has no Fairy energy). Theme: harmony, conclave, tokens, healing,
life-and-growth. Final-stage planeswalker keeps its MTG name; earlier
evolutions get cute Pokedex-style diminutives.
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
# Trostani evolution line — Selesnya parun
# =============================================================================

def _voice_of_growth_effect(attacker, state):
    """Heal 30 damage (3 counters) from this Pokemon — lifelink flavor."""
    if attacker.state.damage_counters > 0:
        attacker.state.damage_counters = max(0, attacker.state.damage_counters - 3)
        return [Event(
            type=EventType.PKM_HEAL,
            payload={'pokemon_id': attacker.id, 'amount': 30,
                     'source': "Trostani, Selesnya's Voice ex"},
        )]
    return []


TROSTLING = make_pokemon(
    name="Trostling",
    hp=60,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Sunny Sprout",
         "cost": [{"type": "G", "count": 1}],
         "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("A sapling-dryad always wearing the same tiny smile. "
          "Even when uprooted, she refuses to look upset."),
    rarity="common",
)

TROSTAVIA = make_pokemon(
    name="Trostavia",
    hp=90,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 1",
    evolves_from="Trostling",
    attacks=[
        {"name": "Twin Bloom",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("Two dryad sisters share a single stalk and always finish each "
          "other's chants. They blossom in matched pinks and golds."),
    rarity="uncommon",
)

TROSTANI_SELESNYAS_VOICE_EX = make_pokemon(
    name="Trostani, Selesnya's Voice ex",
    hp=280,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 2",
    evolves_from="Trostavia",
    attacks=[
        {"name": "Chorus Strike",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 70,
         "text": ""},
        {"name": "Voice of Growth",
         "cost": [{"type": "G", "count": 2}, {"type": "F", "count": 2}],
         "damage": 180,
         "text": "Heal 30 damage from this Pokemon.",
         "effect_fn": _voice_of_growth_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=2,
    is_ex=True,
    text="The triple-throated dryad whose every word becomes a meadow.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _healing_canter_effect(attacker, state):
    """Heal 30 damage (3 counters) from your Active."""
    active_zone = state.zones.get(f"active_spot_{attacker.controller}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target or target.state.damage_counters <= 0:
        return []
    target.state.damage_counters = max(0, target.state.damage_counters - 3)
    return [Event(
        type=EventType.PKM_HEAL,
        payload={'pokemon_id': target_id, 'amount': 30,
                 'source': 'Centaur Healer'},
    )]


CENTAUR_HEALER = make_pokemon(
    name="Centaur Healer",
    hp=80,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Healing Canter",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 20,
         "text": "Heal 30 damage from your Active Pokemon.",
         "effect_fn": _healing_canter_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("A traveling cleric-pony of the Conclave. Patches up scraped "
          "knees with herbs and a stern, motherly hum."),
    rarity="uncommon",
)


def _populate_charge_effect(attacker, state):
    """+20 damage if you have any benched Pokemon — populate flavor."""
    bench_zone = state.zones.get(f"bench_{attacker.controller}")
    bench_count = len(bench_zone.objects) if bench_zone else 0
    if bench_count > 0:
        return [Event(
            type=EventType.PKM_DAMAGE_BONUS,
            payload={'pokemon_id': attacker.id, 'bonus': 20,
                     'source': 'Conclave Cavalier'},
        )]
    return []


CONCLAVE_CAVALIER = make_pokemon(
    name="Conclave Cavalier",
    hp=70,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Populate Charge",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": "If you have any Benched Pokemon, this attack does 20 more damage.",
         "effect_fn": _populate_charge_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("Rides into battle with a banner-pole and a pep-rally smile. "
          "Always brings backup; never marches alone."),
    rarity="uncommon",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _vitu_ghazi_effect(event, state):
    """Each player heals 10 damage (1 counter) from their Active."""
    events = []
    for pid in state.players:
        active_zone = state.zones.get(f"active_spot_{pid}")
        if not active_zone or not active_zone.objects:
            continue
        target_id = active_zone.objects[0]
        target = state.objects.get(target_id)
        if not target or target.state.damage_counters <= 0:
            continue
        target.state.damage_counters = max(0, target.state.damage_counters - 1)
        events.append(Event(
            type=EventType.PKM_HEAL,
            payload={'pokemon_id': target_id, 'amount': 10,
                     'source': 'Vitu-Ghazi, the City-Tree'},
        ))
    return events


VITU_GHAZI_THE_CITY_TREE = make_trainer_stadium(
    name="Vitu-Ghazi, the City-Tree",
    text=("When you play Vitu-Ghazi, the City-Tree, each player heals 10 "
          "damage from their Active Pokemon."),
    rarity="uncommon",
    resolve=_vitu_ghazi_effect,
)


def _captain_sisay_effect(event, state):
    """Search deck for any Basic Pokemon, put it onto the bench, shuffle deck."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    bench = state.zones.get(f"bench_{player_id}")
    if not library or not bench:
        return []
    if len(bench.objects) >= 5:
        return []
    found = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.POKEMON not in obj.characteristics.types:
            continue
        stage = getattr(obj.card_def, 'evolution_stage', None) if obj.card_def else None
        if stage == "Basic":
            found = card_id
            break
    if not found:
        random.shuffle(library.objects)
        return []
    library.objects.remove(found)
    bench.objects.append(found)
    obj = state.objects.get(found)
    if obj:
        obj.zone = ZoneType.BENCH
        obj.state.damage_counters = 0
        obj.state.turns_in_play = 0
        obj.state.evolved_this_turn = False
        obj.state.status_conditions = set()
    random.shuffle(library.objects)
    return [Event(
        type=EventType.PKM_PLAY_BASIC,
        payload={'player': player_id, 'pokemon_id': found,
                 'pokemon_name': obj.name if obj else '?',
                 'source': 'Captain Sisay'},
    )]


CAPTAIN_SISAY = make_trainer_supporter(
    name="Captain Sisay",
    text=("Search your deck for a Basic Pokemon and put it onto your Bench. "
          "Then, shuffle your deck."),
    rarity="rare",
    resolve=_captain_sisay_effect,
)


def _selesnya_cluestone_effect(event, state):
    """Search deck for one Grass Energy and one Fighting Energy, put both in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_grass = None
    found_fighting = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.GRASS.value and not found_grass:
            found_grass = card_id
        elif ptype == PokemonType.FIGHTING.value and not found_fighting:
            found_fighting = card_id
        if found_grass and found_fighting:
            break
    moved = []
    for cid in (found_grass, found_fighting):
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


SELESNYA_CLUESTONE = make_trainer_item(
    name="Selesnya Cluestone",
    text=("Search your deck for a Grass Energy and a Fighting Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_selesnya_cluestone_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_SELESNYA = {
    "Trostling": TROSTLING,
    "Trostavia": TROSTAVIA,
    "Trostani, Selesnya's Voice ex": TROSTANI_SELESNYAS_VOICE_EX,
    "Centaur Healer": CENTAUR_HEALER,
    "Conclave Cavalier": CONCLAVE_CAVALIER,
    "Vitu-Ghazi, the City-Tree": VITU_GHAZI_THE_CITY_TREE,
    "Captain Sisay": CAPTAIN_SISAY,
    "Selesnya Cluestone": SELESNYA_CLUESTONE,
}


def make_selesnya_deck() -> list:
    """60-card Selesnya deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        GRASS_ENERGY, FIGHTING_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    # Pokemon (16)
    deck.extend([TROSTLING] * 4)
    deck.extend([TROSTAVIA] * 3)
    deck.extend([TROSTANI_SELESNYAS_VOICE_EX] * 2)
    deck.extend([CENTAUR_HEALER] * 4)
    deck.extend([CONCLAVE_CAVALIER] * 3)
    # Trainers (22)
    deck.extend([VITU_GHAZI_THE_CITY_TREE] * 2)
    deck.extend([CAPTAIN_SISAY] * 2)
    deck.extend([SELESNYA_CLUESTONE] * 3)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 1)
    deck.extend([POTION] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([IONO] * 1)
    deck.extend([BOSS_ORDERS] * 1)
    deck.extend([JUDGE] * 1)
    # Energy (22) — Selesnya runs both Grass and Fighting (white substitute)
    deck.extend([GRASS_ENERGY] * 14)
    deck.extend([FIGHTING_ENERGY] * 8)
    return deck
