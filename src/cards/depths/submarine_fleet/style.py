"""
Per-set art-style configuration for SUBS (depths set 1, submarine fleet).

v2: deliberate de-homogenization. v1's prompts pushed every single card
toward "submarine in 3/4 underwater profile, sodium-lit, sonar arcs"
because the headline over-prescribed the camera + lighting and the
category buckets were too coarse (one 'vessel' bucket for U-boats,
drones, carriers, crawler-probes, surface boats — all the same 41
cards painting the same picture).

Set identity stays — palette, medium, naval-WWII anchor, oil-on-canvas
register, cold/wet/painterly. Compositions vary per card via:

  * subject sub-bucketing (uboat vs drone vs carrier vs surface_boat
    vs crawler vs infrastructure; torpedo vs deck_gun vs instrument vs
    launcher; etc.)
  * compositional rotation seeded by card-name hash, so the same
    subject card in different decks looks materially different
  * named-boss bespoke flavors (Dönitz ≠ Yamamoto ≠ Black Demon X-7)
"""

from __future__ import annotations

import hashlib
from typing import Any


STYLE_HEADLINE = (
    "Visual register: WWII Kriegsmarine reconnaissance plates and high-"
    "budget deep-sea documentary cinematography, leaning toward Magic: The "
    "Gathering's painterly card-art tradition where the card's named "
    "subject is a SUGGESTION rather than a literal depiction. Aftermath "
    "scenes, reaction-shots of bystanders, detail close-ups of hands or "
    "instruments, and atmospheric environmental pieces are all in-bounds. "
    "Medium: oil-on-canvas painterly with photographic grain — reject "
    "anime, cartoon, super-deformed, pastel, or crisp digital concept-art "
    "glow. Color palette: deep ultramarine and abyssal black, oxidised "
    "brass and rust-orange, sodium-yellow interior glow, sonar cyan as "
    "accent, salt-stained off-white. Tone: cold, wet, oppressive, weighty. "
    "NO text, NO logos, NO card frame, NO borders, NO stat numbers — "
    "illustration only."
)


# =============================================================================
# Category flavors — granular subject + framing per card
# =============================================================================
#
# Naming convention: <bucket>__<subject>__<framing>
# Each line is the *complete* second paragraph for a card in that bucket;
# the headline above provides the global style anchor and these provide
# the specific subject and camera.
#
# Per-card rotation: categorize() picks one framing per subject using
# hash(card.name) % len(framings_for_that_subject), so output is
# deterministic across reruns but compositions rotate across the set.

