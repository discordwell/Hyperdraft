"""
Hyperdraft Priority System

Handles the priority system - who can act and when.
Priority determines which player can take actions at any given moment.

Rules:
- Active player gets priority at the start of most steps/phases
- After casting/activating, that player retains priority (rule 116.3c)
- Players can pass priority
- When all players pass with empty stack, phase/step ends
- When all players pass with stack items, top item resolves
"""

from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING, Any
from enum import Enum, auto
import asyncio
import inspect
import re

from .types import (
    GameState, Event, EventType, CardType, ZoneType, PendingChoice, Color,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id,
)
from .stack import StackManager, StackItem, StackItemType, build_target_chosen_events
from .mana import ManaSystem, ManaCost, ManaType
from .pipeline import EventPipeline
from .cost_query import get_effective_mana_cost
from .cast_permission import (
    is_castable_from_zone as _w7_is_castable_from_zone,
    cost_override_for as _w7_cast_cost_override_for,
)
from .casting_costs import (
    CastCostContext,
    CostPlan, CostStep,
    extract_additional_cost_plan,
    extract_graveyard_permission_cost_plan,
    add_mana_costs,
    eligible_hand_cards,
    eligible_battlefield_permanents,
    eligible_graveyard_cards,
    total_counters_on_creatures_you_control,
    describe_plan,
)
from .warp import (
    parse_warp_cost,
    card_has_warp,
    has_warp_been_used,
    mark_warp_used,
    mark_warp_cast,
    is_warp_pending,
    schedule_warp_exile_for_object,
    is_warp_castable_from_hand,
)
# === Spree cost-per-mode (W12) ===
# OTJ Spree mechanic — see src/engine/spree.py. The names are aliased with
# leading underscores so the priority module's local symbol table stays
# clear of generic helper names imported elsewhere.
from .spree import (
    is_spree_card as _spree_is_card,
    get_spree_modes as _spree_get_modes,
    get_spree_minmax as _spree_get_minmax,
    get_chosen_spree_modes as _spree_get_chosen,
    open_spree_choice as _spree_open_prompt,
    total_spree_extra_cost as _spree_total_extra_cost,
)
# === Conspire (W29) ===
# Shadowmoor / Lorwyn Conspire mechanic — see src/engine/conspire.py.
# Imported here so the cast pipeline can open the optional conspire
# prompt right after the spell lands on the stack.
from .conspire import (
    find_conspire_grants_for_spell as _conspire_find_grants,
    open_conspire_prompt as _conspire_open_prompt,
    is_conspire_handled as _conspire_is_handled,
    mark_conspire_handled as _conspire_mark_handled,
)
# === end Conspire ===

if TYPE_CHECKING:
    from .turn import TurnManager


