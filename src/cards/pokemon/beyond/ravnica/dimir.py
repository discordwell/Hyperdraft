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

# Spice-pack v1 imports — see docs/sets/pkm_brv_spice_designs.md
from src.cards.pokemon._helpers import (
    pkm_move_to_lost_zone,
    pkm_reveal_opp_hand,
    pkm_target_card_in_hand_choice,
    pkm_choose_pokemon_target,
    discard_attached_energy_cross_ctrl,
    count_poisoned_pokemon,
    _get_opp_id,
    _get_opp_active,
)
from src.engine.pokemon_status import apply_status


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


def _disguise_drip_effect(attacker, state):
    return _mill_opponent(state, attacker.controller, 1)


def _mimic_cape_effect(attacker, state):
    events = _draw_cards(state, attacker.controller, 1)
    events.extend(_mill_opponent(state, attacker.controller, 1))
    return events


LAZLET = make_pokemon(
    name="Lazlet",
    hp=60,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Disguise Drip",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 20,
         "text": "Discard the top card of your opponent's deck.",
         "effect_fn": _disguise_drip_effect},
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
         "damage": 50,
         "text": "Draw a card. Discard the top card of your opponent's deck.",
         "effect_fn": _mimic_cape_effect},
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

def _mirko_lost_recall_effect(attacker, state):
    """Lost Recall: look at the top 4 cards of opp's deck, put 1 into the Lost
    Zone, shuffle the rest back. Build-around for the LZ-count archetype.

    Spice-pack v1 — replaces the old `_mind_drinker_effect` (a 5-card reskin
    cluster). See docs/sets/pkm_brv_spice_designs.md.
    """
    opp_id = _get_opp_id(attacker.controller, state)
    if not opp_id:
        return []
    library = state.zones.get(f"library_{opp_id}")
    if not library or not library.objects:
        return []
    # Look at top 4 (or fewer).
    top_n = min(4, len(library.objects))
    top_ids = library.objects[:top_n]
    # Heuristic: pick the most "useful-to-opp" card to remove. We approximate
    # by picking the first Pokemon if any, else the first Trainer, else the
    # first card. This is what the depth scorer reads as a decision-point.
    chosen_id = None
    for cid in top_ids:
        obj = state.objects.get(cid)
        if obj and obj.characteristics and CardType.POKEMON in obj.characteristics.types:
            chosen_id = cid
            break
    if chosen_id is None:
        for cid in top_ids:
            obj = state.objects.get(cid)
            if obj and obj.characteristics and CardType.TRAINER in obj.characteristics.types:
                chosen_id = cid
                break
    if chosen_id is None and top_ids:
        chosen_id = top_ids[0]
    events: list[Event] = [Event(
        type=EventType.PKM_REVEAL,
        payload={'target_player': opp_id, 'revealed_card_ids': list(top_ids),
                 'source': attacker.id},
        source=attacker.id,
    )]
    if chosen_id is not None:
        events.extend(pkm_move_to_lost_zone(chosen_id, state, source=attacker.id))
    # Shuffle the remaining top cards back into the rest of the deck (heuristic:
    # since they're already on top, just shuffle the whole library).
    random.shuffle(library.objects)
    return events


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
        {"name": "Lost Recall",
         "cost": [{"type": "P", "count": 1}, {"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 70,
         "text": "Look at the top 4 cards of your opponent's deck. Put 1 of them into the Lost Zone. Shuffle the rest back into their deck.",
         "effect_fn": _mirko_lost_recall_effect},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=2,
    text=("A vampire who sips memories instead of blood. Victims wake "
          "missing entire decades of their lives — gone where nothing returns."),
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
    target.state.damage_counters += 2  # +20 damage
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 2, 'source': 'Hand of Cruelty'},
    )]


HAND_OF_CRUELTY = make_pokemon(
    name="Hand of Cruelty",
    hp=80,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Executioner's Strike",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": "If your opponent's Active Pokemon has any damage counters, this attack does 20 more damage.",
         "effect_fn": _hand_of_cruelty_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("Orzhov-Dimir hybrid assassin. Finishes what others start, "
          "billing the bereaved for the courtesy."),
    rarity="uncommon",
)


def _spectral_cipher_effect(attacker, state):
    """Mill a card; Trainer hits leave the opposing Active Confused."""
    from src.engine.pokemon_status import apply_status

    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    library = state.zones.get(f"library_{opp_id}")
    grave = state.zones.get(f"graveyard_{opp_id}")
    if not library or not library.objects:
        return []

    top_id = library.objects.pop(0)
    top_obj = state.objects.get(top_id)
    if grave:
        grave.objects.append(top_id)
    if top_obj:
        top_obj.zone = ZoneType.GRAVEYARD

    events = [Event(
        type=EventType.PKM_DISCARD_ENERGY,
        payload={'player': opp_id, 'card_id': top_id, 'source': 'Spectral Cipher'},
    )]
    is_trainer = (
        top_obj
        and top_obj.characteristics
        and CardType.TRAINER in top_obj.characteristics.types
    )
    if not is_trainer:
        return events

    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if active_zone and active_zone.objects:
        events.extend(apply_status(active_zone.objects[0], 'confused', state))
    return events


