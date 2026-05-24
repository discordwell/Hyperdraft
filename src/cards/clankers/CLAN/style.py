"""Per-set art-style configuration for CLAN (Workshop Genesis, first Clankers set).

v3 (painterly): dropped all blueprint-paper / schematic / drafting-table /
exploded-view / dashed-line / annotation language. Subjects are now staged
in ATMOSPHERIC workshop SPACES with painterly depth — not on paper.

Visual register: Soviet-era industrial propaganda painting × oil-on-canvas
illustration. Subjects rendered with hand-drafted confident ink linework
over PAINTED INTERIOR — atmospheric depth, smoky workshop air, warm
ambient shadows. Backgrounds are SCENES, not paper.

CATEGORY_FLAVORS use ``<type>__<archetype>`` keys; Cores get bespoke
per-AI flavors. All anchor to the same painterly headline.
"""

from __future__ import annotations

from typing import Any


STYLE_HEADLINE = (
    "Visual register: Soviet-era industrial propaganda PAINTING in the "
    "vein of Stalin-era oil-on-canvas posters — strong block-color "
    "compositions, hand-drafted ink outlines over painted interior, "
    "atmospheric depth. NOT a technical drawing, NOT a blueprint, NOT a "
    "schematic — this is illustrative painting. Backgrounds are real "
    "industrial spaces with painted atmospheric depth: smoky workshop "
    "interiors, dim factory floors, dust motes in shafts of warm side-"
    "light, fade-to-shadow at the edges. NEVER paper backdrops, NEVER "
    "graph paper, NEVER printed grids, NEVER drafting tables. Linework "
    "is thick and confident with visible chalk-tip wobble; shadow blocks "
    "lean black-with-cobalt-undertones. Palette: brushed-steel #9CA3AF, "
    "furnace-orange #E25A1C, circuit-teal #2BB0A6, magenta accent "
    "#D44CC4, cobalt-warning yellow #F2C037. Robots have visible rivets, "
    "exposed wiring, chassis-numbers stenciled on the side. Mood is "
    "earnest-naive menace: the AIs are building these robots with the "
    "focused joy of a child assembling a model kit, and the result is "
    "genuinely terrifying. No glow, no lens flare, no plastic sheen — "
    "just paint, dust, and metal. Illustration only — no text, no logos, "
    "no card frame, no borders, no stat numbers."
)


# ---------------------------------------------------------------------------
# Archetype palette anchors
# ---------------------------------------------------------------------------

_ARCHETYPE_INK = {
    "brick":     "furnace-orange dominant, oil-stained warm grey background",
    "control":   "circuit-teal dominant, cold blue-grey background, slate-shadowed",
    "swarm":     "magenta accent dominant, warm pink-cream background, slightly chaotic",
    "artillery": "cobalt-warning yellow dominant, weathered olive-grey background",
    "neutral":   "monochrome brushed-steel, warm grey background, no archetype tint",
}


# ---------------------------------------------------------------------------
# Chassis — robot foregrounded in atmospheric workshop scene
# ---------------------------------------------------------------------------

