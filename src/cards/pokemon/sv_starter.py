"""
Pokemon TCG Starter Set — Scarlet & Violet Era

Hand-curated set of real SV-era cards for engine testing.
Includes a mix of types, evolution lines, trainers, and energy
sufficient for 2 playable 30-card decks.
"""

import random

from src.engine.game import (
    make_pokemon, make_trainer_item, make_trainer_supporter,
    make_trainer_stadium, make_pokemon_tool, make_basic_energy,
)
from src.engine.types import PokemonType, Event, EventType, ZoneType, CardType


# =============================================================================
# TRAINER CARD EFFECTS
# =============================================================================

def _professors_research_effect(event, state):
    """Discard your hand and draw 7 cards."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    hand_key = f"hand_{player_id}"
    hand = state.zones.get(hand_key)
    graveyard_key = f"graveyard_{player_id}"
    graveyard = state.zones.get(graveyard_key)
    if not hand:
        return []
    # Discard entire hand (the trainer card itself is already removed by _play_trainer)
    for card_id in list(hand.objects):
        obj = state.objects.get(card_id)
        if obj:
            hand.objects.remove(card_id)
            if graveyard:
                graveyard.objects.append(card_id)
            obj.zone = ZoneType.GRAVEYARD
    # Draw 7
    events = []
    library_key = f"library_{player_id}"
    library = state.zones.get(library_key)
    if library:
        for _ in range(min(7, len(library.objects))):
            if library.objects:
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


def _nest_ball_effect(event, state):
    """Search your deck for a Basic Pokemon and put it onto your Bench."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    bench_key = f"bench_{player_id}"
    bench = state.zones.get(bench_key)
    if not bench or len(bench.objects) >= 5:
        return []
    library_key = f"library_{player_id}"
    library = state.zones.get(library_key)
    if not library:
        return []
    # Find best Basic Pokemon in deck
    best_id = None
    best_hp = 0
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.card_def:
            continue
        if CardType.POKEMON not in obj.characteristics.types:
            continue
        if obj.card_def.evolution_stage != "Basic":
            continue
        hp = obj.card_def.hp or 0
        if hp > best_hp:
            best_hp = hp
            best_id = card_id
    if not best_id:
        return []
    # Move to bench
    library.objects.remove(best_id)
    bench.objects.append(best_id)
    obj = state.objects.get(best_id)
    if obj:
        obj.zone = ZoneType.BENCH
        obj.state.damage_counters = 0
        obj.state.turns_in_play = 0
        obj.state.evolved_this_turn = False
        obj.state.status_conditions = set()
    # Shuffle deck
    random.shuffle(library.objects)
    return [Event(
        type=EventType.PKM_PLAY_BASIC,
        payload={'player': player_id, 'pokemon_id': best_id, 'pokemon_name': obj.name if obj else '?'},
    )]


