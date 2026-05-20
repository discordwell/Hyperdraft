"""
Cats Trick Resolution Manager.

Despite the ``_combat`` filename (chosen to stay consistent with sibling
engine modules like ``minecraft_combat.py``, ``finance_combat.py``,
``hearthstone_combat.py``), this module implements **trick resolution**,
not combat. The Cats engine has no attacker/blocker model: each round both
players commit one card to a shared trick, and a Category-specific
comparison rule (possibly overridden by a Mood) determines the winner.

See ``docs/games/cats.md`` sections 3, 4, and 7 for the full design.

Pipeline (per round)::

    Stretch -> Pounce -> Counter-pounce -> Resolve trick -> Claim pile -> Curl up

This manager is invoked by the turn manager during phases 2-4. It owns the
in-flight ``state.cats.trick`` (or whatever container Agent 1 chose) and
the side effects of resolution — emitting ``CATS_CARD_PLAYED`` and
``CATS_TRICK_RESOLVE`` events so card interceptors (on_play, on_win_trick,
on_lose_trick) fire correctly.

Ownership:
    Owns ONLY this file. Helpers, state-container shapes, and category
    rule functions come from ``src.engine.cats`` (Agent 1). If those
    symbols aren't present at import time we fall back to module-local
    definitions so this file can be loaded standalone for tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.engine.types import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    Player,
)


# ---------------------------------------------------------------------------
# Imports from Agent 1's cats.py — wrapped in try/except so this module can
# load before cats.py exists or while its API is still settling. The
# fallbacks are minimal stand-ins matching the design doc's contract; they
# will be replaced at runtime by the real symbols once cats.py is on the
# import path. Reconciliation step is mechanical: confirm names match and
# remove the fallback branch (or leave it as a safety net).
# ---------------------------------------------------------------------------

_USING_CATS_FALLBACK = False
try:  # pragma: no cover - exercised once Agent 1 lands cats.py
    from src.engine.cats import (  # type: ignore
        CATS_CATEGORY_RULES,
        play_card_to_trick,
        install_category_rule,
        resolve_trick as _agent1_resolve_trick,
        claim_pile,
    )
except Exception:  # pragma: no cover - fallback only used pre-Agent-1
    _USING_CATS_FALLBACK = True
    # TODO: reconciliation — confirm Agent 1's cats.py exports:
    #   CATS_CATEGORY_RULES (dict[str, Callable])
    #   play_card_to_trick(state, player_id, card_obj_id) -> list[Event]
    #   install_category_rule(state, category_name) -> None
    #   resolve_trick(state) -> tuple[str, list[Event]]
    #   claim_pile(state, player_id, pile_name, cards) -> list[Event]
    CATS_CATEGORY_RULES = {}  # type: ignore
    play_card_to_trick = None  # type: ignore
    install_category_rule = None  # type: ignore
    _agent1_resolve_trick = None  # type: ignore
    claim_pile = None  # type: ignore


# State container shapes are also imported lazily — Agent 1 may name them
# differently (``CatsTrickState`` vs ``CatsRoundState``, ``CatsEngineState``
# vs ``CatsGameState``). Defer the import to method bodies for safety.


# ---------------------------------------------------------------------------
# Card-type helpers
# ---------------------------------------------------------------------------

def _is_cats_mood(obj: Optional[GameObject]) -> bool:
    """True if ``obj`` is a Cats Mood card."""
    if obj is None:
        return False
    try:
        return CardType.CATS_MOOD in obj.characteristics.types  # type: ignore[attr-defined]
    except AttributeError:
        # CATS_MOOD enum value not yet added by Agent 1.
        # Fall back to a subtype tag or marker on the card.
        subtypes = getattr(obj.characteristics, "subtypes", set()) or set()
        return "Mood" in subtypes


def _is_cats_snack(obj: Optional[GameObject]) -> bool:
    """True if ``obj`` is a Cats Snack card."""
    if obj is None:
        return False
    try:
        return CardType.CATS_SNACK in obj.characteristics.types  # type: ignore[attr-defined]
    except AttributeError:
        subtypes = getattr(obj.characteristics, "subtypes", set()) or set()
        return "Snack" in subtypes


def _is_cats_cat(obj: Optional[GameObject]) -> bool:
    """True if ``obj`` is a (regular) Cats Cat card."""
    if obj is None:
        return False
    try:
        return CardType.CATS_CAT in obj.characteristics.types  # type: ignore[attr-defined]
    except AttributeError:
        subtypes = getattr(obj.characteristics, "subtypes", set()) or set()
        return "Cat" in subtypes


def _card_value(obj: Optional[GameObject]) -> int:
    """Public Value used in trick comparison.

    Moods are explicitly Value 0 (per docs/games/cats.md §6). For Cats and
    Snacks we read the standard ``power`` slot on Characteristics — which
    is the natural home for a numeric Value in the GameObject shape. If
    Agent 1 stored Value somewhere else (e.g. ``card_def.cats_value``),
    that attribute wins.
    """
    if obj is None:
        return 0
    if _is_cats_mood(obj):
        return 0

    # Preferred: explicit Value on card_def set by Agent 1's loader.
    card_def = getattr(obj, "card_def", None)
    if card_def is not None:
        v = getattr(card_def, "cats_value", None)
        if isinstance(v, int):
            return v

    # Mirrored onto object.state by zone-change setup, if Agent 1 chose that path.
    v = getattr(obj.state, "cats_value", None)
    if isinstance(v, int):
        return v

    # Fall back to the MTG-style power slot.
    pwr = obj.characteristics.power
    if isinstance(pwr, int):
        return pwr
    return 0


def _card_sneaky_value(obj: Optional[GameObject]) -> int:
    """Hidden ``sneaky_value`` used by the Sneaky comparison rule.

    Per design: stored on CardDefinition (fixed per printing). Falls back
    to public Value if missing.
    """
    if obj is None:
        return 0
    card_def = getattr(obj, "card_def", None)
    if card_def is not None:
        v = getattr(card_def, "sneaky_value", None)
        if isinstance(v, int):
            return v
    v = getattr(obj.state, "sneaky_value", None)
    if isinstance(v, int):
        return v
    return _card_value(obj)


def _card_category(obj: Optional[GameObject]) -> Optional[str]:
    """Return the card's Category string ('Sleek'|'Fluffy'|'Scrappy'|'Sneaky')."""
    if obj is None:
        return None
    card_def = getattr(obj, "card_def", None)
    if card_def is not None:
        cat = getattr(card_def, "cats_category", None)
        if isinstance(cat, str):
            return cat
    cat = getattr(obj.state, "cats_category", None)
    if isinstance(cat, str):
        return cat
    # Fall back to subtype intersection.
    subs = getattr(obj.characteristics, "subtypes", set()) or set()
    for known in ("Sleek", "Fluffy", "Scrappy", "Sneaky"):
        if known in subs:
            return known
    return None


