# MNR Slice 02 Production Notes

Generated card-level art packets for slice 02 only. No PNGs generated.

## Scope

- Source manifest: `frontend/public/scp_art_manifest.json` filtered to `expansion_code == "MNR"`.
- Output packets: `art-runs/mnr/production/slice-02-packets.json`
- Packet count: 40
- Theme: the people who can see, and the daily discipline that keeps them remembering.

## Card-Type Breakdown

- SCP_PERSONNEL: 30 (every MNR personnel card)
- SCP_PROCEDURE: 10 (the first ten procedures alphabetically: Anchor Reset, Antimemetic Audit, Antimemetic Brief Box, Antimemetic Defense Brief, Antimemetic Tracker, Backchannel Brief, Black-Bag Job, Brief and Bury, Briefing Update, Class-A Inoculation Dose)

## Composition Rotation

Slice-02 is dominated by human figures, so the rotation skews toward Detail (tight on hands / pill cups / clipboards) and Reaction (posture-foregrounded response).

- Detail: 17 (clinicians' hands, dosing-cups, clipboards, IV ports, pinboards)
- Reaction: 14 (staff posture under fluorescent light, half-remembered exhaustion, the witness pose)
- Wide: 3 (bystander witness pool, briefing hall view)
- Witness POV: 2 (Director, AD seen as a chairback; backchannel brief through a doorway)
- Action: 2 (Black-Bag Job, Hallway Runner)
- Aftermath: 2 (Walked-Out Intern desk, Brief and Bury debrief room)

## Artist Reference Use

Trait sources only — final prompts forbid exact artist imitation and copying source compositions.

- 6x Lucian Freud, Reflection (Self-Portrait) — `https://www.npg.org.uk/collections/search/portrait/` (mnestic-discipline mirrors, ready-room portraits, fluorescent flesh)
- 4x Edgar Degas, A Woman Ironing — `https://www.nga.gov/artworks/46640` (single working figure leaning into routine task)
- 2x John Singer Sargent, Two Soldiers at Arras — `https://www.imperialwarmuseums.org.uk/collections/item/object/16566`
- 2x Sophie Calle, The Hotel — `https://www.perrotin.com/artists/Sophie_Calle/9`
- 2x Edward Hopper, Office at Night — `https://collections.walkerart.org/object/1599`
- 2x Kathe Kollwitz, The Survivors — `https://sammlung.staedelmuseum.de/en/work/the-survivors`
- 2x Lucian Freud, Benefits Supervisor Sleeping — `https://www.christies.com/lot/lot-5071290/`
- 2x Johannes Vermeer, The Geographer — `https://www.staedelmuseum.de/en/collection/the-geographer-1668`
- 2x Jeff Wall, Insomnia — `https://www.tate.org.uk/art/artworks/wall-insomnia-p20198`
- 2x Vilhelm Hammershoi, Interior with Young Woman Seen from Behind — `https://www.smb.museum/en/museums-institutions/nationalgalerie/collection/`
- 1x each: Bechtle Alameda Gran Torino, Wyeth Christina's World, Hopper New York Office, Tooker Subway, Rembrandt Anatomy, Hopper Automat, Daumier Two Lawyers, Wyeth Wind from the Sea, Wright Air Pump, Thiebaud Bakery Counter, Stephen Shore Meeting Room, Fischl Birthday Boy, Wall View from an Apartment, Hammershoi Dust Motes.

## Cards That Required Special Handling

- **MNR Marion Wheeler** — must read as a specific senior analyst (Freud Self-Portrait), exhausted at her desk under a single banker's lamp, NOT as an action-hero MTF operative. The chartreuse pill bottle and drug cup are mandatory tells.
- **MNR Director, Antimemetics Division** — Witness POV from the doorway. The chair must obscure the figure's face; the chair-arm hand holding the drug cup is the protagonist. Do not generate a portrait.
- **MNR Bystander Effect** — civilian bystander reads as ordinary office worker, calm and slightly bored, NOT as a menaced victim. The anomaly is implied, never centered or rendered.
- **MNR Reluctant Subject** — subject reads as 'civilian about to comply' rather than as a torture-room victim. The proffered chartreuse drug cup from off-frame is the operational tell.
- **MNR D-Class (No Recall)** — reads as 'amnestically reset, calm' rather than as a prisoner.
- **MNR Mailroom Junior / Documents Clerk / Hallway Runner / Office Temp / Walked-Out Intern** — these adjacent bystander-staff cards must not collapse into the same beige-office shot. Their composition rotation (Detail / Detail / Action / Detail / Aftermath) gives each a distinct camera role; verify in QA.

## QA Reminders for Image Generation

- Reject readable text, logos, watermarks, frames, captions, copied source compositions.
- For personnel cards: hands, posture, gear, and environment do the work — no passport portraits.
- The chartreuse accent must read as pharmaceutical (gelatine capsule, IV bag label, drug-cup tint), not as sci-fi glow.
- For Marion Wheeler and the Director: avoid hero framing. They are specific people at the end of a long shift, not action protagonists.
- The IV cuff + drug cup combo is the discipline tell across many MNR personnel cards. Verify it remains banal medical, not horror-medical.
