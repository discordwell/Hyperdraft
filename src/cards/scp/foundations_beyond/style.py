"""Art direction for Foundations Beyond (FBN).

Consumed by ``scripts/new_set/art_harness.py``. Each prompt is built as::

    STYLE_HEADLINE + "\\n\\n" + CATEGORY_FLAVORS[category] + "\\n\\n" + card_prompt

where ``category`` is the return value of :func:`categorize`.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType


STYLE_HEADLINE = (
    "Original illustration in the visual language of SCP Foundation "
    "documentation fused with MTG cosmic horror. Sterile-lit concrete "
    "containment architecture, redacted/stamped Foundation paperwork "
    "aesthetics, biohazard signage, and dim sodium-arc institutional "
    "lighting form the substrate. Layered on top: Phyrexian oil-sheen "
    "surfaces, Eldrazi non-Euclidean void-geometry, dragon-scale and "
    "apex-fauna textures, planar-rift chromatic aberration, ambient "
    "leyline glow. Bureaucratic-dread tone, never camp. Photographic-"
    "realism reference for the institutional half; painted cosmic-horror "
    "reference for the entity half. Single focal subject centered in a "
    "square frame. Background suggests classified document overlay or "
    "containment architecture. NO text, NO logos, NO captions, NO "
    "watermarks, NO card frames, NO borders in the image."
)


STYLE_NEGATIVE = (
    "No camp horror, no cartoon mascots, no bright saturated palette, "
    "no clean sci-fi spacecraft, no fantasy-mural medieval scenes, no "
    "kawaii or chibi treatments. Avoid Disney-villain expressions. The "
    "tone is bureaucratic and clinical first, monstrous second."
)


CATEGORY_FLAVORS: dict[str, str] = {
    "anomaly": (
        "Captured MTG entity inside an SCP containment cell or behind "
        "reinforced observation glass. Visible Foundation infrastructure: "
        "warning signage, concrete shielding, exposed wiring, monitoring "
        "equipment. The entity itself is rendered with full MTG cosmic-"
        "horror weight — Phyrexian oil, Eldrazi geometry, dragon scale, "
        "planar bleed. The cell shows containment wear: cracks, scorching, "
        "hastily-applied repair plates."
    ),
    "personnel": (
        "Foundation researcher in a lab coat with classified badge, "
        "photographed at a research site. Tired, focused, mid-career "
        "institutional presence. Faint signs of exposure to the anomaly "
        "they specialize in (oil flecks, scale residue, faint chromatic "
        "burn). Documents and clipboards visible. Sterile institutional "
        "lighting."
    ),
    "facility": (
        "Vast containment infrastructure rendered architecturally: "
        "concrete pillars, neon-signed sector markers, biohazard reactor "
        "cores, ventilation ductwork, distant catwalks. The facility's "
        "specific anomaly type bleeds into the architecture (oil veins, "
        "void-geometry corners, planar rift glow). Scale: dwarfing, "
        "institutional, dread-inducing."
    ),
    "procedure": (
        "Documented containment protocol diagrammed on stamped Foundation "
        "paperwork. Clinical, bureaucratic. Diagrams, redactions, "
        "classified stamps. The paper itself shows wear from circulation. "
        "Faint impressions of the procedure's anomaly subject bleed "
        "through (oil seepage, fractured geometry, scale impressions)."
    ),
    "mandate": (
        "An O5-Council directive with red-stamped 'CLASSIFIED' overlay. "
        "Austere, authoritative, single-page. Official Foundation seal. "
        "Faint glyphwork in the background suggesting the cosmic-horror "
        "mandate (Phyrexian sigils, Eldrazi rune-geometry, dragon-mark). "
        "Tone: institutional finality."
    ),
    "object": (
        "An institutional Foundation artefact — redacted dossier, "
        "containment apparatus, or research tool — photographed against "
        "concrete and sodium-arc light, with faint anomaly bleed-through."
    ),
}


_SCP_CATEGORY_BY_TYPE = {
    CardType.SCP_ANOMALY: "anomaly",
    CardType.SCP_PERSONNEL: "personnel",
    CardType.SCP_FACILITY: "facility",
    CardType.SCP_PROCEDURE: "procedure",
    CardType.SCP_MANDATE: "mandate",
}


def categorize(card: CardDefinition) -> str:
    """Return the art-prompt category for ``card``.

    Falls back to ``"object"`` for any unknown card type so the harness
    always has a flavor blurb.
    """
    types = getattr(card.characteristics, "types", None) or set()
    for scp_type, category in _SCP_CATEGORY_BY_TYPE.items():
        if scp_type in types:
            return category
    return "object"


__all__ = [
    "STYLE_HEADLINE",
    "STYLE_NEGATIVE",
    "CATEGORY_FLAVORS",
    "categorize",
]