def _ultra_ball_effect(event, state):
    """Discard 2 cards from your hand. Search your deck for a Pokemon and put it into your hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    hand_key = f"hand_{player_id}"
    hand = state.zones.get(hand_key)
    graveyard_key = f"graveyard_{player_id}"
    graveyard = state.zones.get(graveyard_key)
    if not hand or len(hand.objects) < 2:
        return []
    # Discard 2 cards (pick least valuable — energy first, then lowest-HP pokemon)
    discard_candidates = []
    for card_id in hand.objects:
        obj = state.objects.get(card_id)
        if not obj:
            continue
        # Score: lower = more discardable
        score = 50
        if CardType.ENERGY in (obj.characteristics.types if obj.characteristics else set()):
            score = 10  # Energy is cheap to discard
        elif obj.card_def and obj.card_def.hp:
            score = obj.card_def.hp  # Higher HP = less discardable
        discard_candidates.append((card_id, score))
    discard_candidates.sort(key=lambda x: x[1])
    discarded = 0
    for card_id, _ in discard_candidates:
        if discarded >= 2:
            break
        if card_id in hand.objects:
            hand.objects.remove(card_id)
            obj = state.objects.get(card_id)
            if obj:
                if graveyard:
                    graveyard.objects.append(card_id)
                obj.zone = ZoneType.GRAVEYARD
            discarded += 1
    if discarded < 2:
        return []
    # Search deck for best Pokemon
    library_key = f"library_{player_id}"
    library = state.zones.get(library_key)
    if not library:
        return []
    best_id = None
    best_score = -1
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.card_def:
            continue
        if CardType.POKEMON not in (obj.characteristics.types if obj.characteristics else set()):
            continue
        score = obj.card_def.hp or 0
        if obj.card_def.is_ex:
            score += 100  # Prioritize ex Pokemon
        if obj.card_def.evolution_stage in ('Stage 1', 'Stage 2'):
            score += 50  # Evolutions are high value search targets
        if score > best_score:
            best_score = score
            best_id = card_id
    if not best_id:
        return []
    library.objects.remove(best_id)
    hand.objects.append(best_id)
    obj = state.objects.get(best_id)
    if obj:
        obj.zone = ZoneType.HAND
    random.shuffle(library.objects)
    return [Event(
        type=EventType.DRAW,
        payload={'player': player_id, 'count': 1},
    )]


def _switch_effect(event, state):
    """Switch your Active Pokemon with 1 of your Benched Pokemon."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    active_key = f"active_spot_{player_id}"
    bench_key = f"bench_{player_id}"
    active_zone = state.zones.get(active_key)
    bench_zone = state.zones.get(bench_key)
    if not active_zone or not active_zone.objects or not bench_zone or not bench_zone.objects:
        return []
    # Pick best bench Pokemon to switch in (highest HP + most energy)
    best_bench_id = None
    best_score = -999
    for pkm_id in bench_zone.objects:
        pkm = state.objects.get(pkm_id)
        if not pkm:
            continue
        score = 0
        if pkm.card_def:
            score += (pkm.card_def.hp or 0) / 10.0
            # Count attached energy
            energy_count = len(getattr(pkm.state, 'attached_energy', []))
            score += energy_count * 5
        if score > best_score:
            best_score = score
            best_bench_id = pkm_id
    if not best_bench_id:
        return []
    # Swap
    old_active_id = active_zone.objects[0]
    active_zone.objects[0] = best_bench_id
    bench_zone.objects.remove(best_bench_id)
    bench_zone.objects.append(old_active_id)
    old_active = state.objects.get(old_active_id)
    new_active = state.objects.get(best_bench_id)
    if old_active:
        old_active.zone = ZoneType.BENCH
        old_active.state.status_conditions = set()  # Moving to bench clears status
    if new_active:
        new_active.zone = ZoneType.ACTIVE_SPOT
    return [Event(
        type=EventType.PKM_SWITCH,
        payload={'player': player_id, 'old_active': old_active_id, 'new_active': best_bench_id},
    )]


def _iono_effect(event, state):
    """Each player shuffles hand into deck, draws cards = remaining prizes."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    events = []
    for pid in state.players:
        hand_key = f"hand_{pid}"
        lib_key = f"library_{pid}"
        hand = state.zones.get(hand_key)
        library = state.zones.get(lib_key)
        if not hand or not library:
            continue
        # Shuffle hand into deck
        for card_id in list(hand.objects):
            hand.objects.remove(card_id)
            library.objects.append(card_id)
            obj = state.objects.get(card_id)
            if obj:
                obj.zone = ZoneType.LIBRARY
        random.shuffle(library.objects)
        # Draw = remaining prizes
        draw_count = state.players[pid].prizes_remaining
        for _ in range(min(draw_count, len(library.objects))):
            if library.objects:
                drawn_id = library.objects.pop(0)
                hand.objects.append(drawn_id)
                obj = state.objects.get(drawn_id)
                if obj:
                    obj.zone = ZoneType.HAND
    return events


def _boss_orders_effect(event, state):
    """Switch in 1 of your opponent's Benched Pokemon to the Active Spot."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    # Find opponent
    opp_id = None
    for pid in state.players:
        if pid != player_id:
            opp_id = pid
            break
    if not opp_id:
        return []
    active_key = f"active_spot_{opp_id}"
    bench_key = f"bench_{opp_id}"
    active_zone = state.zones.get(active_key)
    bench_zone = state.zones.get(bench_key)
    if not active_zone or not active_zone.objects or not bench_zone or not bench_zone.objects:
        return []
    # Pick the weakest bench Pokemon to drag in (lowest HP)
    worst_id = None
    worst_hp = 9999
    for pkm_id in bench_zone.objects:
        pkm = state.objects.get(pkm_id)
        if pkm and pkm.card_def:
            hp = (pkm.card_def.hp or 0) - (pkm.state.damage_counters * 10)
            if hp < worst_hp:
                worst_hp = hp
                worst_id = pkm_id
    if not worst_id:
        worst_id = bench_zone.objects[0]
    old_active_id = active_zone.objects[0]
    active_zone.objects[0] = worst_id
    bench_zone.objects.remove(worst_id)
    bench_zone.objects.append(old_active_id)
    old_active = state.objects.get(old_active_id)
    new_active = state.objects.get(worst_id)
    if old_active:
        old_active.zone = ZoneType.BENCH
    if new_active:
        new_active.zone = ZoneType.ACTIVE_SPOT
    return [Event(
        type=EventType.PKM_SWITCH,
        payload={'player': opp_id, 'old_active': old_active_id, 'new_active': worst_id},
    )]


