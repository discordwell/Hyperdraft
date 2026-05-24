"""
Clankers Combat Manager.

The combat phase resolver for the Clankers game engine. See
``docs/games/clankers.md`` §5 for the combat math design and
``docs/games/clankers_contract.md`` §2 for the interface contract.

Pipeline (per combat phase)::

    declare attackers -> declare blockers -> assign damage (simultaneous)
        -> workshop damage routing -> state-based check / death cascade
        -> reset attacking / blocking flags (damage_marked persists)

This manager is invoked by the Clankers turn manager during the Combat
phase via :meth:`resolve_combat_phase`. AI decisions flow in through
``game.clankers_ai_handlers[player_id]`` (a per-player dict — re-fetched
each call so per-player swaps work). Combat events emit through the
standard pipeline so card interceptors (armor, on_host_attack,
on_self_destroyed, etc.) fire correctly.

Notes on damage routing:
    * Chassis combat damage is marked directly onto ``obj.state.damage_marked``
      and SBA-checked against the chassis's effective integrity. Damage marked
      PERSISTS across turns (Clankers rule, distinct from MTG).
    * Workshop damage targets a player_id, not an object. This module's
      ``resolve_combat_phase`` handles the workshop damage inline — there is
      no separate pipeline handler — so the call site for any future cards
      that emit ``CLANKERS_WORKSHOP_DAMAGE`` (Transients, abilities) must
      route through the same helper or duplicate the routing.

Ownership:
    Owns ONLY this file. Helpers — ``compute_effective_power``,
    ``compute_effective_integrity``, ``death_cascade``, plus the engine
    constants ``CLANKERS_SOLO_PART_POWER`` / ``CLANKERS_SOLO_PART_INTEGRITY``
    — come from ``src.engine.clankers``.
"""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)
from .clankers import (
    CLANKERS_SOLO_PART_POWER,
    CLANKERS_SOLO_PART_INTEGRITY,
    compute_effective_power as _clankers_compute_effective_power,
    compute_effective_integrity as _clankers_compute_effective_integrity,
    death_cascade as _clankers_death_cascade,
)


# ---------------------------------------------------------------------------
# Type predicates
# ---------------------------------------------------------------------------

def _is_chassis(obj: Optional[GameObject]) -> bool:
    if obj is None:
        return False
    try:
        return CardType.CLANKERS_CHASSIS in obj.characteristics.types
    except AttributeError:
        return False


def _is_weapon(obj: Optional[GameObject]) -> bool:
    if obj is None:
        return False
    try:
        return CardType.CLANKERS_WEAPON in obj.characteristics.types
    except AttributeError:
        return False


def _is_add_on(obj: Optional[GameObject]) -> bool:
    if obj is None:
        return False
    try:
        return CardType.CLANKERS_ADD_ON in obj.characteristics.types
    except AttributeError:
        return False


def _is_solo_part(obj: Optional[GameObject]) -> bool:
    """True if ``obj`` is a weapon or add-on currently NOT attached to any
    chassis (a standalone part on the Assembly Floor).
    """
    if obj is None:
        return False
    if not (_is_weapon(obj) or _is_add_on(obj)):
        return False
    return getattr(obj.state, "attached_to", None) is None


def _on_assembly_floor(obj: Optional[GameObject], state: GameState) -> bool:
    """True if ``obj`` is sitting on the Assembly Floor.

    Either ``obj.zone == ZoneType.CLANKERS_ASSEMBLY_FLOOR`` (the canonical
    indicator after a successful ``play_card_from_hand``) or the chassis
    has been registered in ``state.clankers_assemblies`` for its controller.
    """
    if obj is None:
        return False
    if obj.zone == ZoneType.CLANKERS_ASSEMBLY_FLOOR:
        return True
    assemblies = getattr(state, "clankers_assemblies", None)
    if isinstance(assemblies, dict):
        pid = obj.controller
        if pid and obj.id in (assemblies.get(pid) or []):
            return True
    return False


def _has_clankers_keyword(obj: Optional[GameObject], keyword: str) -> bool:
    """Read ``clankers_keywords`` off the card_def (preferred) or the
    object's state mirror.
    """
    if obj is None:
        return False
    card_def = getattr(obj, "card_def", None)
    if card_def is not None:
        kws = getattr(card_def, "clankers_keywords", None) or []
        if keyword in kws:
            return True
    kws = getattr(obj.state, "clankers_keywords", None) or []
    return keyword in kws