# ---------------------------------------------------------------------------
# Trick-state access (resilient to Agent 1's naming choice)
# ---------------------------------------------------------------------------

def _get_cats_state(state: GameState) -> Any:
    """Return Agent 1's cats engine-state container, creating a tiny shim
    if it's missing so testing can proceed.
    """
    if state is None:
        return None
    cs = getattr(state, "cats", None)
    if cs is not None:
        return cs
    # Some engines flatten state fields onto GameState directly (e.g.
    # ``cats_current_trick``, ``cats_round_number``). Build a transient
    # adapter for the trick container.
    trick = getattr(state, "cats_current_trick", None)
    if trick is not None:
        @dataclass
        class _FlatCatsShim:
            trick: Any
        return _FlatCatsShim(trick=trick)
    return None


def _get_trick(state: GameState) -> Any:
    """Return the current trick container (whatever Agent 1 named it)."""
    if state is None:
        return None
    cs = _get_cats_state(state)
    if cs is not None:
        trick = getattr(cs, "trick", None)
        if trick is not None:
            return trick
    return getattr(state, "cats_current_trick", None)


def _trick_cards(trick: Any) -> dict[str, Optional[str]]:
    """Normalize trick contents to ``{player_id: card_obj_id_or_None}``.

    Accepts several plausible shapes Agent 1 might use:
      - dict[str, str] keyed by player_id
      - dataclass with ``.pounce_card`` / ``.counter_card`` and
        ``.pounce_player`` / ``.counter_player`` attributes
      - object exposing ``.cards`` dict
    """
    if trick is None:
        return {}
    # Plain dict shape
    if isinstance(trick, dict):
        # Could be either the cards dict itself or a wrapper with 'cards' key
        if "cards" in trick and isinstance(trick["cards"], dict):
            return dict(trick["cards"])
        # If every value looks like a string id, assume it IS the cards map.
        if all(v is None or isinstance(v, str) for v in trick.values()):
            return {k: v for k, v in trick.items() if not k.startswith("_")}
    # Object with a cards dict attribute
    cards_attr = getattr(trick, "cards", None)
    if isinstance(cards_attr, dict):
        return dict(cards_attr)
    # Dataclass with pounce/counter pairs
    out: dict[str, Optional[str]] = {}
    p_player = getattr(trick, "pounce_player", None)
    p_card = getattr(trick, "pounce_card", None)
    c_player = getattr(trick, "counter_player", None)
    c_card = getattr(trick, "counter_card", None)
    if p_player:
        out[p_player] = p_card
    if c_player:
        out[c_player] = c_card
    return out


