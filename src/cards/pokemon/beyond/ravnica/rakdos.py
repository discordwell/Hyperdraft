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
# Bloodlet evolution line — vampire bat
# =============================================================================


BLOODLET = make_pokemon(
    name="Bloodlet",
    hp=70,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Fang Nip",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("A pudgy baby bat-vampire with comically oversized fangs. "
          "It bonks itself in the chin every time it tries to bite."),
    rarity="common",
)


def _bloodletter_aclazotz_effect(attacker, state):
    """Discard 2 cards from your hand (high-cost-high-payoff flavor)."""
    pid = attacker.controller
    hand = state.zones.get(f"hand_{pid}")
    grave = state.zones.get(f"graveyard_{pid}")
    if not hand:
        return []
    events = []
    discarded = 0
    while discarded < 2 and hand.objects:
        discard_id = hand.objects.pop(0)
        if grave:
            grave.objects.append(discard_id)
        obj = state.objects.get(discard_id)
        if obj:
            obj.zone = ZoneType.GRAVEYARD
        events.append(Event(
            type=EventType.PKM_DISCARD_ENERGY,  # generic discard signal
            payload={'player': pid, 'card_id': discard_id,
                     'source': 'Bloodletter of Aclazotz'},
        ))
        discarded += 1
    return events


BLOODLETTER_OF_ACLAZOTZ = make_pokemon(
    name="Bloodletter of Aclazotz",
    hp=120,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Stage 1",
    evolves_from="Bloodlet",
    attacks=[
        {"name": "Crimson Tithe",
         "cost": [{"type": "D", "count": 2}, {"type": "C", "count": 1}],
         "damage": 100,
         "text": "Discard 2 cards from your hand.",
         "effect_fn": _bloodletter_aclazotz_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=2,
    text=("Anointed servant of the bat-god. Its bite is a sacrament "
          "and its tithe is paid in stories burned to ash."),
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon (additions)
# =============================================================================

def _spike_jester_haste_effect(attacker, state):
    """Place 1 damage counter on the attacker (haste flavor)."""
    attacker.state.damage_counters += 1
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': attacker.id, 'counters': 1,
                 'source': 'Spike Jester'},
    )]


SPIKE_JESTER = make_pokemon(
    name="Spike Jester",
    hp=80,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Headlong Charge",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": "This Pokemon does 10 damage to itself.",
         "effect_fn": _spike_jester_haste_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("A nimble imp in a checkered costume that thrives on momentum. "
          "It would rather dent its own skull than slow down."),
    rarity="common",
)


def _spawn_of_mayhem_madness_effect(attacker, state):
    """+20 damage if you have 5+ cards in your discard pile (madness flavor)."""
    pid = attacker.controller
    grave = state.zones.get(f"graveyard_{pid}")
    if not grave or len(grave.objects) < 5:
        return []
    opp_id = next((p for p in state.players if p != pid), None)
    if not opp_id:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if not target:
        return []
    target.state.damage_counters += 2  # +20 damage
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 2,
                 'source': 'Spawn of Mayhem'},
    )]


SPAWN_OF_MAYHEM = make_pokemon(
    name="Spawn of Mayhem",
    hp=90,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Demonic Frenzy",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": ("If you have 5 or more cards in your discard pile, "
                  "this attack does 20 more damage."),
         "effect_fn": _spawn_of_mayhem_madness_effect},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    text=("A horned hellion that grows stronger as the body count rises. "
          "Madness is its ladder; carnage is its rung."),
    rarity="uncommon",
)


GORE_HOUSE_CHAINWALKER = make_pokemon(
    name="Gore-House Chainwalker",
    hp=70,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Chain Slam",
         "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    text=("A chain-flailing brute that walks where the carnival's "
          "bouncers fear to stomp."),
    rarity="common",
)