# ---------------------------------------------------------------------------
# Solo-part stat helpers
# ---------------------------------------------------------------------------

def _solo_part_effective_power(obj: GameObject) -> int:
    """A solo part hits for ``CLANKERS_SOLO_PART_POWER`` (== 1) by default.
    The card's printed ``power_bonus`` only applies when attached — UNLESS
    the card has the ``self_mobile`` clankers_keyword, in which case the
    bonus is granted while solo as well.
    """
    base = int(CLANKERS_SOLO_PART_POWER)
    if _has_clankers_keyword(obj, "self_mobile"):
        card_def = getattr(obj, "card_def", None)
        bonus = int(getattr(card_def, "power_bonus", 0) or 0) if card_def else 0
        base += bonus
    return base


def _solo_part_effective_integrity(obj: GameObject) -> int:
    """A solo part has ``CLANKERS_SOLO_PART_INTEGRITY`` (== 1) integrity by
    default. ``self_mobile`` grants the printed ``integrity_bonus`` as well.
    """
    base = int(CLANKERS_SOLO_PART_INTEGRITY)
    if _has_clankers_keyword(obj, "self_mobile"):
        card_def = getattr(obj, "card_def", None)
        bonus = int(getattr(card_def, "integrity_bonus", 0) or 0) if card_def else 0
        base += bonus
    return base


def _effective_power(state: GameState, obj: GameObject) -> int:
    """Dispatch to the right power computation depending on chassis vs solo
    part. Chassis go through Agent 1's pipeline-aware
    :func:`compute_effective_power` (which honours static effects). Solo
    parts use the flat baseline + self_mobile rule.
    """
    if obj is None:
        return 0
    if _is_chassis(obj):
        return int(_clankers_compute_effective_power(state, obj.id))
    if _is_solo_part(obj):
        return _solo_part_effective_power(obj)
    # Unknown object type — assume printed power.
    card_def = getattr(obj, "card_def", None)
    return int(getattr(card_def, "power", 0) or 0) if card_def else 0


def _effective_integrity(state: GameState, obj: GameObject) -> int:
    if obj is None:
        return 0
    if _is_chassis(obj):
        return int(_clankers_compute_effective_integrity(state, obj.id))
    if _is_solo_part(obj):
        return _solo_part_effective_integrity(obj)
    card_def = getattr(obj, "card_def", None)
    return int(getattr(card_def, "integrity", 0) or 0) if card_def else 0


# ---------------------------------------------------------------------------
# ClankersCombatManager
# ---------------------------------------------------------------------------

