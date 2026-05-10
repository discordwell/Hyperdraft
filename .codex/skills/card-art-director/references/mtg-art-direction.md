# MTG-Style Art Direction Reference

Use this as a compact public-source-informed guide for card-art packets. It is not official Magic style-guide text and should not be copied into prompts as source prose.

## Useful Public References

- The Magic Style Guide Part 1: https://web.archive.org/web/20060107023828/http%3A//www.wizards.com/default.asp?x=mtgcom%2Fdaily%2Fmc3
- Magic Style Guide Part 1.5: https://web.archive.org/web/20071021022527/http%3A//wizards.com/default.asp?x=mtgcom%2Fdaily%2Fmc4
- Style Guide Part 2: https://web.archive.org/web/20051127081431/http%3A//www.wizards.com/default.asp?x=mtgcom%2Fdaily%2Fmc5
- Ultimate Masters Art Descriptions: https://magic.wizards.com/en/news/feature/ultimate-masters-art-descriptions-2018-12-04
- Wizards freelance art guidance: https://company.wizards.com/fr/freelance-art-submissions

## Packet Shape

Write one packet per card:

```text
Setting/Faction:
Card type:
Location:
Action:
Focus:
Mood:
Reference traits:
Final prompt:
Negative prompt:
Target path:
QA notes:
```

## Direction Principles

- Make the image read at card size. Use a clear foreground, a limited number of focal subjects, strong value contrast, and a readable silhouette.
- Reflect what the card does. Creatures/personnel/anomalies should have a clear focal subject; procedures should foreground the action or consequence; facilities should establish place and function.
- Use the set style guide as a basis, not a copybook. Keep the shared world cues, but allow different artists, camera choices, moods, and solutions.
- Favor dynamic, evocative, cinematic images, but include calm, strange, or abstract cards when the card concept benefits from it.
- Keep palettes controlled. Too many unrelated colors become muddy at card size.
- Do not let the background compete with the focal subject unless the card is explicitly about a location or landscape.
- Avoid real-world letters, logos, UI, watermarks, card frames, title text, and stat elements in generated art.

## Composition Rotation

Use these rotations to avoid batch homogeneity:

- **Action:** impact, chase, escape, activation, containment, transformation.
- **Aftermath:** damage, empty room, evidence, cleanup, abandoned prop.
- **Reaction:** witness face, operator hands, crowd response, staff hesitation.
- **Detail:** instrument, object, document, lock, sample, threshold.
- **Environment:** facility exterior, vast room, map-like view, surveillance angle.
- **POV:** first-person danger, overhead security camera, low-angle threat, through-glass observation.

Across a slice, avoid repeating the same rotation more than twice in a row.

## Artist Reference Handling

Research one drawing or painting reference per card when practical. Record the URL and the traits it contributes. Convert references into general descriptors:

- medium: oil, gouache, ink wash, charcoal, etching, watercolor, digital matte painting
- rendering: hard-edged, scumbled, loose, glazed, graphic, impasto, soft-focus
- composition: diagonal thrust, central icon, crowded frieze, negative space, compressed foreground
- lighting: chiaroscuro, backlit, fluorescent, moonlit, emergency red, sodium vapor
- palette: limited earth tones, cold blue-green, oxidized metal, clinical whites, acidic accent

Do not ask the image model to imitate a living artist by name. Do not copy the source composition.
