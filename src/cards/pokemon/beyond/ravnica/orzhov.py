"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

Orzhov guild (W/B in MTG → Fairy/Darkness in Pokemon types).
Since FAIRY doesn't exist in this engine, FIGHTING is used as the white
substitute. Theme: gothic banking ghosts, debt, indulgence, taxes, pontiffs.

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
# Teysa Karlov evolution line — Orzhov ghost-council matriarch
# =============================================================================

def _ghost_quill_effect(attacker, state):
    """Tiny noble's tax — a basic 1-energy chip attack, no rider."""
    return []


def _final_audit_effect(attacker, state):
    """Place 1 damage counter on each of opponent's Benched Pokemon."""
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    bench_zone = state.zones.get(f"bench_{opp_id}")
    if not bench_zone:
        return []
    events = []
    for pkm_id in list(bench_zone.objects):
        if not pkm_id:
            continue
        target = state.objects.get(pkm_id)
        if not target:
            continue
        target.state.damage_counters += 1
        events.append(Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': pkm_id, 'counters': 1, 'source': 'Final Audit'},
        ))
    return events


TEYSLET = make_pokemon(
    name="Teyslet",
    hp=60,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Ghost Quill",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("A cute baby noble ghost trailing a tiny accountant's quill. "
          "Already keeps a ledger of who owes it cuddles."),
    rarity="common",
)

