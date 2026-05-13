"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

Azorius guild (W+U in MTG → Fighting+Water in Pokemon types — using Fighting
as a white substitute since Fairy energy doesn't exist in this engine).

Theme: lawful judges, sphinxes, control, counterspells, detention. Cute
diminutive names for pre-evolutions; the final stage keeps its MTG canon
title (Isperia, Supreme Judge ex).
"""

import random

from src.engine.game import (
    make_pokemon, make_trainer_item, make_trainer_supporter,
    make_trainer_stadium, make_pokemon_tool,
)
from src.engine.types import (
    PokemonType, Event, EventType, ZoneType, CardType, Interceptor,
    InterceptorPriority, InterceptorAction, InterceptorResult, new_id,
)

# Spice-pack v1 imports — see docs/sets/pkm_brv_spice_designs.md
from src.cards.pokemon._helpers import (
    pkm_force_opp_choose_bench,
    pkm_force_switch_opp,
    pkm_move_energy,
    pkm_reveal_opp_hand,
    pkm_target_card_in_hand_choice,
    discard_attached_energy_cross_ctrl,
    _get_opp_id,
    _get_opp_active,
)
from src.cards.pokemon._tool_helpers import make_tool_setup


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
# Isperia evolution line — Azorius sphinx-judge
# =============================================================================

def _hatchling_riddle_effect(attacker, state):
    # Tiny scribble — nothing fancy
    return []


def _decree_stamp_effect(attacker, state):
    # Clerk-sphinx is too busy stamping to do anything but hit
    return []


def _supreme_judgment_swap(opp_id: str, target_id: str, state) -> list[Event]:
    """Drag-out the chosen opponent bench Pokemon. Preserves the original
    PKM_SWITCH payload shape so downstream tests/log readers don't drift.
    """
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    bench_zone = state.zones.get(f"bench_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    if not bench_zone or target_id not in bench_zone.objects:
        return []
    old_active_id = active_zone.objects[0]
    active_zone.objects[0] = target_id
    bench_zone.objects.remove(target_id)
    bench_zone.objects.append(old_active_id)
    old_active = state.objects.get(old_active_id)
    new_active = state.objects.get(target_id)
    if old_active:
        old_active.zone = ZoneType.BENCH
    if new_active:
        new_active.zone = ZoneType.ACTIVE_SPOT
    return [Event(
        type=EventType.PKM_SWITCH,
        payload={'player': opp_id, 'old_active': old_active_id, 'new_active': target_id},
    )]


def _supreme_judgment_effect(attacker, state):
    """Switch the opponent's Active with a chosen Pokemon on their bench.

    Phase 4 migration: the attacker's controller now makes a real target
    choice over the opponent's bench (the old code auto-picked the
    lowest-current-HP Pokemon). For AI controllers, the heuristic is
    preserved via ``heuristic_pick``, so existing AI behavior doesn't
    change. Humans get a meaningful pick — sometimes the right call is to
    drag out a fully-healthy attacker whose attack is mid-charged, not the
    weakest body.
    """
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    bench_zone = state.zones.get(f"bench_{opp_id}")
    if not active_zone or not active_zone.objects:
        return []
    if not bench_zone or not bench_zone.objects:
        return []

    from src.engine.pending_choice_helpers import create_choice_and_resolve

    options: list[dict] = []
    best_id: str | None = None
    best_hp = 10 ** 9
    for pkm_id in bench_zone.objects:
        pkm = state.objects.get(pkm_id)
        if not pkm or not pkm.card_def:
            continue
        max_hp = pkm.card_def.hp or 0
        current_hp = max_hp - (pkm.state.damage_counters * 10)
        ptype = pkm.card_def.pokemon_type or '?'
        options.append({
            "id": pkm_id,
            "label": pkm.name or pkm.card_def.name or pkm_id,
            "description": f"HP {current_hp}/{max_hp} · Type {ptype}",
        })
        if current_hp < best_hp:
            best_hp = current_hp
            best_id = pkm_id
    if not options:
        return []
    if best_id is None:
        best_id = options[0]["id"]

    def _resolve_handler(choice, selected, st):
        target_id = selected[0] if selected else best_id
        if isinstance(target_id, dict):
            target_id = target_id.get("id", best_id)
        return _supreme_judgment_swap(opp_id, target_id, st)

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=attacker.controller,
        prompt="Drag which of your opponent's benched Pokemon out to Active?",
        options=options,
        source_id=attacker.id,
        min_choices=1,
        max_choices=1,
        handler=_resolve_handler,
        heuristic_pick=[best_id],
    )


ISPERILET = make_pokemon(
    name="Isperilet",
    hp=60,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Hatchling Riddle",
         "cost": [{"type": "W", "count": 1}],
         "damage": 10,
         "text": "",
         "effect_fn": _hatchling_riddle_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    text=("A baby sphinx, talons curled around oversized law-book glasses. "
          "Already issuing tiny stays-of-execution to its own bedtime."),
    rarity="common",
)

ISPERATRA = make_pokemon(
    name="Isperatra",
    hp=90,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Stage 1",
    evolves_from="Isperilet",
    attacks=[
        {"name": "Decree Stamp",
         "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": "",
         "effect_fn": _decree_stamp_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    text=("A clerk-sphinx in spectacles. Stamps decree scrolls so fast "
          "the wax never has time to dry properly between filings."),
    rarity="uncommon",
)

ISPERIA_SUPREME_JUDGE_EX = make_pokemon(
    name="Isperia, Supreme Judge ex",
    hp=280,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Stage 2",
    evolves_from="Isperatra",
    attacks=[
        {"name": "Writ of Detention",
         "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}],
         "damage": 60,
         "text": "",
         "effect_fn": _decree_stamp_effect},
        {"name": "Supreme Judgment",
         "cost": [{"type": "W", "count": 2}, {"type": "F", "count": 2}],
         "damage": 180,
         "text": ("Switch your opponent's Active Pokemon with one of their "
                  "Benched Pokemon."),
         "effect_fn": _supreme_judgment_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=2,
    is_ex=True,
    text="The riddler-judge of Ravnica. Her gavel is the verdict.",
    rarity="rare",
)


# =============================================================================
# Stand-alone Basic Pokemon
# =============================================================================

def _trainer_mill_effect(attacker, state):
    """Mill the top card of opponent's deck. If it's a Trainer, no extra effect
    (the milling itself is the punishment — Lavinia hates ad-hoc paperwork)."""
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    library = state.zones.get(f"library_{opp_id}")
    grave = state.zones.get(f"graveyard_{opp_id}")
    if not library or not library.objects:
        return []
    top_id = library.objects[0]
    top_obj = state.objects.get(top_id)
    is_trainer = (
        top_obj
        and top_obj.characteristics
        and CardType.TRAINER in top_obj.characteristics.types
    )
    if not is_trainer:
        return []
    library.objects.pop(0)
    if grave:
        grave.objects.append(top_id)
    if top_obj:
        top_obj.zone = ZoneType.GRAVEYARD
    return []


LAVINIA_OF_THE_TENTH = make_pokemon(
    name="Lavinia of the Tenth",
    hp=80,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Cite the Code",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50,
         "text": ("Look at the top card of your opponent's deck. "
                  "If it is a Trainer, discard it."),
         "effect_fn": _trainer_mill_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    text=("A by-the-book lawmage who carries her own footnotes. "
          "Has cited every Trainer in Ravnica at least once."),
    rarity="uncommon",
)


def _aetherling_blink_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


AETHERLING = make_pokemon(
    name="Aetherling",
    hp=70,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Phase Blink",
         "cost": [{"type": "W", "count": 1}],
         "damage": 20,
         "text": "Draw a card.",
         "effect_fn": _aetherling_blink_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    text=("A shimmering puddle that has read its own future and politely "
          "declined most of it. Slips between pages of bound legalese."),
    rarity="common",
)


# =============================================================================
# Trainer cards
# =============================================================================

def _prahv_spires_effect(event, state):
    """Each player reveals their hand to themselves (flavor — engine no-op).
    Then your opponent shuffles their hand into their deck and draws 4."""
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
    # Shuffle hand into deck
    for card_id in list(hand.objects):
        hand.objects.remove(card_id)
        library.objects.append(card_id)
        obj = state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.LIBRARY
    random.shuffle(library.objects)
    # Draw 4
    return _draw_cards(state, opp_id, 4)


PRAHV_SPIRES_OF_ORDER = make_trainer_stadium(
    name="Prahv, Spires of Order",
    text=("When you play Prahv, Spires of Order, each player reveals their "
          "hand. Then your opponent shuffles their hand into their deck "
          "and draws 4 cards."),
    rarity="uncommon",
    resolve=_prahv_spires_effect,
)


def _teferi_draw_effect(event, state):
    """Bottom a card first, then draw; Trainer tempo also heals the Active."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    events = []
    hand = state.zones.get(f"hand_{player_id}")
    library = state.zones.get(f"library_{player_id}")
    moved_trainer = False
    if hand and library and hand.objects:
        card_id = hand.objects.pop(0)
        library.objects.append(card_id)
        obj = state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.LIBRARY
            moved_trainer = (
                obj.characteristics
                and CardType.TRAINER in obj.characteristics.types
            )
        events.append(Event(
            type=EventType.PKM_DISCARD_ENERGY,
            payload={'player': player_id, 'card_id': card_id,
                     'source': 'Teferi, Hero of Dominaria'},
        ))
    if moved_trainer:
        active_zone = state.zones.get(f"active_spot_{player_id}")
        if active_zone and active_zone.objects:
            active = state.objects.get(active_zone.objects[0])
            if active and active.state.damage_counters > 0:
                healed = min(2, active.state.damage_counters)
                active.state.damage_counters -= healed
                events.append(Event(
                    type=EventType.PKM_HEAL,
                    payload={'pokemon_id': active.id, 'amount': healed * 10,
                             'source': 'Teferi, Hero of Dominaria'},
                ))
    events.extend(_draw_cards(state, player_id, 3))
    return events