VESSEL_FRAMINGS: dict[str, list[str]] = {
    "uboat": [
        "Scene: a single U-boat, surfaced at night, conning tower "
        "silhouetted against thin moonlight, salt foam at the bow waterline, "
        "low horizon, cinematic broadside profile.",
        "Scene: a single U-boat seen from BELOW, looking up through "
        "dark water at its keel and propeller wash; the viewer is the prey. "
        "Vertical light shafts cut through plankton suspension.",
        "Scene: a 1942 Office-of-Naval-Intelligence cutaway plate of "
        "a U-boat — internal compartments visible (torpedo room, control room, "
        "diesel pen), painterly cross-section, technical register.",
        "Scene: a U-boat running silent at periscope depth, broadside "
        "underwater view, bubbles trailing the props, a single warm sodium glow "
        "leaking from the hull seams.",
        "Scene: a U-boat in dry-dock at dawn, scaffolding overhead, "
        "tiny crew figures around the keel for scale, oil-canvas painterly.",
        "Scene: a U-boat surfacing bow-on through a breaking wave, "
        "foam violent across the deck, low dramatic angle.",
    ],
    "drone": [
        "Scene: a small unmanned underwater drone, mid-water, with a "
        "swarm of identical units in echelon formation receding behind it. Hive "
        "logistics, painterly haze.",
        "Scene: a single unmanned drone-craft on a clean dark field, "
        "technical-diagram register — brass fins, sensor blister, prop ring, "
        "contact horns visible — a specimen plate.",
        "Scene: an unmanned drone-craft mid-launch from the rail of "
        "a tender ship, motion-blurred, splash arc behind, deck markings under-"
        "foot.",
        "Scene: an unmanned drone resting in its pen — cradle, cable "
        "umbilical, dripping, sodium pen-light, a single crewman's silhouette "
        "for scale.",
    ],
    "carrier": [
        "Scene: a flat-deck aircraft carrier at dawn, strike planes "
        "spotted on deck, escorts at distance, painterly oil-paint sky.",
        "Scene: an aircraft carrier seen from BELOW at periscope "
        "depth — vast hull silhouette overhead, propeller wash trailing into "
        "deeper blue.",
        "Scene: cathedral-scale view of a carrier from a destroyer's "
        "bridge — tiny figures on its flight deck establish scale, painterly "
        "foreground crew at the bridge wing.",
    ],
    "surface_boat": [
        "Scene: a fast surface combatant — PT-boat / patrol craft / "
        "frigate — at full speed across choppy water, bow-wave high, gunner at "
        "station, wet weather.",
        "Scene: a surface raider craft seen at the waterline, low "
        "aggressive 3/4 angle, chipped naval grey hull, foam at the bow.",
        "Scene: an aerial recon-photo plate of a surface craft "
        "carving a long white wake across dark water — the wake itself is the "
        "subject as much as the boat.",
        "Scene: a surface craft at night under tracer fire, muzzle "
        "flashes lighting the hull, dramatic chiaroscuro.",
    ],
    "crawler": [
        "Scene: a bottom-walking abyssal probe on the sea floor, "
        "sediment plume around its legs, twin lamp-cones cutting silt, kelp "
        "and bone-coral fringing the frame.",
        "Scene: an isolated specimen plate of a crawler-probe on a "
        "black field — articulated leg detail, antenna and sensor cluster "
        "cataloged like a museum render.",
        "Scene: a crawler-probe from the rear, retreating into total "
        "abyssal blackness, twin running lights as the only illumination.",
    ],
    "infrastructure": [
        "Scene: a moored deep-water installation — listening post, "
        "underwater pylon, cable junction — kelp-strung anchors, single sodium "
        "beacon, no human figure.",
        "Scene: the installation rendered as a heraldic chart-table "
        "symbol with bearing lines fanning out from it, painterly map register.",
    ],
}

WEAPON_FRAMINGS: dict[str, list[str]] = {
    "torpedo": [
        "Scene: a torpedo mid-loading into its tube — brass fittings "
        "catching sodium light, stencil markings on the warhead, gloved hands "
        "at the rails.",
        "Scene: a torpedo running through dark water — corkscrew "
        "propeller wake, glowing wire-guidance filament trail, bubbles "
        "streaming.",
        "Scene: a stacked rack of torpedoes inside the bow "
        "compartment of a sub — low ceiling, oil drips, chain hoists overhead.",
    ],
    "launcher": [
        "Scene: a deck-mounted launcher / catapult in firing "
        "position — heavy recoil column, gun crew braced, salt spray over the "
        "muzzle.",
        "Scene: a swivel catapult rail extended over the deck, an "
        "unmanned drone-craft hung on it ready for launch, flight-deck "
        "markings underfoot.",
    ],
    "instrument": [
        "Scene: a navy munitions / instruments catalog plate — "
        "single device (periscope head, cathode tube, sonar transducer, "
        "depth-charge fuse) on a flat technical register, no human figure.",
        "Scene: the instrument in use — operator's gloved hands on "
        "the eyepiece / dial / control wheel, dim red emergency interior "
        "lighting, the device dominating the foreground.",
    ],
    "armor_fitting": [
        "Scene: a hull armor plate or pressure fitting being lowered "
        "into place by a deck crane — sparks, scaffolding, salt-stained metal.",
    ],
}

