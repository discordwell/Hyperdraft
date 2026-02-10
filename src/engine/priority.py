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
import re

from .types import GameState, Event, EventType, CardType, ZoneType, PendingChoice
from .stack import StackManager, StackItem, StackItemType
from .mana import ManaSystem, ManaCost, ManaType
from .pipeline import EventPipeline
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

if TYPE_CHECKING:
    from .turn import TurnManager


# Casting-from-graveyard support (Flashback). This is intentionally minimal
# and driven by rules text patterns since most sets are imported from Scryfall.
_FLASHBACK_COST_RE = re.compile(r'flashback\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_HARMONIZE_COST_RE = re.compile(r'harmonize\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)
_MAYHEM_COST_RE = re.compile(r'mayhem\s*[—-]?\s*((?:\{[^}]+\})+)', re.IGNORECASE)


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

        # Priority state
        self.priority_player: Optional[str] = None
        self.passed_players: set[str] = set()

        # For human players - callback to get their action
        self.get_human_action: Optional[Callable[[str, list[LegalAction]], asyncio.Future]] = None

        # For AI players - callback to get their action
        self.get_ai_action: Optional[Callable[[str, GameState, list[LegalAction]], PlayerAction]] = None

        # Callback invoked after action is processed (for synchronization)
        self.on_action_processed: Optional[Callable[[], None]] = None

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

        while True:
            # Check SBAs before granting priority
            await self._check_state_based_actions()
            await self._put_triggers_on_stack()

            # Check if game is over
            if self._is_game_over():
                return

            # Get legal actions for current player
            legal_actions = self.get_legal_actions(self.priority_player)

            # Get player action
            action = await self._get_player_action(self.priority_player, legal_actions)

            if action.type == ActionType.PASS:
                self.passed_players.add(self.priority_player)
                # Signal action was processed (for API synchronization)
                if self.on_action_processed:
                    self.on_action_processed()

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
                await self._execute_action(action)
                # Signal action was processed (for API synchronization)
                if self.on_action_processed:
                    self.on_action_processed()
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
                return self.get_ai_action(player_id, self.state, legal_actions)
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

                cost = ManaCost.parse(card.characteristics.mana_cost or "")
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

                if self._can_cast(card, player_id) and self._can_pay_cost_plan(std_plan, ctx):
                    desc = f"Cast {card.name}"
                    if std_plan:
                        desc = f"{desc} ({describe_plan(std_plan)})"
                    actions.append(LegalAction(
                        type=ActionType.CAST_SPELL,
                        card_id=card_id,
                        description=desc,
                        requires_mana=not cost.is_free(),
                        mana_cost=cost
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
                    cost_for_ui = option.alt_mana_cost or ManaCost.parse(card.characteristics.mana_cost or "")
                    full_plan = self._concat_cost_plans(std_plan, option.additional_cost_plan)
                    ctx = CastCostContext(
                        state=self.state,
                        mana_system=self.mana_system,
                        player_id=player_id,
                        casting_card_id=card_id,
                        casting_card_name=card.name,
                        casting_zone=card.zone,
                        base_mana_cost=cost_for_ui,
                        x_value=0,
                    )

                    if option.alt_mana_cost is None:
                        if not self._can_cast(card, player_id):
                            continue
                    else:
                        if not self._can_cast(card, player_id, cost_override=option.alt_mana_cost):
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
                        requires_mana=not cost_for_ui.is_free(),
                        mana_cost=cost_for_ui
                    ))

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
            return ctx.mana_system.can_cast(ctx.player_id, total, ctx.x_value)

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
            eligible = eligible_hand_cards(ctx)
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

        # Check mana cost
        cost = cost_override or ManaCost.parse(mana_cost_str or "")
        if self.mana_system and not cost.is_free():
            if not self.mana_system.can_cast(player_id, cost):
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

        Current implementation supports:
        - Planeswalker loyalty abilities without explicit targets
        - Tap-for-mana abilities from rules text
        """
        actions: list[LegalAction] = []
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
                if (CardType.CREATURE in obj.characteristics.types and
                    getattr(obj, 'summoning_sickness', False)):
                    # Creatures with summoning sickness can't use tap abilities.
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

        from_graveyard = card.zone == ZoneType.GRAVEYARD

        # Choose a single casting option when casting from the graveyard.
        # We still do not expose option selection via the action payload yet,
        # so we pick the first supported option (flashback/harmonize/mayhem/etc.).
        used_flashback = False
        used_harmonize = False
        used_mayhem = False
        exile_on_leave_stack = False
        option_plan: Optional[CostPlan] = None

        if from_graveyard:
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
        else:
            paid_cost = ManaCost.parse(card.characteristics.mana_cost or "")

        printed_cost = ManaCost.parse(card.characteristics.mana_cost or "")

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

        if not self._can_pay_cost_plan(full_plan, ctx):
            return []

        return self._continue_cast_spell_with_additional_costs(
            action=action,
            paid_cost=paid_cost,
            printed_cost=printed_cost,
            plan=tuple(full_plan or ()),
            extra_mana=ManaCost(),
            from_graveyard=from_graveyard,
            used_flashback=used_flashback,
            used_harmonize=used_harmonize,
            used_mayhem=used_mayhem,
            exile_on_leave_stack=exile_on_leave_stack,
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
            total_cost = add_mana_costs(paid_cost, extra_mana)
            if self.mana_system and not total_cost.is_free():
                self.mana_system.pay_cost(action.player_id, total_cost, action.x_value)

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
                        'exile_on_leave_stack': exile_on_leave_stack,
                    }
                )
                self.stack.push(item)

            return [Event(
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
                },
                source=action.card_id,
                controller=action.player_id,
            )]

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
            options = eligible_hand_cards(ctx)
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
        source = self.state.objects.get(action.source_id) if action.source_id else None

        if source and action.ability_id:
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
                        for symbol in mana_symbols:
                            mana_type = symbol_to_type.get(symbol)
                            if mana_type and self.mana_system:
                                self.mana_system.produce_mana(action.player_id, mana_type, 1)
                                events.append(Event(
                                    type=EventType.MANA_PRODUCED,
                                    payload={
                                        'player': action.player_id,
                                        'color': mana_type.value,
                                        'amount': 1
                                    },
                                    source=source.id,
                                    controller=action.player_id
                                ))
                    except ValueError:
                        pass

        # Generic fallback for unknown activated abilities - still put on stack.
        if not events and self.stack:
            item = StackItem(
                id="",
                type=StackItemType.ACTIVATED_ABILITY,
                source_id=action.source_id,
                controller_id=action.player_id,
                chosen_targets=action.targets
            )
            self.stack.push(item)

        events.append(Event(
            type=EventType.ACTIVATE,
            payload={
                'source_id': action.source_id,
                'ability_id': action.ability_id,
                'controller': action.player_id
            }
        ))

        return events

    async def _handle_play_land(self, action: PlayerAction) -> list[Event]:
        """Handle playing a land."""
        events = []

        card = self.state.objects.get(action.card_id)
        if not card:
            return events

        # Move land from hand to battlefield
        events.append(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': action.card_id,
                'from_zone': f'hand_{action.player_id}',
                'to_zone': 'battlefield',
                'to_zone_type': ZoneType.BATTLEFIELD
            }
        ))

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

        # Loop until no more SBAs
        while True:
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
                            payload={'object_id': obj_id, 'reason': 'zero_toughness'}
                        )
                        self._emit_event(event)
                        found_sba = True
                        continue

                    # Lethal damage
                    if obj.state.damage >= toughness:
                        event = Event(
                            type=EventType.OBJECT_DESTROYED,
                            payload={'object_id': obj_id, 'reason': 'lethal_damage'}
                        )
                        self._emit_event(event)
                        found_sba = True

            if not found_sba:
                break

    async def _put_triggers_on_stack(self) -> None:
        """Put any waiting triggered abilities on the stack."""
        # This would process triggered abilities waiting to go on stack
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
