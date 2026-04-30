"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

Dimir guild (U/B in MTG → Psychic/Darkness in Pokemon types).
Theme: spies, secrets, mind-tricks, mill, information warfare.

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


def _mill_opponent(state, player_id: str, count: int) -> list[Event]:
    """Mill `count` cards from the top of the opponent's deck to their graveyard."""
    opp_id = next((p for p in state.players if p != player_id), None)
    if not opp_id:
        return []
    library = state.zones.get(f"library_{opp_id}")
    grave = state.zones.get(f"graveyard_{opp_id}")
    if not library:
        return []
    events = []
    for _ in range(min(count, len(library.objects))):
        top_id = library.objects.pop(0)
        if grave:
            grave.objects.append(top_id)
        top_obj = state.objects.get(top_id)
        if top_obj:
            top_obj.zone = ZoneType.GRAVEYARD
        events.append(Event(
            type=EventType.PKM_DISCARD_ENERGY,  # generic discard signal
            payload={'player': opp_id, 'card_id': top_id, 'source': 'mill'},
        ))
    return events


# =============================================================================
# Lazav evolution line — Dimir guildmaster
# =============================================================================

def _shadowstrike_effect(attacker, state):
    return _mill_opponent(state, attacker.controller, 4)


LAZLET = make_pokemon(
    name="Lazlet",
    hp=60,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Disguise Drip",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=1,
    text=("A cute shape-shifting blob that always wears tiny disguises. "
          "Its favorite costume is a paper mustache stuck to its membrane."),
    rarity="common",
)

LAZANDER = make_pokemon(
    name="Lazander",
    hp=90,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Stage 1",
    evolves_from="Lazlet",
    attacks=[
        {"name": "Mimic Cape",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=1,
    text=("Wears a shadowed cape that copies foes' moves on contact. "
          "Trainers report their own attacks coming back at them."),
    rarity="uncommon",
)

LAZAV_DIMIR_MASTERMIND_EX = make_pokemon(
    name="Lazav, Dimir Mastermind ex",
    hp=280,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Stage 2",
    evolves_from="Lazander",
    attacks=[
        {"name": "Veiled Whisper",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80, "text": ""},
        {"name": "Shadowstrike",
         "cost": [{"type": "P", "count": 2}, {"type": "D", "count": 2}],
         "damage": 200,
         "text": "Discard the top 4 cards of your opponent's deck.",
         "effect_fn": _shadowstrike_effect},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=2,
    is_ex=True,
    text="The mastermind of the Dimir, wearing a thousand stolen faces.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _cutpurse_effect(attacker, state):
    return _mill_opponent(state, attacker.controller, 1)


DIMIR_CUTPURSE = make_pokemon(
    name="Dimir Cutpurse",
    hp=80,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Pickpocket",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": "Discard the top card of your opponent's deck.",
         "effect_fn": _cutpurse_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("A nimble thief who slips through cracks in reality. "
          "Returns to its handler with stolen secrets and lint."),
    rarity="uncommon",
)


def _notion_thief_effect(attacker, state):
    events = _draw_cards(state, attacker.controller, 1)
    events.extend(_mill_opponent(state, attacker.controller, 1))
    return events


NOTION_THIEF = make_pokemon(
    name="Notion Thief",
    hp=70,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Brain Drain",
         "cost": [{"type": "P", "count": 1}],
         "damage": 20,
         "text": "Draw a card. Discard the top card of your opponent's deck.",
         "effect_fn": _notion_thief_effect},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=1,
    text=("Steals thoughts mid-formation. Victims forget what they were "
          "about to say, sometimes for years."),
    rarity="common",
)


# =============================================================================
# Mirko Vosk evolution line — mind-drinker vampire
# =============================================================================

def _mind_drinker_effect(attacker, state):
    return _mill_opponent(state, attacker.controller, 4)


MIRKLET = make_pokemon(
    name="Mirklet",
    hp=70,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Tiny Bite",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=1,
    text=("A baby vampire-spy bundled in a cloak ten sizes too big. "
          "Whispers secrets to itself it's not yet old enough to understand."),
    rarity="common",
)

MIRKO_VOSK_MIND_DRINKER = make_pokemon(
    name="Mirko Vosk, Mind Drinker",
    hp=120,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Stage 1",
    evolves_from="Mirklet",
    attacks=[
        {"name": "Mind Drink",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80,
         "text": "Discard the top 4 cards of your opponent's deck.",
         "effect_fn": _mind_drinker_effect},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=2,
    text=("A vampire who sips memories instead of blood. Victims wake "
          "missing entire decades of their lives."),
    rarity="rare",
)


# =============================================================================
# Additional stand-alone Basic Pokemon
# =============================================================================

def _dinrova_effect(attacker, state):
    return _mill_opponent(state, attacker.controller, 1)


DINROVA_HORROR = make_pokemon(
    name="Dinrova Horror",
    hp=80,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Mind Wipe",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": "Discard the top card of your opponent's deck.",
         "effect_fn": _dinrova_effect},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=2,
    text=("A many-tentacled horror that erases plans before they form. "
          "Foes forget why they came to fight."),
    rarity="uncommon",
)


def _duskmantle_seer_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


DUSKMANTLE_SEER = make_pokemon(
    name="Duskmantle Seer",
    hp=70,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Glimpse Beyond",
         "cost": [{"type": "D", "count": 1}],
         "damage": 30,
         "text": "Draw a card.",
         "effect_fn": _duskmantle_seer_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("Sees through walls and into dreams. The Dimir use them as "
          "scouts, blindfolded, since they don't need eyes."),
    rarity="uncommon",
)


def _hand_of_cruelty_effect(attacker, state):
    """+30 damage if opponent's Active has any damage counters."""
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target or target.state.damage_counters <= 0:
        return []
    target.state.damage_counters += 3  # +30 damage
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 3, 'source': 'Hand of Cruelty'},
    )]