SOULSWORN_SPIRIT = make_pokemon(
    name="Soulsworn Spirit",
    hp=60,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Spectral Cipher",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": ("Discard the top card of your opponent's deck. If it is "
                  "a Trainer card, your opponent's Active Pokemon is now Confused."),
         "effect_fn": _spectral_cipher_effect},
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
    """Each player mills; Trainer hits leave that player's Active confused."""
    from src.engine.pokemon_status import apply_status

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
        is_trainer = (
            top_obj
            and top_obj.characteristics
            and CardType.TRAINER in top_obj.characteristics.types
        )
        if not is_trainer:
            continue
        active_zone = state.zones.get(f"active_spot_{pid}")
        if active_zone and active_zone.objects:
            events.extend(apply_status(active_zone.objects[0], 'confused', state))
    return events


DUSKMANTLE_HOUSE_OF_SHADOW = make_trainer_stadium(
    name="Duskmantle, House of Shadow",
    text=("When you play Duskmantle, House of Shadow, each player "
          "discards the top card of their deck. If a player discarded a "
          "Trainer card this way, that player's Active Pokemon is now Confused."),
    rarity="uncommon",
    resolve=_duskmantle_effect,
)


def _etrata_effect(event, state):
    """Opponent bottoms 3; Pokemon and Trainer hits become pressure."""
    from src.engine.pokemon_status import apply_status

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
    saw_pokemon = False
    saw_trainer = False
    for _ in range(min(3, len(library.objects))):
        top_id = library.objects.pop(0)
        library.objects.append(top_id)
        moved.append(top_id)
        top_obj = state.objects.get(top_id)
        if top_obj and top_obj.characteristics:
            saw_pokemon = saw_pokemon or CardType.POKEMON in top_obj.characteristics.types
            saw_trainer = saw_trainer or CardType.TRAINER in top_obj.characteristics.types
    events = [Event(
        type=EventType.PKM_DISCARD_ENERGY,
        payload={'player': opp_id, 'count': len(moved), 'source': 'Etrata, the Silencer'},
    )]
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if active_zone and active_zone.objects and saw_pokemon:
        target_id = active_zone.objects[0]
        target = state.objects.get(target_id)
        if target:
            target.state.damage_counters += 1
            events.append(Event(
                type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
                payload={'pokemon_id': target_id, 'counters': 1,
                         'source': 'Etrata, the Silencer'},
            ))
    if active_zone and active_zone.objects and saw_trainer:
        events.extend(apply_status(active_zone.objects[0], 'confused', state))
    return events


ETRATA_THE_SILENCER = make_trainer_supporter(
    name="Etrata, the Silencer",
    text=("Your opponent puts the top 3 cards of their deck on the "
          "bottom of their deck in any order. If any were Pokemon, place "
          "1 damage counter on their Active Pokemon. If any were Trainer "
          "cards, their Active Pokemon is now Confused."),
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
    return []


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
# Spice pack v1 — Decision Pressure, Energy denial, Status conditions
# =============================================================================

def _voidmage_apprentice_effect(attacker, state):
    """Energy Drain: discard 1 Energy from opp's Active. Cheap recurring denial."""
    opp_id = _get_opp_id(attacker.controller, state)
    if not opp_id:
        return []
    opp_active = _get_opp_active(opp_id, state)
    if not opp_active:
        return []
    return discard_attached_energy_cross_ctrl(
        state, target_pokemon_id=opp_active.id, count=1, source=attacker.id,
    )


VOIDMAGE_APPRENTICE = make_pokemon(
    name="Voidmage Apprentice",
    hp=60,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Energy Drain",
         "cost": [{"type": "P", "count": 1}],
         "damage": 10,
         "text": "Discard 1 Energy from your opponent's Active Pokemon.",
         "effect_fn": _voidmage_apprentice_effect},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=1,
    text=("A hooded student of the void who can't yet read it. "
          "Every spellbook she's owned has gone unaccountably blank."),
    rarity="common",
)