ACTION_FRAMINGS: dict[str, list[str]] = {
    "strike": [
        "Scene: a torpedo wake closing on a steel hull, water boiling at the "
        "impact line — frozen one second before contact.",
        "Scene: AFTERMATH — debris field on a glass-calm sea at dawn, an "
        "oil slick spreading, a single life-preserver bobbing. The strike "
        "happened off-frame and hours ago; the ocean is the subject.",
        "Scene: REACTION SHOT — a sonar operator's face, headphones on, "
        "lit only by his green scope, eyes wide in the instant a hit "
        "registers. The strike is implied entirely by his expression.",
        "Scene: DETAIL close-up — a brass shell-casing rolling on a wet "
        "deck, distant smoke columns out of focus on the horizon. The "
        "strike is in the background; the small thing is the subject.",
        "Scene: top-down chart view of a saturation salvo — bearing lines "
        "radiating from below toward a convoy. Map register, painterly.",
    ],
    "dock_scene": [
        "Scene: a night dockyard — sub at rest, crew unloading depleted "
        "ordnance, sodium dock-lights, weathered dry-dock timbers.",
        "Scene: DETAIL — a sailor's wet boot on a coiled mooring line, the "
        "sub's hull rising out of frame above. Small human element, vast "
        "implied scale.",
        "Scene: a refit yard at dawn — scaffolding around a hull, welders' "
        "sparks, a chart of damage pinned to a board.",
        "Scene: ATMOSPHERIC — empty dry-dock at dusk, the sub gone, only "
        "blocking timbers and oil stains remaining on the wet floor.",
    ],
    "command_room": [
        "Scene: a command room interior — captain at the chart table, brass "
        "instruments, headset operators in foreground, single chart-light "
        "overhead.",
        "Scene: DETAIL — a chart-table top-down with grease-pencil bearings, "
        "scale rule, dividers, a hand pinning a marker to a position.",
        "Scene: REACTION SHOT — a young helmsman gripping the wheel, knuckles "
        "white, lit by a single overhead bulb. Whatever the order is, "
        "his face holds it.",
        "Scene: ATMOSPHERIC — an empty command room between watches, sodium "
        "lamps still on, an unattended chart table mid-plot, headset hung "
        "over a brass railing.",
    ],
    "signals": [
        "Scene: a radio room — operator at the code key, sodium scope glow, "
        "paper tape spilling out — the 'ALL UNITS' moment.",
        "Scene: DETAIL — a length of paper code-tape spilling from a brass "
        "machine onto a steel deck, lit by a single sodium lamp.",
        "Scene: a recall-flag run up a halyard against an overcast sky — "
        "naval signal flags painterly, no human figure.",
        "Scene: REACTION SHOT — a radioman closing his eyes for a second "
        "after receiving a transmission, headphones still on, paper tape "
        "still feeding into the spool.",
    ],
    "surface_chase": [
        "Scene: a surface combatant under full ahead chasing a low silhouette "
        "across moonlit water, tracer arcs in the dark.",
        "Scene: REACTION SHOT — a deck gunner's face under a tin helmet in "
        "the muzzle flash, salt water on his cheeks, eyes locked on a "
        "distant target out of frame.",
        "Scene: ATMOSPHERIC — searchlight beams sweeping empty fog, the "
        "chase implied but the prey unseen. Negative space and beam-cone.",
        "Scene: aerial recon plate — two wakes converging across dark water, "
        "framed top-down, painterly chart register.",
    ],
    "emergency": [
        "Scene: a crash-dive INSIDE the boat — alarm horn red light, crew "
        "sliding down the ladder, water already spraying down the hatch.",
        "Scene: REACTION SHOT — a chief engineer braced against a bulkhead, "
        "wrench still in hand, looking up as light fixtures swing — the "
        "depth-charge attack happening above is implied entirely through him.",
        "Scene: DETAIL — knuckles white on a brass valve handle, beads of "
        "condensation on overhead pipes, a single drop of water trembling "
        "loose just before it falls.",
        "Scene: ATMOSPHERIC — a depth gauge needle creeping past a red "
        "marker, sweat-blurred glass, the rest of the boat out of focus.",
    ],
    "wolfpack_action": [
        "Scene: three converging subs on a tactical chart-plot, triangulated "
        "bearings drawn over a sea chart, command-room map register.",
        "Scene: three U-boat silhouettes underwater in echelon approaching a "
        "target line, painterly perspective.",
        "Scene: ATMOSPHERIC — a single periscope view through dark water of "
        "two distant mast-heads on the horizon, the third pack-mate implied "
        "but unseen.",
        "Scene: REACTION SHOT — a captain on his bridge wing watching distant "
        "smoke columns rise — three of them — without expression.",
    ],
    "kamikaze": [
        "Scene: a single suicide-craft mid-dive on a hull, seen from the deck "
        "of the target as the gunner reacts.",
        "Scene: REACTION SHOT — a young pilot's face inside a cockpit, "
        "instrument glow on his cheekbones, the target only a reflection in "
        "his goggles.",
        "Scene: AFTERMATH — a smoking gash in a battleship's hull, water "
        "pouring in, deck crews running. The sacrificing craft is gone.",
        "Scene: DETAIL — a pilot's hand on a throttle pushed all the way "
        "forward, a small photograph wedged into the instrument panel.",
    ],
    "decisive_moment": [
        "Scene: a decisive moment from the campaign — escape hatch slamming "
        "shut, rudder hard over, sonar pulse blooming. Cinematic.",
        "Scene: ATMOSPHERIC — a single shaft of light cutting through dark "
        "water onto a hull, no human, no action, just weight and pressure.",
        "Scene: DETAIL — a hand on a brass voice-pipe, the mouth open about "
        "to give an order, the action itself off-frame.",
        "Scene: AFTERMATH — a war diary open on a steel desk, fresh ink "
        "scrawl, a still-smoking pipe in the foreground.",
    ],
}

