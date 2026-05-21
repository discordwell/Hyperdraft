"""Cats LLM AI Adapter.

Claude-powered player for the Cats engine. Mirrors the public interface of
``CatsAIAdapter`` (see ``src/ai/cats_adapter.py``):

    choose_card(state, available_card_ids: list[str]) -> str
    choose_pile(state, won_card_ids: list[str], available_pile_names: list[str]) -> str
    choose_activations(state) -> list[tuple[str, int]]
    mulligan_decision(state) -> bool

Each decision renders the game state as a compact, English-language summary and
asks Claude (via the existing ``ClaudeCodeProvider`` shell-out) for a small
JSON-shaped response. The adapter is **synchronous** (the turn manager expects
blocking returns) — we bridge to the async provider via ``asyncio.run()`` per
decision. Subprocess spawn cost is real (~3-8s per call), so expect ~30+ calls
and several minutes for a full 9-round game.

Card IDs are deliberately NOT shown to the LLM. Instead, hand cards are
labelled with slot numbers (1..N) in the rendered prompt and Claude returns the
slot number; we map slot → card_id server-side. This avoids hallucination of
random uuid-shaped strings.

On error (timeout, malformed JSON, out-of-range slot), the adapter falls back
to ``CatsAIAdapter("medium")`` so a game can still complete.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING


@dataclass
class _CatsLLMResponse:
    """Minimal response shape for the inline shellout provider."""
    content: str
    model: str


class _ClaudeCodeShell:
    """Tiny self-contained `claude -p` shellout.

    Inlined here (rather than imported from src.ai.llm.api_provider) so the
    cats LLM tests don't break when that module's WIP state diverges from
    the cats commits. Mirrors the public surface CatsLLMAdapter needs:
    ``complete_json(prompt, schema, system=None)``.
    """

    def __init__(self, model: str = "haiku", timeout: float = 60.0, claude_bin: str = "claude"):
        self.model = model
        self.timeout = timeout
        self.claude_bin = claude_bin

    @property
    def is_available(self) -> bool:
        return shutil.which(self.claude_bin) is not None

    async def complete(self, prompt: str, system: Optional[str] = None) -> _CatsLLMResponse:
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
        return _CatsLLMResponse(
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
        # Strip code-fence wrappers if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip().startswith("```") else "\n".join(lines[1:])
            text = text.strip()
        return json.loads(text)

if TYPE_CHECKING:
    from src.engine.types import GameState


# Category names — match what cards/the engine assign.
_CATEGORY_SLEEK = "Sleek"
_CATEGORY_FLUFFY = "Fluffy"
_CATEGORY_SCRAPPY = "Scrappy"
_CATEGORY_SNEAKY = "Sneaky"

# Pile caps — sourced from docs/games/cats.md §5.
_PILE_CAPS = {
    "pile_territory": 8,
    "pile_nap": 6,
    "pile_snack": 5,
    "pile_attention": 10**9,
    "territory": 8,
    "nap": 6,
    "snack": 5,
    "attention": 10**9,
}


_SYSTEM_PROMPT = """You are an expert player of Cats — a trick-taking + pile-building game about household cats.

Goal: score the most points across territory/nap/snack piles by round 9.

Core rules:
- Each round both players play 1 card. Highest value wins the trick (default Sleek rule), unless a Mood-card overrides it (e.g. lowest-wins, fewer-hand-wins).
- The Pounce card's category installs the round's rule: Sleek=highest wins, Fluffy=highest wins-ties-to-underdog, Scrappy=lowest wins, Sneaky=hidden values compared.
- Winner picks a scoring pile (territory/nap/snack), unless a Snack was in the trick — then Snack pile is forced.
- Territory: 1pt/card +5 bonus if pile >=6 cards. Cap 8.
- Nap: 2pt/card capped at 12pt total. Cap 6.
- Snack: 3pt/card if pile <5 cards (greedy: only 1pt/card after that). Cap 5.
- Attention pile is uncapped — used as a tiebreak only (more attention cards wins ties).
- Moods are Value 0 — they almost always lose under the default rule but rewrite the rule.
- Snacks force the trick winner to claim into Snack (or attention if full).
- Trinkets attach to a pile and provide a passive bonus; playing one means committing your round-play to attachment (you almost always lose the trick).

