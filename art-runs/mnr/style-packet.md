# MNR (Mnestic Reset) Card Art Style Packet

Run date: 2026-05-13

Extends `art-runs/scp/style-packet.md`. Everything in the SCP base packet still applies (painterly cinematic realism, readable card-size silhouette, no readable text / no logos / no card frame, abstract document and redaction shapes only). The rules below add the antimemetic-cold-war layer that makes MNR specifically MNR.

## Source Notes

- MNR set manifest: `frontend/public/scp_art_manifest.json` filtered to `expansion_code == "MNR"` yields 120 cards: 24 anomalies, 16 facilities, 30 personnel, 42 procedures, 8 mandates.
- Theme inspiration: qntm, *There Is No Antimemetics Division*. Antimemes are ideas the mind cannot retain. The Antimemetics Division loses agents to anomalies that, by definition, nobody can confirm exist. Mnestic drugs are the only intervention that lets staff act on what they have already forgotten.
- Public reference: qntm's novel and short fiction, `https://qntm.org/scp`.
- Visual idiom is bureaucratic-realist: office air, fluorescent lighting, beige folders, ballpoint pens, name badges. The bureaucracy itself is the horror.
- Mnestic-grade pharmaceutical accent: antimemetic chartreuse, the color of generic-amphetamine bottles in a Walgreens pharmacy aisle (pale yellow-green plastic labeling). Use sparingly, as the tell that mnestic intervention has happened.

## Core Fantasy (MNR-specific)

Original SCP-inspired containment art viewed through the qntm lens of a quiet cognitive cold war. The pieces in your hand are not creature designs; they are the empty conference room after everyone forgot the meeting, the IV bag dripping mnestic saturation into a tired analyst's arm, the office cubicle where someone used to sit, the file cabinet missing one drawer that nobody can name.

The set should feel like a documentary photographer accidentally got into a Foundation site at 3am and shot what they could remember the next morning. Painterly, cinematic, emotionally specific, and almost never centered on a monster.

## MNR-Specific Visual Rules

- **Blank spaces with shape.** Compositions should include obvious negative space where something should be: an outline that leads nowhere, a desk with no chair behind it, a hallway where one section is missing but the carpet continues uninterrupted.
- **People looking at things they cannot see.** A favored MNR pose: a single figure staring at empty air with the patient confusion of someone who knows they forgot something important. Hands held out toward nothing. The figure's expression is the focus, not the absent object.
- **Mnestic drug imagery.** Practical bureaucratic objects: pill bottles, IV bags, blister packs of orange capsules, tongue strips, paper drug cups, sublingual sprays, medical clipboards. When mnestic intervention is the subject, render the actual pharmaceutical hardware.
- **Memory holes and blind spots.** File cabinets with missing drawers. Conference rooms with empty chairs facing each other across an empty table. Hallways where one section is gone but the carpet continues. Photographs with a single figure cut out, leaving a person-shaped hole.
- **Bystander Effect.** The MNR civilian is the office worker who is about to die without realizing it. Ordinary clothes, ordinary lighting, looking at something the camera does not show. Coffee cup still in hand. The horror is that they look like everyone you have ever worked with.
- **Bureaucratic warmth.** Yellow fluorescent ceiling lighting, beige paper, ballpoint pens, monitors with green-on-black text, name badges, lanyards, coffee maker rings on desks, donut boxes, breakroom tables. The institutional everyday is the canvas.
- **One palette accent: antimemetic chartreuse.** A pale, sickly yellow-green keyed to the labels on mnestic-grade pharmaceutical bottles. Use as a single accent per card whenever mnestic intervention has occurred, is occurring, or has just failed. A pill cup. A label. The wash of a sodium lamp filtered through medical glass. Never the dominant; always the tell.

## MNR Composition Rotation (mandatory variety)

