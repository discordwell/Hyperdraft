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

# Spice-pack v1 imports — see docs/sets/pkm_brv_spice_designs.md
from src.cards.pokemon._helpers import (
    pkm_move_to_lost_zone,
    pkm_apply_prize_tax,
    pkm_modal_choice,
    pkm_choose_pokemon_target,
    pkm_reveal_opp_hand,
    _get_opp_id,
    _get_opp_active,
)


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


# =============================================================================
# Teysa Karlov evolution line — Orzhov ghost-council matriarch
# =============================================================================

def _ghost_quill_effect(attacker, state):
    """Tiny noble's tax: chip the opponent's Active."""
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
        payload={'pokemon_id': target_id, 'counters': 1,
                 'source': 'Ghost Quill'},
    )]


def _ledger_lash_effect(attacker, state):
    """Heal the attacker and chip the opponent's Active."""
    events = []
    if attacker.state.damage_counters > 0:
        attacker.state.damage_counters -= 1
        events.append(Event(
            type=EventType.PKM_HEAL,
            payload={'pokemon_id': attacker.id, 'amount': 10,
                     'source': 'Ledger Lash'},
        ))
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return events
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    if not active_zone or not active_zone.objects:
        return events
    target_id = active_zone.objects[0]
    target = state.objects.get(target_id)
    if target:
        target.state.damage_counters += 1
        events.append(Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': target_id, 'counters': 1,
                     'source': 'Ledger Lash'},
        ))
    return events


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
         "damage": 20,
         "text": "Place 1 damage counter on your opponent's Active Pokemon.",
         "effect_fn": _ghost_quill_effect},
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
         "damage": 50,
         "text": ("Heal 10 damage from this Pokemon. Then place 1 damage "
                  "counter on your opponent's Active Pokemon."),
         "effect_fn": _ledger_lash_effect},
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
         "damage": 50,
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
    """Opponent shuffles hand into deck, draws, and pays for hidden cards."""
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
    moved = 0
    while hand.objects:
        card_id = hand.objects.pop(0)
        library.objects.append(card_id)
        obj = state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.LIBRARY
        moved += 1
    random.shuffle(library.objects)
    events = _draw_cards(state, opp_id, 4)
    if moved:
        active_zone = state.zones.get(f"active_spot_{opp_id}")
        if active_zone and active_zone.objects:
            target_id = active_zone.objects[0]
            target = state.objects.get(target_id)
            if target:
                target.state.damage_counters += 1
                events.append(Event(
                    type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
                    payload={'pokemon_id': target_id, 'counters': 1,
                             'source': 'Kaya, Ghost Assassin'},
                ))
    return events


KAYA_GHOST_ASSASSIN = make_trainer_supporter(
    name="Kaya, Ghost Assassin",
    text=("Your opponent shuffles their hand into their deck and draws 4 cards. "
          "If they shuffled any cards into their deck this way, place 1 "
          "damage counter on their Active Pokemon."),
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
    return []


ORZHOV_CLUESTONE = make_trainer_item(
    name="Orzhov Cluestone",
    text=("Search your deck for a Fighting Energy and a Darkness Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_orzhov_cluestone_effect,
)


# =============================================================================
# Obzlet → Obzedat evolution line — the Ghost Council itself
# =============================================================================

def _council_punishment_effect(attacker, state):
    """Place 2 damage counters on each of opponent's Benched Pokemon."""
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
        target.state.damage_counters += 2
        events.append(Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': pkm_id, 'counters': 2,
                     'source': 'Council Punishment'},
        ))
    return events


OBZLET = make_pokemon(
    name="Obzlet",
    hp=70,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Tiny Decree",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("A cute trio of tiny spectral nobles in tiny robes, holding "
          "tiny gavels and arguing in tiny voices over tiny grievances."),
    rarity="common",
)