CREW_FRAMINGS: list[str] = [
    "Scene: an engineer in the engine room — hot pipes, oil-stained "
    "overalls, single yellow lamp from above, wrench in hand.",
    "Scene: an officer at the bridge — charts and dividers in front, "
    "headset cocked, sodium lamp on the table, steel ribbed wall behind.",
    "Scene: a sailor on deck in heavy weather — oilskin hood up, "
    "salt spray, low horizon, daylight (NOT interior).",
    "Scene: a gunner at the breech of a deck gun — brass shell case "
    "in hand, salt residue on the gun shield.",
    "Scene: a radio / sonar operator at his green-lit scope — "
    "headphones, hand on the dial, dim stateroom.",
    "Scene: a young pilot in flight gear — helmet under arm, framed "
    "against an aircraft hangar with a strike bomber spotted behind.",
    "Scene: a drone tech crouched beside an unmanned craft in the "
    "pen — calipers in hand, cable-runs everywhere, sodium pen-light.",
    "Scene: a deck officer at the conning-tower rail in a peaked "
    "cap, weather coat collar up, watching the horizon through binoculars.",
]

DOCTRINE_FRAMINGS: list[str] = [
    "Scene: 1940s heraldic propaganda-poster register — bold "
    "composition, naval ensigns, stencil text only IMPLIED (DO NOT render "
    "legible letters), flat painterly fields, faces in shadow.",
    "Scene: a command-room map table — pencil-marked sea chart, "
    "grease-pencil bearings, scale rule, dim chart-light.",
    "Scene: a naval ensign and ribbon arrangement against a dim "
    "deck scene, dramatic banner, heraldic painterly register.",
    "Scene: a recruiting-poster register — silhouette of a sailor "
    "against a giant ensign, dramatic backlight.",
    "Scene: a ship's captain at the bridge issuing orders, low "
    "angle, ensign visible behind — the doctrine as a leadership moment.",
]

MINE_FRAMINGS: list[str] = [
    "Scene: a spherical contact mine moored in mid-water, contact "
    "horns silhouetted, kelp-strung anchor cable rising from below.",
    "Scene: a free-floating mine at the surface line — half above "
    "water, half below, riding chop, dim moonlight on the horns.",
    "Scene: a magnetic mine on silty seabed, exposed coil casing, "
    "ghostly sediment plume.",
    "Scene: an acoustic decoy buoy adrift — small drum-shaped "
    "device, kelp-tangled, transmitter dish above the waterline.",
]

FLAGSHIP_FRAMINGS: list[str] = [
    "Scene: a cathedral-scale capital vessel at periscope depth "
    "seen from below, silhouetted against thin surface light. Slow, "
    "monolithic, untouchable — flag pennants, rivet courses, bow waves.",
    "Scene: a flagship surfaced at dawn with two escort silhouettes "
    "at distance — painterly horizon, dramatic side-on profile, full "
    "cinematic register.",
]