class ClankersCombatManager:
    """Resolves the Combat phase for a Clankers game.

    Constructed once per game by the turn manager (Agent 3). Call
    :meth:`resolve_combat_phase` exactly once per Combat phase. The manager
    is stateless across phases — all bookkeeping lives on ``state``.
    """

    def __init__(self, game_or_state: Any) -> None:
        """Accept either a ``Game`` (per contract §2) or a ``GameState``.

        The mode_adapter factory passes ``state``, but a Game is also
        accepted for direct construction. Either way we resolve both
        ``self.game`` and ``self.state`` so AI lookup works.
        """
        # If we got a Game, it has a `.state` attribute. If we got a state,
        # the Game (if wired) is reachable via state._game.
        if isinstance(game_or_state, GameState):
            self.state: GameState = game_or_state
            self.game: Any = getattr(game_or_state, "_game", None) or game_or_state
        else:
            self.game = game_or_state
            self.state = getattr(game_or_state, "state", None)
            # When a Game is passed and it has state, ensure state._game is set
            # so downstream consumers can reach it.
            if self.state is not None and not hasattr(self.state, "_game"):
                try:
                    setattr(self.state, "_game", self.game)
                except Exception:
                    pass

    # ------------------------------------------------------------------ utils

    def _get_state(self) -> GameState:
        """Return the current GameState — re-resolved each call so
        post-construction Game swaps still work."""
        # If self.game is a Game, prefer game.state (live reference).
        s = getattr(self.game, "state", None)
        if isinstance(s, GameState):
            self.state = s
            return s
        return self.state

    def _emit(self, event: Event) -> Event:
        """Best-effort pipeline emit. Mirrors depths_combat / cats_combat:
        when a Game with ``emit`` is present we go through it (so card
        interceptors fire); otherwise we append to ``state.event_log`` for
        observability.
        """
        try:
            if self.game is not None and hasattr(self.game, "emit"):
                self.game.emit(event)
            else:
                state = self._get_state()
                if state is not None:
                    state.event_log.append(event)
        except Exception:
            # Defensive: never let a misbehaving interceptor break the
            # combat-phase resolution. Tests that want strict-mode emission
            # can monkeypatch self._emit.
            state = self._get_state()
            if state is not None:
                state.event_log.append(event)
        return event

    def _get_ai(self, player_id: str) -> Any:
        """Look up the AI adapter for ``player_id``.

        Per contract §6, the canonical lookup is ``game.clankers_ai_handlers``
        (plural, namespaced — mirrors the depths pattern). We also consult
        the turn-manager-resident dict so callers that registered via
        ``turn_manager.set_ai_handler`` are honoured.

        Works whether ``self.game`` is the Game object or the raw GameState
        — when it's the state, we hop through ``state._game`` to find the
        real Game and then look at ``game.turn_manager``.
        """
        # If self.game is actually a Game (preferred), check it directly.
        handler_map = getattr(self.game, "clankers_ai_handlers", None)
        if isinstance(handler_map, dict):
            ai = handler_map.get(player_id)
            if ai is not None:
                return ai

        # Find the real Game — either self.game (if it has a turn_manager)
        # or state._game.
        real_game = self.game if hasattr(self.game, "turn_manager") else None
        if real_game is None:
            state = self._get_state()
            real_game = getattr(state, "_game", None) if state is not None else None

        if real_game is not None:
            handler_map = getattr(real_game, "clankers_ai_handlers", None)
            if isinstance(handler_map, dict):
                ai = handler_map.get(player_id)
                if ai is not None:
                    return ai
            tm = getattr(real_game, "turn_manager", None)
            if tm is not None:
                tm_map = getattr(tm, "clankers_ai_handlers", None)
                if isinstance(tm_map, dict):
                    ai = tm_map.get(player_id)
                    if ai is not None:
                        return ai
                shared = getattr(tm, "clankers_ai_handler", None)
                if shared is not None:
                    return shared
        return None

    def _derive_defender(self, attacker_player_id: str) -> Optional[str]:
        """Return the *other* player_id in ``state.players``.

        Clankers v1 is strictly 1v1 per docs/games/clankers.md; a 3+-player
        variant would need an explicit ``defender_id`` arg.
        """
        state = self._get_state()
        if state is None or not state.players:
            return None
        for pid in state.players:
            if pid != attacker_player_id:
                return pid
        return None

    # ----------------------------------------------------------- validation

    def _validate_attacker(
        self,
        state: GameState,
        obj_id: str,
        attacker_player_id: str,
    ) -> bool:
        """Check that ``obj_id`` is a legal attacker for
        ``attacker_player_id``.

        Legal attackers:
            * Controlled by the attacker player
            * On the Assembly Floor
            * Untapped
            * Either a chassis OR an unattached weapon / add-on (solo part)
        """
        obj = state.objects.get(obj_id)
        if obj is None:
            return False
        if obj.controller != attacker_player_id:
            return False
        if not _on_assembly_floor(obj, state):
            return False
        if getattr(obj.state, "tapped", False):
            return False
        if _is_chassis(obj):
            return True
        if _is_solo_part(obj):
            return True
        return False

    def _validate_blocker(
        self,
        state: GameState,
        blocker_id: str,
        defender_id: str,
    ) -> bool:
        """Check that ``blocker_id`` is a legal blocker for ``defender_id``.

        Legal blockers:
            * Controlled by the defender
            * On the Assembly Floor
            * Untapped
            * Either a chassis OR a solo part (mirror of attacker rules —
              a solo weapon can chump-block)
        """
        obj = state.objects.get(blocker_id)
        if obj is None:
            return False
        if obj.controller != defender_id:
            return False
        if not _on_assembly_floor(obj, state):
            return False
        if getattr(obj.state, "tapped", False):
            return False
        if not (_is_chassis(obj) or _is_solo_part(obj)):
            return False
        return True

    # -------------------------------------------------------- workshop dmg

    def _route_workshop_damage(
        self,
        state: GameState,
        target_player: str,
        amount: int,
        source_id: str,
        damage_credited_to: str,
    ) -> list[Event]:
        """Inline workshop-damage handler.

        Emits the ``CLANKERS_WORKSHOP_DAMAGE`` event (so cards can intercept
        it pre-application), then mutates
        ``state.clankers_workshop_integrity[target_player]`` accordingly.
        If integrity reaches 0, emits ``CLANKERS_WORKSHOP_BREACHED`` plus
        ``PLAYER_LOSES`` / ``PLAYER_WINS`` markers and flips ``game_over``
        on whichever container owns it.

        Returns the events emitted (in order).
        """
        emitted: list[Event] = []
        if amount <= 0:
            return emitted

        # Emit the workshop damage event itself first — TRANSFORM interceptors
        # on this event (e.g. "your Core takes 1 less damage from unblocked
        # attackers") can reduce the amount. We read back the final amount
        # from the post-emit event's payload.
        dmg_event = Event(
            type=EventType.CLANKERS_WORKSHOP_DAMAGE,
            payload={
                "target_player": target_player,
                "amount": int(amount),
                "source": source_id,
                "damage_credited_to": damage_credited_to,
            },
            source=source_id,
            controller=damage_credited_to,
        )
        self._emit(dmg_event)
        emitted.append(dmg_event)
        # The pipeline may have TRANSFORMed the amount via interceptors;
        # respect it.
        final_amount = int(dmg_event.payload.get("amount", amount) or 0)
        if final_amount <= 0:
            return emitted

        # Apply damage to the workshop integrity. Defensive default of
        # 0 if Agent 1's setup hasn't populated the dict yet — in that
        # case the game would have been initialized incorrectly, but we
        # still avoid a KeyError to keep tests informative.
        wsi = getattr(state, "clankers_workshop_integrity", None)
        if not isinstance(wsi, dict):
            wsi = {}
            try:
                setattr(state, "clankers_workshop_integrity", wsi)
            except Exception:
                pass

        current = int(wsi.get(target_player, 0) or 0)
        new_val = max(0, current - final_amount)
        wsi[target_player] = new_val

        if new_val <= 0:
            # Mark the loser on state so finalisation logic can read it.
            try:
                setattr(state, "clankers_loser", target_player)
            except Exception:
                pass

            breach = Event(
                type=EventType.CLANKERS_WORKSHOP_BREACHED,
                payload={"player_id": target_player},
                source=source_id,
                controller=damage_credited_to,
            )
            self._emit(breach)
            emitted.append(breach)

            # PLAYER_LOSES / PLAYER_WINS — use them if available; otherwise
            # at least set has_lost on the loser so engine win-checks fire.
            player_loses_type = getattr(EventType, "PLAYER_LOSES", None)
            player_wins_type = getattr(EventType, "PLAYER_WINS", None)
            if player_loses_type is not None:
                lose_ev = Event(
                    type=player_loses_type,
                    payload={
                        "player_id": target_player,
                        "reason": "workshop_breached",
                    },
                    source=source_id,
                    controller=damage_credited_to,
                )
                self._emit(lose_ev)
                emitted.append(lose_ev)
            if player_wins_type is not None:
                # Winner is the other player.
                winner_id = None
                for pid in state.players:
                    if pid != target_player:
                        winner_id = pid
                        break
                if winner_id:
                    win_ev = Event(
                        type=player_wins_type,
                        payload={
                            "player_id": winner_id,
                            "reason": "opponent_workshop_breached",
                        },
                        source=source_id,
                        controller=winner_id,
                    )
                    self._emit(win_ev)
                    emitted.append(win_ev)

            # Best-effort game-over flagging across container shapes.
            try:
                player = state.players.get(target_player)
                if player is not None:
                    player.has_lost = True
            except Exception:
                pass
            for attr_owner in (state, self.game):
                if attr_owner is None:
                    continue
                try:
                    setattr(attr_owner, "game_over", True)
                except Exception:
                    pass

        return emitted

    # -------------------------------------------------------- state-based

    def _apply_lethal_check(
        self,
        state: GameState,
        candidates: list[str],
        kill_credit: dict[str, str],
    ) -> list[Event]:
        """For each candidate object_id, check if ``damage_marked >=
        effective_integrity``. If so, destroy it (chassis -> cascade,
        weapon/add-on -> just the marker + OBJECT_DESTROYED).

        ``kill_credit`` maps obj_id -> player_id who killed it (the
        controller of the source). Used so the OBJECT_DESTROYED carries an
        explicit attribution.

        Returns the events emitted (in order).
        """
        emitted: list[Event] = []
        for cand_id in list(candidates):
            obj = state.objects.get(cand_id)
            if obj is None:
                continue
            damage_marked = int(getattr(obj.state, "damage_marked", 0) or 0)
            if damage_marked <= 0:
                continue
            eff_int = _effective_integrity(state, obj)
            if eff_int <= 0:
                # A 0-integrity object on the floor (e.g. a buffed-then-debuffed
                # solo part) dies as soon as it takes any damage.
                pass
            if damage_marked < eff_int:
                continue

            killer = kill_credit.get(cand_id) or obj.controller

            if _is_chassis(obj):
                # Delegate to clankers.death_cascade — it emits the
                # CLANKERS_CHASSIS_DESTROYED + CLANKERS_DEATH_CASCADE markers,
                # scatters attached parts to scrap, and emits the
                # per-part destruction + OBJECT_DESTROYED events.
                # Pass the kill_credited_to along via a controller-attached
                # post-hook by setting it on the chassis's last-damage tag —
                # the helper itself doesn't take a killer arg yet, so we
                # patch the controller fields on the returned events.
                cascade_events = _clankers_death_cascade(state, cand_id) or []
                for ev in cascade_events:
                    # Carry kill_credited_to forward on the first chassis-
                    # destroyed marker so on_destroyed observers see who
                    # killed it (combat attribution).
                    if (
                        ev.type == EventType.CLANKERS_CHASSIS_DESTROYED
                        and "kill_credited_to" not in ev.payload
                    ):
                        ev.payload["kill_credited_to"] = killer
                        ev.payload.setdefault("reason", "combat_damage")
                    self._emit(ev)
                    emitted.append(ev)
            elif _is_weapon(obj):
                marker = Event(
                    type=EventType.CLANKERS_WEAPON_DESTROYED,
                    payload={
                        "object_id": cand_id,
                        "kill_credited_to": killer,
                        "controller": obj.controller,
                        "reason": "combat_damage",
                    },
                    source=cand_id,
                    controller=obj.controller,
                )
                self._emit(marker)
                emitted.append(marker)
                obj_destroyed = Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={
                        "object_id": cand_id,
                        "kill_credited_to": killer,
                        "reason": "combat_damage",
                    },
                    source=cand_id,
                    controller=obj.controller,
                )
                self._emit(obj_destroyed)
                emitted.append(obj_destroyed)
            elif _is_add_on(obj):
                marker = Event(
                    type=EventType.CLANKERS_ADD_ON_DESTROYED,
                    payload={
                        "object_id": cand_id,
                        "kill_credited_to": killer,
                        "controller": obj.controller,
                        "reason": "combat_damage",
                    },
                    source=cand_id,
                    controller=obj.controller,
                )
                self._emit(marker)
                emitted.append(marker)
                obj_destroyed = Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={
                        "object_id": cand_id,
                        "kill_credited_to": killer,
                        "reason": "combat_damage",
                    },
                    source=cand_id,
                    controller=obj.controller,
                )
                self._emit(obj_destroyed)
                emitted.append(obj_destroyed)
            # Other object types (Structures, Cores) cannot be combat-killed
            # — Structures are untargetable by attacks per design, Cores
            # take damage via workshop integrity routing only.

        return emitted

    # ------------------------------------------------------------- public

    def resolve_combat_phase(
        self, attacker_player_id: str
    ) -> list[Event]:
        """Resolve a full Combat phase for ``attacker_player_id``.

        Returns the list of all events emitted by this manager during the
        phase (declarations, damage, destruction markers, workshop damage,
        breach events). Does NOT include events that downstream
        interceptors queued onto the pipeline — only what this module
        directly authored.

        Single public entry point per the Stage-1 contract.
        """
        state = self._get_state()
        emitted: list[Event] = []
        if state is None:
            return emitted

        defender_id = self._derive_defender(attacker_player_id)
        if not defender_id:
            return emitted

        # ------------------------------------------------------------------
        # Step 1: choose & validate attackers
        # ------------------------------------------------------------------
        attacker_ai = self._get_ai(attacker_player_id)
        raw_attackers: list[str] = []
        if attacker_ai is not None and hasattr(attacker_ai, "choose_attackers"):
            try:
                result = attacker_ai.choose_attackers(state, attacker_player_id)
            except Exception:
                result = []
            if isinstance(result, (list, tuple)):
                raw_attackers = [a for a in result if isinstance(a, str)]

        valid_attackers: list[str] = []
        for a_id in raw_attackers:
            if self._validate_attacker(state, a_id, attacker_player_id):
                valid_attackers.append(a_id)

        # Emit ATTACK_DECLARE per valid attacker; tap and flag them.
        for a_id in valid_attackers:
            atk = state.objects.get(a_id)
            if atk is None:
                continue
            atk.state.attacking = True
            atk.state.tapped = True
            declare = Event(
                type=EventType.CLANKERS_ATTACK_DECLARE,
                payload={
                    "attacker_id": a_id,
                    "attacker_controller": attacker_player_id,
                },
                source=a_id,
                controller=attacker_player_id,
            )
            self._emit(declare)
            emitted.append(declare)

        # Early exit if no attackers — defender doesn't even get prompted.
        if not valid_attackers:
            return emitted

        # ------------------------------------------------------------------
        # Step 2: choose & validate blockers
        # ------------------------------------------------------------------
        defender_ai = self._get_ai(defender_id)
        raw_blocks: dict[str, str] = {}
        if defender_ai is not None and hasattr(defender_ai, "choose_blockers"):
            try:
                result = defender_ai.choose_blockers(
                    state, defender_id, list(valid_attackers)
                )
            except Exception:
                result = {}
            if isinstance(result, dict):
                raw_blocks = {
                    str(k): str(v)
                    for k, v in result.items()
                    if isinstance(k, str) and isinstance(v, str)
                }

        # Validate: blocker must be legal, must not be reused, must pair
        # with one of the declared attackers.
        block_map: dict[str, str] = {}
        used_blockers: set[str] = set()
        attacker_set = set(valid_attackers)
        for atk_id, blk_id in raw_blocks.items():
            if atk_id not in attacker_set:
                continue
            if blk_id in used_blockers:
                continue
            if not self._validate_blocker(state, blk_id, defender_id):
                continue
            blocker = state.objects.get(blk_id)
            if blocker is None:
                continue
            blocker.state.blocking = True
            used_blockers.add(blk_id)
            block_map[atk_id] = blk_id

            declare = Event(
                type=EventType.CLANKERS_BLOCK_DECLARE,
                payload={
                    "attacker_id": atk_id,
                    "blocker_id": blk_id,
                    "blocker_controller": defender_id,
                },
                source=blk_id,
                controller=defender_id,
            )
            self._emit(declare)
            emitted.append(declare)

        # ------------------------------------------------------------------
        # Step 3: damage step
        # ------------------------------------------------------------------
        # Compute all effective powers up front so the simultaneous damage
        # resolution can't observe intermediate damage_marked changes (i.e.
        # both sides land their full hit before any SBA check).
        attacker_powers: dict[str, int] = {}
        blocker_powers: dict[str, int] = {}
        for atk_id in valid_attackers:
            atk = state.objects.get(atk_id)
            attacker_powers[atk_id] = _effective_power(state, atk) if atk else 0
        for atk_id, blk_id in block_map.items():
            blk = state.objects.get(blk_id)
            blocker_powers[blk_id] = _effective_power(state, blk) if blk else 0

        # Track who killed what for kill_credited_to attribution on SBA.
        kill_credit: dict[str, str] = {}
        # Track which objects took damage this combat — we only need to SBA
        # check those.
        damaged_objects: list[str] = []

        for atk_id in valid_attackers:
            atk = state.objects.get(atk_id)
            if atk is None:
                continue
            atk_power = int(attacker_powers.get(atk_id, 0) or 0)

            blk_id = block_map.get(atk_id)
            if blk_id is None:
                # Unblocked — workshop damage to defender.
                workshop_events = self._route_workshop_damage(
                    state,
                    target_player=defender_id,
                    amount=atk_power,
                    source_id=atk_id,
                    damage_credited_to=attacker_player_id,
                )
                emitted.extend(workshop_events)
                # If the workshop was breached the game's done — stop here.
                loser = getattr(state, "clankers_loser", None)
                if loser is not None:
                    # Reset combat flags on declared participants before bailing.
                    self._reset_combat_flags(
                        state, valid_attackers, list(used_blockers)
                    )
                    return emitted
                continue

            # Blocked: simultaneous chassis-vs-chassis combat damage.
            blk = state.objects.get(blk_id)
            if blk is None:
                continue
            blk_power = int(blocker_powers.get(blk_id, 0) or 0)

            # Attacker -> blocker
            atk_to_blk = Event(
                type=EventType.CLANKERS_COMBAT_DAMAGE,
                payload={
                    "target": blk_id,
                    "amount": atk_power,
                    "source": atk_id,
                    "damage_credited_to": attacker_player_id,
                    "attacker_id": atk_id,
                    "defender_id": blk_id,
                    "is_combat": True,
                },
                source=atk_id,
                controller=attacker_player_id,
            )
            self._emit(atk_to_blk)
            emitted.append(atk_to_blk)
            # Mark damage (TRANSFORM interceptors may have changed the
            # final amount — e.g. armor add-ons; honour the post-emit value).
            final_atk_dmg = int(atk_to_blk.payload.get("amount", atk_power) or 0)
            if final_atk_dmg > 0:
                blk.state.damage_marked = (
                    int(getattr(blk.state, "damage_marked", 0) or 0)
                    + final_atk_dmg
                )
                blk.state.last_damage_source = atk_id
                damaged_objects.append(blk_id)
                kill_credit[blk_id] = attacker_player_id

            # Blocker -> attacker
            blk_to_atk = Event(
                type=EventType.CLANKERS_COMBAT_DAMAGE,
                payload={
                    "target": atk_id,
                    "amount": blk_power,
                    "source": blk_id,
                    "damage_credited_to": defender_id,
                    "attacker_id": blk_id,
                    "defender_id": atk_id,
                    "is_combat": True,
                },
                source=blk_id,
                controller=defender_id,
            )
            self._emit(blk_to_atk)
            emitted.append(blk_to_atk)
            final_blk_dmg = int(blk_to_atk.payload.get("amount", blk_power) or 0)
            if final_blk_dmg > 0:
                atk.state.damage_marked = (
                    int(getattr(atk.state, "damage_marked", 0) or 0)
                    + final_blk_dmg
                )
                atk.state.last_damage_source = blk_id
                damaged_objects.append(atk_id)
                kill_credit[atk_id] = defender_id

        # ------------------------------------------------------------------
        # Step 4: state-based check / death cascade
        # ------------------------------------------------------------------
        # De-duplicate while preserving first-seen order so test asserts can
        # rely on a stable destruction sequence.
        seen: set[str] = set()
        ordered_damaged: list[str] = []
        for oid in damaged_objects:
            if oid not in seen:
                seen.add(oid)
                ordered_damaged.append(oid)

        sba_events = self._apply_lethal_check(state, ordered_damaged, kill_credit)
        emitted.extend(sba_events)

        # ------------------------------------------------------------------
        # Step 5: reset attacking / blocking flags. damage_marked PERSISTS.
        # ------------------------------------------------------------------
        self._reset_combat_flags(state, valid_attackers, list(used_blockers))

        return emitted

    # ------------------------------------------------------------------ flags

    def _reset_combat_flags(
        self,
        state: GameState,
        attacker_ids: list[str],
        blocker_ids: list[str],
    ) -> None:
        """Clear ``attacking`` / ``blocking`` on declared participants.
        Damage marked is NOT cleared — Clankers rule, distinct from MTG.
        """
        for oid in attacker_ids:
            obj = state.objects.get(oid)
            if obj is not None:
                obj.state.attacking = False
        for oid in blocker_ids:
            obj = state.objects.get(oid)
            if obj is not None:
                obj.state.blocking = False


# ---------------------------------------------------------------------------
# __all__ — public surface
# ---------------------------------------------------------------------------

__all__ = [
    "ClankersCombatManager",
]
