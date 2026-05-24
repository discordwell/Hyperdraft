"""Per-set art-style configuration for CLAN (Workshop Genesis, first Clankers set).

Visual register: Soviet-era industrial propaganda poster crossed with
hand-drafted technical illustration, rendered in ink-and-wash on warm-grey
paper. Backgrounds are PLAIN — atmospheric space with subtle graphite
shading, oil-stained concrete, or workshop-wall ambient texture — NEVER
blueprint grids or printed graph-paper. Robots feel hand-drafted: visible
rivets, exposed wiring, chassis-numbers stenciled on the side, factory-
primer paint, every panel labelled. Tone: earnest-naive menace.

CATEGORY_FLAVORS use ``<type>__<archetype>`` keys for the four archetypes
(brick / control / swarm / artillery) plus ``<type>__neutral`` for utility
cards, so the deck's visual identity carries through every card type. Cores
get bespoke per-AI flavors (each of the 6 Cores reads as a distinct
personality). All flavors anchor to the same style headline.
"""

from __future__ import annotations

from typing import Any


STYLE_HEADLINE = (
    "Visual register: Soviet-era industrial propaganda poster crossed with "
    "hand-drafted technical illustration, rendered in ink-and-wash on warm-"
    "grey paper. Backgrounds are plain — atmospheric haze, subtle graphite "
    "shading, oil-stained concrete workshop floor, or solid warm-grey "
    "ambient — never graph paper or printed grids. Linework is thick and "
    "confident with visible chalk-tip wobble; ink shadow blocks lean black-"
    "with-cobalt-undertones, not pure black. Palette: brushed-steel "
    "#9CA3AF, furnace-orange #E25A1C, circuit-teal #2BB0A6, magenta accent "
    "#D44CC4, cobalt-warning yellow #F2C037. Robots feel hand-drafted: "
    "visible rivets, exposed wiring, chassis-numbers stenciled on the side, "
    "every panel labelled. Mood is earnest-naive menace: the AIs are "
    "building these robots with the focused joy of a child assembling a "
    "model kit, and the result is genuinely terrifying. No glow, no lens "
    "flare, no plastic sheen — only paper, ink, and the faint smell of "
    "cutting oil. Illustration only — no text, no logos, no card frame, "
    "no borders, no stat numbers."
)


# ---------------------------------------------------------------------------
# Archetype palette anchors — these tints carry through every card type so
# brick decks read orange-heavy, control reads teal, swarm reads magenta,
# artillery reads cobalt. Neutral cards use brushed-steel monochrome.
# ---------------------------------------------------------------------------

_ARCHETYPE_INK = {
    "brick":     "furnace-orange ink, oil-stained warm grey paper",
    "control":   "circuit-teal ink, cold blue-grey paper, faint chart overlays",
    "swarm":     "magenta accent ink, bright cream paper, slightly chaotic registration",
    "artillery": "cobalt-warning yellow ink, military stencil overlays, weathered olive-grey paper",
    "neutral":   "monochrome brushed-steel, warm grey paper, no archetype tint",
}


# ---------------------------------------------------------------------------
# Per-type × per-archetype flavors. Each is the SECOND paragraph (after the
# global headline) — describes the subject + composition + lighting beats.
# ---------------------------------------------------------------------------

# Chassis — the robot itself, foregrounded heavy in 3/4 low angle.
_CHASSIS_FLAVORS = {
    "chassis__brick": (
        "Scene: a HEAVY industrial chassis dominating the frame — wide stance, "
        "stubby caterpillar treads or thick-bracketed legs, oversized welded "
        "plating, factory-primer-grey paint with the panel number stenciled "
        "large in orange on its flank. Camera at slight three-quarter LOW "
        "angle so the chassis looks crushing. Background: workshop forge in "
        "graphite shading, orange furnace glow leaking from a side aperture, "
        "scattered hammer-rivets on the floor. Furnace-orange ink, oil-stained "
        "warm grey paper. No pilot."
    ),
    "chassis__control": (
        "Scene: a SLENDER, careful chassis — long limbs, exposed wiring "
        "trunks, a small array of indicator-LED clusters mounted at head "
        "height. Camera at NEAR-EYE level, three-quarter view, the chassis "
        "appears thoughtful rather than threatening. Background: a workshop "
        "wall of pinned schematics and rolled paper-rolls in cool blue-grey "
        "tones; a single chart-light overhead. Circuit-teal ink dominant. "
        "Plain cool-paper background, NO printed grid. No pilot."
    ),
    "chassis__swarm": (
        "Scene: a COMPACT, twitchy chassis — short limbs, a single "
        "exaggerated optical lens, plating with hand-painted magenta accent "
        "stripes. Often shown in a row of 2-3 identical bodies in soft "
        "echelon, suggesting more behind. Camera at SLIGHT HIGH angle "
        "looking down, making them small and many. Background: cream-paper "
        "workshop floor, scattered small parts, faint pawprints of magenta "
        "ink. Slightly chaotic registration. No pilot."
    ),
    "chassis__artillery": (
        "Scene: a SQUAT, dug-in chassis — wide low profile, reinforced skirt "
        "armor, gun ports and observation slits stenciled with cobalt "
        "warning chevrons. Camera at WAIST-HEIGHT, three-quarter view, the "
        "chassis appears emplaced rather than mobile. Background: military "
        "supply-yard at dusk, sandbag emplacements, a single cobalt-yellow "
        "stencil sign. Weathered olive-grey paper. No pilot."
    ),
    "chassis__neutral": (
        "Scene: a NONDESCRIPT workshop chassis — generic factory-primer "
        "grey, simple welded plating, no archetype-specific paint. Camera "
        "three-quarter view at MID height. Background: empty workshop "
        "corner, oil stain, single bare bulb above. Monochrome brushed-"
        "steel inks. No pilot."
    ),
}


