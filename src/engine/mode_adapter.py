"""
Game-mode adapter protocol.

Centralizes per-mode behavior that previously lived as scattered
`if game_mode == "..."` branches in the engine and server layers.

Each adapter subclass overrides only the hooks whose default behavior
(MTG-style) differs for that mode. The base class's defaults match MTG.

Hooks are small and behavioral: every one corresponds to a specific
branch that existed in the pre-refactor code. No speculative hooks.

Usage:
    from .mode_adapter import get_mode_adapter
    adapter = get_mode_adapter(state.game_mode)
    limit = adapter.hand_size_limit(player, state)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .types import GameState, GameObject, Player, Event, ZoneType


# =============================================================================
# Base adapter — MTG-style defaults
# =============================================================================

class GameModeAdapter:
    """
    Base adapter. Defaults model MTG behavior:
      - no hand-size cap enforced mid-turn
      - no board-size cap on permanents
      - draw-from-empty-library loses the game
      - no armor / no max-life cap
      - ZONE_CHANGE from battlefield does not reset card state
      - summoning sickness uses timestamp + haste
      - no card is "MINION" — the 7-minion board cap is a no-op
    """

    mode: str = "mtg"

    # ---------------------------------------------------------------
    # Hand / library / board caps
    # ---------------------------------------------------------------

    def hand_size_limit(self, player: "Player", state: "GameState") -> Optional[int]:
        """
        Max cards a player can hold during draw/ADD_TO_HAND. None = unlimited.
        MTG has a cleanup-step discard to 7, but no mid-turn overdraw rule.
        Hearthstone: overdraw burns the drawn card; capped at state.max_hand_size.
        """
        return None

    def overdraw_burns(self, state: "GameState") -> bool:
        """
        When a DRAW tries to exceed hand_size_limit, burn the drawn card (HS).
        MTG does not overdraw — cards just stay until cleanup discard.
        """
        return False

    def max_minions_on_board(self, controller_id: str, state: "GameState") -> Optional[int]:
        """
        Max permanents with CardType.MINION a controller can have on the battlefield.
        None = no cap. Hearthstone: 7.
        """
        return None

    # ---------------------------------------------------------------
    # Damage / life / armor
    # ---------------------------------------------------------------

    def apply_player_damage(
        self,
        player: "Player",
        amount: int,
        state: "GameState",
    ) -> int:
        """
        Apply damage directly to a player (where target_id is a player_id).
        Default: subtract from life, return remaining (0).
        HS: route through hero, apply armor first.

        Returns the amount of damage still to apply to the hero object's
        `state.damage` counter (0 if mode handled it entirely).
        """
        player.life -= amount
        return 0

    def handles_hero_damage(self) -> bool:
        """
        Whether this mode has a dedicated HERO damage path that short-circuits
        the regular creature-damage fallthrough. Only HS returns True.
        """
        return False

    def apply_hero_damage(
        self,
        hero: "GameObject",
        player: "Player",
        amount: int,
        state: "GameState",
    ) -> None:
        """
        Apply damage when the target is a HERO object. Only called when
        `handles_hero_damage()` is True. HS: apply armor, reduce life,
        stamp hero.state.damage.
        """
        return None

    def post_creature_damage_destroy_check(
        self,
        obj: "GameObject",
        event: "Event",
        state: "GameState",
    ) -> list:
        """
        After damage is applied to a creature/minion, should we immediately
        emit an OBJECT_DESTROYED? MTG defers to explicit SBA checks.
        HS: synchronously destroy if damage >= toughness and the source was
        a spell (to make direct spell effects resolve in-line).

        Returns a list of new events (possibly empty).
        """
        return []

    def life_cap(self, player: "Player", state: "GameState") -> Optional[int]:
        """
        Maximum player life (healing is capped here). MTG: no cap. HS: 30 (or max_life).
        """
        return None

    def sync_hero_damage_with_life(
        self,
        player: "Player",
        hero: "GameObject",
        state: "GameState",
    ) -> None:
        """
        After a life change, keep hero.state.damage in sync with player.life.
        HS mirrors lost life onto hero.state.damage so queries see it.
        Default: no-op.
        """
        return None

    # ---------------------------------------------------------------
    # Library & draw
    # ---------------------------------------------------------------

    def handle_empty_library_draw(
        self,
        player: "Player",
        state: "GameState",
    ) -> list:
        """
        Called when a DRAW is attempted with an empty library.
        MTG / YGO: the player loses the game.
        HS: fatigue damage (1, then 2, 3, ...).
        Returns a list of follow-up events to inject (e.g. fatigue DAMAGE).
        """
        player.has_lost = True
        return []

    # ---------------------------------------------------------------
    # Zone transitions
    # ---------------------------------------------------------------

    def on_leave_battlefield_to_hidden(
        self,
        obj: "GameObject",
        from_zone_type: "ZoneType",
        to_zone_type: "ZoneType",
        state: "GameState",
    ) -> None:
        """
        Fires when an object moves from BATTLEFIELD into a hidden zone (HAND/LIBRARY).
        MTG: no state reset — the object becomes a new instance on re-entry anyway.
        HS: reset minion state (damage, keyword flags, P/T modifiers) and restore
            characteristics from card_def.
        """
        return None

    # ---------------------------------------------------------------
    # Weapons
    # ---------------------------------------------------------------

    def on_weapon_destroyed(
        self,
        obj: "GameObject",
        event: "Event",
        state: "GameState",
    ) -> None:
        """
        HS-specific: clearing player.weapon_attack / weapon_durability when a
        weapon permanent is destroyed (unless it was 'weapon_replaced').
        Default: no-op (MTG/PKM/YGO don't have weapons).
        """
        return None

    # ---------------------------------------------------------------
    # Priority / tap-ability gating
    # ---------------------------------------------------------------

    # ---------------------------------------------------------------
    # Subsystem factories
    # ---------------------------------------------------------------

    def default_max_hand_size(self) -> Optional[int]:
        """
        Initial value assigned to state.max_hand_size in Game.__init__.
        MTG: None (no mid-turn cap). HS: 10. YGO: 6. PKM: 999 (effectively none).
        """
        return None

    def create_mana_system(self, state: "GameState"):
        """Build the mode's mana/energy system. None = no mana."""
        from .mana import ManaSystem
        return ManaSystem(state)

    def create_combat_manager(self, state: "GameState"):
        """Build the mode's combat manager."""
        from .combat import CombatManager
        return CombatManager(state)

    def create_turn_manager(self, state: "GameState"):
        """Build the mode's turn manager."""
        from .turn import TurnManager
        return TurnManager(state)

    # ---------------------------------------------------------------
    # Player zone creation
    # ---------------------------------------------------------------

    def extra_player_zone_types(self) -> list:
        """
        Per-player zone types beyond (LIBRARY, HAND, GRAVEYARD).
        PKM adds (ACTIVE_SPOT, BENCH, PRIZE_CARDS). YGO adds
        (MONSTER_ZONE, SPELL_TRAP_ZONE, FIELD_SPELL_ZONE, PENDULUM_ZONE,
        EXTRA_DECK, BANISHED). MTG/HS: none.
        """
        return []

    def extra_shared_zone_types(self) -> list:
        """
        Shared zone types beyond (BATTLEFIELD, STACK, EXILE, COMMAND).
        PKM adds (LOST_ZONE, STADIUM_ZONE). Others: none.
        """
        return []

    def register_system_interceptors(self, game) -> None:
        """
        Mode-specific system-level interceptors registered on Game init.
        HS: Divine Shield + Immune PREVENT interceptors on DAMAGE.
        Others: none.
        """
        return None

    # ---------------------------------------------------------------
    # Game start / ai registration
    # ---------------------------------------------------------------

    def delegates_start_to_session(self) -> bool:
        """
        If True, Game.start_game() returns early after setting the turn order;
        the session layer drives setup (PKM.setup_game, YGO.setup_game).
        For YGO, even setting the turn order is skipped — see start_game's
        pre-existing branch behavior.
        """
        return False

    def skips_turn_order_setup(self) -> bool:
        """
        If True, Game.start_game() returns before even calling set_turn_order
        (YGO: the turn manager's setup_game has already done it).
        """
        return False

    def shuffle_turn_order(self, player_ids: list) -> list:
        """
        Reorder player_ids before turn order is set. HS: random shuffle.
        Default: preserve original order.
        """
        return player_ids

    async def setup_starting_hands(self, game, player_ids: list) -> bool:
        """
        Hook for drawing starting hands and running mulligans.
        Return True if the adapter handled it (skip default MTG mulligans).
        Default: returns False so MTG's London Mulligan runs.
        """
        return False

    def register_ai_player(self, game, player_id: str) -> None:
        """
        Mode-specific AI-player registration beyond priority_system.set_ai_player.
        HS/PKM: pass to turn_manager.set_ai_player if present.
        YGO: add to turn_manager.ai_players.
        """
        return None

    # ---------------------------------------------------------------
    # Server-layer serialization flags
    # ---------------------------------------------------------------

    def excludes_from_battlefield_serialization(self, obj) -> bool:
        """
        Hide objects from the serialized battlefield list (HS hides HERO and
        HERO_POWER because those render inside PlayerData). Default: False.
        """
        return False

    def uses_pokemon_card_serializer(self) -> bool:
        """PKM uses _serialize_pokemon_card for graveyard/hand. Default: False."""
        return False

    def includes_game_log_in_state(self) -> bool:
        """PKM and YGO surface a game log in the client state. Default: False."""
        return False

    def tap_ability_blocked_by_summoning_sickness(
        self,
        obj: "GameObject",
        state: "GameState",
    ) -> bool:
        """
        Should this creature be prevented from activating a `{T}: Add` ability
        due to summoning sickness?
        MTG: same-timestamp entry blocks tap unless the creature has haste.
        HS: uses the explicit `obj.state.summoning_sickness` flag directly.
        """
        if obj.entered_zone_at == state.timestamp:
            from .queries import has_ability
            if not has_ability(obj, 'haste', state):
                return True
        return False


# =============================================================================
# MTG — the default; all hooks inherited unchanged
# =============================================================================

class MTGModeAdapter(GameModeAdapter):
    mode: str = "mtg"


# =============================================================================
# Hearthstone
# =============================================================================

class HearthstoneModeAdapter(GameModeAdapter):
    mode: str = "hearthstone"

    def default_max_hand_size(self):
        return 10

    def create_mana_system(self, state):
        from .hearthstone_mana import HearthstoneManaSystem
        return HearthstoneManaSystem(state)

    def create_combat_manager(self, state):
        from .hearthstone_combat import HearthstoneCombatManager
        return HearthstoneCombatManager(state)

    def create_turn_manager(self, state):
        from .hearthstone_turn import HearthstoneTurnManager
        return HearthstoneTurnManager(state)

    def hand_size_limit(self, player, state):
        return state.max_hand_size

    def overdraw_burns(self, state):
        return True

    def max_minions_on_board(self, controller_id, state):
        return 7

    def apply_player_damage(self, player, amount, state):
        # HS: direct-to-player damage should be redirected through the hero
        # so armor is applied. If a hero exists we consume it here.
        if player.hero_id and player.hero_id in state.objects:
            hero = state.objects[player.hero_id]
            remaining = amount
            if player.armor > 0:
                absorbed = min(player.armor, remaining)
                player.armor -= absorbed
                remaining -= absorbed
            if remaining > 0:
                player.life -= remaining
                hero.state.damage += remaining
            return 0
        # Fallback: no hero registered — subtract raw.
        player.life -= amount
        return 0

    def handles_hero_damage(self):
        return True

    def apply_hero_damage(self, hero, player, amount, state):
        # Armor first.
        remaining = amount
        if player.armor > 0:
            absorbed = min(player.armor, remaining)
            player.armor -= absorbed
            remaining -= absorbed
        if remaining > 0:
            player.life -= remaining
            hero.state.damage += remaining

    def post_creature_damage_destroy_check(self, obj, event, state):
        from .types import Event, EventType, CardType
        from .queries import get_toughness

        source_obj = state.objects.get(event.source) if event.source else None
        is_spell_damage = bool(event.payload.get('from_spell'))
        if source_obj and CardType.SPELL in source_obj.characteristics.types:
            is_spell_damage = True
        if not is_spell_damage:
            return []

        toughness = get_toughness(obj, state)
        if toughness is not None and obj.state.damage >= toughness:
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj.id, 'reason': 'lethal_damage'},
                source=event.source,
                controller=event.controller,
            )]
        return []

    def life_cap(self, player, state):
        return getattr(player, 'max_life', 30) or 30

    def sync_hero_damage_with_life(self, player, hero, state):
        max_hp = self.life_cap(player, state) or 30
        hero.state.damage = max(0, max_hp - player.life)

    def handle_empty_library_draw(self, player, state):
        from .types import Event, EventType
        player.fatigue_damage += 1
        if not player.hero_id:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={
                'target': player.hero_id,
                'amount': player.fatigue_damage,
                'source': 'fatigue',
            }
        )]

    def on_leave_battlefield_to_hidden(self, obj, from_zone_type, to_zone_type, state):
        from .types import ZoneType, CardType
        if from_zone_type != ZoneType.BATTLEFIELD:
            return
        if to_zone_type not in (ZoneType.HAND, ZoneType.LIBRARY):
            return
        if CardType.MINION not in obj.characteristics.types:
            return

        obj.state.damage = 0
        obj.state.divine_shield = False
        obj.state.stealth = False
        obj.state.windfury = False
        obj.state.frozen = False
        obj.state.summoning_sickness = True
        if hasattr(obj.state, 'pt_modifiers'):
            obj.state.pt_modifiers = []

        # Restore original characteristics from card_def if available
        if obj.card_def and obj.card_def.characteristics:
            import copy
            obj.characteristics = copy.deepcopy(obj.card_def.characteristics)
            obj_keywords = {
                a.get('keyword', '').lower()
                for a in obj.characteristics.abilities
                if isinstance(a, dict) and a.get('keyword')
            }
            if 'divine_shield' in obj_keywords:
                obj.state.divine_shield = True
            if 'stealth' in obj_keywords:
                obj.state.stealth = True
            if 'windfury' in obj_keywords:
                obj.state.windfury = True
            if 'charge' in obj_keywords:
                obj.state.summoning_sickness = False

    def on_weapon_destroyed(self, obj, event, state):
        from .types import CardType
        if CardType.WEAPON not in obj.characteristics.types:
            return
        if event.payload.get('reason') == 'weapon_replaced':
            return
        player = state.players.get(obj.controller)
        if player:
            player.weapon_attack = 0
            player.weapon_durability = 0
        hero_id = player.hero_id if player else None
        if hero_id and hero_id in state.objects:
            hero = state.objects[hero_id]
            hero.state.weapon_attack = 0
            hero.state.weapon_durability = 0

    def tap_ability_blocked_by_summoning_sickness(self, obj, state):
        return bool(obj.state.summoning_sickness)

    def shuffle_turn_order(self, player_ids):
        import random
        order = list(player_ids)
        random.shuffle(order)
        return order

    async def setup_starting_hands(self, game, player_ids):
        """HS: P1 draws 3, P2 draws 4 + The Coin."""
        for i, player_id in enumerate(player_ids):
            draw_count = 3 if i == 0 else 4
            game.draw_cards(player_id, draw_count)
        if len(player_ids) > 1:
            from src.cards.hearthstone.basic import THE_COIN
            import copy
            from .types import ZoneType
            game.create_object(
                name="The Coin",
                owner_id=player_ids[1],
                zone=ZoneType.HAND,
                characteristics=copy.deepcopy(THE_COIN.characteristics),
                card_def=THE_COIN,
            )
        return True

    def register_ai_player(self, game, player_id):
        if hasattr(game.turn_manager, 'set_ai_player'):
            game.turn_manager.set_ai_player(player_id)

    def excludes_from_battlefield_serialization(self, obj):
        from .types import CardType
        return (
            CardType.HERO in obj.characteristics.types
            or CardType.HERO_POWER in obj.characteristics.types
        )

    def register_system_interceptors(self, game):
        """Register HS's Divine Shield + Immune PREVENT interceptors."""
        from .types import (
            Event, EventType, Interceptor, InterceptorPriority,
            InterceptorAction, InterceptorResult, new_id,
        )
        from .queries import has_ability

        def _divine_shield_filter(event, state):
            if event.type != EventType.DAMAGE:
                return False
            target_ref = event.payload.get("target")
            target_id = target_ref[0] if isinstance(target_ref, list) and target_ref else target_ref
            if not isinstance(target_id, str):
                return False
            target = state.objects.get(target_id)
            if target is None:
                return False
            if has_ability(target, "immune", state):
                return False
            return target.state.divine_shield

        def _divine_shield_handler(event, state):
            target_ref = event.payload.get("target")
            target_id = target_ref[0] if isinstance(target_ref, list) and target_ref else target_ref
            if not isinstance(target_id, str) or target_id not in state.objects:
                return InterceptorResult(action=InterceptorAction.PASS)
            target = state.objects[target_id]
            target.state.divine_shield = False
            shield_break = Event(
                type=EventType.DIVINE_SHIELD_BREAK,
                payload={'target': target_id},
                source=event.source,
            )
            return InterceptorResult(
                action=InterceptorAction.PREVENT,
                new_events=[shield_break],
            )

        game.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.PREVENT,
                filter=_divine_shield_filter,
                handler=_divine_shield_handler,
                duration="forever",
            )
        )

        def _immune_filter(event, state):
            if event.type != EventType.DAMAGE:
                return False
            target_ref = event.payload.get("target")
            target_id = target_ref[0] if isinstance(target_ref, list) and target_ref else target_ref
            if not isinstance(target_id, str):
                return False
            target = state.objects.get(target_id)
            return target is not None and has_ability(target, "immune", state)

        def _immune_handler(event, state):
            return InterceptorResult(action=InterceptorAction.PREVENT)

        game.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.PREVENT,
                filter=_immune_filter,
                handler=_immune_handler,
                duration="forever",
            )
        )


