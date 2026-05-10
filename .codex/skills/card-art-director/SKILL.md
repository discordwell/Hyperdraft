---
name: card-art-director
description: "Use when planning, directing, prompting, generating, or QA-ing large batches of Hyperdraft card art for a custom set. Triggers include creating set art direction, avoiding too-similar card illustrations, building MTG-style art-description packets, generating style references, splitting card art manifests across subagents, producing per-card image prompts, and coordinating 1024x1024 card-art PNG generation."
---

# Card Art Director

## Purpose

Use this skill to turn a card set into a coherent but varied art production run. The goal is not one repeated look; it is a set-level visual language with enough camera, subject, mood, palette, and composition variety that individual cards remain recognizable.

Follow `$imagegen` whenever this skill reaches actual raster image generation or image editing.

## First Reads

Before creating prompts or images, inspect the target set and any existing art manifest.

- SCP example manifest: `frontend/public/scp_art_manifest.json`
- SCP manifest exporter: `scripts/art/scp_art_manifest.py`
- SCP set source: `src/cards/scp/`
- MTG art packet reference: `references/mtg-art-direction.md`
- SCP defaults: `references/scp-art-direction.md`

If the set has no manifest, create or ask for a manifest with a top-level `cards` list. Each card should include at least `name`, `prompt`, `types`, `subtypes`, `expansion_code`, and `target_path`.

## Workflow

1. **Survey the set.** Read card names, types, subtypes, mechanics, archetypes, flavor text, existing prompts, and target image paths. Group the set by faction/archetype and by card type.
2. **Research the visual language.** Use web search for the target IP/theme and public MTG art-direction guidance. Capture only short source notes and URLs; do not copy source text into prompts.
3. **Write a compact set style packet.** Include core fantasy, recurring motifs, palette ranges, materials, camera rules, subject rules, and a negative list. Add explicit variety rules so not every card shares the same camera angle, lighting, setting, or pose.
4. **Generate 12 style explorations.** Use square 1024x1024 explorations that sample different subjects, compositions, and moods from the set style packet. Save the run notes beside the images.
5. **Choose 3 style references.** Select the strongest three that together cover the set's range. Record why each was chosen and what traits later prompts should borrow.
6. **Split the manifest.** Run `scripts/split_manifest.py` to create 6 even slices. Do not hand-edit slice membership unless the user asks for a thematic split.
7. **Coordinate 6 subagents.** The user has explicitly requested 6 subagents for this workflow. Before spawning more than 5 agents in one command, follow this repo's `AGENTS.md` preference and ask whether to use `model: "sonnet"` to reduce cost/latency. Assign each subagent exactly one slice and tell it that other agents own other slices.
8. **Generate per-card packets.** Each subagent writes one card-level art packet per card: setting/faction, card type, location, action, focus, mood, artist-reference traits, final prompt, target path, and QA notes.
9. **Generate and save images.** Use `$imagegen` built-in mode by default. Generate one distinct 1024x1024 image per card, then move/copy the final PNG to the manifest `target_path`. Do not overwrite existing images unless the user requested replacement.
10. **QA the batch.** Check every saved image for correct subject, readable silhouette, no text/logos/watermarks/card frame, no broken anatomy, no obvious prompt leakage, and meaningful variation across neighboring cards.

Default slice command for SCP:

```bash
python .codex/skills/card-art-director/scripts/split_manifest.py \
  frontend/public/scp_art_manifest.json \
  --out art-runs/scp/slices
```

Use `art-runs/<set-slug>/` for run-local style packets, slice files, QA notes, and rejected variants unless the user gives a different destination. Final accepted PNGs still go to each card's manifest `target_path`.

## Subagent Contract

Give each subagent a bounded, non-overlapping task:

```text
Use $card-art-director for this Hyperdraft card-art slice. You own only <slice path>.
Read the set style packet and the 3 selected style references. For each card in your slice:
1. Write an MTG-style art-description packet.
2. Websearch one drawing or painting reference and cite the URL.
3. Convert that reference into trait language: medium, brushwork, lighting, palette, composition, and mood.
4. Produce one final 1024x1024 image prompt that follows the set style references without copying the source artwork.
5. Generate/save the PNG at the card's target_path if image generation is in scope.
6. Record QA notes and any failures.

You are not alone in the codebase. Do not edit another slice, do not revert other agents' work, and adapt to existing run artifacts.
```

Prefer action shots, aftermath shots, reaction shots, object-detail shots, and offbeat angles over literal front-facing portraits. Repetition is allowed only when a deliberate cycle or faction identity calls for it.

## Art Policy

- Use artist references as trait sources, not exact imitation requests. Prompts should say what the reference teaches: for example "loose oil brushwork, compressed chiaroscuro, diagonal crowd movement" rather than "in the style of <living artist>."
- Do not copy a source composition, character, painting, signature, watermark, logo, or distinctive protected expression.
- Do not present generated art as official Magic, Wizards of the Coast, SCP Foundation, or source-IP art.
- Keep generated card art illustration-only: no card frame, mana symbols, stat numbers, readable UI, watermark, caption, or title text.

## Depths Lesson

The style guide is a shared vocabulary, not a stamp. Preserve set identity through motifs, materials, palette ranges, and tone, while rotating:

- camera distance: wide, mid, close-up, macro detail
- camera role: witness, victim POV, surveillance, dossier plate, aftermath
- subject type: person, anomaly, facility, procedure action, prop, environment
- lighting: fluorescent, sodium, daylight, emergency red, moonlit, backlit
- emotional beat: calm dread, crisis, discovery, grief, awe, bureaucratic absurdity

If a pass starts producing "same hallway, same lighting, same centered subject," stop and rewrite the prompts before generating more images.

## Outputs

For a full run, save:

- a set style packet
- 12 style exploration images and notes
- 3 selected style references and selection notes
- 6 manifest slice JSON files
- one per-card art packet or production manifest with citations and final prompts
- final PNGs at each card's `target_path`
- QA notes summarizing rejected images, retries, and residual risks