TEFERI_HERO_OF_DOMINARIA = make_trainer_supporter(
    name="Teferi, Hero of Dominaria",
    text=("Put a card from your hand on the bottom of your deck. Draw 3 cards. "
          "If you put a Trainer card on the bottom this way, heal 20 damage "
          "from your Active Pokemon."),
    rarity="rare",
    resolve=_teferi_draw_effect,
)


def _azorius_cluestone_effect(event, state):
    """Search deck for one Water Energy and one Fighting Energy, put them in
    your hand. Then shuffle your deck."""
    player_id = event.payload.get('player')
    if not player_id:
        return []
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    found_water = None
    found_fighting = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.WATER.value and not found_water:
            found_water = card_id
        elif ptype == PokemonType.FIGHTING.value and not found_fighting:
            found_fighting = card_id
        if found_water and found_fighting:
            break
    moved = []
    for cid in (found_water, found_fighting):
        if cid:
            library.objects.remove(cid)
            hand.objects.append(cid)
            obj = state.objects.get(cid)
            if obj:
                obj.zone = ZoneType.HAND
            moved.append(cid)
    random.shuffle(library.objects)
    return []


AZORIUS_CLUESTONE = make_trainer_item(
    name="Azorius Cluestone",
    text=("Search your deck for a Water Energy and a Fighting Energy, "
          "reveal them, and put them into your hand. Then, shuffle your deck."),
    rarity="uncommon",
    resolve=_azorius_cluestone_effect,
)


