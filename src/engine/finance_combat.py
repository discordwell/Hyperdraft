"""
Finance TCG — Combat Manager

Implements declare-attackers / declare-blockers / simultaneous-damage-resolution
for the Finance game.

Combat flow (called from FinanceTurnManager during TRADING_SESSION):
    1. get_legal_attackers(player_id)    → list of attackable Trader object IDs
    2. declare_attackers(player_id, ids) → tap each, emit ATTACK_DECLARED
    3. get_legal_blockers(player_id, attacker_ids)  → list of blockable Trader IDs
    4. declare_blockers(player_id, blocks)  → blocks = {attacker_id: blocker_id}
    5. resolve_combat_damage(attacker_ids, blocks, defending_player_id)
       → simultaneous, overflow to Capital Reserve, lethal → OBJECT_DESTROYED

Key rules:
  - Damage persists (does NOT reset at Market Close).
  - Lethal: damage >= Defense Rating → Trader is Liquidated (OBJECT_DESTROYED).
  - Overflow: attacker Aggression > blocker Defense Rating → difference hits
    defending player's Capital Reserve.
  - Unblocked attacker deals full Aggression to opponent's Capital Reserve.
  - Summoning sickness: Traders with obj.state.summoning_sickness=True cannot
    attack; cleared by clear_summoning_sickness() at Pre-Market start.

Ownership: ONLY this file. Do not import from finance.py, finance_turn.py,
or finance_adapter.py — they own their own modules.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from .types import (
    CardType,
    Event,
    EventType,
    GameState,
    GameObject,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)

if TYPE_CHECKING:
    from .pipeline import EventPipeline

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FIN_TRADER CardType — guarded import so this module loads before finance.py
# wires the new CardType values into types.py.
# ---------------------------------------------------------------------------

try:
    FIN_TRADER: Optional[CardType] = CardType.FIN_TRADER  # type: ignore[attr-defined]
except AttributeError:
    FIN_TRADER = None  # TODO: needs FIN_TRADER from types.py (added by Agent 1)

# ---------------------------------------------------------------------------
# Power / toughness queries — use the pipeline-aware helpers when available.
# ---------------------------------------------------------------------------

try:
    from .queries import get_power, get_toughness as _get_toughness

    def _power(obj: GameObject, state: GameState) -> int:
        return int(get_power(obj, state) or 0)

    def _toughness(obj: GameObject, state: GameState) -> int:
        return int(_get_toughness(obj, state) or 0)

except Exception:  # pragma: no cover
    def _power(obj: GameObject, state: GameState) -> int:  # type: ignore[misc]
        return int(obj.characteristics.power or 0)

    def _toughness(obj: GameObject, state: GameState) -> int:  # type: ignore[misc]
        return int(obj.characteristics.toughness or 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_fin_trader(obj: GameObject) -> bool:
    """Return True if *obj* is a FIN_TRADER on the battlefield."""
    if obj is None:
        return False
    if obj.zone != ZoneType.BATTLEFIELD:
        return False
    if FIN_TRADER is not None:
        return FIN_TRADER in obj.characteristics.types
    # Fallback before Agent 1 wires FIN_TRADER into types.py: check subtypes.
    subtypes = getattr(obj.characteristics, "subtypes", set()) or set()
    return "Trader" in subtypes or "FIN_TRADER" in subtypes


def _battlefield_objects(state: GameState) -> list[GameObject]:
    """Iterate objects on the battlefield."""
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    return [obj for oid in bf.objects if (obj := state.objects.get(oid)) is not None]


# ---------------------------------------------------------------------------
# FinanceCombatManager
# ---------------------------------------------------------------------------

class FinanceCombatManager:
    """Combat manager for Finance TCG.

    Created once per game by FinanceTurnManager. The pipeline is required for
    routing DAMAGE / LIFE_CHANGE events through card interceptors.

    Typical call sequence per Trading Session:
        attackers = mgr.get_legal_attackers(active_player_id)
        # (AI / player picks a subset)
        await mgr.declare_attackers(active_player_id, chosen_attacker_ids)

        blockers = mgr.get_legal_blockers(defending_player_id, chosen_attacker_ids)
        # (AI / player assigns blocks: {attacker_id: blocker_id})
        await mgr.declare_blockers(defending_player_id, blocks_dict)

        await mgr.resolve_combat_damage(chosen_attacker_ids, blocks_dict, defending_player_id)
    """

    def __init__(self, state: GameState, pipeline: "EventPipeline" = None) -> None:
        self.state = state
        self.pipeline = pipeline

    # ------------------------------------------------------------------
    # Public query helpers
    # ------------------------------------------------------------------

    def get_legal_attackers(self, player_id: str) -> list[str]:
        """Return object IDs that can legally attack this turn.

        Requirements:
          - On the battlefield
          - Type FIN_TRADER
          - Controlled by player_id
          - Not tapped
          - No summoning sickness
        """
        legal: list[str] = []
        for obj in _battlefield_objects(self.state):
            if obj.controller != player_id:
                continue
            if not _is_fin_trader(obj):
                continue
            if obj.state.tapped:
                continue
            if obj.state.summoning_sickness:
                continue
            legal.append(obj.id)
        return legal

    def get_legal_blockers(self, player_id: str, attacker_ids: list[str]) -> list[str]:
        """Return object IDs that can legally block any of the given attackers.

        Requirements:
          - On the battlefield
          - Type FIN_TRADER
          - Controlled by player_id (the defending player)
          - Not tapped

        One blocker may only block one attacker; the caller handles the mapping.
        ``attacker_ids`` is accepted for future use (e.g. "can't be blocked"
        restrictions) but is not filtered here yet.
        """
        legal: list[str] = []
        for obj in _battlefield_objects(self.state):
            if obj.controller != player_id:
                continue
            if not _is_fin_trader(obj):
                continue
            if obj.state.tapped:
                continue
            legal.append(obj.id)
        return legal

    # ------------------------------------------------------------------
    # Declaration steps
    # ------------------------------------------------------------------

    async def declare_attackers(
        self, player_id: str, attacker_ids: list[str]
    ) -> list[Event]:
        """Tap each attacker and emit ATTACK_DECLARED per attacker.

        Silently skips IDs that are no longer legal (e.g. tapped between now
        and when the AI chose them). Returns the list of ATTACK_DECLARED events
        that were emitted.
        """
        emitted: list[Event] = []
        legal = set(self.get_legal_attackers(player_id))

        for aid in attacker_ids:
            if aid not in legal:
                logger.debug("finance_combat: skipping illegal attacker %s", aid)
                continue
            obj = self.state.objects.get(aid)
            if obj is None:
                continue
            obj.state.tapped = True
            obj.state.attacking = True

            ev = Event(
                type=EventType.ATTACK_DECLARED,
                payload={
                    "attacker_id": aid,
                    "attacking_player": player_id,
                    "is_finance": True,
                },
                source=aid,
                controller=player_id,
            )
            await self._emit(ev)
            emitted.append(ev)

        return emitted

    async def declare_blockers(
        self, player_id: str, blocks: dict[str, str]
    ) -> list[Event]:
        """Register blocking assignments and emit BLOCK_DECLARED per pair.

        ``blocks`` maps attacker_id → blocker_id. Each blocker may only appear
        once; duplicates are silently dropped (last-write-wins order is
        intentionally avoided — first occurrence wins to be deterministic).
        Returns the list of BLOCK_DECLARED events emitted.
        """
        emitted: list[Event] = []
        legal_blockers = set(self.get_legal_blockers(player_id, list(blocks.keys())))
        used_blockers: set[str] = set()

        for attacker_id, blocker_id in blocks.items():
            if blocker_id not in legal_blockers:
                logger.debug(
                    "finance_combat: illegal blocker %s for attacker %s",
                    blocker_id,
                    attacker_id,
                )
                continue
            if blocker_id in used_blockers:
                logger.debug(
                    "finance_combat: blocker %s already assigned, skipping duplicate",
                    blocker_id,
                )
                continue
            blocker = self.state.objects.get(blocker_id)
            if blocker is None:
                continue

            used_blockers.add(blocker_id)
            blocker.state.blocking = True

            ev = Event(
                type=EventType.BLOCK_DECLARED,
                payload={
                    "blocker_id": blocker_id,
                    "attacker_id": attacker_id,
                    "is_finance": True,
                },
                source=blocker_id,
                controller=player_id,
            )
            await self._emit(ev)
            emitted.append(ev)

        return emitted

    # ------------------------------------------------------------------
    # Damage resolution
    # ------------------------------------------------------------------

    async def resolve_combat_damage(
        self,
        attacker_ids: list[str],
        blocks: dict[str, str],
        defending_player_id: str,
    ) -> list[Event]:
        """Resolve combat damage simultaneously for all declared attackers.

        For each attacker:
          - Blocked: both sides deal damage to each other. Check overflow.
          - Unblocked: attacker deals full Aggression to opponent Capital Reserve.

        After all damage is dealt, check lethality and liquidate dead Traders.

        ``blocks`` maps attacker_id → blocker_id (the subset accepted in
        declare_blockers; pass the same dict).

        Returns all events emitted during this step (DAMAGE, LIFE_CHANGE,
        OBJECT_DESTROYED, ZONE_CHANGE) in emission order.
        """
        emitted: list[Event] = []

        # Collect all objects that take damage so we can check lethality after
        # simultaneous resolution. Keys are object IDs; values are unused here
        # (we re-read from state.objects after damage is applied).
        damage_recipients: set[str] = set()

        for attacker_id in attacker_ids:
            attacker = self.state.objects.get(attacker_id)
            if attacker is None or attacker.zone != ZoneType.BATTLEFIELD:
                continue

            atk_power = _power(attacker, self.state)
            blocker_id = blocks.get(attacker_id)

            if blocker_id is not None:
                blocker = self.state.objects.get(blocker_id)
                # Blocker may have been removed between declare and resolve.
                if blocker is None or blocker.zone != ZoneType.BATTLEFIELD:
                    blocker = None

            if blocker_id is not None and blocker is not None:
                # --- Blocked combat ---
                blk_power = _power(blocker, self.state)
                blk_toughness = _toughness(blocker, self.state)

                # Attacker → blocker
                evs = await self._apply_damage(attacker_id, blocker_id, atk_power)
                emitted.extend(evs)
                damage_recipients.add(blocker_id)

                # Blocker → attacker
                evs = await self._apply_damage(blocker_id, attacker_id, blk_power)
                emitted.extend(evs)
                damage_recipients.add(attacker_id)

                # Overflow rule: attacker Aggression > blocker Defense Rating
                # → excess damages defending player's Capital Reserve.
                if atk_power > blk_toughness:
                    overflow = atk_power - blk_toughness
                    ev = Event(
                        type=EventType.LIFE_CHANGE,
                        payload={
                            "player": defending_player_id,
                            "amount": -overflow,
                            "source": attacker_id,
                            "reason": "finance_combat_overflow",
                        },
                        source=attacker_id,
                        controller=attacker.controller,
                    )
                    await self._emit(ev)
                    emitted.append(ev)
                    # Apply the Capital Reserve change directly so
                    # win-condition checks downstream see the updated value.
                    self._adjust_capital_reserve(defending_player_id, -overflow)

            else:
                # --- Unblocked attacker → Capital Reserve ---
                if atk_power > 0:
                    ev = Event(
                        type=EventType.LIFE_CHANGE,
                        payload={
                            "player": defending_player_id,
                            "amount": -atk_power,
                            "source": attacker_id,
                            "reason": "finance_combat_unblocked",
                        },
                        source=attacker_id,
                        controller=attacker.controller,
                    )
                    await self._emit(ev)
                    emitted.append(ev)
                    self._adjust_capital_reserve(defending_player_id, -atk_power)

        # Post-damage SBA: liquidate any Traders with damage >= Defense Rating.
        for obj_id in damage_recipients:
            evs = await self._liquidate_if_lethal(obj_id)
            emitted.extend(evs)

        # Clear per-combat state flags.
        for attacker_id in attacker_ids:
            obj = self.state.objects.get(attacker_id)
            if obj is not None:
                obj.state.attacking = False
        for blocker_id in blocks.values():
            obj = self.state.objects.get(blocker_id)
            if obj is not None:
                obj.state.blocking = False

        return emitted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_lethal(self, obj: GameObject) -> bool:
        """Return True if accumulated damage on *obj* >= its Defense Rating."""
        if obj is None:
            return False
        toughness = _toughness(obj, self.state)
        if toughness is None or toughness <= 0:
            # Zero-toughness: treat as immediately lethal.
            return True
        return int(obj.state.damage or 0) >= toughness

    async def _apply_damage(
        self, source_id: str, target_id: str, amount: int
    ) -> list[Event]:
        """Emit a DAMAGE event and accumulate damage on the target.

        Returns the list of events emitted (usually just the one DAMAGE event).
        """
        if amount <= 0:
            return []

        target = self.state.objects.get(target_id)
        if target is None:
            return []

        ev = Event(
            type=EventType.DAMAGE,
            payload={
                "target": target_id,
                "amount": amount,
                "source": source_id,
                "is_combat": True,
                "is_finance": True,
            },
            source=source_id,
            controller=(
                self.state.objects[source_id].controller
                if source_id in self.state.objects
                else None
            ),
        )
        await self._emit(ev)

        # Accumulate damage (may have been modified by a TRANSFORM interceptor).
        # Read the (possibly transformed) amount from the emitted event payload.
        resolved_amount = int(ev.payload.get("amount", amount) or amount)
        target.state.damage = int(target.state.damage or 0) + resolved_amount
        target.state.last_damage_source = source_id

        return [ev]

    async def _liquidate_if_lethal(self, obj_id: str) -> list[Event]:
        """If the Trader at *obj_id* has lethal damage, liquidate it.

        Emits OBJECT_DESTROYED followed by ZONE_CHANGE to GRAVEYARD.
        Returns the events emitted, or [] if the Trader is not yet dead.
        """
        obj = self.state.objects.get(obj_id)
        if obj is None:
            return []
        # Already off the battlefield (e.g. killed by a previous pass).
        if obj.zone != ZoneType.BATTLEFIELD:
            return []
        if not self._is_lethal(obj):
            return []

        emitted: list[Event] = []

        destroyed = Event(
            type=EventType.OBJECT_DESTROYED,
            payload={
                "object_id": obj_id,
                "reason": "finance_liquidated",
                "last_damage_source": obj.state.last_damage_source,
            },
            source=obj.state.last_damage_source,
            controller=obj.controller,
        )
        await self._emit(destroyed)
        emitted.append(destroyed)

        zone_change = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": obj_id,
                "from": "battlefield",
                "to": "graveyard",
                "reason": "finance_liquidated",
            },
            source=obj.state.last_damage_source,
            controller=obj.controller,
        )
        await self._emit(zone_change)
        emitted.append(zone_change)

        return emitted

    # ------------------------------------------------------------------
    # Summoning sickness
    # ------------------------------------------------------------------

    def clear_summoning_sickness(self, player_id: str) -> None:
        """Clear summoning sickness on all FIN_TRADERs controlled by *player_id*.

        Called at the start of the Pre-Market phase by FinanceTurnManager.
        """
        for obj in _battlefield_objects(self.state):
            if obj.controller != player_id:
                continue
            if not _is_fin_trader(obj):
                continue
            if obj.state.summoning_sickness:
                obj.state.summoning_sickness = False

    # ------------------------------------------------------------------
    # Capital Reserve adjustment
    # ------------------------------------------------------------------

    def _adjust_capital_reserve(self, player_id: str, delta: int) -> None:
        """Check win condition after a LIFE_CHANGE event was emitted.

        The LIFE_CHANGE event already updated player.life via the pipeline's
        damage handler. This method only sets has_lost so downstream SBA checks
        see the correct state immediately (without waiting for the next SBA pass).
        """
        player = self.state.players.get(player_id)
        if player is None:
            return
        # If pipeline is None (unit-test mode) we must apply the delta ourselves
        # since no handler did it.
        if self.pipeline is None:
            player.life = max(0, int(player.life or 0) + delta)
        if player.life <= 0 and not player.has_lost:
            player.has_lost = True
            logger.info(
                "finance_combat: player %s Capital Reserve reached 0 — bankruptcy",
                player_id,
            )

    # ------------------------------------------------------------------
    # Pipeline emit
    # ------------------------------------------------------------------

    async def _emit(self, event: Event) -> None:
        """Route an event through the pipeline, falling back gracefully.

        If the pipeline exposes a coroutine ``process_event`` or ``emit``, we
        await it. If it only has a synchronous ``emit``, we call that. If
        nothing is wired (unit-test mode), we append to state.event_log so
        tests can assert on emitted events.
        """
        import asyncio as _asyncio

        if self.pipeline is not None:
            process = getattr(self.pipeline, "process_event", None)
            if process is not None:
                if _asyncio.iscoroutinefunction(process):
                    await process(event)
                else:
                    process(event)
                return
            emit_fn = getattr(self.pipeline, "emit", None)
            if emit_fn is not None:
                if _asyncio.iscoroutinefunction(emit_fn):
                    await emit_fn(event)
                else:
                    emit_fn(event)
                return

        # Fallback: unit-test mode — just log.
        self.state.event_log.append(event)


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "FinanceCombatManager",
]
