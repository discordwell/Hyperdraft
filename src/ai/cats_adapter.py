"""
Cats AI Adapter.

Heuristic AI for the Cats trick-taking + pile-building card game. Three
difficulty tiers — easy, medium, hard — implementing the behaviors spelled
out in docs/games/cats.md section 9.

Design contract (matched by Agent 3's CatsTurnManager):

    choose_card(state, available_card_ids: list[str]) -> str
    choose_pile(state, won_card_ids: list[str], available_pile_names: list[str]) -> str
    choose_activations(state) -> list[tuple[str, int]]
    mulligan_decision(state) -> bool

Returns are primitives (str, list[tuple]), NOT dataclasses — the depths
case-study showed dataclass-wrapped action returns are a common drift point
causing AttributeError when the turn manager dispatches on them.

This adapter is defensive against missing state fields: if Agent 1 hasn't
shipped the GameState extensions yet (cats_round_number, cats_current_rule,
cats_current_trick, etc.), every method falls back to easy-tier behavior
rather than raising.
"""

from __future__ import annotations

import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.types import GameState, GameObject


# Category names, as installed by the round's Pounce card.
# Must match what Agent 1/2 assigns to the card's category metadata.
_CATEGORY_SLEEK = "Sleek"
_CATEGORY_FLUFFY = "Fluffy"
_CATEGORY_SCRAPPY = "Scrappy"
_CATEGORY_SNEAKY = "Sneaky"

# Pile names. The design doc uses lowercase tokens for the per-player piles
# (territory/nap/snack/attention). The zone enum names are CATS_PILE_*; we
# expose the human-readable strings here because that's what the turn manager
# passes through `available_pile_names`.
_PILE_TERRITORY = "territory"
_PILE_NAP = "nap"
_PILE_SNACK = "snack"
_PILE_ATTENTION = "attention"

# Medium-tier pile preference: snack first (highest pts/card), then nap, then
# territory, then attention as a last resort. Mirrors section 9's "highest-
# scoring pile that isn't full" with a deterministic tie-break.
_MEDIUM_PILE_ORDER = (_PILE_SNACK, _PILE_NAP, _PILE_TERRITORY, _PILE_ATTENTION)

# Pile caps — sourced from docs/games/cats.md section 5.
_PILE_CAPS = {
    _PILE_TERRITORY: 8,
    _PILE_NAP: 6,
    _PILE_SNACK: 5,
    _PILE_ATTENTION: 10**9,  # effectively unlimited
}


