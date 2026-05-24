"""Clankers LLM AI Adapter.

Claude-powered player for the Clankers engine. Mirrors the public interface of
``ClankersAIAdapter`` (see ``src/ai/clankers_adapter.py``):

    choose_assemble_action(state, player_id) -> Optional[dict]
    choose_attackers(state, player_id) -> list[str]
    choose_blockers(state, player_id, attackers) -> dict[str, str]
    choose_refill(state, player_id) -> bool
    mulligan_decision(state, player_id, num_kept) -> bool
    choose_target(state, source_id, candidates, requirement) -> Optional[str]

Each decision renders the game state as a compact, English-language summary and
asks Claude (via inlined ``_ClaudeCodeShell``) for a small JSON-shaped response.
Synchronous over async via ``asyncio.run()`` per decision.

Card IDs are NOT shown to the LLM. Hand / floor / pile entries are labelled
with slot numbers (1..N) per category in the rendered prompt and Claude
returns slot numbers; we map slot → obj_id server-side. Avoids hallucination.

On error (timeout, malformed JSON, out-of-range slot), the adapter falls
back to ``ClankersAIAdapter("hard")`` so a game can still complete.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

from src.ai.clankers_adapter import ClankersAIAdapter


@dataclass
class _ClankersLLMResponse:
    content: str
    model: str


class _ClaudeCodeShell:
    """Inlined `claude -p` shellout (mirrors cats_llm_adapter.py pattern)."""

    def __init__(self, model: str = "haiku", timeout: float = 60.0, claude_bin: str = "claude"):
        self.model = model
        self.timeout = timeout
        self.claude_bin = claude_bin

    @property
    def is_available(self) -> bool:
        return shutil.which(self.claude_bin) is not None

    async def complete(self, prompt: str, system: Optional[str] = None) -> _ClankersLLMResponse:
        cmd = [self.claude_bin, "-p", "--output-format", "text"]
        if self.model:
            cmd.extend(["--model", self.model])
        if system:
            cmd.extend(["--append-system-prompt", system])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"claude -p timed out after {self.timeout}s")
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"claude -p exit {proc.returncode}: {err}")
        return _ClankersLLMResponse(
            content=stdout.decode("utf-8", errors="replace").strip(),
            model=self.model or "claude-code",
        )

    async def complete_json(self, prompt: str, schema: dict, system: Optional[str] = None) -> dict:
        schema_str = json.dumps(schema, indent=2)
        json_prompt = f"""{prompt}

Respond with ONLY valid JSON matching this schema:
{schema_str}
"""
        response = await self.complete(json_prompt, system=system)
        text = response.content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip().startswith("```") else "\n".join(lines[1:])
            text = text.strip()
        return json.loads(text)


if TYPE_CHECKING:
    from src.engine.types import GameState


_SYSTEM_PROMPT = """You are an expert player of Clankers — a robot-assembly battler.

Goal: reduce your opponent's Workshop Integrity (starts at 30) to 0, OR survive the Containment Failure deathclock (activates when either library hits 5 cards; ramps 2→4→8 damage per turn).

Core rules:
- A "robot" is a Chassis + attached Weapons + attached Add-Ons. Effective Power = chassis.power + sum(weapon.power_bonus) + sum(add_on.power_bonus). Effective Integrity = chassis.integrity + sum(add_on.integrity_bonus).
- Always-7 hand floor: at start of Allocate phase you MAY refill to 7. Refill takes from your library (cycles deck → deathclock pressure).
- Compute is a per-turn pool that resets (3 + turn_number, capped at 10). Cards print compute_cost.
- Combat: each attacker can be blocked by one defender. Unblocked attackers deal Effective Power to opponent's Core (workshop_integrity damage). On lethal damage, chassis dies AND attached parts cascade to scrap.
- Solo parts (weapons/add-ons not attached) are baseline 1/1 — weak. Attach to a chassis to apply the bonus.

Mechanics:
- Synchronize: chassis gets +1/+1 if you control 2-3 Synchronize chassis (0 with 4+ — over-coupling).
- Self-Mobile: solo part keeps its bonus stats even unattached.
- Modular: part can re-attach to a new chassis at end of any turn.
- Reclaim N: when destroyed, gain N scrap.
- Reticulate: at end of turn if you played 0 Transients, draw 1.

