"""Mnestic Reset (MNR) card-side helper factories.

Five verbs interlock here. Each helper either tags a CardDefinition with a
metadata attribute the engine reads (``scp_antimeme``, ``scp_mnestic``,
``scp_cog_hazard``) OR returns an effect callable for the engine's
``scp_effect`` slot.

Card-design agents: ALWAYS run cards through ``_with_mnr_metadata`` before
appending to a sub-module list — the expansion code is what wires cards into
the MNR set filter (``scp_expansion_code == "MNR"``).
"""

from __future__ import annotations

from typing import Callable, Optional

from src.engine import scp
from src.engine.types import (
    CardDefinition,
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
)


EXPANSION = "Mnestic Reset"
EXPANSION_CODE = "MNR"


# ---------------------------------------------------------------------------
# Metadata + base wrappers
# ---------------------------------------------------------------------------


def _with_mnr_metadata(
    card: CardDefinition,
    *,
    archetype: str = "mnestic_reset",
    keywords: Optional[set[str]] = None,
    art_prompt: Optional[str] = None,
) -> CardDefinition:
    """Stamp the standard MNR metadata fields onto ``card``.

    ``archetype`` lets card agents split the set into sub-themes (e.g.
    "antimeme_decay", "redaction_press", "mnestic_wake"); the default
    "mnestic_reset" is fine if no narrower bucket fits.
    """
    card.scp_expansion = EXPANSION
    card.scp_expansion_code = EXPANSION_CODE
    card.scp_archetype = archetype
    card.scp_keywords = sorted(set(keywords or set()))
    card.scp_art_prompt = art_prompt or (
        f"Original SCP-inspired trading card art for {card.name} from {EXPANSION}: "
        f"clinical antimemetic facility under fluorescent light, redacted dossier "
        f"papers, clear focal subject, no text or logos, high-detail digital painting."
    )
    return card


# ---------------------------------------------------------------------------
# Verb 1: Antimeme N
# ---------------------------------------------------------------------------


def _antimeme(card: CardDefinition, n: int) -> CardDefinition:
    """Tag an anomaly with ``scp_antimeme = N``.

    The engine's ``tick_antimeme_counters`` reads this at end-of-turn. N must
    be >=1; lower values mean the anomaly forgets faster. Designers: pair
    Antimeme 1 with a strong on-reveal payoff (you only get one swing
    before it forgets), and Antimeme 3-4 with passive value (it lingers
    long enough to chew on the opponent).
    """
    if n < 1:
        raise ValueError(f"_antimeme: N must be >=1, got {n!r}")
    card.scp_antimeme = int(n)
    return card


# ---------------------------------------------------------------------------
# Verb 2: Mnestic personnel
# ---------------------------------------------------------------------------


def _mnestic_personnel(
    name: str,
    *,
    skills: dict[str, int],
    red_tape: int,
    subtypes: set[str],
    text: str,
    clearance: int = 0,
    rarity: Optional[str] = None,
    aura: Optional[dict] = None,
    archetype: str = "mnestic_reset",
    art_prompt: Optional[str] = None,
) -> CardDefinition:
    """Create a personnel with ``scp_mnestic = True``.

    Pairs with the engine's ``has_mnestic`` query (which short-circuits
    antimeme decay and cognitive hazard for the controller). The Mnestic
    subtype is added to ``subtypes`` automatically so AI / filters /
    aura selectors can target the keyword.
    """
    full_subtypes = set(subtypes) | {"Mnestic"}
    card = scp.make_scp_card(
        name,
        CardType.SCP_PERSONNEL,
        skills=skills,
        red_tape=red_tape,
        clearance=clearance,
        subtypes=full_subtypes,
        text=text,
        rarity=rarity,
        aura=aura,
    )
    card.scp_mnestic = True
    return _with_mnr_metadata(card, archetype=archetype, keywords={"Mnestic"}, art_prompt=art_prompt)


# ---------------------------------------------------------------------------
# Verb 3: Redact N (effect factory)
# ---------------------------------------------------------------------------


def _redact(n: int) -> Callable[[GameObject, GameState], list[Event]]:
    """Return an ``scp_effect`` callable that resolves Redact N.

    Use as the ``effect=`` argument when building a procedure with
    ``make_scp_card`` (or the local ``_mnr_procedure`` wrapper). The
    engine's ``_activate_dossier`` will call it with ``(obj, state)`` or
    ``(obj, state, game)`` — both signatures are accepted by the
    activation glue, so this returns the 2-arg form and grabs ``game``
    off ``state._game`` to call into ``scp.redact_opposing``.
    """
    if n < 1:
        raise ValueError(f"_redact: N must be >=1, got {n!r}")

    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        # Prefer the explicit game arg (3-arg call path) but fall back to
        # state._game for legacy 2-arg invocations.
        actual_game = game if game is not None else getattr(state, "_game", None)
        if actual_game is None:
            return []
        return scp.redact_opposing(actual_game, obj.controller, int(n), source=obj.id)

    return effect


