"""
Beyond Ravnica — Rakdos guild (B/R in MTG = Darkness/Fire in Pokemon).

Theme: clowns, devils, demonic carnival, chaotic violence, riot.
8 cards covering: Basic / Stage 1 / Stage 2 ex / extra Basics / Stadium /
Supporter / Item. Mirrors izzet.py structure.
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
# Rakdos evolution line — Demon Lord of the Cult
# =============================================================================

def _carnival_smash_effect(attacker, state):
    """Big finisher: +30 dmg if opponent's Active has any damage counters (riots flavor)."""
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
    if target.state.damage_counters > 0:
        target.state.damage_counters += 3  # +30 damage
        return [Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': target_id, 'counters': 3,
                     'source': 'Rakdos, Lord of Riots ex'},
        )]
    return []


RAKDOMLING = make_pokemon(
    name="Rakdomling",
    hp=60,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Pinprick",
         "cost": [{"type": "D", "count": 1}],
         "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("A pint-sized imp with a permanent painted smile and a tiny "
          "bell-tipped cap. It cackles at things only it can see."),
    rarity="common",
)

RAKDOMORE = make_pokemon(
    name="Rakdomore",
    hp=90,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Stage 1",
    evolves_from="Rakdomling",
    attacks=[
        {"name": "Chain Juggle",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=2,
    text=("A horned devil with a circus trunk full of barbed chains. "
          "Its juggling routine is technically a war crime."),
    rarity="uncommon",
)

RAKDOS_LORD_OF_RIOTS_EX = make_pokemon(
    name="Rakdos, Lord of Riots ex",
    hp=280,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Stage 2",
    evolves_from="Rakdomore",
    attacks=[
        {"name": "Hellfire Cackle",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80,
         "text": ""},
        {"name": "Carnival of Souls",
         "cost": [{"type": "D", "count": 2}, {"type": "R", "count": 2}],
         "damage": 200,
         "text": ("If your opponent's Active Pokemon has any damage counters "
                  "on it, this attack does 30 more damage."),
         "effect_fn": _carnival_smash_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=3,
    is_ex=True,
    text="The demon-king of Rix Maadi, paid in blood and laughter.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _self_cackle_effect(attacker, state):
    """Place 1 damage counter on attacker (haste-flavored self-damage)."""
    attacker.state.damage_counters += 1
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': attacker.id, 'counters': 1,
                 'source': 'Rakdos Cackler'},
    )]


RAKDOS_CACKLER = make_pokemon(
    name="Rakdos Cackler",
    hp=80,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Reckless Charge",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": "This Pokemon does 10 damage to itself.",
         "effect_fn": _self_cackle_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("A grinning gremlin that hits the field swinging. It cannot be "
          "made to stand still even by death itself."),
    rarity="common",
)


def _hellsteed_burnrush_effect(attacker, state):
    """+30 damage but discard a card from your hand."""
    pid = attacker.controller
    hand = state.zones.get(f"hand_{pid}")
    grave = state.zones.get(f"graveyard_{pid}")
    if not hand or not hand.objects:
        return []
    # Discard the first card in hand (engine has no choice prompt here).
    discard_id = hand.objects.pop(0)
    if grave:
        grave.objects.append(discard_id)
    obj = state.objects.get(discard_id)
    if obj:
        obj.zone = ZoneType.GRAVEYARD
    # Apply +30 damage to opponent's Active.
    opp_id = next((p for p in state.players if p != pid), None)
    events = []
    if opp_id:
        active_zone = state.zones.get(f"active_spot_{opp_id}")
        if active_zone and active_zone.objects:
            target_id = active_zone.objects[0]
            target = state.objects.get(target_id)
            if target:
                target.state.damage_counters += 3  # +30 damage
                events.append(Event(
                    type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
                    payload={'pokemon_id': target_id, 'counters': 3,
                             'source': 'Carnival Hellsteed'},
                ))
    return events


CARNIVAL_HELLSTEED = make_pokemon(
    name="Carnival Hellsteed",
    hp=70,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Burning Charge",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": ("Discard a card from your hand. If you do, this attack "
                  "does 30 more damage."),
         "effect_fn": _hellsteed_burnrush_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("A four-legged bonfire with a saddle. Stable hands at the "
          "carnival are paid hazard wages and burial insurance."),
    rarity="uncommon",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _rix_maadi_dungeon_palace_effect(event, state):
    """When played, each player discards 1 card (the first) from their hand."""
    events = []
    for pid in state.players:
        hand = state.zones.get(f"hand_{pid}")
        grave = state.zones.get(f"graveyard_{pid}")
        if not hand or not hand.objects:
            continue
        discard_id = hand.objects.pop(0)
        if grave:
            grave.objects.append(discard_id)
        obj = state.objects.get(discard_id)
        if obj:
            obj.zone = ZoneType.GRAVEYARD
        events.append(Event(
            type=EventType.PKM_DISCARD_ENERGY,  # generic discard signal
            payload={'player': pid, 'card_id': discard_id,
                     'source': 'Rix Maadi, Dungeon Palace'},
        ))
    return events


RIX_MAADI_DUNGEON_PALACE = make_trainer_stadium(
    name="Rix Maadi, Dungeon Palace",
    text=("When you play Rix Maadi, Dungeon Palace, each player discards "
          "a card from their hand."),
    rarity="uncommon",
    resolve=_rix_maadi_dungeon_palace_effect,
)


def _tibalt_rakish_instigator_effect(event, state):
    """Opponent mills 1; you draw 2."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    opp_id = next((p for p in state.players if p != player_id), None)
    events = []
    if opp_id:
        opp_lib = state.zones.get(f"library_{opp_id}")
        opp_grave = state.zones.get(f"graveyard_{opp_id}")
        if opp_lib and opp_lib.objects:
            top_id = opp_lib.objects.pop(0)
            if opp_grave:
                opp_grave.objects.append(top_id)
            top_obj = state.objects.get(top_id)
            if top_obj:
                top_obj.zone = ZoneType.GRAVEYARD
    events.extend(_draw_cards(state, player_id, 2))
    return events


TIBALT_RAKISH_INSTIGATOR = make_trainer_supporter(
    name="Tibalt, Rakish Instigator",
    text=("Your opponent discards the top card of their deck. "
          "Then, draw 2 cards."),
    rarity="rare",
    resolve=_tibalt_rakish_instigator_effect,
)


def _rakdos_cluestone_effect(event, state):
    """Search deck for one Darkness Energy and one Fire Energy, put them in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_dark = None
    found_fire = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.DARKNESS.value and not found_dark:
            found_dark = card_id
        elif ptype == PokemonType.FIRE.value and not found_fire:
            found_fire = card_id
        if found_dark and found_fire:
            break
    moved = []
    for cid in (found_dark, found_fire):
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


RAKDOS_CLUESTONE = make_trainer_item(
    name="Rakdos Cluestone",
    text=("Search your deck for a Darkness Energy and a Fire Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_rakdos_cluestone_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_RAKDOS = {
    "Rakdomling": RAKDOMLING,
    "Rakdomore": RAKDOMORE,
    "Rakdos, Lord of Riots ex": RAKDOS_LORD_OF_RIOTS_EX,
    "Rakdos Cackler": RAKDOS_CACKLER,
    "Carnival Hellsteed": CARNIVAL_HELLSTEED,
    "Rix Maadi, Dungeon Palace": RIX_MAADI_DUNGEON_PALACE,
    "Tibalt, Rakish Instigator": TIBALT_RAKISH_INSTIGATOR,
    "Rakdos Cluestone": RAKDOS_CLUESTONE,
}


def make_rakdos_deck() -> list:
    """60-card Rakdos deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        DARKNESS_ENERGY, FIRE_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    # Pokemon (16): 4-3-2 evolution line + 4 Cackler + 3 Hellsteed
    deck.extend([RAKDOMLING] * 4)
    deck.extend([RAKDOMORE] * 3)
    deck.extend([RAKDOS_LORD_OF_RIOTS_EX] * 2)
    deck.extend([RAKDOS_CACKLER] * 4)
    deck.extend([CARNIVAL_HELLSTEED] * 3)
    # Trainers (22)
    deck.extend([RIX_MAADI_DUNGEON_PALACE] * 2)
    deck.extend([TIBALT_RAKISH_INSTIGATOR] * 2)
    deck.extend([RAKDOS_CLUESTONE] * 3)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 1)
    deck.extend([POTION] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([IONO] * 1)
    deck.extend([BOSS_ORDERS] * 1)
    deck.extend([JUDGE] * 1)
    # Energy (22) — Rakdos runs both Darkness and Fire
    deck.extend([DARKNESS_ENERGY] * 14)
    deck.extend([FIRE_ENERGY] * 8)
    return deck
