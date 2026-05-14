# MNR Slice 03 Production Notes

Generated card-level art packets for slice 03 only. No PNGs generated.

## Scope

- Source manifest: `frontend/public/scp_art_manifest.json` filtered to `expansion_code == "MNR"`.
- Output packets: `art-runs/mnr/production/slice-03-packets.json`
- Packet count: 40
- Theme: the protocols, the disposals, the mandates — bureaucracy as antimemetic instrument.

## Card-Type Breakdown

- SCP_PROCEDURE: 32 (the remaining procedures, alphabetical from Class-B Inoculation Drill through Witness Erasure)
- SCP_MANDATE: 8 (all MNR mandates 1 through 8)

## Composition Rotation

Slice-03 is operational and directive: procedures show the moment of action, mandates show directive residue (memos, sealed doors, empty desks). The rotation balances Detail (procedural specifics) with Wide (mass-event scale).

- Detail: 14 (hands on valves, pinning slides, feeding furnaces, taping fragments)
- Wide: 11 (mass dosing, anchor array discharge, queue lines, press rooms)
- Aftermath: 5 (Brief and Bury room, memory-holed audit, Mandate 2 stripped corridor)
- Action: 5 (Black-Bag Job, Counter-Raid, Counter-Strike, Records Burn, Walk-Out Order)
- Witness POV: 4 (three mandate cards via doorway/glass; Backchannel Brief alcove)
- Reaction: 1 (Untrained Assignment intake)

## Artist Reference Use

Trait sources only — final prompts forbid exact artist imitation and copying source compositions.

- 3x Rembrandt, The Anatomy Lesson of Dr Nicolaes Tulp — `https://www.mauritshuis.nl/en/our-collection/artworks/146-the-anatomy-lesson-of-dr-nicolaes-tulp`
- 3x Edward Hopper, Office at Night — `https://collections.walkerart.org/object/1599`
- 3x Jeff Wall, Insomnia — `https://www.tate.org.uk/art/artworks/wall-insomnia-p20198`
- 3x Stephen Shore, Meeting Room — `https://www.303gallery.com/artists/stephen-shore`
- 2x Joseph Wright of Derby, An Experiment on a Bird in the Air Pump — `https://www.nationalgallery.org.uk/paintings/joseph-wright-of-derby-an-experiment-on-a-bird-in-the-air-pump`
- 2x Walter De Maria, The Broken Kilometer — `https://www.diaart.org/visit/visit/walter-de-maria-the-broken-kilometer`
- 2x Edgar Degas, A Woman Ironing — `https://www.nga.gov/artworks/46640`
- 2x George Tooker, Government Bureau — `https://www.metmuseum.org/art/collection/search/485874`
- 2x Kathe Kollwitz, The Survivors — `https://sammlung.staedelmuseum.de/en/work/the-survivors`
- 2x Walker Evans, Penny Picture Display, Savannah — `https://www.moma.org/collection/works/49891`
- 2x Jeff Wall, A View from an Apartment — `https://www.tate.org.uk/art/artworks/wall-a-view-from-an-apartment-t12446`
- 2x Edward Hopper, New York Office — `https://www.mfah.org/art/detail/27543`
- 1x each: Whiteread Ghost, Sophie Calle The Hotel, John Register Open Diner, Jenny Saville Propped, Bechtle '56 Olds, Freud Benefits Supervisor Sleeping, Crewdson Beneath the Roses, Hopper Automat, Thiebaud Bakery Counter, Wyeth Christina's World, Freud Self-Portrait, Whiteread House.

## Cards That Required Special Handling

- **MNR Mandate 1: Memory Hole** — Witness POV over a clerk's shoulder, AD chair must remain empty. Do not generate a portrait.
- **MNR Mandate 7: Public Disclosure** — the press conference room is set but NOT yet open to press; empty chairs facing empty podium, chartreuse-labeled briefing folders stacked on a side table. The mandate has not been triggered yet; the room is the readiness.
- **MNR Mandate 8: Cold-Open Inquiry** — Witness POV of the closed inquiry-room door; the body of the mandate is the closed door itself, NOT what's behind it. Chartreuse-lit badge reader and a single guard standing post are mandatory.
- **MNR Mandate 4: Mnestic Saturation** — every chair occupied with two IV-lines per occupant; two IVs is the directive tell distinguishing it from a normal inoculation wave.
- **MNR Mass Remembrance** — uses Saville's institutional flesh as reference. The ring of twelve seated subjects on the anchor array; verify it reads as 'coordinated mass mnestic recall' rather than as a sci-fi resurrection.
- **MNR Records Burn** — the chartreuse-tabbed acknowledgment slip on the clerk's cuff is the discipline tell. Without it the card reads as a movie cover-up.
- **MNR Mnestic Dust Cloud** — chartreuse aerosol haze deployed through hallway; the cloud is mnestic-pharmaceutical, NOT a smoke grenade. The clipboard-carrying operatives in respirators sell the discipline.
- **MNR Conference Redaction** — two clerks pairing on a redaction. The two-clerk pairing with chartreuse-handled markers is the operational tell; without the pairing this reads as office vandalism.
- **MNR Brief and Bury** — the facedown chartreuse-tabbed dossier and the row of unfinished drug cups are the timestamp showing the briefing audience has departed for mnestic erasure, NOT been interrupted.

## QA Reminders for Image Generation

- Reject readable text, logos, watermarks, frames, captions, copied source compositions.
- For Mandate cards: the directive is physical residue (memo, empty desk, sealed door, lectern). Avoid hero framing of authority figures.
- Chartreuse must remain the accent, not the dominant. Where it dominates (Mnestic Dust Cloud, Inoculation Wave, Mnestic Saturation), the dominance is the operational tell, not a regenerate-flag.
- Watch adjacent procedure cycles (Counter-Raid / Counter-Strike / Records Burn / Walk-Out Order are all SCP_PROCEDURE Action cards in the same slice) so they do not collapse into the same tactical-team shot. Each has a distinct staging.
- For directorate / mandate witness POVs: the AD's body should never appear. The chair, the desk, the door, the badge reader, the empty corridor — those are the protagonists.