TEYSERIN = make_pokemon(
    name="Teyserin",
    hp=90,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Stage 1",
    evolves_from="Teyslet",
    attacks=[
        {"name": "Ledger Lash",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("A spectral middle manager forever floating ledgers around its head. "
          "Smells faintly of wax seals and fountain-pen ink."),
    rarity="uncommon",
)

TEYSA_KARLOV_EX = make_pokemon(
    name="Teysa Karlov ex",
    hp=280,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Stage 2",
    evolves_from="Teyserin",
    attacks=[
        {"name": "Tithe Bind",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80, "text": ""},
        {"name": "Final Audit",
         "cost": [{"type": "F", "count": 2}, {"type": "D", "count": 2}],
         "damage": 180,
         "text": "Place 1 damage counter on each of your opponent's Benched Pokemon.",
         "effect_fn": _final_audit_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=2,
    is_ex=True,
    text="Matriarch of the Ghost Council, who collects on every bargain — even death.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _ghostly_ledger_effect(attacker, state):
    """+20 damage if you have at least 5 cards in your discard pile."""
    grave = state.zones.get(f"graveyard_{attacker.controller}")
    if grave and len(grave.objects) >= 5:
        opp_id = next((p for p in state.players if p != attacker.controller), None)
        if not opp_id:
            return []
        active_zone = state.zones.get(f"active_spot_{opp_id}")
        if not active_zone or not active_zone.objects:
            return []
        target_id = active_zone.objects[0]
        target = state.objects.get(target_id)
        if target:
            target.state.damage_counters += 2  # +20 damage
            return [Event(
                type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
                payload={'pokemon_id': target_id, 'counters': 2,
                         'source': 'Ghostly Ledger'},
            )]
    return []


KARLOV_OF_THE_GHOST_COUNCIL = make_pokemon(
    name="Karlov of the Ghost Council",
    hp=80,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Ghostly Ledger",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": "If you have at least 5 cards in your discard pile, "
                 "this attack does 20 more damage.",
         "effect_fn": _ghostly_ledger_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=2,
    text=("A portly ghost in funeral finery who grows fatter with every "
          "dead debtor's contract he reads."),
    rarity="uncommon",
)


def _extort_effect(attacker, state):
    """Place 1 damage counter on opponent's Active Pokemon."""
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
        payload={'pokemon_id': target_id, 'counters': 1, 'source': 'Extort'},
    )]


TITHE_DRINKER = make_pokemon(
    name="Tithe Drinker",
    hp=70,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Extort",
         "cost": [{"type": "D", "count": 1}],
         "damage": 20,
         "text": "Place 1 damage counter on your opponent's Active Pokemon.",
         "effect_fn": _extort_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("A pale vampire-like imp that sips a tithe of life from "
          "everyone it passes. Strictly small change."),
    rarity="common",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _orzhova_effect(event, state):
    """Each player puts 1 card from their hand on the bottom of their deck."""
    events = []
    for pid in state.players:
        hand = state.zones.get(f"hand_{pid}")
        library = state.zones.get(f"library_{pid}")
        if not hand or not library or not hand.objects:
            continue
        # Each player picks first card (deterministic surrogate for "their choice")
        card_id = hand.objects.pop(0)
        library.objects.append(card_id)
        obj = state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.LIBRARY
        events.append(Event(
            type=EventType.PKM_DISCARD_ENERGY,
            payload={'player': pid, 'card_id': card_id,
                     'source': 'Orzhova, the Church of Deals'},
        ))
    return events


ORZHOVA_THE_CHURCH_OF_DEALS = make_trainer_stadium(
    name="Orzhova, the Church of Deals",
    text=("When you play Orzhova, the Church of Deals, each player puts "
          "1 card from their hand on the bottom of their deck."),
    rarity="uncommon",
    resolve=_orzhova_effect,
)


def _kaya_effect(event, state):
    """Opponent shuffles their hand into their deck and draws 4 cards."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    opp_id = next((p for p in state.players if p != player_id), None)
    if not opp_id:
        return []
    hand = state.zones.get(f"hand_{opp_id}")
    library = state.zones.get(f"library_{opp_id}")
    if not hand or not library:
        return []
    # Shuffle opponent's hand into their deck
    while hand.objects:
        card_id = hand.objects.pop(0)
        library.objects.append(card_id)
        obj = state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.LIBRARY
    random.shuffle(library.objects)
    # Opponent draws 4
    return _draw_cards(state, opp_id, 4)


KAYA_GHOST_ASSASSIN = make_trainer_supporter(
    name="Kaya, Ghost Assassin",
    text=("Your opponent shuffles their hand into their deck and draws 4 cards."),
    rarity="rare",
    resolve=_kaya_effect,
)


def _orzhov_cluestone_effect(event, state):
    """Search deck for one Fighting Energy and one Darkness Energy, put both in hand."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_fighting = None
    found_darkness = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.FIGHTING.value and not found_fighting:
            found_fighting = card_id
        elif ptype == PokemonType.DARKNESS.value and not found_darkness:
            found_darkness = card_id
        if found_fighting and found_darkness:
            break
    moved = []
    for cid in (found_fighting, found_darkness):
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


ORZHOV_CLUESTONE = make_trainer_item(
    name="Orzhov Cluestone",
    text=("Search your deck for a Fighting Energy and a Darkness Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_orzhov_cluestone_effect,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_ORZHOV = {
    "Teyslet": TEYSLET,
    "Teyserin": TEYSERIN,
    "Teysa Karlov ex": TEYSA_KARLOV_EX,
    "Karlov of the Ghost Council": KARLOV_OF_THE_GHOST_COUNCIL,
    "Tithe Drinker": TITHE_DRINKER,
    "Orzhova, the Church of Deals": ORZHOVA_THE_CHURCH_OF_DEALS,
    "Kaya, Ghost Assassin": KAYA_GHOST_ASSASSIN,
    "Orzhov Cluestone": ORZHOV_CLUESTONE,
}


def make_orzhov_deck() -> list:
    """60-card Orzhov deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        FIGHTING_ENERGY, DARKNESS_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    # Pokemon (16)
    deck.extend([TEYSLET] * 4)
    deck.extend([TEYSERIN] * 3)
    deck.extend([TEYSA_KARLOV_EX] * 2)
    deck.extend([KARLOV_OF_THE_GHOST_COUNCIL] * 4)
    deck.extend([TITHE_DRINKER] * 3)
    # Trainers (22)
    deck.extend([ORZHOVA_THE_CHURCH_OF_DEALS] * 2)
    deck.extend([KAYA_GHOST_ASSASSIN] * 2)
    deck.extend([ORZHOV_CLUESTONE] * 3)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 1)
    deck.extend([POTION] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([IONO] * 1)
    deck.extend([BOSS_ORDERS] * 1)
    deck.extend([JUDGE] * 1)
    # Energy (22) — Orzhov runs Fighting (white substitute) and Darkness
    deck.extend([FIGHTING_ENERGY] * 14)
    deck.extend([DARKNESS_ENERGY] * 8)
    return deck