def _dimir_interrogation_effect(event, state):
    """Look at opp hand; pick a Pokemon and bury it on their deck. Opp draws 1."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    opp_id = _get_opp_id(player_id, state)
    if not opp_id:
        return []
    events: list[Event] = list(pkm_reveal_opp_hand(opp_id, state, source='Dimir Interrogation'))
    target_id = pkm_target_card_in_hand_choice(
        state, target_controller=opp_id, card_type_filter=CardType.POKEMON,
    )
    if target_id is not None:
        hand = state.zones[f"hand_{opp_id}"]
        library = state.zones[f"library_{opp_id}"]
        hand.objects.remove(target_id)
        library.objects.append(target_id)
        target = state.objects.get(target_id)
        if target:
            target.zone = ZoneType.LIBRARY
        events.append(Event(
            type=EventType.PKM_REVEAL,
            payload={'target_player': opp_id, 'card_id': target_id,
                     'destination': 'library_bottom', 'source': 'Dimir Interrogation'},
            source='Dimir Interrogation',
        ))
    # Opp draws 1 (per card text).
    library = state.zones.get(f"library_{opp_id}")
    hand = state.zones.get(f"hand_{opp_id}")
    if library and hand and library.objects:
        top = library.objects.pop(0)
        hand.objects.append(top)
        top_obj = state.objects.get(top)
        if top_obj:
            top_obj.zone = ZoneType.HAND
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': opp_id, 'count': 1},
        ))
    return events


DIMIR_INTERROGATION = make_trainer_item(
    name="Dimir Interrogation",
    text=("Look at your opponent's hand. Choose 1 Pokemon in their hand and "
          "put it on the bottom of their deck. Your opponent draws 1 card."),
    rarity="uncommon",
    resolve=_dimir_interrogation_effect,
)


def _tox_pawpsule_effect(event, state):
    """Poison opp Active; place damage counters scaling with already-poisoned opp Pokemon."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    opp_id = _get_opp_id(player_id, state)
    if not opp_id:
        return []
    opp_active = _get_opp_active(opp_id, state)
    if not opp_active:
        return []
    events: list[Event] = list(apply_status(opp_active.id, 'poisoned', state))
    # Count includes the just-poisoned Active.
    poisoned_count = count_poisoned_pokemon(opp_id, state)
    if poisoned_count > 0:
        opp_active.state.damage_counters = (
            getattr(opp_active.state, 'damage_counters', 0) + poisoned_count
        )
        events.append(Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': opp_active.id, 'counters': poisoned_count,
                     'source': 'Tox-Pawpsule'},
            source='Tox-Pawpsule',
        ))
    return events


TOX_PAWPSULE = make_trainer_item(
    name="Tox-Pawpsule",
    text=("Your opponent's Active Pokemon is now Poisoned. Then place 1 damage "
          "counter on it for each of your opponent's Poisoned Pokemon in play."),
    rarity="uncommon",
    resolve=_tox_pawpsule_effect,
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
    # Spice pack v1
    "Voidmage Apprentice": VOIDMAGE_APPRENTICE,
    "Dimir Interrogation": DIMIR_INTERROGATION,
    "Tox-Pawpsule": TOX_PAWPSULE,
}


def make_dimir_deck() -> list:
    """60-card Dimir deck (spice pack v1: includes Voidmage Apprentice,
    Dimir Interrogation, Tox-Pawpsule)."""
    from src.cards.pokemon.sv_starter import PSYCHIC_ENERGY, DARKNESS_ENERGY
    from src.cards.pokemon.beyond.ravnica._deck_helpers import standard_trainer_suite
    deck = []
    # Pokemon (17: +1 Voidmage Apprentice — cheap denial Basic)
    deck.extend([LAZLET] * 4)
    deck.extend([LAZANDER] * 3)
    deck.extend([LAZAV_DIMIR_MASTERMIND_EX] * 2)
    deck.extend([MIRKLET] * 3)
    deck.extend([MIRKO_VOSK_MIND_DRINKER] * 2)
    deck.extend([DIMIR_CUTPURSE] * 1)
    deck.extend([VOIDMAGE_APPRENTICE] * 2)
    # Guild trainers (11: +2 Tox-Pawpsule + 2 Dimir Interrogation, -2 Cluestone)
    deck.extend([DUSKMANTLE_HOUSE_OF_SHADOW] * 2)
    deck.extend([ETRATA_THE_SILENCER] * 1)
    deck.extend([DIMIR_CLUESTONE] * 2)
    deck.extend([DIMIR_BLEND_ENERGY] * 2)
    deck.extend([DIMIR_INTERROGATION] * 2)
    deck.extend([TOX_PAWPSULE] * 2)
    # Standard sv_starter trainer suite (19 — trimmed 3)
    deck.extend(standard_trainer_suite()[:-3])
    # Energy (13)
    deck.extend([PSYCHIC_ENERGY] * 8)
    deck.extend([DARKNESS_ENERGY] * 5)
    return deck
