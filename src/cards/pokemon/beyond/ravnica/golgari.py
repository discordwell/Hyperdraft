"""
Beyond Ravnica — Golgari guild cards.

Golgari (B/G in MTG) → Darkness/Grass in Pokemon types.
Theme: necromancy, decay, fungus, recycling-from-the-grave, undergrowth.

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
# Jarad evolution line — Golgari guildmaster
# =============================================================================

def _rotted_grasp_effect(attacker, state):
    """Tiny scaler — 0 extra. Just flavor in the small attack."""
    return []


def _consuming_decay_effect(attacker, state):
    """+10 dmg per Pokemon in your discard pile, max +50."""
    grave = state.zones.get(f"graveyard_{attacker.controller}")
    if not grave:
        return []
    pkm_count = 0
    for cid in grave.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.characteristics:
            continue
        if CardType.POKEMON in obj.characteristics.types:
            pkm_count += 1
    bonus_counters = min(pkm_count, 5)  # cap at +50 dmg = 5 counters
    if bonus_counters <= 0:
        return []
    # Hit opponent's Active
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
    target.state.damage_counters += bonus_counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={
            'pokemon_id': target_id,
            'counters': bonus_counters,
            'source': 'Jarad, Golgari Lich Lord ex',
        },
    )]


JARLET = make_pokemon(
    name="Jarlet",
    hp=60,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Mossy Hum",
         "cost": [{"type": "G", "count": 1}],
         "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("A mossy little zombie hatchling that hums old funeral dirges "
          "to itself. Smells faintly of compost and lullabies."),
    rarity="common",
)

JARADITE = make_pokemon(
    name="Jaradite",
    hp=90,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 1",
    evolves_from="Jarlet",
    attacks=[
        {"name": "Spore Bite",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("Half insect-elf, half fungus, all friendly grin. Jaradites help "
          "compost the Golgari undercity and wave hello with their mandibles."),
    rarity="uncommon",
)

JARAD_GOLGARI_LICH_LORD_EX = make_pokemon(
    name="Jarad, Golgari Lich Lord ex",
    hp=280,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 2",
    evolves_from="Jaradite",
    attacks=[
        {"name": "Rotted Grasp",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 70,
         "text": "",
         "effect_fn": _rotted_grasp_effect},
        {"name": "Consuming Decay",
         "cost": [{"type": "G", "count": 2}, {"type": "D", "count": 2}],
         "damage": 190,
         "text": ("This attack does 10 more damage for each Pokemon in your "
                  "discard pile (max 50)."),
         "effect_fn": _consuming_decay_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=3,
    is_ex=True,
    text="Lich-king of the undergrowth. Even the worms answer to him.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _kraul_sacrifice_effect(attacker, state):
    """+20 damage if you have 3+ Pokemon in your discard pile."""
    grave = state.zones.get(f"graveyard_{attacker.controller}")
    if not grave:
        return []
    pkm_count = 0
    for cid in grave.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.characteristics:
            continue
        if CardType.POKEMON in obj.characteristics.types:
            pkm_count += 1
    if pkm_count < 3:
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
    target.state.damage_counters += 2  # +20 dmg = 2 counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={
            'pokemon_id': target_id,
            'counters': 2,
            'source': 'Mazirek, Kraul Death Priest',
        },
    )]


MAZIREK_KRAUL_DEATH_PRIEST = make_pokemon(
    name="Mazirek, Kraul Death Priest",
    hp=80,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Kraul Sacrifice",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": ("If you have 3 or more Pokemon in your discard pile, "
                  "this attack does 20 more damage."),
         "effect_fn": _kraul_sacrifice_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("A pious mantis-priest. Mazirek tallies every fallen ally on his "
          "carapace and turns each death into a tiny dark blessing."),
    rarity="uncommon",
)


def _grave_feast_effect(attacker, state):
    """Mill top of your own deck. If a Pokemon is milled, heal 10 from this Pokemon."""
    library = state.zones.get(f"library_{attacker.controller}")
    grave = state.zones.get(f"graveyard_{attacker.controller}")
    if not library or not library.objects:
        return []
    top_id = library.objects.pop(0)
    top_obj = state.objects.get(top_id)
    if grave:
        grave.objects.append(top_id)
    if top_obj:
        top_obj.zone = ZoneType.GRAVEYARD
    is_pokemon = (
        top_obj
        and top_obj.characteristics
        and CardType.POKEMON in top_obj.characteristics.types
    )
    if not is_pokemon:
        return []
    if attacker.state.damage_counters > 0:
        attacker.state.damage_counters = max(
            0, attacker.state.damage_counters - 1
        )  # heal 10
    return []


GOLGARI_ROTWURM = make_pokemon(
    name="Golgari Rotwurm",
    hp=70,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Grave Feast",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": ("Discard the top card of your deck. If it is a Pokemon, "
                  "heal 10 damage from this Pokemon."),
         "effect_fn": _grave_feast_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=2,
    text=("A wriggling, smiling worm the length of a parade float. Eats "
          "anything that stops moving — including its own homework."),
    rarity="common",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _korozda_the_tangle_effect(event, state):
    """Each player retrieves 1 random Pokemon from their discard to their hand."""
    events = []
    for pid in state.players:
        grave = state.zones.get(f"graveyard_{pid}")
        hand = state.zones.get(f"hand_{pid}")
        if not grave or not hand:
            continue
        pokemon_ids = [
            cid for cid in grave.objects
            if (obj := state.objects.get(cid))
            and obj.characteristics
            and CardType.POKEMON in obj.characteristics.types
        ]
        if not pokemon_ids:
            continue
        chosen = random.choice(pokemon_ids)
        grave.objects.remove(chosen)
        hand.objects.append(chosen)
        obj = state.objects.get(chosen)
        if obj:
            obj.zone = ZoneType.HAND
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': pid, 'count': 1},
        ))
    return events


KOROZDA_THE_TANGLE = make_trainer_stadium(
    name="Korozda, the Tangle",
    text=("When you play Korozda, the Tangle, each player puts 1 random "
          "Pokemon from their discard pile into their hand."),
    rarity="uncommon",
    resolve=_korozda_the_tangle_effect,
)


def _vraska_golgari_queen_effect(event, state):
    """Shuffle 3 cards from your discard pile back into your deck."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    grave = state.zones.get(f"graveyard_{player_id}")
    library = state.zones.get(f"library_{player_id}")
    if not grave or not library:
        return []
    if not grave.objects:
        return []
    pool = list(grave.objects)
    random.shuffle(pool)
    moved = pool[:3]
    for cid in moved:
        grave.objects.remove(cid)
        library.objects.append(cid)
        obj = state.objects.get(cid)
        if obj:
            obj.zone = ZoneType.LIBRARY
    random.shuffle(library.objects)
    return [Event(
        type=EventType.DRAW,
        payload={'player': player_id, 'count': 0},
    )]