# =============================================================================
# Pokemon TCG
# =============================================================================

class PokemonModeAdapter(GameModeAdapter):
    """
    Pokemon's turn manager manipulates zones directly, so most pipeline
    branches don't apply. The adapter mostly inherits MTG defaults.
    """
    mode: str = "pokemon"

    def default_max_hand_size(self):
        return 999  # no practical hand limit

    def create_mana_system(self, state):
        from .pokemon_energy import PokemonEnergySystem
        return PokemonEnergySystem(state)

    def create_combat_manager(self, state):
        from .pokemon_combat import PokemonCombatManager
        return PokemonCombatManager(state)

    def create_turn_manager(self, state):
        from .pokemon_turn import PokemonTurnManager
        return PokemonTurnManager(state)

    def extra_player_zone_types(self):
        from .types import ZoneType
        return [ZoneType.ACTIVE_SPOT, ZoneType.BENCH, ZoneType.PRIZE_CARDS]

    def extra_shared_zone_types(self):
        from .types import ZoneType
        return [ZoneType.LOST_ZONE, ZoneType.STADIUM_ZONE]

    def delegates_start_to_session(self):
        return True

    def uses_pokemon_card_serializer(self):
        return True

    def includes_game_log_in_state(self):
        return True

    def register_ai_player(self, game, player_id):
        if hasattr(game.turn_manager, 'set_ai_player'):
            game.turn_manager.set_ai_player(player_id)


