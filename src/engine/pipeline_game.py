"""Pipeline-the-Game v0.2 — engine + game manager.

HD-CRIT-002 §06 / §08 step 11. The four-stage interceptor pipeline that
already runs every Hyperdraft match becomes the playable game itself: two
players slot interceptor cards into TRANSFORM / PREVENT / RESOLVE / REACT
columns each turn, the engine resolves the trick, first-to-six wins.

The pitch's load-bearing claim is *"the engine you already shipped resolves
the trick."* Concretely:

1. Each trick has an Event from `event_deck` (a real `Event` instance with
   a real `EventType`).
2. Players slot one card per turn. The card's `stage` (TRANSFORM / PREVENT /
   REACT) becomes its `InterceptorPriority` and is registered on an
   ephemeral `Game` instance.
3. RESOLVE-stage cards are *not* interceptors — they are the spells being
   cast for the trick. Their `effect_fn` is called directly to produce
   events that `game.emit()` runs through the pipeline.
4. After all RESOLVE events are pumped through, the manager observes life
   deltas + emitted-event vocabulary on the ephemeral state and awards the
   trick to whichever player's effects dominated.

The implementation deliberately keeps the ephemeral state minimal (two
`Player` objects, no battlefield, no library). That's enough to surface
DAMAGE, LIFE_CHANGE, DRAW, and a few other canonical events — the trick
heuristic doesn't need a full board to determine a winner. When v0.3 lands
real interceptor effect bodies (instead of the simplified ones in
`pipeline_deck.py`), the same wiring will support richer state.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

from .game import Game
from .types import (
    Event,
    EventType,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    Player,
)

# ───────────────────────── Vocabulary ───────────────────────────────────

PipelineStage = Literal["TRANSFORM", "PREVENT", "RESOLVE", "REACT"]
PipelineEngine = Literal[
    "MTG", "HS", "PKM", "YGO", "MNR", "FIN", "DPT", "SCP"
]

STAGE_TO_PRIORITY: dict[str, InterceptorPriority] = {
    "TRANSFORM": InterceptorPriority.TRANSFORM,
    "PREVENT": InterceptorPriority.PREVENT,
    "REACT": InterceptorPriority.REACT,
    # RESOLVE has no entry — RESOLVE cards are not interceptors. They are
    # the spell being cast on this trick.
}

# Effect functions take (triggering_event, controller_id, opponent_id) and
# return the events they emit. The manager closes over opponent_id when
# binding interceptors so deck definitions don't need to know about it.
EffectFn = Callable[[Event, str, str], list[Event]]


# ───────────────────────── Card + state models ──────────────────────────


@dataclass
class InterceptorDef:
    """A single playable interceptor in Pipeline-the-Game.

    For v0.2, `effect_fn` is a simplified handler that emits canonical
    payload events (DAMAGE / LIFE_CHANGE / DRAW / ...) directly. The real
    `effect_fn` bodies for cards in `src/cards/` expect a full battlefield
    and are deferred — see TODOs on each entry in `pipeline_deck.py`.
    """

    id: str
    engine: str
    stage: str
    cost: int
    name: str
    text: str
    art: str  # 'tri' | 'bar' | 'square' | 'circle' | 'grid'
    effect_fn: EffectFn


# A 4-stage slot map: each stage column holds at most one card per trick.
SlotMap = dict[str, Optional[InterceptorDef]]


def empty_slots() -> SlotMap:
    return {"TRANSFORM": None, "PREVENT": None, "RESOLVE": None, "REACT": None}


@dataclass
class TrickImpact:
    """Observable result of a single trick for one player."""

    damage_dealt: int = 0
    life_gained: int = 0
    cards_drawn: int = 0
    cards_destroyed: int = 0
    prevented: int = 0

    @property
    def total(self) -> int:
        return (
            self.damage_dealt
            + self.life_gained
            + self.cards_drawn
            + self.cards_destroyed
            + self.prevented
        )


@dataclass
class TrickResult:
    """Outcome of resolving a single trick."""

    winner: Optional[str]  # player_id, or None if tied / both forfeited
    a_impact: TrickImpact
    b_impact: TrickImpact
    events_emitted: list[Event] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


@dataclass
class PipelineGameState:
    """Server-authoritative state for one Pipeline-the-Game match."""

    match_id: str
    player_a_id: str
    player_b_id: str
    decks: dict[str, list[InterceptorDef]] = field(default_factory=dict)
    hands: dict[str, list[InterceptorDef]] = field(default_factory=dict)
    slots: dict[str, SlotMap] = field(default_factory=dict)
    event_deck: list[Event] = field(default_factory=list)
    event_idx: int = 0
    tricks: dict[str, int] = field(default_factory=dict)
    phase: Literal["slot", "resolving", "won"] = "slot"
    winner: Optional[str] = None
    last_trick: Optional[TrickResult] = None
    turn: int = 0
    rng_seed: int = 0

    def current_event(self) -> Event:
        return self.event_deck[self.event_idx % len(self.event_deck)]


# ───────────────────────── Game manager ─────────────────────────────────


WIN_TRICKS = 6
HAND_SIZE = 8


class PipelineGameManager:
    """One Pipeline-the-Game match. Runs the real engine on each trick."""

    def __init__(
        self,
        match_id: str,
        player_a_id: str,
        player_b_id: str,
        deck_a: list[InterceptorDef],
        deck_b: list[InterceptorDef],
        event_deck: list[Event],
        rng_seed: int = 0,
    ):
        self.state = PipelineGameState(
            match_id=match_id,
            player_a_id=player_a_id,
            player_b_id=player_b_id,
            decks={
                player_a_id: list(deck_a),
                player_b_id: list(deck_b),
            },
            hands={player_a_id: [], player_b_id: []},
            slots={
                player_a_id: empty_slots(),
                player_b_id: empty_slots(),
            },
            event_deck=list(event_deck),
            tricks={player_a_id: 0, player_b_id: 0},
            rng_seed=rng_seed,
        )
        self._rng = random.Random(rng_seed)
        self._setup()

    # ── setup ─────────────────────────────────────────────────────────

    def _setup(self) -> None:
        """Shuffle decks, draw opening hands."""
        for pid, deck in self.state.decks.items():
            self._rng.shuffle(deck)
            draw = min(HAND_SIZE, len(deck))
            self.state.hands[pid] = [deck.pop() for _ in range(draw)]

    # ── public API ────────────────────────────────────────────────────

    def play_card(self, player_id: str, card_id: str) -> dict:
        if self.state.phase != "slot":
            raise ValueError(f"cannot play in phase {self.state.phase!r}")
        hand = self.state.hands[player_id]
        card = next((c for c in hand if c.id == card_id), None)
        if card is None:
            raise ValueError(f"card {card_id!r} not in {player_id}'s hand")
        slots = self.state.slots[player_id]
        if slots.get(card.stage) is not None:
            raise ValueError(
                f"{player_id} already played a {card.stage} card this trick"
            )
        slots[card.stage] = card
        hand.remove(card)
        return self.snapshot()

    def both_played(self) -> bool:
        a = self.state.slots[self.state.player_a_id]
        b = self.state.slots[self.state.player_b_id]
        return any(a.values()) and any(b.values())

    def resolve_trick(self) -> TrickResult:
        """Run the engine pipeline with both players' interceptors registered."""
        if self.state.phase != "slot":
            raise ValueError(f"cannot resolve in phase {self.state.phase!r}")
        self.state.phase = "resolving"

        # Build an ephemeral Game. Game.add_player assigns its own engine
        # player IDs, so we map our (player_a_id, player_b_id) labels to
        # them and translate at handler / effect-fn boundaries.
        game = Game(mode="mtg")
        eng_a = game.add_player("A", life=20)
        eng_b = game.add_player("B", life=20)
        eng_id: dict[str, str] = {
            self.state.player_a_id: eng_a.id,
            self.state.player_b_id: eng_b.id,
        }

        # Register TRANSFORM / PREVENT / REACT cards as interceptors.
        for pid in (self.state.player_a_id, self.state.player_b_id):
            opp_id = self._opponent_of(pid)
            for stage in ("TRANSFORM", "PREVENT", "REACT"):
                card = self.state.slots[pid][stage]
                if card is None:
                    continue
                game.register_interceptor(
                    self._make_interceptor(card, eng_id[pid], eng_id[opp_id])
                )

        log: list[str] = []
        all_events: list[Event] = []
        triggering_event = self.state.current_event()
        log.append(f"event drops: {triggering_event.type.name}")

        # RESOLVE cards: the spells being cast this trick.
        for pid in (self.state.player_a_id, self.state.player_b_id):
            card = self.state.slots[pid]["RESOLVE"]
            if card is None:
                continue
            opp_id = self._opponent_of(pid)
            log.append(f"{pid}: casts {card.name}")
            for ev in card.effect_fn(triggering_event, eng_id[pid], eng_id[opp_id]):
                resolved = game.emit(ev)
                all_events.append(ev)
                all_events.extend(resolved)

        a_impact = self._compute_impact(
            game.state,
            all_events,
            self.state.player_a_id,
            eng_id[self.state.player_a_id],
            eng_id[self.state.player_b_id],
        )
        b_impact = self._compute_impact(
            game.state,
            all_events,
            self.state.player_b_id,
            eng_id[self.state.player_b_id],
            eng_id[self.state.player_a_id],
        )

        winner = self._determine_winner(a_impact, b_impact, log)
        if winner is not None:
            self.state.tricks[winner] += 1

        result = TrickResult(
            winner=winner,
            a_impact=a_impact,
            b_impact=b_impact,
            events_emitted=all_events,
            log=log,
        )
        self.state.last_trick = result

        if self.state.tricks[self.state.player_a_id] >= WIN_TRICKS:
            self.state.phase = "won"
            self.state.winner = self.state.player_a_id
        elif self.state.tricks[self.state.player_b_id] >= WIN_TRICKS:
            self.state.phase = "won"
            self.state.winner = self.state.player_b_id
        else:
            self._advance_turn()

        return result

    def is_won(self) -> Optional[str]:
        return self.state.winner

    def snapshot(self) -> dict:
        """Serializable view of the game state for the frontend."""
        return {
            "match_id": self.state.match_id,
            "player_a_id": self.state.player_a_id,
            "player_b_id": self.state.player_b_id,
            "hands": {
                pid: [_card_to_dict(c) for c in self.state.hands[pid]]
                for pid in (self.state.player_a_id, self.state.player_b_id)
            },
            "slots": {
                pid: {
                    stage: (_card_to_dict(c) if c else None)
                    for stage, c in slots.items()
                }
                for pid, slots in self.state.slots.items()
            },
            "current_event": _event_to_dict(self.state.current_event()),
            "event_idx": self.state.event_idx,
            "turn": self.state.turn,
            "tricks": dict(self.state.tricks),
            "phase": self.state.phase,
            "winner": self.state.winner,
            "last_trick": (
                None
                if self.state.last_trick is None
                else {
                    "winner": self.state.last_trick.winner,
                    "a_impact": _impact_to_dict(self.state.last_trick.a_impact),
                    "b_impact": _impact_to_dict(self.state.last_trick.b_impact),
                    "log": list(self.state.last_trick.log),
                }
            ),
            "deck_count": {
                pid: len(self.state.decks[pid])
                for pid in (self.state.player_a_id, self.state.player_b_id)
            },
        }

    # ── internals ─────────────────────────────────────────────────────

    def _opponent_of(self, pid: str) -> str:
        return (
            self.state.player_b_id
            if pid == self.state.player_a_id
            else self.state.player_a_id
        )

    def _make_interceptor(
        self, card: InterceptorDef, controller: str, opponent: str
    ) -> Interceptor:
        priority = STAGE_TO_PRIORITY[card.stage]
        # PREVENT cards with empty effect_fn output cancel the event;
        # otherwise the result rides as new_events.
        is_prevent = card.stage == "PREVENT"

        def filter_fn(ev: Event, st: GameState) -> bool:
            # Match any event with the same type as the triggering event,
            # which is the simplest filter that surfaces real cross-engine
            # interaction in v0.2.
            return ev.type == self.state.current_event().type

        def handler(ev: Event, st: GameState) -> InterceptorResult:
            emitted = card.effect_fn(ev, controller, opponent)
            if is_prevent and not emitted:
                return InterceptorResult(action=InterceptorAction.PREVENT)
            return InterceptorResult(
                action=InterceptorAction.REACT, new_events=emitted
            )

        return Interceptor(
            id=f"pipeline-{controller}-{card.id}",
            source=controller,
            controller=controller,
            priority=priority,
            filter=filter_fn,
            handler=handler,
        )

    def _compute_impact(
        self,
        gs: GameState,
        events: list[Event],
        slot_pid: str,
        eng_pid: str,
        eng_opp_id: str,
    ) -> TrickImpact:
        """Score one player's contribution. `slot_pid` is the manager-side
        label used to look up slotted cards; `eng_pid` / `eng_opp_id` are
        the engine-assigned player IDs used to read life totals on the
        ephemeral GameState."""
        impact = TrickImpact()
        you = gs.players[eng_pid]
        opp = gs.players[eng_opp_id]
        impact.damage_dealt = max(0, 20 - opp.life)
        impact.life_gained = max(0, you.life - 20)
        for ev in events:
            if ev.controller != eng_pid:
                continue
            if ev.type == EventType.DRAW:
                impact.cards_drawn += int(ev.payload.get("count", 1))
            elif ev.type == EventType.OBJECT_DESTROYED:
                impact.cards_destroyed += 1
        # PREVENT credit: if you had PREVENT and opponent had RESOLVE but
        # they failed to do net damage, you get credit equal to opponent's
        # RESOLVE cost.
        slot_opp = self._opponent_of(slot_pid)
        prevent_card = self.state.slots[slot_pid]["PREVENT"]
        opp_resolve = self.state.slots[slot_opp]["RESOLVE"]
        if prevent_card and opp_resolve and you.life == 20:
            impact.prevented = opp_resolve.cost
        return impact

    def _determine_winner(
        self,
        a_impact: TrickImpact,
        b_impact: TrickImpact,
        log: list[str],
    ) -> Optional[str]:
        a_resolve = self.state.slots[self.state.player_a_id]["RESOLVE"]
        b_resolve = self.state.slots[self.state.player_b_id]["RESOLVE"]

        if a_resolve is None and b_resolve is None:
            log.append("neither player slotted RESOLVE — trick discarded")
            return None
        if a_resolve and not b_resolve:
            log.append(f"{self.state.player_a_id} wins (only RESOLVE)")
            return self.state.player_a_id
        if b_resolve and not a_resolve:
            log.append(f"{self.state.player_b_id} wins (only RESOLVE)")
            return self.state.player_b_id
        # Both resolved — compare impact, then cost.
        if a_impact.total > b_impact.total:
            log.append(
                f"{self.state.player_a_id} wins on impact {a_impact.total}>{b_impact.total}"
            )
            return self.state.player_a_id
        if b_impact.total > a_impact.total:
            log.append(
                f"{self.state.player_b_id} wins on impact {b_impact.total}>{a_impact.total}"
            )
            return self.state.player_b_id
        if a_resolve.cost > b_resolve.cost:
            log.append(f"{self.state.player_a_id} wins on cost tiebreak")
            return self.state.player_a_id
        if b_resolve.cost > a_resolve.cost:
            log.append(f"{self.state.player_b_id} wins on cost tiebreak")
            return self.state.player_b_id
        log.append("dead heat — trick discarded")
        return None

    def _advance_turn(self) -> None:
        """Refill hands, clear slots, advance to the next event."""
        self.state.phase = "slot"
        self.state.turn += 1
        self.state.event_idx = (self.state.event_idx + 1) % len(
            self.state.event_deck
        )
        self.state.slots = {
            self.state.player_a_id: empty_slots(),
            self.state.player_b_id: empty_slots(),
        }
        for pid in (self.state.player_a_id, self.state.player_b_id):
            deck = self.state.decks[pid]
            hand = self.state.hands[pid]
            if deck and len(hand) < HAND_SIZE:
                hand.append(deck.pop())


# ───────────────────────── Serialization helpers ────────────────────────


def _card_to_dict(c: InterceptorDef) -> dict:
    return {
        "id": c.id,
        "engine": c.engine,
        "stage": c.stage,
        "cost": c.cost,
        "name": c.name,
        "text": c.text,
        "art": c.art,
    }


def _event_to_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "type": e.type.name,
        "payload": dict(e.payload),
    }


def _impact_to_dict(i: TrickImpact) -> dict:
    return {
        "damage_dealt": i.damage_dealt,
        "life_gained": i.life_gained,
        "cards_drawn": i.cards_drawn,
        "cards_destroyed": i.cards_destroyed,
        "prevented": i.prevented,
        "total": i.total,
    }