OBZEDAT_GHOST_COUNCIL = make_pokemon(
    name="Obzedat, Ghost Council",
    hp=120,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Stage 1",
    evolves_from="Obzlet",
    attacks=[
        {"name": "Council Punishment",
         "cost": [{"type": "F", "count": 1}, {"type": "D", "count": 1}],
         "damage": 80,
         "text": "Place 2 damage counters on each of your opponent's "
                 "Benched Pokemon.",
         "effect_fn": _council_punishment_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=2,
    text=("Five spectral patriarchs ruling Orzhov by unanimous, eternal, "
          "and merciless verdict. Their gaze settles every debt."),
    rarity="rare",
)


# =============================================================================
# More stand-alone Basic Pokemon
# =============================================================================

def _drain_life_effect(attacker, state):
    """Heal 30 (3 counters) from this Pokemon."""
    if attacker.state.damage_counters <= 0:
        return []
    healed = min(3, attacker.state.damage_counters)
    attacker.state.damage_counters -= healed
    return [Event(
        type=EventType.PKM_HEAL,
        payload={'pokemon_id': attacker.id, 'amount': healed * 10,
                 'source': 'Drain Life'},
    )]


VIZKOPA_GUILDMAGE = make_pokemon(
    name="Vizkopa Guildmage",
    hp=80,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Drain Life",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": "Heal 30 damage from this Pokemon.",
         "effect_fn": _drain_life_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("A two-tone mage who siphons vitality through brokered contracts. "
          "Her smile is always written in someone else's blood."),
    rarity="uncommon",
)


def _cartel_contract_effect(pokemon, state):
    """Convert a card in hand into drain tempo once per turn."""
    if getattr(pokemon.state, 'ability_used_this_turn', False):
        return []
    player_id = pokemon.controller
    hand = state.zones.get(f"hand_{player_id}")
    library = state.zones.get(f"library_{player_id}")
    if not hand or not library or not hand.objects:
        return []

    card_id = hand.objects.pop(0)
    library.objects.append(card_id)
    moved = state.objects.get(card_id)
    if moved:
        moved.zone = ZoneType.LIBRARY
    pokemon.state.ability_used_this_turn = True

    events = [Event(
        type=EventType.PKM_DISCARD_ENERGY,
        payload={'player': player_id, 'card_id': card_id,
                 'source': 'Cartel Aristocrat'},
    )]

    active_zone = state.zones.get(f"active_spot_{player_id}")
    if active_zone and active_zone.objects:
        active = state.objects.get(active_zone.objects[0])
        if active and active.state.damage_counters > 0:
            healed = min(2, active.state.damage_counters)
            active.state.damage_counters -= healed
            events.append(Event(
                type=EventType.PKM_HEAL,
                payload={'pokemon_id': active.id, 'amount': healed * 10,
                         'source': 'Cartel Aristocrat'},
            ))

    opp_id = next((p for p in state.players if p != player_id), None)
    if not opp_id:
        return events
    opp_active = state.zones.get(f"active_spot_{opp_id}")
    if not opp_active or not opp_active.objects:
        return events
    target_id = opp_active.objects[0]
    target = state.objects.get(target_id)
    if target:
        target.state.damage_counters += 1
        events.append(Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={'pokemon_id': target_id, 'counters': 1,
                     'source': 'Cartel Aristocrat'},
        ))
    return events


CARTEL_ARISTOCRAT = make_pokemon(
    name="Cartel Aristocrat",
    hp=70,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Sacrificial Gambit",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40, "text": ""},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    ability={
        "name": "Contractual Immunity",
        "text": ("Once during your turn, you may put a card from your hand "
                 "on the bottom of your deck. If you do, heal 20 damage "
                 "from your Active Pokemon and place 1 damage counter on "
                 "your opponent's Active Pokemon."),
        "ability_type": "Ability",
        "effect_fn": _cartel_contract_effect,
    },
    text=("Born of old money and older promises. She trades servants "
          "for safety with a polite, untroubled smile."),
    rarity="uncommon",
)