# ---------------------------------------------------------------------------
# Verb 4: Cognitive Hazard X
# ---------------------------------------------------------------------------


def _cog_hazard(card: CardDefinition, x: int) -> CardDefinition:
    """Tag an anomaly with ``scp_cog_hazard = X``.

    The engine's ``apply_cognitive_hazard_start`` reads this at the start
    of each OPPOSING player's turn. The opposing player discards X cards
    from hand unless they control a Mnestic personnel.
    """
    if x < 1:
        raise ValueError(f"_cog_hazard: X must be >=1, got {x!r}")
    card.scp_cog_hazard = int(x)
    return card


# ---------------------------------------------------------------------------
# Verb 5: Mnestic Wake (activated ability registration)
# ---------------------------------------------------------------------------


def _mnestic_wake_ability(
    obj: GameObject,
    state: GameState,
    *,
    ethics_cost: int = 1,
    description: Optional[str] = None,
):
    """Register the Mnestic Wake activated ability on a personnel.

    Pattern: pay ``ethics_cost`` (reduce ethics_debt) + exhaust self; the
    personnel permanently gains the Mnestic tag (``state.scp_mnestic_gained``).
    Once-per-game ("Exhaust"), so each personnel can only Wake once. Built on the
    SCP-native ``make_scp_activated_ability`` (the cost is a real ``SCPCost``).

    Returns the registered ``SCPActivatedAbility`` descriptor.
    """
    from src.engine.scp_abilities import make_scp_activated_ability
    from src.engine.scp_costs import SCPCost, SCPValueHint

    def precondition(o: GameObject, st: GameState) -> bool:
        if o.zone.name != "BATTLEFIELD" or o.state.scp_status != "active":
            return False
        # Already Mnestic (printed or previously woken) → nothing to gain.
        if bool(getattr(o.card_def, "scp_mnestic", False)):
            return False
        if bool(getattr(o.state, "scp_mnestic_gained", False)):
            return False
        return True

    def effect_fn(o: GameObject, st: GameState) -> list[Event]:
        game = getattr(st, "_game", None)
        if game is None:
            # Bare-test fallback (no game attached): synthesize the result.
            o.state.scp_mnestic_gained = True
            return [Event(
                type=EventType.SCP_MNESTIC_ACTIVE,
                payload={"player": o.controller, "object_id": o.id, "already_mnestic": False},
                source=o.id,
                controller=o.controller,
            )]
        return scp.gain_mnestic(game, o.id, source=o.id)

    desc = description or f"Mnestic Wake: pay {ethics_cost} ethics, exhaust. Gain Mnestic."
    # Migrated off the MTG make_activated_ability: that descriptor registered onto
    # activated_abilities but SCP only dispatches is_scp_ability ones, so Mnestic
    # Wake never actually fired (dead code, like the pilot's O5-3). The cost
    # (reduce ethics_debt + exhaust) is now a real SCPCost; the value_hint makes
    # the heuristic AI Wake toward the Mnestic Saturation alt-win.
    return make_scp_activated_ability(
        obj,
        cost=SCPCost(ethics=ethics_cost, exhaust_self=True),
        once_per_game=True,
        description=desc,
        effect_fn=effect_fn,
        precondition_fn=precondition,
        value_hint=SCPValueHint(gains_mnestic=True),
    )


# ---------------------------------------------------------------------------
# Convenience: a make_scp_card thin wrapper that auto-stamps MNR metadata
# so card agents don't have to remember to call _with_mnr_metadata.
# ---------------------------------------------------------------------------


def _mnr_card(
    name: str,
    card_type: CardType,
    *,
    archetype: str = "mnestic_reset",
    keywords: Optional[set[str]] = None,
    art_prompt: Optional[str] = None,
    **make_kwargs,
) -> CardDefinition:
    """Thin wrapper around ``scp.make_scp_card`` that stamps MNR metadata.

    Use this as the default constructor for MNR cards in
    ``anomalies.py`` / ``personnel.py`` / etc. Pass any of ``make_scp_card``'s
    keyword args through ``**make_kwargs``.
    """
    card = scp.make_scp_card(name, card_type, **make_kwargs)
    return _with_mnr_metadata(card, archetype=archetype, keywords=keywords, art_prompt=art_prompt)


__all__ = [
    "EXPANSION",
    "EXPANSION_CODE",
    "_with_mnr_metadata",
    "_antimeme",
    "_mnestic_personnel",
    "_redact",
    "_cog_hazard",
    "_mnestic_wake_ability",
    "_mnr_card",
]