class CatsAIAdapter:
    """AI adapter for the Cats engine.

    Three difficulty tiers (easy / medium / hard) with distinct behaviors per
    docs/games/cats.md section 9.

    Usage:
        ai = CatsAIAdapter("medium")
        ai.player_id = "p2"
        card_id = ai.choose_card(state, hand_card_ids)
        pile = ai.choose_pile(state, won_card_ids, available_pile_names)
        activations = ai.choose_activations(state)
    """

    def __init__(self, difficulty: str = "medium"):
        if difficulty not in ("easy", "medium", "hard"):
            raise ValueError(f"Unknown difficulty: {difficulty}")
        self.difficulty = difficulty
        # Set externally after init by the turn manager / Game.set_ai_difficulty.
        self.player_id: Optional[str] = None

    # ─── Public API (called by CatsTurnManager) ──────────────────

    def choose_card(self, state, available_card_ids: list[str]) -> str:
        """Pick a card_obj_id from the player's hand to play this round.

        - easy: random
        - medium: highest-Value card unless installed rule is Scrappy
          (then lowest)
        - hard: 1-round lookahead — score each candidate against opponent's
          likely play
        """
        if not available_card_ids:
            # Pathological case — the turn manager shouldn't call us with an
            # empty hand, but guard anyway so we don't IndexError.
            return ""
        if len(available_card_ids) == 1:
            return available_card_ids[0]

        try:
            if self.difficulty == "easy":
                return self._easy_choose_card(state, available_card_ids)
            if self.difficulty == "medium":
                return self._medium_choose_card(state, available_card_ids)
            return self._hard_choose_card(state, available_card_ids)
        except AttributeError:
            # State is missing fields we expect. Degrade to easy.
            return self._easy_choose_card(state, available_card_ids)

    def choose_pile(
        self,
        state,
        won_card_ids: list[str],
        available_pile_names: list[str],
    ) -> str:
        """Pick which pile to send a won trick to.

        - easy: random non-full pile
        - medium: highest-scoring non-full pile (Snack > Nap > Territory > attention)
        - hard: weigh score-delta vs cap-pressure vs activation-potential
        """
        if not available_pile_names:
            # Shouldn't happen — attention is unlimited. Fail safe.
            return _PILE_ATTENTION
        if len(available_pile_names) == 1:
            return available_pile_names[0]

        try:
            if self.difficulty == "easy":
                return self._easy_choose_pile(state, won_card_ids, available_pile_names)
            if self.difficulty == "medium":
                return self._medium_choose_pile(state, won_card_ids, available_pile_names)
            return self._hard_choose_pile(state, won_card_ids, available_pile_names)
        except AttributeError:
            return self._easy_choose_pile(state, won_card_ids, available_pile_names)

    def choose_activations(self, state) -> list[tuple[str, int]]:
        """Pick which pile-card activations to fire this round.

        Returns a list of (card_id, ability_index) tuples — primitives, NOT
        a dataclass wrapper.

        - easy: never activates
        - medium: only activates when there's an obvious win-now opportunity
        - hard: activates reactively + proactively
        """
        try:
            if self.difficulty == "easy":
                return self._easy_choose_activations(state)
            if self.difficulty == "medium":
                return self._medium_choose_activations(state)
            return self._hard_choose_activations(state)
        except AttributeError:
            return []

    def mulligan_decision(self, state) -> bool:
        """Whether to mulligan the opening hand.

        Cats may not have mulligans yet, but include this method for forward
        compatibility with the per-mode adapter contract.
        """
        return False

    # ─── State-introspection helpers (defensive) ─────────────────

    def _installed_rule_name(self, state) -> Optional[str]:
        """Return 'Sleek' / 'Fluffy' / 'Scrappy' / 'Sneaky' or None.

        Tries multiple state-field shapes because Agent 1 hasn't necessarily
        finalised the GameState container name. Falls back to None on
        AttributeError.

        TODO(reconcile): once Agent 1's PR lands, drop the fallbacks and read
        the canonical field directly.
        """
        if state is None:
            return None
        # Shape 1: state.cats.trick.installed_rule (namespaced container)
        try:
            cats_container = getattr(state, "cats", None)
            if cats_container is not None:
                trick = getattr(cats_container, "trick", None)
                if trick is not None:
                    rule = getattr(trick, "installed_rule", None)
                    if rule:
                        return self._normalize_rule(rule)
        except AttributeError:
            pass
        # Shape 2: state.cats_current_rule (flat field — per the design doc's
        # "Required GameState fields" list in section 8).
        try:
            rule = getattr(state, "cats_current_rule", None)
            if rule:
                return self._normalize_rule(rule)
        except AttributeError:
            pass
        # Shape 3: legacy / alt name
        try:
            rule = getattr(state, "cats_trick_installed_rule", None)
            if rule:
                return self._normalize_rule(rule)
        except AttributeError:
            pass
        return None

    @staticmethod
    def _normalize_rule(rule) -> Optional[str]:
        """Convert whatever Agent 1 stores into one of the 4 category names."""
        if rule is None:
            return None
        # Could be a string ("Sleek"), an enum-like with .name, or a callable
        # whose __name__ encodes the category. Be forgiving.
        if isinstance(rule, str):
            for cat in (_CATEGORY_SLEEK, _CATEGORY_FLUFFY, _CATEGORY_SCRAPPY, _CATEGORY_SNEAKY):
                if rule.lower() == cat.lower() or cat.lower() in rule.lower():
                    return cat
            return None
        for attr in ("name", "__name__", "category"):
            val = getattr(rule, attr, None)
            if isinstance(val, str):
                for cat in (_CATEGORY_SLEEK, _CATEGORY_FLUFFY, _CATEGORY_SCRAPPY, _CATEGORY_SNEAKY):
                    if val.lower() == cat.lower() or cat.lower() in val.lower():
                        return cat
        return None

    def _get_card_object(self, state, card_id: str):
        """Resolve a card object by id, returning None if state is bare."""
        if state is None or not card_id:
            return None
        objects = getattr(state, "objects", None)
        if objects is None:
            return None
        try:
            return objects.get(card_id)
        except AttributeError:
            return None

    def _card_value(self, state, card_id: str) -> int:
        """Read the printed Value (1-10) for a Cat / Mood / Snack card.

        Moods are Value 0 by design. Cards we can't resolve report 0.
        """
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return 0
        # Preferred: card_def.value (per docs section 6 — Cats carry a
        # numeric Value 1-10 + a Category).
        card_def = getattr(obj, "card_def", None)
        if card_def is not None:
            val = getattr(card_def, "value", None)
            if isinstance(val, (int, float)):
                return int(val)
            # Fallback: some engines stash it as cats_value
            val = getattr(card_def, "cats_value", None)
            if isinstance(val, (int, float)):
                return int(val)
        # Last-ditch: characteristics.power (the value compares like P/T)
        try:
            val = obj.characteristics.power
            if isinstance(val, (int, float)):
                return int(val)
        except AttributeError:
            pass
        return 0

    def _card_category(self, state, card_id: str) -> Optional[str]:
        """Read the Category (Sleek/Fluffy/Scrappy/Sneaky) of a Cat card."""
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return None
        card_def = getattr(obj, "card_def", None)
        if card_def is not None:
            cat = getattr(card_def, "category", None)
            if isinstance(cat, str):
                return self._normalize_rule(cat) or cat
            cat = getattr(card_def, "cats_category", None)
            if isinstance(cat, str):
                return self._normalize_rule(cat) or cat
        # Subtypes fallback: some engines store the category as a subtype string
        try:
            for sub in obj.characteristics.subtypes:
                norm = self._normalize_rule(sub)
                if norm:
                    return norm
        except AttributeError:
            pass
        return None

    def _card_type_label(self, state, card_id: str) -> str:
        """Return one of 'cat', 'mood', 'snack', 'trinket', or 'unknown'.

        Used to bias hard-tier scoring (e.g. don't waste a Trinket round
        when there's a high-value Cat in hand).
        """
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
        # Fallback by name heuristic
        card_def = getattr(obj, "card_def", None)
        if card_def is not None:
            name = (getattr(card_def, "name", "") or "").lower()
            for kw in ("mood", "zoomies", "loaf"):
                if kw in name:
                    return "mood"
        return "unknown"

    def _opponent_id(self, state) -> Optional[str]:
        """Return the opponent's player_id, or None if self.player_id unset."""
        if state is None or not self.player_id:
            return None
        players = getattr(state, "players", None)
        if not players:
            return None
        try:
            for pid in players:
                if pid != self.player_id:
                    return pid
        except (AttributeError, TypeError):
            return None
        return None

    def _pile_size(self, state, pile_name: str) -> int:
        """Count cards in this player's named pile.

        Engine truth: ``state.cats_piles[player_id][pile_name]`` is a list
        of card ids. Fall back to zone-name probing if that dict is absent.
        """
        if state is None or not self.player_id:
            return 0
        # Authoritative source: state.cats_piles[pid][pile_name].
        cats_piles = getattr(state, "cats_piles", None)
        if cats_piles:
            try:
                piles = cats_piles.get(self.player_id, {})
                return len(piles.get(pile_name, []))
            except (AttributeError, TypeError):
                pass
        # Fallback: probe zone-name shapes.
        zones = getattr(state, "zones", None)
        if not zones:
            return 0
        zone_name_caps = "CATS_" + pile_name.upper()  # e.g. CATS_PILE_TERRITORY
        candidate_keys = (
            f"{zone_name_caps}_{self.player_id}",       # CATS_PILE_TERRITORY_p1
            f"pile_{pile_name}_{self.player_id}",
            f"cats_pile_{pile_name}_{self.player_id}",
            f"pile_{pile_name}",
            f"cats_pile_{pile_name}",
        )
        for key in candidate_keys:
            try:
                zone = zones.get(key)
            except AttributeError:
                continue
            if zone is None:
                continue
            try:
                return len(zone.objects)
            except AttributeError:
                cards = getattr(zone, "cards", None)
                if cards is not None:
                    return len(cards)
        return 0

    def _is_pile_full(self, state, pile_name: str) -> bool:
        cap = _PILE_CAPS.get(pile_name, 10**9)
        return self._pile_size(state, pile_name) >= cap

    def _hand_card_ids(self, state, player_id: str) -> list[str]:
        """Best-effort: read the named player's hand card ids.

        The cats engine keys zones as ``f"{ZoneType.name}_{owner}"`` which
        for HAND becomes ``HAND_<pid>`` (uppercase). Earlier shapes used
        ``hand_<pid>`` (lowercase) — keep both fallbacks so this works
        across engine generations.
        """
        if state is None or not player_id:
            return []
        zones = getattr(state, "zones", None)
        if not zones:
            return []
        for key in (
            f"HAND_{player_id}",         # current cats engine
            f"hand_{player_id}",         # legacy / lowercase
            f"cats_hand_{player_id}",    # alt naming
        ):
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

    # ─── Easy tier ───────────────────────────────────────────────

    def _easy_choose_card(self, state, card_ids: list[str]) -> str:
        return random.choice(card_ids)

    def _easy_choose_pile(self, state, won_cards, available_piles: list[str]) -> str:
        non_full = [p for p in available_piles if not self._is_pile_full(state, p)]
        return random.choice(non_full or available_piles)

    def _easy_choose_activations(self, state) -> list[tuple[str, int]]:
        return []

    # ─── Medium tier ─────────────────────────────────────────────

    def _medium_choose_card(self, state, card_ids: list[str]) -> str:
        """Highest-Value card unless the installed rule is Scrappy.

        Ties resolve deterministically by sorting by card_id (so that two
        equally-good plays don't oscillate between runs).
        """
        rule = self._installed_rule_name(state)
        scoring = []
        for cid in card_ids:
            val = self._card_value(state, cid)
            scoring.append((val, cid))
        if not scoring:
            return card_ids[0]
        # Sort by card_id first so ties are deterministic; then by value.
        scoring.sort(key=lambda x: x[1])  # stable: cid asc
        if rule == _CATEGORY_SCRAPPY:
            # Lowest value wins under Scrappy → AI should dump cheap.
            scoring.sort(key=lambda x: x[0])
            return scoring[0][1]
        # Default: highest value
        scoring.sort(key=lambda x: x[0], reverse=True)
        return scoring[0][1]

    def _medium_choose_pile(
        self,
        state,
        won_cards,
        available_piles: list[str],
    ) -> str:
        """Preference order: snack > nap > territory > attention.

        Skip piles at cap. If everything is full, fall back to the first
        available (typically attention, which is uncapped).
        """
        available_set = set(available_piles)
        for pref in _MEDIUM_PILE_ORDER:
            if pref in available_set and not self._is_pile_full(state, pref):
                return pref
        # Everything full or no preferences match — fall back.
        return available_piles[0]

    def _medium_choose_activations(self, state) -> list[tuple[str, int]]:
        """Activate only when there's an obvious win-now opportunity.

        Section 9 spec: "play +1 Value to my Cat to break a tie." Cats may
        not have wired pile activations yet — return [] until they do.

        TODO(reconcile): once pile-activation discovery is wired (Agent 3's
        turn manager), inspect state.cats_current_trick for a tie and look
        for "+1 value" pile-card abilities.
        """
        return []

    # ─── Hard tier ───────────────────────────────────────────────

    def _hard_choose_card(self, state, card_ids: list[str]) -> str:
        """1-round lookahead per docs/games/cats.md §9.

        For each card C in my hand, score the expected outcome against each
        plausible opponent response D:

          1. Install the round's Category Rule that would result if either we
             or the opponent played first (depends on whether we're Pounce or
             Counter-pounce — read from state.cats_current_trick).
          2. Use the engine's real ``CATS_CATEGORY_RULES`` to determine the
             winner of (C vs D) under that rule.
          3. Score: pile-score-delta (winner picks best non-full pile),
             cap-pressure (penalty if best pile is near cap),
             knock-over potential (high-value cards in Territory are better),
             snack-force risk (snacks force claim into Snack pile),
             deliberate-loss bonus (sacrifice a junk card when opp dominates).
          4. Average across all D candidates and pick the C with the highest
             expected score. Ties broken by **card name** for cross-run
             determinism (UUIDs are non-deterministic).
        """
        opp_id = self._opponent_id(state)
        opp_likely = self._estimate_opponent_likely_plays(state, opp_id)
        # ``role`` is 'pounce' when no card has been committed yet this round.
        trick = getattr(state, "cats_current_trick", None) or {}
        playing_pounce = trick.get("pounce_card") in (None, "")

        # Bias the deliberate-loss bonus by hand size: if we have ~5 cards we
        # can afford to throw one; if we're down to 2 we need every win.
        my_hand_size = len(self._hand_card_ids(state, self.player_id or "")) if self.player_id else 5

        candidates: list[tuple[float, str, str]] = []
        for cid in card_ids:
            score_acc = 0.0
            n = 0
            for opp_cid in opp_likely or [None]:
                score_acc += self._score_simulated_trick(
                    state, cid, opp_cid, playing_pounce=playing_pounce,
                )
                n += 1
            avg = score_acc / max(n, 1)
            if self._should_deliberately_lose(state, cid, opp_likely, self._installed_rule_name(state)):
                # Only chase the sacrifice if we have hand depth to spare.
                avg += 6.0 if my_hand_size >= 4 else 2.0
            # Tie-break by card name (deterministic). Resolve name once.
            name = self._card_name(state, cid)
            candidates.append((avg, name, cid))

        # Sort: highest score wins; ties broken by name ascending; final
        # tiebreaker is the cid (last resort, still deterministic for any
        # given object set).
        candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
        return candidates[0][2]

    def _card_name(self, state, card_id: str) -> str:
        """Return the printed card name (deterministic tie-break key)."""
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return ""
        card_def = getattr(obj, "card_def", None)
        if card_def is not None:
            name = getattr(card_def, "name", None)
            if isinstance(name, str):
                return name
        return getattr(obj, "name", "") or ""

    def _resolve_simulated_winner(
        self,
        state,
        my_cid: str,
        opp_cid: Optional[str],
        playing_pounce: bool,
    ) -> bool:
        """Run the real engine rule for a hypothetical (my, opp) trick.

        Returns True if I'm predicted to win. Calls into the engine's
        ``CATS_CATEGORY_RULES`` so the simulation matches what
        ``resolve_trick`` would actually do.

        Determines the installed rule by the category of whichever card
        plays first:
          - If we're Pounce, our card's category sets the rule (or Sleek
            for non-Cat types — matching ``install_category_rule``).
          - If we're Counter-pounce, the opponent's card's category set
            the rule already (read from state.cats_current_trick), and
            we just have to play under it.
        """
        # Resolve installed rule callable.
        try:
            from src.engine.cats import (
                CATS_CATEGORY_RULES, sleek_rule,
            )
        except ImportError:
            return False

        # If we're Counter-pounce, the rule is already installed.
        if not playing_pounce:
            trick = getattr(state, "cats_current_trick", None) or {}
            rule_fn = trick.get("installed_rule") or getattr(state, "cats_current_rule", None) or sleek_rule
        else:
            # We're playing first — our card's category installs the rule.
            cat = self._card_category(state, my_cid)
            rule_fn = CATS_CATEGORY_RULES.get(cat or "", sleek_rule) if cat else sleek_rule

        if not callable(rule_fn):
            rule_fn = sleek_rule

        # The engine rules expect the trick dict to expose pounce/counter
        # players. Synthesize a temporary trick view so the rule callables
        # can read player ids without us having to mutate state.
        trick_view = dict(getattr(state, "cats_current_trick", None) or {})
        opp_id = self._opponent_id(state) or "_opp"
        my_id = self.player_id or "_me"
        if playing_pounce:
            trick_view["pounce_player"] = my_id
            trick_view["counter_player"] = opp_id
            pounce_card = my_cid
            counter_card = opp_cid
        else:
            # Opp went first; we're Counter.
            trick_view["counter_player"] = my_id
            if not trick_view.get("pounce_player"):
                trick_view["pounce_player"] = opp_id
            pounce_card = trick_view.get("pounce_card") or opp_cid
            counter_card = my_cid

        if pounce_card is None or counter_card is None:
            # Without an opponent estimate we can't resolve — assume neutral
            # 50/50 → use raw value comparison.
            my_val = self._card_value(state, my_cid)
            opp_val = self._card_value(state, opp_cid) if opp_cid else 5
            return my_val >= opp_val

        # Temporarily install the trick view for the rule callable's read.
        original = getattr(state, "cats_current_trick", None)
        state.cats_current_trick = trick_view
        try:
            winner_id = rule_fn(pounce_card, counter_card, state)
        except Exception:
            winner_id = ""
        finally:
            state.cats_current_trick = original

        return winner_id == my_id

    def _score_simulated_trick(
        self,
        state,
        my_cid: str,
        opp_cid: Optional[str],
        *,
        playing_pounce: bool,
    ) -> float:
        """Score the outcome of (my_cid vs opp_cid) using engine rule fns.

        Returns a heuristic float; higher is better for self. The score
        combines:
          - Trick-outcome bonus (winning is worth +score-of-target-pile×2,
            losing the trick costs the equivalent for opp's pile)
          - Cap pressure on the target pile
          - Knock-over / activation potential (cards in Territory/Nap with
            wired setup_interceptors are utility batteries)
          - Snack-force risk (winning a snack-trick into a full Snack pile
            overflows to Attention which scores 0)
          - Trinket and Mood tempo costs (Trinkets sacrifice a round)
        """
        my_type = self._card_type_label(state, my_cid)
        my_val = self._card_value(state, my_cid)
        opp_type = self._card_type_label(state, opp_cid) if opp_cid else "unknown"

        # Mood values are 0 — already captured by _card_value but reinforce
        # the assumption for the rule fn.
        i_win = self._resolve_simulated_winner(state, my_cid, opp_cid, playing_pounce)

        score = 0.0
        # Strong intrinsic bias toward winning tricks — every win secures 2
        # cards into a scoring pile, every loss surrenders 2 cards to opp.
        # The pile-specific bonuses below tune *which* trick we want to win.
        snack_in_trick = my_type == "snack" or opp_type == "snack"
        target_pile = self._best_available_pile(state) if i_win else None
        if i_win and snack_in_trick:
            target_pile = _PILE_SNACK
            if self._is_pile_full(state, _PILE_SNACK):
                target_pile = _PILE_ATTENTION

        if i_win:
            score += 10.0  # winning a trick is the baseline goal
            if target_pile is not None:
                per_card_score = self._pile_score_potential(target_pile)
                score += per_card_score * 2.0  # 2 cards land per claim
                score -= self._cap_pressure(state, target_pile) * 3.0
                # Knock-over / utility bonus: high-value Cat in Territory.
                if my_type == "cat" and target_pile == _PILE_TERRITORY:
                    if my_val >= 7:
                        score += 2.0
                    elif my_val >= 5:
                        score += 1.0
                # Wired-interceptor bonus: cards with a setup_interceptors
                # function are utility batteries — prefer them.
                if self._has_wired_setup(state, my_cid):
                    score += 1.0
                # Territory bonus pile threshold (≥6 cards = +5 pts).
                if target_pile == _PILE_TERRITORY:
                    cur = self._pile_size(state, _PILE_TERRITORY)
                    if cur < 6 and cur + 2 >= 6:
                        score += 5.0  # crossing the threshold this trick
                # Snack greed penalty: at 5+ cards Snack drops to 1pt/card.
                if target_pile == _PILE_SNACK:
                    cur = self._pile_size(state, _PILE_SNACK)
                    if cur >= 5:
                        score -= 3.0  # we'd be claiming into the penalty zone
        else:
            # Losing — opp gains 2 cards into their best pile. Use Snack as a
            # conservative proxy (medium AI prefers Snack first) so the
            # asymmetry roughly mirrors the win path.
            score -= 6.0  # losing the trick is bad
            score -= self._pile_score_potential(_PILE_SNACK) * 1.5
            # If a snack is in the trick, opp is FORCED into their snack pile
            # — this can hurt opp if their snack pile is already at/above the
            # greed threshold. We can't inspect opp's piles without swapping
            # adapter context, so apply a modest relief.
            if snack_in_trick:
                score += 1.5

        # Trinket tempo cost: a Trinket commits our round-play to attachment,
        # almost always losing the trick. Only worth it with hand depth.
        if my_type == "trinket":
            score -= 4.0  # tempo loss is real
            if self.player_id:
                hand_remaining = len(self._hand_card_ids(state, self.player_id)) - 1
                if hand_remaining >= 3:
                    score += 2.0

        # Mood tempo cost: value 0 means we usually lose the trick under
        # default Sleek (highest wins). But playing a Mood as Counter-pounce
        # can flip a losing rule into a winning one.
        if my_type == "mood":
            if not playing_pounce:
                # Flipping the rule mid-trick → potential reversal value.
                score += 2.0
            else:
                # Pouncing a Mood gives the opp the option to play whatever
                # they like under our chosen rule — risky.
                score -= 1.0

        return score

    def _has_wired_setup(self, state, card_id: str) -> bool:
        """True if this card has setup_interceptors wired (utility battery)."""
        obj = self._get_card_object(state, card_id)
        if obj is None:
            return False
        card_def = getattr(obj, "card_def", None)
        if card_def is None:
            return False
        return getattr(card_def, "setup_interceptors", None) is not None

    def _best_available_pile(self, state) -> str:
        """Pick the highest-scoring non-full pile (for hard-tier scoring)."""
        for pref in _MEDIUM_PILE_ORDER:
            if not self._is_pile_full(state, pref):
                return pref
        return _PILE_ATTENTION

    @staticmethod
    def _pile_score_potential(pile_name: str) -> float:
        """Approximate score-per-card for the named pile."""
        return {
            _PILE_SNACK: 3.0,       # 3pt/card if <5 cards
            _PILE_NAP: 2.0,         # 2pt/card, capped at 12
            _PILE_TERRITORY: 1.5,   # 1pt/card + 2/Trinket + 5 bonus at >=6
            _PILE_ATTENTION: 0.0,
        }.get(pile_name, 0.0)

    def _cap_pressure(self, state, pile_name: str) -> float:
        """Penalty 0.0-1.0 for piles that are close to cap.

        0.0 = empty, 1.0 = full. Computed as size/cap.
        """
        cap = _PILE_CAPS.get(pile_name, 1)
        if cap >= 10**8:  # attention is unbounded
            return 0.0
        size = self._pile_size(state, pile_name)
        return min(1.0, size / max(cap, 1))

    def _estimate_opponent_likely_plays(
        self,
        state,
        opp_id: Optional[str],
    ) -> list[str]:
        """Best-effort guess at what the opponent might play.

        Hard tier needs *something* to score against. If we can see their
        hand (perfect-info testing), use it. Otherwise return [] which makes
        the simulator treat opp_val as a neutral 5.
        """
        if not opp_id:
            return []
        # Some test harnesses make the opponent's hand visible. Try it.
        return self._hand_card_ids(state, opp_id)

    def _should_deliberately_lose(
        self,
        state,
        my_cid: str,
        opp_likely: list[str],
        rule: Optional[str],
    ) -> bool:
        """True if dumping junk is +EV right now.

        Conditions (all must hold):
          - my card value is <=2 (it's junk)
          - opp's likely cards are mostly high-value (avg >=6)
          - the round contains (or will contain) a Snack → forcing opp into
            their Snack pile if they're near cap is a strong play
          - opp's snack pile is full or near full (we can't see this easily,
            so we proxy by "snack" appearing in opp_likely)
        """
        if not opp_likely:
            return False
        my_val = self._card_value(state, my_cid)
        if my_val > 2:
            return False
        opp_vals = [self._card_value(state, c) for c in opp_likely]
        avg_opp = sum(opp_vals) / max(len(opp_vals), 1)
        if avg_opp < 5.5:
            return False
        # Heuristic: snack-force scenario
        opp_has_snack = any(
            self._card_type_label(state, c) == "snack"
            for c in opp_likely
        )
        my_type = self._card_type_label(state, my_cid)
        return opp_has_snack or my_type == "snack"

    def _hard_choose_pile(
        self,
        state,
        won_cards,
        available_piles: list[str],
    ) -> str:
        """Score each available pile by score-delta + activation - cap-pressure.

        Returns the pile_name string (not a dataclass).
        """
        best_pile = available_piles[0]
        best_score = float("-inf")

        for pile in available_piles:
            if self._is_pile_full(state, pile):
                continue
            # Base: score per card * number of cards being claimed
            cards_in = len(won_cards) if won_cards else 1
            score = self._pile_score_potential(pile) * cards_in
            # Activation potential — cards going into territory/nap can be
            # knocked over for utility. Approximate by giving territory a
            # bonus if any won card is high-value.
            if pile == _PILE_TERRITORY and won_cards:
                high_value_count = sum(
                    1 for c in won_cards if self._card_value(state, c) >= 6
                )
                score += high_value_count * 2.0
            # Cap pressure penalty
            score -= self._cap_pressure(state, pile) * 3.0
            # Snack pile greed penalty: at 5+ cards, snack drops from 3pt to 1pt
            if pile == _PILE_SNACK and self._pile_size(state, pile) + cards_in > 5:
                score -= 3.0

            if score > best_score:
                best_score = score
                best_pile = pile

        # If everything was full, fall back to attention or the first available.
        if best_score == float("-inf"):
            return _PILE_ATTENTION if _PILE_ATTENTION in available_piles else available_piles[0]
        return best_pile

    def _hard_choose_activations(self, state) -> list[tuple[str, int]]:
        """Activate reactively + proactively.

        Section 9: "Hard activates pile abilities both reactively (rescue a
        losing trick) and proactively (set up an opponent-disrupting effect
        at Stretch)."

        Pile-activation discovery requires walking each pile zone and
        reading the activated_abilities list on each card object. Until
        Agent 3 wires that into the turn manager, return [] — the AI will
        skip activations rather than fire random ones.

        TODO(reconcile): walk state.zones for each pile, collect cards with
        non-empty obj.state.activated_abilities, score each (cost vs effect)
        and return the best-EV activations.
        """
        if state is None or not self.player_id:
            return []
        try:
            zones = getattr(state, "zones", None)
            if not zones:
                return []
            candidates: list[tuple[float, str, int]] = []
            for pile_name in (_PILE_TERRITORY, _PILE_NAP, _PILE_SNACK):
                for zone_key in (
                    f"pile_{pile_name}_{self.player_id}",
                    f"cats_pile_{pile_name}_{self.player_id}",
                ):
                    zone = zones.get(zone_key) if zones else None
                    if zone is None:
                        continue
                    try:
                        card_ids = list(zone.objects)
                    except AttributeError:
                        card_ids = list(getattr(zone, "cards", []) or [])
                    for cid in card_ids:
                        obj = self._get_card_object(state, cid)
                        if obj is None:
                            continue
                        # Skip already-knocked-over cards (tapped/exhausted)
                        if getattr(obj.state, "tapped", False):
                            continue
                        abilities = getattr(obj.state, "activated_abilities", None) or []
                        for idx, _ab in enumerate(abilities):
                            # Naive: score 1.0 per available activation,
                            # don't proactively fire until we have a real
                            # cost/effect evaluator wired.
                            candidates.append((1.0, cid, idx))
            # Hard tier proactively fires up to 2 activations per round.
            candidates.sort(key=lambda x: x[0], reverse=True)
            return [(cid, idx) for _, cid, idx in candidates[:2]]
        except (AttributeError, TypeError):
            return []