Across every slice, rotate the following five primary modes. No mode should appear more than twice in a row within a slice. Reaction and Action remain available from the SCP base rotation for cards whose subject is a human-posture response or operational motion respectively; they are secondary and should not crowd out the five primary modes.

- **Detail.** Tight foreground prop, hands, or instrument. The wider context (anomaly, room, witness) implied behind it. Favor practical objects: pill bottle, file folder, name badge, monitor edge, sealed envelope.
- **Wide.** Institutional space dwarfing the human. The Foundation as architecture. Empty corridors, atrium balconies, server rooms, archive stacks. Figures small enough that scale tells the story.
- **Aftermath.** Something has already happened and the evidence remains. Knocked-over chair. Open file cabinet, half-empty. The cup of coffee still warm. No motion in the frame; the motion was a minute ago.
- **Witness POV.** The camera occupies the position of an observer who should not be there. Behind glass. Through a door cracked open. Over a shoulder at a screen. The viewer is implicated.
- **Anomaly Implied.** The strange thing is barely visible: a shadow with no caster, a reflection that does not match, a chair imprint on a carpet where no chair stands, a hand-shape on a fogged window. Restraint over reveal.
- **Reaction** (secondary). Human posture foregrounded, the antimemetic situation read through the figure's response. Common for SCP_PERSONNEL cards where the role-under-pressure is the whole subject.
- **Action** (secondary). Dynamic diagonal staging with motion readable at card size. Common for SCP_PROCEDURE cards whose subject is an operational moment in progress.

The first card in this set's `final_prompt` must always specify which mode it is using, with a short note that distinguishes it from the rotation's name alone.

## Artist Reference Vocabulary

Trait sources only — do not request exact artist imitation, and do not copy source compositions. Vary across the 120 cards: no single reference should be reused more than ~3 times across the set.

