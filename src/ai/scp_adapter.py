"""Small heuristic AI for SCP Containment TCG wet tests."""

from __future__ import annotations

from src.engine.types import CardType, GameState, ZoneType
from src.engine import scp


# Coach note (2026-05-12, ultra-loop iter 1 ACW vs SCR):
#
# Pilot B's losing run was closest to "balanced" (breach_danger=4,
# anomaly_staff_threshold=2). Pilot A's winning run was closest to
# "archivist" but exploited two levers the heuristic does not express:
#   1. Multi-dossier opens per turn (the take_turn body opens at most one
#      dossier per call — see line ~138 onward).
#   2. Opponent alt-win tracking (no signal exists in score() for an
#      opposing mandate's alt-win proximity, so balanced cannot defend
#      against redaction).
# These are decision-logic gaps; weight tuning alone cannot close them.
# The encoder pass should add a future "archive_speedrun" preset:
#   - Bias: open ALL playable tape-≤1 dossiers per turn when assignment
#     slots permit; bias anomaly_staff_threshold low (1) so own-anomaly
#     research engines come online by T3.
#   - Bias: when own Mandate alt_win == "redaction", weight memory_hole
#     of any non-active pending dossier once archives ≥ 4 and secrecy
#     in [10, 11].
#   - Signals required: opp_alt_win_progress(), pending_dossier_ids(),
#     memory_hole legal action — none exist yet in score().
# Coach is leaving the weight dicts effectively untouched this iteration
# because no clean single-digit weight change addresses the structural
# gap. Re-evaluate after the encoder adds opp-alt-win and multi-open
# support.
#
# Iter 2 addendum (2026-05-12, ultra-loop iter 2 ACW vs SCR):
# Encoder pass landed multi-open + opp-alt-win + memory-hole-bridge in
# take_turn() (see lines ~222-248, ~250-338). Weights remain untouched
# this iteration too. Specifically resisted lowering "balanced"
# anomaly_staff_threshold from 2 → 1: iter 2's SCR pilot self-destructed
# on breach overflow precisely because it fast-tracked a haz-3 anomaly
# without contain throughput. Lower threshold = MORE early anomaly opens
# = MORE breach-overflow risk, not less. The "containment" preset (used
# by SCR-style decks) doesn't yet model contain-skill availability, so
# it cannot detect a 0-contain-skill draw and pivot to primary archive
# race. That is the next structural encoder gap: a contain_skill_drawn
# signal feeding a pivot from thaumiel alt-win to primary 7-archive
# mode. Until that lands, the heuristic will keep opening anomalies on
# hazard threshold alone even when contain is structurally unavailable.
# Watch for opponent breach-overflow self-destruct: when the OPPONENT's
# active haz_sum + breach ≥ 9 at their start-of-turn, they are likely 1
# EOT tick from losing — defensive pilots benefit from running out the
# clock rather than racing alt-win. No weight needed; this is a
# decision-logic observation.
#
# Iter 3 addendum (2026-05-12, ultra-loop iter 3 GOI Frontline vs Veil):
# Veil Control won T8 via veil_lockdown (3 archives + 0 breach). Engine
# truth surfaced: reveal does NOT tick hazard (scp.py:172-214 emits
# SCP_ANOMALY_REVEALED but never calls breach_tick — that runs once at
# EOT via scp_turn.py:80), and suppress-to-contain via Protect Mandate
# pays 2 archives per conversion (scp.py:531). The veil_lockdown
# threshold is therefore 2 successful suppressions = win, the fastest
# single-axis alt-win in the game.
#
# One single-digit weight change applied: _anomaly_staff_threshold["veil"]
# raised 2 → 3. Justification: iter 3 Pilot B's optimal line was open
# anomalies SEALED first, then reveal+suppress in the same turn once
# Janitor (sup 3) and Field Agent (sup 2) were both active. Threshold 2
# was too aggressive — biased toward opening anomalies as soon as 2 staff
# existed, which can include zero suppress-skill staff. Threshold 3
# delays anomaly opens until enough staff exist to actually clear
# max(haz, cont) at suppress. The change is conservative and only
# affects the "veil" preset; other presets retain their iter 1/2 values.
#
# No "raid" preset exists yet. Iter 3 evidence suggests a raid preset
# would need: aggressive audit-procedure prioritization (drop opp
# secrecy toward public_panic's ≤6 threshold), low-hazard anomalies as
# the SOLE archive engine (raid card pool has NO +archive procedures),
# and a hard mulligan policy that demands the alt-win Mandate in opener
# (otherwise the deck has no win condition). The current "disruption"
# preset is the closest match (breach_danger=4, threshold=1) but
# disruption assumes the deck has a research engine — raid does not,
# beyond the haz-1 Borderless Site Anomaly. Without a raid preset the
# heuristic falls back to "balanced", which doesn't prioritize audits
# correctly for the public_panic clock. Decision-logic gap; no clean
# weight change closes it.
#
# Cross-iter generalization: an underperforming deck is rescuable by LLM
# pilot skill ONLY when the deck has a self-consistent engine that
# aligns with its alt-win threshold. ACW (iter 1/2) has a redaction
# alt-win bridged by memory-hole + a research-anomaly engine + plenty
# of archive scorers — rescuable. GOI Frontline (iter 3) has a 2-axis
# public_panic alt-win + no +archive procedures + draw-dependent
# anomaly engine — NOT rescuable, structural gap. The next loop pass
# should triage decks by axis-count and engine-alignment before
# spending pilot iterations on them.
SUPPORTED_SCP_PILOTS = frozenset({
    "archivist",
    "balanced",
    "blackfile",
    "clean_hands",
    "conservative",
    "containment",
    "disruption",
    "masquerade",
    "quarantine",
    "rotation",
    "thaumiel",
    "veil",
})