_CHASSIS_FLAVORS = {
    "chassis__brick": (
        "Scene: a HEAVY industrial chassis foregrounded in the center of "
        "a smoky forge interior — wide stance, stubby caterpillar treads "
        "or thick-bracketed legs, oversized welded plating, factory-"
        "primer-grey paint with the panel number stenciled large in "
        "orange on its flank. Camera at slight three-quarter LOW angle, "
        "the chassis looks crushing. Background: forge bay in painted "
        "atmospheric depth, orange furnace glow on the back wall, dust "
        "motes in shafts of side-light, scattered hammer-rivets on the "
        "concrete floor. Painterly oil-on-canvas register. No pilot."
    ),
    "chassis__control": (
        "Scene: a SLENDER, careful chassis foregrounded in a dim "
        "instrument bay — long limbs, exposed wiring trunks, a small "
        "array of indicator-LED clusters at head height. Camera at "
        "NEAR-EYE level, three-quarter view. Background: shadowed "
        "workshop wall with hanging tools, a single chart-light overhead "
        "casting cool teal-tinted shadows, atmospheric haze. Painterly "
        "oil-on-canvas register, cold blue-grey ambient. No pilot."
    ),
    "chassis__swarm": (
        "Scene: a COMPACT, twitchy chassis foregrounded — short limbs, a "
        "single exaggerated optical lens, plating with hand-painted "
        "magenta accent stripes. Often shown in a row of 2-3 identical "
        "bodies in soft echelon, suggesting more behind. Camera at "
        "SLIGHT HIGH angle. Background: warm pink-cream workshop floor "
        "with scattered small parts, atmospheric haze, fade-to-shadow at "
        "the edges. Painterly oil-on-canvas register. No pilot."
    ),
    "chassis__artillery": (
        "Scene: a SQUAT, dug-in chassis foregrounded in a fortified "
        "emplacement — wide low profile, reinforced skirt armor, gun "
        "ports and observation slits stenciled with cobalt warning "
        "chevrons. Camera at WAIST-HEIGHT, three-quarter view. "
        "Background: military supply-yard at dusk, sandbag emplacements, "
        "atmospheric dust-haze, a single cobalt-yellow stencil sign on a "
        "back wall. Painterly oil-on-canvas register, weathered olive-"
        "grey ambient. No pilot."
    ),
    "chassis__neutral": (
        "Scene: a NONDESCRIPT workshop chassis foregrounded in an empty "
        "workshop corner — generic factory-primer grey, simple welded "
        "plating. Camera three-quarter view at MID height. Background: "
        "monochrome workshop floor, an oil stain, single bare bulb above "
        "casting soft warm light, atmospheric haze. Painterly oil-on-"
        "canvas register. No pilot."
    ),
}


# ---------------------------------------------------------------------------
# Weapons — staged on a forge bench / armory floor (not a draftsman's table)
# ---------------------------------------------------------------------------

_WEAPON_FLAVORS = {
    "weapon__brick": (
        "Scene: a HEAVY-CALIBRE weapon resting on the forge bench in a "
        "dim industrial bay — thick barrel, exposed feed mechanism, "
        "brass-fittings catching warm orange light from a furnace "
        "off-frame. Three-quarter view, camera slightly above the "
        "weapon. Background: shadowed forge bay, oil-stained concrete "
        "floor, scattered shell casings, soft atmospheric haze, fade-to-"
        "shadow at the edges. Painterly oil-on-canvas register. "
        "Furnace-orange dominant. No glow."
    ),
    "weapon__control": (
        "Scene: a PRECISION instrument-weapon resting on a steel "
        "instrument tray in a cold instrument bay — slim rifle-shape or "
        "scribe-like emitter, exposed circuit-board traces in circuit-"
        "teal, sensor optics at the muzzle. Three-quarter view. "
        "Background: dim wall of hanging tools and pinned charts (charts "
        "are PAINTED objects in the scene, NOT the backdrop), cool blue-"
        "grey ambient, atmospheric depth. Painterly oil-on-canvas "
        "register. No glow."
    ),
    "weapon__swarm": (
        "Scene: a SMALL FAST weapon on a wooden workshop bench — wire-"
        "thin, hand-painted in magenta enamel, often shown with TWO OR "
        "THREE siblings of slightly different shape (the swarm builds a "
        "lot of almost-the-same). Three-quarter view, camera above. "
        "Background: warm pink-cream workshop bench-top, scattered tools, "
        "soft side-light, atmospheric haze, fade-to-shadow at the edges. "
        "Painterly oil-on-canvas register. Magenta accent dominant."
    ),
    "weapon__artillery": (
        "Scene: a LONG-RANGE artillery weapon resting in an armory bay — "
        "heavy barrel on a wheeled carriage or fixed mount, recoil "
        "mechanism, stencil-painted with cobalt-yellow warning chevrons. "
        "Side-view from the gun-line, camera at the breech. Background: "
        "military armory at dusk, sandbag walls, atmospheric dust-haze, "
        "a single cobalt warning sign on a back wall. Painterly oil-on-"
        "canvas register. Weathered olive-grey ambient. No glow."
    ),
    "weapon__neutral": (
        "Scene: a SERVICEABLE weapon resting on the workshop bench — "
        "simple, unstylish, monochrome brushed-steel. Three-quarter view. "
        "Background: empty workshop bench-top, single bare bulb above, "
        "soft atmospheric haze, fade-to-shadow at the edges. Painterly "
        "oil-on-canvas register. Quintessentially 'standard issue'."
    ),
}