- **Edward Hopper** (*Nighthawks*, *Office at Night*, *New York Office*, *Automat*) — institutional alienation, fluorescent and lamp light pooling in empty interiors, isolated figures in window light.
- **Vilhelm Hammershoi** (interior paintings, *Interior with Young Woman Seen from Behind*) — empty-room dread, muted gray palette, doorways into more empty rooms, figures with their backs turned.
- **Andrew Wyeth** (*Christina's World*, *The Helga Pictures*, *Wind from the Sea*) — figures looking at things unseen, dry land, isolated witnesses, paper-thin light through cheap curtains.
- **Mark Rothko** (color field) — blank-space studies as composition; useful for cards whose subject is absence itself.
- **Jeff Wall** (*Insomnia*, *Dead Troops Talk*, *A View from an Apartment*) — staged-bureaucratic photography, theatrical realism, large-format constructed scenes.
- **Gregory Crewdson** (*Cathedral of the Pines*, *Beneath the Roses*) — cinematic suburban dread, single figures in eerily lit interior tableaux.
- **Caspar David Friedrich** (*Wanderer above the Sea of Fog*, *Monk by the Sea*) — solitary witness compositions, the human dwarfed by what they observe.
- **Lucian Freud** (interior portraits, *Reflection (Self-Portrait)*, *Benefits Supervisor Sleeping*) — fluorescent flesh in office light, unflattering institutional skin tones, posture under exhaustion.
- **Rachel Whiteread** (*House*, *Untitled (Pink Torso)*, *Ghost*) — negative-space sculpture, casts of empty rooms, absence as object.
- **Walter De Maria** (*The Broken Kilometer*, *The New York Earth Room*) — repetitive bureaucratic objects as installation, scale through accumulation.
- **Sophie Calle** (*The Hotel*, *Take Care of Yourself*) — forensic-archival witness work, the everyday catalogued under surveillance.
- **Francisca Aanstoot, René Magritte** (*The Empire of Light*, *Time Transfixed*) — surreal-mundane: the impossible inserted into the ordinary without comment. Reserve for anomaly-implied compositions.
- **Robert Bechtle** (*Alameda Gran Torino*, *56 Olds*) — flat suburban realism, harsh midday light, photographic-painterly Americana for Bystander composition.
- **Jenny Saville** (large-scale portraiture) — institutional flesh, medical context, scale.
- **Stephen Shore** (color photographs, *Uncommon Places*) — beige Americana, motel light, banal interiors as horror canvas.

## Palette Bands (MNR-tuned)

Use one dominant plus antimemetic chartreuse accent where the card calls for it:

- fluorescent yellow-white, beige paper, dark-archive black + chartreuse pill
- gray hallway concrete, navy carpet, monitor green + chartreuse label
- breakroom tan, donut-box pink, coffee brown + chartreuse capsule cap
- archive black, manila folder beige, redacted black bars + chartreuse highlighter slash
- night-fluorescent green-white, ceiling-tile gray, window black + chartreuse IV bag
- pharmacy cabinet white, stainless steel, surgical blue + chartreuse pill-cup
- empty-office mauve, mid-century plaster, baseboard brown + chartreuse blister pack
- security-camera gray, parking-lot sodium amber, asphalt black + chartreuse safety vest stripe

## Expansion And Archetype Cues (MNR)

The MNR archetypes are sub-flavors of the antimemetic cold war:

- **mnestic_reset** — the moment the drug takes hold; a recall in progress. Show the seam where forgetting becomes remembering: the moment an analyst's pen pauses, the IV bag mid-drip, the file pulled back out of the burn bin.
- **mnestic_core** — operational mnestic discipline. Show the routine of staying remembered: agents on a saturation drip in the briefing room, archivists rotating their reading, badge swaps, daily inoculation lines.
- **mnestic_wake** — bystanders, the not-yet-inoculated, the recently-roused. Show ordinary office life with the camera lingering just long enough on the wrong corner. These are usually civilians or non-divisional staff.
- **antimeme_decay** — the anomaly winning. Show absence: missing furniture, blank documents, removed coworkers. The viewer should feel the gap before they identify it.
- **antimemetic** — generic antimemetic facility / artifact framing.
- **redaction_press** — active redaction in motion: black bars going down, files being burned, conference rooms emptying mid-meeting. Mood is aggressive and bureaucratic.
- **bystander_synergy** — the office machinery itself. Roll calls, headcount audits, memo trays. Pure bureaucracy as composition.
- **antimemetic_decay** — alias of antimeme_decay; treat the same.

## Card-Type Direction (MNR-tuned)

- **SCP_ANOMALY** — Show the anomaly's consequence, not its body. Many MNR anomalies are absences (Missing Floor, Stripped Conference Room, Bystander Effect). Render the place where it has acted, with at most an outline or shadow of the thing itself. Favor anomaly-implied composition.
- **SCP_PERSONNEL** — Show role under pressure through hands, posture, gear, and environment. Mnestic operatives carry IV stands, pill carousels, dosed clipboards. Bystander personnel are ordinary clothes and ordinary lighting and a half-second of confusion. Marion Wheeler, when she appears, is one specific exhausted woman with antimemetic chartreuse somewhere on her person (pill, lanyard, drink); not a hero pose.
- **SCP_FACILITY** — Show a place doing a job. MNR facilities are office spaces, briefing rooms, archives, inoculation bays, labs. Architecture should suggest the function (rows of dosing chairs in Inoculation Bay; ceiling-mounted speakers in Briefing Hall; identical filing cabinets in Pre-Amnestic Records).
- **SCP_PROCEDURE** — Show an action, an operational detail, or its consequence. Many MNR procedures are bureaucratic (Roll Call, Memo Disposal, Records Burn) or medical (Inoculation Wave, Mass Remembrance). Render the moment, not the diagram.
- **SCP_MANDATE** — Show directive-level imagery: the empty director's chair, the memo on the desk, the projector beam against an empty wall, the policy in physical form. Witness POV preferred; do not center the Director's body.

## Special-Handling Cards

These cards have specific composition / framing notes that must be respected:

- **MNR The Director's Note / The Director's Note (Containment Critical)** — Witness POV, not a hero shot of the Director. The composition should be over a clerk's shoulder reading the memo, or a hand placing the envelope, or the empty desk after the note has been delivered. Director's chair empty; the note is the protagonist.
- **MNR Marion Wheeler** — single specific woman, not a heroic action portrait. She is the protagonist of qntm's novel, an exhausted senior analyst on a mnestic regimen. Show her at a desk or in a corridor, with antimemetic chartreuse somewhere (a pill bottle on the desk, a lanyard, a paper drug cup). Reference: Lucian Freud / Hammershoi institutional portraiture, not action-hero framing.
- **MNR Bystander Effect** — the civilian about to die. They must look ordinary, not menaced. Coffee, cubicle, paperwork. The anomaly is implied; we do not see what they are looking at.
- **MNR Missing Floor / Missing Floor (Containment Critical)** — the elevator buttons, with a number absent or smudged, OR an architectural floor plan with one floor literally not drawn. Do not invent a CG impossible-architecture shot; lean institutional realism.
- **MNR Five and Three-Eighths** — a stairwell sign or elevator panel showing impossible numbering. Hand reaching for the button. Detail composition. Hopper / Bechtle.
- **MNR The Quiet Hour** — office at 3am with every chair pushed in, fluorescent buzz, single security camera. No people. Aftermath / wide. Hopper or Crewdson.
- **MNR White Hallway Recall** — a single long featureless white corridor with one figure paused mid-step, looking back at something. Anomaly Implied; Whiteread negative-space mood.
- **MNR Stripped Conference Room** — empty boardroom with the chairs facing each other across a polished table, sun coming in through blinds. Aftermath. Hammershoi.
- **MNR The Blank Folder / The Blank Folder (Severe)** — manila folder open on a desk; pages inside are completely blank, but the desk around it is normal (coffee, pen, sticky note). Detail. Sophie Calle.
- **MNR Mandate 7: Public Disclosure** — a press conference room being set up, but the seats are still empty, microphones taped to the lectern, antimemetic-chartreuse briefing folders stacked. The mandate hasn't been triggered yet; the room is the readiness.
- **MNR Mandate 8: Cold-Open Inquiry** — closed door of a committee room, security badge reader green-lit, single guard outside. Witness POV from the corridor. The body of the mandate is the closed door itself.

## Negative Prompt (identical across all 120 cards)

No readable words, letters, numbers, official SCP logo, Magic card frame, mana symbols, stat boxes, watermark, UI overlay, caption, title text, signature, copied source composition, exact artist imitation, comic mascot tone, clean spaceship aesthetic, repeated centered hallway monster.

## Style Reference Selection Criteria

The MNR pieces should be judged on:

- card-size readability of the focal subject
- MNR-specific subject clarity (institutional realism, antimemetic implication, mnestic accent placement)
- painterly cinematic quality without uncanny CG sheen
- variation across the slice — the cards should not collapse into the same beige corridor shot
- absence of text, logos, watermarks, card frames, UI
- restraint: when the subject is absence, the absence should be the protagonist
- bureaucratic specificity over generic horror — donut box on the breakroom table beats fog and dripping pipes

## QA Reminders

- Reject any output with readable documents, logos, watermarks, frames, captions, or copied source compositions.
- Antimemetic chartreuse should appear as the accent — a tell, not the dominant. If it dominates, regenerate.
- Bystanders must look like coworkers, not victims. Banal posture, banal clothes.
- When the card is The Director's Note, the Director's chair must remain empty; do not generate a portrait of the Director.
- When the card is Marion Wheeler, she must read as a specific senior analyst, not as an action-hero MTF operative.
- Anomaly cards should pass the "would I notice this is wrong from across the room?" test — the wrongness should be a held breath, not a jump scare.
