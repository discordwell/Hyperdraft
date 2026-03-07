"""
Yu-Gi-Oh! Chain System

The Chain is a stack-like mechanism for resolving card effects:
1. A trigger effect or card activation starts the Chain (Chain Link 1)
2. Each player gets a chance to respond (add Chain Links)
3. Responses must have Spell Speed >= the previous link's Spell Speed
4. Counter Traps (SS3) can only be responded to by other Counter Traps
5. When both players pass, the Chain resolves in LIFO order (last link first)

Spell Speeds:
- SS1: Normal Spells, Ignition Effects, Trigger Effects (cannot chain to anything)
- SS2: Quick-Play Spells, Trap Cards, Quick Effects
- SS3: Counter Traps (only Counter Traps can respond)
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, TYPE_CHECKING

from .types import (
    GameState, Event, EventType, new_id
)

if TYPE_CHECKING:
    from .pipeline import EventPipeline


@dataclass
class ChainLink:
    """A single link in the Chain."""
    id: str
    card_id: str           # Card being activated
    controller: str        # Player who activated
    spell_speed: int       # 1, 2, or 3
    resolve_fn: Optional[Callable] = None  # Function to call on resolution
    targets: list = field(default_factory=list)  # Target IDs
    card_name: str = ""


class YugiohChainManager:
    """
    Manages the Yu-Gi-Oh! Chain system.

    Chain flow:
    1. start_chain(trigger) — opens chain with first link
    2. Players alternate adding links via add_link()
    3. When both pass, resolve_chain() runs LIFO
    """

    def __init__(self, state: GameState):
        self.state = state
        self.chain_links: list[ChainLink] = []
        self.pipeline: Optional['EventPipeline'] = None
        self._is_resolving: bool = False

    @property
    def is_chain_active(self) -> bool:
        return len(self.chain_links) > 0

    @property
    def current_spell_speed(self) -> int:
        """Get the Spell Speed of the most recent chain link."""
        if not self.chain_links:
            return 0
        return self.chain_links[-1].spell_speed

    def start_chain(self, card_id: str, controller: str, spell_speed: int,
                    resolve_fn: Optional[Callable] = None,
                    targets: list = None, card_name: str = "") -> bool:
        """
        Start a new Chain with the first link.
        Returns True if chain was started successfully.
        """
        if self._is_resolving:
            return False

        link = ChainLink(
            id=new_id(),
            card_id=card_id,
            controller=controller,
            spell_speed=spell_speed,
            resolve_fn=resolve_fn,
            targets=targets or [],
            card_name=card_name,
        )
        self.chain_links = [link]
        return True

    def can_add_link(self, spell_speed: int) -> tuple[bool, str]:
        """
        Check if a new link can be added to the chain.

        Rules:
        - Must have SS >= current chain's SS
        - SS3 (Counter Trap) can only be responded to by SS3
        """
        if not self.chain_links:
            return True, ""

        current_ss = self.current_spell_speed

        # Counter Trap exclusivity: SS3 can only be responded to by SS3
        if current_ss == 3 and spell_speed < 3:
            return False, "Only Counter Traps (SS3) can respond to Counter Traps"

        if spell_speed < current_ss:
            return False, f"Spell Speed {spell_speed} is lower than current chain SS {current_ss}"

        return True, ""

    def add_link(self, card_id: str, controller: str, spell_speed: int,
                 resolve_fn: Optional[Callable] = None,
                 targets: list = None, card_name: str = "") -> tuple[bool, str]:
        """
        Add a new link to the Chain.
        Returns (success, error_message).
        """
        can, reason = self.can_add_link(spell_speed)
        if not can:
            return False, reason

        link = ChainLink(
            id=new_id(),
            card_id=card_id,
            controller=controller,
            spell_speed=spell_speed,
            resolve_fn=resolve_fn,
            targets=targets or [],
            card_name=card_name,
        )
        self.chain_links.append(link)
        return True, ""

    def resolve_chain(self) -> list[Event]:
        """
        Resolve the entire chain in LIFO order (last link resolves first).
        Returns all events generated during resolution.
        """
        events = []
        self._is_resolving = True

        # Resolve in reverse order (LIFO)
        while self.chain_links:
            link = self.chain_links.pop()

            events.append(Event(
                type=EventType.YGO_CHAIN_RESOLVE,
                payload={
                    'chain_link_id': link.id,
                    'card_id': link.card_id,
                    'controller': link.controller,
                    'card_name': link.card_name,
                },
                source=link.card_id,
                controller=link.controller,
            ))

            # Execute the resolve function
            if link.resolve_fn:
                try:
                    result_events = link.resolve_fn(self.state, link.targets)
                    if result_events:
                        events.extend(result_events)
                except Exception:
                    pass  # Swallow resolve errors to keep chain going

        self._is_resolving = False
        return events

    def can_respond(self, player_id: str) -> bool:
        """
        Check if a player has any activatable responses.
        This is a simplified check — full implementation would scan
        the player's hand and field for Quick Effects, Quick-Play Spells,
        and set Trap Cards.
        """
        if not self.chain_links:
            return False

        current_ss = self.current_spell_speed

        # Check hand for Quick-Play Spells (SS2)
        hand_key = f"hand_{player_id}"
        hand = self.state.zones.get(hand_key)
        if hand:
            for obj_id in hand.objects:
                obj = self.state.objects.get(obj_id)
                if obj and obj.card_def:
                    card_ss = getattr(obj.card_def, 'spell_speed', None) or 0
                    if card_ss >= current_ss:
                        if current_ss < 3 or card_ss >= 3:
                            return True

        # Check set Spell/Trap zone
        st_key = f"spell_trap_zone_{player_id}"
        st_zone = self.state.zones.get(st_key)
        if st_zone:
            for obj_id in st_zone.objects:
                if obj_id is None:
                    continue
                obj = self.state.objects.get(obj_id)
                if obj and obj.state.face_down and obj.card_def:
                    # Must be set for at least 1 turn (for traps)
                    turns_set = getattr(obj.state, 'turns_set', 0)
                    card_ss = getattr(obj.card_def, 'spell_speed', None) or 0
                    if card_ss >= current_ss and turns_set >= 1:
                        if current_ss < 3 or card_ss >= 3:
                            return True

        return False

    def clear(self):
        """Clear the chain (used for cleanup)."""
        self.chain_links.clear()
        self._is_resolving = False