Play strategically: think about pile caps, the rule-override risk of moods, whether a snack is worth winning or letting opponent take, and whether dumping a junk card now to save a strong card is +EV.

Return ONLY valid JSON matching the requested schema. No extra prose."""


class CatsLLMAdapter:
    """LLM-driven Cats player.

    Constructs the underlying ``ClaudeCodeProvider`` eagerly but does NOT
    verify the CLI is available — the test suite mocks ``complete_json``
    directly. Provider availability is checked lazily inside ``choose_card``
    / ``choose_pile`` and exceptions cascade to the heuristic fallback.

    Usage:
        ai = CatsLLMAdapter(model="haiku", verbose=True)
        ai.player_id = "p1"
        card_id = ai.choose_card(state, hand_ids)
        pile    = ai.choose_pile(state, won_ids, ["pile_territory", "pile_nap", "pile_snack"])
    """

    def __init__(
        self,
        model: str = "haiku",
        verbose: bool = False,
        timeout: float = 60.0,
    ):
        # Inline shellout — no dependency on src.ai.llm.api_provider, which
        # may have WIP state that diverges from the cats commits.
        self.provider = _ClaudeCodeShell(model=model, timeout=timeout)
        self.player_id: Optional[str] = None
        self.model = model
        self.verbose = verbose
        # Capture every (decision_type, prompt-summary, result) so callers can
        # inspect what the LLM was thinking after a game.
        self.decisions: list[dict] = []

    # ─── Public API (matches CatsAIAdapter) ──────────────────────

    def choose_card(self, state, available_card_ids: list[str]) -> str:
        """Pick a card to play this round.

        Returns the card_obj_id. Falls back to heuristic medium on any error
        (timeout / parse failure / invalid slot index).
        """
        if not available_card_ids:
            return ""
        if len(available_card_ids) == 1:
            return available_card_ids[0]

        try:
            prompt = self._render_choose_card_prompt(state, available_card_ids)
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
            if not isinstance(slot, int) or not (1 <= slot <= len(available_card_ids)):
                # LLM gave nonsense — fall back.
                return self._fallback_card_choice(state, available_card_ids)
            chosen = available_card_ids[slot - 1]
            self._log_decision("choose_card", prompt, result, chosen)
            if self.verbose:
                name = self._card_name(state, chosen)
                print(f"[LLM {self.player_id}] plays slot {slot} ({name}): "
                      f"{result.get('reasoning', '<no reasoning>')}")
            return chosen
        except Exception as e:
            if self.verbose:
                print(f"[LLM {self.player_id}] choose_card error {type(e).__name__}: {e} — falling back")
            return self._fallback_card_choice(state, available_card_ids)

    def choose_pile(
        self,
        state,
        won_card_ids: list[str],
        available_pile_names: list[str],
    ) -> str:
        """Pick which pile to send the trick to.

        Returns the pile name string (whatever string the caller listed in
        ``available_pile_names`` — typically "pile_territory" / "pile_nap" /
        "pile_snack" / "pile_attention"). Falls back to a snack-first
        preference order on error.
        """
        if not available_pile_names:
            return "pile_attention"
        if len(available_pile_names) == 1:
            return available_pile_names[0]

        try:
            prompt = self._render_choose_pile_prompt(state, won_card_ids, available_pile_names)
            schema = {
                "type": "object",
                "properties": {
                    "pile": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["pile"],
            }
            result = self._call_llm_json(prompt, schema)
            pile = result.get("pile", "")
            # Allow either the raw string ("pile_territory") or shorthand
            # ("territory") — normalize and look up.
            if pile not in available_pile_names:
                pile_norm = self._normalize_pile_name(pile, available_pile_names)
                if pile_norm is None:
                    return self._fallback_pile_choice(state, available_pile_names)
                pile = pile_norm
            self._log_decision("choose_pile", prompt, result, pile)
            if self.verbose:
                print(f"[LLM {self.player_id}] claims to {pile}: "
                      f"{result.get('reasoning', '<no reasoning>')}")
            return pile
        except Exception as e:
            if self.verbose:
                print(f"[LLM {self.player_id}] choose_pile error {type(e).__name__}: {e} — falling back")
            return self._fallback_pile_choice(state, available_pile_names)

    def choose_activations(self, state) -> list[tuple[str, int]]:
        """Pile activations.

        Cats's activated abilities are rare and the engine's discovery
        surface isn't fully wired (see ``CatsAIAdapter._hard_choose_activations``
        which also returns []). For v1 we punt — never activate. A future
        version could ask Claude for an activation plan once the turn manager
        exposes the activation legality table.
        """
        return []

    def mulligan_decision(self, state) -> bool:
        """Mulligan opening hand. Cats doesn't ship mulligans — always False."""
        return False

    # ─── LLM call (sync over async) ──────────────────────────────

    def _call_llm_json(self, prompt: str, schema: dict) -> dict:
        """Bridge sync caller -> async provider. Raises on subprocess failure."""
        coro = self.provider.complete_json(
            prompt=prompt,
            schema=schema,
            system=_SYSTEM_PROMPT,
        )
        # asyncio.run() requires there's no running loop. The cats turn
        # manager calls synchronously so this is safe.
        try:
            return asyncio.run(coro)
        except RuntimeError as e:
            # If we're already inside a loop (unusual — would mean a server
            # called us), fall back to a fresh event loop manually.
            if "already running" not in str(e).lower() and "asyncio.run" not in str(e).lower():
                raise
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    # ─── Prompt rendering ────────────────────────────────────────

    def _render_choose_card_prompt(self, state, available_card_ids: list[str]) -> str:
        """Build the 'choose a card to play' prompt.

        Returns a ~30-line text rendering covering round number, lead role,
        pile contents (both players), hand contents with slot numbers, current
        trick state, and the active rule.
        """
        body = self._render_state_header(state)
        body += "\n" + self._render_piles(state)
        body += "\n" + self._render_trick(state)
        body += "\n" + self._render_hand_with_slots(state, available_card_ids)
        body += (
            f"\n\nYou are seat {self.player_id}. Choose which card to play this round.\n"
            f"Return JSON: {{\"slot\": <1..{len(available_card_ids)}>, \"reasoning\": \"<one sentence>\"}}"
        )
        return body

    def _render_choose_pile_prompt(
        self,
        state,
        won_card_ids: list[str],
        available_pile_names: list[str],
    ) -> str:
        """Build the 'choose a pile to claim into' prompt."""
        body = self._render_state_header(state)
        body += "\n" + self._render_piles(state)
        body += "\n" + self._render_won_cards(state, won_card_ids)
        # Show pile caps + how close each is to full.
        body += "\n\nAvailable piles to claim into:"
        for pile in available_pile_names:
            size = self._pile_size(state, pile)
            cap = _PILE_CAPS.get(pile, 0)
            cap_str = "∞" if cap > 10**6 else str(cap)
            body += f"\n  - {pile}: {size}/{cap_str}"
        body += (
            f"\n\nYou are seat {self.player_id}. You won the trick. Choose a pile.\n"
            f"Return JSON: {{\"pile\": \"<one of {available_pile_names}>\", \"reasoning\": \"<one sentence>\"}}"
        )
        return body

    def _render_state_header(self, state) -> str:
        round_num = getattr(state, "cats_round_number", 1) or 1
        lead = getattr(state, "cats_lead_player", None) or "?"
        rule_name = self._installed_rule_name(state) or "Sleek (highest wins)"
        return (
            f"=== CATS — round {round_num} of 9 ===\n"
            f"Lead player (plays second this round): {lead}\n"
            f"Installed trick rule: {rule_name}"
        )

    def _render_piles(self, state) -> str:
        """Render both players' pile contents (just NAMES, not ids)."""
        lines = ["Piles:"]
        for pid in self._all_player_ids(state):
            tag = "YOU" if pid == self.player_id else "OPP"
            piles_dict = getattr(state, "cats_piles", {}).get(pid, {}) or {}
            parts = []
            for pile_name in ("pile_territory", "pile_nap", "pile_snack", "pile_attention"):
                cap = _PILE_CAPS.get(pile_name, 0)
                cap_str = "∞" if cap > 10**6 else str(cap)
                cards = piles_dict.get(pile_name, []) or []
                short_pile = pile_name.replace("pile_", "")
                if not cards:
                    parts.append(f"  {short_pile}: empty (0/{cap_str})")
                else:
                    names = [self._card_name(state, c) or "?" for c in cards]
                    parts.append(f"  {short_pile}: [{', '.join(names)}] ({len(cards)}/{cap_str})")
            lines.append(f" {tag} ({pid}):")
            lines.extend(parts)
        # Hand sizes (you see your own contents below; for opp show count only).
        opp = self._opponent_id(state)
        if opp:
            opp_hand = self._hand_card_ids(state, opp)
            lines.append(f"Opponent hand size: {len(opp_hand)} cards")
        return "\n".join(lines)

    def _render_trick(self, state) -> str:
        trick = getattr(state, "cats_current_trick", None) or {}
        pounce_cid = trick.get("pounce_card")
        counter_cid = trick.get("counter_card")
        lines = ["Current trick:"]
        if pounce_cid:
            ppid = trick.get("pounce_player", "?")
            lines.append(f"  Pounce ({ppid}): {self._describe_card(state, pounce_cid)}")
        else:
            lines.append("  Pounce: not yet played")
        if counter_cid:
            cpid = trick.get("counter_player", "?")
            lines.append(f"  Counter ({cpid}): {self._describe_card(state, counter_cid)}")
        else:
            lines.append("  Counter: not yet played")
        return "\n".join(lines)

    def _render_hand_with_slots(self, state, available_card_ids: list[str]) -> str:
        """Render the hand as slot-numbered card descriptions."""
        lines = ["Your hand (legal plays this round):"]
        for i, cid in enumerate(available_card_ids, start=1):
            lines.append(f"  {i}. {self._describe_card(state, cid, full=True)}")
        return "\n".join(lines)

    def _render_won_cards(self, state, won_card_ids: list[str]) -> str:
        """Render the cards being claimed."""
        if not won_card_ids:
            return "Won trick (no cards listed)."
        lines = ["Cards you won (about to claim):"]
        for cid in won_card_ids:
            lines.append(f"  - {self._describe_card(state, cid)}")
        return "\n".join(lines)

    def _describe_card(self, state, card_id: str, full: bool = False) -> str:
        """Compact rendering of a card.

        Default form (1 line):
            "Mister Whiskers (Sleek, Value 7)"
        Full form (extends with effect text):
            "Mister Whiskers (Sleek, Value 7) — When this wins a trick, peek at opp hand."
        """
        if not card_id:
            return "?"
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return f"<unknown card {card_id[:6]}>"
        card_def = getattr(obj, "card_def", None)
        name = (getattr(card_def, "name", None) if card_def else None) or "<noname>"
        value = self._card_value(state, card_id)
        cat = self._card_category(state, card_id)
        type_label = self._card_type_label(state, card_id)
        # Build the "label" parenthetical.
        if type_label == "mood":
            label = f"Mood, Value {value}"
        elif type_label == "snack":
            label = f"Snack, Value {value}"
        elif type_label == "trinket":
            attaches = getattr(card_def, "cats_attaches_to", None) if card_def else None
            label = f"Trinket -> {attaches or 'pile'}"
        elif cat:
            label = f"{cat}, Value {value}"
        else:
            label = f"Value {value}"
        text = (getattr(card_def, "text", "") or "").strip() if card_def else ""
        # Truncate long text in the compact form.
        if full and text:
            return f"{name} ({label}) — {text}"
        if text and not full:
            short = text if len(text) <= 60 else (text[:57] + "...")
            return f"{name} ({label}) — {short}"
        return f"{name} ({label})"

    # ─── State helpers ───────────────────────────────────────────

    def _all_player_ids(self, state) -> list[str]:
        players = getattr(state, "players", None) or {}
        try:
            return list(players)
        except TypeError:
            return []

    def _opponent_id(self, state) -> Optional[str]:
        if not self.player_id:
            return None
        for pid in self._all_player_ids(state):
            if pid != self.player_id:
                return pid
        return None

    def _get_card_object(self, state, card_id: str):
        if not card_id:
            return None
        objects = getattr(state, "objects", None)
        if objects is None:
            return None
        try:
            return objects.get(card_id)
        except AttributeError:
            return None

    def _card_name(self, state, card_id: str) -> str:
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return ""
        card_def = getattr(obj, "card_def", None)
        if card_def is not None:
            n = getattr(card_def, "name", None)
            if isinstance(n, str):
                return n
        return getattr(obj, "name", "") or ""

    def _card_value(self, state, card_id: str) -> int:
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return 0
        card_def = getattr(obj, "card_def", None)
        if card_def is not None:
            v = getattr(card_def, "cats_value", None)
            if isinstance(v, (int, float)):
                return int(v)
            v = getattr(card_def, "value", None)
            if isinstance(v, (int, float)):
                return int(v)
        try:
            v = obj.characteristics.power
            if isinstance(v, (int, float)):
                return int(v)
        except AttributeError:
            pass
        return 0

    def _card_category(self, state, card_id: str) -> Optional[str]:
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return None
        card_def = getattr(obj, "card_def", None)
        if card_def is not None:
            cat = getattr(card_def, "cats_category", None)
            if isinstance(cat, str) and cat:
                return cat
        return None

    def _card_type_label(self, state, card_id: str) -> str:
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return "unknown"
        try:
            from src.engine.types import CardType
            types = obj.characteristics.types
            if CardType.CATS_CAT in types:
                return "cat"
            if CardType.CATS_MOOD in types:
                return "mood"
            if CardType.CATS_SNACK in types:
                return "snack"
            if CardType.CATS_TRINKET in types:
                return "trinket"
        except (ImportError, AttributeError):
            pass
        return "unknown"

    def _installed_rule_name(self, state) -> Optional[str]:
        """Return a human-readable rule label."""
        trick = getattr(state, "cats_current_trick", None) or {}
        rule = trick.get("installed_rule") or getattr(state, "cats_current_rule", None)
        if rule is None:
            return None
        if isinstance(rule, str):
            return rule
        name = getattr(rule, "__name__", None)
        if isinstance(name, str):
            # Map engine fn names → human strings.
            label_map = {
                "sleek_rule": "Sleek (highest wins)",
                "fluffy_rule": "Fluffy (highest wins, ties to fewer-pile-cards)",
                "scrappy_rule": "Scrappy (LOWEST wins)",
                "sneaky_rule": "Sneaky (hidden values compared)",
            }
            return label_map.get(name, name)
        return None

    def _pile_size(self, state, pile_name: str) -> int:
        if not self.player_id:
            return 0
        piles = getattr(state, "cats_piles", {}) or {}
        try:
            return len(piles.get(self.player_id, {}).get(pile_name, []))
        except (AttributeError, TypeError):
            return 0

    def _hand_card_ids(self, state, player_id: str) -> list[str]:
        zones = getattr(state, "zones", None)
        if not zones:
            return []
        for key in (f"HAND_{player_id}", f"hand_{player_id}", f"cats_hand_{player_id}"):
            try:
                zone = zones.get(key)
            except AttributeError:
                continue
            if zone is None:
                continue
            try:
                return list(zone.objects)
            except AttributeError:
                cards = getattr(zone, "cards", None)
                if cards is not None:
                    return list(cards)
        return []

    @staticmethod
    def _normalize_pile_name(pile: Any, available: list[str]) -> Optional[str]:
        """Map a loose pile string (e.g. 'territory', 'snack pile') to one of available."""
        if not isinstance(pile, str):
            return None
        s = pile.strip().lower().replace(" ", "_")
        for cand in available:
            if cand.lower() == s:
                return cand
            short = cand.replace("pile_", "").lower()
            if short == s or s.endswith(short):
                return cand
        return None

    # ─── Fallback / heuristic delegation ─────────────────────────

    def _fallback_card_choice(self, state, card_ids: list[str]) -> str:
        """Delegate to heuristic medium on failure."""
        try:
            from src.ai.cats_adapter import CatsAIAdapter
            h = CatsAIAdapter("medium")
            h.player_id = self.player_id
            return h.choose_card(state, card_ids)
        except Exception:
            return card_ids[0] if card_ids else ""

    def _fallback_pile_choice(self, state, available: list[str]) -> str:
        """Delegate to heuristic medium on failure."""
        try:
            from src.ai.cats_adapter import CatsAIAdapter
            h = CatsAIAdapter("medium")
            h.player_id = self.player_id
            return h.choose_pile(state, [], available)
        except Exception:
            return available[0] if available else "pile_attention"

    # ─── Decision logging ────────────────────────────────────────

    def _log_decision(self, kind: str, prompt: str, result: dict, chosen: Any) -> None:
        self.decisions.append({
            "type": kind,
            "prompt_chars": len(prompt),
            "result": result,
            "chosen": chosen,
        })