def _trick_pounce_info(trick: Any) -> tuple[Optional[str], Optional[str]]:
    """Return ``(pounce_player_id, pounce_card_obj_id)`` if known."""
    if trick is None:
        return (None, None)
    p_player = getattr(trick, "pounce_player", None)
    p_card = getattr(trick, "pounce_card", None)
    if p_player or p_card:
        return (p_player, p_card)
    if isinstance(trick, dict):
        return (trick.get("pounce_player"), trick.get("pounce_card"))
    return (None, None)


def _trick_counter_info(trick: Any) -> tuple[Optional[str], Optional[str]]:
    """Return ``(counter_player_id, counter_card_obj_id)`` if known."""
    if trick is None:
        return (None, None)
    c_player = getattr(trick, "counter_player", None)
    c_card = getattr(trick, "counter_card", None)
    if c_player or c_card:
        return (c_player, c_card)
    if isinstance(trick, dict):
        return (trick.get("counter_player"), trick.get("counter_card"))
    return (None, None)


def _set_trick_pounce(trick: Any, player_id: str, card_id: str) -> None:
    """Best-effort: record the Pounce card in the trick container."""
    if trick is None:
        return
    if hasattr(trick, "pounce_player"):
        try:
            trick.pounce_player = player_id  # type: ignore[attr-defined]
            trick.pounce_card = card_id  # type: ignore[attr-defined]
            return
        except AttributeError:
            pass
    if isinstance(trick, dict):
        trick["pounce_player"] = player_id
        trick["pounce_card"] = card_id
        # If the dict is being used as a player_id -> card_id map, mirror.
        if not any(k in ("pounce_player", "counter_player") for k in list(trick.keys())[:0]):
            trick[player_id] = card_id


def _set_trick_counter(trick: Any, player_id: str, card_id: str) -> None:
    """Best-effort: record the Counter-pounce card."""
    if trick is None:
        return
    if hasattr(trick, "counter_player"):
        try:
            trick.counter_player = player_id  # type: ignore[attr-defined]
            trick.counter_card = card_id  # type: ignore[attr-defined]
            return
        except AttributeError:
            pass
    if isinstance(trick, dict):
        trick["counter_player"] = player_id
        trick["counter_card"] = card_id


def _trick_installed_rule(trick: Any) -> Optional[Callable]:
    """The rule installed by the Pounce card's category (if any)."""
    if trick is None:
        return None
    rule = getattr(trick, "installed_rule", None)
    if callable(rule):
        return rule
    if isinstance(trick, dict):
        rule = trick.get("installed_rule")
        if callable(rule):
            return rule
    return None


def _set_trick_installed_rule(trick: Any, rule_fn: Callable) -> None:
    if trick is None:
        return
    if hasattr(trick, "installed_rule"):
        try:
            trick.installed_rule = rule_fn  # type: ignore[attr-defined]
            return
        except AttributeError:
            pass
    if isinstance(trick, dict):
        trick["installed_rule"] = rule_fn


# ---------------------------------------------------------------------------
# Pile-count helpers (used for Fluffy / Scrappy tie-breaker)
# ---------------------------------------------------------------------------

def _count_pile_cards(state: GameState, player_id: str) -> int:
    """Total cards across a player's three SCORING piles
    (territory + nap + snack). Excludes attention per the design — only
    scoring piles count for the "underdog" tie-breaker.
    """
    if state is None or not player_id:
        return 0
    total = 0
    for pile_attr in ("pile_territory", "pile_nap", "pile_snack"):
        # Try state.zones keyed by per-player pile name first.
        zone_key = f"{pile_attr}_{player_id}"
        z = state.zones.get(zone_key) if state.zones else None
        if z is not None:
            total += len(z.objects)
            continue
        # Try player.cats_piles dict shape.
        player = state.players.get(player_id) if state.players else None
        if player is not None:
            piles = getattr(player, "cats_piles", None)
            if isinstance(piles, dict):
                p = piles.get(pile_attr.replace("pile_", ""), None)
                if isinstance(p, list):
                    total += len(p)
                    continue
        # Try state.cats_piles[player_id][pile_name].
        cats_piles = getattr(state, "cats_piles", None)
        if isinstance(cats_piles, dict):
            ppiles = cats_piles.get(player_id) if isinstance(cats_piles.get(player_id), dict) else None
            if ppiles:
                p = ppiles.get(pile_attr.replace("pile_", ""), None)
                if isinstance(p, list):
                    total += len(p)
    return total