# =============================================================================
# Tomik evolution line — Azorius advokist
# =============================================================================

def _legal_injunction_effect(attacker, state):
    """Mill opponent's top card if it's a Trainer."""
    opp_id = next((p for p in state.players if p != attacker.controller), None)
    if not opp_id:
        return []
    library = state.zones.get(f"library_{opp_id}")
    grave = state.zones.get(f"graveyard_{opp_id}")
    if not library or not library.objects:
        return []
    top_id = library.objects[0]
    top_obj = state.objects.get(top_id)
    is_trainer = (
        top_obj
        and top_obj.characteristics
        and CardType.TRAINER in top_obj.characteristics.types
    )
    if not is_trainer:
        return []
    library.objects.pop(0)
    if grave:
        grave.objects.append(top_id)
    if top_obj:
        top_obj.zone = ZoneType.GRAVEYARD
    return []


def _stamp_stamp_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


TOMLET = make_pokemon(
    name="Tomlet",
    hp=70,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Stamp Stamp",
         "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": "Draw a card.",
         "effect_fn": _stamp_stamp_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    text=("A pint-sized clerk-sphinx with an ink-stained beak. "
          "Carries a stamp twice its size and uses it on everything."),
    rarity="common",
)


TOMIK_DISTINGUISHED_ADVOKIST = make_pokemon(
    name="Tomik, Distinguished Advokist",
    hp=120,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Stage 1",
    evolves_from="Tomlet",
    attacks=[
        {"name": "Legal Injunction",
         "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}],
         "damage": 80,
         "text": ("Look at the top card of your opponent's deck. "
                  "If it is a Trainer, discard it."),
         "effect_fn": _legal_injunction_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    text=("Files cease-and-desist notices on rival mages mid-incantation. "
          "Tomik never loses an appeal — he writes the precedent first."),
    rarity="rare",
)


# =============================================================================
# More stand-alone Basic Pokemon
# =============================================================================

def _sphinx_oracle_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


SPHINX_OF_MAGOSI = make_pokemon(
    name="Sphinx of Magosi",
    hp=80,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Oracle's Gaze",
         "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}],
         "damage": 40,
         "text": "Draw a card.",
         "effect_fn": _sphinx_oracle_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=2,
    text=("A scholar-sphinx that once memorized the Magosi library "
          "in an afternoon and complained the books were too short."),
    rarity="uncommon",
)


def _augury_owl_effect(attacker, state):
    return _draw_cards(state, attacker.controller, 1)


AUGURY_OWL = make_pokemon(
    name="Augury Owl",
    hp=70,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Foresight",
         "cost": [{"type": "W", "count": 1}],
         "damage": 20,
         "text": "Draw a card.",
         "effect_fn": _augury_owl_effect},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    text=("Hoots the next-day weather a few hours ahead of schedule. "
          "Reliably correct, except about umbrellas."),
    rarity="common",
)


def _soulsworn_jury_effect(attacker, state):
    """Place 1 damage counter on opponent's Active."""
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
        payload={'pokemon_id': target_id, 'counters': 1, 'source': 'Soulsworn Jury'},
    )]