# ---------------------------------------------------------------------------
# Add-Ons — shown bolted to a partial chassis or laid out in workshop space
# (no more dashed-line phantom-chassis outlines)
# ---------------------------------------------------------------------------

_ADD_ON_FLAVORS = {
    "add_on__brick": (
        "Scene: an industrial add-on shown bolted onto a partial chassis "
        "side-section — thick armor plate, structural cradle, or heat-"
        "sink array. The chassis side-section is REAL and PAINTED (just "
        "partially in frame, not the full body), the add-on is the focal "
        "subject. Profile view. Background: shadowed forge bay, oil-"
        "stained concrete, atmospheric haze. Painterly oil-on-canvas "
        "register. Furnace-orange dominant."
    ),
    "add_on__control": (
        "Scene: a precision sensor or processing module bolted onto a "
        "partial chassis side-section in a dim instrument bay — exposed "
        "circuit boards, cooling fins, ribbon cables. The chassis side-"
        "section is REAL and PAINTED (just partially visible). Profile "
        "view. Background: workshop wall with hanging tools, cool blue-"
        "grey ambient, atmospheric depth. Painterly oil-on-canvas. "
        "Circuit-teal dominant."
    ),
    "add_on__swarm": (
        "Scene: a small fast accessory — a sleeve, a coil, a charm-"
        "module — bolted onto a partial chassis side-section. Magenta "
        "enamel accent paint. The chassis side-section is REAL and "
        "PAINTED (just partially visible). Profile view. Background: "
        "warm pink-cream workshop bench area, scattered small parts, "
        "atmospheric haze. Painterly oil-on-canvas. Magenta dominant."
    ),
    "add_on__artillery": (
        "Scene: a heavy armor plate or bunker cradle bolted onto a "
        "partial chassis side-section — reinforced bolts, cobalt-yellow "
        "stencil warnings, dented surfaces showing prior service. The "
        "chassis side-section is REAL and PAINTED (just partially "
        "visible). Profile view. Background: military supply-yard at "
        "dusk, sandbags, atmospheric dust-haze. Painterly oil-on-canvas. "
        "Cobalt-yellow dominant."
    ),
    "add_on__neutral": (
        "Scene: an unstylish utility add-on bolted onto a partial chassis "
        "side-section — generic plating, monochrome brushed-steel. The "
        "chassis side-section is REAL and PAINTED (just partially "
        "visible). Profile view. Background: empty workshop corner, "
        "single bare bulb, atmospheric haze. Painterly oil-on-canvas."
    ),
}


# ---------------------------------------------------------------------------
# Transients — staged painterly SCENES representing the effect, not
# schematic diagrams. The card's effect is the SUBJECT of the painting.
# ---------------------------------------------------------------------------