# ---------------------------------------------------------------------------
# Category rules — default implementations (Agent 1 may export richer ones)
# ---------------------------------------------------------------------------

def sleek_rule(
    card_a: GameObject,
    card_b: GameObject,
    state: GameState,
    *,
    player_a: Optional[str] = None,
    player_b: Optional[str] = None,
    lead_player: Optional[str] = None,
) -> str:
    """Sleek (default): highest Value wins. Ties go to the lead player
    (whoever played second — Counter-pounce).
    """
    va = _card_value(card_a)
    vb = _card_value(card_b)
    pa = player_a or (card_a.controller if card_a else None)
    pb = player_b or (card_b.controller if card_b else None)
    if va > vb:
        return pa or ""
    if vb > va:
        return pb or ""
    # Tie: lead player wins. ``lead_player`` is the Counter-pounce player.
    if lead_player in (pa, pb):
        return lead_player or ""
    # No lead known -> default to player_b (Counter-pounce side) per design.
    return pb or pa or ""


def fluffy_rule(
    card_a: GameObject,
    card_b: GameObject,
    state: GameState,
    *,
    player_a: Optional[str] = None,
    player_b: Optional[str] = None,
    lead_player: Optional[str] = None,
) -> str:
    """Fluffy: highest Value wins; ties go to the player with FEWER total
    cards across scoring piles (the underdog social tie-break).
    """
    va = _card_value(card_a)
    vb = _card_value(card_b)
    pa = player_a or (card_a.controller if card_a else None)
    pb = player_b or (card_b.controller if card_b else None)
    if va > vb:
        return pa or ""
    if vb > va:
        return pb or ""
    # Tied values -> fewer total scoring-pile cards wins.
    ca = _count_pile_cards(state, pa) if pa else 0
    cb = _count_pile_cards(state, pb) if pb else 0
    if ca < cb:
        return pa or ""
    if cb < ca:
        return pb or ""
    # Still tied (same pile counts) -> fall back to lead-player wins ties.
    if lead_player in (pa, pb):
        return lead_player or ""
    return pb or pa or ""


def scrappy_rule(
    card_a: GameObject,
    card_b: GameObject,
    state: GameState,
    *,
    player_a: Optional[str] = None,
    player_b: Optional[str] = None,
    lead_player: Optional[str] = None,
) -> str:
    """Scrappy: LOWEST Value wins (underdog cat). Ties go to the player
    with FEWER cards in piles (consistent with the underdog flavor).

    Critical worked example from §7: Mood (Value 0) vs Scrappy 3 under a
    "lowest wins" override -> Mood (0) wins.
    """
    va = _card_value(card_a)
    vb = _card_value(card_b)
    pa = player_a or (card_a.controller if card_a else None)
    pb = player_b or (card_b.controller if card_b else None)
    if va < vb:
        return pa or ""
    if vb < va:
        return pb or ""
    # Tied values -> fewer pile cards wins.
    ca = _count_pile_cards(state, pa) if pa else 0
    cb = _count_pile_cards(state, pb) if pb else 0
    if ca < cb:
        return pa or ""
    if cb < ca:
        return pb or ""
    if lead_player in (pa, pb):
        return lead_player or ""
    return pb or pa or ""


def sneaky_rule(
    card_a: GameObject,
    card_b: GameObject,
    state: GameState,
    *,
    player_a: Optional[str] = None,
    player_b: Optional[str] = None,
    lead_player: Optional[str] = None,
) -> str:
    """Sneaky: hidden ``sneaky_value`` is compared privately. Ties never
    happen for Sneaky in card design (values are fixed per printing and
    unique within a category), but if one slips through we resolve by
    public Value, then by lead player.
    """
    sa = _card_sneaky_value(card_a)
    sb = _card_sneaky_value(card_b)
    pa = player_a or (card_a.controller if card_a else None)
    pb = player_b or (card_b.controller if card_b else None)
    if sa > sb:
        return pa or ""
    if sb > sa:
        return pb or ""
    # Defensive fallback: public Value, then lead player.
    va = _card_value(card_a)
    vb = _card_value(card_b)
    if va > vb:
        return pa or ""
    if vb > va:
        return pb or ""
    if lead_player in (pa, pb):
        return lead_player or ""
    return pb or pa or ""


_DEFAULT_CATEGORY_RULES: dict[str, Callable] = {
    "Sleek": sleek_rule,
    "Fluffy": fluffy_rule,
    "Scrappy": scrappy_rule,
    "Sneaky": sneaky_rule,
}