SOULSWORN_JURY = make_pokemon(
    name="Soulsworn Jury",
    hp=90,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Verdict Strike",
         "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 70,
         "text": "Place 1 damage counter on the opponent's Active Pokemon.",
         "effect_fn": _soulsworn_jury_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=2,
    text=("Twelve oath-bound spirits speak as one. The verdict is "
          "always unanimous, and always slightly unsettling."),
    rarity="uncommon",
)


def _gate_tax_effect(attacker, state):
    """Chip the opposing Active and detain it if it has no Energy attached."""
    from src.engine.pokemon_status import apply_status

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
    events = [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target_id, 'counters': 1, 'source': 'Gate Tax'},
    )]
    if not target.state.attached_energy:
        events.extend(apply_status(target_id, 'paralyzed', state))
    return events


DOORKEEPER = make_pokemon(
    name="Doorkeeper",
    hp=60,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Gate Tax",
         "cost": [{"type": "F", "count": 1}],
         "damage": 20,
         "text": ("Place 1 damage counter on your opponent's Active Pokemon. "
                  "If it has no Energy attached, it is now Paralyzed."),
         "effect_fn": _gate_tax_effect},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=2,
    text=("Stands in doorways. Has stood in this particular doorway "
          "for forty years. The doorway remembers."),
    rarity="common",
)


# =============================================================================
# Special trainer — Azorius Blend Energy (item that attaches directly)
# =============================================================================

def _azorius_blend_energy_effect(event, state):
    """Search deck for one Water Energy AND one Fighting Energy, attach BOTH
    directly to the active Pokemon. Shuffle deck."""
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
    found_water = None
    found_fighting = None
    for card_id in library.objects:
        obj = state.objects.get(card_id)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        ptype = getattr(obj.card_def, 'pokemon_type', None) if obj.card_def else None
        if ptype == PokemonType.WATER.value and not found_water:
            found_water = card_id
        elif ptype == PokemonType.FIGHTING.value and not found_fighting:
            found_fighting = card_id
        if found_water and found_fighting:
            break
    events = []
    for cid in (found_water, found_fighting):
        if cid:
            library.objects.remove(cid)
            active.state.attached_energy.append(cid)
            energy_obj = state.objects.get(cid)
            if energy_obj:
                energy_obj.zone = ZoneType.BATTLEFIELD
            events.append(Event(
                type=EventType.PKM_ATTACH_ENERGY,
                payload={'pokemon_id': active_id, 'energy_id': cid, 'player': player_id},
            ))
    random.shuffle(library.objects)
    return events


AZORIUS_BLEND_ENERGY = make_trainer_item(
    name="Azorius Blend Energy",
    text=("Search your deck for a Water Energy and a Fighting Energy, and "
          "attach both to your Active Pokemon. Then, shuffle your deck."),
    rarity="rare",
    resolve=_azorius_blend_energy_effect,
)