def _treasury_recover_effect(attacker, state):
    """Retrieve 1 random Pokemon card from your discard to your hand."""
    grave = state.zones.get(f"graveyard_{attacker.controller}")
    hand = state.zones.get(f"hand_{attacker.controller}")
    if not grave or not hand:
        return []
    pokemon_ids = []
    for cid in grave.objects:
        obj = state.objects.get(cid)
        if obj and obj.characteristics and CardType.POKEMON in obj.characteristics.types:
            pokemon_ids.append(cid)
    if not pokemon_ids:
        return []
    chosen = random.choice(pokemon_ids)
    grave.objects.remove(chosen)
    hand.objects.append(chosen)
    obj = state.objects.get(chosen)
    if obj:
        obj.zone = ZoneType.HAND
    return []


TREASURY_THRULL = make_pokemon(
    name="Treasury Thrull",
    hp=90,
    pokemon_type=PokemonType.DARKNESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Vault Reclaim",
         "cost": [{"type": "D", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": "Put a random Pokemon card from your discard pile "
                 "into your hand.",
         "effect_fn": _treasury_recover_effect},
    ],
    weakness_type=PokemonType.GRASS.value,
    retreat_cost=2,
    text=("A hulking servitor wrought of bone and gold leaf. It guards "
          "the cathedral vaults and remembers every coin."),
    rarity="uncommon",
)


def _dutiful_strike_effect(attacker, state):
    """Debt collection: stronger once the opposing Active is marked."""
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
    target.state.damage_counters += 1
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 1,
                 'source': 'Knight of Obligation'},
    )]


KNIGHT_OF_OBLIGATION = make_pokemon(
    name="Knight of Obligation",
    hp=60,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Dutiful Strike",
         "cost": [{"type": "F", "count": 1}],
         "damage": 30,
         "text": ("If your opponent's Active Pokemon already has any damage "
                  "counters, this attack does 10 more damage."),
         "effect_fn": _dutiful_strike_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("Sworn to a covenant older than her bloodline. Her vows "
          "weigh heavier than her armor, and she is plated in silver."),
    rarity="common",
)


# =============================================================================
# Special Energy / Item — Orzhov Blend Energy
# =============================================================================

def _orzhov_blend_energy_effect(event, state):
    """Search deck for one Fighting Energy AND one Darkness Energy and
    attach BOTH directly to the active Pokemon."""
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
    events = []
    for cid in (found_fighting, found_darkness):
        if cid:
            library.objects.remove(cid)
            active.state.attached_energy.append(cid)
            energy_obj = state.objects.get(cid)
            if energy_obj:
                energy_obj.zone = ZoneType.BATTLEFIELD
            events.append(Event(
                type=EventType.PKM_ATTACH_ENERGY,
                payload={'pokemon_id': active_id, 'energy_id': cid,
                         'source': 'Orzhov Blend Energy'},
            ))
    random.shuffle(library.objects)
    return events


ORZHOV_BLEND_ENERGY = make_trainer_item(
    name="Orzhov Blend Energy",
    text=("Search your deck for a Fighting Energy and a Darkness Energy "
          "and attach both to your Active Pokemon. Then, shuffle your deck."),
    rarity="rare",
    resolve=_orzhov_blend_energy_effect,
)


# =============================================================================
# Set registry
# =============================================================================

# =============================================================================
# Spice pack v1 — Prize manipulation + Lost Zone
# =============================================================================

def _obzedat_souls_tax_effect(attacker, state):
    """Soul's Tax: opp reveals their hand. Information asymmetry."""
    opp_id = _get_opp_id(attacker.controller, state)
    if not opp_id:
        return []
    return list(pkm_reveal_opp_hand(opp_id, state, source=attacker.id))


