"""Compatibility wrapper for Minecraft TCG combat."""

from __future__ import annotations

from .types import GameState
from . import minecraft as mc


class MinecraftCombatManager:
    def __init__(self, state: GameState):
        self.state = state
        self.turn_manager = None
        self.priority_system = None
        self.pipeline = None

    def reset_combat(self, player_id: str | None = None) -> None:
        if player_id:
            battlefield = self.state.zones.get("battlefield")
            for oid in list(battlefield.objects) if battlefield else []:
                obj = self.state.objects.get(oid)
                if obj and obj.controller == player_id:
                    obj.state.attacking = False
                    obj.state.blocking = False
        self.state.minecraft_combat = {}

    async def declare_attackers(self, player_id: str, attacks: list[dict]):
        game = getattr(self.state, "_game", None)
        if not game:
            return []
        ok, _message, events = mc.declare_attackers(game, player_id, attacks)
        return events if ok else []
