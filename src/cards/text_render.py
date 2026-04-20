"""
Text Rendering Kit for Card Rules Text

Pure-function text rendering kit. Each function returns a rules-text fragment
that uses ``{this}`` as a placeholder for the card's own name. Use
``substitute_card_name`` to fill the placeholder at card-registration time.

The output matches the existing ``src.engine.abilities.*.render_text`` style
so that migrated cards produce near-identical text strings to the prior
class-based DSL.

Example:
    >>> render_etb_gain_life(3)
    'When {this} enters the battlefield, you gain 3 life.'
    >>> substitute_card_name(render_etb_gain_life(3), "Totoro")
    'When Totoro enters the battlefield, you gain 3 life.'
"""

from typing import Iterable, List, Sequence


# =============================================================================
# INTERNAL UTILITIES
# =============================================================================

_NUMBER_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five"}


def _amount_word(amount: int, *, zero_is_a: bool = False) -> str:
    """Render a small integer as an English number word ('a', 'two', ...).

    Falls back to the decimal representation for values outside the known set.
    """
    if amount in _NUMBER_WORDS:
        return _NUMBER_WORDS[amount]
    if zero_is_a and amount == 0:
        return "a"
    return str(amount)


def _card_word(amount: int) -> str:
    return "card" if amount == 1 else "cards"


def _counter_word(amount: int) -> str:
    return "counter" if amount == 1 else "counters"


def _signed(value: int) -> str:
    """Return +N / -N string; matches PTBoost.render_text behavior."""
    return f"+{value}" if value >= 0 else str(value)


# =============================================================================
# SUBSTITUTION
# =============================================================================

def substitute_card_name(template: str, card_name: str) -> str:
    """Replace the ``{this}`` placeholder in a template with the card's name.

    Idempotent: templates without a placeholder are returned unchanged.
    """
    return template.replace("{this}", card_name)


# =============================================================================
# KEYWORDS
# =============================================================================

def render_keyword(keyword_name: str) -> str:
    """Render a single keyword, capitalized ('Flying', 'Trample', 'Haste')."""
    return keyword_name.capitalize()


def render_keyword_list(keywords: Sequence[str]) -> str:
    """Join a list of keywords as a comma-separated title-cased fragment.

    Examples:
        ['flying']                       -> 'Flying'
        ['flying', 'trample']            -> 'Flying, Trample'
        ['flying', 'trample', 'haste']   -> 'Flying, Trample, Haste'
    """
    return ", ".join(render_keyword(k) for k in keywords)


# =============================================================================
# ETB (ENTER-THE-BATTLEFIELD) TEMPLATES
# =============================================================================

def render_etb_gain_life(amount: int) -> str:
    """'When {this} enters the battlefield, you gain N life.'"""
    return f"When {{this}} enters the battlefield, you gain {amount} life."


def render_etb_lose_life(amount: int) -> str:
    """'When {this} enters the battlefield, each opponent loses N life.'"""
    return f"When {{this}} enters the battlefield, each opponent loses {amount} life."


def render_etb_draw(amount: int) -> str:
    """'When {this} enters the battlefield, draw a/N card(s).'"""
    word = _amount_word(amount)
    return f"When {{this}} enters the battlefield, draw {word} {_card_word(amount)}."


def render_etb_deal_damage(amount: int, target_desc: str) -> str:
    """'When {this} enters the battlefield, {this} deals N damage to <target_desc>.'"""
    return (
        f"When {{this}} enters the battlefield, "
        f"{{this}} deals {amount} damage to {target_desc}."
    )


def render_etb_create_token(
    power: int,
    toughness: int,
    subtype: str,
    count: int = 1,
) -> str:
    """'When {this} enters the battlefield, create a/N P/T <subtype> creature token(s).'"""
    if count == 1:
        count_word = "a"
        token_word = "token"
    else:
        count_word = _amount_word(count)
        token_word = "tokens"
    return (
        f"When {{this}} enters the battlefield, "
        f"create {count_word} {power}/{toughness} {subtype} creature {token_word}."
    )


# =============================================================================
# DEATH TEMPLATES
# =============================================================================

def render_death_drain(amount: int) -> str:
    """'When {this} dies, each opponent loses N life and you gain N life.'"""
    return (
        f"When {{this}} dies, "
        f"each opponent loses {amount} life and you gain {amount} life."
    )


def render_death_draw(amount: int) -> str:
    """'When {this} dies, draw a/N card(s).'"""
    word = _amount_word(amount)
    return f"When {{this}} dies, draw {word} {_card_word(amount)}."


# =============================================================================
# ATTACK TEMPLATES
# =============================================================================

def render_attack_deal_damage(amount: int, target_desc: str) -> str:
    """'Whenever {this} attacks, {this} deals N damage to <target_desc>.'"""
    return (
        f"Whenever {{this}} attacks, "
        f"{{this}} deals {amount} damage to {target_desc}."
    )


def render_attack_add_counters(counter_type: str, count: int) -> str:
    """'Whenever {this} attacks, put a/N <counter_type> counter(s) on {this}.'"""
    word = _amount_word(count)
    return (
        f"Whenever {{this}} attacks, "
        f"put {word} {counter_type} {_counter_word(count)} on {{this}}."
    )


# =============================================================================
# STATIC TEMPLATES (LORDS / AURAS)
# =============================================================================

def render_static_pt_boost(power: int, toughness: int, scope: str) -> str:
    """'<Scope> get +X/+Y.' — matches StaticAbility.render_text composition."""
    return f"{scope.capitalize()} get {_signed(power)}/{_signed(toughness)}."


def render_static_keyword_grant(keywords: Sequence[str], scope: str) -> str:
    """'<Scope> have flying.' / '<Scope> have flying and vigilance.' etc.

    Matches the lowercase keyword style used by ``KeywordGrant.render_text``.
    """
    kws = list(keywords)
    if len(kws) == 1:
        body = kws[0]
    elif len(kws) == 2:
        body = f"{kws[0]} and {kws[1]}"
    else:
        body = ", ".join(kws[:-1]) + f", and {kws[-1]}"
    return f"{scope.capitalize()} have {body}."


# =============================================================================
# UPKEEP / SPELL-CAST TEMPLATES
# =============================================================================

def render_upkeep_gain_life(amount: int) -> str:
    """'At the beginning of your upkeep, you gain N life.'"""
    return f"At the beginning of your upkeep, you gain {amount} life."


def render_spell_cast_draw(amount: int) -> str:
    """'Whenever you cast a spell, draw a/N card(s).'"""
    word = _amount_word(amount)
    return f"Whenever you cast a spell, draw {word} {_card_word(amount)}."


# =============================================================================
# COMPOSITION
# =============================================================================

def render_composite(fragments: Sequence[str]) -> str:
    """Join multiple standalone rules-text fragments into one line.

    Preserves each fragment verbatim (including trailing periods). Intended for
    stacking independent abilities on a single card (e.g. ETB plus attack
    trigger). For combining effect clauses *within* one triggered ability (the
    CompositeEffect "you gain 1 life and draw a card" case), use
    ``render_effect_conjunction`` instead.
    """
    return " ".join(f.strip() for f in fragments if f and f.strip())


def render_effect_conjunction(clauses: Sequence[str]) -> str:
    """Oxford-comma join for clauses inside a single triggered ability.

    Mirrors ``CompositeEffect.render_text``:
        1 -> "draw a card"
        2 -> "gain 1 life and draw a card"
        3 -> "gain 1 life, draw a card, and scry 1"
    """
    items = [c for c in clauses if c]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
