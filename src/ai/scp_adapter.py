"""Small heuristic AI for SCP Containment TCG wet tests."""

from __future__ import annotations

from src.engine.types import CardType, GameState, ZoneType
from src.engine import scp


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
            "veil": 2,
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

    async def take_turn(self, player_id: str, state: GameState, game) -> list:
        events = []
        if not game:
            return events

        # Open one dossier per turn. Fast-track only when the Site is calm.
        hand = list(state.zones.get(f"hand_{player_id}", []).objects if state.zones.get(f"hand_{player_id}") else [])
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
        if hand:
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
                if stabilizer and (site["breach"] >= 4 or site["secrecy"] <= 6):
                    rank = -1
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
                    rank = 1 if self.pilot == "archivist" else 2
                elif CardType.SCP_PROCEDURE in types and ({"GOI", "Audit"} & subtypes or blackfile) and site["breach"] <= 3:
                    rank = 1 if self.pilot in {"disruption", "masquerade", "blackfile"} else 2
                elif CardType.SCP_ANOMALY in types:
                    if self.pilot == "thaumiel" and len(active_anomalies) < 2 and active_staff_count >= 1:
                        rank = 1
                    elif self.pilot == "quarantine" and len(active_anomalies) < 2:
                        rank = 1
                    else:
                        rank = 1 if not active_anomalies and active_staff_count >= self._anomaly_staff_threshold else 3
                else:
                    rank = 4
                return (rank, int(getattr(obj.card_def, "scp_red_tape", 0) or 0), obj.name)

            chosen_id = sorted(hand, key=score)[0]
            chosen = state.objects[chosen_id]
            red_tape = int(getattr(chosen.card_def, "scp_red_tape", 0) or 0)
            fast = site["secrecy"] >= 8 and red_tape <= 1
            ok, _message, action_events = scp.open_dossier(game, player_id, chosen_id, fast_track=fast)
            if ok:
                events.extend(action_events)

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