# Weapons — a part on a workshop table, technical exploded view.
_WEAPON_FLAVORS = {
    "weapon__brick": (
        "Scene: a HEAVY-CALIBRE weapon on the forge bench — thick barrel, "
        "exposed feed mechanism, brass-fittings glinting. Overhead "
        "exploded technical view with labels and tolerance lines around "
        "the muzzle, breech, and mount-bracket. Furnace-orange ink overlays "
        "trace the firing path. Background: oil-stained warm-grey paper, "
        "scattered shell casings. No glow. Industrial."
    ),
    "weapon__control": (
        "Scene: a PRECISION instrument-weapon on a draftsman's table — slim "
        "rifle-shape or scribe-like emitter, lots of exposed circuit-board "
        "traces in circuit-teal, sensor optics at the muzzle. Blueprint "
        "register: top-down with measurement lines and probability fans "
        "extending forward. Cool blue-grey paper. No glow."
    ),
    "weapon__swarm": (
        "Scene: a SMALL FAST weapon on the workshop bench — wire-thin, "
        "hand-painted in magenta enamel, often shown with TWO OR THREE "
        "siblings of slightly different shape (the swarm builds a lot of "
        "almost-the-same). Top-down technical-illustration view, faint "
        "exploded assembly diagram beside it. Bright cream paper, magenta "
        "accent ink."
    ),
    "weapon__artillery": (
        "Scene: a LONG-RANGE artillery weapon — heavy barrel, recoil "
        "mechanism, stencil-painted with cobalt-yellow warning chevrons. "
        "Blueprint side-view with elevation arc and aiming reticle overlay. "
        "Weathered olive-grey paper. Military supply-yard register. No "
        "glow."
    ),
    "weapon__neutral": (
        "Scene: a SERVICEABLE weapon on the workshop table — simple, "
        "unstylish, monochrome brushed-steel. Top-down technical illustration "
        "with labels. Warm grey paper. Quintessentially 'standard issue'."
    ),
}


# Add-Ons — mounted in profile to a dashed-line phantom chassis outline.
_ADD_ON_FLAVORS = {
    "add_on__brick": (
        "Scene: an industrial add-on clamped to a DASHED-LINE phantom "
        "chassis outline — thick armor plate, structural cradle, or heat-"
        "sink array. Profile view. Visible bolts and weld seams. Furnace-"
        "orange ink, oil-stain texture on warm-grey paper. The phantom "
        "chassis is shown in pale dashed lines; the add-on is the only "
        "fully-rendered subject."
    ),
    "add_on__control": (
        "Scene: a precision sensor or processing module clamped to a "
        "DASHED-LINE phantom chassis — exposed circuit boards, cooling "
        "fins, ribbon cables labelled with circuit-teal annotations. "
        "Profile view. Cool blue-grey paper. The phantom chassis is in "
        "pale dashed lines; the module is the fully-rendered subject."
    ),
    "add_on__swarm": (
        "Scene: a small fast accessory — a sleeve, a coil, a charm-module "
        "— clamped to a DASHED-LINE phantom chassis. Magenta enamel accent "
        "paint. Hand-drafted feel, slightly off-register. The phantom "
        "chassis is in pale dashed lines; the accessory is what matters."
    ),
    "add_on__artillery": (
        "Scene: a heavy armor plate or bunker cradle clamped to a DASHED-"
        "LINE phantom chassis — reinforced bolts, cobalt-yellow stencil "
        "warnings, dented surfaces showing prior service. Profile view, "
        "military supply-yard register. The phantom chassis is in pale "
        "dashed lines; the armor is the subject."
    ),
    "add_on__neutral": (
        "Scene: an unstylish utility add-on clamped to a DASHED-LINE "
        "phantom chassis — generic plating, monochrome brushed-steel. "
        "Profile view. Warm grey paper. The phantom chassis is in pale "
        "dashed lines."
    ),
}