def _resolve_category_rule(category: Optional[str]) -> Callable:
    """Return the rule_fn for a given category, falling back to sleek."""
    if not category:
        return sleek_rule
    # Prefer Agent 1's rules if exported.
    if isinstance(CATS_CATEGORY_RULES, dict) and category in CATS_CATEGORY_RULES:
        candidate = CATS_CATEGORY_RULES[category]
        if callable(candidate):
            return candidate
    return _DEFAULT_CATEGORY_RULES.get(category, sleek_rule)


# ---------------------------------------------------------------------------
# Module-level helpers required by the brief
# ---------------------------------------------------------------------------

def query_active_rule(state: GameState) -> Callable:
    """Run ``CATS_TRICK_RULE_QUERY`` through the event pipeline so Mood
    interceptors can install a replacement rule, and return the final
    callable the manager should use to compare the two trick cards.

    Resolution order:
      1. Mood interceptor REPLACE (via pipeline emit) — wins outright.
      2. Rule installed by the Pounce card's category (stored on the
         trick container as ``installed_rule``).
      3. Fallback to ``sleek_rule``.
    """
    if state is None:
        return sleek_rule

    trick = _get_trick(state)

    # Start from the installed rule if Agent 1's helpers have already set one.
    installed = _trick_installed_rule(trick)
    base_rule: Callable = installed if callable(installed) else sleek_rule

    # Ask the pipeline if any Mood wants to replace it.
    pipeline = getattr(state, "_pipeline", None) or getattr(state, "pipeline", None)
    game = getattr(state, "_game", None)
    if pipeline is None and game is not None:
        pipeline = getattr(game, "pipeline", None)

    try:
        query_event_type = EventType.CATS_TRICK_RULE_QUERY  # type: ignore[attr-defined]
    except AttributeError:
        # EventType.CATS_TRICK_RULE_QUERY not yet added by Agent 1.
        # TODO: reconciliation — once cats.md's required EventTypes land
        # in src/engine/types.py this branch can be dropped.
        return base_rule

    if pipeline is not None and hasattr(pipeline, "emit"):
        query_event = Event(
            type=query_event_type,
            payload={
                "current_rule": base_rule,
                "trick": trick,
            },
            source=None,
        )
        try:
            processed = pipeline.emit(query_event)
        except Exception:  # pragma: no cover - defensive against early-stage breakage
            processed = [query_event]
        # The Mood interceptor convention: write the replacement rule
        # back into ``payload['current_rule']`` (TRANSFORM/REPLACE).
        for ev in processed:
            if ev.type == query_event_type:
                replacement = ev.payload.get("current_rule") if isinstance(ev.payload, dict) else None
                if callable(replacement):
                    base_rule = replacement
                    break

    return base_rule if callable(base_rule) else sleek_rule


def determine_trick_winner(state: GameState, rule_fn: Callable) -> str:
    """Apply ``rule_fn`` to the two trick cards in
    ``state.cats.trick`` (or wherever Agent 1 stashed them). Return the
    winning player_id (empty string when the trick can't be resolved —
    callers must treat that as a no-op).
    """
    if state is None or not callable(rule_fn):
        return ""

    trick = _get_trick(state)
    if trick is None:
        return ""

    p_player, p_card_id = _trick_pounce_info(trick)
    c_player, c_card_id = _trick_counter_info(trick)

    # Fall back to a flat dict shape if pounce/counter weren't found.
    if not (p_card_id and c_card_id):
        cards = _trick_cards(trick)
        ids = [(pid, cid) for pid, cid in cards.items() if cid]
        if len(ids) < 2:
            return ""
        (p_player, p_card_id), (c_player, c_card_id) = ids[0], ids[1]

    card_a = state.objects.get(p_card_id) if state.objects else None
    card_b = state.objects.get(c_card_id) if state.objects else None
    if card_a is None or card_b is None:
        return ""

    # Lead player == Counter-pounce player per docs/games/cats.md §3.
    lead = c_player or getattr(state, "cats_lead_player", None)

    try:
        return rule_fn(
            card_a,
            card_b,
            state,
            player_a=p_player,
            player_b=c_player,
            lead_player=lead,
        ) or ""
    except TypeError:
        # Rule function may not accept keyword args (older shape). Fall
        # back to positional 3-arg form and let it determine players from
        # the GameObject .controller.
        return rule_fn(card_a, card_b, state) or ""


def is_snack_in_trick(state: GameState) -> bool:
    """True if either card in the current trick has CardType.CATS_SNACK."""
    if state is None:
        return False
    trick = _get_trick(state)
    if trick is None:
        return False
    cards = _trick_cards(trick)
    for cid in cards.values():
        if not cid:
            continue
        obj = state.objects.get(cid) if state.objects else None
        if _is_cats_snack(obj):
            return True
    return False