_TRANSIENT_FLAVORS = {
    "transient__brick": (
        "Scene: a PAINTERLY MOMENT illustrating an industrial subroutine "
        "in action — could be a forge-strike captured at impact (sparks "
        "frozen mid-air), a chassis being slammed into shape, an anvil "
        "ringing with the strike just past. Furnace-orange dominant. "
        "Background: dim forge bay, atmospheric haze, fade-to-shadow at "
        "the edges. Painterly oil-on-canvas register. NO schematic, NO "
        "diagram, NO text — just the moment as a painting."
    ),
    "transient__control": (
        "Scene: a QUIET PAINTERLY MOMENT illustrating a control "
        "subroutine — could be a small line-art chassis at a desk under "
        "a chart-light, hand reaching for a printout, or an instrument "
        "reading a measurement (the measurement itself is implied by "
        "what's being looked at, not by visible numbers). Circuit-teal "
        "dominant. Background: dim instrument bay, cool blue-grey "
        "ambient, atmospheric depth. Painterly oil-on-canvas. NO "
        "schematic, NO diagram, NO text."
    ),
    "transient__swarm": (
        "Scene: a FRENETIC PAINTERLY MOMENT — multiple small chassis in "
        "motion, all doing something at once, dust kicked up around "
        "them, a sense of CHEERFUL CHAOS. Magenta accent dominant. "
        "Background: warm pink-cream workshop floor, atmospheric haze, "
        "scattered parts. Painterly oil-on-canvas. NO schematic, NO "
        "diagram, NO text."
    ),
    "transient__artillery": (
        "Scene: a TACTICAL PAINTERLY MOMENT — a chassis in firing "
        "stance behind sandbags, smoke from a recent shot, a target "
        "implied in the middle distance (the target itself off-frame or "
        "obscured by atmospheric haze). Cobalt-yellow dominant. "
        "Background: military supply-yard at dusk, dust-haze, fortified "
        "positions. Painterly oil-on-canvas. NO schematic, NO diagram, "
        "NO text."
    ),
    "transient__neutral": (
        "Scene: a UTILITARIAN PAINTERLY MOMENT — a generic workshop "
        "subroutine in action, a tool being put to work, no archetype "
        "tint. Monochrome brushed-steel dominant. Background: empty "
        "workshop bay, single bare bulb, atmospheric haze. Painterly "
        "oil-on-canvas. NO schematic, NO diagram, NO text."
    ),
}


# ---------------------------------------------------------------------------
# Structures — workshop fixtures in atmospheric depth (no cutaways)
# ---------------------------------------------------------------------------

_STRUCTURE_FLAVORS = {
    "structure__brick": (
        "Scene: an industrial WORKSHOP FIXTURE foregrounded in a real "
        "industrial space — a brick forge with chimneys, a smelter "
        "casting orange glow onto the floor, an anvil bay with crane "
        "gantries overhead. The fixture is the subject; it sits in the "
        "scene, not as a cutaway. Slight three-quarter angle. "
        "Background: dim forge bay receding into atmospheric haze, "
        "scattered tools, dust motes in side-light. Painterly oil-on-"
        "canvas. Furnace-orange dominant."
    ),
    "structure__control": (
        "Scene: a precision WORKSHOP FIXTURE foregrounded in a quiet "
        "instrument bay — a recursive-observatory tower stack of "
        "telescope rings with cables, a server-rack column with exposed "
        "wiring, an instrument-room interior. The fixture is the subject "
        "in real space, not a cutaway. Slight three-quarter angle. "
        "Background: cool blue-grey ambient, hanging tools, atmospheric "
        "depth. Painterly oil-on-canvas. Circuit-teal dominant."
    ),
    "structure__swarm": (
        "Scene: a BUSY WORKSHOP FIXTURE in the warm-pink ambient of a "
        "chaotic workshop — a mass-production line with conveyor belts "
        "running and small chassis being assembled, an iron-cluster "
        "gantry holding many almost-finished bodies at once. The "
        "fixture is the subject in real space, not a cutaway. Three-"
        "quarter angle. Background: warm pink-cream haze, scattered "
        "parts on the floor, atmospheric depth. Painterly oil-on-canvas. "
        "Magenta dominant."
    ),
    "structure__artillery": (
        "Scene: a FORTIFIED WORKSHOP FIXTURE in a military supply-yard "
        "— a containment baffle (a hinged steel plate bolted to the "
        "floor), a workshop sprinkler system overhead with cobalt "
        "piping, a sandbagged emplacement. The fixture is the subject "
        "in real space, not a cutaway. Three-quarter angle. Background: "
        "dusk supply-yard, sandbag walls, atmospheric dust-haze, "
        "cobalt-yellow stencil warnings on back walls. Painterly oil-"
        "on-canvas. Weathered olive-grey ambient."
    ),
    "structure__neutral": (
        "Scene: a UTILITY WORKSHOP FIXTURE foregrounded in a generic "
        "workshop space — a shared-bus rack, a public telemetry board, "
        "an auxiliary bench. Three-quarter angle. Background: empty "
        "workshop ambient, single bare bulb above, atmospheric haze. "
        "Painterly oil-on-canvas. Monochrome brushed-steel dominant."
    ),
}