# =============================================================================
# Spice pack v1 — Decision Pressure (Niv-Mizzet's Quandary, Jace) + Tool
# =============================================================================

def _niv_mizzets_quandary_effect(event, state):
    """Forced opp switch (opp chooses) → you redirect up to 2 of their energy.

    Build-around spice — the first BRV card where the opponent is forced into
    a real decision against their interest. Target fingerprint S=2 D=3 Z=2
    A=3 Y=0 = 10 (spicy).
    """
    player_id = event.payload.get('player')
    if not player_id:
        return []
    opp_id = _get_opp_id(player_id, state)
    if not opp_id:
        return []
    # Opp picks the bench Pokemon to bring up — heuristic v1 picks their
    # highest-investment one to maximize the "bad for opp" decision pressure.
    new_active_id = pkm_force_opp_choose_bench(opp_id, state, source='Niv-Mizzet\'s Quandary')
    if not new_active_id:
        return []
    events: list[Event] = list(pkm_force_switch_opp(
        opp_id, state, new_active_id=new_active_id, source='Niv-Mizzet\'s Quandary',
    ))
    # Caster picks up to 2 of opp's energy and moves them to the new Active.
    moved = 0
    for obj in list(state.objects.values()):
        if moved >= 2:
            break
        if obj.controller != opp_id:
            continue
        if obj.id == new_active_id:
            continue
        attached = getattr(getattr(obj, 'state', None), 'attached_energy', None)
        if not attached:
            continue
        # Take one energy from this Pokemon, move to the new Active.
        energy_id = attached[0]
        events.extend(pkm_move_energy(
            energy_id, new_pokemon_id=new_active_id, state=state,
            source='Niv-Mizzet\'s Quandary',
        ))
        moved += 1
    return events


NIV_MIZZETS_QUANDARY = make_trainer_supporter(
    name="Niv-Mizzet's Quandary",
    text=("Your opponent chooses one of their Benched Pokemon and switches it "
          "with their Active. After they switch, you may move up to 2 Energy "
          "from any of their Pokemon to the new Active."),
    rarity="rare",
    resolve=_niv_mizzets_quandary_effect,
)


def _jace_mental_triage_effect(attacker, state):
    """Look at opp hand; pick an Item to discard. Opp draws 1.

    Target fingerprint S=2 D=2 Z=2 A=3 Y=0 = 9 (spicy).
    """
    opp_id = _get_opp_id(attacker.controller, state)
    if not opp_id:
        return []
    events: list[Event] = list(pkm_reveal_opp_hand(opp_id, state, source=attacker.id))
    target_id = pkm_target_card_in_hand_choice(
        state, target_controller=opp_id, card_type_filter=CardType.TRAINER,
    )
    if target_id is not None:
        hand = state.zones[f"hand_{opp_id}"]
        grave = state.zones[f"graveyard_{opp_id}"]
        if target_id in hand.objects:
            hand.objects.remove(target_id)
            grave.objects.append(target_id)
            target = state.objects.get(target_id)
            if target:
                target.zone = ZoneType.GRAVEYARD
            events.append(Event(
                type=EventType.PKM_REVEAL,
                payload={'target_player': opp_id, 'card_id': target_id,
                         'destination': 'graveyard', 'source': attacker.id},
                source=attacker.id,
            ))
    # Opp draws 1.
    library = state.zones.get(f"library_{opp_id}")
    hand = state.zones.get(f"hand_{opp_id}")
    if library and library.objects and hand:
        top = library.objects.pop(0)
        hand.objects.append(top)
        top_obj = state.objects.get(top)
        if top_obj:
            top_obj.zone = ZoneType.HAND
        events.append(Event(type=EventType.DRAW,
                            payload={'player': opp_id, 'count': 1}))
    return events


JACE_MEMORY_ADEPT = make_pokemon(
    name="Jace, Memory Adept",
    hp=80,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Mental Triage",
         "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}],
         "damage": 30,
         "text": "Look at your opponent's hand. Choose 1 Item card and discard it. Your opponent draws 1 card.",
         "effect_fn": _jace_mental_triage_effect},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    retreat_cost=1,
    text=("An academy prodigy who reads minds like books. Has read every "
          "book in Vryn and is mostly bored of them now."),
    rarity="rare",
)


