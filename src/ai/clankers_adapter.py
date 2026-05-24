"""
Clankers AI Adapter.

Heuristic AI for the Clankers multi-part robot assembly battler. Three
difficulty tiers — easy, medium, hard — implementing the behaviors
spelled out in `docs/games/clankers.md` §8 (AI Difficulty Model).

Design contract (matches `docs/games/clankers_contract.md` §1):

    choose_assemble_action(state, player_id) -> Optional[dict]
    choose_attackers(state, player_id) -> list[str]
    choose_blockers(state, player_id, attackers) -> dict[str, str]
    choose_refill(state, player_id) -> bool
    mulligan_decision(state, player_id, num_kept: int) -> bool
    choose_target(state, source_id, candidates, requirement) -> Optional[str]

Action dicts use the exact keys defined in contract §1. The adapter is
defensive against missing state fields: every method has a sane fallback
when an upstream agent (engine / combat / turn) hasn't shipped yet — we
return "pass" / [] / None rather than raising. This is the same defensive
pattern used by `cats_adapter.py`, and it keeps Stage 1.5 smoke tests
green while sibling agents land their PRs.

Hard tier is allowed up to ``HARD_ASSEMBLE_ACTION_LIMIT`` actions per
Assemble phase before returning ``{"action": "pass"}``. This guards
against pathological cycles (e.g. a card that looks affordable forever
because its compute-cost dispatch isn't wired). Easy and Medium terminate
naturally — they only consider affordable cards, and each play decrements
compute / hand size.
"""

from __future__ import annotations

import random
from typing import Optional, TYPE_CHECKING

from src.engine.types import CardType
from src.engine.clankers import (
    compute_effective_power as _compute_effective_power,
    compute_effective_integrity as _compute_effective_integrity,
)

if TYPE_CHECKING:
    from src.engine.types import GameState  # noqa: F401


# Hard tier safety: even if engine queries lie about affordability, never
# loop more than this many times in a single Assemble phase. Picked at
# 24 = 2x the typical max compute pool plus headroom for free attach
# actions.
HARD_ASSEMBLE_ACTION_LIMIT = 24

# Library size below which Hard tier starts declining refills.
# Slowing the deathclock is worth a card or two of tempo loss.
HARD_LIBRARY_DECLINE_THRESHOLD = 12
HARD_LIBRARY_DECLINE_HAND_MIN = 4

# Archetype-match bonus weight in Hard's assembly scoring.
ARCHETYPE_MATCH_BONUS = 2.0

# Number of robots Hard prioritises building before going wide.
HARD_BUILD_TALL_TARGET = 2


