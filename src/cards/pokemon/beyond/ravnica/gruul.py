"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

PoC scope: 8 Gruul (R+G in MTG = Fire+Grass in Pokemon-color terms) cards.
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
# Borborygmos evolution line — Gruul cyclops chieftain
# =============================================================================

def _boulder_toss_effect(attacker, state):
    # Pure damage; flavor only. Keep effect_fn-free path simple.
    return []


def _stampede_effect(attacker, state):
    # Pure damage; the rampage rage-bonus lives on the big attack.
    return []


def _rage_bonus_effect(attacker, state):
    """Borborygmos's rage: +20 damage per energy attached beyond the cost.

    Cost is {R}{R}{G}{G} = 4 energy. Each extra attached energy beyond
    that places 2 additional damage counters (20 dmg) on opponent's Active.
    """
    base_cost = 4
    extra = max(0, len(attacker.state.attached_energy) - base_cost)
    if extra <= 0:
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
    bonus_counters = 2 * extra  # 10 dmg per counter, +20 per extra energy
    target.state.damage_counters += bonus_counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={
            'pokemon_id': target_id,
            'counters': bonus_counters,
            'source': 'Borborygmos ex (Rage)',
        },
    )]


BORBLET = make_pokemon(
    name="Borblet",
    hp=60,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Pebble Toss",
         "cost": [{"type": "R", "count": 1}],
         "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("A tiny boulder-tossing cyclops cub. Hurls pebbles at anything "
          "that moves and giggles when they bounce off."),
    rarity="common",
)