def _pithing_drone_trigger_filter(event, state, tool_obj, holder_id):
    """Fire when the holder Pokemon is KO'd (the attacker is identified
    in the event payload)."""
    kod = event.payload.get('pokemon_id')
    if kod != holder_id:
        return False
    attacker_id = (
        event.payload.get('attacker_id')
        or event.payload.get('source_pokemon_id')
    )
    return bool(attacker_id)


def _pithing_drone_trigger_handler(event, state, tool_obj, holder_id):
    """Discard all energy from the attacker that KO'd the holder."""
    attacker_id = (
        event.payload.get('attacker_id')
        or event.payload.get('source_pokemon_id')
    )
    if not attacker_id:
        return []
    return discard_attached_energy_cross_ctrl(
        state, target_pokemon_id=attacker_id, count=999, source=tool_obj.id,
    )


_pithing_drone_setup = make_tool_setup(
    event_type=EventType.PKM_KNOCKOUT,
    trigger_filter=_pithing_drone_trigger_filter,
    trigger_handler=_pithing_drone_trigger_handler,
)


PITHING_DRONE = make_pokemon_tool(
    name="Pithing Drone",
    text=("Attach to 1 of your Pokemon. When the attached Pokemon is "
          "Knocked Out by an opponent's attack, your opponent discards "
          "all Energy from the attacking Pokemon."),
    rarity="uncommon",
    setup_interceptors=_pithing_drone_setup,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_RAVNICA_AZORIUS = {
    "Isperilet": ISPERILET,
    "Isperatra": ISPERATRA,
    "Isperia, Supreme Judge ex": ISPERIA_SUPREME_JUDGE_EX,
    "Lavinia of the Tenth": LAVINIA_OF_THE_TENTH,
    "Aetherling": AETHERLING,
    "Prahv, Spires of Order": PRAHV_SPIRES_OF_ORDER,
    "Teferi, Hero of Dominaria": TEFERI_HERO_OF_DOMINARIA,
    "Azorius Cluestone": AZORIUS_CLUESTONE,
    "Tomlet": TOMLET,
    "Tomik, Distinguished Advokist": TOMIK_DISTINGUISHED_ADVOKIST,
    "Sphinx of Magosi": SPHINX_OF_MAGOSI,
    "Augury Owl": AUGURY_OWL,
    "Soulsworn Jury": SOULSWORN_JURY,
    "Doorkeeper": DOORKEEPER,
    "Azorius Blend Energy": AZORIUS_BLEND_ENERGY,
    # Spice pack v1
    "Niv-Mizzet's Quandary": NIV_MIZZETS_QUANDARY,
    "Jace, Memory Adept": JACE_MEMORY_ADEPT,
    "Pithing Drone": PITHING_DRONE,
}


def make_azorius_deck() -> list:
    """60-card Azorius deck (spice pack v1: Niv-Mizzet's Quandary, Jace, Pithing Drone)."""
    from src.cards.pokemon.sv_starter import WATER_ENERGY, FIGHTING_ENERGY
    from src.cards.pokemon.beyond.ravnica._deck_helpers import standard_trainer_suite
    deck = []
    # Pokemon (16: +2 Jace, -2 from Isperilet/Tomlet)
    deck.extend([ISPERILET] * 3)
    deck.extend([ISPERATRA] * 3)
    deck.extend([ISPERIA_SUPREME_JUDGE_EX] * 2)
    deck.extend([TOMLET] * 2)
    deck.extend([TOMIK_DISTINGUISHED_ADVOKIST] * 2)
    deck.extend([LAVINIA_OF_THE_TENTH] * 2)
    deck.extend([JACE_MEMORY_ADEPT] * 2)
    # Guild trainers (11: +1 Quandary +2 Pithing Drone, -1 Cluestone)
    deck.extend([PRAHV_SPIRES_OF_ORDER] * 2)
    deck.extend([TEFERI_HERO_OF_DOMINARIA] * 2)
    deck.extend([AZORIUS_CLUESTONE] * 2)
    deck.extend([AZORIUS_BLEND_ENERGY] * 2)
    deck.extend([NIV_MIZZETS_QUANDARY] * 1)
    deck.extend([PITHING_DRONE] * 2)
    # Standard sv_starter trainer suite (20 — trimmed 2)
    deck.extend(standard_trainer_suite()[:-2])
    # Energy (13)
    deck.extend([WATER_ENERGY] * 8)
    deck.extend([FIGHTING_ENERGY] * 5)
    return deck