def _super_rod_effect(event, state):
    """Choose up to 3 Pokemon/Energy from discard and shuffle into deck."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    grave_key = f"graveyard_{player_id}"
    lib_key = f"library_{player_id}"
    graveyard = state.zones.get(grave_key)
    library = state.zones.get(lib_key)
    if not graveyard or not library or not graveyard.objects:
        return []
    # Pick up to 3 Pokemon or Energy cards
    recovered = 0
    for card_id in list(graveyard.objects):
        if recovered >= 3:
            break
        obj = state.objects.get(card_id)
        if not obj:
            continue
        types = obj.characteristics.types if obj.characteristics else set()
        if CardType.POKEMON in types or CardType.ENERGY in types:
            graveyard.objects.remove(card_id)
            library.objects.append(card_id)
            obj.zone = ZoneType.LIBRARY
            recovered += 1
    if recovered > 0:
        random.shuffle(library.objects)
    return []


def _potion_effect(event, state):
    """Heal 30 damage from 1 of your Pokemon."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    # Find the most damaged Pokemon
    best_id = None
    most_damage = 0
    for zone_key, zone in state.zones.items():
        if zone.type in (ZoneType.ACTIVE_SPOT, ZoneType.BENCH) and zone.owner == player_id:
            for pkm_id in zone.objects:
                pkm = state.objects.get(pkm_id)
                if pkm and pkm.state.damage_counters > most_damage:
                    most_damage = pkm.state.damage_counters
                    best_id = pkm_id
    if not best_id or most_damage == 0:
        return []
    pkm = state.objects.get(best_id)
    heal_counters = min(3, pkm.state.damage_counters)  # 30 damage = 3 counters
    pkm.state.damage_counters -= heal_counters
    return [Event(
        type=EventType.PKM_HEAL,
        payload={'pokemon_id': best_id, 'amount': heal_counters * 10},
    )]


# =============================================================================
# FIRE POKEMON
# =============================================================================

CHARMANDER = make_pokemon(
    name="Charmander",
    hp=70,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Ember", "cost": [{"type": "R", "count": 1}], "damage": 30,
         "text": "Discard an Energy from this Pokemon."},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    rarity="common",
    image_url="https://images.pokemontcg.io/sv3pt5/4.png",
)