BORBORGREW = make_pokemon(
    name="Borborgrew",
    hp=90,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Borblet",
    attacks=[
        {"name": "Herd Charge",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    text=("A roaming herd-leader covered in moss. Where it sleeps, "
          "the wilds reclaim the stones in a single night."),
    rarity="uncommon",
)

BORBORYGMOS_EX = make_pokemon(
    name="Borborygmos ex",
    hp=280,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 2",
    evolves_from="Borborgrew",
    attacks=[
        {"name": "Boulder Toss",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80,
         "text": "",
         "effect_fn": _boulder_toss_effect},
        {"name": "Stampede",
         "cost": [{"type": "R", "count": 2}, {"type": "G", "count": 2}],
         "damage": 200,
         "text": ("This attack does 20 more damage for each Energy attached "
                  "to this Pokemon beyond its cost."),
         "effect_fn": _rage_bonus_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=4,
    is_ex=True,
    text="The cyclops chieftain of the Gruul Clans. The ground shakes when he laughs.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _cascade_attach_effect(attacker, state):
    """Search deck for a basic energy and attach it to a benched Pokemon."""
    player_id = attacker.controller
    library = state.zones.get(f"library_{player_id}")
    if not library or not library.objects:
        return []
    # Find an attachable basic energy in deck
    energy_id = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY in obj.characteristics.types:
            energy_id = card_id
            break
    if not energy_id:
        return []
    # Find a benched Pokemon to attach to
    bench_zone = state.zones.get(f"bench_{player_id}")
    bench_target_id = None
    if bench_zone:
        for slot_id in bench_zone.objects:
            if slot_id:
                bench_target_id = slot_id
                break
    if not bench_target_id:
        return []
    bench_target = state.objects.get(bench_target_id)
    if not bench_target:
        return []
    # Move energy from deck to attached_energy
    library.objects.remove(energy_id)
    bench_target.state.attached_energy.append(energy_id)
    energy_obj = state.objects.get(energy_id)
    if energy_obj:
        energy_obj.zone = ZoneType.BATTLEFIELD
    random.shuffle(library.objects)
    return [Event(
        type=EventType.PKM_ATTACH_ENERGY,
        payload={
            'pokemon_id': bench_target_id,
            'energy_id': energy_id,
            'source': 'Burning-Tree Emissary (Cascade)',
        },
    )]


BURNING_TREE_EMISSARY = make_pokemon(
    name="Burning-Tree Emissary",
    hp=80,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Cascade",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": ("Search your deck for a basic Energy and attach it to "
                  "1 of your Benched Pokemon. Shuffle your deck."),
         "effect_fn": _cascade_attach_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("A two-headed shaman that radiates wild mana. Wherever it walks, "
          "embers and saplings bloom in equal measure."),
    rarity="uncommon",
)


def _bloodrush_effect(attacker, state):
    """Place 1 extra damage counter (10 dmg) on opponent's Active."""
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
        payload={
            'pokemon_id': target_id,
            'counters': 1,
            'source': 'Ghor-Clan Rampager (Bloodrush)',
        },
    )]


GHOR_CLAN_RAMPAGER = make_pokemon(
    name="Ghor-Clan Rampager",
    hp=70,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Bloodrush",
         "cost": [{"type": "R", "count": 1}],
         "damage": 20,
         "text": "Place 1 extra damage counter on the Defending Pokemon.",
         "effect_fn": _bloodrush_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("A centaur berserker that smells fear from miles away. "
          "It charges first and asks territorial questions never."),
    rarity="common",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _skarrg_attach_effect(event, state):
    """Each player attaches 1 basic energy from hand to their Active."""
    events = []
    for pid in state.players:
        hand = state.zones.get(f"hand_{pid}")
        active_zone = state.zones.get(f"active_spot_{pid}")
        if not hand or not active_zone or not active_zone.objects:
            continue
        active_id = active_zone.objects[0]
        active = state.objects.get(active_id)
        if not active:
            continue
        # Find a basic energy in hand
        energy_id = None
        for card_id in hand.objects:
            obj = state.objects.get(card_id)
            if not obj or not obj.characteristics:
                continue
            if CardType.ENERGY in obj.characteristics.types:
                energy_id = card_id
                break
        if not energy_id:
            continue  # skip if no energies in hand
        hand.objects.remove(energy_id)
        active.state.attached_energy.append(energy_id)
        energy_obj = state.objects.get(energy_id)
        if energy_obj:
            energy_obj.zone = ZoneType.BATTLEFIELD
        events.append(Event(
            type=EventType.PKM_ATTACH_ENERGY,
            payload={
                'pokemon_id': active_id,
                'energy_id': energy_id,
                'source': 'Skarrg, the Rage Pits',
            },
        ))
    return events


SKARRG_THE_RAGE_PITS = make_trainer_stadium(
    name="Skarrg, the Rage Pits",
    text=("When you play Skarrg, the Rage Pits, each player may attach "
          "1 basic Energy from their hand to their Active Pokemon."),
    rarity="uncommon",
    resolve=_skarrg_attach_effect,
)


def _domri_rade_effect(event, state):
    """Discard top 3 of deck. Per Pokemon discarded, 1 damage counter on opp Active."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    grave = state.zones.get(f"graveyard_{player_id}")
    if not library or not grave:
        return []
    pokemon_count = 0
    events = []
    for _ in range(min(3, len(library.objects))):
        top_id = library.objects.pop(0)
        top_obj = state.objects.get(top_id)
        grave.objects.append(top_id)
        if top_obj:
            top_obj.zone = ZoneType.GRAVEYARD
            if top_obj.characteristics and CardType.POKEMON in top_obj.characteristics.types:
                pokemon_count += 1
    if pokemon_count <= 0:
        return events
    opp_id = next((p for p in state.players if p != player_id), None)
    if not opp_id:
        return events
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return events
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target:
        return events
    target.state.damage_counters += pokemon_count
    events.append(Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={
            'pokemon_id': target_id,
            'counters': pokemon_count,
            'source': 'Domri Rade',
        },
    ))
    return events


DOMRI_RADE = make_trainer_supporter(
    name="Domri Rade",
    text=("Discard the top 3 cards of your deck. Place 1 damage counter on "
          "your opponent's Active Pokemon for each Pokemon you discarded."),
    rarity="rare",
    resolve=_domri_rade_effect,
)


def _gruul_cluestone_effect(event, state):
    """Search deck for a Fire Energy and a Grass Energy, put them in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_fire = None
    found_grass = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.FIRE.value and not found_fire:
            found_fire = card_id
        elif ptype == PokemonType.GRASS.value and not found_grass:
            found_grass = card_id
        if found_fire and found_grass:
            break
    moved = []
    for cid in (found_fire, found_grass):
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


GRUUL_CLUESTONE = make_trainer_item(
    name="Gruul Cluestone",
    text=("Search your deck for a Fire Energy and a Grass Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_gruul_cluestone_effect,
)


# =============================================================================
# Ruric Thar evolution line — twin-headed cyclops berserker
# =============================================================================

RURICLET = make_pokemon(
    name="Ruriclet",
    hp=70,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Twin Tantrum",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("Cute cyclops-troll twins joined at the shoulder. They argue "
          "constantly but always agree on smashing things together."),
    rarity="common",
)


def _rage_backlash_effect(attacker, state):
    """Place 1 damage counter on attacker (rage backlash)."""
    if not attacker:
        return []
    attacker.state.damage_counters += 1
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={
            'pokemon_id': attacker.id,
            'counters': 1,
            'source': 'Ruric Thar (Backlash)',
        },
    )]


RURIC_THAR_THE_UNBOWED = make_pokemon(
    name="Ruric Thar, the Unbowed",
    hp=120,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Ruriclet",
    attacks=[
        {"name": "Unbowed Smash",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80,
         "text": "Place 1 damage counter on this Pokemon.",
         "effect_fn": _rage_backlash_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    text="The Unbowed two-headed cyclops, scourge of the Ninth District.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon (extended)
# =============================================================================

ATARKA_PUP = make_pokemon(
    name="Atarka Pup",
    hp=80,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Big Swing",
         "cost": [{"type": "R", "count": 2}, {"type": "C", "count": 1}],
         "damage": 80, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    text=("A juvenile dragon-broodling of clan Atarka. Eats first, "
          "asks scaled questions never. Already bigger than most warriors."),
    rarity="uncommon",
)


def _bloodied_bonus_effect(attacker, state):
    """Capped +60 (+10 per damage counter on attacker, max 6 counters worth)."""
    if not attacker:
        return []
    counters = min(attacker.state.damage_counters, 6)
    bonus = counters  # 1 counter = 10 dmg = 1 damage counter
    if bonus <= 0:
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
    target.state.damage_counters += bonus
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={
            'pokemon_id': target_id,
            'counters': bonus,
            'source': 'Skarrgan Hellkite (Bloodied)',
        },
    )]


SKARRGAN_HELLKITE = make_pokemon(
    name="Skarrgan Hellkite",
    hp=90,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Bloodied Roar",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": ("This attack does 10 more damage for each damage counter "
                  "on this Pokemon (max +60)."),
         "effect_fn": _bloodied_bonus_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    text=("A red-scaled dragon born from the rage pits. The angrier and "
          "bloodier it gets, the harder it hits."),
    rarity="rare",
)


def _wood_elves_effect(attacker, state):
    """Search deck for a Grass Energy and attach it to active Pokemon."""
    from src.cards.pokemon.sv_starter import GRASS_ENERGY
    player_id = attacker.controller
    library = state.zones.get(f"library_{player_id}")
    active_zone = state.zones.get(f"active_spot_{player_id}")
    if not library or not active_zone or not active_zone.objects:
        return []
    active_id = active_zone.objects[0]
    active = state.objects.get(active_id)
    if not active:
        return []
    # Find a Grass Energy in deck
    energy_id = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.GRASS.value:
            energy_id = card_id
            break
    if not energy_id:
        return []
    library.objects.remove(energy_id)
    active.state.attached_energy.append(energy_id)
    energy_obj = state.objects.get(energy_id)
    if energy_obj:
        energy_obj.zone = ZoneType.BATTLEFIELD
    random.shuffle(library.objects)
    return [Event(
        type=EventType.PKM_ATTACH_ENERGY,
        payload={
            'pokemon_id': active_id,
            'energy_id': energy_id,
            'source': 'Wood Elves',
        },
    )]


WOOD_ELVES = make_pokemon(
    name="Wood Elves",
    hp=70,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Mana Dork",
         "cost": [{"type": "G", "count": 1}],
         "damage": 20,
         "text": ("Search your deck for a Grass Energy and attach it to "
                  "your Active Pokemon. Shuffle your deck."),
         "effect_fn": _wood_elves_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("Quiet forest scouts who plant a sapling for every step. "
          "They speak in pollen and never raise their voice."),
    rarity="common",
)


def _burning_tree_mill_effect(attacker, state):
    """Mill the top card of EACH player's deck."""
    events = []
    for pid in state.players:
        library = state.zones.get(f"library_{pid}")
        grave = state.zones.get(f"graveyard_{pid}")
        if not library or not grave or not library.objects:
            continue
        top_id = library.objects.pop(0)
        grave.objects.append(top_id)
        top_obj = state.objects.get(top_id)
        if top_obj:
            top_obj.zone = ZoneType.GRAVEYARD
    return events


BURNING_TREE_SHAMAN = make_pokemon(
    name="Burning-Tree Shaman",
    hp=60,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Wild Communion",
         "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": "Each player discards the top card of their deck.",
         "effect_fn": _burning_tree_mill_effect},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    text=("A green-flame druid who chants the names of dead trees. "
          "The Burning-Tree clan listens for omens in every ash."),
    rarity="uncommon",
)


# =============================================================================
# Special Energy / Trainer (extended)
# =============================================================================

def _gruul_blend_effect(event, state):
    """Search deck for one Fire Energy and one Grass Energy, attach BOTH to active."""
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
    found_grass = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.FIRE.value and not found_fire:
            found_fire = card_id
        elif ptype == PokemonType.GRASS.value and not found_grass:
            found_grass = card_id
        if found_fire and found_grass:
            break
    events = []
    for cid in (found_fire, found_grass):
        if cid:
            library.objects.remove(cid)
            active.state.attached_energy.append(cid)
            obj = state.objects.get(cid)
            if obj:
                obj.zone = ZoneType.BATTLEFIELD
            events.append(Event(
                type=EventType.PKM_ATTACH_ENERGY,
                payload={
                    'pokemon_id': active_id,
                    'energy_id': cid,
                    'source': 'Gruul Blend Energy',
                },
            ))
    random.shuffle(library.objects)
    return events


GRUUL_BLEND_ENERGY = make_trainer_item(
    name="Gruul Blend Energy",
    text=("Search your deck for a Fire Energy and a Grass Energy and attach "
          "both to your Active Pokemon. Then, shuffle your deck."),
    rarity="rare",
    resolve=_gruul_blend_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_GRUUL = {
    "Borblet": BORBLET,
    "Borborgrew": BORBORGREW,
    "Borborygmos ex": BORBORYGMOS_EX,
    "Burning-Tree Emissary": BURNING_TREE_EMISSARY,
    "Ghor-Clan Rampager": GHOR_CLAN_RAMPAGER,
    "Skarrg, the Rage Pits": SKARRG_THE_RAGE_PITS,
    "Domri Rade": DOMRI_RADE,
    "Gruul Cluestone": GRUUL_CLUESTONE,
    "Ruriclet": RURICLET,
    "Ruric Thar, the Unbowed": RURIC_THAR_THE_UNBOWED,
    "Atarka Pup": ATARKA_PUP,
    "Skarrgan Hellkite": SKARRGAN_HELLKITE,
    "Wood Elves": WOOD_ELVES,
    "Burning-Tree Shaman": BURNING_TREE_SHAMAN,
    "Gruul Blend Energy": GRUUL_BLEND_ENERGY,
}


def make_gruul_deck() -> list:
    """60-card Gruul deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        FIRE_ENERGY, GRASS_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    # Pokemon (16) — Borborygmos line + Ruric Thar line + filler
    deck.extend([BORBLET] * 4)
    deck.extend([BORBORGREW] * 3)
    deck.extend([BORBORYGMOS_EX] * 2)
    deck.extend([RURICLET] * 3)
    deck.extend([RURIC_THAR_THE_UNBOWED] * 2)
    deck.extend([BURNING_TREE_EMISSARY] * 2)
    # Trainers (22)
    deck.extend([SKARRG_THE_RAGE_PITS] * 2)
    deck.extend([DOMRI_RADE] * 2)
    deck.extend([GRUUL_CLUESTONE] * 3)
    deck.extend([GRUUL_BLEND_ENERGY] * 2)
    deck.extend([NEST_BALL] * 3)
    deck.extend([ULTRA_BALL] * 1)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 1)
    deck.extend([POTION] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([IONO] * 1)
    deck.extend([BOSS_ORDERS] * 1)
    deck.extend([JUDGE] * 1)
    # Energy (22) — Gruul runs both Fire and Grass
    deck.extend([FIRE_ENERGY] * 14)
    deck.extend([GRASS_ENERGY] * 8)
    return deck
