"""
Damage, life, armor, and weapon-equip handlers.
"""

from ...types import Event, GameState, CardType


def _handle_damage(event: Event, state: GameState):
    """Handle DAMAGE event."""
    from ...mode_adapter import get_mode_adapter
    adapter = get_mode_adapter(state.game_mode)

    target_id = event.payload.get('target')
    amount = event.payload.get('amount', 0)

    if amount <= 0:
        return

    # Damage to player
    if target_id in state.players:
        player = state.players[target_id]
        adapter.apply_player_damage(player, amount, state)
        return

    # Damage to creature/hero
    if target_id in state.objects:
        obj = state.objects[target_id]

        # Note: Divine Shield is handled by a PREVENT interceptor registered in
        # Game.__init__. DAMAGE events targeting shielded minions are prevented
        # before reaching this handler.

        # Damage to HERO — delegated to the adapter. HS is the only mode that
        # treats HERO specially; other modes never had this branch and fall
        # through to the regular creature damage path.
        if CardType.HERO in obj.characteristics.types and adapter.handles_hero_damage():
            player = state.players.get(obj.owner)
            if player is not None:
                adapter.apply_hero_damage(obj, player, amount, state)
            return

        # Regular creature damage
        obj.state.damage += amount

        # Mode-specific: HS synchronously destroys on lethal spell damage.
        follow_ups = adapter.post_creature_damage_destroy_check(obj, event, state)
        if follow_ups:
            return follow_ups


def _handle_life_change(event: Event, state: GameState):
    """Handle LIFE_CHANGE event."""
    from ...mode_adapter import get_mode_adapter
    adapter = get_mode_adapter(state.game_mode)

    player_id = event.payload.get('player')
    object_id = event.payload.get('object_id') or event.payload.get('target')
    amount = event.payload.get('amount', 0)

    if player_id in state.players:
        player = state.players[player_id]
        player.life += amount
        # Cap healing at the life cap (HS: max_hp, default 30). MTG: no cap.
        cap = adapter.life_cap(player, state)
        if cap is not None and amount > 0:
            player.life = min(player.life, cap)
        # Sync hero.state.damage (HS). MTG: no-op.
        if player.hero_id and player.hero_id in state.objects:
            hero = state.objects[player.hero_id]
            adapter.sync_hero_damage_with_life(player, hero, state)
        return

    # Support object-based healing payloads used by Hearthstone card scripts.
    if object_id in state.objects:
        obj = state.objects[object_id]

        # Hero object healing should also update owning player's life.
        if CardType.HERO in obj.characteristics.types:
            player = state.players.get(obj.owner)
            if not player:
                return
            player.life += amount
            cap = adapter.life_cap(player, state)
            if cap is not None and amount > 0:
                player.life = min(player.life, cap)
            adapter.sync_hero_damage_with_life(player, obj, state)
            return

        # Minion/object healing: reduce marked damage; negative amounts add damage.
        if amount >= 0:
            obj.state.damage = max(0, obj.state.damage - amount)
        else:
            obj.state.damage += abs(amount)


def _handle_armor_gain(event: Event, state: GameState):
    """Handle ARMOR_GAIN event — increment player's armor."""
    player_id = event.payload.get('player')
    amount = event.payload.get('amount', 0)
    if amount > 0 and player_id in state.players:
        state.players[player_id].armor += amount


def _handle_weapon_equip(event: Event, state: GameState):
    """Handle WEAPON_EQUIP event — set player's weapon stats."""
    # Ignore synthetic events from unknown sources (legacy tests emit
    # WEAPON_EQUIP as informational markers with source='test').
    if event.source is not None and event.source not in state.objects:
        return

    player_id = event.payload.get('player')
    if not player_id:
        hero_id = event.payload.get('hero_id')
        if hero_id in state.objects:
            player_id = state.objects[hero_id].owner

    if player_id in state.players:
        player = state.players[player_id]
        attack = event.payload.get('weapon_attack')
        durability = event.payload.get('weapon_durability')
        if attack is None:
            attack = event.payload.get('attack', 0)
        if durability is None:
            durability = event.payload.get('durability', 0)

        player.weapon_attack = max(0, int(attack))
        player.weapon_durability = max(0, int(durability))

        if player.hero_id and player.hero_id in state.objects:
            hero = state.objects[player.hero_id]
            hero.state.weapon_attack = player.weapon_attack
            hero.state.weapon_durability = player.weapon_durability