# ---------------------------------------------------------------------------
# CatsTrickManager
# ---------------------------------------------------------------------------

@dataclass
class _TrickManagerLocalState:
    """Local cache. The authoritative trick state lives on ``GameState.cats``
    (Agent 1's container). These fields are mirrors used when the manager
    is asked questions outside an active pipeline.
    """
    winner_id: Optional[str] = None
    loser_id: Optional[str] = None
    resolved: bool = False


class CatsTrickManager:
    """Resolves tricks in the Cats engine.

    Despite the ``_combat`` filename, this is trick-resolution, not
    combat. Provides the orchestrator that the turn manager calls into to:

      * Receive a Pounce card (and install the category rule)
      * Receive a Counter-pounce card
      * Resolve the trick via the installed rule (and any Mood overrides)
      * Hand off to claim-pile selection
    """

    def __init__(self, state: GameState):
        self.state = state
        self._local = _TrickManagerLocalState()
        # Other systems are bound by the Game class once construction is
        # complete (see how MTG CombatManager is wired). Cats may not
        # need most of these but we keep the slot for interface parity.
        self.turn_manager: Optional[Any] = None
        self.pipeline: Optional[Any] = None

    # ------------------------------------------------------------------
    # Pipeline access (matches the convention in other *_combat modules)
    # ------------------------------------------------------------------

    def _get_pipeline(self) -> Optional[Any]:
        if self.pipeline is not None:
            return self.pipeline
        if self.state is None:
            return None
        pipe = getattr(self.state, "_pipeline", None) or getattr(self.state, "pipeline", None)
        if pipe is not None:
            return pipe
        game = getattr(self.state, "_game", None)
        if game is not None:
            return getattr(game, "pipeline", None)
        return None

    def _emit(self, event: Event) -> list[Event]:
        """Emit through pipeline if present, otherwise return the lone event."""
        pipe = self._get_pipeline()
        if pipe is not None and hasattr(pipe, "emit"):
            try:
                return list(pipe.emit(event))
            except Exception:  # pragma: no cover - defensive
                return [event]
        return [event]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def receive_pounce(self, player_id: str, card_obj_id: str) -> list[Event]:
        """First card committed to the trick. Installs the category rule
        (if the card has a Category) and emits ``CATS_CARD_PLAYED``.

        Returns the list of events emitted (which may include on-play
        triggers fired downstream of the pipeline).
        """
        events: list[Event] = []
        if self.state is None or not player_id or not card_obj_id:
            return events

        # Defer the call into Agent 1's helper if available; otherwise
        # mutate the trick container locally.
        try:
            from src.engine import cats as _cats_mod  # noqa: F401
        except Exception:
            _cats_mod = None  # type: ignore

        if _cats_mod is not None and getattr(_cats_mod, "play_card_to_trick", None):
            try:
                helper_events = _cats_mod.play_card_to_trick(  # type: ignore[attr-defined]
                    self.state, player_id, card_obj_id, role="pounce"
                )
                if helper_events:
                    events.extend(helper_events)
                # Reset local cache — a new trick is being assembled.
                self._local = _TrickManagerLocalState()
                return events
            except TypeError:
                # Helper may have a different signature; try simpler call.
                try:
                    helper_events = _cats_mod.play_card_to_trick(  # type: ignore[attr-defined]
                        self.state, player_id, card_obj_id
                    )
                    if helper_events:
                        events.extend(helper_events)
                    self._local = _TrickManagerLocalState()
                    return events
                except Exception:
                    pass  # Fall through to local fallback.
            except Exception:
                pass

        # Local fallback: write the pounce card to the trick container and
        # install the category rule.
        trick = _get_trick(self.state)
        if trick is None:
            # If Agent 1 hasn't created a trick container yet, do a
            # minimal in-place init so smoke tests work.
            trick = {"pounce_player": None, "pounce_card": None,
                     "counter_player": None, "counter_card": None,
                     "installed_rule": None}
            setattr(self.state, "cats_current_trick", trick)
        _set_trick_pounce(trick, player_id, card_obj_id)

        card_obj = self.state.objects.get(card_obj_id) if self.state.objects else None
        category = _card_category(card_obj)
        if category:
            rule = _resolve_category_rule(category)
            _set_trick_installed_rule(trick, rule)
            # Notify Agent 1's installer too (for state mirrors).
            if _cats_mod is not None and getattr(_cats_mod, "install_category_rule", None):
                try:
                    _cats_mod.install_category_rule(self.state, category)  # type: ignore[attr-defined]
                except Exception:
                    pass

        # Emit CATS_CARD_PLAYED so on-play interceptors can react.
        try:
            ct = EventType.CATS_CARD_PLAYED  # type: ignore[attr-defined]
        except AttributeError:
            # TODO: reconciliation — needs CATS_CARD_PLAYED added in types.py.
            ct = None

        if ct is not None:
            played = Event(
                type=ct,
                payload={
                    "player_id": player_id,
                    "card_id": card_obj_id,
                    "role": "pounce",
                    "category": category,
                },
                source=card_obj_id,
                controller=player_id,
            )
            events.extend(self._emit(played))

        self._local = _TrickManagerLocalState()
        return events

    def receive_counter_pounce(self, player_id: str, card_obj_id: str) -> list[Event]:
        """Second card committed to the trick. Emits ``CATS_CARD_PLAYED``.

        A Counter-pounce Mood will install/replace the rule before the
        comparison runs (handled by ``query_active_rule`` at resolve
        time, not here — we just record the card and let the Mood's own
        interceptor fire on the played event).

        Returns events emitted.
        """
        events: list[Event] = []
        if self.state is None or not player_id or not card_obj_id:
            return events

        try:
            from src.engine import cats as _cats_mod  # noqa: F401
        except Exception:
            _cats_mod = None  # type: ignore

        if _cats_mod is not None and getattr(_cats_mod, "play_card_to_trick", None):
            try:
                helper_events = _cats_mod.play_card_to_trick(  # type: ignore[attr-defined]
                    self.state, player_id, card_obj_id, role="counter"
                )
                if helper_events:
                    events.extend(helper_events)
                return events
            except TypeError:
                try:
                    helper_events = _cats_mod.play_card_to_trick(  # type: ignore[attr-defined]
                        self.state, player_id, card_obj_id
                    )
                    if helper_events:
                        events.extend(helper_events)
                    return events
                except Exception:
                    pass
            except Exception:
                pass

        trick = _get_trick(self.state)
        if trick is None:
            trick = {"pounce_player": None, "pounce_card": None,
                     "counter_player": None, "counter_card": None,
                     "installed_rule": None}
            setattr(self.state, "cats_current_trick", trick)
        _set_trick_counter(trick, player_id, card_obj_id)

        card_obj = self.state.objects.get(card_obj_id) if self.state.objects else None
        category = _card_category(card_obj)

        try:
            ct = EventType.CATS_CARD_PLAYED  # type: ignore[attr-defined]
        except AttributeError:
            ct = None

        if ct is not None:
            played = Event(
                type=ct,
                payload={
                    "player_id": player_id,
                    "card_id": card_obj_id,
                    "role": "counter",
                    "category": category,
                },
                source=card_obj_id,
                controller=player_id,
            )
            events.extend(self._emit(played))

        return events

    def resolve(self) -> tuple[str, list[Event]]:
        """Compare the two cards under the active rule.

        Consults ``CATS_TRICK_RULE_QUERY`` interceptors first (Moods can
        replace the rule). Falls back to the rule installed by the Pounce
        card's category, then to :func:`sleek_rule`.

        Returns ``(winner_player_id, events)`` where events include the
        master ``CATS_TRICK_RESOLVE`` event and per-card events that allow
        ``on_win`` / ``on_lose`` interceptors to filter.
        """
        emitted: list[Event] = []
        if self.state is None:
            return ("", emitted)

        # Prefer Agent 1's resolve_trick if available — it knows the full
        # state-container shape best.
        try:
            from src.engine import cats as _cats_mod  # noqa: F401
        except Exception:
            _cats_mod = None  # type: ignore

        if _cats_mod is not None and getattr(_cats_mod, "resolve_trick", None):
            try:
                winner_id, agent1_events = _cats_mod.resolve_trick(self.state)  # type: ignore[attr-defined]
                self._local.winner_id = winner_id or None
                # Find loser from the trick.
                trick = _get_trick(self.state)
                cards = _trick_cards(trick) if trick is not None else {}
                self._local.loser_id = next(
                    (pid for pid in cards.keys() if pid != winner_id), None
                )
                self._local.resolved = bool(winner_id)
                if agent1_events:
                    emitted.extend(agent1_events)
                return (winner_id or "", emitted)
            except Exception:
                # Fall through to local resolve.
                pass

        # Local resolution path.
        rule_fn = query_active_rule(self.state)
        winner_id = determine_trick_winner(self.state, rule_fn)

        trick = _get_trick(self.state)
        cards = _trick_cards(trick) if trick is not None else {}

        # Identify loser as the other player in the trick.
        loser_id = ""
        for pid in cards.keys():
            if pid and pid != winner_id:
                loser_id = pid
                break

        # Identify winning and losing card ids.
        winning_card_ids: list[str] = []
        losing_card_ids: list[str] = []
        for pid, cid in cards.items():
            if not cid:
                continue
            if pid == winner_id:
                winning_card_ids.append(cid)
            else:
                losing_card_ids.append(cid)

        # Cache for get_winner().
        self._local.winner_id = winner_id or None
        self._local.loser_id = loser_id or None
        self._local.resolved = bool(winner_id)

        # Emit the master resolve event.
        try:
            resolve_type = EventType.CATS_TRICK_RESOLVE  # type: ignore[attr-defined]
        except AttributeError:
            # TODO: reconciliation — needs CATS_TRICK_RESOLVE in types.py.
            resolve_type = None

        if resolve_type is not None and winner_id:
            master = Event(
                type=resolve_type,
                payload={
                    "winner_id": winner_id,
                    "loser_id": loser_id,
                    "winning_cards": list(winning_card_ids),
                    "losing_cards": list(losing_card_ids),
                    "rule": rule_fn,
                },
                source=None,
                controller=winner_id,
            )
            emitted.extend(self._emit(master))

            # Per-card phase-tagged events so on_win / on_lose trigger
            # interceptors can filter cleanly (mirrors how
            # minecraft_combat emits per-creature damage events).
            for cid in winning_card_ids:
                ev = Event(
                    type=resolve_type,
                    payload={
                        "phase": "on_win",
                        "card_id": cid,
                        "winner_id": winner_id,
                        "loser_id": loser_id,
                    },
                    source=cid,
                    controller=winner_id,
                )
                emitted.extend(self._emit(ev))
            for cid in losing_card_ids:
                ev = Event(
                    type=resolve_type,
                    payload={
                        "phase": "on_lose",
                        "card_id": cid,
                        "winner_id": winner_id,
                        "loser_id": loser_id,
                    },
                    source=cid,
                    controller=loser_id or None,
                )
                emitted.extend(self._emit(ev))

        return (winner_id or "", emitted)

    def is_trick_complete(self) -> bool:
        """True if both cards have been played to the current trick."""
        if self.state is None:
            return False
        trick = _get_trick(self.state)
        if trick is None:
            return False
        _, p_card = _trick_pounce_info(trick)
        _, c_card = _trick_counter_info(trick)
        if p_card and c_card:
            return True
        # Fall back to counting non-None cards in a flat map.
        cards = _trick_cards(trick)
        non_null = [cid for cid in cards.values() if cid]
        return len(non_null) >= 2

    def get_winner(self) -> Optional[str]:
        """After ``resolve()``, returns the winning player_id.

        Returns None if the trick has not been resolved yet.
        """
        if self._local.resolved:
            return self._local.winner_id
        return None

    def reset(self) -> None:
        """Reset trick state after claim-pile is done.

        Called by the turn manager at end-of-round (Curl up phase).
        Clears both the local cache and the authoritative trick container
        on the GameState.
        """
        self._local = _TrickManagerLocalState()
        if self.state is None:
            return

        # Try Agent 1's container first.
        cs = _get_cats_state(self.state)
        if cs is not None:
            # If the container exposes a reset hook, use it.
            reset_fn = getattr(cs, "reset_trick", None)
            if callable(reset_fn):
                try:
                    reset_fn()
                    return
                except Exception:
                    pass
            # Otherwise null the trick attribute / dict entries.
            if hasattr(cs, "trick"):
                try:
                    if isinstance(cs.trick, dict):
                        cs.trick.clear()
                        # Restore canonical keys to None so later access works.
                        cs.trick.update({
                            "pounce_player": None,
                            "pounce_card": None,
                            "counter_player": None,
                            "counter_card": None,
                            "installed_rule": None,
                        })
                    else:
                        # Dataclass shape — clear well-known fields.
                        for attr in (
                            "pounce_player",
                            "pounce_card",
                            "counter_player",
                            "counter_card",
                            "installed_rule",
                        ):
                            if hasattr(cs.trick, attr):
                                try:
                                    setattr(cs.trick, attr, None)
                                except AttributeError:
                                    pass
                except AttributeError:
                    pass

        # Also clear the flat-shape attribute if present.
        flat = getattr(self.state, "cats_current_trick", None)
        if isinstance(flat, dict):
            flat.clear()
            flat.update({
                "pounce_player": None,
                "pounce_card": None,
                "counter_player": None,
                "counter_card": None,
                "installed_rule": None,
            })
        elif flat is not None:
            for attr in (
                "pounce_player",
                "pounce_card",
                "counter_player",
                "counter_card",
                "installed_rule",
            ):
                if hasattr(flat, attr):
                    try:
                        setattr(flat, attr, None)
                    except AttributeError:
                        pass