# Casting-from-graveyard support (Flashback). This is intentionally minimal
# and driven by rules text patterns since most sets are imported from Scryfall.
_FLASHBACK_COST_RE = re.compile(r'flashback\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_HARMONIZE_COST_RE = re.compile(r'harmonize\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_MAYHEM_COST_RE = re.compile(r'mayhem\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_DISTURB_COST_RE = re.compile(r'disturb\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_UNEARTH_COST_RE = re.compile(r'unearth\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_EMBALM_COST_RE = re.compile(r'embalm\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_ETERNALIZE_COST_RE = re.compile(r'eternalize\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_ESCAPE_RE = re.compile(
    r'escape\s*[—-]\s*((?:\{[^}]+\})+)\s*,\s*exile\s+(\w+)\s+(?:other\s+)?cards?\s+from your graveyard',
    re.IGNORECASE,
)
_JUMP_START_RE = re.compile(r'\bjump-start\b', re.IGNORECASE)
_RETRACE_RE = re.compile(r'\bretrace\b', re.IGNORECASE)
_DELVE_RE = re.compile(r'\bdelve\b', re.IGNORECASE)


@dataclass(frozen=True)
class CastOption:
    """
    A specific way to cast a spell (e.g., flashback from graveyard, normal cast from hand).

    - alt_mana_cost: the cost paid to cast (None = use printed mana cost)
    - additional_cost_plan: extra non-mana and/or extra-mana costs that must be paid
      (e.g., "As an additional cost..., discard a card" or "pay 2 life and sacrifice...").
    """
    description_suffix: str
    alt_mana_cost: Optional[ManaCost]
    metadata: dict
    additional_cost_plan: Optional[CostPlan] = None


class ActionType(Enum):
    """Types of actions a player can take."""
    PASS = auto()              # Pass priority
    CAST_SPELL = auto()        # Cast a spell
    ACTIVATE_ABILITY = auto()  # Activate an ability
    PLAY_LAND = auto()         # Play a land
    SPECIAL_ACTION = auto()    # Special actions (morph, suspend, etc.)
    CAST_ADVENTURE = auto()    # Cast adventure side of a card
    CAST_SPLIT_LEFT = auto()   # Cast left half of split card
    CAST_SPLIT_RIGHT = auto()  # Cast right half of split card
    CREW = auto()              # Crew a Vehicle
    CYCLE_CARD = auto()        # W8: cycle a card from hand (alias for ACTIVATE_ABILITY on a cycling ability)


@dataclass
class PlayerAction:
    """An action a player wants to take."""
    type: ActionType
    player_id: str

    # For casting spells
    card_id: Optional[str] = None
    targets: list[list] = field(default_factory=list)  # List of target lists per requirement
    x_value: int = 0
    modes: list[int] = field(default_factory=list)

    # For activating abilities
    ability_id: Optional[str] = None
    source_id: Optional[str] = None  # Permanent with the ability

    # Additional data
    data: dict = field(default_factory=dict)


@dataclass
class LegalAction:
    """A legal action available to a player."""
    type: ActionType
    card_id: Optional[str] = None
    ability_id: Optional[str] = None
    source_id: Optional[str] = None
    description: str = ""
    requires_targets: bool = False
    requires_mana: bool = False
    mana_cost: Optional[ManaCost] = None
    crew_cost: int = 0  # Power required to crew (for CREW actions)
    crew_with: list[str] = None  # Creature IDs to use for crewing


class PrioritySystem:
    """
    Manages priority and the main game loop.
    """

    def __init__(self, state: GameState):
        self.state = state

        # Other systems (set by Game class)
        self.stack: Optional[StackManager] = None
        self.turn_manager: Optional['TurnManager'] = None
        self.mana_system: Optional[ManaSystem] = None
        self.pipeline: Optional[EventPipeline] = None
        # Set by Game class. Used to auto-resolve pending_choice for AI players
        # (humans get the choice via session.py; AI has no UI, so we resolve
        # in-engine with a deterministic first-option fallback).
        self.game: Optional[Any] = None

        # Priority state
        self.priority_player: Optional[str] = None
        self.passed_players: set[str] = set()

        # For human players - callback to get their action
        self.get_human_action: Optional[Callable[[str, list[LegalAction]], asyncio.Future]] = None

        # For AI players - callback to get their action (sync or async)
        self.get_ai_action: Optional[Callable[[str, GameState, list[LegalAction]], Any]] = None

        # Callback invoked after action is processed (for synchronization)
        # Accepts (action) or () for back-compat; may return an awaitable.
        self.on_action_processed: Optional[Callable[..., Any]] = None

        # Player type tracking
        self.ai_players: set[str] = set()
        # Track loyalty activations by permanent per turn.
        self._loyalty_activation_turn: dict[str, int] = {}

        # Action handlers
        self._action_handlers: dict[ActionType, Callable] = {
            ActionType.PASS: self._handle_pass,
            ActionType.CAST_SPELL: self._handle_cast_spell,
            ActionType.ACTIVATE_ABILITY: self._handle_activate_ability,
            ActionType.PLAY_LAND: self._handle_play_land,
            ActionType.SPECIAL_ACTION: self._handle_special_action,
            ActionType.CREW: self._handle_crew,
            # W8 Cycling: dispatched through the same activated-ability path.
            ActionType.CYCLE_CARD: self._handle_cycle_card,
        }

    def set_ai_player(self, player_id: str) -> None:
        """Mark a player as AI-controlled."""
        self.ai_players.add(player_id)

    def is_ai_player(self, player_id: str) -> bool:
        """Check if a player is AI-controlled."""
        return player_id in self.ai_players

    async def run_priority_loop(self) -> None:
        """
        Main priority loop.

        1. Active player gets priority
        2. Players can act or pass
        3. When all pass with empty stack, proceed
        4. When all pass with stack items, resolve top
        """
        # Check state-based actions before starting
        await self._check_state_based_actions()
        await self._put_triggers_on_stack()

        self.passed_players.clear()
        self.priority_player = self.turn_manager.active_player if self.turn_manager else None

        if not self.priority_player:
            return

        iteration_cap = 5000
        iterations = 0
        # Diagnostic: track action sequence to identify what's looping when
        # the cap fires. Logged only on cap hit.
        action_log: list[tuple] = []
        while True:
            iterations += 1
            if iterations > iteration_cap:
                import logging
                from collections import Counter
                action_counts = Counter(action_log)
                top = action_counts.most_common(5)
                summary = "; ".join(f"{a}:{s}={c}" for (a, s), c in top)
                logging.getLogger(__name__).warning(
                    "PrioritySystem: priority loop hit iteration cap (%d); "
                    "bailing out. Top actions: %s", iteration_cap, summary or "(none)")
                return
            # Check SBAs before granting priority
            await self._check_state_based_actions()
            await self._put_triggers_on_stack()

            # Check if game is over
            if self._is_game_over():
                return

            # Auto-resolve pending_choice for AI players. Without this, the AI
            # has no path to answer choices (no UI), legal_actions still lists
            # CAST_SPELL options, and the cast handler bails because
            # pending_choice is set — silently looping until the iter cap.
            if (self.state.pending_choice is not None
                and self.is_ai_player(self.state.pending_choice.player)
                and self.game is not None):
                pc = self.state.pending_choice
                fallback = self._auto_choice_fallback(pc)
                self.game.submit_choice(pc.id, pc.player, fallback)
                continue

            # Get legal actions for current player
            legal_actions = self.get_legal_actions(self.priority_player)

            # Get player action
            action = await self._get_player_action(self.priority_player, legal_actions)
            # Track for diagnostic on iter-cap fires
            _atype = action.type.name if hasattr(action.type, 'name') else str(action.type)
            _src_id = getattr(action, 'source_id', None) or getattr(action, 'card_id', None) or '_'
            _src_obj = self.state.objects.get(_src_id) if _src_id and _src_id != '_' else None
            _src_name = _src_obj.name if _src_obj else (_src_id or '_')
            action_key = (_atype, _src_name)
            action_log.append(action_key)
            if len(action_log) > 100:
                action_log = action_log[-100:]
            # Hard-force PASS if same non-PASS action repeated 8+ times. This
            # catches loops that the silent-fail and zone-snapshot detectors
            # miss (e.g., cast that "succeeds" by emitting events but never
            # actually advances state).
            if (action.type != ActionType.PASS
                and len(action_log) >= 8
                and all(a == action_key for a in action_log[-8:])):
                action = PlayerAction(type=ActionType.PASS, player_id=self.priority_player)

            if action.type == ActionType.PASS:
                self.passed_players.add(self.priority_player)
                await self._notify_action_processed(action)

                if self._all_players_passed():
                    if self.stack and self.stack.is_empty():
                        return  # Phase/step ends
                    else:
                        # Resolve top of stack
                        if self.stack:
                            events = self.stack.resolve_top()
                            for event in events:
                                self._emit_event(event)

                        self.passed_players.clear()
                        self.priority_player = self.turn_manager.active_player if self.turn_manager else None
                        continue
                else:
                    # Next player gets priority
                    self.priority_player = self._get_next_player()
                    continue
            else:
                # Player took an action - reset passes
                self.passed_players.clear()
                # Snapshot the card's zone before execution so we can detect
                # "no-op casts" — actions that returned events but didn't
                # actually move the card (a downstream silent failure).
                pre_zone = None
                if action.card_id and action.type == ActionType.CAST_SPELL:
                    pre_card = self.state.objects.get(action.card_id)
                    if pre_card:
                        pre_zone = pre_card.zone
                executed_events = await self._execute_action(action)
                await self._notify_action_processed(action)
                # Detect silent-fail or no-op:
                # 1. No events emitted AND no pending choice → silent fail
                # 2. CAST_SPELL but card didn't leave its source zone → no-op
                no_op = False
                if not executed_events and self.state.pending_choice is None:
                    no_op = True
                elif (action.type == ActionType.CAST_SPELL
                      and action.card_id
                      and pre_zone is not None
                      and self.state.pending_choice is None):
                    post_card = self.state.objects.get(action.card_id)
                    if post_card and post_card.zone == pre_zone:
                        no_op = True
                if no_op:
                    self.passed_players.add(self.priority_player)
                    if self._all_players_passed():
                        if self.stack and self.stack.is_empty():
                            return
                        if self.stack:
                            stack_events = self.stack.resolve_top()
                            for ev in stack_events:
                                self._emit_event(ev)
                        self.passed_players.clear()
                        self.priority_player = self.turn_manager.active_player if self.turn_manager else None
                        continue
                    self.priority_player = self._get_next_player()
                    continue
                # Player retains priority after acting (rule 116.3c)
                continue

    async def _get_player_action(
        self,
        player_id: str,
        legal_actions: list[LegalAction]
    ) -> PlayerAction:
        """Get action from a player (human or AI)."""
        if self.is_ai_player(player_id):
            # AI player
            if self.get_ai_action:
                result = self.get_ai_action(player_id, self.state, legal_actions)
                if inspect.isawaitable(result):
                    return await result
                return result
            else:
                # Default: pass priority
                return PlayerAction(type=ActionType.PASS, player_id=player_id)
        else:
            # Human player
            if self.get_human_action:
                return await self.get_human_action(player_id, legal_actions)
            else:
                # No handler - auto-pass
                return PlayerAction(type=ActionType.PASS, player_id=player_id)

    def _auto_choice_fallback(self, pc) -> list:
        """
        Build a deterministic fallback selection for an AI player's pending_choice.
        Picks the first `min_choices` options. Mirrors session.py's human-timeout
        fallback so AI matches behave like a human who fails to respond.
        """
        fallback: list = []
        n = max(1, pc.min_choices or 1)
        for opt in (pc.options or [])[:n]:
            if isinstance(opt, dict):
                if opt.get("id") is not None:
                    fallback.append(opt["id"])
                elif opt.get("index") is not None:
                    fallback.append(opt["index"])
                else:
                    fallback.append(opt)
            else:
                fallback.append(opt)
        return fallback

    def _emit_cast_target_choice(self, card, action: PlayerAction) -> Optional[list[Event]]:
        """Emit a PendingChoice for cast-time targets and pause the cast.

        Phase 5b: when a CardDefinition declares ``target_requirements`` and
        the action didn't pre-supply targets (drag-to-target / AI selection
        both pre-supply), the engine chains one PendingChoice per requirement
        and re-enters ``_handle_cast_spell_sync`` with all targets filled in.

        Returns:
            - ``[]`` cast paused; PendingChoice is set on state. Caller must
              return this verbatim from the cast handler.
            - ``None`` no PendingChoice was emitted (no requirements, or a
              requirement had zero legal targets — caller should return ``[]``
              itself to abort the cast cleanly, MTG rules: a spell with no
              legal targets can't be cast).
        """
        reqs = card.card_def.target_requirements
        if not reqs:
            return None
        return self._emit_cast_target_choice_with(card, action, reqs)

    def _emit_cast_target_choice_with(
        self, card, action: PlayerAction, reqs: list,
    ) -> Optional[list[Event]]:
        """Variant of ``_emit_cast_target_choice`` that accepts an explicit
        list of requirements. Used when the requirements come from a CardFace
        (Adventure half) rather than the parent CardDefinition.
        """
        from .targeting import TargetingSystem
        if not reqs:
            return None
        return self._emit_cast_target_choice_step(
            card, action, reqs, 0, [], TargetingSystem(self.state)
        )

    def _emit_cast_target_choice_step(
        self,
        card,
        action: PlayerAction,
        reqs: list,
        idx: int,
        accumulated: list,
        targeting,
    ) -> Optional[list[Event]]:
        """Recursive helper: emit choice for reqs[idx], chain to idx+1 on resolve.

        Phase 5b cross-target: each entry in ``reqs`` may be a plain
        ``TargetRequirement`` OR a ``TargetRequirementBuilder`` callable
        (``Callable[[state, controller_id, prior_picks_ids], TargetRequirement]``).
        Callables are resolved at this step so a later requirement can
        depend on the IDs picked for earlier ones (e.g. "another target
        creature" exclude the first pick, "different controllers" exclude
        the first pick's controller, "same mana value" pin the second
        filter's MV to the first pick's MV).
        """
        import dataclasses
        from .pending_choice_helpers import create_choice_and_resolve
        from .targeting import Target, resolve_target_requirement_spec

        # Base case: all requirements satisfied — re-enter the cast.
        if idx >= len(reqs):
            new_action = dataclasses.replace(action, targets=accumulated)
            return self._handle_cast_spell_sync(new_action)

        # Cross-target: project the accumulated picks down to a
        # list-of-list-of-ids so the builder callable can read prior picks
        # without leaking ``Target`` internals to card-side code.
        accumulated_ids: list[list[str]] = []
        for picks in accumulated:
            accumulated_ids.append([
                (t.id if hasattr(t, 'id') else t) for t in picks
            ])

        try:
            req = resolve_target_requirement_spec(
                reqs[idx], self.state, action.player_id, accumulated_ids
            )
        except TypeError:
            # Malformed spec — abort the cast rather than crash the engine.
            return []

        legal_ids = targeting.get_legal_targets(req, card, action.player_id)
        if not legal_ids:
            # No legal target for this requirement — cast can't proceed.
            # MTG rules: "if no legal targets, the spell can't be cast".
            # For optional requirements (count_type='up_to' with min=0),
            # advance past this requirement with an empty pick list so the
            # rest of the chain still runs. Divide-damage requirements are
            # NOT optional even when count_type='any_number' — a divide-X
            # spell must allocate to at least one legal target, so abort.
            if req.min_targets() == 0 and getattr(req, "divide_amount", None) is None:
                return self._emit_cast_target_choice_step(
                    card, action, reqs, idx + 1, accumulated + [[]], targeting
                )
            return []

        # Build options for the modal. Players get a display label; objects
        # use their name.
        options: list[dict] = []
        for tid in legal_ids:
            obj = self.state.objects.get(tid)
            if obj is not None:
                label = getattr(obj, "name", None) or tid
                # divide_allocation renderer reads ``name``/``type``/``life``
                # to render +/- target chips. Emit them on every option so a
                # divide-damage req gets a useful UI.
                option = {"id": tid, "label": label, "name": label}
                if hasattr(obj, "characteristics"):
                    chs = obj.characteristics
                    if chs.toughness is not None:
                        option["life"] = (chs.toughness or 0) - int(
                            getattr(obj.state, "damage", 0) or 0
                        )
                    option["type"] = (
                        "creature"
                        if any(
                            t.name == "CREATURE"
                            for t in getattr(chs, "types", set()) or set()
                        )
                        else "permanent"
                    )
            else:
                player = self.state.players.get(tid)
                label = getattr(player, "name", None) or f"Player {tid[:8]}"
                option = {
                    "id": tid,
                    "label": label,
                    "name": label,
                    "type": "player",
                }
                if player is not None:
                    option["life"] = getattr(player, "life", 0)
            options.append(option)

        priority_sys = self
        # Snapshot for the handler closure.
        state_snapshot = self.state

        # Phase 5b: divide-damage path. When the TargetRequirement carries
        # a ``divide_amount`` (int or callable), emit a single
        # ``divide_allocation`` PendingChoice instead of a plain ``target``
        # choice. Submission shape is list[{target_id, amount}]; the
        # handler bakes each amount into the chosen ``Target.divided_amount``
        # so the resolve callback (typically ``make_divide_damage_resolve``)
        # can emit one DAMAGE event per allocation.
        divide_amount = getattr(req, "divide_amount", None)
        if divide_amount is not None:
            # Resolve callable budgets (X-cost) at prompt time.
            if callable(divide_amount):
                try:
                    total_amount = int(divide_amount(self.state, action.player_id) or 0)
                except Exception:
                    total_amount = 0
            else:
                total_amount = int(divide_amount or 0)

            if total_amount <= 0:
                # Nothing to allocate — treat as no-legal-targets (cast aborts).
                return []

            def divide_handler(choice, selected, st):
                # Normalize selection into a list of (target_id, amount).
                allocations: list[tuple[str, int]] = []
                if isinstance(selected, dict):
                    for tid, amt in selected.items():
                        allocations.append((str(tid), int(amt or 0)))
                elif isinstance(selected, list):
                    for item in selected:
                        if isinstance(item, dict):
                            tid = item.get("target_id") or item.get("id")
                            amt = int(item.get("amount", 0) or 0)
                            if tid:
                                allocations.append((str(tid), amt))
                        elif isinstance(item, tuple) and len(item) == 2:
                            allocations.append((str(item[0]), int(item[1] or 0)))

                # Build Targets with divided_amount.
                picked: list[Target] = []
                for tid, amt in allocations:
                    if amt <= 0:
                        continue
                    is_player = tid in state_snapshot.players
                    picked.append(Target(
                        id=tid,
                        is_player=is_player,
                        divided_amount=amt,
                    ))
                return priority_sys._emit_cast_target_choice_step(
                    card, action, reqs, idx + 1, accumulated + [picked], targeting
                )

            # AI fallback heuristic for divide_allocation: pile everything
            # on the first legal target. The real heuristic lives in
            # ``AIEngine._make_divide_allocation_choice``, which spreads
            # damage across opponent creatures preferentially.
            heuristic = [{"target_id": legal_ids[0], "amount": total_amount}]

            prompt = req.label or f"Allocate {total_amount} damage among targets"
            return create_choice_and_resolve(
                self.state,
                choice_type="divide_allocation",
                player_id=action.player_id,
                prompt=prompt,
                options=options,
                source_id=card.id,
                min_choices=1,
                max_choices=len(options),
                handler=divide_handler,
                heuristic_pick=heuristic,
                total_amount=total_amount,
                effect="damage",
                interaction_mode="overlay",
            )

        def handler(choice, selected, st):
            picked_ids = [s.get("id") if isinstance(s, dict) else s for s in selected]
            # Phase 5b: normalize chosen IDs to ``Target`` instances so the
            # stack's ``validate_targets`` and resolve helpers (which expect
            # ``Target`` shape) see the proper object protocol. Without this
            # ``target.is_player`` and ``target.id`` access on resolve fails.
            picked: list[Target] = []
            for tid in picked_ids:
                is_player = tid in state_snapshot.players
                picked.append(Target(id=tid, is_player=is_player))
            # Phase 5b cross-target: clear this requirement's PendingChoice
            # before chaining. ``submit_choice`` does this in game.py:1497
            # BEFORE invoking _process_choice; the AI inline path
            # (``resolve_pending_choice_inline``) defers clearing to its
            # ``finally`` block, which leaves a stale c_N on state.pending_choice
            # while the handler is running. That stale value would make the
            # base-case re-entry into ``_handle_cast_spell_sync`` early-out at
            # its ``if pending_choice is not None`` guard, silently dropping
            # the cast on the AI path. Self-clearing here makes both paths
            # behave identically.
            st.pending_choice = None
            return priority_sys._emit_cast_target_choice_step(
                card, action, reqs, idx + 1, accumulated + [picked], targeting
            )

        # AI fallback heuristic: pick the first ``min_targets()`` legal
        # targets so cross-target requirements that need more than one pick
        # (e.g. "two other target creatures") satisfy their min count for
        # the AI path. Better heuristics live in
        # src/ai/engine.py:_select_targets_for_spell (which runs before the
        # action is submitted, so this code path only fires for AIs that
        # submit untargeted casts — rare).
        min_t = req.min_targets()
        max_t = req.max_targets()
        # Take at least one pick even if min_targets==0 (so the chain has
        # an option for the AI to pursue); cap at min(min_t, available).
        heuristic_count = max(1, min_t)
        heuristic_picks = legal_ids[:min(heuristic_count, len(legal_ids))]
        # Phase 5b polish: MTG cast-time target prompts render as
        # click-to-target board overlays (legacy drag-style UX) rather
        # than the generic modal panel. ``interaction_mode='overlay'`` is
        # propagated through ``callback_data`` to the client; other
        # engines that build choices via ``create_choice_and_resolve``
        # omit this hint and keep modal-style rendering.
        return create_choice_and_resolve(
            self.state,
            choice_type="target",
            player_id=action.player_id,
            prompt=req.label or "Choose a target",
            options=options,
            source_id=card.id,
            min_choices=min_t,
            max_choices=int(max_t) if max_t != float('inf') else len(options),
            handler=handler,
            heuristic_pick=heuristic_picks,
            interaction_mode="overlay",
        )

    # ------------------------------------------------------------------
    # Phase 5b: activated-ability cast-time target picker
    # ------------------------------------------------------------------
    def _emit_activate_target_choice_step(
        self,
        action: PlayerAction,
        ability,
        source,
        reqs: list,
        idx: int,
        accumulated: list,
        targeting,
    ) -> Optional[list[Event]]:
        """Recursive helper: emit choice for reqs[idx], chain to idx+1 on resolve.

        Structural twin of ``_emit_cast_target_choice_step`` but for activated
        abilities. CR 602.1 mandates announce -> choose targets -> pay costs,
        so the choice fires BEFORE ``can_pay_activation`` / ``pay_activation_cost``.
        Base case re-enters ``_handle_activate_registered_ability_sync`` with
        ``dataclasses.replace(action, targets=accumulated)``.

        ``reqs`` entries may be plain ``TargetRequirement`` or
        ``TargetRequirementBuilder`` callables (cross-target support); the
        builder receives the IDs picked for earlier requirements.

        Returns:
            - ``[]`` choice paused — PendingChoice is set on state.
            - ``None`` no choice emitted (no requirements, no legal targets
              for a non-optional req).
        """
        import dataclasses
        from .pending_choice_helpers import create_choice_and_resolve
        from .targeting import Target, resolve_target_requirement_spec

        # Base case: all requirements satisfied — re-enter the activation.
        if idx >= len(reqs):
            new_action = dataclasses.replace(action, targets=accumulated)
            return self._handle_activate_registered_ability_sync(new_action, source)

        accumulated_ids: list[list[str]] = []
        for picks in accumulated:
            accumulated_ids.append([
                (t.id if hasattr(t, 'id') else t) for t in picks
            ])

        try:
            req = resolve_target_requirement_spec(
                reqs[idx], self.state, action.player_id, accumulated_ids
            )
        except TypeError:
            # Malformed spec — abort without cost paid.
            return []

        legal_ids = targeting.get_legal_targets(req, source, action.player_id)
        if not legal_ids:
            # No legal target. For optional requirements (count_type='up_to'
            # with min=0), advance with an empty pick list. Otherwise abort
            # cleanly — CR 602.1 says no cost is paid yet, so the player
            # simply walks away.
            if req.min_targets() == 0 and getattr(req, "divide_amount", None) is None:
                return self._emit_activate_target_choice_step(
                    action, ability, source, reqs, idx + 1,
                    accumulated + [[]], targeting,
                )
            return []

        # Build options for the modal.
        options: list[dict] = []
        for tid in legal_ids:
            obj = self.state.objects.get(tid)
            if obj is not None:
                label = getattr(obj, "name", None) or tid
                option = {"id": tid, "label": label, "name": label}
                if hasattr(obj, "characteristics"):
                    chs = obj.characteristics
                    if chs.toughness is not None:
                        option["life"] = (chs.toughness or 0) - int(
                            getattr(obj.state, "damage", 0) or 0
                        )
                    option["type"] = (
                        "creature"
                        if any(
                            t.name == "CREATURE"
                            for t in getattr(chs, "types", set()) or set()
                        )
                        else "permanent"
                    )
            else:
                player = self.state.players.get(tid)
                label = getattr(player, "name", None) or f"Player {tid[:8]}"
                option = {
                    "id": tid,
                    "label": label,
                    "name": label,
                    "type": "player",
                }
                if player is not None:
                    option["life"] = getattr(player, "life", 0)
            options.append(option)

        priority_sys = self
        state_snapshot = self.state

        divide_amount = getattr(req, "divide_amount", None)
        if divide_amount is not None:
            if callable(divide_amount):
                try:
                    total_amount = int(divide_amount(self.state, action.player_id) or 0)
                except Exception:
                    total_amount = 0
            else:
                total_amount = int(divide_amount or 0)

            if total_amount <= 0:
                return []

            def divide_handler(choice, selected, st):
                allocations: list[tuple[str, int]] = []
                if isinstance(selected, dict):
                    for tid, amt in selected.items():
                        allocations.append((str(tid), int(amt or 0)))
                elif isinstance(selected, list):
                    for item in selected:
                        if isinstance(item, dict):
                            tid = item.get("target_id") or item.get("id")
                            amt = int(item.get("amount", 0) or 0)
                            if tid:
                                allocations.append((str(tid), amt))
                        elif isinstance(item, tuple) and len(item) == 2:
                            allocations.append((str(item[0]), int(item[1] or 0)))

                picked: list[Target] = []
                for tid, amt in allocations:
                    if amt <= 0:
                        continue
                    is_player = tid in state_snapshot.players
                    picked.append(Target(
                        id=tid,
                        is_player=is_player,
                        divided_amount=amt,
                    ))
                return priority_sys._emit_activate_target_choice_step(
                    action, ability, source, reqs, idx + 1,
                    accumulated + [picked], targeting,
                )

            heuristic = [{"target_id": legal_ids[0], "amount": total_amount}]
            prompt = req.label or f"Allocate {total_amount} among targets"
            return create_choice_and_resolve(
                self.state,
                choice_type="divide_allocation",
                player_id=action.player_id,
                prompt=prompt,
                options=options,
                source_id=source.id,
                min_choices=1,
                max_choices=len(options),
                handler=divide_handler,
                heuristic_pick=heuristic,
                total_amount=total_amount,
                effect="damage",
                interaction_mode="overlay",
            )

        def handler(choice, selected, st):
            picked_ids = [s.get("id") if isinstance(s, dict) else s for s in selected]
            picked: list[Target] = []
            for tid in picked_ids:
                is_player = tid in state_snapshot.players
                picked.append(Target(id=tid, is_player=is_player))
            # Mirror the cast handler: clear the pending_choice here so the
            # recursive re-entry doesn't trip its own pending-choice guard
            # on the AI inline path (cast does this at priority.py:645).
            st.pending_choice = None
            return priority_sys._emit_activate_target_choice_step(
                action, ability, source, reqs, idx + 1,
                accumulated + [picked], targeting,
            )

        min_t = req.min_targets()
        max_t = req.max_targets()
        heuristic_count = max(1, min_t)
        heuristic_picks = legal_ids[:min(heuristic_count, len(legal_ids))]
        return create_choice_and_resolve(
            self.state,
            choice_type="target",
            player_id=action.player_id,
            prompt=req.label or "Choose a target",
            options=options,
            source_id=source.id,
            min_choices=min_t,
            max_choices=int(max_t) if max_t != float('inf') else len(options),
            handler=handler,
            heuristic_pick=heuristic_picks,
            interaction_mode="overlay",
        )

    def _handle_activate_registered_ability_sync(
        self, action: PlayerAction, source,
    ) -> list[Event]:
        """Sync core of registered ``activated:N`` ability dispatch.

        Factored out of ``_handle_activate_ability`` so the Phase 5b
        target-choice handler can re-enter the activation flow with baked-in
        ``action.targets``. The async outer handler also delegates here when
        ``action.ability_id`` starts with ``"activated:"``.

        Order matches CR 602.1: identify ability → emit cast-time target
        choice (if declared and empty) → pay costs → push stack item.
        """
        from .activated import (
            can_pay_activation,
            pay_activation_cost,
            record_activation,
        )
        from .cost_query import get_effective_activation_cost

        events: list[Event] = []
        pushed_stack_item = False

        if not action.ability_id or not action.ability_id.startswith("activated:"):
            return []
        try:
            idx = int(action.ability_id.split(":", 1)[1])
        except ValueError:
            return []
        abilities = getattr(source.state, "activated_abilities", []) or []
        if not (0 <= idx < len(abilities)):
            return []
        ability = abilities[idx]

        # Phase 5b: engine-authoritative cast-time targeting. If the ability
        # declares ``target_requirements`` and the action arrives without
        # pre-supplied targets, emit a chained PendingChoice and pause the
        # activation — BEFORE paying any cost (CR 602.1). Pre-supplied
        # targets (drag-to-target / AI ``_select_activated_targets``) skip
        # this path entirely.
        if (
            not action.targets
            and getattr(ability, 'target_requirements', None)
        ):
            from .targeting import TargetingSystem
            # Never start a new picker while another choice is pending.
            if self.state.pending_choice is not None:
                return []
            paused = self._emit_activate_target_choice_step(
                action, ability, source,
                ability.target_requirements, 0, [],
                TargetingSystem(self.state),
            )
            if paused is not None:
                return paused

        _is_active = (
            self.turn_manager is not None
            and self.turn_manager.turn_state.active_player_id == action.player_id
        )
        _is_main = False
        if self.turn_manager is not None:
            from .turn import Phase as _Phase
            _is_main = self.turn_manager.turn_state.phase in (
                _Phase.PRECOMBAT_MAIN, _Phase.POSTCOMBAT_MAIN
            )
        _stack_empty = (self.stack is None) or (len(self.stack.items) == 0)
        _x = int(getattr(action, 'x_value', 0) or 0)
        _effective_cost = None
        if ability.mana_cost is not None:
            try:
                _effective_cost = get_effective_activation_cost(
                    ability, source, action.player_id, self.state,
                )
            except Exception:
                _effective_cost = ability.mana_cost
        if not can_pay_activation(
            ability, source, self.state, action.player_id,
            mana_system=self.mana_system,
            is_active_player=_is_active,
            is_main_phase=_is_main,
            stack_empty=_stack_empty,
            x_value=_x,
            effective_mana_cost=_effective_cost,
        ):
            return []
        # Pay costs (mana paid via mana_system; tap/sac/etc emit events).
        events.extend(pay_activation_cost(
            ability, source, self.state, action.player_id,
            mana_system=self.mana_system,
            x_value=_x,
            effective_mana_cost=_effective_cost,
        ))
        _src_id = source.id
        _effect_fn = ability.effect_fn

        try:
            _sig = inspect.signature(_effect_fn)
            _accepts_x = (
                'x_value' in _sig.parameters
                or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in _sig.parameters.values()
                )
            )
        except (TypeError, ValueError):
            _accepts_x = False

        def _resolve_activated(targets, st: GameState) -> list[Event]:
            obj = st.objects.get(_src_id)
            if obj is None:
                return []
            flat: list = []
            for group in (targets or []):
                if isinstance(group, list):
                    flat.extend(group)
                else:
                    flat.append(group)
            try:
                if _accepts_x:
                    return list(_effect_fn(obj, st, flat, x_value=_x) or [])
                return list(_effect_fn(obj, st, flat) or [])
            except Exception:
                return []

        if self.stack:
            self.stack.push(StackItem(
                id="",
                type=StackItemType.ACTIVATED_ABILITY,
                source_id=source.id,
                controller_id=action.player_id,
                chosen_targets=action.targets,
                resolve_fn=_resolve_activated,
            ))
            pushed_stack_item = True
        record_activation(ability, self.state)
        # === Crime tracking (OTJ) ===
        from .crime import check_cast_targets_for_crime as _ccfc
        _crime_events = _ccfc(
            controller_id=action.player_id,
            targets=action.targets,
            state=self.state,
            source_id=action.source_id,
        )
        events.extend(_crime_events)
        events.append(Event(
            type=EventType.ACTIVATE,
            payload={
                'source_id': action.source_id,
                'ability_id': action.ability_id,
                'controller': action.player_id,
                'is_exhaust': bool(getattr(ability, 'is_exhaust', False)),
                'x_value': _x,
            },
        ))
        # Ward / TARGET_CHOSEN parity.
        if pushed_stack_item and action.targets:
            events.extend(build_target_chosen_events(
                action.source_id, action.player_id, action.targets,
            ))
        return events

    async def _notify_action_processed(self, action: PlayerAction) -> None:
        """
        Invoke the `on_action_processed` hook.

        - Supports both legacy callbacks with no args and newer callbacks that accept
          the processed `PlayerAction`.
        - Supports async callbacks by awaiting the return value if awaitable.
        """
        if not self.on_action_processed:
            return

        try:
            result = self.on_action_processed(action)
        except TypeError:
            # Back-compat for older callbacks: on_action_processed()
            result = self.on_action_processed()

        if inspect.isawaitable(result):
            await result

    def get_legal_actions(self, player_id: str) -> list[LegalAction]:
        """
        Get all legal actions for a player.
        """
        actions = []

        # Can always pass
        actions.append(LegalAction(
            type=ActionType.PASS,
            description="Pass priority"
        ))

        # Check if player can cast spells
        hand_key = f"hand_{player_id}"
        hand = self.state.zones.get(hand_key)

        if hand:
            for card_id in hand.objects:
                card = self.state.objects.get(card_id)
                if not card:
                    continue

                mana_cost_str = card.characteristics.mana_cost
                printed = ManaCost.parse(mana_cost_str or "")
                # Apply registered cost-reduction interceptors to the printed
                # cost before considering delve.
                cost = get_effective_mana_cost(card, player_id, self.state, base_cost=printed)
                delve_discount = self._delve_discount(card, player_id, cost)
                cost_for_cast = self._reduce_generic_cost(cost, delve_discount)
                std_plan = self._get_standard_additional_cost_plan(card)
                ctx = CastCostContext(
                    state=self.state,
                    mana_system=self.mana_system,
                    player_id=player_id,
                    casting_card_id=card_id,
                    casting_card_name=card.name,
                    casting_zone=card.zone,
                    base_mana_cost=cost_for_cast,
                    x_value=0,
                )

                # Don't accidentally allow cards with no printed mana cost.
                cost_override = cost_for_cast if (mana_cost_str and mana_cost_str.strip() != "") else None
                if self._can_cast(card, player_id, cost_override=cost_override) and self._can_pay_cost_plan(std_plan, ctx):
                    desc = f"Cast {card.name}"
                    if std_plan:
                        desc = f"{desc} ({describe_plan(std_plan)})"
                    actions.append(LegalAction(
                        type=ActionType.CAST_SPELL,
                        card_id=card_id,
                        description=desc,
                        requires_mana=not cost_for_cast.is_free(),
                        mana_cost=cost_for_cast
                    ))

                # EOE Warp: alternate cast cost from hand. Each card may be
                # warp-cast at most once; we add this as an additional cast
                # option alongside the printed cost.
                if is_warp_castable_from_hand(card, self.state, player_id):
                    warp_cost = parse_warp_cost(
                        getattr(getattr(card, "card_def", None), "text", None)
                    )
                    if warp_cost is not None:
                        warp_ctx = CastCostContext(
                            state=self.state,
                            mana_system=self.mana_system,
                            player_id=player_id,
                            casting_card_id=card_id,
                            casting_card_name=card.name,
                            casting_zone=card.zone,
                            base_mana_cost=warp_cost,
                            x_value=0,
                        )
                        if self._can_cast(card, player_id, cost_override=warp_cost) and self._can_pay_cost_plan(std_plan, warp_ctx):
                            actions.append(LegalAction(
                                type=ActionType.CAST_SPELL,
                                card_id=card_id,
                                ability_id="hand:warp",
                                description=f"Cast {card.name} (warp {warp_cost.to_string()})",
                                requires_mana=not warp_cost.is_free(),
                                mana_cost=warp_cost,
                            ))

        # Casting from graveyard (Flashback/Harmonize/Mayhem/etc.).
        graveyard_key = f"graveyard_{player_id}"
        graveyard = self.state.zones.get(graveyard_key)
        if graveyard:
            for card_id in graveyard.objects:
                card = self.state.objects.get(card_id)
                if not card or card.owner != player_id:
                    continue

                std_plan = self._get_standard_additional_cost_plan(card)
                options = self._get_graveyard_cast_options(card, player_id)
                for idx, option in enumerate(options):
                    mana_cost_str = card.characteristics.mana_cost
                    base_for_option = option.alt_mana_cost or ManaCost.parse(mana_cost_str or "")
                    # Apply registered cost-reduction interceptors to whichever
                    # base cost we're using (printed or alt like flashback).
                    cost_for_ui = get_effective_mana_cost(
                        card, player_id, self.state, base_cost=base_for_option,
                    )
                    delve_discount = self._delve_discount(card, player_id, cost_for_ui)
                    cost_for_cast = self._reduce_generic_cost(cost_for_ui, delve_discount)
                    full_plan = self._concat_cost_plans(std_plan, option.additional_cost_plan)
                    ctx = CastCostContext(
                        state=self.state,
                        mana_system=self.mana_system,
                        player_id=player_id,
                        casting_card_id=card_id,
                        casting_card_name=card.name,
                        casting_zone=card.zone,
                        base_mana_cost=cost_for_cast,
                        x_value=0,
                    )

                    # Only allow printed-cost options if a printed mana cost exists.
                    if option.alt_mana_cost is None and (not mana_cost_str or mana_cost_str.strip() == ""):
                        continue

                    if not self._can_cast(card, player_id, cost_override=cost_for_cast):
                        continue

                    if not self._can_pay_cost_plan(full_plan, ctx):
                        continue

                    desc = f"Cast {card.name} ({option.description_suffix})"
                    if full_plan:
                        desc = f"{desc}; {describe_plan(full_plan)}"
                    actions.append(LegalAction(
                        type=ActionType.CAST_SPELL,
                        card_id=card_id,
                        ability_id=self._cast_option_ability_id(ZoneType.GRAVEYARD, idx, option),
                        description=desc,
                        requires_mana=not cost_for_cast.is_free(),
                        mana_cost=cost_for_cast
                    ))

            # Graveyard activated abilities (Unearth/Embalm/Eternalize/etc.).
            for card_id in graveyard.objects:
                card = self.state.objects.get(card_id)
                if not card or card.owner != player_id:
                    continue

                if CardType.CREATURE not in card.characteristics.types:
                    continue

                # Unearth
                unearth_cost = self._get_unearth_cost(card)
                if unearth_cost is not None and self._can_cast(card, player_id, cost_override=unearth_cost):
                    actions.append(LegalAction(
                        type=ActionType.ACTIVATE_ABILITY,
                        source_id=card_id,
                        ability_id="graveyard:unearth",
                        description=f"Unearth {card.name} ({unearth_cost.to_string()})",
                        requires_mana=not unearth_cost.is_free(),
                        mana_cost=unearth_cost,
                    ))

                # Embalm
                embalm_cost = self._get_embalm_cost(card)
                if embalm_cost is not None and self._can_cast(card, player_id, cost_override=embalm_cost):
                    actions.append(LegalAction(
                        type=ActionType.ACTIVATE_ABILITY,
                        source_id=card_id,
                        ability_id="graveyard:embalm",
                        description=f"Embalm {card.name} ({embalm_cost.to_string()})",
                        requires_mana=not embalm_cost.is_free(),
                        mana_cost=embalm_cost,
                    ))

                # Eternalize
                eternalize_cost = self._get_eternalize_cost(card)
                if eternalize_cost is not None and self._can_cast(card, player_id, cost_override=eternalize_cost):
                    actions.append(LegalAction(
                        type=ActionType.ACTIVATE_ABILITY,
                        source_id=card_id,
                        ability_id="graveyard:eternalize",
                        description=f"Eternalize {card.name} ({eternalize_cost.to_string()})",
                        requires_mana=not eternalize_cost.is_free(),
                        mana_cost=eternalize_cost,
                    ))

        # WOE Adventure: cast the main half of an Adventure card from exile.
        # Only the owner of a card flagged ``adventure_exile=True`` can cast
        # it from exile, and only for its printed mana cost.
        exile_zone = self.state.zones.get('exile')
        if exile_zone:
            for card_id in exile_zone.objects:
                card = self.state.objects.get(card_id)
                if not card or card.owner != player_id:
                    continue
                if not getattr(card.state, 'adventure_exile', False):
                    continue

                mana_cost_str = card.characteristics.mana_cost
                printed = ManaCost.parse(mana_cost_str or "")
                cost = get_effective_mana_cost(card, player_id, self.state, base_cost=printed)
                std_plan = self._get_standard_additional_cost_plan(card)
                ctx = CastCostContext(
                    state=self.state,
                    mana_system=self.mana_system,
                    player_id=player_id,
                    casting_card_id=card_id,
                    casting_card_name=card.name,
                    casting_zone=card.zone,
                    base_mana_cost=cost,
                    x_value=0,
                )

                cost_override = cost if (mana_cost_str and mana_cost_str.strip() != "") else None
                if cost_override is None:
                    continue
                if not self._can_cast(card, player_id, cost_override=cost_override):
                    continue
                if not self._can_pay_cost_plan(std_plan, ctx):
                    continue

                desc = f"Cast {card.name} (from exile, Adventure)"
                if std_plan:
                    desc = f"{desc}; {describe_plan(std_plan)}"
                actions.append(LegalAction(
                    type=ActionType.CAST_SPELL,
                    card_id=card_id,
                    ability_id="exile:adventure",
                    description=desc,
                    requires_mana=not cost.is_free(),
                    mana_cost=cost,
                ))

        # OTJ Plot: cast a plotted card from exile for free on a later turn,
        # sorcery-speed. ``can_cast_plotted`` enforces (a) the card is in
        # exile with a recorded plotted_turn (b) plot_cast_used is False
        # (c) current turn > plotted_turn (the "later turn" rule). We gate
        # this further to the controller's own main phase with empty stack
        # so Plot casts respect sorcery speed (CR 702.166c).
        if exile_zone:
            # Reuse the is_active/is_main/stack_empty flags computed below in
            # this method's later phase 4 section. They're not yet in scope
            # here, so we recompute (cheap).
            _plot_is_active = (
                self.turn_manager is not None
                and self.turn_manager.turn_state.active_player_id == player_id
            )
            _plot_is_main = False
            if self.turn_manager is not None:
                from .turn import Phase as _Phase
                _plot_is_main = self.turn_manager.turn_state.phase in (
                    _Phase.PRECOMBAT_MAIN, _Phase.POSTCOMBAT_MAIN
                )
            _plot_stack_empty = (self.stack is None) or (len(self.stack.items) == 0)

            if _plot_is_active and _plot_is_main and _plot_stack_empty:
                from .plot_saddle import can_cast_plotted
                for card_id in exile_zone.objects:
                    card = self.state.objects.get(card_id)
                    if not card or card.owner != player_id:
                        continue
                    if not can_cast_plotted(card, self.state):
                        continue
                    # Don't double-add if Adventure already surfaced this card.
                    if any(
                        a.card_id == card_id and a.ability_id == "exile:plot"
                        for a in actions
                    ):
                        continue
                    # Plot cast is free (mana cost = empty). Only additional
                    # cost plans (rare for Plot cards) still need to be payable.
                    std_plan = self._get_standard_additional_cost_plan(card)
                    free_cost = ManaCost()
                    ctx = CastCostContext(
                        state=self.state,
                        mana_system=self.mana_system,
                        player_id=player_id,
                        casting_card_id=card_id,
                        casting_card_name=card.name,
                        casting_zone=card.zone,
                        base_mana_cost=free_cost,
                        x_value=0,
                    )
                    if not self._can_pay_cost_plan(std_plan, ctx):
                        continue
                    desc = f"Cast {card.name} (plotted, free)"
                    if std_plan:
                        desc = f"{desc}; {describe_plan(std_plan)}"
                    actions.append(LegalAction(
                        type=ActionType.CAST_SPELL,
                        card_id=card_id,
                        ability_id="exile:plot",
                        description=desc,
                        requires_mana=False,
                        mana_cost=free_cost,
                    ))

        # === W7 cast-from-zone (legal actions surface) ===
        # Generic cast-from-zone permissions installed via cast_permission.py.
        # We surface a CAST_SPELL action for any card whose owner has a W7
        # grant in its current non-HAND zone. Bespoke handlers above have
        # already added their own actions; we skip cards that already produced
        # a flashback/adventure/etc. action this pass.
        existing_w7_keys = {
            (a.card_id, a.ability_id) for a in actions
            if a.type == ActionType.CAST_SPELL
        }
        for obj_id, candidate in self.state.objects.items():
            if candidate.owner != player_id:
                continue
            if candidate.zone in (ZoneType.HAND, ZoneType.STACK, ZoneType.BATTLEFIELD):
                continue
            if not _w7_is_castable_from_zone(obj_id, candidate.zone, self.state):
                continue
            if (obj_id, None) in existing_w7_keys:
                continue
            override = _w7_cast_cost_override_for(obj_id, candidate.zone, self.state)
            base = override if override is not None else \
                ManaCost.parse(candidate.characteristics.mana_cost or "")
            cost_for_cast = get_effective_mana_cost(
                candidate, player_id, self.state, base_cost=base,
            )
            mana_cost_str = candidate.characteristics.mana_cost
            cost_override_for_can = cost_for_cast if (
                override is not None or (mana_cost_str and mana_cost_str.strip() != "")
            ) else None
            if cost_override_for_can is None:
                continue
            if not self._can_cast(candidate, player_id, cost_override=cost_override_for_can):
                continue
            std_plan = self._get_standard_additional_cost_plan(candidate)
            ctx = CastCostContext(
                state=self.state,
                mana_system=self.mana_system,
                player_id=player_id,
                casting_card_id=obj_id,
                casting_card_name=candidate.name,
                casting_zone=candidate.zone,
                base_mana_cost=cost_for_cast,
                x_value=0,
            )
            if not self._can_pay_cost_plan(std_plan, ctx):
                continue
            zone_label = candidate.zone.name.lower()
            desc = f"Cast {candidate.name} (from {zone_label})"
            actions.append(LegalAction(
                type=ActionType.CAST_SPELL,
                card_id=obj_id,
                description=desc,
                requires_mana=not cost_for_cast.is_free(),
                mana_cost=cost_for_cast,
            ))
        # === end W7 ===

        # Check if player can play lands
        if self._can_play_land(player_id):
            if hand:
                for card_id in hand.objects:
                    card = self.state.objects.get(card_id)
                    if card and CardType.LAND in card.characteristics.types:
                        actions.append(LegalAction(
                            type=ActionType.PLAY_LAND,
                            card_id=card_id,
                            description=f"Play {card.name}"
                        ))
            if self._graveyard_land_permission_active(player_id):
                gy = self.state.zones.get(f"graveyard_{player_id}")
                if gy:
                    for card_id in gy.objects:
                        card = self.state.objects.get(card_id)
                        if not card or card.owner != player_id:
                            continue
                        if CardType.LAND not in card.characteristics.types:
                            continue
                        actions.append(LegalAction(
                            type=ActionType.PLAY_LAND,
                            card_id=card_id,
                            description=f"Play {card.name} (from graveyard)"
                        ))

        # Check for activatable abilities on permanents
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = self.state.objects.get(obj_id)
                if obj and obj.controller == player_id:
                    abilities = self._get_activatable_abilities(obj, player_id)
                    actions.extend(abilities)

            # Check for Vehicles that can be crewed
            crew_actions = self._get_crew_actions(player_id, battlefield)
            actions.extend(crew_actions)

        # Phase: graveyard-zone activated abilities. These are registered by
        # card_def.setup_in_graveyard on ZONE_CHANGE → GRAVEYARD and live on
        # obj.state.activated_abilities like normal. Only the card's owner
        # can activate them.
        graveyard = self.state.zones.get(f'graveyard_{player_id}')
        if graveyard:
            for obj_id in graveyard.objects:
                obj = self.state.objects.get(obj_id)
                if obj and obj.owner == player_id and getattr(obj.state, 'activated_abilities', None):
                    abilities = self._get_activatable_abilities(obj, player_id)
                    actions.extend(abilities)

        # Hand-zone activated abilities (Cycling, Evoke, etc.). Registered by
        # card_def.setup_in_hand. Only the card's owner can activate them.
        hand_zone = self.state.zones.get(f'hand_{player_id}')
        if hand_zone:
            for obj_id in hand_zone.objects:
                obj = self.state.objects.get(obj_id)
                if obj and obj.owner == player_id and getattr(obj.state, 'activated_abilities', None):
                    abilities = self._get_activatable_abilities(obj, player_id)
                    actions.extend(abilities)

        # === Cycling (W8) ===
        # Re-tag any HAND-zone activated-ability action whose ability text is
        # "Cycling ..." with ActionType.CYCLE_CARD so AI/UI can filter cycling
        # actions separately. Dispatch still flows through the normal
        # activated-ability handler (it accepts CYCLE_CARD via the action
        # handler registry below). Cycling abilities are identified by the
        # description prefix set in src/engine/cycling.py.
        for la in actions:
            if (la.type == ActionType.ACTIVATE_ABILITY
                    and la.source_id is not None
                    and la.ability_id and la.ability_id.startswith("activated:")
                    and la.description.startswith("Activate ")
                    and ": Cycling " in la.description):
                source = self.state.objects.get(la.source_id)
                if source is not None and source.zone == ZoneType.HAND:
                    la.type = ActionType.CYCLE_CARD
                    la.card_id = source.id
                    # Trim "Activate <name>: " prefix; keep the cycling cost label.
                    la.description = la.description.split(": ", 1)[-1].replace(
                        "Cycling ", f"Cycle {source.name} for "
                    )
        # === end Cycling (W8) ===

        return actions

    def _get_standard_additional_cost_plan(self, card) -> Optional[CostPlan]:
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        return extract_additional_cost_plan(text)

    def _cast_option_ability_id(self, zone: ZoneType, idx: int, option: CastOption) -> str:
        """
        Produce a stable identifier for a specific cast option.

        We use LegalAction.ability_id for cast actions to disambiguate multiple
        supported ways to cast the same card (e.g., flashback vs harmonize).
        """
        suffix = (option.description_suffix or "").strip().lower()
        suffix = re.sub(r"\s+", "_", suffix)
        suffix = re.sub(r"[^a-z0-9_]+", "", suffix)

        cost_key = "printed"
        if option.alt_mana_cost is not None:
            # Strip braces so the id is safe for UI keys/URLs.
            cost_key = option.alt_mana_cost.to_string().replace("{", "").replace("}", "")
            cost_key = cost_key.replace("/", "_")

        # Include idx to guarantee uniqueness even if two options share a label/cost.
        return f"cast:{zone.name.lower()}:{idx}:{suffix}:{cost_key}"

    def _concat_cost_plans(self, a: Optional[CostPlan], b: Optional[CostPlan]) -> Optional[CostPlan]:
        if not a and not b:
            return None
        return tuple(a or ()) + tuple(b or ())

    def _can_pay_cost_plan(self, plan: Optional[CostPlan], ctx: CastCostContext, extra_mana: Optional[ManaCost] = None) -> bool:
        """
        Check whether a player can pay an additional-cost plan, including any extra mana.

        This is used for legal-action generation to avoid offering casts that would
        immediately fail due to missing discard fodder, sacrifice candidates, etc.
        """
        extra_mana = extra_mana or ManaCost()
        plan = plan or ()

        # Base case: all non-mana checks passed; ensure total mana is payable.
        if not plan:
            if not ctx.mana_system:
                return True
            total = add_mana_costs(ctx.base_mana_cost, extra_mana)
            casting_obj = ctx.state.objects.get(ctx.casting_card_id) if ctx.casting_card_id else None
            return ctx.mana_system.can_cast(
                ctx.player_id, total, ctx.x_value, for_card=casting_obj
            )

        step = plan[0]
        rest = plan[1:]

        if step.kind == "pay_life":
            player = ctx.state.players.get(ctx.player_id)
            if not player or player.life < step.amount:
                return False
            return self._can_pay_cost_plan(rest, ctx, extra_mana)

        if step.kind == "add_mana":
            return self._can_pay_cost_plan(rest, ctx, add_mana_costs(extra_mana, step.mana_cost or ManaCost()))

        if step.kind == "discard":
            eligible = eligible_hand_cards(ctx, step.allowed_types)
            return len(eligible) >= step.amount and self._can_pay_cost_plan(rest, ctx, extra_mana)

        if step.kind == "sacrifice":
            eligible = eligible_battlefield_permanents(ctx, step.allowed_types)
            return len(eligible) >= step.amount and self._can_pay_cost_plan(rest, ctx, extra_mana)

        if step.kind == "tap":
            eligible = eligible_battlefield_permanents(ctx, step.allowed_types, must_be_untapped=True)
            return len(eligible) >= step.amount and self._can_pay_cost_plan(rest, ctx, extra_mana)

        if step.kind == "exile_from_graveyard":
            eligible = eligible_graveyard_cards(ctx)
            return len(eligible) >= step.amount and self._can_pay_cost_plan(rest, ctx, extra_mana)

        if step.kind == "return_to_hand":
            eligible = eligible_battlefield_permanents(ctx)
            return len(eligible) >= step.amount and self._can_pay_cost_plan(rest, ctx, extra_mana)

        if step.kind == "exile_you_control":
            eligible = eligible_battlefield_permanents(ctx, step.allowed_types)
            return len(eligible) >= step.amount and self._can_pay_cost_plan(rest, ctx, extra_mana)

        if step.kind == "remove_counters":
            totals = total_counters_on_creatures_you_control(ctx)
            return sum(totals.values()) >= step.amount and self._can_pay_cost_plan(rest, ctx, extra_mana)

        if step.kind == "or":
            for opt in (step.options or ()):
                combined = tuple(opt) + tuple(rest)
                if self._can_pay_cost_plan(combined, ctx, extra_mana):
                    return True
            return False

        # Unknown cost kind - treat as not payable to avoid offering illegal actions.
        return False

    def _get_flashback_cost(self, card) -> Optional[ManaCost]:
        """Parse a card's flashback cost from rules text, if present."""
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        if not text:
            return None

        match = _FLASHBACK_COST_RE.search(text)
        if not match:
            return None

        cost_str = match.group(1)
        try:
            return ManaCost.parse(cost_str)
        except Exception:
            return None

    def _get_harmonize_cost(self, card) -> Optional[ManaCost]:
        """Parse a card's harmonize cost from rules text, if present."""
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        if not text:
            return None

        match = _HARMONIZE_COST_RE.search(text)
        if not match:
            return None

        cost_str = match.group(1)
        try:
            return ManaCost.parse(cost_str)
        except Exception:
            return None

    def _get_mayhem_cost(self, card) -> Optional[ManaCost]:
        """Parse a card's mayhem cost from rules text, if present."""
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        if not text:
            return None

        match = _MAYHEM_COST_RE.search(text)
        if not match:
            return None

        cost_str = match.group(1)
        try:
            return ManaCost.parse(cost_str)
        except Exception:
            return None

    def _get_disturb_cost(self, card) -> Optional[ManaCost]:
        """Parse a card's disturb cost from rules text, if present."""
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        if not text:
            return None

        match = _DISTURB_COST_RE.search(text)
        if not match:
            return None

        cost_str = match.group(1)
        try:
            return ManaCost.parse(cost_str)
        except Exception:
            return None

    def _get_unearth_cost(self, card) -> Optional[ManaCost]:
        """Parse a card's unearth cost from rules text, if present."""
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        if not text:
            return None

        match = _UNEARTH_COST_RE.search(text)
        if not match:
            return None

        cost_str = match.group(1)
        try:
            return ManaCost.parse(cost_str)
        except Exception:
            return None

    def _get_embalm_cost(self, card) -> Optional[ManaCost]:
        """Parse a card's embalm cost from rules text, if present."""
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        if not text:
            return None

        match = _EMBALM_COST_RE.search(text)
        if not match:
            return None

        cost_str = match.group(1)
        try:
            return ManaCost.parse(cost_str)
        except Exception:
            return None

    def _get_eternalize_cost(self, card) -> Optional[ManaCost]:
        """Parse a card's eternalize cost from rules text, if present."""
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        if not text:
            return None

        match = _ETERNALIZE_COST_RE.search(text)
        if not match:
            return None

        cost_str = match.group(1)
        try:
            return ManaCost.parse(cost_str)
        except Exception:
            return None

    def _get_escape_cost_and_exile_count(self, card) -> tuple[Optional[ManaCost], int]:
        """
        Parse an escape cost and its "exile N cards" requirement from rules text.

        Expected pattern (common reminder text):
          "Escape—{3}{G}{G}, Exile three other cards from your graveyard."
        """
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        if not text:
            return (None, 0)

        match = _ESCAPE_RE.search(text)
        if not match:
            return (None, 0)

        cost_str = match.group(1)
        count_token = match.group(2)
        try:
            cost = ManaCost.parse(cost_str)
        except Exception:
            return (None, 0)

        token = (count_token or "").strip().lower()
        if not token:
            return (cost, 0)

        if token.isdigit():
            return (cost, int(token))

        words = {
            "a": 1,
            "an": 1,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        return (cost, int(words.get(token) or 0))

    def _has_jump_start(self, card) -> bool:
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        return bool(text and _JUMP_START_RE.search(text))

    def _has_retrace(self, card) -> bool:
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        return bool(text and _RETRACE_RE.search(text))

    def _has_delve(self, card) -> bool:
        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""
        return bool(text and _DELVE_RE.search(text))

    def _graveyard_cast_permission_active(self, player_id: str) -> bool:
        perms = getattr(self.state, "cast_from_graveyard_until", {}) or {}
        if player_id not in perms:
            return False
        expires = perms.get(player_id)
        if expires is None:
            return True
        return self.state.turn_number <= int(expires)

    def _graveyard_land_permission_active(self, player_id: str) -> bool:
        perms = getattr(self.state, "play_lands_from_graveyard_until", {}) or {}
        if player_id not in perms:
            return False
        expires = perms.get(player_id)
        if expires is None:
            return True
        return self.state.turn_number <= int(expires)

    def _delve_discount(self, card, player_id: str, cost: ManaCost) -> int:
        """
        Compute the maximum Delve discount available for this cast.

        We only reduce the generic portion of the mana cost and we exclude the
        casting card itself when casting from the graveyard.
        """
        if not self._has_delve(card):
            return 0
        if cost.generic <= 0:
            return 0
        gy = self.state.zones.get(f"graveyard_{player_id}")
        if not gy:
            return 0
        eligible = [cid for cid in gy.objects if cid != getattr(card, "id", None)]
        return min(cost.generic, len(eligible))

    def _reduce_generic_cost(self, cost: ManaCost, reduce_by: int) -> ManaCost:
        if reduce_by <= 0:
            return cost
        return ManaCost(
            white=cost.white,
            blue=cost.blue,
            black=cost.black,
            red=cost.red,
            green=cost.green,
            colorless=cost.colorless,
            generic=max(0, cost.generic - int(reduce_by)),
            snow=cost.snow,
            x_count=cost.x_count,
            hybrid=list(cost.hybrid),
            phyrexian=list(cost.phyrexian),
        )

    def _discarded_this_turn_by(self, card, player_id: str) -> bool:
        """Return True if this card was discarded by player_id during the current turn."""
        st = getattr(card, "state", None)
        if not st:
            return False

        last_turn = getattr(st, "last_discarded_turn", None)
        last_by = getattr(st, "last_discarded_by", None)
        return last_turn == self.state.turn_number and last_by == player_id

    def _get_graveyard_cast_options(self, card, player_id: str) -> list[CastOption]:
        """Return supported ways to cast this card from the graveyard."""
        options: list[CastOption] = []

        # Flashback: cast for flashback cost, then exile it.
        flashback_cost = self._get_flashback_cost(card)
        if flashback_cost is not None:
            options.append(CastOption(
                description_suffix="flashback",
                alt_mana_cost=flashback_cost,
                metadata={"flashback": True, "exile_on_leave_stack": True},
            ))

        # Harmonize: cast for harmonize cost, then exile it.
        harmonize_cost = self._get_harmonize_cost(card)
        if harmonize_cost is not None:
            options.append(CastOption(
                description_suffix="harmonize",
                alt_mana_cost=harmonize_cost,
                metadata={"harmonize": True, "exile_on_leave_stack": True},
            ))

        # Mayhem: cast for mayhem cost if discarded this turn. Does not exile.
        mayhem_cost = self._get_mayhem_cost(card)
        if mayhem_cost is not None and self._discarded_this_turn_by(card, player_id):
            options.append(CastOption(
                description_suffix="mayhem",
                alt_mana_cost=mayhem_cost,
                metadata={"mayhem": True},
            ))

        # Jump-start: cast for printed cost, discard a card, then exile it.
        if self._has_jump_start(card):
            options.append(CastOption(
                description_suffix="jump-start",
                alt_mana_cost=None,
                metadata={"jump_start": True, "exile_on_leave_stack": True},
                additional_cost_plan=(CostStep(kind="discard", amount=1),),
            ))

        # Retrace: cast for printed cost, discard a land card. Does not exile.
        if self._has_retrace(card):
            options.append(CastOption(
                description_suffix="retrace",
                alt_mana_cost=None,
                metadata={"retrace": True},
                additional_cost_plan=(CostStep(kind="discard", amount=1, allowed_types={CardType.LAND}),),
            ))

        # Escape: cast for escape cost, exile N other cards from your graveyard.
        escape_cost, escape_exile = self._get_escape_cost_and_exile_count(card)
        if escape_cost is not None and escape_exile > 0:
            options.append(CastOption(
                description_suffix="escape",
                alt_mana_cost=escape_cost,
                metadata={"escape": True},
                additional_cost_plan=(CostStep(kind="exile_from_graveyard", amount=escape_exile),),
            ))

        # Disturb: cast for disturb cost from graveyard, then exile it.
        disturb_cost = self._get_disturb_cost(card)
        if disturb_cost is not None:
            options.append(CastOption(
                description_suffix="disturb",
                alt_mana_cost=disturb_cost,
                metadata={"disturb": True, "exile_on_leave_stack": True},
            ))

        text = ""
        if getattr(card, "card_def", None) and getattr(card.card_def, "text", None):
            text = card.card_def.text or ""

        # Per-card graveyard permission with extra costs:
        #   "You may cast this card from your graveyard by ... in addition to paying its other costs."
        permission_plan = extract_graveyard_permission_cost_plan(text)
        if permission_plan is not None:
            options.append(CastOption(
                description_suffix="from graveyard",
                alt_mana_cost=None,
                metadata={"from_graveyard_permission": True},
                additional_cost_plan=permission_plan,
            ))

        # Generic unconditional permission (no extra cost).
        # We only support the unconditional form, to avoid incorrectly enabling
        # conditional variants like "Max speed — You may cast this card from your graveyard."
        if text:
            for line in text.splitlines():
                lowered = line.strip().lower()
                if lowered.startswith("you may cast this card from your graveyard."):
                    options.append(CastOption(
                        description_suffix="from graveyard",
                        alt_mana_cost=None,
                        metadata={},
                    ))
                    break

        # Global permission ("You may cast spells from your graveyard this turn").
        if self._graveyard_cast_permission_active(player_id):
            options.append(CastOption(
                description_suffix="from graveyard",
                alt_mana_cost=None,
                metadata={"from_graveyard_global": True},
            ))

        return options

    def _can_cast(self, card, player_id: str, *, cost_override: Optional[ManaCost] = None) -> bool:
        """Check if a player can cast a card (optionally using an alternate cost)."""
        # Check if it's a spell (not a land)
        if CardType.LAND in card.characteristics.types:
            return False

        # Cards without a mana cost cannot be cast (back faces of transform cards, etc.).
        # Exception: alternate costs like flashback can make them castable.
        # Note: {0} is a valid free cost, but "" or None means no mana cost defined.
        mana_cost_str = card.characteristics.mana_cost
        if (cost_override is None) and (not mana_cost_str or mana_cost_str.strip() == ""):
            return False

        # Check timing restrictions
        is_instant = CardType.INSTANT in card.characteristics.types
        has_flash = False  # Would check for flash ability

        if not is_instant and not has_flash:
            # Sorcery speed - can only cast during main phase with empty stack
            if self.turn_manager:
                from .turn import Phase
                if self.turn_manager.phase not in [Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN]:
                    return False

            # Check stack is empty
            if self.stack and not self.stack.is_empty():
                return False

            # Must be active player
            if self.turn_manager and self.turn_manager.active_player != player_id:
                return False

        # Check mana cost. If the caller didn't supply an override, apply any
        # registered cost-reduction interceptors to the printed cost. (When an
        # override IS supplied, callers are expected to have already routed it
        # through get_effective_mana_cost - the legal-action and cast-handler
        # entry points both do.)
        if cost_override is not None:
            cost = cost_override
        else:
            base = ManaCost.parse(mana_cost_str or "")
            cost = get_effective_mana_cost(card, player_id, self.state, base_cost=base)
        if self.mana_system and not cost.is_free():
            if not self.mana_system.can_cast(player_id, cost, for_card=card):
                return False

        return True

    def _can_play_land(self, player_id: str) -> bool:
        """Check if a player can play a land."""
        if self.turn_manager:
            return self.turn_manager.can_play_land(player_id)
        return False

    def _get_activatable_abilities(
        self,
        obj,
        player_id: str
    ) -> list[LegalAction]:
        """
        Get activatable abilities on a permanent.

        Sources of abilities:
        - Phase 4: card-registered ``obj.state.activated_abilities`` (preferred path)
        - Planeswalker loyalty abilities without explicit targets
        - Tap-for-mana abilities from rules text
        """
        actions: list[LegalAction] = []

        # Phase 4: registered activated abilities.
        from .activated import can_pay_activation, get_mirrored_abilities
        from .cost_query import get_effective_activation_cost
        is_active = (
            self.turn_manager is not None
            and self.turn_manager.turn_state.active_player_id == player_id
        )
        is_main = False
        if self.turn_manager is not None:
            from .turn import Phase as _Phase
            is_main = self.turn_manager.turn_state.phase in (
                _Phase.PRECOMBAT_MAIN, _Phase.POSTCOMBAT_MAIN
            )
        stack_empty = (self.stack is None) or (len(self.stack.items) == 0)
        for idx, ability in enumerate(getattr(obj.state, "activated_abilities", []) or []):
            # Apply activated-cost reductions for the legality check. We use
            # x_value=0 here (we don't know the chosen X yet at the legal-
            # actions surface; the player will pick X when they activate).
            effective_cost = None
            if ability.mana_cost is not None:
                try:
                    effective_cost = get_effective_activation_cost(
                        ability, obj, player_id, self.state,
                    )
                except Exception:
                    effective_cost = ability.mana_cost
            if not can_pay_activation(
                ability, obj, self.state, player_id,
                mana_system=self.mana_system,
                is_active_player=is_active,
                is_main_phase=is_main,
                stack_empty=stack_empty,
                effective_mana_cost=effective_cost,
            ):
                continue
            actions.append(LegalAction(
                type=ActionType.ACTIVATE_ABILITY,
                source_id=obj.id,
                ability_id=f"activated:{idx}",
                description=f"Activate {obj.name}: {ability.description}",
                requires_mana=bool(ability.mana_cost and not ability.mana_cost.is_free()),
                mana_cost=effective_cost or ability.mana_cost,
            ))

        # Marvin-style ability mirror: surface activated abilities copied
        # from other creatures (per a card-supplied predicate). The mirrored
        # ability descriptor is a transient view "owned" by ``obj``, so
        # legality applies to ``obj`` (e.g. {T} taps ``obj``, not the source).
        for mirror_view in get_mirrored_abilities(obj, self.state):
            src_obj_id = mirror_view.mirror_source_obj_id
            src_idx = mirror_view.mirror_source_ability_index
            if src_obj_id is None or src_idx is None:
                continue
            effective_cost = None
            if mirror_view.mana_cost is not None:
                try:
                    effective_cost = get_effective_activation_cost(
                        mirror_view, obj, player_id, self.state,
                    )
                except Exception:
                    effective_cost = mirror_view.mana_cost
            if not can_pay_activation(
                mirror_view, obj, self.state, player_id,
                mana_system=self.mana_system,
                is_active_player=is_active,
                is_main_phase=is_main,
                stack_empty=stack_empty,
                effective_mana_cost=effective_cost,
            ):
                continue
            src_obj = self.state.objects.get(src_obj_id)
            src_name = src_obj.name if src_obj is not None else "source"
            actions.append(LegalAction(
                type=ActionType.ACTIVATE_ABILITY,
                source_id=obj.id,
                ability_id=f"mirror:{src_obj_id}:{src_idx}",
                description=(
                    f"Activate {obj.name} (mirror of {src_name}): "
                    f"{mirror_view.description}"
                ),
                requires_mana=bool(
                    mirror_view.mana_cost and not mirror_view.mana_cost.is_free()
                ),
                mana_cost=effective_cost or mirror_view.mana_cost,
            ))

        ability_lines = self._get_activated_ability_lines(obj)

        for idx, line in enumerate(ability_lines):
            normalized = line.replace('−', '-').strip()
            lower = normalized.lower()

            # Planeswalker loyalty abilities: +N: ... / -N: ...
            loyalty_match = re.match(r'^([+-]\d+)\s*:\s*(.+)$', normalized)
            if loyalty_match and CardType.PLANESWALKER in obj.characteristics.types:
                current_turn = self.state.turn_number
                if self._loyalty_activation_turn.get(obj.id) == current_turn:
                    # Planeswalkers can activate loyalty abilities only once each turn.
                    continue

                loyalty_cost = int(loyalty_match.group(1))
                effect_text = loyalty_match.group(2).strip()

                # Only surface non-targeted loyalty abilities for now.
                if 'target' in effect_text.lower():
                    continue

                current_loyalty = self._get_current_loyalty(obj)
                if loyalty_cost < 0 and current_loyalty < abs(loyalty_cost):
                    continue

                actions.append(LegalAction(
                    type=ActionType.ACTIVATE_ABILITY,
                    ability_id=f"loyalty:{idx}:{loyalty_cost}",
                    source_id=obj.id,
                    description=f"Activate {obj.name}: {line}"
                ))
                continue

            # Basic mana abilities from text: "{T}: Add {R}" etc.
            if '{t}' in lower and 'add' in lower:
                if obj.state.tapped:
                    continue
                if CardType.CREATURE in obj.characteristics.types:
                    # Creatures with summoning sickness can't use tap abilities.
                    from .mode_adapter import get_mode_adapter
                    adapter = get_mode_adapter(self.state.game_mode)
                    if adapter.tap_ability_blocked_by_summoning_sickness(obj, self.state):
                        continue

                actions.append(LegalAction(
                    type=ActionType.ACTIVATE_ABILITY,
                    ability_id=f"mana:{idx}",
                    source_id=obj.id,
                    description=f"Activate {obj.name}: {line}"
                ))

        return actions

    def _get_activated_ability_lines(self, obj) -> list[str]:
        """Extract likely activated-ability lines from card rules text."""
        if not obj or not obj.card_def or not obj.card_def.text:
            return []

        lines = []
        for raw_line in obj.card_def.text.splitlines():
            line = raw_line.strip()
            if not line or ':' not in line:
                continue
            if (
                line.startswith('{') or
                line.startswith('+') or
                line.startswith('-') or
                line.startswith('−') or
                '{T}:' in line
            ):
                lines.append(line)
        return lines

    def _get_current_loyalty(self, obj) -> int:
        """Get current loyalty for a planeswalker, with a text fallback."""
        if 'loyalty' in obj.state.counters:
            return obj.state.counters['loyalty']

        text = obj.card_def.text if obj.card_def and obj.card_def.text else ""
        match = re.search(r'\[loyalty:\s*(\d+)\]', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0

    def _parse_mana_symbols(self, ability_text: str) -> list[str]:
        """Parse explicit mana symbols from an activated ability line."""
        if ':' not in ability_text:
            return []
        add_text = ability_text.split(':', 1)[1]
        return re.findall(r'\{([WUBRGC])\}', add_text)

    def _resolve_simple_non_target_ability(
        self,
        ability_text: str,
        source_id: str,
        player_id: str
    ) -> list[Event]:
        """
        Resolve simple non-targeted activated effects from text.

        This intentionally handles only a small safe subset.
        """
        text = ability_text.lower()
        events: list[Event] = []

        # Surveil N
        surveil_match = re.search(r'surveil (\d+)', text)
        if surveil_match:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': player_id, 'amount': int(surveil_match.group(1))},
                source=source_id
            ))

        # Scry N
        scry_match = re.search(r'scry (\d+)', text)
        if scry_match:
            events.append(Event(
                type=EventType.SCRY,
                payload={'player': player_id, 'amount': int(scry_match.group(1))},
                source=source_id
            ))

        # Draw cards
        draw_match = re.search(r'draw (\d+|a|an) cards?', text)
        if draw_match:
            amount_str = draw_match.group(1)
            amount = 1 if amount_str in ('a', 'an') else int(amount_str)
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': player_id, 'count': amount},
                source=source_id
            ))

        return events

    def _get_crew_actions(self, player_id: str, battlefield) -> list[LegalAction]:
        """Get all valid crew actions for Vehicles."""
        from .queries import get_power

        actions = []

        # Find all Vehicles controlled by player
        vehicles = []
        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if (obj and obj.controller == player_id and
                'Vehicle' in obj.characteristics.subtypes and
                CardType.CREATURE not in obj.characteristics.types):  # Not already a creature
                # Parse crew cost from text or abilities
                crew_cost = self._get_crew_cost(obj)
                if crew_cost is not None:
                    vehicles.append((obj, crew_cost))

        if not vehicles:
            return actions

        # Find all untapped creatures that can crew
        available_crew = []
        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if (obj and obj.controller == player_id and
                CardType.CREATURE in obj.characteristics.types and
                not obj.state.tapped):
                power = get_power(obj, self.state)
                available_crew.append((obj, power))

        if not available_crew:
            return actions

        # For each vehicle, check if we have enough power to crew it
        for vehicle, crew_cost in vehicles:
            total_power = sum(p for _, p in available_crew)
            if total_power >= crew_cost:
                # Generate a simple crew option using minimum creatures needed
                crew_with = []
                power_used = 0
                for creature, power in sorted(available_crew, key=lambda x: -x[1]):  # Highest power first
                    if power_used >= crew_cost:
                        break
                    crew_with.append(creature.id)
                    power_used += power

                if power_used >= crew_cost:
                    actions.append(LegalAction(
                        type=ActionType.CREW,
                        card_id=vehicle.id,
                        description=f"Crew {vehicle.name} (power {crew_cost})",
                        crew_cost=crew_cost,
                        crew_with=crew_with
                    ))

        return actions

    def _get_crew_cost(self, vehicle) -> int:
        """Extract crew cost from a Vehicle's text or abilities."""
        # Check text for "Crew N" pattern
        text = getattr(vehicle, 'card_def', None)
        if text and hasattr(text, 'text'):
            text = text.text
        else:
            text = ""

        import re
        match = re.search(r'Crew (\d+)', text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Check abilities
        for ability in vehicle.characteristics.abilities:
            if isinstance(ability, dict):
                keyword = ability.get('keyword', '')
                if keyword.lower().startswith('crew'):
                    # Try to extract number from "Crew 2" format
                    match = re.search(r'crew\s*(\d+)', keyword, re.IGNORECASE)
                    if match:
                        return int(match.group(1))

        # Default crew cost if Vehicle but no explicit cost found
        return 2

    async def _execute_action(self, action: PlayerAction) -> list[Event]:
        """Execute a player action."""
        handler = self._action_handlers.get(action.type)
        if handler:
            events = await handler(action)
            # Emit each event through the pipeline to actually apply changes
            if self.pipeline:
                for event in events:
                    self.pipeline.emit(event)
            return events
        return []

    async def _handle_pass(self, action: PlayerAction) -> list[Event]:
        """Handle passing priority."""
        return []

    async def _handle_cast_spell(self, action: PlayerAction) -> list[Event]:
        """Handle casting a spell."""
        # Keep the handler async for the main priority loop, but implement casting
        # synchronously so PendingChoice handlers (which are sync) can reuse it.
        return self._handle_cast_spell_sync(action)

    def _handle_cast_spell_sync(self, action: PlayerAction) -> list[Event]:
        """
        Synchronous cast implementation.

        Notes:
        - Additional costs may require player choices; in that case, this method
          sets `state.pending_choice` and returns [].
        - This method applies non-mana additional costs by emitting events through
          the pipeline immediately (before moving the spell to the stack).
        """
        if not action.card_id:
            return []

        # Never start resolving a cast while another choice is pending.
        if self.state.pending_choice is not None:
            return []

        card = self.state.objects.get(action.card_id)
        if not card:
            return []

        # Phase 5b: cast-time target picker via PendingChoice. If the card
        # declares ``target_requirements`` and the action didn't pre-supply
        # targets (drag-to-target casts and AI ``_select_targets_for_spell``
        # both pre-supply), emit a PendingChoice and pause the cast. The
        # choice handler re-enters this method with targets filled in.
        #
        # Multi-face support: when the cast action carries a face marker
        # (``action.data['_cast_face']`` set to ``'adventure'`` / ``'left'``
        # / ``'right'`` / ``'back'``), the engine first looks for
        # ``target_requirements`` on the named ``CardFace`` and falls back
        # to the parent CardDefinition if absent. Adventure spell halves
        # currently activate through ACTIVATE_ABILITY (with
        # ``targets_required``/``target_kind`` on the ActivatedAbility), so
        # this face-marker path is forward-compat for routing those
        # through CAST_SPELL. Cast-from-adventure-exile (the main creature/
        # enchantment half) still reads parent CardDefinition.target_requirements
        # because the main face IS the parent definition.
        if not action.targets and card.card_def is not None:
            face_reqs = None
            cast_face_id = action.data.get('_cast_face') if action.data else None
            if cast_face_id:
                face = getattr(card.card_def, cast_face_id, None)
                if face is not None:
                    face_reqs = getattr(face, 'target_requirements', None)
            reqs = face_reqs if face_reqs else getattr(card.card_def, 'target_requirements', None)
            if reqs:
                paused = self._emit_cast_target_choice_with(card, action, reqs)
                if paused is not None:
                    return paused

        # === W7 cast-from-zone (pre zone-check) ===
        # Generic cast-from-zone permission lookup. Runs BEFORE the bespoke
        # graveyard/adventure handling so a card whose only ticket out of a
        # non-HAND zone is a W7 grant still gets a chance to be cast. Bespoke
        # paths (Flashback, Adventure recursion, Warp) take precedence and are
        # consulted in their own branches below; we only set the override when
        # neither of those applies.
        w7_cost_override: Optional[ManaCost] = None
        if (card.zone not in (ZoneType.HAND, ZoneType.STACK)
                and action.ability_id is None
                and not getattr(card.state, 'adventure_exile', False)
                and _w7_is_castable_from_zone(card.id, card.zone, self.state)):
            w7_cost_override = _w7_cast_cost_override_for(card.id, card.zone, self.state)
        # === end W7 ===

        from_graveyard = card.zone == ZoneType.GRAVEYARD

        # WOE Adventure: cast the main half from exile for the printed cost.
        # The card must be flagged ``adventure_exile=True`` (set when the
        # Adventure activation paid its ``Exile this card`` cost) and owned
        # by the casting player.
        from_adventure_exile = (
            card.zone == ZoneType.EXILE
            and getattr(card.state, 'adventure_exile', False)
            and card.owner == action.player_id
            and (action.ability_id == "exile:adventure" or action.ability_id is None)
        )

        # OTJ Plot: cast a previously-plotted card from exile for free on
        # a later turn. The card must have ``state.plotted_turn`` set and
        # be owned by the casting player. ``can_cast_plotted`` already
        # enforces the "later turn" rule and that plot_cast_used is False.
        from .plot_saddle import can_cast_plotted as _can_cast_plotted
        from_plotted_exile = (
            card.zone == ZoneType.EXILE
            and action.ability_id == "exile:plot"
            and card.owner == action.player_id
            and _can_cast_plotted(card, self.state)
        )

        # Choose a single casting option when casting from the graveyard.
        # We still do not expose option selection via the action payload yet,
        # so we pick the first supported option (flashback/harmonize/mayhem/etc.).
        used_flashback = False
        used_harmonize = False
        used_mayhem = False
        used_warp = False
        exile_on_leave_stack = False
        option_plan: Optional[CostPlan] = None

        # === W7 cast-from-zone (graveyard fast path) ===
        # When a W7 grant exists for a graveyard card and no bespoke
        # graveyard option (Flashback/Harmonize/Mayhem/etc.) applies, route
        # through the W7 generic path so the action isn't rejected. Bespoke
        # paths still take precedence when available.
        w7_use_for_graveyard = (
            from_graveyard
            and _w7_is_castable_from_zone(card.id, card.zone, self.state)
            and not self._get_graveyard_cast_options(card, action.player_id)
        )

        if from_graveyard and not w7_use_for_graveyard:
            options = self._get_graveyard_cast_options(card, action.player_id)
            if not options:
                return []

            chosen = None
            if action.ability_id:
                for idx, opt in enumerate(options):
                    if action.ability_id == self._cast_option_ability_id(ZoneType.GRAVEYARD, idx, opt):
                        chosen = opt
                        break
                if chosen is None:
                    # Client asked for an option we don't currently recognize as legal.
                    return []
            else:
                chosen = options[0]
            option_plan = chosen.additional_cost_plan

            used_flashback = bool(chosen.metadata.get("flashback"))
            used_harmonize = bool(chosen.metadata.get("harmonize"))
            used_mayhem = bool(chosen.metadata.get("mayhem"))
            exile_on_leave_stack = bool(chosen.metadata.get("exile_on_leave_stack"))

            paid_cost = chosen.alt_mana_cost or ManaCost.parse(card.characteristics.mana_cost or "")
        elif action.ability_id == "hand:warp" and is_warp_castable_from_hand(card, self.state, action.player_id):
            # EOE Warp: cast from hand for the warp cost. Mark this card as
            # having used its warp; mark the in-flight object so the cast
            # site can register the end-step exile after ETB.
            warp_cost = parse_warp_cost(getattr(getattr(card, "card_def", None), "text", None))
            if warp_cost is None:
                return []
            paid_cost = warp_cost
            used_warp = True
        elif from_adventure_exile:
            # WOE Adventure recursion: pay the printed mana cost. The
            # ``adventure_exile`` flag is cleared once the card actually
            # leaves exile (post stack-push), so an aborted cast leaves
            # the card castable from exile next time.
            paid_cost = ManaCost.parse(card.characteristics.mana_cost or "")
        elif from_plotted_exile:
            # OTJ Plot: cast for free. The ``plot_cast_used`` flag is set
            # after the cast commits (in _continue_cast_spell_with_additional_costs).
            # We flag this cast as a free alt-cost so the upfront affordability
            # check bypasses mana payment (mirrors Discover cast-for-free).
            paid_cost = ManaCost()
            action.data['_alt_cost'] = True
        else:
            # === W7 cast-from-zone (cost selection) ===
            # If a generic cast-from-zone permission applies (and we didn't
            # already use a bespoke alt-cost above), prefer the W7 cost
            # override. Falls back to the printed cost otherwise.
            paid_cost = w7_cost_override if w7_cost_override is not None else \
                ManaCost.parse(card.characteristics.mana_cost or "")

        printed_cost = ManaCost.parse(card.characteristics.mana_cost or "")

        # Apply registered cost-reduction interceptors before delve. We use the
        # already-resolved base (printed cost / flashback cost / warp cost) so
        # alternate casting modes still get reductions applied correctly.
        paid_cost = get_effective_mana_cost(
            card, action.player_id, self.state, base_cost=paid_cost,
        )

        # Delve: automatically apply the maximum generic-cost reduction available
        # for this cast, and pay it by exiling cards from the caster's graveyard.
        delve_exile_count = self._delve_discount(card, action.player_id, paid_cost)
        paid_cost = self._reduce_generic_cost(paid_cost, delve_exile_count)

        # === Spree cost-per-mode (W12) ===
        # OTJ Spree: "Choose one or more additional costs" — each chosen mode
        # adds its own mana cost AND its effect to the spell. We must prompt
        # the caster BEFORE the standard cost plan is built, then add the
        # chosen modes' total surcharge to ``extra_mana`` so it gets paid as
        # part of the cast. The chosen-mode list is stashed on
        # ``state.turn_data`` so the spell's resolve callable can dispatch
        # the right effects when it resolves.
        spree_extra_mana = ManaCost()
        if _spree_is_card(card):
            spree_modes = _spree_get_modes(card)
            cap_min, cap_max = _spree_get_minmax(card)
            recorded = _spree_get_chosen(self.state, card.id)
            if recorded is None:
                # First pass: open the mode prompt. The choice handler will
                # record the selection and re-invoke this method for a second
                # pass; while the prompt is open we return [].
                if self.state.pending_choice is not None:
                    return []
                self_action = action  # captured for closure
                paid_cost_capt = paid_cost  # capture pre-spree base for prompt affordability

                def _on_spree_chosen(indices: list, _state: GameState) -> list[Event]:
                    # Re-enter the cast pipeline now that modes are recorded.
                    return self._handle_cast_spell_sync(self_action)

                events = _spree_open_prompt(
                    obj=card,
                    state=self.state,
                    caster=action.player_id,
                    base_cost=paid_cost_capt,
                    modes=spree_modes,
                    min_modes=cap_min,
                    max_modes=cap_max,
                    on_complete=_on_spree_chosen,
                )
                if events:
                    self._emit_cost_events(events)
                # If no prompt was opened (no affordable mode), the spell is
                # uncastable; otherwise the prompt is now pending.
                return []
            else:
                # Second pass: chosen modes are recorded; compute the
                # combined mode cost and roll into extra_mana.
                spree_extra_mana = _spree_total_extra_cost(spree_modes, recorded)
        # === end Spree ===

        # Build additional cost plan(s).
        std_plan = self._get_standard_additional_cost_plan(card)
        full_plan = self._concat_cost_plans(std_plan, option_plan)

        ctx = CastCostContext(
            state=self.state,
            mana_system=self.mana_system,
            player_id=action.player_id,
            casting_card_id=card.id,
            casting_card_name=card.name,
            casting_zone=card.zone,
            base_mana_cost=paid_cost,
            x_value=action.x_value,
        )

        # === Discover cast-for-free (W11) ===
        # When casting "without paying its mana cost" (action.data['_alt_cost']),
        # bypass the upfront affordability check (additional non-mana costs
        # still apply, but the mana base cost should not block the cast).
        # We swap in a free base_cost just for the precheck; the actual
        # mana skip happens in _continue_cast_spell_with_additional_costs.
        if action.data.get('_alt_cost'):
            free_ctx = CastCostContext(
                state=self.state,
                mana_system=self.mana_system,
                player_id=action.player_id,
                casting_card_id=card.id,
                casting_card_name=card.name,
                casting_zone=card.zone,
                base_mana_cost=ManaCost(),  # free
                x_value=0,
            )
            if not self._can_pay_cost_plan(full_plan, free_ctx, extra_mana=spree_extra_mana):
                return []
        elif not self._can_pay_cost_plan(full_plan, ctx, extra_mana=spree_extra_mana):
            return []
        # === end Discover cast-for-free ===

        return self._continue_cast_spell_with_additional_costs(
            action=action,
            paid_cost=paid_cost,
            printed_cost=printed_cost,
            plan=tuple(full_plan or ()),
            extra_mana=spree_extra_mana,
            from_graveyard=from_graveyard,
            used_flashback=used_flashback,
            used_harmonize=used_harmonize,
            used_mayhem=used_mayhem,
            used_warp=used_warp,
            exile_on_leave_stack=exile_on_leave_stack,
            delve_exile_count=delve_exile_count,
        )

    def _emit_cost_events(self, events: list[Event]) -> None:
        """Emit cost-payment events immediately so later cost steps see updated state."""
        if not events:
            return
        if not self.pipeline:
            return
        for e in events:
            self.pipeline.emit(e)

    def _coerce_selected_ids(self, selected: list[Any]) -> list[str]:
        ids: list[str] = []
        for s in selected or []:
            if isinstance(s, dict):
                sid = s.get("id") or s.get("target_id") or s.get("index")
                if sid is not None:
                    ids.append(str(sid))
            else:
                ids.append(str(s))
        return ids

    def _continue_cast_spell_with_additional_costs(
        self,
        *,
        action: PlayerAction,
        paid_cost: ManaCost,
        printed_cost: ManaCost,
        plan: CostPlan,
        extra_mana: ManaCost,
        from_graveyard: bool,
        used_flashback: bool,
        used_harmonize: bool,
        used_mayhem: bool,
        exile_on_leave_stack: bool,
        delve_exile_count: int = 0,
        used_warp: bool = False,
    ) -> list[Event]:
        """
        Process (and pay) additional costs until either:
        - another player choice is required (pending_choice set, returns []), or
        - costs are fully paid and the spell is put on the stack (returns [CAST]).
        """
        if not action.card_id:
            return []

        card = self.state.objects.get(action.card_id)
        if not card:
            return []

        # Rebuild context each time so eligibility checks see updated state.
        ctx = CastCostContext(
            state=self.state,
            mana_system=self.mana_system,
            player_id=action.player_id,
            casting_card_id=card.id,
            casting_card_name=card.name,
            casting_zone=card.zone,
            base_mana_cost=paid_cost,
            x_value=action.x_value,
        )

        # If all additional costs are done, pay mana and cast.
        if not plan:
            # Delve: pay for {1} per exiled card by exiling from our graveyard.
            # We model this as an automatic maximum reduction (no prompt).
            effective_paid_cost = paid_cost
            if delve_exile_count and delve_exile_count > 0:
                eligible = eligible_graveyard_cards(ctx)
                actual = min(int(delve_exile_count), len(eligible))
                missing = int(delve_exile_count) - actual

                # If we can't exile as many cards as we discounted (because some other
                # cost step already moved cards out of the graveyard), undo the
                # over-discount by adding generic mana back.
                if missing > 0:
                    effective_paid_cost = ManaCost(
                        white=paid_cost.white,
                        blue=paid_cost.blue,
                        black=paid_cost.black,
                        red=paid_cost.red,
                        green=paid_cost.green,
                        colorless=paid_cost.colorless,
                        generic=paid_cost.generic + missing,
                        snow=paid_cost.snow,
                        x_count=paid_cost.x_count,
                        hybrid=list(paid_cost.hybrid),
                        phyrexian=list(paid_cost.phyrexian),
                    )

                to_exile = list(eligible[:actual])
                self._emit_cost_events([
                    Event(
                        type=EventType.EXILE,
                        payload={'object_id': cid},
                        source=action.card_id,
                        controller=action.player_id,
                    )
                    for cid in to_exile
                ])

            total_cost = add_mana_costs(effective_paid_cost, extra_mana)
            # === Discover cast-for-free (W11) ===
            # Discover (CR 702.166) lets the player cast the discovered card
            # "without paying its mana cost". The discover handler routes the
            # cast through this path with action.data['_alt_cost'] set. We
            # skip the mana-payment step and still let the rest of the cast
            # pipeline run (targets, SPELL_CAST, CRIME_COMMITTED, etc.).
            # X-cost spells: when cast for free, X is 0 (CR 107.3f); we honor
            # whatever action.x_value the caller supplies (default 0).
            alt_cost = bool(action.data.get('_alt_cost'))
            if self.mana_system and not total_cost.is_free() and not alt_cost:
                # Pass the card being cast so restricted mana ("Spend this
                # mana only to cast ...") is honoured.
                self.mana_system.pay_cost(
                    action.player_id, total_cost, action.x_value,
                    for_card=card,
                )
            # === end Discover cast-for-free ===

            # BLB Expend tracking: record total mana spent on this cast and
            # fire EXPEND_4/EXPEND_8 threshold events if crossed.
            mv_spent = int(total_cost.mana_value or 0) + int(action.x_value or 0)
            if mv_spent > 0:
                from .blb_mechanics import record_mana_spent_for_expend
                expend_events = record_mana_spent_for_expend(
                    self.state, action.player_id, mv_spent, source_id=action.card_id,
                )
                if expend_events and self.pipeline:
                    for ev in expend_events:
                        self.pipeline.emit(ev)

            # WOE Adventure recursion: clear the cast-from-exile flag now that
            # we're committed to moving the card from exile to the stack. This
            # ensures an aborted cast (rare path) leaves the card still flagged.
            if card.zone == ZoneType.EXILE and getattr(card.state, 'adventure_exile', False):
                card.state.adventure_exile = False

            # OTJ Plot: mark the plotted cast as consumed so the card can't
            # be cast for free a second time. ``plotted_turn`` is cleared
            # too so ``can_cast_plotted`` returns False on subsequent passes.
            # We do this once we're committed to the cast (mirrors the
            # Adventure flag-clear above). Only triggers when this cast is
            # specifically the plotted-cast ability (``exile:plot``).
            if (card.zone == ZoneType.EXILE
                    and action.ability_id == "exile:plot"
                    and getattr(card.state, 'plotted_turn', None) is not None
                    and not getattr(card.state, 'plot_cast_used', False)):
                card.state.plot_cast_used = True
                card.state.plotted_turn = None

            stack_item_id_for_conspire: Optional[str] = None
            if self.stack:
                from .stack import SpellBuilder
                builder = SpellBuilder(self.state, self.stack)
                item = builder.cast_spell(
                    card_id=action.card_id,
                    controller_id=action.player_id,
                    targets=action.targets,
                    x_value=action.x_value,
                    modes=action.modes,
                    additional_data={
                        'from_graveyard': from_graveyard,
                        'flashback': used_flashback,
                        'harmonize': used_harmonize,
                        'mayhem': used_mayhem,
                        'warp': used_warp,
                        'exile_on_leave_stack': exile_on_leave_stack,
                    }
                )
                self.stack.push(item)
                stack_item_id_for_conspire = item.id

            # === Conspire (W29) ===
            # CR 702.78: "As you cast a noncreature spell, you may tap two
            # untapped creatures you control that share a color with it.
            # When you do, copy that spell." We open the optional conspire
            # prompt now (the spell is on the stack and we know its stack
            # item id). If no human handler is attached or there are no two
            # color-sharing creatures, the helper auto-declines (no prompt
            # opens), so legacy tests aren't affected. The choice handler
            # (when accepted) emits TAP, CONSPIRE_TRIGGERED, and
            # COPY_STACK_ITEM events through ``submit_choice``'s normal
            # event-emission path.
            if (stack_item_id_for_conspire is not None
                    and not _conspire_is_handled(self.state, action.card_id)):
                grants = _conspire_find_grants(
                    self.state, action.player_id, card,
                )
                if grants:
                    _conspire_mark_handled(self.state, action.card_id)
                    _conspire_open_prompt(
                        state=self.state,
                        spell_obj=card,
                        spell_stack_item_id=stack_item_id_for_conspire,
                        caster=action.player_id,
                        grant=grants[0],
                    )
            # === end Conspire ===

            # Ward / TARGET_CHOSEN: now that the spell's chosen targets are
            # committed to a stack item, fire one TARGET_CHOSEN per (spell,
            # target) pair so static abilities like Ward can react. We do this
            # here (instead of stack.push) so we don't double-fire when the
            # same item is pushed via multiple paths in tests.
            target_chosen_events = build_target_chosen_events(
                spell_id=action.card_id,
                controller_id=action.player_id,
                targets=action.targets,
            )

            # === Crime tracking (OTJ) ===
            # CR 701.55: a player commits a crime as they cast a spell that
            # targets opponents / opp's permanents / opp's GY cards. Detect
            # and emit CRIME_COMMITTED for any pre-chosen targets on this
            # cast; choices made via PendingChoice are detected in
            # ``Game.submit_choice`` instead.
            from .crime import check_cast_targets_for_crime
            crime_events = check_cast_targets_for_crime(
                controller_id=action.player_id,
                targets=action.targets,
                state=self.state,
                source_id=action.card_id,
            )

            # EOE Warp: mark the in-flight object so end-step exile is
            # registered after ETB, and mark the card definition as having
            # used its warp cast (one warp per card per game).
            extra_events: list[Event] = []
            if used_warp:
                mark_warp_cast(card)
                if getattr(card, "card_def", None) is not None:
                    mark_warp_used(card.card_def)
                # Schedule the end-step exile interceptor immediately. The
                # interceptor itself only triggers an exile if the object is
                # on the battlefield at the next end step, so it's safe to
                # register now even though the spell is currently on the
                # stack.
                schedule_warp_exile_for_object(self.state, card, action.player_id)
                extra_events.append(Event(
                    type=EventType.WARP_CAST,
                    payload={
                        'card_id': action.card_id,
                        'controller': action.player_id,
                        'warp_cost': paid_cost.to_string(),
                    },
                    source=action.card_id,
                    controller=action.player_id,
                ))
                extra_events.append(Event(
                    type=EventType.WARP_EXILE_SCHEDULED,
                    payload={
                        'object_id': action.card_id,
                        'controller': action.player_id,
                    },
                    source=action.card_id,
                    controller=action.player_id,
                ))

            return crime_events + [Event(
                type=EventType.CAST,
                payload={
                    # Canonical spell-cast payload (used by spell-cast triggers).
                    'spell_id': action.card_id,
                    'card_id': action.card_id,
                    'caster': action.player_id,
                    'controller': action.player_id,
                    'types': list(card.characteristics.types),
                    'colors': list(card.characteristics.colors),
                    'mana_value': printed_cost.mana_value,
                    'from_graveyard': from_graveyard,
                    'flashback': used_flashback,
                    'harmonize': used_harmonize,
                    'mayhem': used_mayhem,
                    'warp': used_warp,
                },
                source=action.card_id,
                controller=action.player_id,
            )] + extra_events + target_chosen_events

        step = plan[0]
        rest = plan[1:]

        # Deterministic cost steps: apply immediately and continue.
        if step.kind == "pay_life":
            self._emit_cost_events([
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': action.player_id, 'amount': -step.amount},
                    source=action.card_id,
                    controller=action.player_id,
                )
            ])
            return self._continue_cast_spell_with_additional_costs(
                action=action,
                paid_cost=paid_cost,
                printed_cost=printed_cost,
                plan=rest,
                extra_mana=extra_mana,
                from_graveyard=from_graveyard,
                used_flashback=used_flashback,
                used_harmonize=used_harmonize,
                used_mayhem=used_mayhem,
                exile_on_leave_stack=exile_on_leave_stack,
                delve_exile_count=delve_exile_count,
                used_warp=used_warp,
            )

        if step.kind == "add_mana":
            return self._continue_cast_spell_with_additional_costs(
                action=action,
                paid_cost=paid_cost,
                printed_cost=printed_cost,
                plan=rest,
                extra_mana=add_mana_costs(extra_mana, step.mana_cost or ManaCost()),
                from_graveyard=from_graveyard,
                used_flashback=used_flashback,
                used_harmonize=used_harmonize,
                used_mayhem=used_mayhem,
                exile_on_leave_stack=exile_on_leave_stack,
                delve_exile_count=delve_exile_count,
                used_warp=used_warp,
            )

        # OR choice: pick if forced, otherwise prompt.
        if step.kind == "or":
            options = list(step.options or ())
            if not options:
                return []

            payable: list[tuple[int, CostPlan]] = []
            for idx, opt in enumerate(options):
                combined = tuple(opt) + tuple(rest)
                if self._can_pay_cost_plan(combined, ctx, extra_mana):
                    payable.append((idx, opt))

            if not payable:
                return []

            if len(payable) == 1:
                chosen_plan = tuple(payable[0][1]) + tuple(rest)
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=chosen_plan,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            # Prompt the player to choose which additional cost path to take.
            opt_entries = [
                {'id': str(idx), 'label': describe_plan(opt_plan)}
                for idx, opt_plan in payable
            ]

            def _on_choose_or(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
                picked_ids = self._coerce_selected_ids(selected)
                if not picked_ids:
                    return []
                picked = picked_ids[0]
                chosen = None
                for idx, opt_plan in payable:
                    if str(idx) == str(picked):
                        chosen = opt_plan
                        break
                if chosen is None:
                    return []
                new_plan = tuple(chosen) + tuple(rest)
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=new_plan,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            self.state.pending_choice = PendingChoice(
                choice_type="additional_cost_or",
                player=action.player_id,
                prompt=f"Choose an additional cost to cast {card.name}",
                options=opt_entries,
                source_id=action.card_id,
                min_choices=1,
                max_choices=1,
                callback_data={'handler': _on_choose_or},
            )
            return []

        # Choice steps.
        if step.kind == "discard":
            options = eligible_hand_cards(ctx, step.allowed_types)
            if len(options) < step.amount:
                return []

            def _on_discard(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
                picked = self._coerce_selected_ids(selected)
                if len(picked) != step.amount:
                    return []
                self._emit_cost_events([
                    Event(
                        type=EventType.DISCARD,
                        payload={'player': action.player_id, 'object_id': cid},
                        source=action.card_id,
                        controller=action.player_id,
                    )
                    for cid in picked
                ])
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=rest,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            self.state.pending_choice = PendingChoice(
                choice_type="discard",
                player=action.player_id,
                prompt=f"Additional cost: discard {step.amount} card(s) to cast {card.name}",
                options=options,
                source_id=action.card_id,
                min_choices=step.amount,
                max_choices=step.amount,
                callback_data={'handler': _on_discard},
            )
            return []

        if step.kind == "sacrifice":
            options = eligible_battlefield_permanents(ctx, step.allowed_types)
            if len(options) < step.amount:
                return []

            def _on_sacrifice(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
                picked = self._coerce_selected_ids(selected)
                if len(picked) != step.amount:
                    return []
                self._emit_cost_events([
                    Event(
                        type=EventType.SACRIFICE,
                        payload={'player': action.player_id, 'object_id': oid},
                        source=action.card_id,
                        controller=action.player_id,
                    )
                    for oid in picked
                ])
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=rest,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            self.state.pending_choice = PendingChoice(
                choice_type="sacrifice",
                player=action.player_id,
                prompt=f"Additional cost: sacrifice {step.amount} permanent(s) to cast {card.name}",
                options=options,
                source_id=action.card_id,
                min_choices=step.amount,
                max_choices=step.amount,
                callback_data={'handler': _on_sacrifice},
            )
            return []

        if step.kind == "tap":
            options = eligible_battlefield_permanents(ctx, step.allowed_types, must_be_untapped=True)
            if len(options) < step.amount:
                return []

            def _on_tap(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
                picked = self._coerce_selected_ids(selected)
                if len(picked) != step.amount:
                    return []
                self._emit_cost_events([
                    Event(
                        type=EventType.TAP,
                        payload={'object_id': oid},
                        source=action.card_id,
                        controller=action.player_id,
                    )
                    for oid in picked
                ])
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=rest,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            self.state.pending_choice = PendingChoice(
                choice_type="tap",
                player=action.player_id,
                prompt=f"Additional cost: tap {step.amount} permanent(s) to cast {card.name}",
                options=options,
                source_id=action.card_id,
                min_choices=step.amount,
                max_choices=step.amount,
                callback_data={'handler': _on_tap},
            )
            return []

        if step.kind == "exile_from_graveyard":
            options = eligible_graveyard_cards(ctx)
            if len(options) < step.amount:
                return []

            def _on_exile(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
                picked = self._coerce_selected_ids(selected)
                if len(picked) != step.amount:
                    return []
                self._emit_cost_events([
                    Event(
                        type=EventType.EXILE,
                        payload={'object_id': cid},
                        source=action.card_id,
                        controller=action.player_id,
                    )
                    for cid in picked
                ])
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=rest,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            self.state.pending_choice = PendingChoice(
                choice_type="exile_from_graveyard",
                player=action.player_id,
                prompt=f"Additional cost: exile {step.amount} card(s) from your graveyard to cast {card.name}",
                options=options,
                source_id=action.card_id,
                min_choices=step.amount,
                max_choices=step.amount,
                callback_data={'handler': _on_exile},
            )
            return []

        if step.kind == "return_to_hand":
            options = eligible_battlefield_permanents(ctx)
            if len(options) < step.amount:
                return []

            def _on_return(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
                picked = self._coerce_selected_ids(selected)
                if len(picked) != step.amount:
                    return []
                self._emit_cost_events([
                    Event(
                        type=EventType.BOUNCE,
                        payload={'object_id': oid},
                        source=action.card_id,
                        controller=action.player_id,
                    )
                    for oid in picked
                ])
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=rest,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            self.state.pending_choice = PendingChoice(
                choice_type="return_to_hand",
                player=action.player_id,
                prompt=f"Additional cost: return {step.amount} permanent(s) you control to its owner's hand to cast {card.name}",
                options=options,
                source_id=action.card_id,
                min_choices=step.amount,
                max_choices=step.amount,
                callback_data={'handler': _on_return},
            )
            return []

        if step.kind == "exile_you_control":
            options = eligible_battlefield_permanents(ctx, step.allowed_types)
            if len(options) < step.amount:
                return []

            def _on_exile_control(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
                picked = self._coerce_selected_ids(selected)
                if len(picked) != step.amount:
                    return []
                self._emit_cost_events([
                    Event(
                        type=EventType.EXILE,
                        payload={'object_id': oid},
                        source=action.card_id,
                        controller=action.player_id,
                    )
                    for oid in picked
                ])
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=rest,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            self.state.pending_choice = PendingChoice(
                choice_type="exile_you_control",
                player=action.player_id,
                prompt=f"Additional cost: exile {step.amount} permanent(s) you control to cast {card.name}",
                options=options,
                source_id=action.card_id,
                min_choices=step.amount,
                max_choices=step.amount,
                callback_data={'handler': _on_exile_control},
            )
            return []

        if step.kind == "remove_counters":
            totals = total_counters_on_creatures_you_control(ctx)
            options = []
            for oid, total in totals.items():
                obj = self.state.objects.get(oid)
                if not obj:
                    continue
                options.append({'id': oid, 'name': obj.name, 'type': 'creature', 'total_counters': total})

            if sum(totals.values()) < step.amount or not options:
                return []

            def _validate_remove(choice: PendingChoice, selected_allocs: list[Any]) -> tuple[bool, str]:
                # selected_allocs is a list of {target_id, amount} dicts from the UI.
                allocations = {}
                for item in selected_allocs or []:
                    if isinstance(item, dict):
                        tid = item.get('target_id') or item.get('id')
                        amt = int(item.get('amount', 0))
                        if tid:
                            allocations[str(tid)] = amt

                for tid, amt in allocations.items():
                    if amt < 1:
                        return False, "Each selected creature must have at least 1 counter removed"
                    if amt > int(totals.get(tid, 0)):
                        return False, "Cannot remove more counters than a creature has"
                return True, ""

            def _on_remove(choice: PendingChoice, allocations: dict, state: GameState) -> list[Event]:
                # allocations: dict[target_id -> amount]
                cost_events: list[Event] = []
                for oid, amt in (allocations or {}).items():
                    obj = state.objects.get(oid)
                    if not obj:
                        continue
                    remaining = int(amt)
                    # Remove from +1/+1 first, then other counters deterministically.
                    counter_types = list((obj.state.counters or {}).keys())
                    ordered_types = []
                    if '+1/+1' in counter_types:
                        ordered_types.append('+1/+1')
                    for ct in sorted(counter_types):
                        if ct != '+1/+1':
                            ordered_types.append(ct)

                    for ct in ordered_types:
                        if remaining <= 0:
                            break
                        current = int((obj.state.counters or {}).get(ct, 0) or 0)
                        if current <= 0:
                            continue
                        take = min(current, remaining)
                        remaining -= take
                        cost_events.append(Event(
                            type=EventType.COUNTER_REMOVED,
                            payload={'object_id': oid, 'counter_type': ct, 'amount': take},
                            source=action.card_id,
                            controller=action.player_id,
                        ))

                self._emit_cost_events(cost_events)
                return self._continue_cast_spell_with_additional_costs(
                    action=action,
                    paid_cost=paid_cost,
                    printed_cost=printed_cost,
                    plan=rest,
                    extra_mana=extra_mana,
                    from_graveyard=from_graveyard,
                    used_flashback=used_flashback,
                    used_harmonize=used_harmonize,
                    used_mayhem=used_mayhem,
                    exile_on_leave_stack=exile_on_leave_stack,
                    delve_exile_count=delve_exile_count,
                    used_warp=used_warp,
                )

            self.state.pending_choice = PendingChoice(
                choice_type="divide_allocation",
                player=action.player_id,
                prompt=f"Remove {step.amount} counter(s) from among creatures you control to cast {card.name}",
                options=options,
                source_id=action.card_id,
                min_choices=1,
                max_choices=len(options),
                callback_data={
                    'handler': _on_remove,
                    'validator': _validate_remove,
                    'total_amount': step.amount,
                    'effect': 'counters',
                }
            )
            return []

        # Unknown cost kind: stop (don't cast).
        return []

    async def _handle_activate_ability(self, action: PlayerAction) -> list[Event]:
        """Handle activating an ability."""
        events = []
        pushed_stack_item = False
        source = self.state.objects.get(action.source_id) if action.source_id else None

        if source and action.ability_id:
            # Phase 4: registered activated abilities (cards/interceptor_helpers.make_activated_ability).
            if action.ability_id.startswith("activated:"):
                return self._handle_activate_registered_ability_sync(action, source)

            # Marvin-style mirror dispatch: ability_id is
            # ``mirror:<source_obj_id>:<source_ability_index>``. The
            # mirrored ability descriptor is a transient view "owned" by
            # ``source`` (the mimic), so cost-pay applies to ``source``
            # (Marvin taps itself, etc.). The effect_fn closure is the
            # original from the source creature, but it is invoked with
            # ``source`` as the GameObject — Marvin's id, not the source's.
            if action.ability_id.startswith("mirror:"):
                from .activated import (
                    can_pay_activation,
                    pay_activation_cost,
                    record_activation,
                    find_mirrored_ability,
                )
                from .cost_query import get_effective_activation_cost
                parts = action.ability_id.split(":")
                if len(parts) != 3:
                    return []
                _, src_obj_id, src_idx_str = parts
                try:
                    src_idx = int(src_idx_str)
                except ValueError:
                    return []
                mirror_view = find_mirrored_ability(
                    source, self.state, src_obj_id, src_idx
                )
                if mirror_view is None:
                    return []
                _is_active = (
                    self.turn_manager is not None
                    and self.turn_manager.turn_state.active_player_id == action.player_id
                )
                _is_main = False
                if self.turn_manager is not None:
                    from .turn import Phase as _Phase
                    _is_main = self.turn_manager.turn_state.phase in (
                        _Phase.PRECOMBAT_MAIN, _Phase.POSTCOMBAT_MAIN
                    )
                _stack_empty = (self.stack is None) or (len(self.stack.items) == 0)
                _x = int(getattr(action, 'x_value', 0) or 0)
                _effective_cost = None
                if mirror_view.mana_cost is not None:
                    try:
                        _effective_cost = get_effective_activation_cost(
                            mirror_view, source, action.player_id, self.state,
                        )
                    except Exception:
                        _effective_cost = mirror_view.mana_cost
                # Legality applies to the *mimic* (source) — its tap state,
                # its summoning sickness, its counters, its mana.
                if not can_pay_activation(
                    mirror_view, source, self.state, action.player_id,
                    mana_system=self.mana_system,
                    is_active_player=_is_active,
                    is_main_phase=_is_main,
                    stack_empty=_stack_empty,
                    x_value=_x,
                    effective_mana_cost=_effective_cost,
                ):
                    return []
                # Cost-pay applies to ``source`` (Marvin taps itself; if the
                # mirrored cost says "sacrifice this", Marvin gets sac'd).
                events.extend(pay_activation_cost(
                    mirror_view, source, self.state, action.player_id,
                    mana_system=self.mana_system,
                    x_value=_x,
                    effective_mana_cost=_effective_cost,
                ))
                _src_id = source.id
                _effect_fn = mirror_view.effect_fn
                try:
                    _sig = inspect.signature(_effect_fn)
                    _accepts_x = (
                        'x_value' in _sig.parameters
                        or any(
                            p.kind == inspect.Parameter.VAR_KEYWORD
                            for p in _sig.parameters.values()
                        )
                    )
                except (TypeError, ValueError):
                    _accepts_x = False

                def _resolve_mirror(targets, st: GameState) -> list[Event]:
                    # Crucial: the mimic is the GameObject passed to the
                    # effect_fn so the effect's "this creature" references
                    # resolve to the mimic (Marvin), per CR 706: copied
                    # abilities use the new object as their source.
                    obj = st.objects.get(_src_id)
                    if obj is None:
                        return []
                    flat: list = []
                    for group in (targets or []):
                        if isinstance(group, list):
                            flat.extend(group)
                        else:
                            flat.append(group)
                    try:
                        if _accepts_x:
                            return list(_effect_fn(obj, st, flat, x_value=_x) or [])
                        return list(_effect_fn(obj, st, flat) or [])
                    except Exception:
                        return []

                if self.stack:
                    self.stack.push(StackItem(
                        id="",
                        type=StackItemType.ACTIVATED_ABILITY,
                        source_id=source.id,
                        controller_id=action.player_id,
                        chosen_targets=action.targets,
                        resolve_fn=_resolve_mirror,
                    ))
                    pushed_stack_item = True
                # Record activation on BOTH descriptors:
                # - the mimic's view tracks once-per-turn from Marvin's
                #   perspective (mirror_view is transient but we update the
                #   source descriptor below, so for now record there);
                # - the *source* descriptor's counter is also bumped so the
                #   source's own activation of the same ability still
                #   respects once-per-turn (rare but possible).
                src_obj = self.state.objects.get(src_obj_id)
                if src_obj is not None:
                    src_abilities = getattr(src_obj.state, "activated_abilities", []) or []
                    if 0 <= src_idx < len(src_abilities):
                        record_activation(src_abilities[src_idx], self.state)
                from .crime import check_cast_targets_for_crime as _ccfc
                _crime_events = _ccfc(
                    controller_id=action.player_id,
                    targets=action.targets,
                    state=self.state,
                    source_id=action.source_id,
                )
                events.extend(_crime_events)
                events.append(Event(
                    type=EventType.ACTIVATE,
                    payload={
                        'source_id': action.source_id,
                        'ability_id': action.ability_id,
                        'controller': action.player_id,
                        'is_exhaust': bool(getattr(mirror_view, 'is_exhaust', False)),
                        'x_value': _x,
                        'is_mirror': True,
                        'mirror_source_id': src_obj_id,
                        'mirror_source_ability_index': src_idx,
                    },
                ))
                if pushed_stack_item and action.targets:
                    events.extend(build_target_chosen_events(
                        action.source_id, action.player_id, action.targets,
                    ))
                return events

            # Graveyard activated abilities (Unearth/Embalm/Eternalize).
            if action.ability_id.startswith("graveyard:") and self.stack:
                kind = action.ability_id.split(":", 1)[1]

                # Only the card's owner can activate its graveyard keyword abilities.
                if source.owner != action.player_id:
                    return []

                if source.zone != ZoneType.GRAVEYARD:
                    return []

                def _push_ability(resolve_fn) -> None:
                    nonlocal pushed_stack_item
                    item = StackItem(
                        id="",
                        type=StackItemType.ACTIVATED_ABILITY,
                        source_id=source.id,
                        controller_id=action.player_id,
                        chosen_targets=action.targets,
                        resolve_fn=resolve_fn,
                    )
                    self.stack.push(item)
                    pushed_stack_item = True

                if kind == "unearth":
                    cost = self._get_unearth_cost(source)
                    if cost is None:
                        return []
                    if not self._can_cast(source, action.player_id, cost_override=cost):
                        return []
                    if self.mana_system and not cost.is_free():
                        self.mana_system.pay_cost(action.player_id, cost, 0)

                    def _resolve_unearth(_targets, st: GameState) -> list[Event]:
                        obj = st.objects.get(source.id)
                        if not obj or obj.zone != ZoneType.GRAVEYARD:
                            return []

                        # Mark replacement state: if it would leave the battlefield, exile it instead.
                        setattr(obj.state, "_exile_on_leave_battlefield", True)
                        setattr(obj.state, "_unearth_active", True)

                        # One-shot delayed exile at the next end step.
                        int_id = new_id()

                        def _end_step_filter(e: Event, s: GameState) -> bool:
                            return e.type == EventType.PHASE_START and e.payload.get("phase") == "end_step"

                        def _end_step_handler(e: Event, s: GameState) -> InterceptorResult:
                            current = s.objects.get(obj.id)
                            if not current or current.zone != ZoneType.BATTLEFIELD:
                                return InterceptorResult(action=InterceptorAction.PASS)
                            return InterceptorResult(
                                action=InterceptorAction.REACT,
                                new_events=[
                                    Event(
                                        type=EventType.EXILE,
                                        payload={"object_id": current.id},
                                        source=obj.id,
                                        controller=action.player_id,
                                    )
                                ],
                            )

                        interceptor = Interceptor(
                            id=int_id,
                            source=obj.id,
                            controller=action.player_id,
                            priority=InterceptorPriority.REACT,
                            filter=_end_step_filter,
                            handler=_end_step_handler,
                            duration="forever",
                            uses_remaining=1,
                        )
                        interceptor.timestamp = st.next_timestamp()
                        st.interceptors[interceptor.id] = interceptor
                        if interceptor.id not in obj.interceptor_ids:
                            obj.interceptor_ids.append(interceptor.id)

                        return [
                            Event(
                                type=EventType.ZONE_CHANGE,
                                payload={
                                    "object_id": obj.id,
                                    "from_zone_type": ZoneType.GRAVEYARD,
                                    "to_zone": "battlefield",
                                    "to_zone_type": ZoneType.BATTLEFIELD,
                                },
                                source=obj.id,
                                controller=action.player_id,
                            ),
                            Event(
                                type=EventType.GRANT_KEYWORD,
                                payload={
                                    "object_id": obj.id,
                                    "keyword": "haste",
                                    "duration": "end_of_turn",
                                },
                                source=obj.id,
                                controller=action.player_id,
                            ),
                        ]

                    _push_ability(_resolve_unearth)

                elif kind == "embalm":
                    cost = self._get_embalm_cost(source)
                    if cost is None:
                        return []
                    if not self._can_cast(source, action.player_id, cost_override=cost):
                        return []
                    if self.mana_system and not cost.is_free():
                        self.mana_system.pay_cost(action.player_id, cost, 0)

                    # Snapshot printed characteristics before we exile the card.
                    snap = {
                        "name": source.name,
                        "types": set(source.characteristics.types),
                        "subtypes": set(source.characteristics.subtypes),
                        "supertypes": set(source.characteristics.supertypes),
                        "power": source.characteristics.power,
                        "toughness": source.characteristics.toughness,
                        "abilities": list(source.characteristics.abilities or []),
                    }

                    # Exile the card as part of the activation cost.
                    events.append(Event(
                        type=EventType.EXILE,
                        payload={"object_id": source.id},
                        source=source.id,
                        controller=action.player_id,
                    ))

                    def _resolve_embalm(_targets, st: GameState) -> list[Event]:
                        # Create the token copy (simplified).
                        types = set(snap["types"]) | {CardType.CREATURE}
                        subtypes = set(snap["subtypes"]) | {"Zombie"}
                        return [
                            Event(
                                type=EventType.OBJECT_CREATED,
                                payload={
                                    "name": snap["name"],
                                    "controller": action.player_id,
                                    "owner": action.player_id,
                                    "to_zone_type": ZoneType.BATTLEFIELD,
                                    "types": types,
                                    "subtypes": subtypes,
                                    "supertypes": set(snap["supertypes"]),
                                    "colors": {Color.WHITE},
                                    "power": snap["power"],
                                    "toughness": snap["toughness"],
                                    "abilities": list(snap["abilities"]),
                                    "is_token": True,
                                },
                                source=source.id,
                                controller=action.player_id,
                            )
                        ]

                    _push_ability(_resolve_embalm)

                elif kind == "eternalize":
                    cost = self._get_eternalize_cost(source)
                    if cost is None:
                        return []
                    if not self._can_cast(source, action.player_id, cost_override=cost):
                        return []
                    if self.mana_system and not cost.is_free():
                        self.mana_system.pay_cost(action.player_id, cost, 0)

                    snap = {
                        "name": source.name,
                        "types": set(source.characteristics.types),
                        "subtypes": set(source.characteristics.subtypes),
                        "supertypes": set(source.characteristics.supertypes),
                        "abilities": list(source.characteristics.abilities or []),
                    }

                    events.append(Event(
                        type=EventType.EXILE,
                        payload={"object_id": source.id},
                        source=source.id,
                        controller=action.player_id,
                    ))

                    def _resolve_eternalize(_targets, st: GameState) -> list[Event]:
                        types = set(snap["types"]) | {CardType.CREATURE}
                        subtypes = set(snap["subtypes"]) | {"Zombie"}
                        return [
                            Event(
                                type=EventType.OBJECT_CREATED,
                                payload={
                                    "name": snap["name"],
                                    "controller": action.player_id,
                                    "owner": action.player_id,
                                    "to_zone_type": ZoneType.BATTLEFIELD,
                                    "types": types,
                                    "subtypes": subtypes,
                                    "supertypes": set(snap["supertypes"]),
                                    "colors": {Color.BLACK},
                                    "power": 4,
                                    "toughness": 4,
                                    "abilities": list(snap["abilities"]),
                                    "is_token": True,
                                },
                                source=source.id,
                                controller=action.player_id,
                            )
                        ]

                    _push_ability(_resolve_eternalize)

                else:
                    return []

            # Loyalty ability path.
            if action.ability_id.startswith("loyalty:"):
                parts = action.ability_id.split(":")
                if len(parts) >= 3:
                    try:
                        current_turn = self.state.turn_number
                        if self._loyalty_activation_turn.get(source.id) == current_turn:
                            # Enforce one loyalty activation per permanent per turn.
                            return []

                        line_idx = int(parts[1])
                        loyalty_delta = int(parts[2])
                        lines = self._get_activated_ability_lines(source)
                        ability_line = lines[line_idx] if 0 <= line_idx < len(lines) else ""
                        effect_text = ability_line.split(":", 1)[1].strip() if ":" in ability_line else ""

                        current = self._get_current_loyalty(source)
                        source.state.counters['loyalty'] = current + loyalty_delta

                        if loyalty_delta >= 0:
                            events.append(Event(
                                type=EventType.COUNTER_ADDED,
                                payload={
                                    'object_id': source.id,
                                    'counter_type': 'loyalty',
                                    'amount': loyalty_delta
                                },
                                source=source.id
                            ))
                        else:
                            events.append(Event(
                                type=EventType.COUNTER_REMOVED,
                                payload={
                                    'object_id': source.id,
                                    'counter_type': 'loyalty',
                                    'amount': abs(loyalty_delta)
                                },
                                source=source.id
                            ))

                        # Resolve a safe subset of non-targeted loyalty effects.
                        if effect_text and "target" not in effect_text.lower():
                            events.extend(self._resolve_simple_non_target_ability(
                                ability_text=effect_text,
                                source_id=source.id,
                                player_id=action.player_id
                            ))

                        # Record turn after successful loyalty activation.
                        self._loyalty_activation_turn[source.id] = current_turn
                    except ValueError:
                        pass

            # Basic mana ability path.
            elif action.ability_id.startswith("mana:"):
                parts = action.ability_id.split(":")
                if len(parts) >= 2:
                    try:
                        line_idx = int(parts[1])
                        lines = self._get_activated_ability_lines(source)
                        ability_line = lines[line_idx] if 0 <= line_idx < len(lines) else ""

                        # Detect "Spend this mana only to ..." spell-cast
                        # restrictions on this specific ability line. We
                        # also fall back to the full card text if the line
                        # doesn't contain the clause directly (some printings
                        # put the restriction in a separate sentence).
                        from .mana import parse_spend_restriction
                        restriction_info = parse_spend_restriction(ability_line)
                        if restriction_info is None:
                            full_text = (source.card_def.text if getattr(source, "card_def", None) else "") or ""
                            # Only apply card-text-level restriction if the
                            # card has exactly one mana ability — otherwise
                            # we can't tell which ability it pertains to.
                            mana_lines = [
                                ln for ln in lines
                                if re.search(r'\{T\}\s*:\s*Add\b', ln, re.IGNORECASE)
                                or re.search(r':\s*Add\b', ln, re.IGNORECASE)
                            ]
                            if len(mana_lines) == 1:
                                restriction_info = parse_spend_restriction(full_text)
                        restriction_fn = restriction_info[0] if restriction_info else None
                        restriction_text = restriction_info[1] if restriction_info else ""

                        if '{T}' in ability_line and not source.state.tapped:
                            events.append(Event(
                                type=EventType.TAP,
                                payload={'object_id': source.id},
                                source=source.id,
                                controller=action.player_id
                            ))

                        mana_symbols = self._parse_mana_symbols(ability_line)
                        symbol_to_type = {
                            'W': ManaType.WHITE,
                            'U': ManaType.BLUE,
                            'B': ManaType.BLACK,
                            'R': ManaType.RED,
                            'G': ManaType.GREEN,
                            'C': ManaType.COLORLESS,
                        }
                        produced_any = False
                        for symbol in mana_symbols:
                            mana_type = symbol_to_type.get(symbol)
                            if mana_type and self.mana_system:
                                self.mana_system.produce_mana(
                                    action.player_id, mana_type, 1,
                                    source_id=source.id,
                                    restriction=restriction_fn,
                                    restriction_text=restriction_text,
                                )
                                payload = {
                                    'player': action.player_id,
                                    'color': mana_type.value,
                                    'amount': 1,
                                }
                                if restriction_text:
                                    payload['restriction'] = restriction_text
                                events.append(Event(
                                    type=EventType.MANA_PRODUCED,
                                    payload=payload,
                                    source=source.id,
                                    controller=action.player_id
                                ))
                                produced_any = True

                        # Pragmatic fallback for "Add one mana of any color"
                        # / "Add two mana in any combination of colors":
                        # the cast UI doesn't yet prompt the player for a
                        # color, so we produce colorless. This unblocks ~40
                        # cards across the 12 sets at the cost of perfect
                        # color flexibility. (Engine gap: PendingChoice
                        # integration in the mana ability path.)
                        if not produced_any:
                            lower_line = ability_line.lower()
                            any_color_match = re.search(
                                r'add (\w+) mana (?:of any (?:one )?color|in any combination of colors)',
                                lower_line,
                            )
                            if any_color_match and self.mana_system:
                                amount_word = any_color_match.group(1)
                                amount_map = {
                                    'one': 1, 'a': 1, 'two': 2, 'three': 3,
                                    'four': 4, 'five': 5, 'six': 6, 'seven': 7,
                                    'eight': 8,
                                }
                                amount = amount_map.get(amount_word, 1)
                                if amount_word.isdigit():
                                    amount = int(amount_word)
                                self.mana_system.produce_mana(
                                    action.player_id, ManaType.COLORLESS, amount,
                                    source_id=source.id,
                                    restriction=restriction_fn,
                                    restriction_text=restriction_text,
                                )
                                payload = {
                                    'player': action.player_id,
                                    'color': ManaType.COLORLESS.value,
                                    'amount': amount,
                                    'note': 'any-color fallback (colorless)',
                                }
                                if restriction_text:
                                    payload['restriction'] = restriction_text
                                events.append(Event(
                                    type=EventType.MANA_PRODUCED,
                                    payload=payload,
                                    source=source.id,
                                    controller=action.player_id,
                                ))
                    except ValueError:
                        pass

        # Generic fallback for unknown activated abilities - still put on stack.
        if not events and self.stack and not pushed_stack_item:
            item = StackItem(
                id="",
                type=StackItemType.ACTIVATED_ABILITY,
                source_id=action.source_id,
                controller_id=action.player_id,
                chosen_targets=action.targets
            )
            self.stack.push(item)
            pushed_stack_item = True

        # === Crime tracking (OTJ) ===
        # CR 701.55: activating an ability with opponent-facing targets is a
        # crime. This covers fallback / unknown activated-ability shapes.
        if action.targets:
            from .crime import check_cast_targets_for_crime as _ccfc_fallback
            events.extend(_ccfc_fallback(
                controller_id=action.player_id,
                targets=action.targets,
                state=self.state,
                source_id=action.source_id,
            ))

        events.append(Event(
            type=EventType.ACTIVATE,
            payload={
                'source_id': action.source_id,
                'ability_id': action.ability_id,
                'controller': action.player_id
            }
        ))

        # Ward / TARGET_CHOSEN parity with the cast-spell path: emit one
        # TARGET_CHOSEN event per chosen target so ward and similar
        # interceptors fire for activated-ability targeting too.
        if pushed_stack_item and action.targets:
            events.extend(build_target_chosen_events(
                action.source_id, action.player_id, action.targets,
            ))

        return events

    async def _handle_play_land(self, action: PlayerAction) -> list[Event]:
        """Handle playing a land."""
        events = []

        card = self.state.objects.get(action.card_id)
        if not card:
            return events

        # Must be a land.
        if CardType.LAND not in card.characteristics.types:
            return events

        # Determine the source zone. By default, lands are played from hand.
        from_zone = None
        from_zone_type = None
        if card.zone == ZoneType.HAND:
            from_zone = f"hand_{action.player_id}"
            from_zone_type = ZoneType.HAND
        elif card.zone == ZoneType.GRAVEYARD:
            # Effects like Crucible of Worlds can permit playing lands from graveyard.
            if not self._graveyard_land_permission_active(action.player_id):
                return events
            from_zone = f"graveyard_{card.owner}"
            from_zone_type = ZoneType.GRAVEYARD
        else:
            return events

        # Determine if the land enters tapped based on its rules text.
        # Two cases handled here:
        #   1. Unconditional: "This land enters tapped." → tapped.
        #   2. Conditional ("unless you control..."): not handled here; defer
        #      to setup_interceptors.
        # Shocklands ("As this land enters, you may pay 2 life. If you don't,
        # it enters tapped.") are handled via ``make_shockland_setup`` on the
        # card definition — the framework opens a PendingChoice on ETB so a
        # human can decide; AI auto-resolves via the heuristic. Keeping any
        # inline logic here would double-fire the LIFE_CHANGE for AI players.
        tapped = False
        text = (card.card_def.text if card.card_def else "") or ""
        if re.search(
            r"^\s*(?:this\s+land|it)\s+enters\s+(?:the\s+battlefield\s+)?tapped\.?\s*$",
            text, re.IGNORECASE | re.MULTILINE,
        ):
            tapped = True

        # Move land to battlefield
        payload = {
            'object_id': action.card_id,
            'from_zone': from_zone,
            'from_zone_type': from_zone_type,
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        }
        if tapped:
            payload['tapped'] = True
        events.append(Event(type=EventType.ZONE_CHANGE, payload=payload))

        # Record land play
        if self.turn_manager:
            self.turn_manager.play_land()

        return events

    async def _handle_special_action(self, action: PlayerAction) -> list[Event]:
        """Handle special actions (morph, suspend, etc.)."""
        # Special actions don't use the stack
        return []

    async def _handle_crew(self, action: PlayerAction) -> list[Event]:
        """Handle crewing a Vehicle."""
        events = []

        vehicle = self.state.objects.get(action.card_id)
        if not vehicle:
            return events

        # Get crew data from action
        crew_with = action.data.get('crew_with', [])

        # Tap the creatures used to crew
        for creature_id in crew_with:
            creature = self.state.objects.get(creature_id)
            if creature and not creature.state.tapped:
                events.append(Event(
                    type=EventType.TAP,
                    payload={'object_id': creature_id},
                    source=vehicle.id,
                    controller=action.player_id
                ))

        # Mark vehicle as crewed (becomes a creature until end of turn)
        if CardType.CREATURE not in vehicle.characteristics.types:
            vehicle.characteristics.types.add(CardType.CREATURE)

        # Mark for cleanup at end of turn
        vehicle.state.crewed_until_eot = True

        return events

    # === Cycling (W8) ===
    async def _handle_cycle_card(self, action: PlayerAction) -> list[Event]:
        """Handle a CYCLE_CARD action by dispatching through the activated path.

        The cycle is registered as an activated ability with a cycling
        ``description`` (see ``src/engine/cycling.py``). The legal-actions
        surface re-tags such actions to ``ActionType.CYCLE_CARD`` and uses
        ``card_id`` to point at the card in hand. We translate back to the
        activated-ability dispatch by setting ``source_id`` from ``card_id``
        and forwarding to ``_handle_activate_ability``.
        """
        if action.source_id is None and action.card_id is not None:
            action.source_id = action.card_id
        return await self._handle_activate_ability(action)
    # === end Cycling (W8) ===

    def _all_players_passed(self) -> bool:
        """Check if all players have passed priority."""
        return len(self.passed_players) >= len(self.state.players)

    def _get_next_player(self) -> Optional[str]:
        """Get the next player in turn order."""
        if not self.turn_manager or not self.turn_manager.turn_order:
            players = list(self.state.players.keys())
            if not players:
                return None
            current_idx = players.index(self.priority_player) if self.priority_player in players else 0
            return players[(current_idx + 1) % len(players)]

        turn_order = self.turn_manager.turn_order
        current_idx = turn_order.index(self.priority_player) if self.priority_player in turn_order else 0
        return turn_order[(current_idx + 1) % len(turn_order)]

    async def _check_state_based_actions(self) -> None:
        """Check and process state-based actions."""
        from .queries import get_toughness, is_creature

        # Loop until no more SBAs (with safety cap to prevent infinite loops).
        # 500 is generous: even a chained-deaths board state shouldn't need
        # more than a few dozen passes.
        sba_iter = 0
        while True:
            sba_iter += 1
            if sba_iter > 500:
                import logging
                logging.getLogger(__name__).warning(
                    "PrioritySystem: SBA loop hit iteration cap (500); "
                    "bailing out. Likely a self-perpetuating SBA — investigate.")
                return
            found_sba = False

            # Check player life totals
            for player in self.state.players.values():
                if player.life <= 0 and not player.has_lost:
                    event = Event(
                        type=EventType.PLAYER_LOSES,
                        payload={'player': player.id, 'reason': 'life'}
                    )
                    self._emit_event(event)
                    found_sba = True

            # Check creature toughness
            battlefield = self.state.zones.get('battlefield')
            if battlefield:
                for obj_id in list(battlefield.objects):
                    obj = self.state.objects.get(obj_id)
                    if not obj:
                        continue

                    if not is_creature(obj, self.state):
                        continue

                    toughness = get_toughness(obj, self.state)

                    # Zero or less toughness
                    if toughness <= 0:
                        event = Event(
                            type=EventType.OBJECT_DESTROYED,
                            payload={'object_id': obj_id, 'reason': 'zero_toughness'},
                            source=obj.state.last_damage_source,
                        )
                        self._emit_event(event)
                        found_sba = True
                        continue

                    # Lethal damage
                    if obj.state.damage >= toughness:
                        event = Event(
                            type=EventType.OBJECT_DESTROYED,
                            payload={'object_id': obj_id, 'reason': 'lethal_damage'},
                            source=obj.state.last_damage_source,
                        )
                        self._emit_event(event)
                        found_sba = True

            # W15: planeswalker zero-loyalty SBA + legend rule SBA.
            from .turn import (
                check_planeswalker_zero_loyalty_sbas,
                check_legend_rule_sbas,
            )
            pw_events = check_planeswalker_zero_loyalty_sbas(self.state, self.pipeline)
            if pw_events:
                found_sba = True
            legend_events = check_legend_rule_sbas(self.state, self.pipeline)
            if legend_events:
                found_sba = True

            if not found_sba:
                break

    async def _put_triggers_on_stack(self) -> None:
        """Put any waiting triggered abilities on the stack (CR 603.3).

        Drains ``state.pending_triggers`` in APNAP order and pushes them
        onto the stack as TriggeredStackItem entries. Players will then
        receive priority and may respond before the triggers resolve.

        When ``state.options.auto_resolve_triggers`` is True (the test
        default), the pipeline already drained these triggers inline before
        returning, so this is a no-op. When False (production play), this
        is the canonical path that brings triggers onto the stack.
        """
        if not self.state.pending_triggers:
            return
        if self.stack is None:
            return
        try:
            from .stack import process_pending_triggers
            process_pending_triggers(self.state, self.stack)
        except Exception:
            # Defensive: don't let a malformed trigger crash the priority loop.
            pass

    def _is_game_over(self) -> bool:
        """Check if the game is over."""
        alive_players = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive_players) <= 1

    def _emit_event(self, event: Event) -> None:
        """Emit an event through the game's event pipeline."""
        if self.pipeline:
            self.pipeline.emit(event)


class ActionValidator:
    """
    Validates that actions are legal before execution.
    """

    def __init__(self, state: GameState, priority_system: PrioritySystem):
        self.state = state
        self.priority_system = priority_system

    def validate(self, action: PlayerAction) -> tuple[bool, str]:
        """
        Validate an action.

        Returns (is_valid, error_message).
        """
        # Check player has priority
        if action.player_id != self.priority_system.priority_player:
            return (False, "You don't have priority")

        # Validate specific action types
        if action.type == ActionType.CAST_SPELL:
            return self._validate_cast(action)
        elif action.type == ActionType.PLAY_LAND:
            return self._validate_land(action)
        elif action.type == ActionType.ACTIVATE_ABILITY:
            return self._validate_ability(action)

        return (True, "")

    def _validate_cast(self, action: PlayerAction) -> tuple[bool, str]:
        """Validate spell casting."""
        card = self.state.objects.get(action.card_id)
        if not card:
            return (False, "Card not found")

        # Check card is in hand
        hand_key = f"hand_{action.player_id}"
        hand = self.state.zones.get(hand_key)
        if not hand or action.card_id not in hand.objects:
            return (False, "Card not in hand")

        # Check can cast
        if not self.priority_system._can_cast(card, action.player_id):
            return (False, "Cannot cast this spell now")

        return (True, "")

    def _validate_land(self, action: PlayerAction) -> tuple[bool, str]:
        """Validate land play."""
        if not self.priority_system._can_play_land(action.player_id):
            return (False, "Cannot play a land now")

        card = self.state.objects.get(action.card_id)
        if not card:
            return (False, "Card not found")

        if CardType.LAND not in card.characteristics.types:
            return (False, "Not a land card")

        return (True, "")

    def _validate_ability(self, action: PlayerAction) -> tuple[bool, str]:
        """Validate ability activation."""
        # Would check ability can be activated
        return (True, "")
