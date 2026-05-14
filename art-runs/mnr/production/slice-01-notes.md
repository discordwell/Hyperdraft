# MNR Slice 01 Production Notes

Generated card-level art packets for slice 01 only. No PNGs generated.

## Scope

- Source manifest: `frontend/public/scp_art_manifest.json` filtered to `expansion_code == "MNR"`.
- Output packets: `art-runs/mnr/production/slice-01-packets.json`
- Packet count: 40
- Theme: the things you cannot see, and the institutions built around them.

## Card-Type Breakdown

- SCP_ANOMALY: 24 (every MNR anomaly)
- SCP_FACILITY: 16 (every MNR facility)

## Composition Rotation

The five primary MNR modes plus Reaction/Action carryovers. Slice-01 leans Wide and Detail because the cards are environments and props.

- Wide: 19 (facility architecture, mass-event spaces, missing-floor stairwells)
- Detail: 8 (pill bottles, filing cabinets, hopover desk props)
- Aftermath: 5 (just-vacated rooms, stripped tables, dragged carpets)
- Witness POV: 5 (AD office vantage from the doorway, sealed conference viewport)
- Anomaly Implied: 3 (white hallway recall, filed-away window, anniversary ghost)

## Artist Reference Use

Trait sources only — final prompts forbid exact artist imitation and copying source compositions.

- 4x Walter De Maria, The Broken Kilometer — `https://www.diaart.org/visit/visit/walter-de-maria-the-broken-kilometer`
- 3x Vilhelm Hammershoi, Interior with Young Woman Seen from Behind — `https://www.smb.museum/en/museums-institutions/nationalgalerie/collection/`
- 3x Vilhelm Hammershoi, Dust Motes Dancing in the Sunbeams — `https://www.ordrupgaard.dk/en/the-collection/`
- 2x George Tooker, Government Bureau — `https://www.metmuseum.org/art/collection/search/485874`
- 2x Sophie Calle, The Hotel — `https://www.perrotin.com/artists/Sophie_Calle/9`
- 2x Robert Bechtle, '56 Olds — `https://collections.lacma.org/node/231458`
- 2x Mark Rothko, No. 14, 1960 — `https://www.sfmoma.org/artwork/98.308/`
- 2x Jeff Wall, A View from an Apartment — `https://www.tate.org.uk/art/artworks/wall-a-view-from-an-apartment-t12446`
- 2x Edward Hopper, New York Office — `https://www.mfah.org/art/detail/27543`
- 2x Rachel Whiteread, Ghost — `https://www.nga.gov/artworks/110341`
- 2x Joseph Wright of Derby, An Experiment on a Bird in the Air Pump — `https://www.nationalgallery.org.uk/paintings/joseph-wright-of-derby-an-experiment-on-a-bird-in-the-air-pump`
- 1x each: Robert Bechtle Alameda Gran Torino, Lucian Freud Self-Portrait, Walker Evans Penny Picture Display, Friedrich Monk by the Sea, Whiteread House, Hopper Office at Night, De Maria New York Earth Room, Stephen Shore Meeting Room, John Register Open Diner, Hopper Automat, Magritte Time Transfixed, Rembrandt Anatomy, Hopper Conference at Night, Magritte Empire of Light.

## Cards That Required Special Handling

- **MNR Missing Floor / Missing Floor (Containment Critical)** — institutional-realism handling specified in the style packet: elevator panel detail and stairwell architectural seam, NOT a CG impossible-architecture shot. Verify the panel reads as 'pressed many times, never working' rather than 'broken hardware'.
- **MNR White Hallway Recall** — single figure paused mid-step in a corridor of all-white surfaces. Anomaly Implied. The figure must look mid-recall, not mid-walk.
- **MNR Stripped Conference Room** — the empty boardroom must read as 'meeting that did not happen / cannot be recalled' rather than 'meeting before everyone arrives'; the sun-faded wall rectangles are the timestamp.
- **MNR Anniversary Ghost** — the empty rolling chair beside the half-eaten cake must rock as if just-vacated, not malfunctioning.
- **MNR Sealed Conference Room** — Witness POV through a wire-mesh viewport, chartreuse badge reader is mandatory.
- **MNR Director's Office, AD** — AD chair must remain empty; do not generate a portrait of the Director.

## QA Reminders for Image Generation

- Reject readable text, logos, watermarks, frames, captions, copied source compositions.
- Antimemetic chartreuse appears as an accent (pill bottle, IV bag, badge reader, capsule, lanyard, etc.). It should never dominate the frame. If chartreuse dominates, regenerate.
- For anomaly cards whose subject is absence (Missing Floor, Stripped Conference Room, Bystander Effect, The Blank Folder, Personnel Drift), the wrongness should be a held breath, not a jump scare.
- Watch the four-card cycles where Severe / Containment Critical variants exist (Cognitive Wedge, Memory Reef, Missing Floor, Personnel Drift, Soft Erasure, The Blank Folder, The Director's Note): the Severe / Critical variant should escalate scale or evidence, not just repeat the same composition.