def _obzedat_spectral_decree_effect(attacker, state):
    """Spectral Decree: modal — KO a low-HP opp bench Pokemon OR apply prize tax.

    Heuristic v1: prefer mode A (KO bench) if a legal target exists with
    HP ≤ 30 effective; else mode B (prize tax). Build-around target
    fingerprint S=3 D=3 Z=2 A=3 Y=3 = 14 (build-around).
    """
    opp_id = _get_opp_id(attacker.controller, state)
    if not opp_id:
        return []
    # Check for a KO-eligible bench Pokemon.
    bench = state.zones.get(f"bench_{opp_id}")
    ko_target = None
    if bench:
        for bid in bench.objects:
            obj = state.objects.get(bid)
            if not obj or not obj.card_def:
                continue
            remaining_hp = (
                (obj.card_def.hp or 0)
                - (getattr(obj.state, 'damage_counters', 0) * 10)
            )
            if remaining_hp <= 30 and remaining_hp > 0:
                ko_target = bid
                break
    pick = 0 if ko_target else 1

    def mode_a(st):
        # KO the bench target outright.
        if not ko_target:
            return []
        target = st.objects.get(ko_target)
        if not target:
            return []
        # Mark as KO'd by ramping damage to lethal.
        target.state.damage_counters = (
            getattr(target.state, 'damage_counters', 0)
            + (target.card_def.hp or 30) // 10
        )
        return [Event(
            type=EventType.PKM_KNOCKOUT,
            payload={'pokemon_id': ko_target, 'attacker_id': attacker.id,
                     'source': attacker.id},
            source=attacker.id,
        )]

    def mode_b(st):
        return pkm_apply_prize_tax(opp_id, st, amount=1, source=attacker.id)

    return pkm_modal_choice(
        attacker.controller, state,
        source=attacker.id,
        mode_names=('KO Bench', 'Prize Tax'),
        mode_effects=(mode_a, mode_b),
        heuristic_pick=pick,
    )