CHARMELEON = make_pokemon(
    name="Charmeleon",
    hp=100,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Charmander",
    attacks=[
        {"name": "Slash", "cost": [{"type": "C", "count": 2}], "damage": 30, "text": ""},
        {"name": "Fire Fang", "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 2}], "damage": 60, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv3pt5/5.png",
)

CHARIZARD_EX = make_pokemon(
    name="Charizard ex",
    hp=330,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 2",
    evolves_from="Charmeleon",
    attacks=[
        {"name": "Brave Wing", "cost": [{"type": "R", "count": 1}], "damage": 60, "text": ""},
        {"name": "Burning Dark", "cost": [{"type": "R", "count": 2}, {"type": "C", "count": 1}],
         "damage": 180, "text": "This attack does 30 more damage for each Prize card your opponent has taken."},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    is_ex=True,
    rarity="rare",
    image_url="https://images.pokemontcg.io/sv3pt5/6.png",
)

ARCANINE = make_pokemon(
    name="Arcanine",
    hp=130,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Growlithe",
    attacks=[
        {"name": "Heat Tackle", "cost": [{"type": "R", "count": 2}, {"type": "C", "count": 1}],
         "damage": 120, "text": "This Pokemon also does 30 damage to itself."},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv3pt5/59.png",
)

GROWLITHE = make_pokemon(
    name="Growlithe",
    hp=80,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Bite", "cost": [{"type": "C", "count": 1}], "damage": 10, "text": ""},
        {"name": "Flare", "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}], "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    rarity="common",
    image_url="https://images.pokemontcg.io/sv3pt5/58.png",
)

# =============================================================================
# WATER POKEMON
# =============================================================================

SQUIRTLE = make_pokemon(
    name="Squirtle",
    hp=70,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Water Gun", "cost": [{"type": "W", "count": 1}], "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    rarity="common",
    image_url="https://images.pokemontcg.io/sv3pt5/7.png",
)

WARTORTLE = make_pokemon(
    name="Wartortle",
    hp=100,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Stage 1",
    evolves_from="Squirtle",
    attacks=[
        {"name": "Wave Splash", "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}], "damage": 40, "text": ""},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=2,
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv3pt5/8.png",
)

BLASTOISE_EX = make_pokemon(
    name="Blastoise ex",
    hp=330,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Stage 2",
    evolves_from="Wartortle",
    attacks=[
        {"name": "Surf", "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}], "damage": 60, "text": ""},
        {"name": "Twin Cannons", "cost": [{"type": "W", "count": 2}, {"type": "C", "count": 1}],
         "damage": 280, "text": "Discard 2 Energy from this Pokemon."},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=3,
    is_ex=True,
    rarity="rare",
    image_url="https://images.pokemontcg.io/sv3pt5/9.png",
)

LAPRAS = make_pokemon(
    name="Lapras",
    hp=130,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Icy Wind", "cost": [{"type": "W", "count": 1}], "damage": 30,
         "text": "Your opponent's Active Pokemon is now Asleep."},
        {"name": "Splash Arch", "cost": [{"type": "W", "count": 2}, {"type": "C", "count": 1}],
         "damage": 100, "text": ""},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=2,
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv3pt5/131.png",
)

# =============================================================================
# GRASS POKEMON
# =============================================================================

BULBASAUR = make_pokemon(
    name="Bulbasaur",
    hp=70,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Vine Whip", "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}], "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    rarity="common",
    image_url="https://images.pokemontcg.io/sv3pt5/1.png",
)

IVYSAUR = make_pokemon(
    name="Ivysaur",
    hp=100,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 1",
    evolves_from="Bulbasaur",
    attacks=[
        {"name": "Razor Leaf", "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}], "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=2,
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv3pt5/2.png",
)

VENUSAUR_EX = make_pokemon(
    name="Venusaur ex",
    hp=340,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 2",
    evolves_from="Ivysaur",
    attacks=[
        {"name": "Razor Leaf", "cost": [{"type": "G", "count": 2}], "damage": 80, "text": ""},
        {"name": "Giant Bloom", "cost": [{"type": "G", "count": 2}, {"type": "C", "count": 2}],
         "damage": 260, "text": "Heal 30 damage from this Pokemon."},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=3,
    is_ex=True,
    rarity="rare",
    image_url="https://images.pokemontcg.io/sv3pt5/3.png",
)

# =============================================================================
# LIGHTNING POKEMON
# =============================================================================

PIKACHU = make_pokemon(
    name="Pikachu",
    hp=60,
    pokemon_type=PokemonType.LIGHTNING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Thunder Shock", "cost": [{"type": "L", "count": 1}], "damage": 20,
         "text": "Flip a coin. If heads, your opponent's Active Pokemon is now Paralyzed."},
    ],
    weakness_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="common",
    image_url="https://images.pokemontcg.io/sv3pt5/25.png",
)

RAICHU = make_pokemon(
    name="Raichu",
    hp=120,
    pokemon_type=PokemonType.LIGHTNING.value,
    evolution_stage="Stage 1",
    evolves_from="Pikachu",
    attacks=[
        {"name": "Thunderbolt", "cost": [{"type": "L", "count": 2}, {"type": "C", "count": 1}],
         "damage": 140, "text": "Discard all Energy from this Pokemon."},
    ],
    weakness_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="rare",
    image_url="https://images.pokemontcg.io/sv3pt5/26.png",
)

# =============================================================================
# PSYCHIC POKEMON
# =============================================================================

RALTS = make_pokemon(
    name="Ralts",
    hp=60,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Smack", "cost": [{"type": "C", "count": 1}], "damage": 10, "text": ""},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="common",
    image_url="https://images.pokemontcg.io/sv2/67.png",
)

KIRLIA = make_pokemon(
    name="Kirlia",
    hp=80,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Stage 1",
    evolves_from="Ralts",
    attacks=[
        {"name": "Psychic Shot", "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}], "damage": 30, "text": ""},
    ],
    ability={"name": "Refinement", "text": "Once during your turn, you may discard a card from your hand. If you do, draw 2 cards.", "ability_type": "Ability"},
    weakness_type=PokemonType.DARKNESS.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv2/68.png",
)

GARDEVOIR_EX = make_pokemon(
    name="Gardevoir ex",
    hp=310,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Stage 2",
    evolves_from="Kirlia",
    attacks=[
        {"name": "Miracle Force", "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 2}],
         "damage": 190, "text": ""},
    ],
    ability={"name": "Psychic Embrace", "text": "As often as you like during your turn, you may attach a Basic Psychic Energy from your discard pile to 1 of your Psychic Pokemon. If you attached Energy this way, put 2 damage counters on that Pokemon.", "ability_type": "Ability"},
    weakness_type=PokemonType.DARKNESS.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=2,
    is_ex=True,
    rarity="rare",
    image_url="https://images.pokemontcg.io/sv2/86.png",
)

# =============================================================================
# FIGHTING POKEMON
# =============================================================================

RIOLU = make_pokemon(
    name="Riolu",
    hp=70,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Jab", "cost": [{"type": "F", "count": 1}], "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    rarity="common",
    image_url="https://images.pokemontcg.io/sv2/112.png",
)

LUCARIO = make_pokemon(
    name="Lucario",
    hp=120,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Stage 1",
    evolves_from="Riolu",
    attacks=[
        {"name": "Aura Sphere", "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": "This attack also does 30 damage to 1 of your opponent's Benched Pokemon."},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    rarity="rare",
    image_url="https://images.pokemontcg.io/sv2/113.png",
)

# =============================================================================
# COLORLESS POKEMON
# =============================================================================

PIDGEY = make_pokemon(
    name="Pidgey",
    hp=60,
    pokemon_type=PokemonType.COLORLESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Gust", "cost": [{"type": "C", "count": 1}], "damage": 10, "text": ""},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="common",
    image_url="https://images.pokemontcg.io/sv3pt5/16.png",
)

PIDGEOT_EX = make_pokemon(
    name="Pidgeot ex",
    hp=280,
    pokemon_type=PokemonType.COLORLESS.value,
    evolution_stage="Stage 2",
    evolves_from="Pidgeotto",
    attacks=[
        {"name": "Blustery Wind", "cost": [{"type": "C", "count": 3}],
         "damage": 120, "text": "You may have your opponent switch their Active Pokemon with 1 of their Benched Pokemon."},
    ],
    ability={"name": "Quick Search", "text": "Once during your turn, you may search your deck for a card and put it into your hand. Then, shuffle your deck.", "ability_type": "Ability"},
    weakness_type=PokemonType.LIGHTNING.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    is_ex=True,
    rarity="rare",
    image_url="https://images.pokemontcg.io/sv3/164.png",
)

# =============================================================================
# TRAINER CARDS
# =============================================================================

NEST_BALL = make_trainer_item(
    name="Nest Ball",
    text="Search your deck for a Basic Pokemon and put it onto your Bench. Then, shuffle your deck.",
    rarity="common",
    image_url="https://images.pokemontcg.io/sv1/181.png",
    resolve=_nest_ball_effect,
)

ULTRA_BALL = make_trainer_item(
    name="Ultra Ball",
    text="Discard 2 cards from your hand. Search your deck for a Pokemon and put it into your hand. Then, shuffle your deck.",
    rarity="common",
    image_url="https://images.pokemontcg.io/sv1/196.png",
    resolve=_ultra_ball_effect,
)

RARE_CANDY = make_trainer_item(
    name="Rare Candy",
    text="Choose 1 of your Basic Pokemon in play. If you have a Stage 2 card in your hand that evolves from that Pokemon, put that card onto the Basic Pokemon to evolve it, skipping the Stage 1.",
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv1/191.png",
)

SWITCH = make_trainer_item(
    name="Switch",
    text="Switch your Active Pokemon with 1 of your Benched Pokemon.",
    rarity="common",
    image_url="https://images.pokemontcg.io/sv1/194.png",
    resolve=_switch_effect,
)

POTION = make_trainer_item(
    name="Potion",
    text="Heal 30 damage from 1 of your Pokemon.",
    rarity="common",
    image_url="https://images.pokemontcg.io/sv1/188.png",
    resolve=_potion_effect,
)

SUPER_ROD = make_trainer_item(
    name="Super Rod",
    text="Choose up to 3 in any combination of Pokemon and basic Energy cards from your discard pile and shuffle them into your deck.",
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv2/188.png",
    resolve=_super_rod_effect,
)

BOSS_ORDERS = make_trainer_supporter(
    name="Boss's Orders",
    text="Switch in 1 of your opponent's Benched Pokemon to the Active Spot.",
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv2/172.png",
    resolve=_boss_orders_effect,
)

PROFESSOR_RESEARCH = make_trainer_supporter(
    name="Professor's Research",
    text="Discard your hand and draw 7 cards.",
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv1/190.png",
    resolve=_professors_research_effect,
)

IONO = make_trainer_supporter(
    name="Iono",
    text="Each player shuffles their hand into their deck. Then, each player draws a card for each of their remaining Prize cards.",
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv2/185.png",
    resolve=_iono_effect,
)

JUDGE = make_trainer_supporter(
    name="Judge",
    text="Each player shuffles their hand into their deck and draws 4 cards.",
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv1/176.png",
)

ARTAZON = make_trainer_stadium(
    name="Artazon",
    text="Once during each player's turn, that player may search their deck for a Basic Pokemon that doesn't have a Rule Box and put it onto their Bench. Then, that player shuffles their deck.",
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv2/171.png",
)

CHOICE_BELT = make_pokemon_tool(
    name="Choice Belt",
    text="The attacks of the Pokemon this card is attached to do 30 more damage to your opponent's Active Pokemon ex.",
    rarity="uncommon",
    image_url="https://images.pokemontcg.io/sv2/176.png",
)

# =============================================================================
# ENERGY CARDS
# =============================================================================

FIRE_ENERGY = make_basic_energy("Fire Energy", PokemonType.FIRE.value, image_url="https://images.pokemontcg.io/sve/2.png")
WATER_ENERGY = make_basic_energy("Water Energy", PokemonType.WATER.value, image_url="https://images.pokemontcg.io/sve/3.png")
GRASS_ENERGY = make_basic_energy("Grass Energy", PokemonType.GRASS.value, image_url="https://images.pokemontcg.io/sve/1.png")
LIGHTNING_ENERGY = make_basic_energy("Lightning Energy", PokemonType.LIGHTNING.value, image_url="https://images.pokemontcg.io/sve/4.png")
PSYCHIC_ENERGY = make_basic_energy("Psychic Energy", PokemonType.PSYCHIC.value, image_url="https://images.pokemontcg.io/sve/5.png")
FIGHTING_ENERGY = make_basic_energy("Fighting Energy", PokemonType.FIGHTING.value, image_url="https://images.pokemontcg.io/sve/6.png")
DARKNESS_ENERGY = make_basic_energy("Darkness Energy", PokemonType.DARKNESS.value, image_url="https://images.pokemontcg.io/sve/7.png")
METAL_ENERGY = make_basic_energy("Metal Energy", PokemonType.METAL.value, image_url="https://images.pokemontcg.io/sve/8.png")

# =============================================================================
# CARD REGISTRY
# =============================================================================

SV_STARTER_CARDS = {
    # Fire
    "Charmander": CHARMANDER,
    "Charmeleon": CHARMELEON,
    "Charizard ex": CHARIZARD_EX,
    "Growlithe": GROWLITHE,
    "Arcanine": ARCANINE,
    # Water
    "Squirtle": SQUIRTLE,
    "Wartortle": WARTORTLE,
    "Blastoise ex": BLASTOISE_EX,
    "Lapras": LAPRAS,
    # Grass
    "Bulbasaur": BULBASAUR,
    "Ivysaur": IVYSAUR,
    "Venusaur ex": VENUSAUR_EX,
    # Lightning
    "Pikachu": PIKACHU,
    "Raichu": RAICHU,
    # Psychic
    "Ralts": RALTS,
    "Kirlia": KIRLIA,
    "Gardevoir ex": GARDEVOIR_EX,
    # Fighting
    "Riolu": RIOLU,
    "Lucario": LUCARIO,
    # Colorless
    "Pidgey": PIDGEY,
    "Pidgeot ex": PIDGEOT_EX,
    # Trainers
    "Nest Ball": NEST_BALL,
    "Ultra Ball": ULTRA_BALL,
    "Rare Candy": RARE_CANDY,
    "Switch": SWITCH,
    "Potion": POTION,
    "Super Rod": SUPER_ROD,
    "Boss's Orders": BOSS_ORDERS,
    "Professor's Research": PROFESSOR_RESEARCH,
    "Iono": IONO,
    "Judge": JUDGE,
    "Artazon": ARTAZON,
    "Choice Belt": CHOICE_BELT,
    # Energy
    "Fire Energy": FIRE_ENERGY,
    "Water Energy": WATER_ENERGY,
    "Grass Energy": GRASS_ENERGY,
    "Lightning Energy": LIGHTNING_ENERGY,
    "Psychic Energy": PSYCHIC_ENERGY,
    "Fighting Energy": FIGHTING_ENERGY,
    "Darkness Energy": DARKNESS_ENERGY,
    "Metal Energy": METAL_ENERGY,
}

# Pre-built decks for testing
def make_fire_deck() -> list:
    """60-card Fire deck."""
    deck = []
    # Pokemon (16)
    deck.extend([CHARMANDER] * 4)
    deck.extend([CHARMELEON] * 3)
    deck.extend([CHARIZARD_EX] * 2)
    deck.extend([GROWLITHE] * 3)
    deck.extend([ARCANINE] * 2)
    deck.extend([PIDGEY] * 2)
    # Trainers (22)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 2)
    deck.extend([POTION] * 2)
    deck.extend([SUPER_ROD] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 3)
    deck.extend([IONO] * 2)
    deck.extend([BOSS_ORDERS] * 2)
    deck.extend([JUDGE] * 2)
    # Energy (22)
    deck.extend([FIRE_ENERGY] * 22)
    return deck  # 60 cards


def make_water_deck() -> list:
    """60-card Water deck."""
    deck = []
    # Pokemon (16)
    deck.extend([SQUIRTLE] * 4)
    deck.extend([WARTORTLE] * 3)
    deck.extend([BLASTOISE_EX] * 2)
    deck.extend([LAPRAS] * 3)
    deck.extend([PIDGEY] * 2)
    deck.extend([RIOLU] * 2)
    # Trainers (22)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 2)
    deck.extend([POTION] * 2)
    deck.extend([SUPER_ROD] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 3)
    deck.extend([IONO] * 2)
    deck.extend([BOSS_ORDERS] * 2)
    deck.extend([JUDGE] * 2)
    # Energy (22)
    deck.extend([WATER_ENERGY] * 22)
    return deck  # 60 cards