VRASKA_GOLGARI_QUEEN = make_trainer_supporter(
    name="Vraska, Golgari Queen",
    text=("Shuffle 3 cards from your discard pile back into your deck."),
    rarity="rare",
    resolve=_vraska_golgari_queen_effect,
)


def _golgari_cluestone_effect(event, state):
    """Search deck for one Darkness Energy and one Grass Energy, put them in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_dark = None
    found_grass = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.DARKNESS.value and not found_dark:
            found_dark = card_id
        elif ptype == PokemonType.GRASS.value and not found_grass:
            found_grass = card_id
        if found_dark and found_grass:
            break
    moved = []
    for cid in (found_dark, found_grass):
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


GOLGARI_CLUESTONE = make_trainer_item(
    name="Golgari Cluestone",
    text=("Search your deck for a Darkness Energy and a Grass Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_golgari_cluestone_effect,
)


# =============================================================================
# Izoni evolution line — recursion-flavored insect-elf
# =============================================================================

IZOLET = make_pokemon(
    name="Izolet",
    hp=70,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Tiny Skitter",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("A cute baby insect-elf with a thousand twinkling eyes. "
          "Each tiny pupil reflects a different memory of the undercity."),
    rarity="common",
)


def _recursive_swarm_effect(attacker, state):
    """+10 dmg per Pokemon in your discard pile, max +60."""
    grave = state.zones.get(f"graveyard_{attacker.controller}")
    if not grave:
        return []
    pkm_count = 0
    for cid in grave.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.characteristics:
            continue
        if CardType.POKEMON in obj.characteristics.types:
            pkm_count += 1
    bonus_counters = min(pkm_count, 6)  # cap at +60 dmg = 6 counters
    if bonus_counters <= 0:
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
    target.state.damage_counters += bonus_counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={
            'pokemon_id': target_id,
            'counters': bonus_counters,
            'source': 'Izoni, Thousand-Eyed',
        },
    )]


IZONI_THOUSAND_EYED = make_pokemon(
    name="Izoni, Thousand-Eyed",
    hp=120,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 1",
    evolves_from="Izolet",
    attacks=[
        {"name": "Recursive Swarm",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 60,
         "text": ("This attack does 10 more damage for each Pokemon in your "
                  "discard pile (max 60)."),
         "effect_fn": _recursive_swarm_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=2,
    text=("Mother of swarms, queen of the Devkarin necropolis. Every eye "
          "remembers a fallen drone — and calls it back."),
    rarity="rare",
)


# =============================================================================
# More stand-alone Basic Pokemon
# =============================================================================

def _venom_curl_effect(attacker, state):
    """Heal 10 (1 counter) from this Pokemon."""
    if attacker.state.damage_counters > 0:
        attacker.state.damage_counters = max(
            0, attacker.state.damage_counters - 1
        )
        return [Event(
            type=EventType.PKM_HEAL,
            payload={'pokemon_id': attacker.id, 'amount': 10},
        )]
    return []


SLUICEWAY_SCORPION = make_pokemon(
    name="Sluiceway Scorpion",
    hp=80,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Venom Curl",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": "Heal 10 damage from this Pokemon.",
         "effect_fn": _venom_curl_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("Skitters through Ravnica's drainage canals, leaching life from "
          "anything it stings to mend its own carapace."),
    rarity="common",
)


DRUDGE_BEETLE = make_pokemon(
    name="Drudge Beetle",
    hp=70,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Mandible Crunch",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=2,
    text=("A diligent compost-beetle. Drags fallen leaves and broken bones "
          "to the same neat heap with the patience of a saint."),
    rarity="common",
)


def _harvest_souls_effect(attacker, state):
    """+30 damage if opponent has any benched Pokemon."""
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    bench_zone = state.zones.get(f"bench_{opp_id}")
    if not bench_zone or not bench_zone.objects:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target:
        return []
    target.state.damage_counters += 3  # +30 dmg = 3 counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={
            'pokemon_id': target_id,
            'counters': 3,
            'source': 'Slum Reaper',
        },
    )]


SLUM_REAPER = make_pokemon(
    name="Slum Reaper",
    hp=90,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Harvest Souls",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": ("If your opponent has any Benched Pokemon, "
                  "this attack does 30 more damage."),
         "effect_fn": _harvest_souls_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=2,
    text=("Stalks the alleys at dusk, scythe rasping against the cobblestones. "
          "Hunts where the herd is fattest."),
    rarity="uncommon",
)


def _self_mill_effect(attacker, state):
    """Mill the top card of your own deck (golgari self-mill flavor)."""
    library = state.zones.get(f"library_{attacker.controller}")
    grave = state.zones.get(f"graveyard_{attacker.controller}")
    if not library or not library.objects:
        return []
    top_id = library.objects.pop(0)
    top_obj = state.objects.get(top_id)
    if grave:
        grave.objects.append(top_id)
    if top_obj:
        top_obj.zone = ZoneType.GRAVEYARD
    return []


ERSTWHILE_TROOPER = make_pokemon(
    name="Erstwhile Trooper",
    hp=60,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Bonepile Salute",
         "cost": [{"type": "G", "count": 1}],
         "damage": 30,
         "text": "Discard the top card of your deck.",
         "effect_fn": _self_mill_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("A patchwork zombie soldier still drilling for a war that ended "
          "centuries ago. Every step shakes loose another piece of itself."),
    rarity="common",
)


# =============================================================================
# Special Trainer — Golgari Blend Energy
# =============================================================================

def _golgari_blend_energy_effect(event, state):
    """Search deck for one Grass Energy AND one Darkness Energy, attach BOTH to active."""
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
    found_grass = None
    found_dark = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.GRASS.value and not found_grass:
            found_grass = card_id
        elif ptype == PokemonType.DARKNESS.value and not found_dark:
            found_dark = card_id
        if found_grass and found_dark:
            break
    events = []
    for cid in (found_grass, found_dark):
        if cid:
            library.objects.remove(cid)
            active.state.attached_energy.append(cid)
            obj = state.objects.get(cid)
            if obj:
                obj.zone = ZoneType.BATTLEFIELD
            events.append(Event(
                type=EventType.PKM_ATTACH_ENERGY,
                payload={'pokemon_id': active_id, 'energy_id': cid},
            ))
    random.shuffle(library.objects)
    return events


GOLGARI_BLEND_ENERGY = make_trainer_item(
    name="Golgari Blend Energy",
    text=("Search your deck for a Grass Energy and a Darkness Energy "
          "and attach both to your Active Pokemon. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_golgari_blend_energy_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_GOLGARI = {
    "Jarlet": JARLET,
    "Jaradite": JARADITE,
    "Jarad, Golgari Lich Lord ex": JARAD_GOLGARI_LICH_LORD_EX,
    "Mazirek, Kraul Death Priest": MAZIREK_KRAUL_DEATH_PRIEST,
    "Golgari Rotwurm": GOLGARI_ROTWURM,
    "Korozda, the Tangle": KOROZDA_THE_TANGLE,
    "Vraska, Golgari Queen": VRASKA_GOLGARI_QUEEN,
    "Golgari Cluestone": GOLGARI_CLUESTONE,
    "Izolet": IZOLET,
    "Izoni, Thousand-Eyed": IZONI_THOUSAND_EYED,
    "Sluiceway Scorpion": SLUICEWAY_SCORPION,
    "Drudge Beetle": DRUDGE_BEETLE,
    "Slum Reaper": SLUM_REAPER,
    "Erstwhile Trooper": ERSTWHILE_TROOPER,
    "Golgari Blend Energy": GOLGARI_BLEND_ENERGY,
}


def make_golgari_deck() -> list:
    """60-card Golgari deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        DARKNESS_ENERGY, GRASS_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    # Pokemon (16) — 4-3-2 Jarad line + 3-2 Izoni line + 2 Mazirek
    deck.extend([JARLET] * 4)
    deck.extend([JARADITE] * 3)
    deck.extend([JARAD_GOLGARI_LICH_LORD_EX] * 2)
    deck.extend([IZOLET] * 3)
    deck.extend([IZONI_THOUSAND_EYED] * 2)
    deck.extend([MAZIREK_KRAUL_DEATH_PRIEST] * 2)
    # Trainers (22) — 9 Golgari + 13 sv_starter
    deck.extend([KOROZDA_THE_TANGLE] * 2)
    deck.extend([VRASKA_GOLGARI_QUEEN] * 2)
    deck.extend([GOLGARI_CLUESTONE] * 3)
    deck.extend([GOLGARI_BLEND_ENERGY] * 2)
    deck.extend([NEST_BALL] * 3)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 1)
    deck.extend([POTION] * 1)
    deck.extend([SUPER_ROD] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([IONO] * 1)
    # Energy (22) — Golgari runs both Grass and Darkness
    deck.extend([GRASS_ENERGY] * 14)
    deck.extend([DARKNESS_ENERGY] * 8)
    return deck