SUPPORTED_SCP_DIFFICULTIES = frozenset({"easy", "medium", "hard", "expert", "ultra"})


def validate_scp_pilot(pilot: str) -> str:
    """Return a normalized SCP pilot name or raise for unknown pilots."""
    normalized = str(pilot).strip().lower()
    if normalized not in SUPPORTED_SCP_PILOTS:
        supported = ", ".join(sorted(SUPPORTED_SCP_PILOTS))
        raise ValueError(f"Unknown SCP pilot name: {pilot!r}. Supported pilots: {supported}")
    return normalized


def validate_scp_difficulty(difficulty: str) -> str:
    normalized = str(difficulty).strip().lower()
    if normalized not in SUPPORTED_SCP_DIFFICULTIES:
        supported = ", ".join(sorted(SUPPORTED_SCP_DIFFICULTIES))
        raise ValueError(f"Unknown SCP difficulty: {difficulty!r}. Supported difficulties: {supported}")
    return normalized


class SCPAIAdapter:
    """Non-combat heuristic: stabilize first, then archive."""

    def __init__(self, difficulty: str = "medium", pilot: str | None = None):
        if pilot is None:
            first_arg = str(difficulty).strip().lower()
            if first_arg in SUPPORTED_SCP_PILOTS:
                pilot = first_arg
                difficulty = "medium"
            elif first_arg not in SUPPORTED_SCP_DIFFICULTIES:
                supported = ", ".join(sorted(SUPPORTED_SCP_PILOTS))
                raise ValueError(f"Unknown SCP pilot name: {difficulty!r}. Supported pilots: {supported}")
        self.difficulty = validate_scp_difficulty(difficulty)
        self.pilot = validate_scp_pilot(pilot or "balanced")

    @property
    def _breach_danger(self) -> int:
        return {
            "conservative": 3,
            "balanced": 4,
            "archivist": 5,
            "containment": 4,
            "disruption": 4,
            "veil": 3,
            "masquerade": 5,
            "quarantine": 4,
            "thaumiel": 4,
            "blackfile": 4,
            "clean_hands": 4,
            "rotation": 3,
        }.get(self.pilot, 4)

    @property
    def _anomaly_staff_threshold(self) -> int:
        return {
            "archivist": 1,
            "disruption": 1,
            "balanced": 2,
            "containment": 2,
            "veil": 3,  # iter 3: raised 2→3 to bias toward sealed-then-suppress line
            "conservative": 3,
            "masquerade": 1,
            "quarantine": 2,
            "thaumiel": 2,
            "blackfile": 1,
            "clean_hands": 2,
            "rotation": 2,
        }.get(self.pilot, 2)

    def _has_mandate(self, state: GameState, player_id: str, alt_win: str) -> bool:
        for mandate_id in list(state.scp_mandates.get(player_id, [])):
            mandate = state.objects.get(mandate_id)
            if (
                mandate
                and mandate.state.scp_status == "active"
                and getattr(mandate.card_def, "scp_alt_win", None) == alt_win
            ):
                return True
        return False

    def _active_bonus(self, state: GameState, player_id: str, task: str) -> int:
        total = 0
        for registry in (state.scp_facilities, state.scp_mandates):
            for object_id in list(registry.get(player_id, [])):
                obj = state.objects.get(object_id)
                if not obj or obj.zone != ZoneType.BATTLEFIELD or obj.state.scp_status != "active":
                    continue
                total += int(getattr(obj.card_def, "scp_bonus", {}).get(task, 0) or 0)
        return total

    def _task_power(self, state: GameState, player_id: str, staff: list, task: str) -> int:
        return self._active_bonus(state, player_id, task) + sum(
            int(getattr(obj.card_def, "scp_skills", {}).get(task, 0) or 0)
            for obj in staff
        )

    # --- Helper queries used by take_turn() and future presets ---

    def _own_alt_win_kind(self, state: GameState, player_id: str) -> str | None:
        """Return the alt_win kind on this player's active mandate, or None."""
        for mandate_id in list(state.scp_mandates.get(player_id, [])):
            mandate = state.objects.get(mandate_id)
            if (
                mandate
                and mandate.state.scp_status == "active"
                and getattr(mandate.card_def, "scp_alt_win", None)
            ):
                return getattr(mandate.card_def, "scp_alt_win", None)
        return None

    def _pending_dossier_ids(self, state: GameState, player_id: str) -> list[str]:
        """IDs of this player's pending (non-active) dossiers on battlefield."""
        ids: list[str] = []
        for obj in state.objects.values():
            if (
                obj.controller == player_id
                and obj.zone == ZoneType.BATTLEFIELD
                and obj.state.scp_status not in {"active", "contained", "sealed"}
            ):
                ids.append(obj.id)
        return ids

    def _opp_alt_win_proximity(
        self, state: GameState, player_id: str, opponent_id: str
    ) -> tuple[str | None, int]:
        """Return (alt_win_kind, turns_to_win_estimate) for opponent, or (None, 99).

        Rough estimate: smaller numbers = closer to win. Used for defensive bias.
        """
        opp_site = scp.site(state, opponent_id)
        closest_kind: str | None = None
        closest_distance = 99
        for mandate_id in list(state.scp_mandates.get(opponent_id, [])):
            mandate = state.objects.get(mandate_id)
            if not mandate or mandate.state.scp_status != "active":
                continue
            kind = getattr(mandate.card_def, "scp_alt_win", None)
            if not kind:
                continue
            if kind == "redaction":
                gap = max(0, 3 - opp_site["archives"]) + max(0, 12 - opp_site["secrecy"])
            elif kind == "thaumiel":
                contained = len(state.scp_contained.get(opponent_id, [])) if hasattr(state, "scp_contained") else 0
                gap = max(0, 4 - contained) + opp_site["breach"]
            elif kind == "veil_lockdown":
                gap = max(0, 3 - opp_site["archives"]) + opp_site["breach"]
            elif kind == "ethics_audit":
                # Threshold tracks check_scp_victory secrecy 8 -> 7 (May 2026
                # archetype-trace audit). ethics_debt term retained as a soft
                # signal even though the engine no longer enforces it.
                gap = max(0, 4 - opp_site["archives"]) + max(0, 7 - opp_site["secrecy"]) + max(0, opp_site["ethics_debt"] - 2)
            elif kind == "public_panic":
                gap = max(0, 4 - opp_site["archives"])
            elif kind == "memory_hole":
                # MNR alt-win: 3 forgotten anomalies (across all players) +
                # secrecy >= 8. Estimate the gap as the deficit on both axes
                # summed. Threshold tracks the engine value in check_scp_victory
                # (lowered 10 -> 8 in the May 2026 archetype-trace audit).
                forgotten_total = 0
                if hasattr(state, "scp_forgotten"):
                    for fp_id in state.players:
                        if fp_id == opponent_id:
                            continue
                        forgotten_total += len(state.scp_forgotten.get(fp_id, []))
                gap = max(0, 3 - forgotten_total) + max(0, 8 - opp_site["secrecy"])
            else:
                gap = 99
            if gap < closest_distance:
                closest_distance = gap
                closest_kind = kind
        return closest_kind, closest_distance

    def _cheap_incident_resolves(self, state: GameState, player_id: str) -> list[int]:
        """Indices of pending incidents that are free / near-free to resolve.

        Engine `resolve_incident()` has no resource cost — always +1 briefing,
        sometimes +secrecy / -breach. Returns all incident indices (strict upside).
        """
        incidents = list(state.scp_incidents.get(player_id, []))
        return list(range(len(incidents)))

    def _visible_contain_capacity(self, state: GameState, player_id: str) -> int:
        """Sum of contain skill across active personnel + contain-bearing cards in hand."""
        total = 0
        for sid in list(state.scp_personnel.get(player_id, [])):
            obj = state.objects.get(sid)
            if obj and obj.state.scp_status == "active" and obj.card_def:
                total += int(getattr(obj.card_def, "scp_skills", {}).get("contain", 0) or 0)
        hand_zone = state.zones.get(f"hand_{player_id}")
        if hand_zone:
            for hid in list(hand_zone.objects):
                obj = state.objects.get(hid)
                if obj and obj.card_def:
                    total += int(getattr(obj.card_def, "scp_skills", {}).get("contain", 0) or 0)
        return total

    def _opp_breach_overflow_imminent(self, state: GameState, opponent_id: str) -> bool:
        """True when opponent is likely 1 EOT tick from breach-overflow loss."""
        opp_site = scp.site(state, opponent_id)
        if opp_site.get("breach", 0) < 8:
            return False
        haz_sum = 0
        contain_skill = 0
        for aid in list(state.scp_anomalies.get(opponent_id, [])):
            obj = state.objects.get(aid)
            if obj and obj.state.scp_status == "active":
                haz_sum += scp.effective_hazard_for_ai(obj)
        for sid in list(state.scp_personnel.get(opponent_id, [])):
            obj = state.objects.get(sid)
            if obj and obj.state.scp_status == "active" and obj.card_def:
                contain_skill += int(getattr(obj.card_def, "scp_skills", {}).get("contain", 0) or 0)
        # Imminent if next breach tick (≈ haz_sum) would push past 10 AND opp has no
        # visible contain throughput to drain anomalies.
        return (opp_site["breach"] + haz_sum >= 10) and contain_skill <= 1

    def _total_suppress_capacity(self, state: GameState, player_id: str) -> int:
        """Sum suppress skill across active personnel + facility/mandate bonus + hand."""
        total = self._active_bonus(state, player_id, "suppress")
        for sid in list(state.scp_personnel.get(player_id, [])):
            obj = state.objects.get(sid)
            if obj and obj.state.scp_status == "active" and obj.card_def:
                total += int(getattr(obj.card_def, "scp_skills", {}).get("suppress", 0) or 0)
        hand_zone = state.zones.get(f"hand_{player_id}")
        if hand_zone:
            for hid in list(hand_zone.objects):
                obj = state.objects.get(hid)
                if obj and obj.card_def:
                    total += int(getattr(obj.card_def, "scp_skills", {}).get("suppress", 0) or 0)
        return total

    def _has_audit_cards(self, state: GameState, player_id: str) -> bool:
        """True when player has any Audit/Raid/Bureaucracy procedures in hand/battlefield."""
        keys = ("audit", "leak", "witness", "raid")
        audit_subs = {"Audit", "Raid", "Bureaucracy", "GOI"}
        for zone_name in (f"hand_{player_id}", "battlefield"):
            zone = state.zones.get(zone_name)
            if not zone:
                continue
            for oid in list(zone.objects):
                obj = state.objects.get(oid)
                if not obj or (zone_name == "battlefield" and obj.controller != player_id):
                    continue
                if audit_subs & set(obj.characteristics.subtypes or set()):
                    return True
                text = (obj.card_def.text or "").lower() if obj.card_def else ""
                if any(k in text for k in keys):
                    return True
        return False

    def _alt_win_feasible(self, state: GameState, player_id: str) -> bool | None:
        """None if no alt-win mandate. Otherwise True/False per deck engine survey."""
        kind = self._own_alt_win_kind(state, player_id)
        if kind is None:
            return None
        if kind == "redaction":
            return True  # archive+memory-hole bridge is broadly available
        if kind == "thaumiel":
            return self._visible_contain_capacity(state, player_id) >= 2
        if kind == "veil_lockdown":
            return self._total_suppress_capacity(state, player_id) >= 2
        if kind in {"public_panic", "ethics_audit"}:
            return self._has_audit_cards(state, player_id)
        return None

    def _controlled_objects(self, state, player_id):
        """Objects ``player_id`` controls, across the SCP zone indexes."""
        out = []
        seen = set()
        for key in ("scp_personnel", "scp_anomalies", "scp_contained", "scp_facilities", "scp_mandates"):
            index = getattr(state, key, {}) or {}
            for oid in index.get(player_id, []) or []:
                if oid in seen:
                    continue
                seen.add(oid)
                obj = state.objects.get(oid)
                if obj is not None:
                    out.append(obj)
        return out

    def _estimate_ability_value(self, obj, state, player_id, hint) -> float:
        """Scalar value of an effect from its declared SCPValueHint, using the
        same site-state weights the rest of the heuristic encodes. Negative
        breach/ethics_debt deltas (reducing a loss clock) score as upside."""
        if hint is None:
            return 0.0
        site = scp.site(state, player_id)
        v = 0.0
        if hint.breach:
            cur_breach = int(site.get("breach", 0) or 0)
            if hint.breach < 0:
                # Reducing breach: worth nothing if there's no breach to remove,
                # worth more when near the loss clock.
                reducible = min(-hint.breach, cur_breach)
                danger = 3.0 if cur_breach >= self._breach_danger else 1.0
                v += reducible * danger
            else:
                v += -hint.breach  # raising your own breach is a downside
        if hint.secrecy:
            v += hint.secrecy * (2.5 if int(site.get("secrecy", 0) or 0) <= 6 else 1.0)
        if hint.archives:
            v += hint.archives * 2.0
        if hint.briefing:
            v += hint.briefing * 0.6
        if hint.clearance:
            v += hint.clearance * 0.5
        if hint.ethics_debt:
            v += -hint.ethics_debt * (2.0 if int(site.get("ethics_debt", 0) or 0) >= 6 else 0.8)
        if hint.gains_mnestic:
            v += 1.5
        if hint.contains_anomaly:
            v += 2.0
        if hint.steals_permanent:
            v += 3.0
        if hint.custom_value_fn:
            v += float(hint.custom_value_fn(obj, state, None))
        return v

    def _cost_value(self, obj, state, player_id, cost) -> float:
        """Heuristic value of the resources a cost spends (so the AI doesn't
        fire an ability whose cost outweighs its gain). Paying ethics REDUCES a
        liability, so it's nearly free."""
        site = scp.site(state, player_id)
        c = 0.0
        if cost.ethics:
            c += cost.ethics * 0.2
        if cost.secrecy:
            c += cost.secrecy * (2.5 if int(site.get("secrecy", 0) or 0) <= 6 else 1.0)
        if cost.briefing:
            c += cost.briefing * 0.6
        if cost.clearance:
            c += cost.clearance * 0.5
        if cost.archives:
            c += cost.archives * 2.0
        if cost.exhaust_self:
            c += 0.5
        return c

    def _consider_activated_abilities(self, player_id, state, game) -> list:
        """Fire beneficial SCP activated/modal abilities. Single pass over
        controlled permanents; picks the best mode for modal abilities. The
        FIRE_THRESHOLD keeps the AI from firing marginal abilities and is a
        per-preset knob (tunable later via /ultra-loop)."""
        from src.engine.scp_abilities import is_scp_ability
        from src.engine.scp_costs import can_pay_scp_cost

        events = []
        threshold = getattr(self, "_ability_fire_threshold", 0.5)
        for obj in self._controlled_objects(state, player_id):
            for idx, ability in enumerate(getattr(obj.state, "activated_abilities", None) or []):
                if not is_scp_ability(ability):
                    continue
                if ability.once_per_game and ability.used_this_game:
                    continue
                if ability.once_per_turn and ability.activations_this_turn > 0:
                    continue
                if ability.precondition_fn and not ability.precondition_fn(obj, state):
                    continue
                ok, _why = can_pay_scp_cost(obj, state, ability.cost)
                if not ok:
                    continue
                cost_val = self._cost_value(obj, state, player_id, ability.cost)
                if ability.is_modal:
                    best_mode, best_gain = None, float("-inf")
                    for m_idx, mode in enumerate(ability.modes):
                        gain = self._estimate_ability_value(obj, state, player_id, mode.value_hint)
                        if gain > best_gain:
                            best_gain, best_mode = gain, m_idx
                    if best_mode is not None and best_gain - cost_val > threshold:
                        a_ok, _msg, a_ev = scp.activate_ability(game, player_id, obj.id, idx, mode=best_mode)
                        if a_ok:
                            events.extend(a_ev)
                else:
                    gain = self._estimate_ability_value(obj, state, player_id, ability.value_hint)
                    if gain - cost_val > threshold:
                        a_ok, _msg, a_ev = scp.activate_ability(game, player_id, obj.id, idx)
                        if a_ok:
                            events.extend(a_ev)
        return events

    async def take_turn(self, player_id: str, state: GameState, game) -> list:
        events = []
        if not game:
            return events

        site = scp.site(state, player_id)
        active_anomalies = [
            state.objects[aid]
            for aid in state.scp_anomalies.get(player_id, [])
            if aid in state.objects and state.objects[aid].state.scp_status == "active"
        ]
        active_staff_count = sum(
            1
            for sid in state.scp_personnel.get(player_id, [])
            if sid in state.objects and state.objects[sid].state.scp_status == "active"
        )

        # Opponent alt-win tracking (defensive signal — encoded from ultra-loop iter 1).
        opponent_id = next((pid for pid in state.players if pid != player_id), None)
        disrupt_redaction = False
        opp_breach_overflow = False
        if opponent_id is not None:
            opp_kind, opp_gap = self._opp_alt_win_proximity(state, player_id, opponent_id)
            opp_site = scp.site(state, opponent_id)
            if (
                opp_kind == "redaction"
                and opp_site.get("archives", 0) >= 2
                and opp_site.get("secrecy", 0) >= 9
            ):
                disrupt_redaction = True
            # Iter 2: opponent breach-overflow imminent — run out the clock instead
            # of racing alt-win. Encoded from Pilot A's T13-14 winning observation.
            if (
                self._opp_breach_overflow_imminent(state, opponent_id)
                and site.get("breach", 0) <= 4
                and site.get("secrecy", 0) >= 6
            ):
                opp_breach_overflow = True

        # Iter 2: pivot-from-contain-plan — thaumiel alt-win is unreachable without
        # contain-skill draws. Iter 3: generalized via _alt_win_feasible so the
        # same pivot applies to veil_lockdown (no suppress) and public_panic (no
        # audit cards). After T4, if the alt-win engine is absent, race archives.
        own_alt_win = self._own_alt_win_kind(state, player_id)
        alt_win_feasible = self._alt_win_feasible(state, player_id)
        pivot_from_contain_plan = (
            own_alt_win == "thaumiel"
            and state.turn_number >= 4
            and self._visible_contain_capacity(state, player_id) <= 1
        )
        pivot_alt_win = (
            alt_win_feasible is False
            and state.turn_number >= 4
        )
        # Iter 3: veil_lockdown SEAL-then-REVEAL line. When opening anomalies and
        # total suppress capacity is short of what's needed to clear hazard, prefer
        # to seal them face-down (no breach tick) and reveal later once Janitor +
        # Field Agent are both active. Pilot B's winning T4/T8 line.
        veil_suppress_capacity = (
            self._total_suppress_capacity(state, player_id)
            if own_alt_win == "veil_lockdown" else 0
        )

        # Iter 2: proactively resolve any pending incidents — strict upside (engine
        # resolve_incident has no resource cost; always +1 briefing, sometimes
        # +secrecy / -breach). Pilot A flagged this as a hidden tempo gem.
        for incident_index in self._cheap_incident_resolves(state, player_id):
            ok, _msg, ri_events = scp.resolve_incident(game, player_id, index=0)
            if ok:
                events.extend(ri_events)
            else:
                break
        site = scp.site(state, player_id)

        # Memory-hole as a secrecy bridge: own redaction alt-win + surplus archives
        # + near-cap secrecy → trade 1 archive for 1 secrecy on a pending dossier.
        if (
            own_alt_win == "redaction"
            and site.get("archives", 0) >= 4
            and 10 <= site.get("secrecy", 0) <= 11
        ):
            for pending_id in self._pending_dossier_ids(state, player_id):
                ok, _msg, mh_events = scp.memory_hole(game, player_id, pending_id, source=pending_id)
                if ok:
                    events.extend(mh_events)
                    site = scp.site(state, player_id)
                    break

        # Multi-dossier opens per turn — encoded from ultra-loop iter 1:
        # heuristic opened 1/turn; LLM pilots open 4-6 on T1.
        # Iter 2: when opp breach-overflow is imminent, cap opens to 1 (low-action,
        # run-out-the-clock turn — don't fast-track, don't draw extra hazard).
        MAX_OPENS_PER_TURN = 1 if opp_breach_overflow else 6
        opens_this_turn = 0
        while opens_this_turn < MAX_OPENS_PER_TURN:
            hand_zone = state.zones.get(f"hand_{player_id}")
            hand = list(hand_zone.objects) if hand_zone else []
            if not hand:
                break
            site = scp.site(state, player_id)

            # MNR memory_hole engine signal — counted once per turn so the
            # nested score() can read it without rescanning state.
            mnr_total_forgotten = (
                sum(len(state.scp_forgotten.get(pid, [])) for pid in state.players)
                if own_alt_win == "memory_hole" else 0
            )

            def score(card_id: str) -> tuple[int, int, str]:
                obj = state.objects[card_id]
                types = obj.characteristics.types
                text = (obj.card_def.text or "").lower() if obj.card_def else ""
                subtypes = set(obj.characteristics.subtypes or set())
                stabilizer = ("breach -" in text) or ("secrecy +" in text)
                archive_scorer = "archive +1" in text
                blackfile = "blackfile" in text or "audit" in text
                rotation = "rotation" in text
                quarantine = "quarantine" in text
                anchor = "anchor" in text
                clean_hands = "ethics" in text and self.pilot == "clean_hands"
                # Secrecy-pump priority for alt-wins that require secrecy
                # thresholds (May 2026 archetype-trace fix):
                #   - memory_hole: 3+ forgotten + secrecy >= 8
                #   - ethics_audit: 4 archives + secrecy >= 7
                #   - redaction: archives + secrecy >= 12
                # When below the win-line secrecy, secrecy-pump procedures are
                # the primary clock. The old score() default sent procedures
                # with neither Audit/Raid/Bureaucracy nor a pilot-keyword to
                # rank=4 ("play if nothing better"), which left Witness
                # Relocation / Class-A Amnestic Broadcast / Incident Report
                # Rewrite dead in ETH and MNR despite being the deck's actual
                # win-clock cards. We rank these AFTER the stabilizer check
                # below so emergency breach control still takes priority.
                secrecy_pump = "secrecy +" in text and CardType.SCP_PROCEDURE in types
                secrecy_target = (
                    8 if own_alt_win == "memory_hole"
                    else 7 if own_alt_win == "ethics_audit"
                    else 12 if own_alt_win == "redaction"
                    else None
                )
                alt_win_secrecy_pump = (
                    secrecy_pump
                    and secrecy_target is not None
                    and site["secrecy"] < secrecy_target
                )
                # Recovery procedures pop forgotten anomalies back, but under
                # memory_hole the forgotten pile is the win condition (3+
                # forgotten + 8 secrecy). Only prio Recovery when we already
                # have surplus forgotten (4+); below that, leave forgotten in
                # place to keep racking the alt-win threshold.
                is_recovery = "Recovery" in subtypes and CardType.SCP_PROCEDURE in types
                alt_win_recovery = (
                    own_alt_win == "memory_hole"
                    and is_recovery
                    and mnr_total_forgotten >= 4
                )
                if stabilizer and (site["breach"] >= 4 or site["secrecy"] <= 6):
                    rank = -1
                elif alt_win_secrecy_pump:
                    rank = 0
                elif alt_win_recovery:
                    rank = 0
                elif CardType.SCP_PROCEDURE in types and rotation and self.pilot == "rotation":
                    rank = 0
                elif CardType.SCP_PROCEDURE in types and quarantine and self.pilot == "quarantine" and active_anomalies:
                    rank = 0
                elif CardType.SCP_PROCEDURE in types and anchor and self.pilot == "thaumiel" and active_anomalies:
                    rank = 0
                elif CardType.SCP_PROCEDURE in types and clean_hands and site["ethics_debt"] >= 2:
                    rank = 0
                elif CardType.SCP_PERSONNEL in types:
                    rank = 0
                elif CardType.SCP_MANDATE in types:
                    rank = 1
                elif CardType.SCP_FACILITY in types:
                    rank = 2
                elif CardType.SCP_PROCEDURE in types and archive_scorer and site["breach"] <= 3:
                    # Iter 2: when pivoting off contain plan, prio archive scorers.
                    if pivot_from_contain_plan:
                        rank = 0
                    else:
                        rank = 1 if self.pilot == "archivist" else 2
                elif CardType.SCP_PROCEDURE in types and ({"GOI", "Audit"} & subtypes or blackfile) and site["breach"] <= 3:
                    rank = 1 if self.pilot in {"disruption", "masquerade", "blackfile"} else 2
                elif CardType.SCP_PROCEDURE in types and (
                    {"Audit", "Raid", "Bureaucracy"} & subtypes
                ) and own_alt_win in {"public_panic", "ethics_audit"} and not pivot_alt_win:
                    # Iter 3: when running a panic/audit alt-win and engine is
                    # feasible, audit-style procedures are the primary clock.
                    rank = 0
                elif CardType.SCP_ANOMALY in types:
                    # Iter 2/3: pivot — when alt-win engine is absent, deprioritize.
                    if pivot_from_contain_plan or (pivot_alt_win and own_alt_win in {"thaumiel", "veil_lockdown"}):
                        rank = 5
                    elif self.pilot == "thaumiel" and len(active_anomalies) < 2 and active_staff_count >= 1:
                        rank = 1
                    elif self.pilot == "quarantine" and len(active_anomalies) < 2:
                        rank = 1
                    elif own_alt_win == "veil_lockdown" and len(active_anomalies) < 2:
                        # Iter 3: veil_lockdown wants anomalies on field — they
                        # are the archive engine. Open even without research staff.
                        rank = 1
                    else:
                        rank = 1 if not active_anomalies and active_staff_count >= self._anomaly_staff_threshold else 3
                else:
                    rank = 4
                return (rank, int(getattr(obj.card_def, "scp_red_tape", 0) or 0), obj.name)

            chosen_id = sorted(hand, key=score)[0]
            chosen = state.objects[chosen_id]
            red_tape = int(getattr(chosen.card_def, "scp_red_tape", 0) or 0)
            # Iter 2: seal-as-memory-hole-fodder. When own alt-win is redaction
            # and archives ≥ 3 (already at threshold), seal anomalies face-down
            # — never paperwork-ticks, never breach-hits, can be memory-holed for
            # the +1 secrecy bridge later. Pilot A T11 line.
            is_anomaly = CardType.SCP_ANOMALY in chosen.characteristics.types
            anomaly_hazard = scp.effective_hazard_for_ai(chosen) if is_anomaly else 0
            seal_for_fodder = (
                is_anomaly
                and own_alt_win == "redaction"
                and site.get("archives", 0) >= 3
            )
            # Iter 3: veil_lockdown SEAL line. If suppress capacity is short of the
            # anomaly's hazard, seal face-down (no breach tick). Reveal-and-suppress
            # is handled after the open-loop once capacity is sufficient.
            seal_for_suppress = (
                is_anomaly
                and own_alt_win == "veil_lockdown"
                and veil_suppress_capacity < max(1, anomaly_hazard)
            )
            # Tape-0 cards always open free; tape-1+ only when secrecy buffer holds
            # (or when racing a redaction opp who'd punish slow-rolling).
            # When opp is about to overflow, never fast-track — preserve secrecy.
            if opens_this_turn >= 1:
                if red_tape == 0:
                    fast = False
                elif opp_breach_overflow:
                    break
                elif red_tape == 1 and site["secrecy"] - 1 >= 4:
                    fast = True
                elif disrupt_redaction and red_tape <= 2 and site["secrecy"] - red_tape >= 4:
                    fast = True
                else:
                    break
            else:
                fast = (not opp_breach_overflow) and site["secrecy"] >= 8 and red_tape <= 1
                if disrupt_redaction and not opp_breach_overflow and red_tape <= 2 and site["secrecy"] - red_tape >= 4:
                    fast = True
            if seal_for_fodder or seal_for_suppress:
                ok, _message, action_events = scp.open_dossier(
                    game, player_id, chosen_id, fast_track=False, sealed=True
                )
            else:
                ok, _message, action_events = scp.open_dossier(
                    game, player_id, chosen_id, fast_track=fast
                )
            if ok:
                events.extend(action_events)
                opens_this_turn += 1
                # refresh derived state for the next iteration
                active_anomalies = [
                    state.objects[aid]
                    for aid in state.scp_anomalies.get(player_id, [])
                    if aid in state.objects and state.objects[aid].state.scp_status == "active"
                ]
                active_staff_count = sum(
                    1
                    for sid in state.scp_personnel.get(player_id, [])
                    if sid in state.objects and state.objects[sid].state.scp_status == "active"
                )
            else:
                break

        # Iter 3: veil_lockdown REVEAL-when-ready. After the open-loop, reveal a
        # sealed anomaly whose max(haz, cont) ≤ current suppress capacity so the
        # assignment block below can suppress-to-contain this same turn.
        if own_alt_win == "veil_lockdown":
            cur_suppress = self._total_suppress_capacity(state, player_id)
            for obj in list(state.objects.values()):
                if not (obj.controller == player_id and obj.zone == ZoneType.BATTLEFIELD
                        and obj.state.scp_status == "sealed"
                        and CardType.SCP_ANOMALY in obj.characteristics.types):
                    continue
                tgt = max(scp.effective_hazard_for_ai(obj), scp.effective_containment_for_ai(obj))
                if cur_suppress >= tgt:
                    ok, _msg, rv_events = scp.reveal_dossier(game, player_id, obj.id)
                    if ok:
                        events.extend(rv_events)
                        break

        # Fire beneficial activated / modal abilities before the assignment
        # phase (some abilities set up the board for assignments).
        events.extend(self._consider_activated_abilities(player_id, state, game))
        site = scp.site(state, player_id)

        active = [
            state.objects[aid]
            for aid in state.scp_anomalies.get(player_id, [])
            if aid in state.objects and state.objects[aid].state.scp_status == "active"
        ]
        staff = [
            state.objects[sid]
            for sid in state.scp_personnel.get(player_id, [])
            if sid in state.objects
            and state.objects[sid].state.scp_status == "active"
            and not state.objects[sid].state.scp_exhausted
        ]
        if not active or not staff:
            return events

        staff_ids = [obj.id for obj in staff]
        contain_power = self._task_power(state, player_id, staff, "contain")
        research_power = self._task_power(state, player_id, staff, "research")
        suppress_power = self._task_power(state, player_id, staff, "suppress")

        def plan(anomaly):
            hazard = scp.effective_hazard_for_ai(anomaly)
            containment = scp.effective_containment_for_ai(anomaly)
            curiosity = scp.effective_curiosity_for_ai(anomaly)
            redaction_target = max(hazard, containment)
            if self._has_mandate(state, player_id, "veil_lockdown") and suppress_power >= redaction_target:
                return (90 + hazard + containment, "suppress", anomaly)
            if (
                (self.pilot in {"archivist", "quarantine"} or self._has_mandate(state, player_id, "redaction"))
                and site["breach"] < self._breach_danger
                and research_power >= curiosity
            ):
                return (78 + curiosity, "research", anomaly)
            if (
                self._has_mandate(state, player_id, "public_panic")
                and site["archives"] < 4
                and site["breach"] < self._breach_danger
                and research_power >= curiosity
            ):
                return (76 + curiosity, "research", anomaly)
            if contain_power >= containment:
                return (70 + hazard + containment, "contain", anomaly)
            if site["breach"] >= self._breach_danger and suppress_power >= hazard and hazard > 0:
                return (65 + hazard, "suppress", anomaly)
            if research_power >= curiosity:
                return (55 + curiosity, "research", anomaly)
            if suppress_power >= hazard and hazard > 0:
                return (35 + hazard, "suppress", anomaly)
            return (hazard, "suppress", anomaly)

        _priority, action, target = max((plan(anomaly) for anomaly in active), key=lambda item: item[0])
        if action == "contain":
            ok, _message, action_events = scp.contain_anomaly(game, player_id, target.id, staff_ids)
        elif action == "research":
            ok, _message, action_events = scp.run_test(game, player_id, target.id, staff_ids)
        else:
            ok, _message, action_events = scp.suppress_anomaly(game, player_id, target.id, staff_ids)
        if ok:
            events.extend(action_events)
        return events