Strategy:
- Hand is not scarce; don't hoard. Plays come from the library.
- Big robots: 1 chassis + 2 weapons + 2 add-ons is the design sweet spot.
- Refill decision: take it unless you're racing the deathclock and want to slow your own draw.
- Attack with anything that can kill or chip Workshop Integrity profitably.
- Block lethal threats; let chip damage through if your trade would be unfavorable.

Return ONLY valid JSON matching the requested schema. No extra prose."""


class ClankersLLMAdapter:
    """LLM-driven Clankers player.

    Constructs the underlying shellout eagerly but does NOT verify the CLI
    is available — failures cascade to the heuristic fallback.

    Usage:
        ai = ClankersLLMAdapter(player_id="p1", model="haiku")
        action = ai.choose_assemble_action(state, "p1")
        # ...
    """

    def __init__(
        self,
        player_id: Optional[str] = None,
        difficulty: str = "hard",  # unused but kept for adapter-shape compat
        model: str = "haiku",
        verbose: bool = False,
        timeout: float = 60.0,
    ):
        self.provider = _ClaudeCodeShell(model=model, timeout=timeout)
        self.player_id = player_id
        self.model = model
        self.verbose = verbose
        self.difficulty = "llm"
        # Heuristic fallback for errors + decisions where LLM call is overkill.
        self._fallback = ClankersAIAdapter(difficulty="hard")
        # Capture every (decision_type, prompt-summary, result) so callers can
        # inspect what the LLM was thinking after a game.
        self.decisions: list[dict] = []

    # ─── Public API (matches ClankersAIAdapter) ──────────────────────

    def choose_assemble_action(self, state, player_id: str) -> Optional[dict]:
        """Pick one action in the Assemble / Reassemble phase loop.

        Returns one of the action dicts per the contract, or {"action": "pass"}
        / None to end the phase.
        """
        legal = self._enumerate_legal_actions(state, player_id)
        if not legal:
            return {"action": "pass"}
        # If only "pass" is legal, skip LLM call.
        if len(legal) == 1 and legal[0].get("action") == "pass":
            return {"action": "pass"}

        try:
            prompt = self._render_assemble_prompt(state, player_id, legal)
            schema = {
                "type": "object",
                "properties": {
                    "slot": {"type": "integer"},
                    "reasoning": {"type": "string"},
                },
                "required": ["slot"],
            }
            result = self._call_llm_json(prompt, schema)
            slot = result.get("slot")
            if not isinstance(slot, int) or not (0 <= slot <= len(legal)):
                return self._fallback.choose_assemble_action(state, player_id)
            # Slot 0 = pass; slots 1..N = legal[slot-1]
            if slot == 0:
                chosen = {"action": "pass"}
            else:
                chosen = legal[slot - 1]
            self._log_decision("choose_assemble_action", prompt, result, chosen)
            if self.verbose:
                print(f"[LLM {player_id}] {chosen.get('action')}: {result.get('reasoning', '')}")
            return chosen
        except Exception as e:
            if self.verbose:
                print(f"[LLM {player_id}] choose_assemble_action error {type(e).__name__}: {e} — falling back")
            return self._fallback.choose_assemble_action(state, player_id)

    def choose_attackers(self, state, player_id: str) -> list[str]:
        """Pick which units attack. Returns list of obj_ids."""
        candidates = self._eligible_attackers(state, player_id)
        if not candidates:
            return []
        # If the heuristic says "attack with all," skip LLM call — common case.
        if len(candidates) <= 1:
            return [c[0] for c in candidates]

        try:
            prompt = self._render_attack_prompt(state, player_id, candidates)
            schema = {
                "type": "object",
                "properties": {
                    "slots": {"type": "array", "items": {"type": "integer"}},
                    "reasoning": {"type": "string"},
                },
                "required": ["slots"],
            }
            result = self._call_llm_json(prompt, schema)
            slots = result.get("slots", [])
            if not isinstance(slots, list):
                return self._fallback.choose_attackers(state, player_id)
            chosen = []
            for s in slots:
                if isinstance(s, int) and 1 <= s <= len(candidates):
                    chosen.append(candidates[s - 1][0])
            self._log_decision("choose_attackers", prompt, result, chosen)
            return chosen
        except Exception as e:
            if self.verbose:
                print(f"[LLM {player_id}] choose_attackers error {type(e).__name__}: {e} — falling back")
            return self._fallback.choose_attackers(state, player_id)

    def choose_blockers(self, state, player_id: str, attackers: list[str]) -> dict[str, str]:
        """For each attacker, pick a blocker (or omit to let through)."""
        defenders = self._eligible_blockers(state, player_id)
        if not defenders or not attackers:
            return {}

        try:
            prompt = self._render_block_prompt(state, player_id, attackers, defenders)
            schema = {
                "type": "object",
                "properties": {
                    "blocks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "attacker_slot": {"type": "integer"},
                                "blocker_slot": {"type": "integer"},
                            },
                            "required": ["attacker_slot", "blocker_slot"],
                        },
                    },
                    "reasoning": {"type": "string"},
                },
                "required": ["blocks"],
            }
            result = self._call_llm_json(prompt, schema)
            blocks_arr = result.get("blocks", [])
            assignments: dict[str, str] = {}
            if not isinstance(blocks_arr, list):
                return self._fallback.choose_blockers(state, player_id, attackers)
            used_blockers: set[str] = set()
            for entry in blocks_arr:
                if not isinstance(entry, dict):
                    continue
                a_slot = entry.get("attacker_slot")
                b_slot = entry.get("blocker_slot")
                if not isinstance(a_slot, int) or not isinstance(b_slot, int):
                    continue
                if 1 <= a_slot <= len(attackers) and 1 <= b_slot <= len(defenders):
                    blocker_id = defenders[b_slot - 1][0]
                    if blocker_id in used_blockers:
                        continue
                    used_blockers.add(blocker_id)
                    assignments[attackers[a_slot - 1]] = blocker_id
            self._log_decision("choose_blockers", prompt, result, assignments)
            return assignments
        except Exception as e:
            if self.verbose:
                print(f"[LLM {player_id}] choose_blockers error {type(e).__name__}: {e} — falling back")
            return self._fallback.choose_blockers(state, player_id, attackers)

    def choose_refill(self, state, player_id: str) -> bool:
        """Take the may-refill? Cheap to LLM-call but often heuristic-correct."""
        # Library has plenty → just take it. Deathclock approaching → ask.
        library_size = self._library_size(state, player_id)
        hand_size = self._hand_size(state, player_id)
        if library_size > 20:
            return True
        if library_size > 7 and hand_size < 4:
            return True
        # Borderline — ask LLM.
        try:
            prompt = (
                f"Refill decision. Library: {library_size} cards. Hand: {hand_size} cards. "
                f"Workshop Integrity (you): {self._workshop_integrity(state, player_id)}/30. "
                f"Refilling takes {7 - hand_size if hand_size < 7 else 0} cards from your library."
                f" Deathclock activates at library size 5."
                f"\n\nShould you take the refill? Respond JSON with 'take': true/false."
            )
            schema = {
                "type": "object",
                "properties": {"take": {"type": "boolean"}, "reasoning": {"type": "string"}},
                "required": ["take"],
            }
            result = self._call_llm_json(prompt, schema)
            take = result.get("take", True)
            self._log_decision("choose_refill", prompt, result, take)
            return bool(take)
        except Exception:
            return True

    def mulligan_decision(self, state, player_id: str, num_kept: int = 7) -> bool:
        """Clankers mulligan — generally we don't mulligan in v1."""
        return False

    def choose_target(self, state, source_id, candidates, requirement) -> Optional[str]:
        """Mid-resolution target picker — small surface, fallback is fine."""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return self._fallback.choose_target(state, source_id, candidates, requirement)

    # ─── Legal-action enumeration (mirror heuristic logic) ───────────

    def _enumerate_legal_actions(self, state, player_id: str) -> list[dict]:
        """Build the list of legal Assemble actions, in display order."""
        # Reuse the heuristic adapter's internal enumerator if it has one.
        try:
            # Most heuristics expose this via the fallback's private helper.
            return self._fallback._legal_actions_for(state, player_id)  # type: ignore[attr-defined]
        except Exception:
            return [{"action": "pass"}]

    def _eligible_attackers(self, state, player_id: str) -> list[tuple[str, str]]:
        """Return [(obj_id, descriptor), ...] for everything that can attack."""
        out: list[tuple[str, str]] = []
        try:
            from src.engine.types import CardType
            assemblies = getattr(state, "clankers_assemblies", {}).get(player_id, [])
            for obj_id in assemblies:
                obj = state.objects.get(obj_id)
                if obj is None or obj.state.tapped:
                    continue
                if obj.state.damage_marked >= self._effective_integrity(state, obj_id):
                    continue
                out.append((obj_id, self._describe_assembly(state, obj_id)))
            # Solo parts on the floor
            for obj_id, obj in state.objects.items():
                if obj.controller != player_id:
                    continue
                if obj.state.attached_to is not None:
                    continue
                if obj.state.tapped:
                    continue
                card_def = obj.card_def
                if card_def is None:
                    continue
                types = getattr(card_def.characteristics, "types", set()) or set()
                if CardType.CLANKERS_WEAPON in types or CardType.CLANKERS_ADD_ON in types:
                    out.append((obj_id, f"solo {card_def.name}"))
        except Exception:
            pass
        return out

    def _eligible_blockers(self, state, player_id: str) -> list[tuple[str, str]]:
        """Same as attackers but for the defender."""
        return self._eligible_attackers(state, player_id)

    # ─── State rendering ─────────────────────────────────────────────

    def _render_assemble_prompt(self, state, player_id: str, legal: list[dict]) -> str:
        body = self._render_state_header(state, player_id)
        body += "\n\n" + self._render_assemblies(state, player_id, "YOUR")
        opp = self._opponent_id(state, player_id)
        body += "\n\n" + self._render_assemblies(state, opp, "OPPONENT'S")
        body += "\n\n" + self._render_hand(state, player_id)
        body += "\n\nLegal actions (slot 0 = pass):\n"
        body += "  0: pass\n"
        for i, action in enumerate(legal, 1):
            body += f"  {i}: {self._describe_action(state, action)}\n"
        body += "\nPick a slot. Return JSON {\"slot\": int, \"reasoning\": str}."
        return body

    def _render_attack_prompt(self, state, player_id: str, candidates: list[tuple[str, str]]) -> str:
        opp = self._opponent_id(state, player_id)
        body = self._render_state_header(state, player_id)
        body += f"\n\nOpponent Workshop Integrity: {self._workshop_integrity(state, opp)}/30."
        body += "\n\n" + self._render_assemblies(state, opp, "OPPONENT'S")
        body += "\n\nYour attackers (eligible):\n"
        for i, (_, desc) in enumerate(candidates, 1):
            body += f"  {i}: {desc}\n"
        body += "\nPick which slots attack (list). Empty = no attack. Return JSON {\"slots\": [int...], \"reasoning\": str}."
        return body

    def _render_block_prompt(self, state, player_id: str, attackers: list[str], defenders: list[tuple[str, str]]) -> str:
        body = self._render_state_header(state, player_id)
        body += f"\n\nYour Workshop Integrity: {self._workshop_integrity(state, player_id)}/30."
        body += "\n\nIncoming attackers:\n"
        for i, a_id in enumerate(attackers, 1):
            body += f"  {i}: {self._describe_assembly(state, a_id)}\n"
        body += "\nYour defenders (eligible):\n"
        for i, (_, desc) in enumerate(defenders, 1):
            body += f"  {i}: {desc}\n"
        body += "\nAssign blocker slots to attacker slots (each blocker only once). Return JSON {\"blocks\": [{\"attacker_slot\": int, \"blocker_slot\": int}, ...], \"reasoning\": str}."
        return body

    def _render_state_header(self, state, player_id: str) -> str:
        opp = self._opponent_id(state, player_id)
        return (
            f"=== Turn {state.turn_number} ===\n"
            f"You ({player_id}): WI {self._workshop_integrity(state, player_id)}/30, "
            f"Compute {self._compute_pool(state, player_id)}, "
            f"Scrap {self._scrap_pool(state, player_id)}, "
            f"Library {self._library_size(state, player_id)}.\n"
            f"Opponent ({opp}): WI {self._workshop_integrity(state, opp)}/30, "
            f"Library {self._library_size(state, opp)}."
        )

    def _render_assemblies(self, state, player_id: str, label: str) -> str:
        out = f"{label} Assembly Floor:"
        assemblies = getattr(state, "clankers_assemblies", {}).get(player_id, [])
        if not assemblies:
            return out + " (empty)"
        for i, obj_id in enumerate(assemblies, 1):
            out += f"\n  {i}: {self._describe_assembly(state, obj_id)}"
        return out

    def _render_hand(self, state, player_id: str) -> str:
        zone_key = f"hand_{player_id}"
        zone = state.zones.get(zone_key)
        if zone is None:
            return "Hand: (zone missing)"
        out = f"Hand (slots):"
        for i, obj_id in enumerate(zone.objects, 1):
            obj = state.objects.get(obj_id)
            if obj is None or obj.card_def is None:
                continue
            cd = obj.card_def
            cost = getattr(cd, "compute_cost", 0)
            arch = getattr(cd, "clankers_archetype", "?")
            out += f"\n  hand-{i}: {cd.name} (Compute {cost}, {arch})"
        return out

    def _describe_assembly(self, state, chassis_id: str) -> str:
        obj = state.objects.get(chassis_id)
        if obj is None or obj.card_def is None:
            return "?"
        cd = obj.card_def
        eff_p = self._effective_power(state, chassis_id)
        eff_i = self._effective_integrity(state, chassis_id)
        dmg = obj.state.damage_marked
        tapped = " TAPPED" if obj.state.tapped else ""
        attached = obj.state.attachments or []
        attached_str = ""
        if attached:
            names = []
            for a_id in attached:
                a = state.objects.get(a_id)
                if a is None or a.card_def is None:
                    continue
                names.append(a.card_def.name)
            attached_str = f" [+ {', '.join(names)}]" if names else ""
        damage_str = f" dmg {dmg}" if dmg else ""
        return f"{cd.name} ({eff_p}/{eff_i}){attached_str}{damage_str}{tapped}"

    def _describe_action(self, state, action: dict) -> str:
        kind = action.get("action", "?")
        if kind == "pass":
            return "pass"
        card_obj_id = action.get("card_obj_id")
        if card_obj_id:
            obj = state.objects.get(card_obj_id)
            if obj is not None and obj.card_def is not None:
                cost = action.get("compute_cost", "?")
                target = action.get("target_chassis_id")
                target_str = ""
                if target is not None:
                    t = state.objects.get(target)
                    if t is not None and t.card_def is not None:
                        target_str = f" → attach to {t.card_def.name}"
                return f"{kind}: {obj.card_def.name} (Compute {cost}){target_str}"
        if kind == "attach_floor_part":
            part = state.objects.get(action.get("part_obj_id", ""))
            target = state.objects.get(action.get("target_chassis_id", ""))
            if part and target and part.card_def and target.card_def:
                return f"attach_floor_part: {part.card_def.name} → {target.card_def.name}"
        if kind == "activate_ability":
            src = state.objects.get(action.get("source_obj_id", ""))
            if src and src.card_def:
                return f"activate_ability: {src.card_def.name}"
        return kind

    # ─── State query helpers ─────────────────────────────────────────

    def _workshop_integrity(self, state, player_id: str) -> int:
        return getattr(state, "clankers_workshop_integrity", {}).get(player_id, 0)

    def _compute_pool(self, state, player_id: str) -> int:
        return getattr(state, "clankers_compute_pool", {}).get(player_id, 0)

    def _scrap_pool(self, state, player_id: str) -> int:
        return getattr(state, "clankers_scrap_pool", {}).get(player_id, 0)

    def _library_size(self, state, player_id: str) -> int:
        zone = state.zones.get(f"library_{player_id}")
        return len(zone.objects) if zone else 0

    def _hand_size(self, state, player_id: str) -> int:
        zone = state.zones.get(f"hand_{player_id}")
        return len(zone.objects) if zone else 0

    def _opponent_id(self, state, player_id: str) -> str:
        for pid in state.players:
            if pid != player_id:
                return pid
        return "?"

    def _effective_power(self, state, chassis_id: str) -> int:
        try:
            from src.engine.clankers import compute_effective_power
            return compute_effective_power(state, chassis_id)
        except Exception:
            return 0

    def _effective_integrity(self, state, chassis_id: str) -> int:
        try:
            from src.engine.clankers import compute_effective_integrity
            return compute_effective_integrity(state, chassis_id)
        except Exception:
            return 0

    # ─── LLM call ─────────────────────────────────────────────────

    def _call_llm_json(self, prompt: str, schema: dict) -> dict:
        coro = self.provider.complete_json(prompt=prompt, schema=schema, system=_SYSTEM_PROMPT)
        try:
            return asyncio.run(coro)
        except RuntimeError as e:
            if "already running" not in str(e).lower():
                raise
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    def _log_decision(self, kind: str, prompt: str, result: dict, chosen: Any) -> None:
        self.decisions.append({
            "kind": kind,
            "prompt_summary": prompt[:200],
            "result": result,
            "chosen": str(chosen)[:200],
        })
