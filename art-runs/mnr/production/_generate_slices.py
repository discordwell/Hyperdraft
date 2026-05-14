#!/usr/bin/env python3
"""Generate MNR slice packet JSON files from per-card creative metadata.

This script is the source-of-truth for MNR slice generation. Run once and
commit the resulting slice-NN-packets.json files. The validator at
`validate_packets.py` checks the emitted JSON for schema compliance.

The CARDS dict below holds the bespoke creative writing for all 120 MNR
cards (location, action, focus, mood, artist reference, palette accent).
The rest of the packet is rendered by `_render_packet()` consistent with
the SCP slice-01 format.
"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "frontend/public/scp_art_manifest.json"

NEGATIVE_PROMPT = (
    "No readable words, letters, numbers, official SCP logo, Magic card frame, "
    "mana symbols, stat boxes, watermark, UI overlay, caption, title text, "
    "signature, copied source composition, exact artist imitation, comic "
    "mascot tone, clean spaceship aesthetic, repeated centered hallway monster."
)

SETTING_FACTION = "Mnestic Reset / The Antimemetics Division"

# Composition rotation labels and the short note appended in final_prompt.
# The five primary MNR modes are Detail, Wide, Aftermath, Witness POV,
# and Anomaly Implied (per the MNR style packet). Reaction and Action
# are carried over from the SCP base composition rotation for cards
# whose subject is human-posture-foregrounded or motion-staged.
COMP_NOTE = {
    "Detail": "tight foreground prop or hands with the wider antimemetic context implied behind it",
    "Wide": "institutional space dwarfing the human, scale tells the story",
    "Aftermath": "the motion is already past; the evidence remains in a still frame",
    "Witness POV": "camera occupies an observer's position behind glass / through a door / over a shoulder",
    "Anomaly Implied": "the strange thing is barely visible, a shadow without caster or a reflection that does not match",
    "Reaction": "human posture foregrounded, the antimemetic situation read through the figure's response",
    "Action": "dynamic diagonal staging, motion of bureaucratic or operational discipline readable at card size",
}

# Card-type direction lines (mirrors SCP packet phrasing, MNR-tuned)
TYPE_DIRECTION = {
    "SCP_ANOMALY": (
        "show the anomaly's consequence or implication with antimemetic restraint, "
        "favoring absence and witness over centered monster reveal"
    ),
    "SCP_PERSONNEL": (
        "show role under pressure through hands, posture, gear, and environment, "
        "not a passport portrait"
    ),
    "SCP_FACILITY": (
        "show an institutional space doing its job, with architecture and staff "
        "scale making the operational function legible"
    ),
    "SCP_PROCEDURE": (
        "show an operational action, procedural detail, or its consequence as a "
        "single readable moment"
    ),
    "SCP_MANDATE": (
        "show directive-level imagery as physical residue (memo, empty desk, "
        "lectern, sealed door); witness POV preferred to centered authority"
    ),
}


# Artist reference catalog. Each entry: (title, url, traits)
REFS = {
    "hopper_nighthawks": (
        "Edward Hopper, Nighthawks",
        "https://www.artic.edu/artworks/111628/nighthawks",
        "warm window light against night exterior, isolated figures in late-hours interior, geometric architectural framing, hard-edge realism, fluorescent green-yellow palette, civic loneliness",
    ),
    "hopper_office": (
        "Edward Hopper, Office at Night",
        "https://collections.walkerart.org/object/1599",
        "single overhead lamp on a paper desk, two figures in mid-task with implied tension, austere institutional geometry, green-shaded fluorescent palette, isolation inside a working room",
    ),
    "hopper_new_york_office": (
        "Edward Hopper, New York Office",
        "https://www.mfah.org/art/detail/27543",
        "tall vertical office windows framing a single figure mid-task, daylight cutting institutional interior, restrained civic palette, the city as observer, painterly stillness",
    ),
    "hopper_automat": (
        "Edward Hopper, Automat",
        "https://desmoinesartcenter.org/explore/collection/edward-hopper-automat/",
        "single figure under a single lamp in a public-but-empty interior, paper-cup quietude, ceiling rhythm, dark window reflecting nothing, hushed urban solitude",
    ),
    "hammershoi_interior": (
        "Vilhelm Hammershoi, Interior with Young Woman Seen from Behind",
        "https://www.smb.museum/en/museums-institutions/nationalgalerie/collection/",
        "muted gray-on-gray interior palette, figure with back turned, doorways into more empty rooms, soft northern window light, quiet domestic gravity",
    ),
    "hammershoi_dust_motes": (
        "Vilhelm Hammershoi, Dust Motes Dancing in the Sunbeams",
        "https://www.ordrupgaard.dk/en/the-collection/",
        "diagonal sunlight across an empty floor, dust suspended in stillness, gray panelled walls, austere domestic absence, painterly hush",
    ),
    "wyeth_christina": (
        "Andrew Wyeth, Christina's World",
        "https://www.moma.org/collection/works/78455",
        "single figure on dry ground looking toward a distant building, low horizon, sun-baked muted palette, the act of looking as the entire subject, anxious patience",
    ),
    "wyeth_wind_from_sea": (
        "Andrew Wyeth, Wind from the Sea",
        "https://www.nga.gov/artworks/52199-wind-sea",
        "thin curtain lifting at an upstairs window, dry-board interior, a glimpse of land beyond, near-monochrome cream-gray-brown palette, breath-held interior",
    ),
    "rothko_field": (
        "Mark Rothko, No. 14, 1960",
        "https://www.sfmoma.org/artwork/98.308/",
        "stacked color fields with soft horizontal edges, ambient depth without depicted object, palette as composition, contemplative absence, monumental quiet",
    ),
    "wall_insomnia": (
        "Jeff Wall, Insomnia",
        "https://www.tate.org.uk/art/artworks/wall-insomnia-p20198",
        "staged-bureaucratic kitchen interior under fluorescent ceiling, figure on the floor in mid-narrative pause, large-format constructed scene, theatrical realism, banal horror",
    ),
    "wall_view_apartment": (
        "Jeff Wall, A View from an Apartment",
        "https://www.tate.org.uk/art/artworks/wall-a-view-from-an-apartment-t12446",
        "ordinary interior with quiet domestic action and a window onto larger urban indifference, constructed realism, daylight palette, observed banality",
    ),
    "crewdson_pines": (
        "Gregory Crewdson, Cathedral of the Pines",
        "https://www.gagosian.com/exhibitions/2016/gregory-crewdson-cathedral-of-the-pines/",
        "cinematic single-figure interior tableau, lighting designed like a film set, suburban dread, painterly photographic depth, narrative pause",
    ),
    "crewdson_beneath_roses": (
        "Gregory Crewdson, Beneath the Roses",
        "https://www.gagosian.com/exhibitions/2008/gregory-crewdson-beneath-the-roses/",
        "wide street-or-interior tableau under heavy artificial lighting, single figure in mid-pause, cinematic narrative ambiguity, painterly photographic palette",
    ),
    "friedrich_wanderer": (
        "Caspar David Friedrich, Wanderer above the Sea of Fog",
        "https://www.kunsthalle-hamburg.de/de/sammlung-online/",
        "solitary figure seen from behind looking out at what they cannot understand, the witness composition, atmospheric depth, mid-tone gray palette, sublime restraint",
    ),
    "friedrich_monk": (
        "Caspar David Friedrich, The Monk by the Sea",
        "https://www.smb.museum/en/museums-institutions/alte-nationalgalerie/",
        "tiny single figure against an immense empty horizon, three flat horizontal bands, scale through absence, somber palette, the witness reduced to a mark",
    ),
    "freud_self": (
        "Lucian Freud, Reflection (Self-Portrait)",
        "https://www.npg.org.uk/collections/search/portrait/",
        "fluorescent-flesh portraiture, unflattering institutional skin tones, thickly-built paint surface, exhausted under hard light, posture-as-subject",
    ),
    "freud_benefits": (
        "Lucian Freud, Benefits Supervisor Sleeping",
        "https://www.christies.com/lot/lot-5071290/",
        "monumental interior figure under bare-bulb light, institutional weight, paint applied as worn upholstery, posture of exhaustion, civic flesh",
    ),
    "whiteread_house": (
        "Rachel Whiteread, House",
        "https://www.tate.org.uk/art/artworks/whiteread-house-t06829",
        "cast of an empty interior as solid object, absence rendered as form, gray concrete monumentality, negative space made tangible, civic memorial silence",
    ),
    "whiteread_ghost": (
        "Rachel Whiteread, Ghost",
        "https://www.nga.gov/artworks/110341",
        "cast of a room's interior as a freestanding object, the empty space made physical, plaster monumentality, gray-white surface, absent presence",
    ),
    "de_maria_kilometer": (
        "Walter De Maria, The Broken Kilometer",
        "https://www.diaart.org/visit/visit/walter-de-maria-the-broken-kilometer",
        "repetitive identical bureaucratic objects arrayed in a long bright interior, scale through accumulation, museum-warehouse light, austere geometry, ritual repetition",
    ),
    "de_maria_earth": (
        "Walter De Maria, The New York Earth Room",
        "https://www.diaart.org/visit/visit/walter-de-maria-the-new-york-earth-room",
        "interior space fully filled with one substance, institutional white walls disrupted by mass material presence, quiet monumental displacement, single dominant texture",
    ),
    "calle_hotel": (
        "Sophie Calle, The Hotel",
        "https://www.perrotin.com/artists/Sophie_Calle/9",
        "forensic-archival photography of a stranger's belongings, the everyday catalogued under surveillance, paper-evidence palette, quiet voyeur composition, document-as-art",
    ),
    "magritte_empire": (
        "Rene Magritte, The Empire of Light",
        "https://www.moma.org/collection/works/78969",
        "ordinary suburban exterior under impossible simultaneous daylight and night, the surreal inserted into the banal without comment, smooth painterly surface, restrained palette, deadpan dread",
    ),
    "magritte_time": (
        "Rene Magritte, Time Transfixed",
        "https://www.artic.edu/artworks/34181/time-transfixed",
        "ordinary fireplace with an impossible object inserted as if always there, deadpan domestic-surreal, smooth illustrative surface, restrained palette",
    ),
    "bechtle_torino": (
        "Robert Bechtle, Alameda Gran Torino",
        "https://www.sfmoma.org/artwork/2005.139/",
        "harsh midday suburban light on a parked car, flat photographic-painterly realism, beige-and-asphalt palette, banal Americana made monumental",
    ),
    "bechtle_olds": (
        "Robert Bechtle, '56 Olds",
        "https://collections.lacma.org/node/231458",
        "flat suburban driveway under bright daylight, photographic-painterly realism, beige-and-stucco palette, banal stillness as subject",
    ),
    "shore_uncommon": (
        "Stephen Shore, U.S. 89, Arizona, June 1972",
        "https://www.moma.org/collection/works/47432",
        "color-photograph banal American interior or street, motel light, painterly photographic flatness, beige palette, the ordinary as evidence",
    ),
    "shore_meeting": (
        "Stephen Shore, Meeting Room",
        "https://www.303gallery.com/artists/stephen-shore",
        "fluorescent meeting-room interior, banal furniture, color-photograph realism, beige-and-monitor palette, institutional emptiness",
    ),
    "sargent_two_soldiers": (
        "John Singer Sargent, Two Soldiers at Arras",
        "https://www.imperialwarmuseums.org.uk/collections/item/object/16566",
        "two figures in service uniform in a worn interior, alla prima brushwork, muted palette, posture-of-duty composition, painterly restraint",
    ),
    "wright_air_pump": (
        "Joseph Wright of Derby, An Experiment on a Bird in the Air Pump",
        "https://www.nationalgallery.org.uk/paintings/joseph-wright-of-derby-an-experiment-on-a-bird-in-the-air-pump",
        "circle of witnesses around a central scientific apparatus, single dramatic light source, faces lit from below, somber palette, civic-experiment gravity",
    ),
    "saville_propped": (
        "Jenny Saville, Propped",
        "https://www.gagosian.com/artists/jenny-saville/",
        "monumental figure in a fluorescent-medical context, painterly flesh, thick surface, scale through close framing, institutional weight",
    ),
    "rembrandt_anatomy": (
        "Rembrandt, The Anatomy Lesson of Dr Nicolaes Tulp",
        "https://www.mauritshuis.nl/en/our-collection/artworks/146-the-anatomy-lesson-of-dr-nicolaes-tulp",
        "ring of witnesses around a central body on an institutional table, single warm light source, somber palette, civic-medical gravity, posture of professional attention",
    ),
    "degas_ironing": (
        "Edgar Degas, A Woman Ironing",
        "https://www.nga.gov/artworks/46640",
        "single working figure leaning into routine task, soft interior light, mid-tone palette, posture-as-subject, painterly grain of fatigue",
    ),
    "redon_eyes_closed": (
        "Odilon Redon, Eyes Closed",
        "https://www.musee-orsay.fr/en/artworks/les-yeux-clos-50066",
        "single closed-eyed face floating in soft atmospheric ground, contemplative dream-state palette, painterly veil, restrained surrealism",
    ),
    "daumier_clerks": (
        "Honore Daumier, Two Lawyers",
        "https://www.artic.edu/artworks/14569/two-lawyers",
        "two robed civic figures in mid-discussion, pen-and-ink graphic shorthand, compressed institutional space, anxious bureaucratic mood",
    ),
    "kollwitz_survivors": (
        "Kathe Kollwitz, The Survivors",
        "https://sammlung.staedelmuseum.de/en/work/the-survivors",
        "cluster of figures under a central protective gesture, charcoal-on-paper graphic weight, somber palette, civic grief, posture-of-protection composition",
    ),
    "tooker_bureau": (
        "George Tooker, Government Bureau",
        "https://www.metmuseum.org/art/collection/search/485874",
        "rows of identical clerks behind frosted-glass partitions in a fluorescent-lit bureaucratic interior, geometric architectural rhythm, muted institutional palette, civic anonymity, posture-of-clerks composition",
    ),
    "tooker_subway": (
        "George Tooker, The Subway",
        "https://whitney.org/collection/works/3137",
        "compressed institutional interior with figures lined up under fluorescent fixtures, geometric architectural framing, muted civic palette, posture of bureaucratic compliance, painterly anonymity",
    ),
    "fischl_birthday": (
        "Eric Fischl, Birthday Boy",
        "https://www.metmuseum.org/art/collection/search/489942",
        "interior figure under domestic-fluorescent light, painterly realism with psychological pressure, restrained color, posture-as-subject, narrative ambiguity",
    ),
    "register_open_diner": (
        "John Register, Open Diner",
        "https://americanart.si.edu/artwork/open-diner-66935",
        "empty institutional interior under flat fluorescent light, geometric architectural quiet, restrained beige-cream palette, banal-melancholy composition",
    ),
    "hopper_conference_night": (
        "Edward Hopper, Conference at Night",
        "https://collections.wichitaartmuseum.org/objects-1/info/85",
        "three figures in a sparsely-furnished interior under fluorescent light, geometric architectural framing, hard-edge realism, restrained civic palette, late-night working composition",
    ),
    "walker_evans_objects": (
        "Walker Evans, Penny Picture Display, Savannah",
        "https://www.moma.org/collection/works/49891",
        "grid-arrayed forensic photography of accumulated paper objects, documentary realism, paper-evidence palette, posture-of-record composition",
    ),
    "thiebaud_counter": (
        "Wayne Thiebaud, Bakery Counter",
        "https://americanart.si.edu/artwork/bakery-counter-22789",
        "row of identical institutional objects on a flat counter under cool overhead light, thick painterly surface, restrained palette, deadpan still-life composition",
    ),
    "vermeer_geographer": (
        "Johannes Vermeer, The Geographer",
        "https://www.staedelmuseum.de/en/collection/the-geographer-1668",
        "single working figure leaning over a desk by a tall window, soft side-light, restrained palette, posture-of-thinking composition, painterly stillness",
    ),
}

# === The Cards ===
# Each entry: name -> {composition, ref, location, action, focus, mood, palette, qa, note?}
# The 'note' field is an optional extra creative note that gets appended after Composition rotation in the final_prompt.
CARDS: dict[str, dict] = {
    # === ANOMALIES (24) ===
    "MNR Anniversary Ghost": dict(
        composition="Anomaly Implied",
        ref="tooker_bureau",
        location="a small open-plan office with three desks and a half-eaten sheet cake on a side table at 7:14pm",
        action="An empty rolling chair at the cake desk gently rocks itself as if someone unseen just stood up to leave a one-year-of-service party that nobody else can remember scheduling.",
        focus="the chair rocking by itself next to a half-eaten cake and an unblown candle",
        mood="commemorative dread, the office anniversary that no one attended",
        palette="fluorescent yellow-white over beige carpet, sheet-cake pink, and a thin antimemetic chartreuse accent on the candle wax",
        qa="verify the chair rocking reads as 'just-vacated' rather than 'malfunctioning'; the cake and candle do most of the storytelling.",
        note="leave a person-shaped negative space at the chair where a figure ought to be",
    ),
    "MNR Bystander Effect": dict(
        composition="Witness POV",
        ref="bechtle_torino",
        location="a cubicle interior in a non-divisional accounting office at 2:43pm on a Tuesday",
        action="A middle-aged civilian in a polo shirt looks calmly toward the cubicle wall, coffee cup half-raised, completely unaware of the antimemetic event already underway in the doorway behind their right shoulder.",
        focus="the bystander's calm uncomprehending face and the coffee cup mid-lift",
        mood="banal pre-mortem, the moment before being forgotten",
        palette="cubicle gray, polo-shirt beige, fluorescent ceiling white, and a thin antimemetic chartreuse on the bystander's name lanyard",
        qa="verify the bystander reads as 'ordinary coworker about to die without knowing' rather than as a menaced victim; he must look calm and slightly bored.",
        note="the anomaly is implied at the periphery, never centered or rendered",
    ),
    "MNR Cognitive Wedge": dict(
        composition="Detail",
        ref="calle_hotel",
        location="an analyst's desk in a windowless interior office",
        action="A single sheet of paper sits on a desk under fluorescent light, its center cut out in a perfect rectangle, the cut edges fresh and the missing rectangle nowhere in the room.",
        focus="the paper with the rectangular hole and the pen still resting on its edge",
        mood="precision absence, surgical forgetting",
        palette="desk-pine brown, paper cream, fluorescent overhead white, and a thin antimemetic chartreuse on a highlighter cap beside the page",
        qa="verify the cut-out hole reads as deliberate antimemetic excision rather than as a craft project; the edges are crisp, the absence is the subject.",
    ),
    "MNR Cognitive Wedge (Severe)": dict(
        composition="Aftermath",
        ref="hammershoi_interior",
        location="the same windowless office an hour later",
        action="The desk now bears five sheets of paper each missing a larger rectangle, stacked unevenly, the analyst's chair pushed back hard enough to mark the carpet, and no analyst.",
        focus="the stack of progressively-emptier pages and the dragged carpet behind the chair",
        mood="escalating excision, the wedge deepening",
        palette="cubicle gray, paper cream, carpet-mark beige, and a thin antimemetic chartreuse on a fallen pill bottle next to the chair leg",
        qa="verify the empty chair reads as 'the analyst was here ten minutes ago' rather than 'this office is closed for the day'; carpet drag is the timestamp.",
    ),
    "MNR Counter-Mnestic": dict(
        composition="Detail",
        ref="freud_self",
        location="a Foundation infirmary station with a paper drug cup on a stainless tray",
        action="A gloved hand tilts a translucent pill cup onto the palm of a senior analyst, three antimemetic-chartreuse capsules sliding out under a single overhead exam light.",
        focus="the gloved hand, the pill cup, and the three chartreuse capsules mid-fall",
        mood="dosed discipline, the routine of staying remembered",
        palette="exam-room white, stainless-tray steel, glove-blue, and antimemetic chartreuse on the capsule shells as the dominant tell",
        qa="verify the capsules are recognizably pharmaceutical (gelatine seam, clear-to-yellow split) rather than abstract pills; the chartreuse must read as 'pharmacy aisle' not 'sci-fi glow'.",
    ),
    "MNR Counter-Mnestic (Severe)": dict(
        composition="Aftermath",
        ref="hammershoi_dust_motes",
        location="the same infirmary an hour later, lights still on",
        action="The exam tray now holds an empty IV bag and a tipped pill cup, the chair beside it pushed askew, with a single chartreuse capsule rolled into the corner under a baseboard.",
        focus="the empty IV bag, the askew chair, and the lone chartreuse capsule in the corner",
        mood="depleted dosage, the second-line intervention spent",
        palette="exam-room white, sodium overhead, baseboard brown, and antimemetic chartreuse on the lone capsule and the IV-bag label",
        qa="verify the empty IV bag and tipped cup read as 'the dose was used in a hurry' rather than as a discarded medical mess; the lone capsule in the corner is the punctuation.",
    ),
    "MNR Filed-Away Window": dict(
        composition="Anomaly Implied",
        ref="hammershoi_interior",
        location="a corner of an analyst's office where a window ought to be on an outside wall",
        action="The plaster wall is unbroken and beige, but the carpet directly beneath it bears a sun-faded rectangular bleach where a window must have been for decades, with a radiator beneath the bleach as if remembering where to be.",
        focus="the sun-faded carpet rectangle and the radiator under nothing",
        mood="the room misses the window more than the room admits",
        palette="plaster beige, carpet brown, radiator off-white, and a thin antimemetic chartreuse on a forgotten pill blister on the radiator top",
        qa="verify the absent window reads as 'always was here' rather than 'recently bricked up'; the carpet bleach is the proof, not the wall.",
    ),
    "MNR Five and Three-Eighths": dict(
        composition="Detail",
        ref="bechtle_olds",
        location="an elevator panel in an interior lobby",
        action="A finger hovers over a brass elevator panel where the buttons read 4, 5, 6, 7 normally but a thinner unmarked button sits between 5 and 6, faintly etched with the fraction five-and-three-eighths.",
        focus="the hovering finger and the slim extra button between 5 and 6",
        mood="impossible numbering, the floor that math admits but the building denies",
        palette="brass panel, sodium-amber lobby light, dark cab carpet, and a thin antimemetic chartreuse on a building-directory sticker beside the panel",
        qa="verify the impossible button reads as a real-world panel ambiguity rather than a sci-fi prop; the etched fraction is the punchline, not a flashing light.",
    ),
    "MNR Locked Filing Cabinet": dict(
        composition="Detail",
        ref="walker_evans_objects",
        location="a row of identical four-drawer filing cabinets in a basement records room",
        action="One drawer in the center cabinet is missing entirely, leaving a perfectly square dark void at chest height, while the drawers above and below remain seated and labeled with smudged tape.",
        focus="the missing drawer's perfectly square absence between two intact drawers",
        mood="archival theft, the categorical excision",
        palette="cabinet beige, label-tape yellow, dust-motes amber, and a thin antimemetic chartreuse on a single pill capsule sitting in the dark void where the drawer ought to be",
        qa="verify the missing drawer reads as 'this drawer was never installed' rather than 'someone removed it for repair'; the chartreuse capsule inside is the antimemetic tell.",
    ),
    "MNR Memory Reef": dict(
        composition="Wide",
        ref="rothko_field",
        location="a long featureless interior corridor in the antimemetic wing",
        action="The corridor recedes into a wall of soft horizontal color bands that should be a far doorway, but the bands resolve into nothing concrete, a perceptual reef where memory of the geometry breaks against itself.",
        focus="the corridor receding into resolved-but-unreadable color bands",
        mood="perceptual ground giving way, the reef where remembering breaks",
        palette="corridor concrete gray, ceiling-tile white, navy baseboard, and antimemetic chartreuse as a thin band in the unresolved far wall",
        qa="verify the unresolved bands read as a perceptual failure rather than a paint job; this card uses Rothko as composition, not as decoration.",
    ),
    "MNR Memory Reef (Containment Critical)": dict(
        composition="Wide",
        ref="friedrich_monk",
        location="a containment-pressure corridor where the antimemetic anomaly has expanded",
        action="A single figure in coveralls stands at the boundary where the corridor's geometry dissolves into bands, dwarfed by the failing perspective, with rope barriers and a chartreuse hazard placard at their feet.",
        focus="the tiny figure at the boundary, the rope barrier, and the chartreuse placard",
        mood="containment scale, the reef widening",
        palette="corridor gray-on-gray, rope-orange barrier, and antimemetic chartreuse on the placard and the figure's IV-pole bag",
        qa="verify the figure reads as 'the only thing keeping this contained' rather than as a hero pose; scale and isolation do the work.",
    ),
    "MNR Missing Floor": dict(
        composition="Detail",
        ref="bechtle_olds",
        location="an elevator panel in a Foundation site interior",
        action="A close framing of the elevator panel shows the standard column 12, 13, 14, 15 with the 14 button shallowly recessed and unlit while every other button gleams, the brass around 14 slightly burnished as if pressed for decades but never registering.",
        focus="the recessed unlit 14 button surrounded by working buttons",
        mood="quiet impossibility, the floor the building owns but cannot reach",
        palette="brass panel, cab steel, sodium-amber, and a thin antimemetic chartreuse on a small adhesive label below the panel",
        qa="verify the dead button reads as 'pressed many times, never working' rather than 'broken hardware'; the burnish around it is the tell.",
    ),
    "MNR Missing Floor (Containment Critical)": dict(
        composition="Wide",
        ref="whiteread_house",
        location="a stairwell landing at the 13/15 boundary inside a Foundation site",
        action="The stairwell rises through 13 with a heavy metal fire door labeled in worn paint, then a blank concrete wall where the 14 landing should be, then the 15 landing visible above, with a single technician staring up at the seam.",
        focus="the technician looking up at the concrete seam between 13 and 15",
        mood="architectural amnesia, the building disowning a floor",
        palette="stairwell concrete gray, fire-door rust red, sodium overhead, and antimemetic chartreuse on the technician's drug-cup taped to the railing",
        qa="verify the seam reads as 'this floor never existed in this building' rather than as construction-in-progress; the technician's drug-cup is the discipline tell.",
    ),
    "MNR Personnel Drift": dict(
        composition="Aftermath",
        ref="tooker_bureau",
        location="a four-person open-plan analyst pod at end of day",
        action="Three desks are still actively in use (warm coffee, open laptops, jacket on chair) but the fourth desk sits clean and dustless with a single name placard turned face-down, the chair pushed in, and no trace of the analyst who occupied it that morning.",
        focus="the clean fourth desk and the face-down placard among three working desks",
        mood="quiet personnel loss, the seat absented without ceremony",
        palette="fluorescent yellow-white, desk beige, laptop-screen blue, and a thin antimemetic chartreuse on the chartreuse-tabbed badge clipped to the empty desk's monitor",
        qa="verify the empty desk reads as 'this person worked here this morning and now does not exist' rather than 'this desk is unassigned'; the face-down placard is the tell.",
    ),
    "MNR Personnel Drift (Containment Critical)": dict(
        composition="Wide",
        ref="de_maria_kilometer",
        location="a long row of identical analyst desks in a deep antimemetic wing",
        action="A wide view down the corridor of desks reveals every third or fourth desk has been cleared and abandoned, chairs pushed in, monitors dark, face-down placards, with the remaining staff working with deliberate concentration on the still-occupied desks.",
        focus="the rhythm of cleared-and-occupied desks down the wide row",
        mood="distributed loss, drift at scale",
        palette="fluorescent ceiling, desk-beige rhythm, monitor-dark voids, and antimemetic chartreuse on the staff badges of the analysts still in seats",
        qa="verify the row reads as 'every third coworker is gone' rather than 'office is downsizing'; the rhythm of cleared desks is the entire subject.",
    ),
    "MNR Soft Erasure": dict(
        composition="Detail",
        ref="rothko_field",
        location="an open page in an analyst's notebook on a desk",
        action="A notebook page is half-filled with ballpoint handwriting that fades smoothly from legible block letters at the top into nothing by the middle of the page, the pen still resting on the empty lower half.",
        focus="the page's gradient from handwriting into nothing and the pen at the boundary",
        mood="soft excision, memory dissolving along a tideline",
        palette="paper cream, ballpoint blue, desk-pine brown, and a thin antimemetic chartreuse on a sticky note clipped to the notebook's edge",
        qa="verify the fade reads as antimemetic dissolution rather than as bad handwriting; the gradient must be unmistakably mid-page, not edge-bleed.",
    ),
    "MNR Soft Erasure (Severe)": dict(
        composition="Aftermath",
        ref="hammershoi_dust_motes",
        location="the same desk an hour later, lights still on",
        action="The notebook now lies open with two facing pages both entirely blank, the pen on the floor, the chair turned ninety degrees with the analyst absent, and a thin antimemetic-chartreuse pill cup left on the page.",
        focus="the blank facing pages, the floor pen, and the pill cup left on the open notebook",
        mood="completed erasure, the page kept open out of habit",
        palette="paper cream, fluorescent overhead, carpet beige, and antimemetic chartreuse on the pill cup as the only color in the frame",
        qa="verify the blank pages read as 'fully erased writing' rather than as a fresh notebook; the pill cup on top is the antimemetic discipline tell.",
    ),
    "MNR Stripped Conference Room": dict(
        composition="Wide",
        ref="hammershoi_interior",
        location="a boardroom on an upper floor at midday",
        action="A long polished conference table runs through the frame with twelve identical chairs around it, set as if for a meeting, while every wall is bare beige plaster with rectangular sun-faded marks where pictures, projectors, and whiteboards used to be, and one chair pulled out slightly.",
        focus="the long table set for twelve and the sun-faded rectangles on the walls",
        mood="meeting that did not happen, room kept ready out of habit",
        palette="table-polish brown, chair-leather black, plaster beige, daylight from blinds, and a thin antimemetic chartreuse on a paper drug cup forgotten on the table",
        qa="verify the empty room reads as 'meeting that did not happen / cannot be recalled' rather than 'meeting before everyone arrives'; the faded wall rectangles are the timestamp.",
    ),
    "MNR The Blank Folder": dict(
        composition="Detail",
        ref="calle_hotel",
        location="an analyst's desk in a windowless reading room",
        action="A manila folder lies open on a desk, the pages inside completely blank cream paper, the tab on the folder cleanly labeled with a redacted block instead of a name, with normal desk debris around it (coffee ring, ballpoint, sticky-note).",
        focus="the open folder with blank pages and the redacted tab",
        mood="archival void, the folder kept current out of policy",
        palette="manila beige, paper cream, desk-pine, fluorescent overhead, and antimemetic chartreuse on the sticky-note color",
        qa="verify the blank folder reads as 'antimemetically emptied dossier' rather than 'new empty folder'; the redacted tab and normal desk debris around it sell the contrast.",
    ),
    "MNR The Blank Folder (Severe)": dict(
        composition="Aftermath",
        ref="de_maria_kilometer",
        location="a small reading room with a long table",
        action="A long table is covered end-to-end with open manila folders, all of them holding blank pages, the chair pushed back, the analyst's coat draped over it, the room otherwise empty.",
        focus="the long row of open blank folders covering the table",
        mood="archival void at scale, the discipline taken to its conclusion",
        palette="manila beige, paper cream, table-pine, fluorescent overhead, and antimemetic chartreuse on the coat lanyard left on the chairback",
        qa="verify the row of folders reads as 'every dossier has been antimemetically emptied' rather than 'folders prepared but not yet filled'; the coat and chair say the analyst was here moments ago.",
    ),
    "MNR The Director's Note": dict(
        composition="Witness POV",
        ref="wall_view_apartment",
        location="the AD's outer office at 8:11am",
        action="The camera is positioned over a clerk's shoulder watching them slide a sealed manila envelope into the AD's empty in-tray on a polished desk, the AD's chair empty behind it, the office lit by a single sodium lamp.",
        focus="the envelope in the tray and the empty AD chair behind it",
        mood="directive arriving without the director, the office obeyed in absence",
        palette="desk-pine, manila envelope beige, sodium-amber, chair-leather black, and a thin antimemetic chartreuse on the wax seal of the envelope",
        qa="verify the AD chair stays empty and the envelope reads as the protagonist; do not generate a portrait of the Director.",
        note="composition framed over the clerk's shoulder, not centered on the desk",
    ),
    "MNR The Director's Note (Containment Critical)": dict(
        composition="Witness POV",
        ref="hopper_new_york_office",
        location="the AD's inner office in the late afternoon",
        action="The camera is in the doorway looking inward as a senior clerk in shirt-sleeves carries a stack of three sealed manila envelopes to the AD's still-empty desk, the office's tall windows pouring late daylight onto the polished floor.",
        focus="the clerk mid-step with three envelopes and the empty desk ahead",
        mood="directives arriving in volume, the absent director's authority intensifying",
        palette="desk-polish brown, window daylight, floor parquet, and antimemetic chartreuse on the lanyard around the clerk's neck",
        qa="verify the AD desk reads as 'still empty, still authoritative' rather than 'unoccupied office'; do not generate a portrait of the Director.",
    ),
    "MNR The Quiet Hour": dict(
        composition="Wide",
        ref="hopper_office",
        location="an open-plan office floor at 3:14am",
        action="A long view of an open-plan office at three in the morning, every chair pushed in, every monitor on idle screensaver, the only motion a slow ceiling fan, a single security camera mounted high in one corner, and no people anywhere.",
        focus="the rhythm of pushed-in chairs and idle monitors under fluorescent ceiling buzz",
        mood="institutional hush, the hour when the building remembers itself",
        palette="fluorescent ceiling white, carpet navy, monitor-screen blue, and antimemetic chartreuse on a single safety vest hung over a far chairback",
        qa="verify the empty office reads as 'three a.m. when nothing is supposed to be happening' rather than 'office closed for renovation'; the ceiling fan and screensavers are the timestamp.",
    ),
    "MNR White Hallway Recall": dict(
        composition="Anomaly Implied",
        ref="whiteread_ghost",
        location="a long featureless white interior corridor",
        action="A single figure in coveralls is paused mid-step in a corridor of identical white walls, white ceiling, and white floor, turned slightly back over their shoulder as if they have just remembered something the corridor wants them to forget.",
        focus="the paused figure looking back over their shoulder in the white corridor",
        mood="recall under pressure, the corridor as antimemetic medium",
        palette="corridor white-on-white, coverall gray, sodium amber from a single fixture, and a thin antimemetic chartreuse on a pill bottle in the figure's hand",
        qa="verify the corridor reads as 'antimemetic blank' rather than 'unfinished construction'; the figure must look mid-recall, not mid-walk.",
    ),

    # === FACILITIES (16) ===
    "MNR Antimemetic Atlas": dict(
        composition="Wide",
        ref="de_maria_kilometer",
        location="a long archive hall of cartographic cabinets and rolling map cases",
        action="An immense interior is lined with shallow map drawers and rolling-rack mural cases, each rack pulled out an inch to show a beige folded map, with a single archivist on a sliding ladder reading a chartreuse-tabbed dossier.",
        focus="the long rhythm of pulled-out map drawers and the archivist on the ladder",
        mood="cartographic discipline, the world re-mapped to admit what cannot be remembered",
        palette="cabinet beige, map-fold brown, fluorescent ceiling, and antimemetic chartreuse on the archivist's tab",
        qa="verify the hall reads as 'maps that account for antimemetic geography' rather than as a city map library; the drawer rhythm is the architecture.",
    ),
    "MNR Antimemetic Quarantine Lab": dict(
        composition="Wide",
        ref="wright_air_pump",
        location="a containment lab with airlock antechambers and observation glass",
        action="A circular observation window looks into a lab where two suited technicians lean over a small steel apparatus on a central bench, one calibrating dials while the other adjusts an IV drip on a chartreuse bag, lit by a single overhead surgical lamp.",
        focus="the two suited technicians and the steel apparatus under the surgical lamp",
        mood="quarantine pressure, the careful work of holding the unrememberable still",
        palette="lab tile gray, suit-blue, surgical lamp white, and antimemetic chartreuse on the IV bag",
        qa="verify the lab reads as 'antimemetic quarantine in progress' rather than 'standard biolab'; the IV bag is the mnestic discipline tell.",
    ),
    "MNR Black-Box Library": dict(
        composition="Wide",
        ref="de_maria_earth",
        location="a basement archive room dominated by black storage boxes",
        action="A wide interior reveals floor-to-ceiling industrial shelving entirely filled with identical matte-black document boxes, each box labeled only with a redacted block, and a single archivist walking the central aisle with a clipboard.",
        focus="the rhythm of black boxes and the archivist with the clipboard",
        mood="bureaucratic discipline, the archive that admits only what cannot be opened",
        palette="black box matte, shelving steel, aisle concrete, fluorescent ceiling, and antimemetic chartreuse on the archivist's clipboard tab",
        qa="verify the boxes read as 'antimemetic archival containment' rather than 'movie prop crates'; the rhythm and the redacted labels are the architecture.",
    ),
    "MNR Bystander Briefing Hall": dict(
        composition="Wide",
        ref="shore_meeting",
        location="a large pre-meeting hall with rows of folding chairs and a low stage",
        action="A wide view of a fluorescent-lit hall set with three hundred empty folding chairs facing a low stage with a single podium and a folded-up screen, the side aisle holding a tray of chartreuse-labeled drug cups on a service cart.",
        focus="the rows of empty chairs facing the empty stage and the chartreuse drug-cup cart",
        mood="briefing readiness, the audience that has not yet arrived to be inoculated",
        palette="hall fluorescent white, chair gray, stage navy, and antimemetic chartreuse on the drug-cup cart",
        qa="verify the hall reads as 'pre-event mnestic briefing' rather than 'lecture room before class'; the drug-cup cart is the antimemetic tell.",
    ),
    "MNR Bystander Briefing Room": dict(
        composition="Wide",
        ref="register_open_diner",
        location="a small interior briefing room with a circular table and ten chairs",
        action="A small interior briefing room sits empty at end of day, the round table cleared except for ten paper drug cups, one at each seat, the projector still casting a faded slide on the back wall, the door cracked open.",
        focus="the round table with ten drug cups at ten empty seats and the faded slide on the wall",
        mood="briefing aftermath, the smaller hall where individual sessions are held",
        palette="table-pine brown, chair-navy, projector-blue slide light, fluorescent overhead, and antimemetic chartreuse on the ten drug cups",
        qa="verify the room reads as 'just-vacated mnestic briefing' rather than 'meeting being set up'; the drug cups at every seat are the antimemetic tell.",
    ),
    "MNR Bystander Lounge": dict(
        composition="Wide",
        ref="hopper_automat",
        location="a Foundation breakroom with vending machines and a coffee maker",
        action="A breakroom interior at midmorning shows three civilian-tier staff sitting separately at small round tables, each one with a paper drug cup in front of them and an open paperback, vending machines lit behind, no conversation passing between them.",
        focus="the three separated bystanders with their drug cups in the breakroom",
        mood="bureaucratic warmth, communal dosage without communal speech",
        palette="vending-machine glow, formica tabletop, coffee-maker red light, fluorescent ceiling, and antimemetic chartreuse on the drug cups",
        qa="verify the breakroom reads as 'civilian-tier mnestic discipline room' rather than as a generic lunchroom; the drug cups in front of every bystander are the dominant tell.",
    ),
    "MNR Cognitive Anchor Array": dict(
        composition="Wide",
        ref="magritte_time",
        location="a circular interior lab with a central instrument pedestal",
        action="A circular lab is ringed by twelve identical waist-high steel pedestals each bearing a brass-and-glass cognitive anchor, all twelve aimed inward at a central operating chair where a technician adjusts a chartreuse IV cuff on a seated subject.",
        focus="the ring of twelve anchors aimed inward and the seated subject in the central chair",
        mood="instrumented saturation, the array stabilizing one mind at a time",
        palette="lab-tile pale gray, anchor-brass, sodium overhead lamps, and antimemetic chartreuse on the IV cuff",
        qa="verify the ring reads as 'mnestic instrument array' rather than 'museum of brass instruments'; the seated subject and IV cuff are the operational tell.",
    ),
    "MNR Deep Memory Vault": dict(
        composition="Wide",
        ref="whiteread_ghost",
        location="a deep underground vault with a single massive door",
        action="A wide view of a vault antechamber dominated by a single bank-vault-scale steel door at the far end, the antechamber lit by a low sodium fixture, with a small archivist's desk to the side bearing a single chartreuse-tabbed binder.",
        focus="the massive vault door and the small archivist's desk to its side",
        mood="deep storage, the memory kept under literal weight",
        palette="vault-door steel, antechamber concrete, sodium amber, and antimemetic chartreuse on the archivist's binder tab",
        qa="verify the vault reads as 'antimemetic deep storage' rather than as a bank vault; the small archivist's desk is the operational tell.",
    ),
    "MNR Director's Office, AD": dict(
        composition="Witness POV",
        ref="hopper_new_york_office",
        location="the AD's inner office viewed from the doorway",
        action="From the doorway, the camera sees a high-ceilinged corner office at dusk, the AD's desk angled toward two tall windows, the chair empty, a single banker's lamp on, and an open binder on the desk with a chartreuse-tabbed dossier.",
        focus="the empty desk, the lit banker's lamp, and the chartreuse-tabbed dossier",
        mood="absent authority, the office working on its own",
        palette="dusk window-blue, desk-pine, banker's lamp brass-green, and antimemetic chartreuse on the dossier tab",
        qa="verify the AD office reads as 'occupied by the work, not the person' rather than 'office between tenants'; the empty chair is mandatory.",
    ),
    "MNR Inoculation Bay": dict(
        composition="Wide",
        ref="rembrandt_anatomy",
        location="a long row of medical dosing chairs in a foundation infirmary",
        action="A wide view of a long inoculation bay shows fourteen reclined dosing chairs in two rows, each occupied by a Foundation staff member on a chartreuse IV drip, two technicians walking the aisle with clipboards, ceiling-mounted lights on a regular grid.",
        focus="the long bay of reclined chairs on chartreuse IV drips with technicians walking the aisle",
        mood="bureaucratic medical discipline, the routine of staying remembered at scale",
        palette="bay-tile gray, chair-vinyl beige, lamp-white grid, and antimemetic chartreuse on every IV bag as the dominant tell",
        qa="verify the bay reads as 'mass mnestic dosing routine' rather than 'emergency blood drive'; the IV bags on every chair are the dominant tell.",
    ),
    "MNR Junior Coordination Office": dict(
        composition="Wide",
        ref="hopper_conference_night",
        location="a small two-desk office where two coordination juniors share a phone bank",
        action="A small interior office holds two desks back-to-back, each with a junior in shirt-sleeves on a desk phone with a clipboard, a wall-mounted whiteboard ruled with empty schedule grids behind them, fluorescent ceiling.",
        focus="the two juniors on phones with empty schedule grids on the wall behind",
        mood="entry-level bureaucratic labor, coordination as ongoing process",
        palette="desk-pine, shirt-sleeve white, whiteboard pale, fluorescent ceiling, and antimemetic chartreuse on a row of tabbed binders behind one desk",
        qa="verify the office reads as 'junior coordination work-in-progress' rather than 'call center'; the whiteboard with empty grids is the bureaucratic tell.",
    ),
    "MNR Mnemonic Imprint Station": dict(
        composition="Detail",
        ref="wright_air_pump",
        location="a single station bench at a memory-imprint lab",
        action="A close-mid view of a steel lab bench shows a single seated subject in a head-frame with twelve thin chartreuse-tipped neural leads connected to a brass-faced amplifier rack, a technician's gloved hands adjusting one lead at a time.",
        focus="the head-frame, the chartreuse-tipped leads, and the technician's gloved hands",
        mood="precise imprinting, memory put back by hand",
        palette="bench-steel, frame-brass, lab-tile pale gray, and antimemetic chartreuse on every neural-lead tip",
        qa="verify the station reads as 'targeted mnestic imprinting' rather than as a torture device; the gloved hands and the chartreuse leads are the operational tell.",
    ),
    "MNR Mnestic Ward": dict(
        composition="Wide",
        ref="hammershoi_dust_motes",
        location="a long single-corridor ward with windowed patient rooms on both sides",
        action="A wide view down a fluorescent-lit ward corridor reveals twenty windowed patient rooms on each side, half with their privacy blinds drawn closed, half with single occupants visible on chartreuse IV drips, an attendant walking the center of the corridor with a tray.",
        focus="the long ward corridor with its rhythm of drawn and open windows and the attendant in the center",
        mood="long-term mnestic discipline, the ward as residence",
        palette="ward-tile gray, blind-white, sodium amber, and antimemetic chartreuse on the visible IV bags",
        qa="verify the ward reads as 'long-term mnestic residency' rather than as a hospital ward; the IV bags are the antimemetic tell.",
    ),
    "MNR Pre-Amnestic Records": dict(
        composition="Wide",
        ref="de_maria_kilometer",
        location="an archival hall of identical brown banker's boxes stacked floor-to-ceiling",
        action="A wide interior aisle runs between two walls of identical brown banker's boxes stacked four high, each box labeled with a date-only tape strip, with a single archivist on a step ladder pulling one box halfway out.",
        focus="the long aisle of identical date-only boxes and the archivist on the ladder",
        mood="pre-event archival discipline, the records preserved before the amnestic kicks in",
        palette="box brown, aisle concrete, fluorescent overhead, and antimemetic chartreuse on the archivist's binder tab",
        qa="verify the hall reads as 'records preserved against future amnestic' rather than 'tax archive'; the date-only labels are the bureaucratic tell.",
    ),
    "MNR Reality Stabilization Suite": dict(
        composition="Wide",
        ref="magritte_empire",
        location="a circular control suite ringed with monitor banks and a central reading floor",
        action="A wide interior of a circular suite shows three operators at panel stations around the perimeter watching a central floor where a single freestanding brass cognitive anchor hums under sodium light, all monitors showing slow green oscilloscope traces.",
        focus="the central anchor and the three operators at panel stations around it",
        mood="instrumented stillness, the suite calibrated to one anomaly",
        palette="panel matte black, monitor green-trace, sodium overhead, and antimemetic chartreuse on the chartreuse-coded panel tabs",
        qa="verify the suite reads as 'reality calibration in progress' rather than 'mission control'; the central freestanding anchor and slow green traces are the operational tell.",
    ),
    "MNR Sealed Conference Room": dict(
        composition="Witness POV",
        ref="wall_view_apartment",
        location="a closed conference-room door with a viewport window viewed from the corridor",
        action="From the corridor, the camera looks through a small wire-mesh viewport in a closed conference-room door at a dim interior with eight figures in dress shirts around a table, the room locked, a chartreuse-keyed badge reader glowing beside the door.",
        focus="the wire-mesh viewport, the eight figures inside, and the chartreuse badge reader",
        mood="sealed deliberation, the room kept airtight to keep what cannot be repeated inside",
        palette="corridor sodium amber, viewport-mesh black, interior dim navy, and antimemetic chartreuse on the badge reader",
        qa="verify the conference room reads as 'antimemetically sealed deliberation' rather than 'private meeting'; the chartreuse badge reader and wire-mesh viewport are the access tells.",
    ),

    # === PERSONNEL (30) ===
    "MNR Antimemetic Tactician": dict(
        composition="Detail",
        ref="sargent_two_soldiers",
        location="a briefing room corner with a tactical board",
        action="A senior tactician in dress shirt and tactical vest leans over a tactical board pinned with chartreuse-tabbed cards, one hand mid-gesture marking a route, the other holding an unlit ballpoint pen.",
        focus="the tactician's hands on the tactical board with the chartreuse-tabbed cards",
        mood="competent operational pressure, the routes worked out before the briefing starts",
        palette="board-cork brown, vest-navy, dress-shirt white, fluorescent overhead, and antimemetic chartreuse on the tab cards",
        qa="verify the tactician reads as 'mid-planning, not yet briefing' rather than as a hero pose; hands and the board do the work.",
    ),
    "MNR Black-Box Archivist": dict(
        composition="Detail",
        ref="calle_hotel",
        location="a small archivist's desk in front of the Black-Box Library shelving",
        action="An archivist seated at a low desk lifts a matte-black document box onto the desk with both gloved hands, a chartreuse-tabbed binder open beside it, the shelving of identical black boxes filling the background.",
        focus="the gloved hands lifting the black box and the chartreuse-tabbed binder",
        mood="archival discipline, the box opened with both hands because both hands matter",
        palette="box matte black, shelving steel, fluorescent overhead, and antimemetic chartreuse on the binder tab",
        qa="verify the archivist reads as 'practiced handling of antimemetic archive' rather than as a museum curator; the gloved hands and the chartreuse-tabbed binder are the tells.",
    ),
    "MNR Briefing-Room Listener": dict(
        composition="Reaction",
        ref="hopper_office",
        location="a small briefing room with seven other chairs",
        action="A single mid-career staff member sits forward in a briefing chair, paper drug cup beside their hand, head tilted in concentration as they listen, the room out of focus around them.",
        focus="the listener's tilted-head concentration and the paper drug cup beside their hand",
        mood="dosed attention, the act of listening as a job in itself",
        palette="chair-navy, dress-shirt cream, fluorescent overhead, and antimemetic chartreuse on the drug cup",
        qa="verify the listener reads as 'mid-briefing concentration' rather than as a passive crowd-extra; the drug cup is the dosage tell.",
    ),
    "MNR Bystander Coordinator": dict(
        composition="Detail",
        ref="degas_ironing",
        location="a small office desk with a clipboard and an active phone line",
        action="A bystander coordinator in a cardigan and lanyard stands at the corner of a desk, phone wedged between shoulder and ear, marking names on a clipboard with a chartreuse highlighter, a tray of paper drug cups in front of her.",
        focus="the coordinator's posture, the clipboard, and the chartreuse highlighter mid-stroke",
        mood="competent routine, the coordinator who keeps the civilians inoculated on schedule",
        palette="cardigan beige, lanyard navy, desk-pine, fluorescent overhead, and antimemetic chartreuse on the highlighter",
        qa="verify the coordinator reads as 'tracking civilian dosage by name' rather than as a receptionist; the chartreuse highlighter is the operational tell.",
    ),
    "MNR Bystander Witness Pool": dict(
        composition="Wide",
        ref="kollwitz_survivors",
        location="a holding room with rows of folding chairs and an attendant at the door",
        action="A wide view of a holding room shows twenty-four civilians in everyday clothes sitting in three rows of folding chairs, each with a paper drug cup, an attendant at the door checking names off a clipboard.",
        focus="the rows of civilian witnesses with their drug cups and the attendant at the door",
        mood="collective bystander discipline, the pool kept ready to be debriefed and forgotten",
        palette="holding-room beige, civilian-clothes earth tones, attendant-shirt navy, fluorescent overhead, and antimemetic chartreuse on every drug cup",
        qa="verify the pool reads as 'civilian witnesses awaiting mnestic processing' rather than as a jury room; the rows of drug cups are the operational tell.",
    ),
    "MNR Class-A Inoculated Agent": dict(
        composition="Reaction",
        ref="freud_self",
        location="an operator-ready room mirror at the start of a shift",
        action="An MTF agent in tactical layered clothing stands at a wall mirror in an operator-ready room, IV cuff still taped to forearm, tipping back a paper drug cup of three chartreuse capsules, eyes meeting their own reflection.",
        focus="the agent's reflection, the IV cuff on the forearm, and the chartreuse drug cup mid-tip",
        mood="pre-deployment mnestic discipline, the dosage that makes the next eight hours possible",
        palette="tactical earth tones, mirror reflection, ready-room fluorescent, and antimemetic chartreuse as the dominant tell on cup and capsules",
        qa="verify the agent reads as 'mid-saturation, not yet deployed' rather than as a hero pose; the IV cuff and the drug cup are the operational tells.",
    ),
    "MNR Cleanup Crew Lead": dict(
        composition="Detail",
        ref="bechtle_torino",
        location="the lip of a hallway being prepped for cleanup",
        action="A cleanup crew lead in coveralls and respirator pulled down to neck speaks into a radio at the entrance to a side corridor, a clipboard against thigh and a chartreuse hazard placard already set down on the carpet.",
        focus="the lead's hand on the radio, the clipboard, and the chartreuse placard on the carpet",
        mood="practical operational command, the corridor being made safe before staff return",
        palette="coverall beige, respirator black, fluorescent overhead, and antimemetic chartreuse on the placard",
        qa="verify the lead reads as 'mid-deployment cleanup leadership' rather than as a hazmat poster; the radio, clipboard, and placard are the operational tells.",
    ),
    "MNR Conference Attendee": dict(
        composition="Reaction",
        ref="hopper_office",
        location="a small conference room mid-session",
        action="A mid-level conference attendee sits at a table in a small session, posture politely attentive, paper drug cup at one elbow, ballpoint pen in the other hand resting on a closed manila folder, a chair beside them empty.",
        focus="the attendee's polite posture, the drug cup at the elbow, and the empty adjacent chair",
        mood="meeting-room dosed attention, the seat that knows the seat beside it has been emptied recently",
        palette="conference table-pine, dress-shirt cream, fluorescent overhead, and antimemetic chartreuse on the drug cup",
        qa="verify the attendee reads as 'mid-meeting bystander' rather than as a deposition witness; the empty adjacent chair is the antimemetic tell.",
    ),
    "MNR D-Class (No Recall)": dict(
        composition="Reaction",
        ref="freud_benefits",
        location="a small interview room with a table and two chairs",
        action="A D-Class subject in orange coveralls sits across from an empty chair, head turned slightly, expression patient and entirely uncomprehending, a paper drug cup of two chartreuse capsules on the table in front of them.",
        focus="the D-Class subject's uncomprehending posture and the paper drug cup on the table",
        mood="post-amnestic patience, the subject who no longer knows what they did or did not see",
        palette="coverall orange, table-pine, fluorescent overhead, interview-room navy walls, and antimemetic chartreuse on the drug cup",
        qa="verify the D-Class reads as 'amnestically reset, calm' rather than as a prisoner; the empty chair across from them is the bureaucratic tell.",
    ),
    "MNR Department Newcomer": dict(
        composition="Reaction",
        ref="wyeth_christina",
        location="a new-staff orientation corridor",
        action="A young analyst in still-creased badge and lanyard stands at the threshold of an open office, looking down a corridor of identical doors, clipboard hugged to chest, paper drug cup in the other hand.",
        focus="the newcomer's posture at the threshold, the clipboard, and the drug cup",
        mood="first-day disorientation, the corridor that does not introduce itself",
        palette="badge-lanyard navy, dress-shirt white, corridor fluorescent, carpet beige, and antimemetic chartreuse on the drug cup",
        qa="verify the newcomer reads as 'first day, mnestic discipline already starting' rather than as a tourist; the drug cup and clipboard are the discipline tells.",
    ),
    "MNR Director, Antimemetics Division": dict(
        composition="Witness POV",
        ref="hopper_new_york_office",
        location="the Director's inner office viewed from the doorway",
        action="From the doorway, the camera sees the Director's high-backed chair turned three-quarters away from the desk toward a tall window, an arm resting on the chair-arm holding a paper drug cup, the rest of the figure obscured by the chairback.",
        focus="the chair-arm hand holding the drug cup and the tall window beyond",
        mood="present-but-faceless authority, the Director rendered as posture not portrait",
        palette="window dusk-blue, chair-leather black, desk-pine, banker's lamp brass, and antimemetic chartreuse on the drug cup",
        qa="verify the Director reads as 'a working director on a saturation dose' rather than as a hero portrait; the chair must obscure the face and the drug cup must dominate.",
        note="do not generate a portrait; the chairback is the face",
    ),
    "MNR Documents Clerk": dict(
        composition="Detail",
        ref="degas_ironing",
        location="a clerk's stand-up desk in front of a wall of pigeonhole shelves",
        action="A documents clerk in dress shirt and cardigan stands at a high desk, sliding a manila envelope into a numbered pigeonhole, paper drug cup at one elbow, chartreuse-tabbed sort tray under the other hand.",
        focus="the clerk's hand placing the envelope, the drug cup, and the chartreuse-tabbed sort tray",
        mood="routine bureaucratic discipline, the clerk who sorts what cannot be remembered into bins",
        palette="cardigan beige, pigeonhole-wood brown, fluorescent overhead, and antimemetic chartreuse on the sort tray tab",
        qa="verify the clerk reads as 'mid-sort discipline' rather than as a postal worker; the chartreuse-tabbed sort tray is the operational tell.",
    ),
    "MNR Forgotten Bureau Liaison": dict(
        composition="Reaction",
        ref="vermeer_geographer",
        location="a corridor where two government departments meet, with a small visitor desk",
        action="A senior liaison in a gray suit stands at a small visitor desk between two corridors, signing in with a ballpoint, a soft leather briefcase set on the floor and a chartreuse-tabbed dossier in their off hand, no one at the desk to receive them.",
        focus="the liaison signing in alone at the empty visitor desk with the chartreuse-tabbed dossier",
        mood="quiet diplomatic patience, the official whose department has been antimemetically misplaced",
        palette="suit gray, briefcase brown, desk-pine, fluorescent overhead, and antimemetic chartreuse on the dossier tab",
        qa="verify the liaison reads as 'representing a department nobody remembers existing' rather than as a visiting executive; the unattended desk and the chartreuse-tabbed dossier are the tells.",
    ),
    "MNR Hallway Runner": dict(
        composition="Action",
        ref="wall_insomnia",
        location="a fluorescent-lit interior corridor in mid-stride",
        action="A junior staff member in shirt-sleeves is caught mid-stride down a fluorescent-lit corridor, a chartreuse-tabbed envelope held flat against their chest, the corridor receding behind them.",
        focus="the runner mid-stride and the chartreuse-tabbed envelope against their chest",
        mood="practical bureaucratic motion, the runner whose hands carry what the network cannot",
        palette="corridor fluorescent white, shirt-sleeve cream, carpet navy, and antimemetic chartreuse on the envelope tab",
        qa="verify the runner reads as 'urgent inter-office delivery in progress' rather than as a track event; the chartreuse-tabbed envelope is the operational tell.",
    ),
    "MNR Inoculated D-Class": dict(
        composition="Reaction",
        ref="freud_benefits",
        location="a recovery chair in a quiet corner of the inoculation bay",
        action="A D-Class subject in orange coveralls reclines in a dosing chair, eyes half-open under bandaged forearm IV, a chartreuse bag dripping slowly, an attendant checking pulse at the wrist.",
        focus="the reclined D-Class, the chartreuse IV bag, and the attendant's hand at the wrist",
        mood="post-inoculation drift, the subject newly capable of remembering what they are about to be told",
        palette="coverall orange, chair-vinyl beige, lamp-white grid, and antimemetic chartreuse on the IV bag",
        qa="verify the D-Class reads as 'just inoculated, becoming useful' rather than as a coma patient; the attendant's hand at the wrist is the operational tell.",
    ),
    "MNR Inoculated Recordkeeper": dict(
        composition="Detail",
        ref="calle_hotel",
        location="an archivist's reading desk in a small annex room",
        action="A senior recordkeeper in cardigan and bifocals sits at a reading desk with a yellow legal pad, mid-sentence writing, an IV-port band still on their forearm, a small chartreuse pill bottle uncapped beside the pad.",
        focus="the recordkeeper's writing hand, the IV-port band, and the uncapped chartreuse pill bottle",
        mood="dosed recall, the archivist whose job is to remember on chemical pension",
        palette="cardigan beige, pad yellow, fluorescent overhead, and antimemetic chartreuse on the pill bottle",
        qa="verify the recordkeeper reads as 'mnestically inoculated for archival recall' rather than as a paperwork clerk; the IV-port band and the chartreuse pill bottle are the discipline tells.",
    ),
    "MNR Mailroom Junior": dict(
        composition="Detail",
        ref="degas_ironing",
        location="a small basement mailroom with a long sorting table",
        action="A mailroom junior in shirt-sleeves sorts a stack of manila envelopes on a long table under a single fluorescent strip, paper drug cup at one elbow, a chartreuse-marked priority bin at the table's end.",
        focus="the junior's hands sorting envelopes and the chartreuse-marked priority bin",
        mood="entry-level discipline, the mailroom where every envelope is potentially antimemetic",
        palette="table-pine, envelope beige, fluorescent strip white, and antimemetic chartreuse on the priority bin",
        qa="verify the junior reads as 'mid-sort, lower-tier discipline' rather than as a postal stock photo; the drug cup and chartreuse priority bin are the operational tells.",
    ),
    "MNR Marion Wheeler": dict(
        composition="Reaction",
        ref="freud_self",
        location="a senior analyst's narrow office at 9pm, one banker's lamp on",
        action="A specific woman in her forties in a worn dress shirt and lanyard sits at her desk under a single banker's lamp, one hand at her temple, the other resting on an open notebook, a small chartreuse pill bottle on the desk beside a paper drug cup.",
        focus="Marion at the desk, hand at temple, with the chartreuse pill bottle and drug cup",
        mood="exhausted senior discipline, the analyst who keeps remembering on schedule",
        palette="banker's lamp brass-green, desk-pine, dress-shirt cream, and antimemetic chartreuse on the pill bottle and drug cup",
        qa="verify Marion reads as 'a specific senior analyst at the end of a long shift' rather than as an action-hero MTF operative; the chartreuse pill bottle and drug cup are mandatory tells.",
        note="single specific exhausted senior analyst, not a hero pose",
    ),
    "MNR Memory Pattern Analyst": dict(
        composition="Detail",
        ref="tooker_subway",
        location="an analyst's desk with two monitors and a wall of printout",
        action="An analyst in dress shirt leans toward two monitors that display slow oscilloscope traces in green, a thin chartreuse highlighter mid-stroke across a printout taped to the wall, a paper drug cup on the desk corner.",
        focus="the green oscilloscope traces, the chartreuse highlighter on the wall printout, and the drug cup",
        mood="instrumented attention, the analyst reading patterns the way others read weather",
        palette="monitor-screen green, wall-printout cream, desk-pine, fluorescent overhead, and antimemetic chartreuse on the highlighter",
        qa="verify the analyst reads as 'mid-pattern-recognition' rather than as a typical sci-fi researcher; the green traces and chartreuse highlighter are the operational tells.",
    ),
    "MNR Mnemonic Field Agent": dict(
        composition="Reaction",
        ref="sargent_two_soldiers",
        location="a parking-garage stairwell exit at end of shift",
        action="A field agent in tactical layered clothing stands at the open exit door of a parking garage, dosing-cup in hand, the city dim beyond, IV-port band on the forearm, a black field bag at their feet.",
        focus="the agent at the open door with the dosing cup and field bag",
        mood="end-of-deployment discipline, the agent dosing once more before returning to the world",
        palette="garage sodium amber, tactical earth tones, exit-door black, and antimemetic chartreuse on the dosing cup",
        qa="verify the agent reads as 'end-of-shift mnestic regimen' rather than as a hero pose; the dosing cup and field bag are the operational tells.",
    ),
    "MNR Mnemonic Surgeon": dict(
        composition="Detail",
        ref="rembrandt_anatomy",
        location="a small precise surgical station in the imprint lab",
        action="A surgeon in scrubs and head-loupe leans over a seated subject in a head-frame, one hand on a chartreuse-tipped probe and the other adjusting an articulated lamp, a sterile tray of probes laid out at hand.",
        focus="the surgeon's hands on the probe and lamp and the head-frame",
        mood="precise discipline, the work of putting memory back by hand",
        palette="scrub blue, head-frame steel, lamp-white, and antimemetic chartreuse on the probe tip",
        qa="verify the surgeon reads as 'mnemonic precision work' rather than as a horror surgeon; the chartreuse-tipped probe and the articulated lamp are the operational tells.",
    ),
    "MNR Mnestic Anchor Operative": dict(
        composition="Reaction",
        ref="freud_self",
        location="an operator-ready room at the cognitive anchor array",
        action="An operative in tactical earth tones stands holding a small brass cognitive anchor in both hands at chest height, eyes closed in deliberate concentration, IV cuff on forearm, the anchor array faintly visible behind them.",
        focus="the operative's hands cradling the brass anchor and the IV cuff on the forearm",
        mood="discipline as ritual, the anchor steadied by deliberate concentration",
        palette="tactical earth tones, anchor brass, ready-room fluorescent, and antimemetic chartreuse on the IV cuff",
        qa="verify the operative reads as 'mid-anchor-discipline' rather than as a religious icon; the IV cuff and the brass anchor are the operational tells.",
    ),
    "MNR Mnestic Cathedral Curator": dict(
        composition="Wide",
        ref="hammershoi_interior",
        location="a vaulted high-ceiling archive hall with long ranks of brass anchors on plinths",
        action="A curator in a tweed jacket walks the central aisle of a vaulted archive hall, dozens of brass cognitive anchors set on plinths along both sides, the curator pausing to adjust one anchor with a gloved hand.",
        focus="the curator pausing to adjust one brass anchor in the long vaulted hall",
        mood="curatorial discipline, the archive of memory anchors maintained one at a time",
        palette="vaulted-stone gray, anchor brass, sodium overhead lamps, and antimemetic chartreuse on the curator's clipboard tag",
        qa="verify the curator reads as 'maintaining the anchor archive' rather than as a museum staff; the gloved hand on one anchor and the chartreuse clipboard tag are the operational tells.",
    ),
    "MNR Mnestic-Coated Operative": dict(
        composition="Detail",
        ref="freud_self",
        location="an operator-ready room mirror at the start of a deployment",
        action="An MTF operative in full tactical gear stands at a wall mirror, both forearm IV cuffs taped, a transparent chartreuse-tinted gloss visible on bare skin at the wrist where mnestic skin-coating has been applied.",
        focus="the operative's forearm with the IV cuff and the chartreuse skin-coating at the wrist",
        mood="full-saturation discipline, the operative coated against forgetting",
        palette="tactical earth tones, mirror reflection, ready-room fluorescent, and antimemetic chartreuse on the skin-coating and IV cuffs as the dominant tell",
        qa="verify the operative reads as 'mid-coating discipline' rather than as a horror dermatology case; the chartreuse skin-gloss must read as 'pharmaceutical' not 'glow'.",
    ),
    "MNR Office Temp": dict(
        composition="Detail",
        ref="hopper_automat",
        location="a temp's loaner desk in a corner of a divisional office",
        action="A temp in business-casual sits at a borrowed desk with a temporary laptop, single coffee cup, paper drug cup the temp clearly does not yet know to take, a stack of unread orientation papers, no name placard.",
        focus="the temp's posture at the borrowed desk and the unfamiliar drug cup beside the coffee",
        mood="liminal staff discipline, the temp who has been assigned but not yet inoculated to the antimemes",
        palette="desk-pine, dress-shirt cream, fluorescent overhead, and antimemetic chartreuse on the unfamiliar drug cup",
        qa="verify the temp reads as 'borrowed-desk new hire' rather than as a permanent analyst; the missing placard and the unfamiliar drug cup are the tells.",
    ),
    "MNR Reluctant Subject": dict(
        composition="Reaction",
        ref="kollwitz_survivors",
        location="a small interview-and-dose room",
        action="A civilian subject in their fifties sits in an interview chair, body tense, head turned slightly away from the proffered paper drug cup held out by a gloved attendant's hand from off-frame.",
        focus="the subject's tense posture and the proffered chartreuse drug cup at the edge of the frame",
        mood="reluctant compliance, the dose offered but not yet accepted",
        palette="chair-vinyl beige, civilian-clothes navy, fluorescent overhead, and antimemetic chartreuse on the proffered drug cup",
        qa="verify the subject reads as 'reluctant civilian about to comply' rather than as a torture-room victim; the off-frame gloved hand and chartreuse drug cup are the operational tells.",
    ),
    "MNR SZB Liaison": dict(
        composition="Reaction",
        ref="daumier_clerks",
        location="a small inter-office meeting space between two departments",
        action="An SZB-branch liaison in a dark suit and lapel pin sits across a small table from an unseen counterpart, hands folded over a chartreuse-tabbed dossier, a paper drug cup at one elbow, the room austere.",
        focus="the liaison's folded hands on the chartreuse-tabbed dossier and the drug cup at the elbow",
        mood="inter-bureau composure, the SZB liaison practiced in dosed diplomacy",
        palette="suit dark navy, table-pine, dress-shirt cream, fluorescent overhead, and antimemetic chartreuse on the dossier tab and drug cup",
        qa="verify the liaison reads as 'practiced inter-bureau official' rather than as a generic businessman; the chartreuse-tabbed dossier and drug cup are the discipline tells.",
    ),
    "MNR Untrained Observer": dict(
        composition="Reaction",
        ref="wyeth_wind_from_sea",
        location="a partly-cracked door at the end of a corridor",
        action="A civilian in casual clothes stands at a partly-cracked door at the end of a corridor, looking through the gap at something out of frame, one hand still on the doorknob.",
        focus="the observer's posture at the cracked door and the hand still on the knob",
        mood="accidental witness, the civilian who has just seen something they will not be allowed to remember",
        palette="corridor fluorescent, door-paint cream, civilian-clothes earth tones, and a thin antimemetic chartreuse on a building-directory placard beside the door",
        qa="verify the observer reads as 'accidental civilian witness' rather than as a stalker; the cracked door and the hand on the knob are the tells.",
    ),
    "MNR Walked-Out Intern": dict(
        composition="Aftermath",
        ref="hammershoi_interior",
        location="an intern's empty corner desk and an open door to the corridor",
        action="An empty intern desk holds a half-finished coffee, a laptop still on with a screensaver, a name placard reading nothing legible, and the office door open to a corridor where no one is walking back.",
        focus="the empty intern desk with the warm coffee and the open door",
        mood="quiet walk-out, the intern who has just left and will not be retrieved",
        palette="desk-pine, coffee-cup white, laptop-screen blue, fluorescent overhead, and antimemetic chartreuse on the placard's redacted label strip",
        qa="verify the desk reads as 'just-vacated, walked out two minutes ago' rather than 'unassigned' or 'vacation'; the warm coffee and open door are the timestamp.",
    ),
    "MNR Witness in 12-B": dict(
        composition="Reaction",
        ref="freud_self",
        location="an interview room labeled 12-B at the end of a corridor",
        action="A civilian in their thirties sits across an interview table in room 12-B, one hand on the table near a paper drug cup, the other in their lap, expression patient and slightly confused, the room number painted on the wall behind them.",
        focus="the civilian's patient confusion and the paper drug cup at the table edge",
        mood="bystander deposition, the witness whose memory will not survive the interview",
        palette="interview-room navy walls, table-pine, civilian-clothes earth tones, fluorescent overhead, and antimemetic chartreuse on the drug cup",
        qa="verify the civilian reads as 'mid-witness-deposition, calm' rather than as a hostile witness; the room number on the wall and the drug cup are the institutional tells.",
    ),

    # === PROCEDURES (42) ===
    "MNR Anchor Reset": dict(
        composition="Detail",
        ref="wright_air_pump",
        location="the cognitive anchor array's central operating chair",
        action="A technician's gloved hands cradle a brass cognitive anchor over the head-frame of a seated subject, mid-recalibration, with a single overhead surgical lamp throwing a sharp pool of light on the anchor.",
        focus="the gloved hands cradling the brass anchor and the head-frame in the surgical pool",
        mood="instrumented reset, the anchor returned to a known state",
        palette="surgical lamp white, anchor brass, frame steel, and antimemetic chartreuse on the IV line into the subject's arm",
        qa="verify the anchor reset reads as 'mid-recalibration' rather than as a torture device; the gloved hands and the surgical lamp are the operational tells.",
    ),
    "MNR Antimemetic Audit": dict(
        composition="Detail",
        ref="vermeer_geographer",
        location="an auditor's stand-up desk in a small annex room",
        action="An auditor in a dark suit ticks off a long list on a clipboard with a chartreuse pen, a column of identical brown banker's boxes pulled halfway out on a shelf behind, three boxes marked with chartreuse audit tags.",
        focus="the auditor's chartreuse pen ticking the list and the three chartreuse-tagged boxes on the shelf",
        mood="audit discipline, the count taken against records that may not match",
        palette="suit dark navy, clipboard cream, shelf-box brown, fluorescent overhead, and antimemetic chartreuse on the pen and the audit tags",
        qa="verify the audit reads as 'antimemetic discrepancy audit in progress' rather than as a tax inspection; the chartreuse pen and tags are the operational tells.",
    ),
    "MNR Antimemetic Brief Box": dict(
        composition="Detail",
        ref="thiebaud_counter",
        location="a clerk's desk in a small archive intake room",
        action="A locked steel briefing box sits open on a desk, exposing a stack of chartreuse-tabbed dossiers inside, the lid lined with a foam grid, a clerk's gloved hand reaching for the topmost dossier.",
        focus="the open steel box, the chartreuse-tabbed dossiers, and the gloved hand reaching for the top",
        mood="secure-archive discipline, the box opened only with gloves and only here",
        palette="box steel, foam-lining gray, desk-pine, fluorescent overhead, and antimemetic chartreuse on every tab",
        qa="verify the brief box reads as 'antimemetic secure briefing kit' rather than as a generic flight case; the foam grid, gloved hand, and chartreuse tabs are the operational tells.",
    ),
    "MNR Antimemetic Defense Brief": dict(
        composition="Wide",
        ref="shore_meeting",
        location="a circular briefing room with seating for eight and a wall-mounted screen",
        action="A wide view of a circular briefing room shows eight staff seated around the table watching a wall screen displaying a single chartreuse pattern diagram, a senior analyst at the head of the table mid-gesture, paper drug cups at every seat.",
        focus="the wall screen with the chartreuse pattern, the analyst mid-gesture, and the drug cups at every seat",
        mood="active briefing discipline, the defense pattern walked through one diagram at a time",
        palette="screen-blue, table-pine, dress-shirt cream, fluorescent overhead, and antimemetic chartreuse on the screen diagram and every drug cup",
        qa="verify the brief reads as 'mid-defense walkthrough' rather than as a corporate presentation; the chartreuse pattern on the screen and the drug cups at every seat are the operational tells.",
    ),
    "MNR Antimemetic Tracker": dict(
        composition="Detail",
        ref="fischl_birthday",
        location="a single analyst's desk with two monitors and a wall pinboard",
        action="A close-mid view of an analyst's desk shows two monitors displaying slow oscilloscope traces, a wall pinboard with a string-and-pin tracking network, a hand mid-pin with a chartreuse pin between fingers.",
        focus="the analyst's hand mid-pin with the chartreuse pin and the string network on the board",
        mood="instrumented pursuit, the antimeme tracked one node at a time",
        palette="monitor green, pinboard cork brown, string-red, fluorescent overhead, and antimemetic chartreuse on the pin",
        qa="verify the tracker reads as 'mid-pursuit pinboard' rather than as a true-crime moodboard; the chartreuse pin and oscilloscope traces are the operational tells.",
    ),
    "MNR Backchannel Brief": dict(
        composition="Witness POV",
        ref="wall_view_apartment",
        location="a doorway looking into a small private corridor alcove",
        action="From a corridor doorway, the camera sees two senior staff in dress shirts leaning toward each other in a narrow alcove, one passing a chartreuse-tabbed envelope to the other under a single sodium fixture.",
        focus="the envelope mid-pass between the two figures in the alcove",
        mood="off-record discipline, the brief that does not go through the system",
        palette="alcove sodium amber, dress-shirt cream, corridor fluorescent overflow, and antimemetic chartreuse on the envelope tab",
        qa="verify the backchannel reads as 'unrecorded inter-staff exchange' rather than as a spy-thriller drop; the alcove framing and chartreuse-tabbed envelope are the operational tells.",
    ),
    "MNR Black-Bag Job": dict(
        composition="Action",
        ref="wall_insomnia",
        location="a civilian office at night under low security lighting",
        action="A black-bagged operative in dark gear lifts a single document folder from a desk drawer in a civilian office at night, a small flashlight braced under the chin, the office windows showing city lights outside.",
        focus="the operative's hands on the folder and the chin-braced flashlight",
        mood="covert extraction, the bag-job that will not be remembered by the office tomorrow",
        palette="office-dark navy, flashlight-white pool, city-window amber, and antimemetic chartreuse on the folder's tab",
        qa="verify the job reads as 'mid-bag-job extraction' rather than as a movie-thriller pose; the chin-braced flashlight and the chartreuse folder tab are the operational tells.",
    ),
    "MNR Brief and Bury": dict(
        composition="Aftermath",
        ref="hammershoi_dust_motes",
        location="a debriefing room ten minutes after the brief ended",
        action="A small debriefing room sits empty, eight chairs pushed in around a table that still holds the open chartreuse-tabbed dossier facedown on top of a row of unfinished drug cups, the projector still casting a blank rectangle.",
        focus="the facedown chartreuse-tabbed dossier on the table and the row of unfinished drug cups",
        mood="briefing-and-erasure discipline, the room kept ready to receive the next batch",
        palette="table-pine, chair-navy, projector-blue rectangle, fluorescent overhead, and antimemetic chartreuse on the dossier and the cups",
        qa="verify the room reads as 'just-finished brief, audience already departed for mnestic erasure' rather than as a meeting interrupted; the facedown dossier and unfinished drug cups are the timestamp.",
    ),
    "MNR Briefing Update": dict(
        composition="Detail",
        ref="degas_ironing",
        location="a stand-up desk at the front of an empty briefing room",
        action="A senior analyst at a stand-up lectern pins a new chartreuse-tabbed slide into a binder on the lectern, the briefing room empty behind them, the projector still on the previous slide on the wall.",
        focus="the analyst's hand pinning the new slide into the binder",
        mood="incremental discipline, the briefing kept current one slide at a time",
        palette="lectern wood, slide-binder cream, projector-blue wall, fluorescent overhead, and antimemetic chartreuse on the new slide's tab",
        qa="verify the update reads as 'briefing being kept current' rather than as a magician's reveal; the binder, the lectern, and the chartreuse-tabbed slide are the operational tells.",
    ),
    "MNR Class-A Inoculation Dose": dict(
        composition="Detail",
        ref="freud_self",
        location="a dosing chair in the inoculation bay",
        action="A close-mid view of a forearm in a reclined dosing chair shows a fresh IV line newly taped to the skin, a chartreuse drip beginning, a gloved hand still on the tape, the chair vinyl visible beneath.",
        focus="the IV line, the chartreuse drip beginning, and the gloved hand on the tape",
        mood="initial dose discipline, the Class-A baseline established",
        palette="chair-vinyl beige, glove-blue, IV-line clear, sodium overhead, and antimemetic chartreuse on the drip as the dominant tell",
        qa="verify the dose reads as 'baseline Class-A inoculation in progress' rather than as a generic IV; the chartreuse drip just beginning is the operational tell.",
    ),
    "MNR Class-B Inoculation Drill": dict(
        composition="Wide",
        ref="rembrandt_anatomy",
        location="a training room set with a row of practice dosing chairs",
        action="A wide view of a training room shows six staff members in scrubs practicing IV-line placement on each other in matched dosing chairs, an instructor walking the row with a chartreuse drill chart, all bags chartreuse, no patient on real treatment.",
        focus="the row of practicing pairs and the instructor with the chartreuse chart",
        mood="drill discipline, the dosage routine kept in muscle memory",
        palette="scrubs blue, chair-vinyl beige, fluorescent overhead, and antimemetic chartreuse on every drill IV bag",
        qa="verify the drill reads as 'practice run' rather than as live treatment; the matched pairs and chartreuse drill chart are the operational tells.",
    ),
    "MNR Cognitive Cleanse": dict(
        composition="Detail",
        ref="wright_air_pump",
        location="a clean-room dosing station with a single subject and a small instrument tray",
        action="A clean-room subject is seated under a single overhead lamp with a sequence of three chartreuse infusion bags hanging on a stand, a technician transferring the first bag's line from the bag to a forearm port.",
        focus="the three chartreuse bags on the stand and the technician's hand connecting the first line",
        mood="staged-cleanse discipline, the wash done in three timed passes",
        palette="clean-room white, bag-stand chrome, sodium overhead, and antimemetic chartreuse on all three bags as the dominant tell",
        qa="verify the cleanse reads as 'three-stage mnestic protocol' rather than as a generic chemo drip; the three bags on the stand are the staged-process tell.",
    ),
    "MNR Cold Storage Open": dict(
        composition="Detail",
        ref="whiteread_ghost",
        location="the antechamber of a cold-storage vault",
        action="A heavy cold-storage door is rolled half-open into the antechamber, the interior fog spilling slowly across the threshold, a single archivist standing at the boundary with a chartreuse-tabbed binder and a respirator pulled down to their neck.",
        focus="the half-open vault door, the spilling fog, and the archivist at the boundary",
        mood="storage breach discipline, the cold opened on purpose",
        palette="vault-door steel, fog white, antechamber concrete, sodium overhead, and antimemetic chartreuse on the binder tab",
        qa="verify the storage open reads as 'controlled cold-vault access' rather than as a sci-fi spaceship door; the archivist's posture and the chartreuse binder are the operational tells.",
    ),
    "MNR Cold Trail Reopened": dict(
        composition="Aftermath",
        ref="hopper_office",
        location="an analyst's desk where an old file has just been re-pulled",
        action="A desk under a single banker's lamp holds an old brown banker's box pulled out of dust, a sheaf of yellowed papers fanned across the desktop, a fresh chartreuse-tabbed note clipped to the top sheet, and a coffee that just got poured.",
        focus="the dusty banker's box, the yellowed papers, and the fresh chartreuse-tabbed note",
        mood="case reopened, the cold trail picked back up after years",
        palette="banker's lamp brass-green, paper-yellow, box-brown, desk-pine, and antimemetic chartreuse on the new note",
        qa="verify the trail reopened reads as 'old case freshly reopened tonight' rather than as a movie research moment; the dusty box and the fresh chartreuse note are the timestamp.",
    ),
    "MNR Conference Redaction": dict(
        composition="Action",
        ref="wall_insomnia",
        location="a long conference table mid-redaction at end of meeting",
        action="Two clerks in shirt-sleeves stand on opposite sides of a long conference table, both drawing fat black redaction bars across the same set of pages with chartreuse-handled markers, the rest of the meeting already departed.",
        focus="the two clerks' hands drawing redaction bars with chartreuse-handled markers",
        mood="redaction in progress, the meeting being erased in two-clerk pairs",
        palette="table-pine, dress-shirt cream, marker-black, fluorescent overhead, and antimemetic chartreuse on the marker handles",
        qa="verify the redaction reads as 'mid-erasure work' rather than as office vandalism; the two-clerk pairing with chartreuse markers is the operational tell.",
    ),
    "MNR Department Roll Call": dict(
        composition="Wide",
        ref="de_maria_kilometer",
        location="a long roll-call line in a corridor",
        action="A wide view of a corridor shows forty Foundation staff lined up at right angles to the camera, a coordinator at one end with a chartreuse clipboard ticking off names, each staffer holding a paper drug cup, four conspicuous gaps in the line.",
        focus="the long roll-call line, the coordinator with the chartreuse clipboard, and the four conspicuous gaps",
        mood="institutional census discipline, the count taken against the gaps",
        palette="corridor fluorescent, dress-shirt cream, carpet navy, and antimemetic chartreuse on the clipboard and every drug cup",
        qa="verify the roll call reads as 'departmental headcount with antimemetic gaps' rather than as a fire drill; the four gaps in the line are mandatory and the chartreuse clipboard is the operational tell.",
    ),
    "MNR Director's Memo": dict(
        composition="Detail",
        ref="calle_hotel",
        location="a clerk's intake desk in front of the AD's office",
        action="A clerk's intake desk holds a single open manila envelope, a folded sheet of memo paper half-pulled out, a chartreuse wax seal broken on the desk beside the envelope, a gloved hand still on the folded sheet.",
        focus="the open envelope, the folded memo, the broken chartreuse wax seal, and the gloved hand",
        mood="directive arrival, the memo just read by a clerk on the AD's behalf",
        palette="desk-pine, envelope manila, memo cream, fluorescent overhead, and antimemetic chartreuse on the broken wax seal as the dominant tell",
        qa="verify the memo reads as 'just received and just read by the gatekeeper clerk' rather than as a movie envelope; the broken chartreuse wax seal is the operational tell.",
    ),
    "MNR Found Files": dict(
        composition="Aftermath",
        ref="register_open_diner",
        location="a clerk's desk in a small files annex",
        action="A clerk's desk in the files annex holds a small dusty box pulled out of a drawer that had not been opened in years, three thin dossiers fanned across the desktop, a chartreuse-tabbed sticky note clipped to the top dossier reading nothing legible.",
        focus="the dusty box, the three fanned dossiers, and the chartreuse-tabbed sticky note",
        mood="recovery discipline, the files surfaced from a forgotten drawer",
        palette="box-brown, paper-cream, desk-pine, fluorescent overhead, and antimemetic chartreuse on the sticky note as the recovery tell",
        qa="verify the found files read as 'recovered from antimemetic obscurity tonight' rather than as a generic archive moment; the dusty box and the chartreuse-tabbed sticky note are the operational tells.",
    ),
    "MNR Headcount Audit": dict(
        composition="Detail",
        ref="degas_ironing",
        location="a coordinator's stand-up desk at the end of a corridor",
        action="A coordinator at a stand-up desk runs a chartreuse-tipped pen down a printed roster, three names struck through with a single horizontal stroke, the corridor staff visible in soft focus down the hall behind.",
        focus="the coordinator's pen mid-strike on the roster, three names already struck",
        mood="bureaucratic loss accounting, the count taken honestly",
        palette="desk-pine, roster cream, fluorescent overhead, and antimemetic chartreuse on the pen and the struck names",
        qa="verify the audit reads as 'departmental headcount being reduced one name at a time' rather than as a corporate layoff; the chartreuse pen mid-strike is the operational tell.",
    ),
    "MNR Inoculation Schedule": dict(
        composition="Detail",
        ref="hopper_office",
        location="a coordinator's office wall with a large schedule grid",
        action="A coordinator at a low desk faces a large wall-mounted schedule grid filled with rows of names and times, the coordinator's hand adding a new row with a chartreuse marker, a small tray of paper drug cups at the desk corner.",
        focus="the coordinator's hand adding to the schedule grid with the chartreuse marker",
        mood="scheduling discipline, the inoculation routine maintained one entry at a time",
        palette="schedule grid pale, dress-shirt cream, fluorescent overhead, and antimemetic chartreuse on the marker and the drug cups",
        qa="verify the schedule reads as 'scheduling-grid being kept current' rather than as a calendar shot; the chartreuse marker and the drug-cup tray are the operational tells.",
    ),
    "MNR Inoculation Wave": dict(
        composition="Wide",
        ref="rembrandt_anatomy",
        location="the inoculation bay during a wave-dosing event",
        action="A wide view of the inoculation bay shows fourteen dosing chairs simultaneously in use, three technicians moving between them with carts of chartreuse infusion bags, every IV-line newly placed, the bay in full coordinated operation.",
        focus="the bay full of dosing chairs in simultaneous use and the three technicians on carts",
        mood="mass-dosing discipline, the wave moving through scheduled staff",
        palette="bay-tile gray, chair-vinyl beige, fluorescent overhead, and antimemetic chartreuse on every infusion bag as the dominant tell",
        qa="verify the wave reads as 'mass coordinated mnestic dosing' rather than as an emergency response; every chair occupied and chartreuse IV bags on each is the operational tell.",
    ),
    "MNR Mass Remembrance": dict(
        composition="Wide",
        ref="saville_propped",
        location="the cognitive anchor array during a mass-recall event",
        action="A wide view of the cognitive anchor array shows twelve seated subjects in head-frames simultaneously connected to the ring of brass anchors, three technicians at panel stations, every IV-cuff chartreuse, oscilloscope monitors all showing rising green traces.",
        focus="the ring of twelve seated subjects, the brass anchors, and the rising green oscilloscope traces",
        mood="mass-recall discipline, the array bringing twelve memories back at once",
        palette="array-chrome, brass anchors, monitor-green, sodium overhead, and antimemetic chartreuse on every IV cuff",
        qa="verify the remembrance reads as 'coordinated mass mnestic recall' rather than as a sci-fi resurrection; the twelve seated subjects and rising green traces are the operational tells.",
    ),
    "MNR Memo Disposal": dict(
        composition="Detail",
        ref="bechtle_olds",
        location="a basement document incinerator slot in a hallway",
        action="A gloved hand feeds a single folded manila memo into a stainless slot in a hallway wall, the slot above a small green status light, a small stack of further memos under the same hand waiting their turn.",
        focus="the gloved hand feeding the memo into the slot and the small waiting stack",
        mood="quiet disposal discipline, the memos burned one at a time",
        palette="hallway concrete, slot-steel, gloved-hand blue, fluorescent overhead, and antimemetic chartreuse on the small status light",
        qa="verify the disposal reads as 'quiet routine memo destruction' rather than as cinematic shredding; the gloved hand and the small chartreuse status light are the operational tells.",
    ),
    "MNR Memory Triage": dict(
        composition="Detail",
        ref="freud_benefits",
        location="a triage station in a recall recovery bay",
        action="A nurse-style technician at a small triage desk fills out a chartreuse-tabbed assessment form, a seated patient mid-recall on a chair beside the desk with one hand still at temple, an IV line and a small drug cup at the patient's elbow.",
        focus="the technician's hand on the chartreuse-tabbed form and the patient mid-recall beside",
        mood="triage discipline, the recall sorted patient by patient",
        palette="desk-pine, chair-vinyl beige, fluorescent overhead, and antimemetic chartreuse on the form tab and the drug cup",
        qa="verify the triage reads as 'recall recovery being sorted patient by patient' rather than as an ER scene; the chartreuse-tabbed form and the drug cup are the operational tells.",
    ),
    "MNR Memory-Holed Audit": dict(
        composition="Aftermath",
        ref="de_maria_kilometer",
        location="an audit annex where files have already been disposed",
        action="A long annex desk holds a single open audit ledger and a tray with the burnt corners of forty manila tab strips, the room otherwise austere, the ledger's open page showing a column of chartreuse-tabbed entries each struck through.",
        focus="the audit ledger with struck-through entries and the tray of burnt tab corners",
        mood="memory-holed accounting, the audit kept honest by burning what it counts",
        palette="ledger cream, tray-steel, desk-pine, fluorescent overhead, and antimemetic chartreuse on the struck entries",
        qa="verify the audit reads as 'antimemetic file disposal audited honestly' rather than as a cover-up scene; the ledger of struck entries and the burnt-corner tray are the operational tells.",
    ),
    "MNR Mnestic Counter-Raid": dict(
        composition="Action",
        ref="wall_insomnia",
        location="a corridor at night under emergency sodium light",
        action="Three operatives in tactical earth tones move down a corridor in formation, the lead with a hand on a door handle and the second deploying a chartreuse-canistered aerosol fogger, the third holding a clipboard.",
        focus="the lead's hand on the door, the fogger canister, and the clipboard-holder behind",
        mood="counter-raid discipline, the team going in with practiced order",
        palette="corridor sodium amber, tactical earth tones, fogger-canister steel, and antimemetic chartreuse on the canister label and the clipboard tab",
        qa="verify the counter-raid reads as 'mid-deployment three-person stack' rather than as a SWAT photo; the chartreuse fogger canister is the operational tell.",
    ),
    "MNR Mnestic Counter-Strike": dict(
        composition="Action",
        ref="tooker_bureau",
        location="the cognitive anchor array in active counter-strike mode",
        action="A close-mid view of the anchor array shows three operators at panel stations slamming chartreuse-keyed levers down in sequence, monitors showing sharp green spikes, sodium emergency lights flashing.",
        focus="the three hands on the chartreuse-keyed levers and the spike on the monitors",
        mood="strike discipline, the array fired in coordinated sequence",
        palette="panel matte black, monitor green-spike, sodium-red emergency flash, and antimemetic chartreuse on the levers as the operational tell",
        qa="verify the counter-strike reads as 'mid-coordinated array discharge' rather than as missile-launch theater; the chartreuse-keyed levers and the sharp green spikes are the operational tells.",
    ),
    "MNR Mnestic Dust Cloud": dict(
        composition="Wide",
        ref="crewdson_beneath_roses",
        location="a hallway intersection under emergency conditions",
        action="A wide view of a hallway intersection shows a chartreuse aerosol dust cloud already spreading through the space, two operatives in respirators advancing into the cloud with clipboards out, the lights overhead haloed by the dust.",
        focus="the chartreuse aerosol dust cloud and the two respirator-clad operatives advancing",
        mood="atmospheric discipline, the cloud deployed to anchor what was about to be forgotten",
        palette="hallway sodium amber, dust haze, respirator black, and antimemetic chartreuse on the dust cloud as the dominant tell",
        qa="verify the dust cloud reads as 'mnestic aerosol deployment' rather than as a smoke grenade; the chartreuse haze and the clipboard-carrying operatives are the operational tells.",
    ),
    "MNR Mnestic Quarantine": dict(
        composition="Wide",
        ref="kollwitz_survivors",
        location="a quarantine room corridor with a sealed observation window",
        action="A wide view of a corridor shows a long sealed observation window into a quarantine room where six bystanders sit on benches each with a chartreuse-bagged IV pole, a coordinator outside with a clipboard, the window flagged with chartreuse hazard tape.",
        focus="the row of six bystanders inside with chartreuse IV bags and the coordinator outside",
        mood="quarantine discipline, the bystanders held under mnestic pressure for the duration of the event",
        palette="corridor fluorescent, window glass, civilian-clothes earth tones, and antimemetic chartreuse on the IV bags and hazard tape",
        qa="verify the quarantine reads as 'civilian mnestic quarantine in progress' rather than as a biohazard scene; the chartreuse IV bags and the coordinator with the clipboard are the operational tells.",
    ),
    "MNR Office Memo": dict(
        composition="Detail",
        ref="hopper_automat",
        location="an open-plan office desk during the afternoon",
        action="A staff member in shirt-sleeves stands at an open-plan desk and lifts a single folded office memo from an in-tray, eyes already starting to read, a paper drug cup still in their other hand.",
        focus="the staffer's hand lifting the memo and the drug cup in the other hand",
        mood="routine bureaucratic moment, the memo received and read in real time",
        palette="desk-pine, dress-shirt cream, fluorescent overhead, and antimemetic chartreuse on the drug cup",
        qa="verify the memo reads as 'mid-receipt of office memo' rather than as a dramatic letter; the in-tray, the drug cup, and the casual posture are the operational tells.",
    ),
    "MNR Operative Erasure": dict(
        composition="Aftermath",
        ref="walker_evans_objects",
        location="an operator-ready locker room",
        action="A row of operator lockers stands open, one specific locker swept entirely empty, the chair in front of it pushed in, a paper drug cup left on the bench seat, a small chartreuse-coded badge in the cup.",
        focus="the empty locker, the pushed-in chair, the paper drug cup, and the chartreuse-coded badge",
        mood="erasure discipline, the operative removed from the roster overnight",
        palette="locker beige, bench wood, fluorescent overhead, and antimemetic chartreuse on the badge in the cup",
        qa="verify the erasure reads as 'operative struck from the roster overnight' rather than as a retirement; the chartreuse-coded badge in the drug cup is the operational tell.",
    ),
    "MNR Overexposure Probe": dict(
        composition="Detail",
        ref="wright_air_pump",
        location="a small dosing station mid-probe in the inoculation bay",
        action="A close-mid view of a probe station shows a seated staff member with two IV-lines simultaneously connected to two chartreuse bags, a technician adjusting a third stand mid-prep, sodium overhead.",
        focus="the two simultaneous IV lines, the two chartreuse bags, and the technician's hand on the third",
        mood="probe discipline, the dosage taken past nominal to find the edge",
        palette="bay-tile gray, chair-vinyl beige, sodium overhead, and antimemetic chartreuse on the two and the third bags as the dominant tell",
        qa="verify the probe reads as 'double-saturation overexposure probe' rather than as a torture scene; the two IV lines and the third bag mid-prep are the operational tells.",
    ),
    "MNR Pattern Disruption": dict(
        composition="Detail",
        ref="tooker_bureau",
        location="a desk in front of a wall-mounted pattern board",
        action="A close-mid view of a pattern board on the wall shows a string-and-pin network being deliberately cut by an analyst's hand, the chartreuse pins falling onto the desk below as the strings drop.",
        focus="the analyst's hand mid-cut on the string network and the chartreuse pins falling",
        mood="disruption discipline, the antimemetic pattern being broken on purpose",
        palette="pinboard cork, string-red, desk-pine, fluorescent overhead, and antimemetic chartreuse on the falling pins",
        qa="verify the disruption reads as 'antimemetic pattern being actively broken' rather than as office vandalism; the falling chartreuse pins are the operational tell.",
    ),
    "MNR Pattern Recognition Drill": dict(
        composition="Wide",
        ref="shore_meeting",
        location="a training room set with rows of paired desks",
        action="A wide view of a training room shows eight pairs of trainees at facing desks reviewing identical chartreuse-tabbed pattern booklets, an instructor walking the center aisle with a stopwatch.",
        focus="the rows of paired trainees with chartreuse-tabbed booklets and the instructor on the aisle",
        mood="drill discipline, the recognition exercise practiced as muscle memory",
        palette="desk-pine, trainee-shirt cream, fluorescent overhead, and antimemetic chartreuse on every booklet tab",
        qa="verify the drill reads as 'pattern-recognition training exercise' rather than as a test; the chartreuse-tabbed booklets and the instructor with the stopwatch are the operational tells.",
    ),
    "MNR Reconstruction Project": dict(
        composition="Detail",
        ref="walker_evans_objects",
        location="a reconstruction analyst's wide desk in a small annex room",
        action="A long desk in a small annex holds fragments of dossier pages laid out in rough order, an analyst's hands taping two pieces together with chartreuse-marked archival tape, a paper drug cup at the edge.",
        focus="the analyst's hands taping the fragments with the chartreuse-marked archival tape",
        mood="reconstruction discipline, the lost record put back one fragment at a time",
        palette="paper cream, desk-pine, fluorescent overhead, and antimemetic chartreuse on the archival tape and the drug cup",
        qa="verify the reconstruction reads as 'antimemetic record reassembly in progress' rather than as a forensic crime lab; the chartreuse-marked archival tape and the drug cup are the operational tells.",
    ),
    "MNR Records Burn": dict(
        composition="Action",
        ref="hopper_office",
        location="a basement incineration room with a single furnace door",
        action="A clerk in coveralls feeds a stack of manila dossiers one by one into an open furnace door at the back of a basement room, the furnace glow lighting their face from below, a small chartreuse-tabbed acknowledgment slip clipped to their cuff.",
        focus="the clerk's hand feeding a dossier into the furnace and the chartreuse-tabbed slip on the cuff",
        mood="disposal discipline, the records ended on purpose with a clerk's signature",
        palette="furnace-glow orange-red, coverall beige, basement concrete, and antimemetic chartreuse on the cuff slip",
        qa="verify the records burn reads as 'authorized institutional incineration' rather than as a movie cover-up; the chartreuse-tabbed acknowledgment slip on the cuff is the operational tell.",
    ),
    "MNR Rotation Drill": dict(
        composition="Wide",
        ref="shore_meeting",
        location="a shift-change room with two rows of facing chairs",
        action="A wide view of a shift-change room shows ten staff in dress shirts shifting from one row to the other in a single coordinated rotation, each holding a clipboard and a paper drug cup, a coordinator at the end with a chartreuse stopwatch.",
        focus="the ten staff mid-rotation between two rows and the coordinator with the chartreuse stopwatch",
        mood="rotation discipline, the briefing-shift drilled to muscle memory",
        palette="dress-shirt cream, chair-navy, fluorescent overhead, and antimemetic chartreuse on the stopwatch face",
        qa="verify the rotation reads as 'shift-rotation drill in progress' rather than as a corporate game; the coordinated movement and the chartreuse stopwatch are the operational tells.",
    ),
    "MNR Selective Forgetting": dict(
        composition="Detail",
        ref="thiebaud_counter",
        location="a small precise dosing station in the inoculation bay",
        action="A close-mid view shows a technician dialing a chartreuse-coded valve on an infusion line one quarter of a turn, a single seated subject mid-dose with the technician's other hand on the subject's wrist for pulse.",
        focus="the technician's hand on the chartreuse-coded valve and the other on the pulse",
        mood="selective discipline, the dose dialed to one quarter of a turn",
        palette="bay-tile gray, valve-chrome, chair-vinyl beige, sodium overhead, and antimemetic chartreuse on the valve and the bag",
        qa="verify the dose reads as 'precision quarter-turn selective forgetting protocol' rather than as a generic IV; the chartreuse-coded valve and the pulse hand are the operational tells.",
    ),
    "MNR Standard Protocol Refresh": dict(
        composition="Detail",
        ref="degas_ironing",
        location="a coordinator's stand-up desk by a wall-mounted protocol board",
        action="A coordinator at a stand-up desk pins a fresh chartreuse-tabbed protocol card onto a board that already holds twelve identical cards in a grid, one older card lifted in their other hand mid-replace.",
        focus="the coordinator's hand pinning the new chartreuse-tabbed protocol card",
        mood="refresh discipline, the standard kept current one card at a time",
        palette="board cork brown, protocol-card cream, desk-pine, fluorescent overhead, and antimemetic chartreuse on the new tab",
        qa="verify the refresh reads as 'standard protocol being kept current' rather than as a craft project; the chartreuse-tabbed protocol card is the operational tell.",
    ),
    "MNR Untrained Assignment": dict(
        composition="Reaction",
        ref="wyeth_christina",
        location="a new-assignment intake desk in an unfamiliar wing",
        action="An untrained staff member in shirt-sleeves stands at an intake desk holding a single chartreuse-tabbed dossier they have just been handed, looking past the desk down a corridor of unfamiliar doors with patient confusion.",
        focus="the staffer holding the chartreuse-tabbed dossier and looking down the unfamiliar corridor",
        mood="assignment discipline, the staffer handed a file they were not trained to read",
        palette="dress-shirt cream, intake-desk pine, corridor fluorescent, and antimemetic chartreuse on the dossier tab",
        qa="verify the assignment reads as 'untrained staffer at unfamiliar intake' rather than as a tourist; the chartreuse-tabbed dossier and the patient confusion are the tells.",
    ),
    "MNR Walk-Out Order": dict(
        composition="Action",
        ref="wall_insomnia",
        location="an open-plan office mid-evacuation",
        action="A senior coordinator at the center of an open-plan office signals a walk-out by raising a chartreuse-tabbed printed slip overhead, the staff at surrounding desks all rising and lifting jackets in coordinated motion, the room emptying in real time.",
        focus="the coordinator's raised chartreuse-tabbed slip and the staff rising in coordinated motion",
        mood="walk-out discipline, the office evacuated cleanly on a single signal",
        palette="open-plan beige, jacket-navy, dress-shirt cream, fluorescent overhead, and antimemetic chartreuse on the raised slip",
        qa="verify the walk-out reads as 'coordinated evacuation on a single signal' rather than as panic; the raised chartreuse-tabbed slip and the simultaneous rising are the operational tells.",
    ),
    "MNR Witness Erasure": dict(
        composition="Detail",
        ref="freud_self",
        location="a small dosing booth at the edge of the inoculation bay",
        action="A close-mid view of a small dosing booth shows a civilian witness in a single chair receiving a measured chartreuse drink from a paper drug cup held by a gloved hand from off-frame, eyes already losing focus.",
        focus="the witness's hand holding the drug cup, the gloved off-frame hand, and the unfocused eyes",
        mood="erasure discipline, the witness mnestically cleared one cup at a time",
        palette="booth-vinyl beige, civilian-clothes earth tones, fluorescent overhead, and antimemetic chartreuse on the drink in the cup as the dominant tell",
        qa="verify the erasure reads as 'witness amnestic dosing in progress' rather than as a poisoning scene; the chartreuse drink in the cup is the operational tell.",
    ),

    # === MANDATES (8) ===
    "MNR Mandate 1: Memory Hole": dict(
        composition="Witness POV",
        ref="wall_view_apartment",
        location="the AD's outer office threshold at the start of mandate execution",
        action="From a clerk's-shoulder vantage in the doorway, the camera sees a small ceremonial brass desk pedestal with a single Mandate 1 directive folder placed on it, the clerk's gloved hand still on the folder, the AD's empty chair beyond.",
        focus="the directive folder on the pedestal, the clerk's gloved hand, and the empty AD chair behind",
        mood="mandate arrival, the first directive placed and not yet acted on",
        palette="desk-pine, folder cream, pedestal-brass, sodium overhead, and antimemetic chartreuse on the folder's wax seal",
        qa="verify the mandate reads as 'directive arrival, AD chair empty' rather than as a portrait of the AD; the clerk-over-shoulder framing is mandatory.",
    ),
    "MNR Mandate 2: Total Erasure": dict(
        composition="Aftermath",
        ref="whiteread_house",
        location="a directorate hallway after a total-erasure event",
        action="A directorate hallway sits entirely empty, every door closed, every name placard removed from every door leaving only square outlines of slightly cleaner paint, the corridor lit by a single sodium fixture.",
        focus="the long hall of doors with every placard removed, leaving cleaner-paint outlines",
        mood="total erasure aftermath, the corridor stripped of who lived behind it",
        palette="hallway off-white, baseboard brown, sodium overhead, and antimemetic chartreuse on a single fallen placard tab on the carpet",
        qa="verify the total erasure reads as 'every door cleared of identification on a single mandate' rather than as a renovation; the cleaner-paint placard outlines and the single fallen chartreuse tab are the operational tells.",
    ),
    "MNR Mandate 3: Selective Forgetting": dict(
        composition="Witness POV",
        ref="hopper_new_york_office",
        location="a directorate viewing room overlooking the inoculation bay",
        action="From a directorate viewing room, the camera looks through tall glass down into the inoculation bay where every fourth dosing chair is occupied on a chartreuse drip, the others empty, a coordinator on the floor with a chartreuse-tabbed roster.",
        focus="the rhythm of every-fourth chair occupied below and the coordinator with the chartreuse roster",
        mood="selective directive, the dose given to a specifically counted subset",
        palette="viewing-room glass, bay below tile gray, dress-shirt cream, sodium overhead, and antimemetic chartreuse on the occupied chairs' IV bags",
        qa="verify the mandate reads as 'directive enacted as a selective dosing pattern below' rather than as an emergency response; the every-fourth occupancy pattern is mandatory.",
    ),
    "MNR Mandate 4: Mnestic Saturation": dict(
        composition="Wide",
        ref="rembrandt_anatomy",
        location="the inoculation bay during a saturation event",
        action="A wide view of the bay during a saturation event shows every chair occupied, two IV-lines per occupant, six technicians moving between them with rolling stands of chartreuse infusion bags, sodium overhead grid at full intensity.",
        focus="the bay at full occupancy with two IV-lines per occupant and six technicians moving",
        mood="saturation mandate, the dosage taken to ceiling on every staffer at once",
        palette="bay-tile gray, chair-vinyl beige, sodium-amber overhead, and antimemetic chartreuse on every IV bag as the dominant tell",
        qa="verify the saturation reads as 'mandated mass mnestic ceiling-dose' rather than as a hospital scene; two IV-lines per occupant is the directive tell.",
    ),
    "MNR Mandate 5: Inoculation Mandate": dict(
        composition="Wide",
        ref="kollwitz_survivors",
        location="a corridor lined with staff queuing for inoculation",
        action="A wide view down a corridor shows a long single file of Foundation staff queuing at a single dosing station at the far end, every staffer holding a paper drug cup already, the line orderly and quiet, a coordinator at the front with a chartreuse-tabbed clipboard.",
        focus="the long orderly queue with drug cups already in hand and the coordinator with the chartreuse clipboard",
        mood="mandated discipline, the inoculation universal and orderly",
        palette="corridor fluorescent, dress-shirt cream, carpet navy, and antimemetic chartreuse on every drug cup and the clipboard tab",
        qa="verify the mandate reads as 'universal mandated inoculation queue' rather than as a fire drill; the drug cups already in hand are the discipline tell.",
    ),
    "MNR Mandate 6: Memory Reform": dict(
        composition="Witness POV",
        ref="wall_view_apartment",
        location="a directorate reading room with a long polished table",
        action="From a doorway, the camera sees a long polished table covered with twelve reform-protocol folders open and side-by-side, two senior staff in dress shirts walking the table reading down the row, the AD chair at the head empty.",
        focus="the long table of twelve open reform-protocol folders, the two staff reading them, and the empty AD chair",
        mood="reform directive, the protocols being read into adoption",
        palette="table polish brown, folder cream, dress-shirt cream, sodium overhead, and antimemetic chartreuse on the AD chair's lanyard hanging on the backrest",
        qa="verify the mandate reads as 'reform protocols being adopted in directorate session' rather than as a tribunal; the empty AD chair with the chartreuse lanyard hanging is mandatory.",
    ),
    "MNR Mandate 7: Public Disclosure": dict(
        composition="Wide",
        ref="shore_meeting",
        location="a public-press conference room being prepared",
        action="A wide view of a press conference room shows rows of empty folding chairs facing a low stage with a single podium, microphones taped to the lectern, a stack of chartreuse-labeled briefing folders ready on a side table, the room not yet open to press.",
        focus="the empty press chairs facing the empty podium and the stack of chartreuse-labeled briefing folders",
        mood="public-disclosure readiness, the room set and not yet triggered",
        palette="hall fluorescent, chair gray, podium navy, and antimemetic chartreuse on the briefing folders as the dominant tell",
        qa="verify the disclosure reads as 'press room set, mandate not yet triggered' rather than as a press event in progress; the empty chairs and chartreuse folders on the side table are mandatory.",
    ),
    "MNR Mandate 8: Cold-Open Inquiry": dict(
        composition="Witness POV",
        ref="hopper_new_york_office",
        location="the corridor outside a sealed inquiry committee room",
        action="From a corridor vantage, the camera sees the closed door of a committee room with a chartreuse-keyed badge reader green-lit beside it, a single security guard standing post in front of the door with hands folded, the corridor otherwise empty.",
        focus="the closed door, the chartreuse-lit badge reader, and the single guard standing post",
        mood="cold-open inquiry, the door sealed and the body of the mandate consigned to the closed room",
        palette="corridor sodium amber, door-paint cream, guard-uniform navy, and antimemetic chartreuse on the badge reader as the dominant tell",
        qa="verify the inquiry reads as 'sealed committee room with mandated cold-open access' rather than as a generic locked door; the chartreuse-lit badge reader and the single guard standing post are mandatory.",
    ),
}


# === Slice composition ===
# slice-01: all 24 anomalies + all 16 facilities = 40 cards
# slice-02: all 30 personnel + first 10 procedures (alphabetical) = 40 cards
# slice-03: remaining 32 procedures + all 8 mandates = 40 cards
SLICE_PLAN = [
    ("slice-01", "anomalies + facilities", ["SCP_ANOMALY", "SCP_FACILITY"], None),
    ("slice-02", "personnel + first 10 procedures", ["SCP_PERSONNEL", "SCP_PROCEDURE"], 10),
    ("slice-03", "remaining procedures + mandates", ["SCP_PROCEDURE", "SCP_MANDATE"], None),
]


def _palette_default(card: dict) -> str:
    return card.get("palette", "institutional beige, fluorescent overhead, archive-black, and antimemetic chartreuse as the antimemetic tell")


def _render_packet(manifest_entry: dict, source_index: int, creative: dict) -> dict:
    name = manifest_entry["name"]
    card_type = manifest_entry["types"][0]
    composition = creative["composition"]
    ref_key = creative["ref"]
    ref_title, ref_url, ref_traits = REFS[ref_key]
    location = creative["location"]
    action = creative["action"]
    focus = creative["focus"]
    mood = creative["mood"]
    palette = _palette_default(creative)
    qa = creative["qa"]
    extra_note = creative.get("note")
    type_dir = TYPE_DIRECTION[card_type]

    comp_phrase = f"{composition} - {COMP_NOTE[composition]}"
    if extra_note:
        comp_phrase = f"{composition} - {COMP_NOTE[composition]}; {extra_note}"

    final_prompt = (
        f"Square 1024x1024 original SCP-inspired trading card illustration for "
        f"{name}. Card type direction: {type_dir}. Setting/faction: "
        f"{SETTING_FACTION}; location: {location}. Action: {action} "
        f"Focus: {focus}. Composition rotation: {comp_phrase}. Mood: {mood}. "
        f"Palette: {palette}. Reference-trait borrow only: {ref_traits}. "
        f"Use painterly cinematic realism, practical concrete/steel/glass "
        f"materials, readable card-size silhouette, strong value contrast, "
        f"and abstract document/redaction shapes only. Illustration only, no "
        f"readable text, no logos, no card frame."
    )

    return {
        "name": name,
        "source_index": source_index,
        "expansion_code": "MNR",
        "archetype": manifest_entry["archetype"],
        "types": list(manifest_entry["types"]),
        "subtypes": list(manifest_entry["subtypes"]),
        "target_path": manifest_entry["target_path"],
        "composition_rotation": composition,
        "setting_faction": SETTING_FACTION,
        "card_type_direction": type_dir,
        "location": location,
        "action": action,
        "focus": focus,
        "mood": mood,
        "artist_reference_title": ref_title,
        "artist_reference_url": ref_url,
        "reference_traits": ref_traits,
        "final_prompt": final_prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "qa_notes": qa,
    }


def main() -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cards = data.get("cards") or data.get("entries") or data
    mnr_entries = [c for c in cards if c.get("expansion_code") == "MNR"]
    assert len(mnr_entries) == 120, f"expected 120 MNR entries, got {len(mnr_entries)}"

    # Validate all CARDS keys correspond to manifest names
    manifest_names = {c["name"] for c in mnr_entries}
    missing_in_creative = manifest_names - CARDS.keys()
    extra_in_creative = CARDS.keys() - manifest_names
    assert not missing_in_creative, f"creative dict missing: {sorted(missing_in_creative)}"
    assert not extra_in_creative, f"creative dict has extras: {sorted(extra_in_creative)}"

    # Group manifest entries by type
    by_type: dict[str, list[dict]] = {}
    for c in mnr_entries:
        by_type.setdefault(c["types"][0], []).append(c)
    # Stable name order
    for t in by_type:
        by_type[t].sort(key=lambda c: c["name"])

    out_dir = Path(__file__).resolve().parent
    next_index = 0
    slice_results: list[tuple[str, list[dict]]] = []

    # Pre-sorted procedure list for slice-02 spillover
    procedures_sorted = list(by_type["SCP_PROCEDURE"])
    procedures_consumed = 0

    for slice_name, _label, type_set, proc_cap in SLICE_PLAN:
        slice_packets = []
        for t in type_set:
            entries = list(by_type[t])
            if t == "SCP_PROCEDURE" and proc_cap is not None:
                # take first N procedures (alphabetical) for slice-02
                entries = procedures_sorted[:proc_cap]
                procedures_consumed = proc_cap
            elif t == "SCP_PROCEDURE" and proc_cap is None and slice_name == "slice-03":
                entries = procedures_sorted[procedures_consumed:]
            for entry in entries:
                creative = CARDS[entry["name"]]
                packet = _render_packet(entry, next_index, creative)
                slice_packets.append(packet)
                next_index += 1
        slice_results.append((slice_name, slice_packets))

    # Write slice JSON files
    for slice_name, packets in slice_results:
        out_path = out_dir / f"{slice_name}-packets.json"
        out_path.write_text(json.dumps(packets, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path.name} ({len(packets)} packets)")

    # Summary numbers
    total = sum(len(packets) for _, packets in slice_results)
    print(f"total packets: {total}")
    assert total == 120, f"expected 120 total, got {total}"


if __name__ == "__main__":
    main()