OBZEDAT_GHOST_COUNCIL_EX = make_pokemon(
    name="Obzedat, Ghost Council ex",
    hp=280,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Stage 2",
    evolves_from="Karlov of the Ghost Council",
    attacks=[
        {"name": "Soul's Tax",
         "cost": [{"type": "F", "count": 1}, {"type": "D", "count": 1}],
         "damage": 60,
         "text": "Your opponent reveals their hand.",
         "effect_fn": _obzedat_souls_tax_effect},
        {"name": "Spectral Decree",
         "cost": [{"type": "F", "count": 1}, {"type": "D", "count": 1},
                  {"type": "C", "count": 2}],
         "damage": 150,
         "text": "Choose one: KO an opp Benched Pokemon with 30 HP or less; OR your opponent takes 1 fewer Prize from their next KO against you.",
         "effect_fn": _obzedat_spectral_decree_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=2,
    is_ex=True,
    text=("The Ghost Council collects debts the living forgot. Three ghosts "
          "in one robe, all of them in a hurry."),
    rarity="rare",
)


def _sanguine_sacrament_effect(event, state):
    """Sacrifice 1 of your Pokemon (+ attached) to LZ; heal 2 others fully.

    Self-LZ feeder with stabilization payoff. Target fingerprint S=2 D=2 Z=3
    A=0 Y=3 = 10 (spicy).
    """
    player_id = event.payload.get('player')
    if not player_id:
        return []
    # Pick a sacrifice target — heuristic: a Bench Pokemon with no attached
    # energy, lowest damage_counters (least invested).
    sacrifice_id = pkm_choose_pokemon_target(
        state, controller=player_id, prefer_active=False,
        filter_fn=lambda obj, st: not getattr(obj.state, 'attached_energy', []),
    )
    if sacrifice_id is None:
        # Fall back to any Pokemon in play.
        sacrifice_id = pkm_choose_pokemon_target(
            state, controller=player_id, prefer_active=False,
        )
    events: list[Event] = []
    if sacrifice_id is not None:
        sacrifice = state.objects.get(sacrifice_id)
        if sacrifice:
            # Move attached energy to LZ first.
            for eid in list(getattr(sacrifice.state, 'attached_energy', []) or []):
                events.extend(pkm_move_to_lost_zone(eid, state, source='Sanguine Sacrament'))
            events.extend(pkm_move_to_lost_zone(
                sacrifice_id, state, source='Sanguine Sacrament',
            ))
    # Heal up to 2 of remaining Pokemon (full heal each).
    healed = 0
    for zone_key in (f"active_spot_{player_id}", f"bench_{player_id}"):
        zone = state.zones.get(zone_key)
        if not zone:
            continue
        for oid in zone.objects:
            if not oid or oid == sacrifice_id:
                continue
            obj = state.objects.get(oid)
            if not obj:
                continue
            old_dmg = getattr(obj.state, 'damage_counters', 0) or 0
            if old_dmg > 0 and healed < 2:
                obj.state.damage_counters = 0
                events.append(Event(
                    type=EventType.PKM_HEAL,
                    payload={'pokemon_id': oid, 'amount': old_dmg * 10,
                             'source': 'Sanguine Sacrament'},
                    source='Sanguine Sacrament',
                ))
                healed += 1
    return events


SANGUINE_SACRAMENT = make_trainer_supporter(
    name="Sanguine Sacrament",
    text=("Put 1 of your Pokemon and all cards attached to it into the Lost "
          "Zone. Then, heal all damage from up to 2 of your remaining Pokemon."),
    rarity="rare",
    resolve=_sanguine_sacrament_effect,
)


BEYOND_RAVNICA_ORZHOV = {
    "Teyslet": TEYSLET,
    "Teyserin": TEYSERIN,
    "Teysa Karlov ex": TEYSA_KARLOV_EX,
    "Karlov of the Ghost Council": KARLOV_OF_THE_GHOST_COUNCIL,
    "Tithe Drinker": TITHE_DRINKER,
    "Orzhova, the Church of Deals": ORZHOVA_THE_CHURCH_OF_DEALS,
    "Kaya, Ghost Assassin": KAYA_GHOST_ASSASSIN,
    "Orzhov Cluestone": ORZHOV_CLUESTONE,
    "Obzlet": OBZLET,
    "Obzedat, Ghost Council": OBZEDAT_GHOST_COUNCIL,
    "Vizkopa Guildmage": VIZKOPA_GUILDMAGE,
    "Cartel Aristocrat": CARTEL_ARISTOCRAT,
    "Treasury Thrull": TREASURY_THRULL,
    "Knight of Obligation": KNIGHT_OF_OBLIGATION,
    "Orzhov Blend Energy": ORZHOV_BLEND_ENERGY,
    # Spice pack v1
    "Obzedat, Ghost Council ex": OBZEDAT_GHOST_COUNCIL_EX,
    "Sanguine Sacrament": SANGUINE_SACRAMENT,
}


def make_orzhov_deck() -> list:
    """60-card Orzhov deck (spice pack v1: Obzedat ex, Sanguine Sacrament)."""
    from src.cards.pokemon.sv_starter import FIGHTING_ENERGY, DARKNESS_ENERGY
    from src.cards.pokemon.beyond.ravnica._deck_helpers import standard_trainer_suite
    deck = []
    # Pokemon (16: +2 Obzedat ex, -2 from OBZLET/non-ex Obzedat)
    deck.extend([TEYSLET] * 4)
    deck.extend([TEYSERIN] * 3)
    deck.extend([TEYSA_KARLOV_EX] * 2)
    deck.extend([OBZLET] * 2)
    deck.extend([OBZEDAT_GHOST_COUNCIL] * 1)
    deck.extend([OBZEDAT_GHOST_COUNCIL_EX] * 2)
    deck.extend([KARLOV_OF_THE_GHOST_COUNCIL] * 2)
    # Guild trainers (10: +2 Sanguine Sacrament, -1 Cluestone)
    deck.extend([ORZHOVA_THE_CHURCH_OF_DEALS] * 2)
    deck.extend([KAYA_GHOST_ASSASSIN] * 2)
    deck.extend([ORZHOV_CLUESTONE] * 2)
    deck.extend([ORZHOV_BLEND_ENERGY] * 2)
    deck.extend([SANGUINE_SACRAMENT] * 2)
    # Standard sv_starter trainer suite (21 — trimmed 1)
    deck.extend(standard_trainer_suite()[:-1])
    # Energy (13)
    deck.extend([FIGHTING_ENERGY] * 8)
    deck.extend([DARKNESS_ENERGY] * 5)
    return deck