# Bespoke per-name flavors for the named legendary bosses.
NAMED_BOSS_FLAVORS: dict[str, str] = {
    "Admiral Dönitz": (
        "Scene: portrait of Admiral Karl Dönitz — German Kriegs-"
        "marine commander in winter coat with naval cap, charts spread on "
        "a U-boat command-room table, dark oak panelling, single overhead "
        "lamp. Cold, calculating, painterly oil register."
    ),
    "Fleet Admiral Yamamoto": (
        "Scene: portrait of Fleet Admiral Yamamoto on the bridge "
        "of a battleship, framed against the gloom of an anti-aircraft gun "
        "turret, IJN dress whites, painterly oil register."
    ),
    "Black Demon X-7": (
        "Scene: a stealth super-submarine — jet-black anechoic-"
        "tile hull, only a single sonar arc revealing its outline against "
        "deep water. Almost invisible, the absence-of-form is the subject."
    ),
    "Triton-Class": (
        "Scene: a Triton-class flagship sub — vast nuclear-era "
        "successor to the U-boat, escort drones in formation around its "
        "hull, scale established by the tiny escorts."
    ),
}


# =============================================================================
# Flat CATEGORY_FLAVORS — what art_harness.py actually consumes
# =============================================================================
#
# We assemble a flat dict mapping bucket-key → flavor string. categorize()
# returns one of these keys. Per-card rotation happens inside categorize.

CATEGORY_FLAVORS: dict[str, str] = {}

for _subject, _framings in VESSEL_FRAMINGS.items():
    for _i, _f in enumerate(_framings):
        CATEGORY_FLAVORS[f"vessel__{_subject}__{_i}"] = _f
for _subject, _framings in WEAPON_FRAMINGS.items():
    for _i, _f in enumerate(_framings):
        CATEGORY_FLAVORS[f"weapon__{_subject}__{_i}"] = _f
for _subject, _framings in ACTION_FRAMINGS.items():
    for _i, _f in enumerate(_framings):
        CATEGORY_FLAVORS[f"action__{_subject}__{_i}"] = _f
for _i, _f in enumerate(CREW_FRAMINGS):
    CATEGORY_FLAVORS[f"crew__{_i}"] = _f
for _i, _f in enumerate(DOCTRINE_FRAMINGS):
    CATEGORY_FLAVORS[f"doctrine__{_i}"] = _f
for _i, _f in enumerate(MINE_FRAMINGS):
    CATEGORY_FLAVORS[f"mine__{_i}"] = _f
for _i, _f in enumerate(FLAGSHIP_FRAMINGS):
    CATEGORY_FLAVORS[f"flagship__{_i}"] = _f
for _name, _flavor in NAMED_BOSS_FLAVORS.items():
    CATEGORY_FLAVORS[f"named_boss__{_name}"] = _flavor

# Fallback bucket if nothing else matches.
CATEGORY_FLAVORS["object"] = (
    "Scene: a submarine-warfare artifact in the same lighting "
    "register — weathered, technical, painterly oil-on-canvas."
)


# =============================================================================
# Per-card subject classification + rotation
# =============================================================================

def _name_hash(name: str, mod: int) -> int:
    """Deterministic name → small int, stable across reruns."""
    return int(hashlib.sha256(name.encode("utf-8")).hexdigest(), 16) % mod


def _classify_vessel(name: str, subtypes: set, keywords: set) -> str:
    n = name.lower()
    if "drone" in n or "drone" in {s.lower() for s in subtypes}:
        return "drone"
    if "carrier" in n or "Carrier" in subtypes:
        return "carrier"
    if any(k in n for k in ("crawler", "probe", "bottom")):
        return "crawler"
    if any(k in n for k in ("listening post", "post", "buoy", "pylon", "pen")):
        # 'pen' appears in 'Drone Pen Mate' which is a crew, not vessel; this
        # path only hits when classify_vessel is called on a DEPTHS_VESSEL
        return "infrastructure"
    if any(k in n for k in ("boat", "frigate", "cruiser", "patrol bomber", "raider",
                              "skirmisher", "cutter", "corvette")):
        return "surface_boat"
    if "carrier" in n:
        return "carrier"
    return "uboat"