HAND_OF_CRUELTY = make_pokemon(
    name="Hand of Cruelty",
    hp=90,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Executioner's Strike",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": "If your opponent's Active Pokemon has any damage counters, this attack does 30 more damage.",
         "effect_fn": _hand_of_cruelty_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("Orzhov-Dimir hybrid assassin. Finishes what others start, "
          "billing the bereaved for the courtesy."),
    rarity="uncommon",
)


SOULSWORN_SPIRIT = make_pokemon(
    name="Soulsworn Spirit",
    hp=60,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Spectral Slash",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40, "text": ""},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=1,
    text=("A ghost bound to silence by Dimir oath. Speaks only through "
          "the wounds it leaves."),
    rarity="common",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _duskmantle_effect(event, state):
    """Each player mills the top card of their own deck."""
    events = []
    for pid in state.players:
        library = state.zones.get(f"library_{pid}")
        grave = state.zones.get(f"graveyard_{pid}")
        if not library or not library.objects:
            continue
        top_id = library.objects.pop(0)
        if grave:
            grave.objects.append(top_id)
        top_obj = state.objects.get(top_id)
        if top_obj:
            top_obj.zone = ZoneType.GRAVEYARD
        events.append(Event(
            type=EventType.PKM_DISCARD_ENERGY,
            payload={'player': pid, 'card_id': top_id, 'source': 'Duskmantle'},
        ))
    return events


DUSKMANTLE_HOUSE_OF_SHADOW = make_trainer_stadium(
    name="Duskmantle, House of Shadow",
    text=("When you play Duskmantle, House of Shadow, each player "
          "discards the top card of their deck."),
    rarity="uncommon",
    resolve=_duskmantle_effect,
)


def _etrata_effect(event, state):
    """Opponent puts the top 3 cards of their deck on the bottom."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    opp_id = next((p for p in state.players if p != player_id), None)
    if not opp_id:
        return []
    library = state.zones.get(f"library_{opp_id}")
    if not library:
        return []
    moved = []
    for _ in range(min(3, len(library.objects))):
        top_id = library.objects.pop(0)
        library.objects.append(top_id)
        moved.append(top_id)
    return [Event(
        type=EventType.PKM_DISCARD_ENERGY,
        payload={'player': opp_id, 'count': len(moved), 'source': 'Etrata, the Silencer'},
    )]


ETRATA_THE_SILENCER = make_trainer_supporter(
    name="Etrata, the Silencer",
    text=("Your opponent puts the top 3 cards of their deck on the "
          "bottom of their deck in any order."),
    rarity="rare",
    resolve=_etrata_effect,
)


def _dimir_cluestone_effect(event, state):
    """Search deck for one Psychic Energy and one Darkness Energy, put both in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_psychic = None
    found_darkness = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.PSYCHIC.value and not found_psychic:
            found_psychic = card_id
        elif ptype == PokemonType.DARKNESS.value and not found_darkness:
            found_darkness = card_id
        if found_psychic and found_darkness:
            break
    moved = []
    for cid in (found_psychic, found_darkness):
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


DIMIR_CLUESTONE = make_trainer_item(
    name="Dimir Cluestone",
    text=("Search your deck for a Psychic Energy and a Darkness Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_dimir_cluestone_effect,
)


def _dimir_blend_energy_effect(event, state):
    """Search deck for one Psychic and one Darkness Energy, attach BOTH to active Pokemon."""
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
    found_psychic = None
    found_darkness = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.PSYCHIC.value and not found_psychic:
            found_psychic = card_id
        elif ptype == PokemonType.DARKNESS.value and not found_darkness:
            found_darkness = card_id
        if found_psychic and found_darkness:
            break
    events = []
    for cid in (found_psychic, found_darkness):
        if cid:
            library.objects.remove(cid)
            active.state.attached_energy.append(cid)
            energy_obj = state.objects.get(cid)
            if energy_obj:
                energy_obj.zone = ZoneType.BATTLEFIELD
            events.append(Event(
                type=EventType.PKM_ATTACH_ENERGY,
                payload={'pokemon_id': active_id, 'energy_id': cid, 'source': 'Dimir Blend Energy'},
            ))
    random.shuffle(library.objects)
    return events


DIMIR_BLEND_ENERGY = make_trainer_item(
    name="Dimir Blend Energy",
    text=("Search your deck for a Psychic Energy and a Darkness Energy and "
          "attach them both to your Active Pokemon. Then, shuffle your deck."),
    rarity="rare",
    resolve=_dimir_blend_energy_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_DIMIR = {
    "Lazlet": LAZLET,
    "Lazander": LAZANDER,
    "Lazav, Dimir Mastermind ex": LAZAV_DIMIR_MASTERMIND_EX,
    "Dimir Cutpurse": DIMIR_CUTPURSE,
    "Notion Thief": NOTION_THIEF,
    "Mirklet": MIRKLET,
    "Mirko Vosk, Mind Drinker": MIRKO_VOSK_MIND_DRINKER,
    "Dinrova Horror": DINROVA_HORROR,
    "Duskmantle Seer": DUSKMANTLE_SEER,
    "Hand of Cruelty": HAND_OF_CRUELTY,
    "Soulsworn Spirit": SOULSWORN_SPIRIT,
    "Duskmantle, House of Shadow": DUSKMANTLE_HOUSE_OF_SHADOW,
    "Etrata, the Silencer": ETRATA_THE_SILENCER,
    "Dimir Cluestone": DIMIR_CLUESTONE,
    "Dimir Blend Energy": DIMIR_BLEND_ENERGY,
}


def make_dimir_deck() -> list:
    """60-card Dimir deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        PSYCHIC_ENERGY, DARKNESS_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH,
    )
    deck = []
    # Pokemon (16)
    deck.extend([LAZLET] * 4)
    deck.extend([LAZANDER] * 3)
    deck.extend([LAZAV_DIMIR_MASTERMIND_EX] * 2)
    deck.extend([MIRKLET] * 3)
    deck.extend([MIRKO_VOSK_MIND_DRINKER] * 2)
    deck.extend([DIMIR_CUTPURSE] * 2)
    # Trainers (22)
    deck.extend([DUSKMANTLE_HOUSE_OF_SHADOW] * 2)
    deck.extend([ETRATA_THE_SILENCER] * 2)
    deck.extend([DIMIR_CLUESTONE] * 3)
    deck.extend([DIMIR_BLEND_ENERGY] * 2)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 2)
    deck.extend([POTION] * 1)
    deck.extend([SUPER_ROD] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 1)
    # Energy (22) — Dimir runs both Psychic and Darkness
    deck.extend([PSYCHIC_ENERGY] * 14)
    deck.extend([DARKNESS_ENERGY] * 8)
    return deck