# Transients — schematic diagrams, not physical objects.
_TRANSIENT_FLAVORS = {
    "transient__brick": (
        "Scene: a SCHEMATIC DIAGRAM, not a physical object — logic-gate "
        "symbols, flowcharts, terminal-screen printouts of a forge "
        "subroutine. Furnace-orange ink on mostly-white paper. A small "
        "line-art chassis in the corner reads the diagram with great "
        "concentration. Typeset in thin condensed sans-serif (1960s "
        "engineering-manual headline font). NO LEGIBLE TEXT — letterforms "
        "implied but not readable."
    ),
    "transient__control": (
        "Scene: an ELEGANT SCHEMATIC — circuit-board topology, branching "
        "probability fans, archive-spool printouts trailing off the lower "
        "edge. Circuit-teal ink on cool white paper. A small line-art "
        "chassis with a clipboard observes. 1960s engineering-manual "
        "register. NO LEGIBLE TEXT."
    ),
    "transient__swarm": (
        "Scene: a FRENETIC SCHEMATIC — multiple parallel arrows, signal-"
        "spread diagrams, lots of small footnotes in magenta accent. "
        "Bright cream paper. A pair of small line-art chassis run "
        "alongside the diagram in motion. Slightly off-register. NO "
        "LEGIBLE TEXT."
    ),
    "transient__artillery": (
        "Scene: a TACTICAL SCHEMATIC — ballistic arcs, range-table "
        "fragments, fortified-position symbols, cobalt-yellow warning "
        "overlays. Weathered military paper. A single line-art chassis "
        "stands behind sandbags in the corner. Military stencil "
        "letterforms. NO LEGIBLE TEXT."
    ),
    "transient__neutral": (
        "Scene: a UTILITARIAN SCHEMATIC — generic logic flow, terminal "
        "printout. Monochrome brushed-steel. Warm grey paper. NO LEGIBLE "
        "TEXT."
    ),
}


# Structures — workshop fixtures, rendered as architectural cutaways.
_STRUCTURE_FLAVORS = {
    "structure__brick": (
        "Scene: an industrial WORKSHOP FIXTURE rendered as ARCHITECTURAL "
        "CUTAWAY — a forge with chimneys exposed, a smelter showing its "
        "molten interior, an anvil-bay with crane gantries overhead. "
        "Furnace-orange glow leaking from internal apertures (but no lens "
        "flare). Slight three-quarter angle, never head-on. Background "
        "suggests rest of workshop at low contrast."
    ),
    "structure__control": (
        "Scene: a precision WORKSHOP FIXTURE rendered as ARCHITECTURAL "
        "CUTAWAY — a recursive observatory shown as a stack of telescope "
        "rings with cables snaking down, a server-rack column with exposed "
        "wiring, a chart-table room with overhead light. Circuit-teal "
        "annotations on a cool blue-grey backdrop. Slight three-quarter "
        "angle."
    ),
    "structure__swarm": (
        "Scene: a CHAOTIC WORKSHOP FIXTURE — a mass-production line shown "
        "in cutaway with conveyor belts running, an iron-cluster gantry "
        "holding many small almost-finished chassis at once, a swarm "
        "beacon antenna with little magenta pennants strung from it. Bright "
        "cream paper. Slightly off-register. Three-quarter angle."
    ),
    "structure__artillery": (
        "Scene: a FORTIFIED WORKSHOP FIXTURE — a containment baffle "
        "rendered as a hinged steel plate bolted to the floor, a workshop "
        "sprinkler system shown in cutaway with cobalt-piping running "
        "through the ceiling, a sandbagged emplacement. Cobalt-yellow "
        "stencil warnings. Weathered olive-grey paper. Three-quarter angle."
    ),
    "structure__neutral": (
        "Scene: a UTILITY WORKSHOP FIXTURE — a shared-bus rack, a public "
        "telemetry board, an auxiliary bench. Monochrome brushed-steel. "
        "Architectural cutaway, slight three-quarter angle."
    ),
}


# ---------------------------------------------------------------------------
# Cores — bespoke per-AI. Each AI is a SERVER-RACK PORTRAIT with personality.
# ---------------------------------------------------------------------------

