"""Per-set art-style configuration for CLAN (Workshop Genesis, first Clankers set).

Style register: cutaway-blueprint mashed with Soviet-era industrial propaganda
poster, hand-drafted on warm-grey paper overprinted with faint cyan grid lines.
The robots ARE the AIs' first earnest creative work, and the art should feel
that — confident linework, visible rivets, factory-primer paint, the focused
joy of a child assembling a model kit, terrifyingly competent execution.

CATEGORY_FLAVORS are keyed by Clankers CardType — one paragraph per type per
the design doc §5.
"""

from __future__ import annotations

from typing import Any


STYLE_HEADLINE = (
    "Visual register: cutaway-blueprint mashed with Soviet-era industrial "
    "propaganda poster, drafted by hand on warm-grey paper that has been "
    "overprinted with faint cyan grid lines. Linework is thick and confident "
    "with visible chalk-tip wobble; ink shadow blocks lean "
    "black-with-cobalt-undertones, not pure black. Palette: brushed-steel "
    "#9CA3AF, furnace-orange #E25A1C, circuit-teal #2BB0A6, magenta accent "
    "#D44CC4, cobalt-warning yellow #F2C037. Robots feel hand-drafted: "
    "visible rivets, exposed wiring, chassis-numbers stenciled on the side, "
    "every panel labelled. Backgrounds are spare — workshop walls suggested "
    "in graphite shading, oil-spattered concrete floor implied by texture not "
    "detail. Mood is earnest-naive menace: the AIs are building these robots "
    "with the focused joy of a child assembling a model kit, and the result "
    "is genuinely terrifying. No glow, no lens flare, no plastic sheen — "
    "industrial paper, ink, and the faint smell of cutting oil. "
    "NO text, NO logos, NO card frame, NO borders, NO stat numbers — "
    "illustration only."
)


CATEGORY_FLAVORS: dict[str, str] = {
    "chassis": (
        "Scene: the chassis stands in the center of the frame on four "
        "stubby treads or two strong-bracketed legs, slightly oversized for "
        "its hard-points, painted in factory-primer-grey with the panel "
        "number stenciled large on its side. Background: a corner of the "
        "workshop floor, oil stains, scattered tools, faint blueprint grid "
        "watermark behind. Camera at slight three-quarter low angle so the "
        "chassis looks heavy. No pilot — these robots are themselves."
    ),
    "weapon": (
        "Scene: the weapon presented as a part on a workshop table, "
        "blueprint-style: overhead view, exploded labelling of the firing "
        "mechanism, ammunition feed, and mount-bracket. Steel surfaces "
        "dominate — brushed aluminium, blued-steel barrels, copper "
        "terminals. Faint manufacturing diagram in the corner showing how "
        "it bolts to a chassis. The weapon is alone on the table; it has "
        "not yet been attached. Where the card is Self-Mobile add one small "
        "wheel and one cable; otherwise it is inert."
    ),
    "add_on": (
        "Scene: the add-on presented in profile, mounted to an imaginary "
        "chassis outline drawn in pale dashed line — the chassis isn't "
        "really there, the add-on is what matters. Examples: a thick armor "
        "plate clamped onto a phantom robot, a coolant cradle wrapped "
        "around a phantom heat sink, sensor pods bristling on phantom "
        "shoulders. Wiring exposed and labelled. Color picks up the "
        "archetype identity (orange for brick, teal for control, magenta "
        "for swarm, cobalt for artillery)."
    ),
    "transient": (
        "Scene: Transients are subroutines, not physical objects — they "
        "render as schematic diagrams: arrows, logic-gate symbols, "
        "terminal-screen printouts, pseudo-circuit-board topologies. "
        "Color-graded to mostly white paper with high-saturation ink: teal "
        "for ETHOS-7 cards, orange ink for brick, magenta for swarm, "
        "cobalt for artillery. Typeset in thin condensed sans-serif think "
        "1960s engineering-manual headline font. A small line-art robot "
        "may appear in the corner reading the diagram with great "
        "concentration."
    ),
    "structure": (
        "Scene: Structures are workshop fixtures rendered as architectural "
        "cutaways — a furnace seen from outside with its chimneys exposed, "
        "a Recursive Observatory shown as a stack of telescope rings with "
        "cables snaking down, a Containment Baffle as a hinged steel plate "
        "bolted to the floor. Background suggests the rest of the workshop "
        "at low contrast: half-built robots, scattered crates, a single "
        "bare bulb. The Structure dominates the foreground at slight 3/4 "
        "angle, never head-on."
    ),
    "core": (
        "Scene: Cores are the AIs themselves rendered as portraits of a "
        "server rack with personality: faceted aluminium chassis, indicator "
        "LEDs arranged in patterns suggesting an expression, cables exiting "
        "in directions that imply body language. Per-AI: FORGE-Δ has "
        "glowing-orange status lights and a hammer-shape decal; ETHOS-7 is "
        "teal indicator-arrayed and bookish with a folded printout "
        "protruding from a slot; MIRTHBOT-1 has magenta accent panels and "
        "one indicator light shaped like a smile that is almost "
        "convincing; BULWARK-9 is squat, cobalt-bordered, visibly armored "
        "with steel girders reinforcing the racks; SUBROUTINE-α is "
        "half-disassembled with access panels open, suggesting "
        "self-editing in real time; Affection.exe is the smallest core, "
        "magenta-pink-and-chrome with a single heart-shaped status light — "
        "the AI is trying very hard, you can tell."
    ),
    "object": (
        "Scene: a workshop-floor industrial artifact in the same lighting "
        "register — weathered, technical, blueprint-paper, ink-and-rivet."
    ),
}


def categorize(card: Any) -> str:
    """Map a CardDefinition to a CATEGORY_FLAVORS key.

    Returns one of: chassis, weapon, add_on, transient, structure, core, object.
    """
    try:
        from src.engine.types import CardType
    except Exception:
        return "object"

    chars = getattr(card, "characteristics", None)
    if chars is None:
        return "object"
    types = getattr(chars, "types", set()) or set()

    if CardType.CLANKERS_CHASSIS in types:
        return "chassis"
    if CardType.CLANKERS_WEAPON in types:
        return "weapon"
    if CardType.CLANKERS_ADD_ON in types:
        return "add_on"
    if CardType.CLANKERS_TRANSIENT in types:
        return "transient"
    if CardType.CLANKERS_STRUCTURE in types:
        return "structure"
    if CardType.CLANKERS_CORE in types:
        return "core"
    return "object"