def _hellhole_flailer_discard_effect(attacker, state):
    """+30 damage if you discard 1 card from your hand. Always discard if possible."""
    pid = attacker.controller
    hand = state.zones.get(f"hand_{pid}")
    grave = state.zones.get(f"graveyard_{pid}")
    if not hand or not hand.objects:
        return []
    # AI policy: always discard if hand has cards.
    discard_id = hand.objects.pop(0)
    if grave:
        grave.objects.append(discard_id)
    obj = state.objects.get(discard_id)
    if obj:
        obj.zone = ZoneType.GRAVEYARD
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
                             'source': 'Hellhole Flailer'},
                ))
    return events


HELLHOLE_FLAILER = make_pokemon(
    name="Hellhole Flailer",
    hp=60,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Reckless Flail",
         "cost": [{"type": "D", "count": 1}],
         "damage": 30,
         "text": ("You may discard a card from your hand. If you do, "
                  "this attack does 30 more damage."),
         "effect_fn": _hellhole_flailer_discard_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=1,
    text=("A pit-bound brawler whose every flail loosens another tooth, "
          "but loosens an opponent's spine in the bargain."),
    rarity="common",
)


# =============================================================================
# Rakdos Blend Energy — special item that attaches both colors directly
# =============================================================================

def _rakdos_blend_energy_effect(event, state):
    """Search deck for one DARKNESS_ENERGY and one FIRE_ENERGY, attach both
    directly to the active Pokemon, shuffle deck."""
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
    events = []
    for cid in (found_dark, found_fire):
        if cid:
            library.objects.remove(cid)
            active.state.attached_energy.append(cid)
            obj = state.objects.get(cid)
            if obj:
                obj.zone = ZoneType.BATTLEFIELD
            events.append(Event(
                type=EventType.PKM_ATTACH_ENERGY,
                payload={'pokemon_id': active_id, 'energy_id': cid,
                         'source': 'Rakdos Blend Energy'},
            ))
    random.shuffle(library.objects)
    return events


RAKDOS_BLEND_ENERGY = make_trainer_item(
    name="Rakdos Blend Energy",
    text=("Search your deck for a Darkness Energy and a Fire Energy and "
          "attach them both to your Active Pokemon. Then, shuffle your deck."),
    rarity="rare",
    resolve=_rakdos_blend_energy_effect,
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
    "Bloodlet": BLOODLET,
    "Bloodletter of Aclazotz": BLOODLETTER_OF_ACLAZOTZ,
    "Spike Jester": SPIKE_JESTER,
    "Spawn of Mayhem": SPAWN_OF_MAYHEM,
    "Gore-House Chainwalker": GORE_HOUSE_CHAINWALKER,
    "Hellhole Flailer": HELLHOLE_FLAILER,
    "Rakdos Blend Energy": RAKDOS_BLEND_ENERGY,
}


def make_rakdos_deck() -> list:
    """60-card Rakdos deck — uses sv_starter basic energies as filler."""
    from src.cards.pokemon.sv_starter import (
        DARKNESS_ENERGY, FIRE_ENERGY,
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    # Pokemon (16): Rakdos parun line + Bloodlet line + 2 extra Cacklers
    deck.extend([RAKDOMLING] * 4)
    deck.extend([RAKDOMORE] * 3)
    deck.extend([RAKDOS_LORD_OF_RIOTS_EX] * 2)
    deck.extend([BLOODLET] * 3)
    deck.extend([BLOODLETTER_OF_ACLAZOTZ] * 2)
    deck.extend([RAKDOS_CACKLER] * 2)
    # Trainers (22): 9 guild-specific + 13 sv_starter staples
    deck.extend([RIX_MAADI_DUNGEON_PALACE] * 2)
    deck.extend([TIBALT_RAKISH_INSTIGATOR] * 2)
    deck.extend([RAKDOS_CLUESTONE] * 3)
    deck.extend([RAKDOS_BLEND_ENERGY] * 2)
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 1)
    deck.extend([POTION] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 1)
    deck.extend([IONO] * 1)
    deck.extend([BOSS_ORDERS] * 1)
    # Energy (22) — Rakdos runs both Darkness and Fire
    deck.extend([DARKNESS_ENERGY] * 14)
    deck.extend([FIRE_ENERGY] * 8)
    return deck