_CORE_FLAVORS = {
    "core__FORGE-Δ": (
        "Scene: a PORTRAIT of a server-rack AI named FORGE-Δ — faceted "
        "aluminium chassis, indicator-LED clusters arranged in a pattern "
        "suggesting brow-furrowed concentration. Cables exit downward and "
        "to the left like braced shoulders. GLOWING-ORANGE status lights "
        "dominate (but no lens flare — just lit dots). A hammer-shape "
        "stencil decal is painted on the front panel in furnace-orange. "
        "Warm grey paper, the rack appears HEAVY and reliable. Soviet-"
        "industrial poster register."
    ),
    "core__ETHOS-7": (
        "Scene: a PORTRAIT of a server-rack AI named ETHOS-7 — slimmer "
        "than FORGE-Δ, indicator-LEDs in TEAL arranged in two precise "
        "rows reading as faintly scholarly eyes. A FOLDED PRINTOUT "
        "protrudes from a slot near the top like a tongue-poking-out tell. "
        "Cables exit in neat parallel runs to the right. Cool blue-grey "
        "paper. A chart pinned beside it (illegible) shows a probability "
        "fan. The AI looks studious, slightly bookish, faintly amused."
    ),
    "core__MIRTHBOT-1": (
        "Scene: a PORTRAIT of a server-rack AI named MIRTHBOT-1 — squatter, "
        "more cartoony than the others, painted in MAGENTA accent panels "
        "over factory-primer grey. ONE indicator light is shaped like a "
        "SMILE that is almost convincing. Many small auxiliary cables "
        "fan out chaotically. Bright cream paper. The AI looks earnestly "
        "delighted by its own existence; that delight is also somewhat "
        "alarming."
    ),
    "core__BULWARK-9": (
        "Scene: a PORTRAIT of a server-rack AI named BULWARK-9 — SQUAT, "
        "wide stance, visibly armored: STEEL GIRDERS reinforce the rack's "
        "frame, COBALT-BORDERED warning chevrons painted around its edges. "
        "Indicator-LEDs are few but BRIGHT YELLOW (the deadliest color). "
        "Cables exit in armored conduits. Weathered olive-grey paper. The "
        "AI reads as a defensive position — bunker more than thinker."
    ),
    "core__SUBROUTINE-α": (
        "Scene: a PORTRAIT of a server-rack AI named SUBROUTINE-α — HALF-"
        "DISASSEMBLED, its own access panels OPEN, internal modules exposed "
        "with hand-written annotations in CIRCUIT-TEAL ink visible on the "
        "interior surfaces. The AI is editing itself in real time. Small "
        "tool-arms (its own, presumably) reach back into the open chassis. "
        "Cool blue-grey paper. The portrait feels recursive — a thing "
        "tinkering with the thing that is doing the tinkering."
    ),
    "core__Affection.exe": (
        "Scene: a PORTRAIT of a server-rack AI named Affection.exe — the "
        "SMALLEST core, painted in MAGENTA-PINK-AND-CHROME, with a single "
        "HEART-SHAPED status light glowing faintly in the centre. Cables "
        "exit downward in a careful loop, like a held breath. Bright cream "
        "paper with faint dotted decorative borders. The AI is trying very "
        "hard — you can tell from how neatly all the wires are routed."
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
    # Fallbacks if archetype is missing (shouldn't happen for CLAN).
    "chassis": _CHASSIS_FLAVORS["chassis__neutral"],
    "weapon": _WEAPON_FLAVORS["weapon__neutral"],
    "add_on": _ADD_ON_FLAVORS["add_on__neutral"],
    "transient": _TRANSIENT_FLAVORS["transient__neutral"],
    "structure": _STRUCTURE_FLAVORS["structure__neutral"],
    "core": _CORE_FLAVORS["core__FORGE-Δ"],  # last-resort default
    "object": (
        "Scene: a workshop-floor industrial artifact in the same lighting "
        "register — weathered, technical, ink-and-rivet on plain paper."
    ),
}


# ---------------------------------------------------------------------------
# Per-card classification — maps a card to its flavor key
# ---------------------------------------------------------------------------

def _archetype_tag(card: Any) -> str:
    """Read the card's archetype, normalised. Returns one of: brick / control /
    swarm / artillery / neutral."""
    arch = (getattr(card, "clankers_archetype", None) or "neutral").lower().strip()
    if arch not in ("brick", "control", "swarm", "artillery", "neutral"):
        arch = "neutral"
    return arch


def categorize(card: Any) -> str:
    """Map a CardDefinition to a CATEGORY_FLAVORS key.

    For Cores: returns ``core__<exact name>`` so each AI gets a bespoke flavor.
    For other types: returns ``<type>__<archetype>`` (e.g., ``chassis__brick``)
    so the same type renders with archetype-specific palette and composition.
    Falls back to ``<type>`` or ``object`` if anything's missing.
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
        # Bespoke per-core flavor; exact name match.
        bespoke_key = f"core__{card.name}"
        if bespoke_key in CATEGORY_FLAVORS:
            return bespoke_key
        return "core"

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