# =============================================================================
# Yu-Gi-Oh!
# =============================================================================

class YugiohModeAdapter(GameModeAdapter):
    """
    YGO keeps MTG-style "lose on empty deck draw" semantics; no armor, no
    board-size cap, no overdraw burn. Most hooks inherit.
    """
    mode: str = "yugioh"

    def default_max_hand_size(self):
        return 6  # End Phase discard-to-6

    def create_mana_system(self, state):
        return None  # YGO has no mana system

    def create_combat_manager(self, state):
        from .yugioh_combat import YugiohCombatManager
        return YugiohCombatManager(state)

    def create_turn_manager(self, state):
        from .yugioh_turn import YugiohTurnManager
        return YugiohTurnManager(state)

    def extra_player_zone_types(self):
        from .types import ZoneType
        return [ZoneType.MONSTER_ZONE, ZoneType.SPELL_TRAP_ZONE,
                ZoneType.FIELD_SPELL_ZONE, ZoneType.PENDULUM_ZONE,
                ZoneType.EXTRA_DECK, ZoneType.BANISHED]

    def delegates_start_to_session(self):
        return True

    def skips_turn_order_setup(self):
        return True

    def includes_game_log_in_state(self):
        return True

    def register_ai_player(self, game, player_id):
        game.turn_manager.ai_players.add(player_id)


# =============================================================================
# Registry
# =============================================================================

_REGISTRY: dict[str, GameModeAdapter] = {
    "mtg": MTGModeAdapter(),
    "hearthstone": HearthstoneModeAdapter(),
    "pokemon": PokemonModeAdapter(),
    "yugioh": YugiohModeAdapter(),
}


def get_mode_adapter(game_mode: str) -> GameModeAdapter:
    """Look up the adapter for a given mode string. Unknown modes fall back to MTG."""
    adapter = _REGISTRY.get(game_mode)
    if adapter is None:
        return _REGISTRY["mtg"]
    return adapter