def _classify_weapon(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("torpedo", "tube", "spread", "salvo", "warhead")):
        return "torpedo"
    if any(k in n for k in ("catapult", "launcher", "rail")):
        return "launcher"
    if any(k in n for k in ("periscope", "cathode", "transducer", "sonar",
                              "fuse", "sensor", "sextant")):
        return "instrument"
    if any(k in n for k in ("plate", "armor", "fitting", "hull")):
        return "armor_fitting"
    return "torpedo"  # default


def _classify_action(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("kamikaze", "last stand", "suicide")):
        return "kamikaze"
    if any(k in n for k in ("wolfpack", "pack tactic", "wolf at")):
        return "wolfpack_action"
    if any(k in n for k in ("crash dive", "emergency", "blow ballast",
                              "depth charge", "hold breath", "brace")):
        return "emergency"
    if any(k in n for k in ("recall", "broadcast", "decode", "signal", "order",
                              "dispatch", "communique")):
        return "signals"
    if any(k in n for k in ("refit", "reload", "dock", "repair", "refuel",
                              "rearm", "tender")):
        return "dock_scene"
    if any(k in n for k in ("plan", "doctrine", "command", "directive",
                              "logbook", "chart")):
        return "command_room"
    if any(k in n for k in ("chase", "pursuit", "raid", "skirmish", "crash-boat",
                              "intercept")):
        return "surface_chase"
    if any(k in n for k in ("strike", "salvo", "volley", "saturation", "barrage",
                              "torpedo", "hit", "blow", "bombard", "kill")):
        return "strike"
    return "decisive_moment"


def categorize(card: Any) -> str:
    """Map a CardDefinition to a CATEGORY_FLAVORS key, with rotation.

    Same card name always returns the same bucket (deterministic). Different
    cards in the same logical category get rotated through alternate
    framings via name hash.
    """
    try:
        from src.engine.types import CardType
    except Exception:
        return "object"

    chars = getattr(card, "characteristics", None)
    if not chars:
        return "object"

    name = card.name
    types = getattr(chars, "types", set()) or set()
    subtypes = getattr(chars, "subtypes", set()) or set()
    keywords = getattr(chars, "keywords", set()) or set()
    if not isinstance(keywords, (set, frozenset, list)):
        keywords = set()
    keywords = set(keywords)

    is_legendary = "Legendary" in subtypes or "Legend" in subtypes

    # Bespoke named-boss buckets short-circuit everything else.
    if name in NAMED_BOSS_FLAVORS:
        return f"named_boss__{name}"

    if CardType.DEPTHS_VESSEL in types:
        if "Flagship" in subtypes:
            n = len(FLAGSHIP_FRAMINGS)
            return f"flagship__{_name_hash(name, n)}"
        # Legendary non-flagship: route into the named-boss bespokes by name
        # if available, else into uboat with a special framing index. We've
        # already short-circuited if name is in NAMED_BOSS_FLAVORS above.
        subject = _classify_vessel(name, subtypes, keywords)
        framings = VESSEL_FRAMINGS.get(subject, VESSEL_FRAMINGS["uboat"])
        return f"vessel__{subject}__{_name_hash(name, len(framings))}"

    if CardType.DEPTHS_CREW in types:
        return f"crew__{_name_hash(name, len(CREW_FRAMINGS))}"

    if CardType.DEPTHS_WEAPON in types:
        subject = _classify_weapon(name)
        framings = WEAPON_FRAMINGS.get(subject, WEAPON_FRAMINGS["torpedo"])
        return f"weapon__{subject}__{_name_hash(name, len(framings))}"

    if CardType.DEPTHS_MINE in types:
        return f"mine__{_name_hash(name, len(MINE_FRAMINGS))}"

    if CardType.ENCHANTMENT in types:
        return f"doctrine__{_name_hash(name, len(DOCTRINE_FRAMINGS))}"

    if CardType.INSTANT in types or CardType.SORCERY in types:
        subject = _classify_action(name)
        framings = ACTION_FRAMINGS.get(subject, ACTION_FRAMINGS["decisive_moment"])
        return f"action__{subject}__{_name_hash(name, len(framings))}"

    return "object"