class ClankersAIAdapter:
    """AI adapter for the Clankers engine.

    Three difficulty tiers (easy / medium / hard) — see `docs/games/clankers.md` §8.

    Usage:
        ai = ClankersAIAdapter("medium")
        # Turn manager calls these directly; player_id is passed per-call.
        action = ai.choose_assemble_action(state, "p2")
        attackers = ai.choose_attackers(state, "p2")
        blockers = ai.choose_blockers(state, "p2", attackers)
    """

    def __init__(self, difficulty: str = "medium"):
        assert difficulty in ("easy", "medium", "hard"), (
            f"unknown difficulty {difficulty}"
        )
        self.difficulty = difficulty
        # Optional convenience attribute, mirroring cats_adapter.player_id.
        # The turn manager passes player_id explicitly on every call, so we
        # don't depend on this — but tests / harnesses sometimes set it.
        self.player_id: Optional[str] = None
        # Per-phase action counter (Hard only). Reset by the turn manager
        # whenever a fresh Assemble phase begins; we lazy-reset on the
        # first action of a new turn by tracking turn_number.
        self._hard_action_counts: dict[tuple[str, int, str], int] = {}

    # ──────────────────────────────────────────────────────────────────
    # Public API — methods called by ClankersTurnManager / ClankersCombatManager
    # ──────────────────────────────────────────────────────────────────

    def choose_assemble_action(self, state, player_id) -> Optional[dict]:
        """Pick the next Assemble-phase action for player_id.

        Returns one of the action dicts in contract §1, or
        ``{"action": "pass"}`` to end the Assemble phase.
        """
        try:
            if self.difficulty == "easy":
                return self._easy_assemble_action(state, player_id)
            if self.difficulty == "medium":
                return self._medium_assemble_action(state, player_id)
            return self._hard_assemble_action(state, player_id)
        except (AttributeError, KeyError, TypeError):
            # Engine isn't wired yet, or a state field is missing.
            # Fall back to easy behaviour rather than raise.
            try:
                return self._easy_assemble_action(state, player_id)
            except Exception:
                return {"action": "pass"}

    def choose_attackers(self, state, player_id) -> list[str]:
        """Return list of chassis / solo-part obj_ids declared as attackers."""
        try:
            if self.difficulty == "easy":
                return self._easy_attackers(state, player_id)
            if self.difficulty == "medium":
                return self._medium_attackers(state, player_id)
            return self._hard_attackers(state, player_id)
        except (AttributeError, KeyError, TypeError):
            return []

    def choose_blockers(
        self,
        state,
        player_id,
        attackers: list[str],
    ) -> dict[str, str]:
        """Return {attacker_id: blocker_id} — missing keys = unblocked."""
        try:
            if self.difficulty == "easy":
                return self._easy_blockers(state, player_id, attackers)
            if self.difficulty == "medium":
                return self._medium_blockers(state, player_id, attackers)
            return self._hard_blockers(state, player_id, attackers)
        except (AttributeError, KeyError, TypeError):
            return {}

    def choose_refill(self, state, player_id) -> bool:
        """Whether to take the Allocate-phase refill (True) or decline (False)."""
        try:
            if self.difficulty == "easy":
                return True
            if self.difficulty == "medium":
                return self._medium_choose_refill(state, player_id)
            return self._hard_choose_refill(state, player_id)
        except (AttributeError, KeyError, TypeError):
            return True

    def mulligan_decision(self, state, player_id, num_kept: int) -> bool:
        """Whether to mulligan the opening hand (True = mulligan, False = keep).

        Vancouver-style: ``num_kept`` is the number of cards we'd keep on
        the next mulligan iteration. Easy never mulligans; medium mulligans
        if the hand has zero chassis (no way to assemble).
        """
        try:
            if self.difficulty == "easy":
                return False
            if self.difficulty == "medium":
                return self._medium_mulligan(state, player_id, num_kept)
            return self._hard_mulligan(state, player_id, num_kept)
        except (AttributeError, KeyError, TypeError):
            return False

    def choose_target(
        self,
        state,
        source_id: str,
        candidates: list[str],
        requirement: dict,
    ) -> Optional[str]:
        """Mid-resolution target choice (Transient effect, ward, etc.)."""
        if not candidates:
            return None
        try:
            if self.difficulty == "easy":
                return candidates[0]
            if self.difficulty == "medium":
                return self._medium_choose_target(
                    state, source_id, candidates, requirement
                )
            return self._hard_choose_target(
                state, source_id, candidates, requirement
            )
        except (AttributeError, KeyError, TypeError):
            return candidates[0] if candidates else None

    # ──────────────────────────────────────────────────────────────────
    # State-introspection helpers
    # ──────────────────────────────────────────────────────────────────

    def _get_obj(self, state, obj_id):
        """Resolve a GameObject by id; None on any lookup failure."""
        if state is None or not obj_id:
            return None
        objects = getattr(state, "objects", None)
        if objects is None:
            return None
        try:
            return objects.get(obj_id)
        except AttributeError:
            return None

    def _card_def(self, obj):
        return getattr(obj, "card_def", None) if obj is not None else None

    def _is_card_type(self, obj, type_name: str) -> bool:
        """Check ``obj.characteristics.types`` for a CardType member by name."""
        if obj is None:
            return False
        try:
            types = obj.characteristics.types
        except AttributeError:
            return False
        target = getattr(CardType, type_name, None)
        if target is None:
            return False
        return target in types

    def _hand_card_ids(self, state, player_id: str) -> list[str]:
        """Return the player's hand card obj_ids.

        Reads the canonical per-player lowercase zone key
        ``f"hand_{player_id}"``.
        """
        if state is None or not player_id:
            return []
        zones = getattr(state, "zones", None)
        if not zones:
            return []
        zone = zones.get(f"hand_{player_id}")
        if zone is None:
            return []
        return list(getattr(zone, "objects", []) or [])

    def _floor_obj_ids(self, state, player_id: Optional[str] = None) -> list[str]:
        """Return Assembly Floor object ids.

        When ``player_id`` is supplied, returns only that player's floor.
        With no argument, walks every player's per-player floor zone.
        Per-player zones are keyed ``f"clankers_assembly_floor_{pid}"``.
        """
        if state is None:
            return []
        zones = getattr(state, "zones", None)
        if not zones:
            return []
        if player_id is not None:
            zone = zones.get(f"clankers_assembly_floor_{player_id}")
            if zone is None:
                return []
            return list(getattr(zone, "objects", []) or [])
        players = getattr(state, "players", None) or {}
        result: list[str] = []
        for pid in players:
            zone = zones.get(f"clankers_assembly_floor_{pid}")
            if zone is None:
                continue
            result.extend(getattr(zone, "objects", []) or [])
        return result

    def _controlled_chassis(self, state, player_id: str) -> list[str]:
        """All chassis controlled by `player_id` currently on the floor."""
        result = []
        # Prefer the engine's tracked dict if present (fast path).
        tracked = getattr(state, "clankers_assemblies", None)
        if isinstance(tracked, dict):
            ids = tracked.get(player_id) or []
            for cid in ids:
                obj = self._get_obj(state, cid)
                if obj is None:
                    continue
                if self._is_card_type(obj, "CLANKERS_CHASSIS"):
                    result.append(cid)
            if result:
                return result
        # Fallback: scan the player's floor zone.
        for oid in self._floor_obj_ids(state, player_id):
            obj = self._get_obj(state, oid)
            if obj is None:
                continue
            if self._is_card_type(obj, "CLANKERS_CHASSIS"):
                result.append(oid)
        return result

    def _solo_parts(self, state, player_id: str) -> list[str]:
        """Parts on this player's floor that aren't attached to anything."""
        result = []
        for oid in self._floor_obj_ids(state, player_id):
            obj = self._get_obj(state, oid)
            if obj is None:
                continue
            if not (
                self._is_card_type(obj, "CLANKERS_WEAPON")
                or self._is_card_type(obj, "CLANKERS_ADD_ON")
            ):
                continue
            attached_to = getattr(getattr(obj, "state", None), "attached_to", None)
            if attached_to:
                continue
            result.append(oid)
        return result

    def _attached_parts(self, state, chassis_id: str) -> list[str]:
        """Object ids of parts currently attached to chassis_id."""
        chassis = self._get_obj(state, chassis_id)
        if chassis is None:
            return []
        attachments = getattr(getattr(chassis, "state", None), "attachments", None) or []
        return list(attachments)

    def _weapon_slot_open(self, state, chassis_id: str) -> bool:
        """True if chassis_id has at least one free weapon slot."""
        chassis = self._get_obj(state, chassis_id)
        if chassis is None:
            return False
        card_def = self._card_def(chassis)
        max_slots = int(getattr(card_def, "weapon_slots", 2) or 0)
        if max_slots <= 0:
            return False
        used = 0
        for part_id in self._attached_parts(state, chassis_id):
            part = self._get_obj(state, part_id)
            if part is None or not self._is_card_type(part, "CLANKERS_WEAPON"):
                continue
            part_def = self._card_def(part)
            used += int(getattr(part_def, "weapon_slot_cost", 1) or 1)
        return used < max_slots

    def _add_on_slot_open(self, state, chassis_id: str) -> bool:
        chassis = self._get_obj(state, chassis_id)
        if chassis is None:
            return False
        card_def = self._card_def(chassis)
        max_slots = int(getattr(card_def, "add_on_slots", 2) or 0)
        if max_slots <= 0:
            return False
        used = 0
        for part_id in self._attached_parts(state, chassis_id):
            part = self._get_obj(state, part_id)
            if part is None or not self._is_card_type(part, "CLANKERS_ADD_ON"):
                continue
            used += 1
        return used < max_slots

    def _open_weapon_slots(self, state, chassis_id: str) -> int:
        """Number of remaining weapon slots on chassis_id."""
        chassis = self._get_obj(state, chassis_id)
        if chassis is None:
            return 0
        card_def = self._card_def(chassis)
        max_slots = int(getattr(card_def, "weapon_slots", 2) or 0)
        used = 0
        for part_id in self._attached_parts(state, chassis_id):
            part = self._get_obj(state, part_id)
            if part is None or not self._is_card_type(part, "CLANKERS_WEAPON"):
                continue
            part_def = self._card_def(part)
            used += int(getattr(part_def, "weapon_slot_cost", 1) or 1)
        return max(0, max_slots - used)

    def _open_add_on_slots(self, state, chassis_id: str) -> int:
        chassis = self._get_obj(state, chassis_id)
        if chassis is None:
            return 0
        card_def = self._card_def(chassis)
        max_slots = int(getattr(card_def, "add_on_slots", 2) or 0)
        used = 0
        for part_id in self._attached_parts(state, chassis_id):
            part = self._get_obj(state, part_id)
            if part is None or not self._is_card_type(part, "CLANKERS_ADD_ON"):
                continue
            used += 1
        return max(0, max_slots - used)

    def _compute_cost(self, obj_or_def) -> int:
        if obj_or_def is None:
            return 0
        card_def = obj_or_def if hasattr(obj_or_def, "compute_cost") else self._card_def(obj_or_def)
        return int(getattr(card_def, "compute_cost", 0) or 0)

    def _compute_pool(self, state, player_id: str) -> int:
        pool = getattr(state, "clankers_compute_pool", None) or {}
        try:
            return int(pool.get(player_id, 0) or 0)
        except AttributeError:
            return 0

    def _scrap_pool(self, state, player_id: str) -> int:
        pool = getattr(state, "clankers_scrap_pool", None) or {}
        try:
            return int(pool.get(player_id, 0) or 0)
        except AttributeError:
            return 0

    def _workshop_integrity(self, state, player_id: str) -> int:
        wi = getattr(state, "clankers_workshop_integrity", None) or {}
        try:
            return int(wi.get(player_id, 0) or 0)
        except AttributeError:
            return 0

    def _library_size(self, state, player_id: str) -> int:
        """Return cards left in this player's library zone.

        Reads ``state.zones[f"library_{player_id}"]`` — the canonical
        per-player lowercase key.
        """
        if state is None or not player_id:
            return 0
        zones = getattr(state, "zones", None)
        if not zones:
            return 0
        zone = zones.get(f"library_{player_id}")
        if zone is None:
            return 0
        return len(getattr(zone, "objects", []) or [])

    def _hand_size(self, state, player_id: str) -> int:
        return len(self._hand_card_ids(state, player_id))

    def _opponent_id(self, state, player_id: str) -> Optional[str]:
        players = getattr(state, "players", None)
        if not players:
            return None
        try:
            for pid in players:
                if pid != player_id:
                    return pid
        except (AttributeError, TypeError):
            return None
        return None

    # ── Effective stats — delegate to engine when present ────────────

    def _effective_power(self, state, chassis_id: str) -> int:
        """Effective power of a chassis (delegates to engine query)."""
        try:
            return int(_compute_effective_power(state, chassis_id) or 0)
        except Exception:
            return self._effective_power_fallback(state, chassis_id)

    def _effective_integrity(self, state, chassis_id: str) -> int:
        """Effective integrity of a chassis (delegates to engine query)."""
        try:
            return int(_compute_effective_integrity(state, chassis_id) or 0)
        except Exception:
            return self._effective_integrity_fallback(state, chassis_id)

    def _effective_power_fallback(self, state, chassis_id: str) -> int:
        chassis = self._get_obj(state, chassis_id)
        if chassis is None:
            return 0
        # Solo parts default to 1 power per §12 SOLO_PART_POWER.
        if not self._is_card_type(chassis, "CLANKERS_CHASSIS"):
            if (
                self._is_card_type(chassis, "CLANKERS_WEAPON")
                or self._is_card_type(chassis, "CLANKERS_ADD_ON")
            ):
                return 1
            return 0
        card_def = self._card_def(chassis)
        base = int(getattr(card_def, "power", 0) or 0)
        total = base
        for part_id in self._attached_parts(state, chassis_id):
            part_def = self._card_def(self._get_obj(state, part_id))
            total += int(getattr(part_def, "power_bonus", 0) or 0)
        return total

    def _effective_integrity_fallback(self, state, chassis_id: str) -> int:
        chassis = self._get_obj(state, chassis_id)
        if chassis is None:
            return 0
        if not self._is_card_type(chassis, "CLANKERS_CHASSIS"):
            if (
                self._is_card_type(chassis, "CLANKERS_WEAPON")
                or self._is_card_type(chassis, "CLANKERS_ADD_ON")
            ):
                return 1  # solo part baseline
            return 0
        card_def = self._card_def(chassis)
        base = int(getattr(card_def, "integrity", 0) or 0)
        total = base
        for part_id in self._attached_parts(state, chassis_id):
            part = self._get_obj(state, part_id)
            part_def = self._card_def(part)
            # Add-ons add integrity; weapons don't (per §5).
            if self._is_card_type(part, "CLANKERS_ADD_ON"):
                total += int(getattr(part_def, "integrity_bonus", 0) or 0)
        return total

    def _is_ready(self, obj) -> bool:
        """True if the object can attack / contribute (not tapped/exhausted)."""
        if obj is None:
            return False
        state_obj = getattr(obj, "state", None)
        if state_obj is None:
            return True
        if bool(getattr(state_obj, "tapped", False)):
            return False
        if bool(getattr(state_obj, "exhausted", False)):
            return False
        if bool(getattr(state_obj, "summoning_sickness", False)):
            return False
        return True

    def _damage_marked(self, obj) -> int:
        if obj is None:
            return 0
        state_obj = getattr(obj, "state", None)
        if state_obj is None:
            return 0
        return int(getattr(state_obj, "damage_marked", 0) or 0)

    def _armor_buffer(self, state, chassis_id: str) -> int:
        """Sum of unexhausted armor_value across add-ons attached to chassis_id.

        Hard tier uses this to predict whether an attack will actually kill,
        accounting for damage absorption that the defender can still activate.
        """
        total = 0
        for part_id in self._attached_parts(state, chassis_id):
            part = self._get_obj(state, part_id)
            if part is None or not self._is_card_type(part, "CLANKERS_ADD_ON"):
                continue
            if not self._is_ready(part):
                continue
            part_def = self._card_def(part)
            av = getattr(part_def, "armor_value", None)
            if av is None:
                continue
            try:
                total += int(av or 0)
            except (TypeError, ValueError):
                continue
        return total

    def _read_ability_field(self, descriptor, key: str, default=None):
        """Read a field from an activated-ability descriptor.

        ``make_weapon_activated`` writes dicts; tolerate attribute access so
        future descriptor shapes (e.g. dataclasses) keep working.
        """
        if isinstance(descriptor, dict):
            return descriptor.get(key, default)
        return getattr(descriptor, key, default)

    def _enumerate_activatable_abilities(
        self,
        state,
        player_id: str,
    ) -> list[tuple[str, int, dict, dict]]:
        """Enumerate currently-payable activated abilities for ``player_id``.

        Walks every chassis controlled by the player, every part attached to
        those chassis, and every solo part on the player's floor. For each
        ``obj.state.activated_abilities`` entry whose cost is payable right
        now, yields ``(source_obj_id, ability_index, cost_spec, descriptor)``.

        Cost spec is a normalised dict:
            {"compute": int, "exhaust_self": bool}

        Affordability rules:
          - ``compute`` cost must be <= player's compute pool
          - if ``exhaust_self``, the source must not already be tapped
          - source must currently be in play (battlefield/floor); we filter
            by "currently has an obj.state record we can read"
        """
        out: list[tuple[str, int, dict, dict]] = []
        pool = self._compute_pool(state, player_id)

        # Collect candidate source ids: own chassis, attached parts, solo parts.
        source_ids: list[str] = []
        for ch_id in self._controlled_chassis(state, player_id):
            source_ids.append(ch_id)
            source_ids.extend(self._attached_parts(state, ch_id))
        source_ids.extend(self._solo_parts(state, player_id))
        # Structures live in state.clankers_structures[player_id].
        structures = getattr(state, "clankers_structures", None) or {}
        try:
            source_ids.extend(structures.get(player_id, []) or [])
        except AttributeError:
            pass

        seen: set[str] = set()
        for src_id in source_ids:
            if src_id in seen:
                continue
            seen.add(src_id)
            obj = self._get_obj(state, src_id)
            if obj is None:
                continue
            if getattr(obj, "controller", None) != player_id:
                continue
            abilities = (
                getattr(getattr(obj, "state", None), "activated_abilities", None)
                or []
            )
            for idx, descriptor in enumerate(abilities):
                compute_cost = int(
                    self._read_ability_field(descriptor, "compute_cost", 0) or 0
                )
                exhaust_self = bool(
                    self._read_ability_field(descriptor, "exhaust_self", False)
                )
                if compute_cost > pool:
                    continue
                if exhaust_self and bool(
                    getattr(getattr(obj, "state", None), "tapped", False)
                ):
                    continue
                cost_spec = {
                    "compute": compute_cost,
                    "exhaust_self": exhaust_self,
                }
                out.append((src_id, idx, cost_spec, descriptor))
        return out

    def _ability_damage_hint(self, descriptor) -> int:
        """Best-effort damage estimate from an ability's description text.

        Looks for ``N damage`` anywhere in the descriptor's ``description``
        (covers both "deal N damage" and shorthand like "N damage to a
        chassis" used by Recoil Mount). Returns 0 for utility abilities
        like "ready an exhausted add-on" or "free-attach".
        """
        text = (
            self._read_ability_field(descriptor, "description", "")
            or ""
        ).lower()
        import re
        m = re.search(r"(\d+)\s+damage", text)
        if not m:
            return 0
        try:
            return int(m.group(1))
        except (TypeError, ValueError):
            return 0

    # ──────────────────────────────────────────────────────────────────
    # Easy tier
    # ──────────────────────────────────────────────────────────────────

    def _easy_assemble_action(self, state, player_id) -> dict:
        """First playable card in hand. Solo-attach if no host chassis."""
        action = self._first_legal_play(state, player_id, prefer_attach=True)
        return action or {"action": "pass"}

    def _first_legal_play(
        self,
        state,
        player_id: str,
        *,
        prefer_attach: bool,
    ) -> Optional[dict]:
        """Scan hand for the first card with a legal play. Returns an action dict or None.

        - Chassis / Transient / Structure: play if affordable.
        - Weapon / Add-on: prefer attached (first chassis with open slot
          of the right kind) when `prefer_attach=True`, else solo. If no
          chassis has an open matching slot, fall through to solo play.
        """
        hand = self._hand_card_ids(state, player_id)
        if not hand:
            return None
        pool = self._compute_pool(state, player_id)
        controlled = self._controlled_chassis(state, player_id)

        for cid in hand:
            obj = self._get_obj(state, cid)
            if obj is None:
                continue
            card_def = self._card_def(obj)
            cost = self._compute_cost(card_def)
            if cost > pool:
                continue
            if self._is_card_type(obj, "CLANKERS_CHASSIS"):
                return {"action": "play_chassis", "card_obj_id": cid, "compute_cost": cost}
            if self._is_card_type(obj, "CLANKERS_WEAPON"):
                target = None
                if prefer_attach:
                    for ch_id in controlled:
                        if self._weapon_slot_open(state, ch_id):
                            target = ch_id
                            break
                return {
                    "action": "play_weapon",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "target_chassis_id": target,
                }
            if self._is_card_type(obj, "CLANKERS_ADD_ON"):
                target = None
                if prefer_attach:
                    for ch_id in controlled:
                        if self._add_on_slot_open(state, ch_id):
                            target = ch_id
                            break
                return {
                    "action": "play_add_on",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "target_chassis_id": target,
                }
            if self._is_card_type(obj, "CLANKERS_TRANSIENT"):
                return {
                    "action": "play_transient",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "targets": [],
                }
            if self._is_card_type(obj, "CLANKERS_STRUCTURE"):
                # Respect the 3-Structure cap (§12 MAX_STRUCTURES).
                structures = getattr(state, "clankers_structures", None) or {}
                try:
                    cur = len(structures.get(player_id, []) or [])
                except AttributeError:
                    cur = 0
                if cur >= 3:
                    continue
                return {
                    "action": "play_structure",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                }
        return None

    def _easy_attackers(self, state, player_id) -> list[str]:
        """All untapped chassis + solo parts the player controls on the floor."""
        first_turn = bool(getattr(state, "clankers_first_turn", False))
        if first_turn:
            return []
        result = []
        # Chassis
        for ch_id in self._controlled_chassis(state, player_id):
            obj = self._get_obj(state, ch_id)
            if self._is_ready(obj):
                result.append(ch_id)
        # Solo parts also act as 1/1 attackers per §4.
        for part_id in self._solo_parts(state, player_id):
            obj = self._get_obj(state, part_id)
            if self._is_ready(obj):
                result.append(part_id)
        return result

    def _easy_blockers(
        self,
        state,
        player_id,
        attackers: list[str],
    ) -> dict[str, str]:
        """First available defender per attacker; no trade calculation."""
        available = self._own_potential_blockers(state, player_id)
        used: set[str] = set()
        result: dict[str, str] = {}
        for atk in attackers:
            for cand in available:
                if cand in used:
                    continue
                result[atk] = cand
                used.add(cand)
                break
        return result

    def _own_potential_blockers(self, state, player_id: str) -> list[str]:
        """All untapped own-controlled floor units that could block."""
        result = []
        for ch_id in self._controlled_chassis(state, player_id):
            obj = self._get_obj(state, ch_id)
            if self._is_ready(obj):
                result.append(ch_id)
        for part_id in self._solo_parts(state, player_id):
            obj = self._get_obj(state, part_id)
            if self._is_ready(obj):
                result.append(part_id)
        return result

    # ──────────────────────────────────────────────────────────────────
    # Medium tier
    # ──────────────────────────────────────────────────────────────────

    def _medium_assemble_action(self, state, player_id) -> dict:
        """Highest-compute-cost affordable card; smart attach target.

        Reads:
          - Lethal-finish heuristic for damage Transients: if a Transient
            could close the game on the opponent's Core, prefer it.
          - Lethal-finish heuristic for activated abilities: if a damage
            ability could close the game, fire it before considering hand
            plays. Otherwise medium skips activations (saves compute for
            tempo plays — see gap #1 in engine_gaps_clan.md).
          - Build-tall: when attaching, pick the chassis with the most
            matching open slots (so we stack onto the biggest robot).
        """
        hand = self._hand_card_ids(state, player_id)
        pool = self._compute_pool(state, player_id)
        controlled = self._controlled_chassis(state, player_id)
        opponent = self._opponent_id(state, player_id)

        # Step 1: check for a lethal-finisher activated ability. Medium only
        # activates when it directly closes the game — saves compute otherwise.
        finisher = self._medium_lethal_activation(state, player_id, opponent)
        if finisher is not None:
            return finisher

        if not hand:
            return {"action": "pass"}

        # Score every affordable hand card; higher is better.
        candidates: list[tuple[float, int, str, dict]] = []
        for cid in hand:
            obj = self._get_obj(state, cid)
            if obj is None:
                continue
            card_def = self._card_def(obj)
            cost = self._compute_cost(card_def)
            if cost > pool:
                continue
            action = self._medium_action_for(state, player_id, obj, cost, controlled)
            if action is None:
                continue
            # Base score = compute cost (spend the pool).
            score = float(cost)

            # Lethal Transient bonus: if the card looks like direct damage
            # and could close lethal, prioritize it.
            if action["action"] == "play_transient":
                lethal_dmg = self._transient_lethal_damage(state, obj, opponent)
                if lethal_dmg > 0 and self._can_finish_lethal(state, player_id, extra_damage=lethal_dmg):
                    score += 100.0
                else:
                    # Hold a Transient that does damage but won't finish — but
                    # don't outright refuse to play it; just deprioritise.
                    score -= 1.0

            # Penalise solo plays for Weapons / Add-ons when we have chassis
            # (medium AI should attach, build-tall).
            if action["action"] in ("play_weapon", "play_add_on"):
                if action.get("target_chassis_id") is None and controlled:
                    score -= 2.0
                elif action.get("target_chassis_id"):
                    score += 1.5  # reward attaching

            candidates.append((score, cost, cid, action))

        if not candidates:
            return {"action": "pass"}
        # Higher score wins; tie-break on cost desc, then cid asc for determinism.
        candidates.sort(key=lambda x: (-x[0], -x[1], x[2]))
        return candidates[0][3]

    def _medium_action_for(
        self,
        state,
        player_id: str,
        obj,
        cost: int,
        controlled: list[str],
    ) -> Optional[dict]:
        """Build the best action dict for `obj` under medium-tier rules.

        Returns None if no legal play exists (e.g. Structure cap hit).
        """
        cid = getattr(obj, "id", None)
        if cid is None:
            return None
        if self._is_card_type(obj, "CLANKERS_CHASSIS"):
            return {"action": "play_chassis", "card_obj_id": cid, "compute_cost": cost}
        if self._is_card_type(obj, "CLANKERS_WEAPON"):
            # Pick the chassis with the MOST matching open slots
            # (build-tall: stack onto the biggest robot).
            target = self._build_tall_target(state, controlled, slot_kind="weapon")
            return {
                "action": "play_weapon",
                "card_obj_id": cid,
                "compute_cost": cost,
                "target_chassis_id": target,
            }
        if self._is_card_type(obj, "CLANKERS_ADD_ON"):
            target = self._build_tall_target(state, controlled, slot_kind="add_on")
            return {
                "action": "play_add_on",
                "card_obj_id": cid,
                "compute_cost": cost,
                "target_chassis_id": target,
            }
        if self._is_card_type(obj, "CLANKERS_TRANSIENT"):
            return {
                "action": "play_transient",
                "card_obj_id": cid,
                "compute_cost": cost,
                "targets": [],
            }
        if self._is_card_type(obj, "CLANKERS_STRUCTURE"):
            structures = getattr(state, "clankers_structures", None) or {}
            try:
                cur = len(structures.get(player_id, []) or [])
            except AttributeError:
                cur = 0
            if cur >= 3:
                return None
            return {
                "action": "play_structure",
                "card_obj_id": cid,
                "compute_cost": cost,
            }
        return None

    def _medium_lethal_activation(
        self,
        state,
        player_id: str,
        opponent: Optional[str],
    ) -> Optional[dict]:
        """Find an activated ability that closes lethal (medium tier).

        Medium tier is conservative: it only fires an activated ability when
        a damage ability could finish lethal on the opponent's Core. Any
        utility abilities (ready add-on, recur transient, ...) are deferred
        to hard tier.
        """
        if not opponent:
            return None
        candidates = self._enumerate_activatable_abilities(state, player_id)
        if not candidates:
            return None
        # Look for direct-damage abilities that close lethal.
        for src_id, idx, _cost_spec, descriptor in candidates:
            dmg = self._ability_damage_hint(descriptor)
            if dmg <= 0:
                continue
            if self._can_finish_lethal(state, player_id, extra_damage=dmg):
                return {
                    "action": "activate_ability",
                    "source_obj_id": src_id,
                    "ability_index": idx,
                    "targets": [],
                }
        return None

    def _build_tall_target(
        self,
        state,
        controlled: list[str],
        *,
        slot_kind: str,
    ) -> Optional[str]:
        """Return the chassis with the most matching open slots, or None.

        Build-tall: pick the chassis already carrying the most parts (and
        with capacity). Falls back to "any chassis with an open slot" if
        the part-count tie-breaker doesn't break.
        """
        if not controlled:
            return None
        scored: list[tuple[int, int, str]] = []
        for ch_id in controlled:
            if slot_kind == "weapon":
                open_slots = self._open_weapon_slots(state, ch_id)
            else:
                open_slots = self._open_add_on_slots(state, ch_id)
            if open_slots <= 0:
                continue
            attached_count = len(self._attached_parts(state, ch_id))
            # Higher attached_count first (already-tall chassis), then more
            # open slots (so we can keep stacking), then alphabetical cid
            # for determinism.
            scored.append((-attached_count, -open_slots, ch_id))
        if not scored:
            return None
        scored.sort()
        return scored[0][2]

    def _transient_lethal_damage(
        self,
        state,
        obj,
        opponent_id: Optional[str],
    ) -> int:
        """Best-effort estimate of a Transient's direct damage to a Core.

        Reads `card_def.text` for "Deal N damage" patterns. This is a
        heuristic — real damage is decided by the resolve function.
        """
        if obj is None or not opponent_id:
            return 0
        card_def = self._card_def(obj)
        text = (getattr(card_def, "text", None) or "").lower()
        import re
        match = re.search(r"deal\s+(\d+)\s+damage", text)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                return 0
        return 0

    def _can_finish_lethal(
        self,
        state,
        player_id: str,
        *,
        extra_damage: int = 0,
    ) -> bool:
        """Cheap lethal check: can our current attackers + extra damage close out?

        Only counts unblocked-worst-case attackers (since we don't know
        defender's block choices). This is intentionally optimistic for
        the "should I play this Transient?" decision — false positives
        just mean we burn the spell.
        """
        opponent = self._opponent_id(state, player_id)
        if not opponent:
            return False
        target_hp = self._workshop_integrity(state, opponent)
        if target_hp <= 0:
            return True  # already lethal
        total = float(extra_damage)
        for ch_id in self._controlled_chassis(state, player_id):
            obj = self._get_obj(state, ch_id)
            if not self._is_ready(obj):
                continue
            total += self._effective_power(state, ch_id)
        for part_id in self._solo_parts(state, player_id):
            obj = self._get_obj(state, part_id)
            if not self._is_ready(obj):
                continue
            total += 1  # solo part power floor
        return total >= target_hp

    def _medium_attackers(self, state, player_id) -> list[str]:
        """Attack with chassis that can kill or favorably trade.

        Section 8 spec: attack with any chassis whose effective power can
        kill an undefended target, OR if the defender has fewer untapped
        blockers than total attackers (favorable trade). Skip clearly bad
        trades.
        """
        first_turn = bool(getattr(state, "clankers_first_turn", False))
        if first_turn:
            return []
        opponent = self._opponent_id(state, player_id)
        if not opponent:
            return []

        # All defender blockers we'd have to face (untapped chassis +
        # solo parts on opp side).
        defender_blockers = self._own_potential_blockers(state, opponent)
        my_potentials = self._own_potential_blockers(state, player_id)
        # "Favorable trade" condition: opp has fewer untapped blockers
        # than we have attackers — implies guaranteed unblocked damage.
        favorable = len(defender_blockers) < len(my_potentials)

        # Compute integrity of the weakest defender blocker (used for
        # "can my eff_power kill" check).
        weakest_def_integrity = None
        for did in defender_blockers:
            integ = self._effective_integrity(state, did)
            if weakest_def_integrity is None or integ < weakest_def_integrity:
                weakest_def_integrity = integ
        # If no defender blockers, every attacker is unblocked.
        no_defenders = not defender_blockers

        attackers: list[str] = []
        for aid in my_potentials:
            attacker_obj = self._get_obj(state, aid)
            eff_pow = self._effective_power(state, aid)
            eff_int = self._effective_integrity(state, aid)
            # Always attack if no defenders (face damage is free).
            if no_defenders:
                attackers.append(aid)
                continue
            # Favorable trade is a strong reason to attack.
            if favorable:
                attackers.append(aid)
                continue
            # Can-kill-undefended check: if our power can kill the weakest
            # defender, attack (defender forced to use a blocker or take damage).
            if weakest_def_integrity is not None and eff_pow >= weakest_def_integrity:
                attackers.append(aid)
                continue
            # Skip "clearly bad" trades: 1-power into 5-integrity etc.
            # Threshold: skip if our effective integrity is well under any
            # defender's effective power (clean death with no value).
            if self._would_chump(state, aid, defender_blockers):
                continue
            # Otherwise default to NOT attacking — medium plays patient.
        return attackers

    def _would_chump(
        self,
        state,
        attacker_id: str,
        defender_ids: list[str],
    ) -> bool:
        """True if every legal defender both survives AND kills the attacker."""
        eff_int = self._effective_integrity(state, attacker_id)
        eff_pow = self._effective_power(state, attacker_id)
        if not defender_ids:
            return False
        # Any defender we can kill is enough reason to attack.
        for did in defender_ids:
            def_int = self._effective_integrity(state, did)
            def_pow = self._effective_power(state, did)
            if eff_pow >= def_int:
                return False  # we threaten a kill — attack
            if def_pow < eff_int:
                return False  # we survive — at least we live
        return True

    def _medium_blockers(
        self,
        state,
        player_id,
        attackers: list[str],
    ) -> dict[str, str]:
        """Block lethal attacks first; ignore small unblocked damage."""
        if not attackers:
            return {}
        my_core_hp = self._workshop_integrity(state, player_id)
        available = self._own_potential_blockers(state, player_id)
        if not available:
            return {}
        # Sort attackers by effective power descending — biggest threats first.
        ranked = sorted(
            attackers,
            key=lambda aid: -self._effective_power(state, aid),
        )
        used: set[str] = set()
        result: dict[str, str] = {}
        for aid in ranked:
            eff_pow = self._effective_power(state, aid)
            # If this attacker could lethal-the-Core in 1 hit (or in 2 if
            # we have HP to spare past 1 swing), block it.
            if eff_pow >= my_core_hp:
                # 1-hit lethal — must block.
                cand = self._pick_best_blocker(state, aid, available, used)
                if cand is not None:
                    result[aid] = cand
                    used.add(cand)
                continue
            # 2-turn-lethal check: my_core_hp / eff_pow <= 2
            if eff_pow > 0 and (my_core_hp / eff_pow) <= 2.0:
                cand = self._pick_best_blocker(state, aid, available, used)
                if cand is not None:
                    result[aid] = cand
                    used.add(cand)
                continue
            # Otherwise leave unblocked — small ongoing damage is acceptable.
        return result

    def _pick_best_blocker(
        self,
        state,
        attacker_id: str,
        available: list[str],
        used: set[str],
    ) -> Optional[str]:
        """Pick a blocker that ideally kills the attacker without dying.

        Priority:
          1. Survives AND kills attacker (perfect trade).
          2. Kills attacker but dies (1-for-1).
          3. Survives but doesn't kill (chump that buys time).
          4. Any unused blocker (full chump).
        """
        eff_atk_pow = self._effective_power(state, attacker_id)
        eff_atk_int = self._effective_integrity(state, attacker_id)
        # Score available blockers.
        best_score = -1
        best_id: Optional[str] = None
        for bid in available:
            if bid in used:
                continue
            b_pow = self._effective_power(state, bid)
            b_int = self._effective_integrity(state, bid)
            kills = b_pow >= eff_atk_int
            survives = b_int > eff_atk_pow
            score = 0
            if kills and survives:
                score = 100
            elif kills:
                score = 60
            elif survives:
                score = 30
            else:
                score = 10
            if score > best_score:
                best_score = score
                best_id = bid
        return best_id

    def _medium_choose_refill(self, state, player_id) -> bool:
        """Decline refill if `library_size < hand_size`.

        Rationale: taking the refill in that case would draw fewer cards
        than we'd preserve by holding — and accelerates the deathclock.
        """
        lib_size = self._library_size(state, player_id)
        hand_size = self._hand_size(state, player_id)
        if lib_size < hand_size:
            return False
        return True

    def _medium_mulligan(self, state, player_id, num_kept: int) -> bool:
        """Mulligan if hand has 0 chassis."""
        hand = self._hand_card_ids(state, player_id)
        for cid in hand:
            obj = self._get_obj(state, cid)
            if obj is None:
                continue
            if self._is_card_type(obj, "CLANKERS_CHASSIS"):
                return False
        return True

    def _medium_choose_target(
        self,
        state,
        source_id: str,
        candidates: list[str],
        requirement: dict,
    ) -> Optional[str]:
        """Prefer high-value targets ("kill the bomb")."""
        if not candidates:
            return None
        kind = (requirement or {}).get("kind", "")
        if kind == "chassis":
            # Pick the chassis with the most attached parts (highest value).
            best = candidates[0]
            best_score = -1
            for cid in candidates:
                attached = len(self._attached_parts(state, cid))
                if attached > best_score:
                    best_score = attached
                    best = cid
            return best
        if kind == "part":
            # Prefer weapons over add-ons (weapons usually carry more value).
            for cid in candidates:
                obj = self._get_obj(state, cid)
                if obj and self._is_card_type(obj, "CLANKERS_WEAPON"):
                    return cid
            return candidates[0]
        if kind == "player":
            # Prefer the opponent (the only sane choice for damage effects).
            opp = self._opponent_id(state, self.player_id or "")
            if opp and opp in candidates:
                return opp
            return candidates[0]
        return candidates[0]

    # ──────────────────────────────────────────────────────────────────
    # Hard tier
    # ──────────────────────────────────────────────────────────────────

    def _hard_assemble_action(self, state, player_id) -> dict:
        """1-turn lookahead: score every candidate play, pick the best.

        Termination: hard-bounded by HARD_ASSEMBLE_ACTION_LIMIT per turn
        to avoid pathological loops with stuck cards that look affordable
        but never resolve.

        Action sources (any one is enough to avoid passing):
          1. Affordable hand cards
          2. Solo parts ripe for free attach
          3. Activated abilities currently payable

        Empty hand alone is not a pass condition — we may still activate
        in-play abilities (lethal finishers, etc.).
        """
        turn_no = int(getattr(state, "turn_number", 0) or 0)
        key = (player_id, turn_no, "assemble")
        count = int(self._hard_action_counts.get(key, 0))
        if count >= HARD_ASSEMBLE_ACTION_LIMIT:
            # Reset the counter at the next turn boundary by leaving the key
            # in place; turn_number bumps will create a fresh key.
            return {"action": "pass"}

        hand = self._hand_card_ids(state, player_id)
        pool = self._compute_pool(state, player_id)
        controlled = self._controlled_chassis(state, player_id)
        opponent = self._opponent_id(state, player_id)

        # Build candidate action list.
        scored: list[tuple[float, int, str, dict]] = []

        # 1. Hand-card plays.
        for cid in hand:
            obj = self._get_obj(state, cid)
            if obj is None:
                continue
            card_def = self._card_def(obj)
            cost = self._compute_cost(card_def)
            if cost > pool:
                continue
            for action, score in self._hard_action_candidates(
                state, player_id, obj, cost, controlled, opponent
            ):
                scored.append((score, cost, cid, action))

        # 2. Floor-attach actions (move a solo part onto a chassis for free).
        for part_id in self._solo_parts(state, player_id):
            part = self._get_obj(state, part_id)
            if part is None:
                continue
            target = None
            if self._is_card_type(part, "CLANKERS_WEAPON"):
                target = self._build_tall_target(state, controlled, slot_kind="weapon")
            elif self._is_card_type(part, "CLANKERS_ADD_ON"):
                target = self._build_tall_target(state, controlled, slot_kind="add_on")
            if target is None:
                continue
            action = {
                "action": "attach_floor_part",
                "part_obj_id": part_id,
                "target_chassis_id": target,
            }
            # Score: same delta as if we'd played the part attached.
            score = 5.0 + self._attach_score_delta(state, part, target)
            scored.append((score, 0, part_id, action))

        # 3. Activated abilities (Fire-style).
        for activation, score in self._hard_activation_candidates(
            state, player_id, opponent
        ):
            scored.append((score, 0, activation.get("source_obj_id", ""), activation))

        if not scored:
            return {"action": "pass"}
        # Pick the highest-scoring action. Tie-break on cost desc, then id.
        scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
        top_score, _cost, _cid, top_action = scored[0]
        # If the top action's score is negative or zero, prefer to pass
        # rather than burn a card for no benefit.
        if top_score <= 0.0:
            return {"action": "pass"}
        self._hard_action_counts[key] = count + 1
        return top_action

    def _hard_action_candidates(
        self,
        state,
        player_id: str,
        obj,
        cost: int,
        controlled: list[str],
        opponent: Optional[str],
    ) -> list[tuple[dict, float]]:
        """Score every play of `obj` (could be attach OR solo for parts)."""
        cid = getattr(obj, "id", None)
        if cid is None:
            return []
        out: list[tuple[dict, float]] = []
        card_def = self._card_def(obj)
        archetype = getattr(card_def, "clankers_archetype", None)
        # Build-tall threshold (build wide once we have HARD_BUILD_TALL_TARGET robots).
        going_wide = len(controlled) >= HARD_BUILD_TALL_TARGET

        if self._is_card_type(obj, "CLANKERS_CHASSIS"):
            # Score = chassis P/T + slot count (room to grow) + cost.
            base_p = int(getattr(card_def, "power", 0) or 0)
            base_i = int(getattr(card_def, "integrity", 0) or 0)
            w_slots = int(getattr(card_def, "weapon_slots", 2) or 0)
            a_slots = int(getattr(card_def, "add_on_slots", 2) or 0)
            score = float(base_p + base_i + 0.5 * (w_slots + a_slots))
            # If we already have enough chassis and slots open, don't add a
            # new one — let the existing one grow instead.
            if not going_wide:
                # First two chassis are always welcome.
                score += 3.0
            elif len(controlled) >= 4:
                score -= 5.0  # cap board to 4 chassis
            # Compute-cost weight (use the pool).
            score += 0.5 * cost
            out.append((
                {"action": "play_chassis", "card_obj_id": cid, "compute_cost": cost},
                score,
            ))
            return out

        if self._is_card_type(obj, "CLANKERS_WEAPON"):
            # Attached version (if a chassis has an open weapon slot).
            target = self._build_tall_target(state, controlled, slot_kind="weapon")
            if target is not None:
                score = self._weapon_attach_score(
                    state, obj, target, archetype
                )
                out.append((
                    {
                        "action": "play_weapon",
                        "card_obj_id": cid,
                        "compute_cost": cost,
                        "target_chassis_id": target,
                    },
                    score,
                ))
            # Solo version — only worth it as last resort.
            solo_score = float(int(getattr(card_def, "power_bonus", 0) or 0)) * 0.3 - 2.0
            out.append((
                {
                    "action": "play_weapon",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "target_chassis_id": None,
                },
                solo_score,
            ))
            return out

        if self._is_card_type(obj, "CLANKERS_ADD_ON"):
            target = self._build_tall_target(state, controlled, slot_kind="add_on")
            if target is not None:
                score = self._add_on_attach_score(state, obj, target, archetype)
                out.append((
                    {
                        "action": "play_add_on",
                        "card_obj_id": cid,
                        "compute_cost": cost,
                        "target_chassis_id": target,
                    },
                    score,
                ))
            solo_score = float(int(getattr(card_def, "integrity_bonus", 0) or 0)) * 0.2 - 2.0
            out.append((
                {
                    "action": "play_add_on",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "target_chassis_id": None,
                },
                solo_score,
            ))
            return out

        if self._is_card_type(obj, "CLANKERS_TRANSIENT"):
            # Damage Transients score by extra-damage value; non-damage
            # Transients get a flat low score.
            dmg = self._transient_lethal_damage(state, obj, opponent)
            score = 0.5 + cost  # baseline
            if dmg > 0:
                score += dmg * 0.5
                if self._can_finish_lethal(state, player_id, extra_damage=dmg):
                    score += 50.0
            out.append((
                {
                    "action": "play_transient",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "targets": [],
                },
                score,
            ))
            return out

        if self._is_card_type(obj, "CLANKERS_STRUCTURE"):
            structures = getattr(state, "clankers_structures", None) or {}
            try:
                cur = len(structures.get(player_id, []) or [])
            except AttributeError:
                cur = 0
            if cur >= 3:
                return []
            # Structures are passive value — score them by cost + a small
            # premium for being permanent.
            score = float(cost) + 4.0
            out.append((
                {"action": "play_structure", "card_obj_id": cid, "compute_cost": cost},
                score,
            ))
            return out

        return out

    def _weapon_attach_score(
        self,
        state,
        weapon_obj,
        target_chassis_id: str,
        archetype: Optional[str],
    ) -> float:
        """Score a weapon attaching to target_chassis_id.

        Formula approx: `eff_power_after + eff_integrity_after + 2 *
        new_weapon_count + 0.5 * archetype_match_bonus`. Delta from the
        chassis's current score is what actually matters here.
        """
        card_def = self._card_def(weapon_obj)
        pb = int(getattr(card_def, "power_bonus", 0) or 0)
        new_eff_p = self._effective_power(state, target_chassis_id) + pb
        new_eff_i = self._effective_integrity(state, target_chassis_id)
        weapons_after = sum(
            1
            for part_id in self._attached_parts(state, target_chassis_id)
            if self._is_card_type(self._get_obj(state, part_id), "CLANKERS_WEAPON")
        ) + 1
        score = float(new_eff_p) + float(new_eff_i) + 2.0 * weapons_after
        if archetype and self._archetype_match(state, target_chassis_id, archetype):
            score += ARCHETYPE_MATCH_BONUS
        return score

    def _add_on_attach_score(
        self,
        state,
        add_on_obj,
        target_chassis_id: str,
        archetype: Optional[str],
    ) -> float:
        card_def = self._card_def(add_on_obj)
        pb = int(getattr(card_def, "power_bonus", 0) or 0)
        ib = int(getattr(card_def, "integrity_bonus", 0) or 0)
        armor = int(getattr(card_def, "armor_value", 0) or 0)
        new_eff_p = self._effective_power(state, target_chassis_id) + pb
        new_eff_i = self._effective_integrity(state, target_chassis_id) + ib
        weapons_after = sum(
            1
            for part_id in self._attached_parts(state, target_chassis_id)
            if self._is_card_type(self._get_obj(state, part_id), "CLANKERS_WEAPON")
        )
        score = float(new_eff_p) + float(new_eff_i) + 2.0 * weapons_after
        # Armor add-ons get a defensive bonus.
        score += armor * 0.75
        if archetype and self._archetype_match(state, target_chassis_id, archetype):
            score += ARCHETYPE_MATCH_BONUS
        return score

    def _attach_score_delta(
        self,
        state,
        part_obj,
        target_chassis_id: str,
    ) -> float:
        """Score delta for moving a SOLO part onto target_chassis_id (free action)."""
        card_def = self._card_def(part_obj)
        pb = int(getattr(card_def, "power_bonus", 0) or 0)
        ib = int(getattr(card_def, "integrity_bonus", 0) or 0)
        return float(pb + ib) + 1.0  # +1 for "no longer a vulnerable solo"

    def _archetype_match(
        self,
        state,
        chassis_id: str,
        archetype: str,
    ) -> bool:
        """True if the chassis (or its other attached parts) shares the archetype."""
        chassis = self._get_obj(state, chassis_id)
        if chassis is None or not archetype:
            return False
        card_def = self._card_def(chassis)
        if getattr(card_def, "clankers_archetype", None) == archetype:
            return True
        for part_id in self._attached_parts(state, chassis_id):
            part_def = self._card_def(self._get_obj(state, part_id))
            if getattr(part_def, "clankers_archetype", None) == archetype:
                return True
        return False

    def _assemble_score(self, state, chassis_id: str) -> float:
        """Public-ish score function for an assembly.

        `eff_power + eff_integrity + 2 * weapons_attached + 0.5 *
        archetype_match_bonus`. Used by Hard and exposed for Stage 2 tests.
        """
        eff_p = self._effective_power(state, chassis_id)
        eff_i = self._effective_integrity(state, chassis_id)
        weapons = sum(
            1
            for part_id in self._attached_parts(state, chassis_id)
            if self._is_card_type(self._get_obj(state, part_id), "CLANKERS_WEAPON")
        )
        score = float(eff_p + eff_i) + 2.0 * weapons
        # Archetype match: chassis archetype matched against attached parts.
        chassis = self._get_obj(state, chassis_id)
        chassis_arch = getattr(self._card_def(chassis), "clankers_archetype", None)
        if chassis_arch:
            matches = sum(
                1
                for part_id in self._attached_parts(state, chassis_id)
                if getattr(self._card_def(self._get_obj(state, part_id)), "clankers_archetype", None) == chassis_arch
            )
            score += 0.5 * matches
        return score

    def _hard_activation_candidates(
        self,
        state,
        player_id: str,
        opponent: Optional[str],
    ) -> list[tuple[dict, float]]:
        """Score every legal activated-ability action under hard-tier rules.

        Walks ``_enumerate_activatable_abilities`` and scores by:
          (a) lethal-finisher damage abilities (+50 bonus)
          (b) abilities that prevent opponent lethal (Workshop Wrench-style
              ready, Reactor Shell self-ready, Stunner Arm lockout)
          (c) damage / utility abilities that produce >= 2 effective value
              for <= 2 compute (proactive value plays)

        Hard skips activations whose final score < 2.0 (saves compute for
        better turns).
        """
        if not opponent:
            return []
        out: list[tuple[dict, float]] = []
        candidates = self._enumerate_activatable_abilities(state, player_id)
        if not candidates:
            return []
        opp_unblocked = self._unblocked_workshop_damage(state, opponent) if opponent else 0
        for src_id, idx, cost_spec, descriptor in candidates:
            compute_cost = int(cost_spec.get("compute", 0) or 0)
            description = (
                self._read_ability_field(descriptor, "description", "")
                or ""
            ).lower()
            dmg = self._ability_damage_hint(descriptor)

            # Base score: small premium so a cheap utility activation beats
            # passing when nothing else is worth doing.
            score = 1.0

            # Direct-damage value bonus.
            if dmg > 0:
                score += dmg * 0.4
                if self._can_finish_lethal(state, player_id, extra_damage=dmg):
                    score += 50.0
                if self._unblocked_workshop_damage(state, player_id) >= 4:
                    score += 5.0

            # Defensive-utility bonus (b): prevent opponent lethal next turn.
            # Recognise common keywords: "ready", "can't attack", "lockout".
            if opp_unblocked >= self._workshop_integrity(state, player_id):
                if any(
                    tok in description
                    for tok in ("can't attack", "cannot attack", "lockout", "stun")
                ):
                    score += 40.0
                if "ready" in description:
                    score += 10.0  # ready up a blocker

            # Proactive utility (c): >= 2 effective damage/utility for <= 2 compute.
            if compute_cost <= 2:
                if dmg >= 2:
                    score += 2.0
                # Recycle-a-Transient style abilities: cheap card advantage.
                if "transient" in description and (
                    "return" in description or "recurse" in description
                ):
                    score += 2.5
                # Free-attach (Auxiliary Bench): tempo boost.
                if "attach" in description or "free attach" in description:
                    score += 2.0
                # Modular relocate: not always good; keep small premium.
                if "modular" in description or "move" in description:
                    score += 0.5

            # Compute-efficiency penalty: expensive utility with no clear
            # finisher dropping a low net.
            if compute_cost >= 2 and dmg == 0:
                score -= 1.5

            if score >= 2.0:
                out.append((
                    {
                        "action": "activate_ability",
                        "source_obj_id": src_id,
                        "ability_index": idx,
                        "targets": [],
                    },
                    score,
                ))
        return out

    def _unblocked_workshop_damage(self, state, player_id: str) -> int:
        """Estimate of unblocked combat damage we'd push through this turn.

        Sums up `eff_power` of our ready attackers minus opponent's total
        defensive integrity (treating each blocker as soaking its eff_int).
        """
        opp = self._opponent_id(state, player_id)
        if not opp:
            return 0
        my_power = 0
        for ch_id in self._controlled_chassis(state, player_id):
            obj = self._get_obj(state, ch_id)
            if self._is_ready(obj):
                my_power += self._effective_power(state, ch_id)
        for part_id in self._solo_parts(state, player_id):
            obj = self._get_obj(state, part_id)
            if self._is_ready(obj):
                my_power += 1
        # Defender's available block-points.
        def_pts = 0
        for ch_id in self._controlled_chassis(state, opp):
            obj = self._get_obj(state, ch_id)
            if self._is_ready(obj):
                def_pts += self._effective_integrity(state, ch_id)
        return max(0, my_power - def_pts)

    def _hard_attackers(self, state, player_id) -> list[str]:
        """Hard tier: play around armor, prefer high-value targets.

        Same core rule as medium, but:
        - Adds defender's unexhausted armor to integrity in kill checks.
        - Death-cascade tempo: attack chassis with many attached parts
          (we'll scrap the weapons too).
        - Skips attacks that obviously trade poorly unless we win lethal.
        """
        first_turn = bool(getattr(state, "clankers_first_turn", False))
        if first_turn:
            return []
        opponent = self._opponent_id(state, player_id)
        if not opponent:
            return []

        defender_blockers = self._own_potential_blockers(state, opponent)
        my_potentials = self._own_potential_blockers(state, player_id)
        if not my_potentials:
            return []

        # If we can lethal this turn — attack with EVERYTHING.
        if self._can_finish_lethal(state, player_id):
            return list(my_potentials)

        no_defenders = not defender_blockers
        favorable = len(defender_blockers) < len(my_potentials)

        # Sort defender blockers by "death cascade value" — high-part chassis
        # are juicier targets.
        def cascade_value(did):
            obj = self._get_obj(state, did)
            if obj is None:
                return 0
            attached = len(self._attached_parts(state, did))
            return attached

        sorted_def = sorted(defender_blockers, key=cascade_value, reverse=True)

        attackers: list[str] = []
        for aid in my_potentials:
            eff_pow = self._effective_power(state, aid)
            eff_int = self._effective_integrity(state, aid)

            if no_defenders:
                attackers.append(aid)
                continue

            # Can we kill the juiciest defender (post-armor)?
            kills_juicy = False
            for did in sorted_def:
                target_integrity = self._effective_integrity(state, did)
                # Hard plays around armor: add unexhausted armor buffer.
                target_integrity += self._armor_buffer(state, did)
                if eff_pow >= target_integrity:
                    kills_juicy = True
                    break

            if kills_juicy:
                attackers.append(aid)
                continue
            if favorable:
                attackers.append(aid)
                continue
            # Skip clearly bad trades.
            if self._would_chump(state, aid, defender_blockers):
                continue
            # Otherwise hold back — patient.
        return attackers

    def _hard_blockers(
        self,
        state,
        player_id,
        attackers: list[str],
    ) -> dict[str, str]:
        """Block lethal first; account for armor buffer on the blocker side too."""
        if not attackers:
            return {}
        my_core_hp = self._workshop_integrity(state, player_id)
        available = self._own_potential_blockers(state, player_id)
        if not available:
            return {}
        # Sum total attacker damage and find the highest-impact ones to block.
        atk_with_power = [(aid, self._effective_power(state, aid)) for aid in attackers]
        # If total damage doesn't threaten us in the next 2 turns, don't block at all.
        total_dmg = sum(p for _, p in atk_with_power)
        if total_dmg > 0 and (my_core_hp / total_dmg) > 2.0:
            # Only block attacks that would 1-shot a critical asset (e.g.
            # our own loaded chassis). Skip for now — return {}.
            return {}
        ranked = sorted(atk_with_power, key=lambda x: -x[1])
        used: set[str] = set()
        result: dict[str, str] = {}
        damage_avoided = 0
        for aid, eff_pow in ranked:
            if damage_avoided >= my_core_hp - 1:
                # We've already blocked enough; stop wasting bodies.
                break
            cand = self._pick_best_blocker(state, aid, available, used)
            if cand is None:
                continue
            result[aid] = cand
            used.add(cand)
            damage_avoided += eff_pow
        return result

    def _hard_choose_refill(self, state, player_id) -> bool:
        """Decline refill when slowing the deathclock is +EV.

        - If library_size < HARD_LIBRARY_DECLINE_THRESHOLD (12 by default) AND
          hand_size >= HARD_LIBRARY_DECLINE_HAND_MIN (4), decline.
        - Otherwise default to taking the refill.
        """
        lib_size = self._library_size(state, player_id)
        hand_size = self._hand_size(state, player_id)
        if lib_size < HARD_LIBRARY_DECLINE_THRESHOLD and hand_size >= HARD_LIBRARY_DECLINE_HAND_MIN:
            return False
        # Also decline if drawing more than the library can provide is
        # worse than holding (same as medium's basic rule).
        if lib_size < hand_size:
            return False
        return True

    def _hard_mulligan(self, state, player_id, num_kept: int) -> bool:
        """Mulligan if hand has no chassis OR no early-game compute spend."""
        hand = self._hand_card_ids(state, player_id)
        chassis_count = 0
        cheap_play_count = 0
        for cid in hand:
            obj = self._get_obj(state, cid)
            if obj is None:
                continue
            if self._is_card_type(obj, "CLANKERS_CHASSIS"):
                chassis_count += 1
            cost = self._compute_cost(self._card_def(obj))
            if cost <= 3:
                cheap_play_count += 1
        if chassis_count == 0:
            return True
        if cheap_play_count < 2:
            return True
        return False

    def _hard_choose_target(
        self,
        state,
        source_id: str,
        candidates: list[str],
        requirement: dict,
    ) -> Optional[str]:
        """Highest-value target by attached weapons + raw power."""
        if not candidates:
            return None
        kind = (requirement or {}).get("kind", "")
        if kind == "chassis":
            best = candidates[0]
            best_score = float("-inf")
            for cid in candidates:
                obj = self._get_obj(state, cid)
                if obj is None:
                    continue
                # Score: assemble_score + 2 * weapons (death-cascade premium)
                score = self._assemble_score(state, cid)
                weapons = sum(
                    1
                    for part_id in self._attached_parts(state, cid)
                    if self._is_card_type(self._get_obj(state, part_id), "CLANKERS_WEAPON")
                )
                score += weapons * 2.0
                if score > best_score:
                    best_score = score
                    best = cid
            return best
        return self._medium_choose_target(state, source_id, candidates, requirement)

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers exposed for tests / Stage 2 consumers
    # ──────────────────────────────────────────────────────────────────

    def _legal_actions_for(self, state, player_id: str) -> list[dict]:
        """Enumerate every legal Assemble action for `player_id` right now.

        Returns a list of action dicts (per contract §1). Exposed for
        tests, balance scripts, and the optional Stage-2 "show me what
        the AI is considering" UI.
        """
        actions: list[dict] = []
        hand = self._hand_card_ids(state, player_id)
        pool = self._compute_pool(state, player_id)
        controlled = self._controlled_chassis(state, player_id)
        for cid in hand:
            obj = self._get_obj(state, cid)
            if obj is None:
                continue
            card_def = self._card_def(obj)
            cost = self._compute_cost(card_def)
            if cost > pool:
                continue
            if self._is_card_type(obj, "CLANKERS_CHASSIS"):
                actions.append(
                    {"action": "play_chassis", "card_obj_id": cid, "compute_cost": cost}
                )
            elif self._is_card_type(obj, "CLANKERS_WEAPON"):
                # Every chassis with an open weapon slot is a candidate.
                for ch_id in controlled:
                    if self._weapon_slot_open(state, ch_id):
                        actions.append({
                            "action": "play_weapon",
                            "card_obj_id": cid,
                            "compute_cost": cost,
                            "target_chassis_id": ch_id,
                        })
                # Solo play is always legal.
                actions.append({
                    "action": "play_weapon",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "target_chassis_id": None,
                })
            elif self._is_card_type(obj, "CLANKERS_ADD_ON"):
                for ch_id in controlled:
                    if self._add_on_slot_open(state, ch_id):
                        actions.append({
                            "action": "play_add_on",
                            "card_obj_id": cid,
                            "compute_cost": cost,
                            "target_chassis_id": ch_id,
                        })
                actions.append({
                    "action": "play_add_on",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "target_chassis_id": None,
                })
            elif self._is_card_type(obj, "CLANKERS_TRANSIENT"):
                actions.append({
                    "action": "play_transient",
                    "card_obj_id": cid,
                    "compute_cost": cost,
                    "targets": [],
                })
            elif self._is_card_type(obj, "CLANKERS_STRUCTURE"):
                structures = getattr(state, "clankers_structures", None) or {}
                try:
                    cur = len(structures.get(player_id, []) or [])
                except AttributeError:
                    cur = 0
                if cur < 3:
                    actions.append({
                        "action": "play_structure",
                        "card_obj_id": cid,
                        "compute_cost": cost,
                    })
        # Floor attach actions (free).
        for part_id in self._solo_parts(state, player_id):
            part = self._get_obj(state, part_id)
            if part is None:
                continue
            for ch_id in controlled:
                if self._is_card_type(part, "CLANKERS_WEAPON"):
                    if not self._weapon_slot_open(state, ch_id):
                        continue
                elif self._is_card_type(part, "CLANKERS_ADD_ON"):
                    if not self._add_on_slot_open(state, ch_id):
                        continue
                else:
                    continue
                actions.append({
                    "action": "attach_floor_part",
                    "part_obj_id": part_id,
                    "target_chassis_id": ch_id,
                })
        actions.append({"action": "pass"})
        return actions

    def _attack_will_kill(
        self,
        state,
        attacker_id: str,
        blocker_id: str,
    ) -> bool:
        """Hard-tier kill predictor: does attacker_id's eff_power kill blocker_id?

        Accounts for unexhausted armor on the blocker side.
        """
        eff_pow = self._effective_power(state, attacker_id)
        eff_int = self._effective_integrity(state, blocker_id)
        eff_int += self._armor_buffer(state, blocker_id)
        return eff_pow >= eff_int
