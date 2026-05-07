"""
Per-set art-style configuration for SUBS (depths set 1, submarine fleet).

Consumed by `scripts/new_set/art_harness.py` — defines the visual style
preamble + per-category flavor + a custom categorize() that handles
depths-specific CardType enums (DEPTHS_VESSEL, DEPTHS_CREW, DEPTHS_WEAPON,
DEPTHS_MINE).
"""

from __future__ import annotations

from typing import Any


STYLE_HEADLINE = (
    "Render in the visual language of declassified WWII Kriegsmarine "
    "reconnaissance plates crossed with high-budget deep-sea documentary "
    "cinematography. Compositions are dim, technical, and oppressively "
    "wet — every frame should feel like it was lit by a single failing "
    "sodium lamp inside a steel pressure hull or by the cold blue-green "
    "spill of an active sonar dome. Color palette: deep ultramarine and "
    "abyssal black for water and negative space, oxidised brass and rust-"
    "orange for vessel hulls and fittings, sodium-yellow for interior "
    "glow, sonar cyan/teal for sweep lines and detection arcs, salt-"
    "stained off-white for foam and stencil text. Shape language is "
    "functional: rivet seams, anechoic-tile texture, conning-tower "
    "silhouettes, periscope masts, propeller wash. Reject anime, cartoon, "
    "super-deformed, or pastel registers. Reject clean digital concept-"
    "art glow. Strongly prefer painterly oil-on-canvas or photographic "
    "grain over crisp digital surfaces. Always include a strong sense "
    "of vertical pressure: water column above, abyss below, claustrophobic "
    "space inside. NO text, NO logos, NO card frame, NO borders, NO "
    "stat numbers — illustration only."
)


CATEGORY_FLAVORS: dict[str, str] = {
    "vessel": (
        "A submarine in three-quarter underwater profile, sonar light "
        "raking across the conning tower, depth-line markers etched on "
        "the hull. Bubbles trail from prop wash; cold light cuts through "
        "plankton suspension."
    ),
    "flagship": (
        "A cathedral-scale capital vessel at periscope depth seen from "
        "below, silhouetted against thin surface light. Monolithic, slow, "
        "and unkillable until proven otherwise — flag pennants, rivet "
        "courses, bow waves."
    ),
    "stealth_vessel": (
        "Same framing as `vessel` but with the conning tower vanishing "
        "into the gloom; only running lights or a wake hint show position. "
        "Heavy negative space, single cold rim-light."
    ),
    "boss_vessel": (
        "Flagship-grade composition for a Legendary or marquee Vessel — "
        "frame the hull at scale against tiny escort silhouettes or "
        "against a kraken-shaped abyssal shadow."
    ),
    "crew": (
        "A single weathered sailor framed tightly inside a brass-fitted "
        "control room, lit by the green sodium of a sonar scope or by "
        "emergency red. Hands on a wheel, headphones, sweat. Humanity "
        "inside the steel."
    ),
    "weapon": (
        "Clean-cut technical diagram register: torpedoes mid-loading, "
        "tubes seen from inside the bow with stencil markings, depth-"
        "charge racks. Pair the tool with a small vignette of its launch, "
        "like a contemporary munitions catalog plate."
    ),
    "mine": (
        "A lone sphere-mine moored mid-water, contact horns silhouetted "
        "against blue gloom, kelp tendrils rising from below. Patient and "
        "lethal — the trap-set-and-waiting mood."
    ),
    "action": (
        "A single decisive moment — torpedo wake closing on a hull, sonar "
        "pulse blooming outward, escape hatch slamming shut. Cinematic, "
        "painterly, no UI overlay."
    ),
    "doctrine": (
        "A heraldic / propaganda-poster register: bold horizon lines, "
        "stenciled type implied (do not render legible text), naval "
        "ensign silhouettes, command-room maps with grease pencil. The "
        "faction's strategic philosophy, not a single moment."
    ),
    "object": (
        "A submarine-warfare artifact in the same lighting style — "
        "weathered, technical, painterly."
    ),
}


def categorize(card: Any) -> str:
    """Map a CardDefinition to a CATEGORY_FLAVORS key.

    Reads card.characteristics.types + subtypes + flags so depths-specific
    CardType enums route to the right flavor block.
    """
    try:
        from src.engine.types import CardType
    except Exception:
        return "object"

    chars = getattr(card, "characteristics", None)
    if not chars:
        return "object"

    types = getattr(chars, "types", set()) or set()
    subtypes = getattr(chars, "subtypes", set()) or set()
    keywords = getattr(chars, "keywords", set()) or set()
    if not isinstance(keywords, (set, frozenset, list)):
        keywords = set()
    keywords = set(keywords)

    is_legendary = "Legendary" in subtypes or "Legend" in subtypes

    if CardType.DEPTHS_VESSEL in types:
        if "Flagship" in subtypes:
            return "flagship"
        if is_legendary:
            return "boss_vessel"
        if "silent_running" in keywords or getattr(card, "depths_silent_running", False):
            return "stealth_vessel"
        return "vessel"
    if CardType.DEPTHS_CREW in types:
        return "crew"
    if CardType.DEPTHS_WEAPON in types:
        return "weapon"
    if CardType.DEPTHS_MINE in types:
        return "mine"
    if CardType.ENCHANTMENT in types:
        return "doctrine"
    if CardType.INSTANT in types or CardType.SORCERY in types:
        return "action"
    return "object"