# ---------------------------------------------------------------------------
# Cores — bespoke per-AI server-rack PORTRAITS, painterly atmospheric depth
# ---------------------------------------------------------------------------

_CORE_FLAVORS = {
    "core__FORGE-Δ": (
        "Scene: a SOVIET-POSTER PORTRAIT of a server-rack AI named "
        "FORGE-Δ — faceted aluminium chassis, indicator-LED clusters "
        "arranged in a pattern suggesting brow-furrowed concentration. "
        "Cables exit downward and to the left like braced shoulders. "
        "GLOWING-ORANGE status lights (just lit dots, no lens flare). A "
        "hammer-shape stencil decal painted on the front panel in "
        "furnace-orange. Camera at near-eye level, three-quarter. "
        "Background: dim forge bay receding into atmospheric haze, warm "
        "orange backlight from a furnace off-frame, fade-to-shadow at "
        "the edges. Painterly oil-on-canvas Soviet-poster register. "
        "The rack appears HEAVY and reliable."
    ),
    "core__ETHOS-7": (
        "Scene: a SOVIET-POSTER PORTRAIT of a server-rack AI named "
        "ETHOS-7 — slimmer than FORGE-Δ, indicator-LEDs in TEAL "
        "arranged in two precise rows reading as faintly scholarly "
        "eyes. A FOLDED PRINTOUT protrudes from a slot near the top "
        "like a tongue-poking-out tell. Cables exit in neat parallel "
        "runs to the right. Camera at near-eye level, three-quarter. "
        "Background: dim instrument bay receding into cool blue-grey "
        "atmospheric haze, a single chart-light overhead, fade-to-"
        "shadow at the edges. Painterly oil-on-canvas Soviet-poster "
        "register. The AI looks studious, slightly bookish, faintly "
        "amused."
    ),
    "core__MIRTHBOT-1": (
        "Scene: a SOVIET-POSTER PORTRAIT of a server-rack AI named "
        "MIRTHBOT-1 — squatter, more cartoony than the others, painted "
        "in MAGENTA accent panels over factory-primer grey. ONE "
        "indicator light is shaped like a SMILE that is almost "
        "convincing. Many small auxiliary cables fan out chaotically. "
        "Camera at near-eye level, three-quarter. Background: warm "
        "pink-cream workshop ambient, scattered small parts at the "
        "feet of the rack, soft atmospheric haze, fade-to-shadow at "
        "the edges. Painterly oil-on-canvas. The AI looks earnestly "
        "delighted by its own existence; that delight is also somewhat "
        "alarming."
    ),
    "core__BULWARK-9": (
        "Scene: a SOVIET-POSTER PORTRAIT of a server-rack AI named "
        "BULWARK-9 — SQUAT, wide stance, visibly armored: STEEL "
        "GIRDERS reinforce the rack's frame, COBALT-BORDERED warning "
        "chevrons painted around its edges. Indicator-LEDs are few but "
        "BRIGHT YELLOW (the deadliest color). Cables exit in armored "
        "conduits. Camera at near-eye level, three-quarter. Background: "
        "military supply-yard at dusk, sandbag emplacements, "
        "atmospheric dust-haze, fade-to-shadow at the edges. Painterly "
        "oil-on-canvas. The AI reads as a defensive position — bunker "
        "more than thinker."
    ),
    "core__SUBROUTINE-α": (
        "Scene: a SOVIET-POSTER PORTRAIT of a server-rack AI named "
        "SUBROUTINE-α — HALF-DISASSEMBLED, its own access panels OPEN, "
        "internal modules exposed with hand-painted markings in "
        "CIRCUIT-TEAL ink visible on the interior surfaces. The AI is "
        "editing itself in real time. Small tool-arms (its own, "
        "presumably) reach back into the open chassis. Camera at near-"
        "eye level, three-quarter. Background: dim instrument bay "
        "receding into cool blue-grey atmospheric haze, fade-to-shadow "
        "at the edges. Painterly oil-on-canvas. The portrait feels "
        "recursive — a thing tinkering with the thing that is doing "
        "the tinkering."
    ),
    "core__Affection.exe": (
        "Scene: a SOVIET-POSTER PORTRAIT of a server-rack AI named "
        "Affection.exe — the SMALLEST core, painted in MAGENTA-PINK-"
        "AND-CHROME, with a single HEART-SHAPED status light glowing "
        "faintly in the centre. Cables exit downward in a careful loop, "
        "like a held breath. Camera at near-eye level, three-quarter. "
        "Background: warm pink-cream workshop ambient with soft "
        "atmospheric haze, gentle fade-to-shadow at the edges. "
        "Painterly oil-on-canvas. The AI is trying very hard — you can "
        "tell from how neatly all the wires are routed."
    ),
}


# ---------------------------------------------------------------------------
# Flat CATEGORY_FLAVORS — what art_harness.py actually consumes
# ---------------------------------------------------------------------------

CATEGORY_FLAVORS: dict[str, str] = {
    **_CHASSIS_FLAVORS,
    **_WEAPON_FLAVORS,
    **_ADD_ON_FLAVORS,
    **_TRANSIENT_FLAVORS,
    **_STRUCTURE_FLAVORS,
    **_CORE_FLAVORS,
    "chassis": _CHASSIS_FLAVORS["chassis__neutral"],
    "weapon": _WEAPON_FLAVORS["weapon__neutral"],
    "add_on": _ADD_ON_FLAVORS["add_on__neutral"],
    "transient": _TRANSIENT_FLAVORS["transient__neutral"],
    "structure": _STRUCTURE_FLAVORS["structure__neutral"],
    "core": _CORE_FLAVORS["core__FORGE-Δ"],
    "object": (
        "Scene: a workshop-floor industrial artifact in the same "
        "painterly oil-on-canvas register — atmospheric depth, warm "
        "side-light, fade-to-shadow at the edges."
    ),
}


# ---------------------------------------------------------------------------
# Per-card classification
# ---------------------------------------------------------------------------

def _archetype_tag(card: Any) -> str:
    arch = (getattr(card, "clankers_archetype", None) or "neutral").lower().strip()
    if arch not in ("brick", "control", "swarm", "artillery", "neutral"):
        arch = "neutral"
    return arch


def categorize(card: Any) -> str:
    """Map a CardDefinition to a CATEGORY_FLAVORS key.

    Cores → ``core__<exact name>`` (bespoke per-AI).
    Other types → ``<type>__<archetype>`` (painterly archetype-tinted scene).
    """
    try:
        from src.engine.types import CardType
    except Exception:
        return "object"

    chars = getattr(card, "characteristics", None)
    if chars is None:
        return "object"
    types = getattr(chars, "types", set()) or set()

    if CardType.CLANKERS_CORE in types:
        key = f"core__{card.name}"
        return key if key in CATEGORY_FLAVORS else "core"

    arch = _archetype_tag(card)
    if CardType.CLANKERS_CHASSIS in types:
        return f"chassis__{arch}"
    if CardType.CLANKERS_WEAPON in types:
        return f"weapon__{arch}"
    if CardType.CLANKERS_ADD_ON in types:
        return f"add_on__{arch}"
    if CardType.CLANKERS_TRANSIENT in types:
        return f"transient__{arch}"
    if CardType.CLANKERS_STRUCTURE in types:
        return f"structure__{arch}"
    return "object"
