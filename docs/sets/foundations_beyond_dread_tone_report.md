# Foundations Beyond - Stage 7.6 Dread-Tone Judgment

300 cards scored across 10 archetypes. This report is the tonal gate between parallel codegen and the Stage 8 tournament loop. The goal is to surface cards whose mechanics are correct but whose flavor is generic, so they can be rewritten before they bake into balance data.

## Methodology

Each card was scored 1-5 on three axes, read from `card.name`, `card.text`, and `card.scp_art_prompt`. Scoring was a deterministic, regex-based heuristic (in `/tmp/fbn_judge/score.py`, scratch only) calibrated against the Site Zero / SCP house style. The heuristic is intentionally generous on bureaucratic vocabulary (the set's core voice) and stricter on MTG fidelity and on the third axis, where "dread density" requires more than mood-words.

**Bureaucratic-horror tone (1-5)** -- does the language read as a Foundation containment file? Tier-5 markers: "containment integrity: holding", "Class: Thaumiel/Euclid/Keter/Apollyon", "O5-Council", "amnestic/mnestic", "designation", "redact", "Site Zero", "ethics_debt". Tier-3 markers: "contain", "research", "anomaly", "dossier", "personnel", "archive". Penalty for generic action verbs ("deal damage", "destroy target", "summon").

**MTG flavor fidelity (1-5)** -- does it reference a specific MTG entity in a way that lands? Tier-5: Yawgmoth, Sheoldred, Bolas, Ulamog, Liliana, Karn, Marit Lage, Griselbrand, Worldspine, Necropotence, Hedron, Omenpath, Compleation. Tier-3: generic MTG type names (Dragon, Lich, Wurm). Tier-1: only "creature/monster/entity" with no MTG specificity.

**Cosmic dread density (1-5)** -- does the text evoke dread instead of action? Tier-5: passive recursion ("the cooperation is annotated", "the lake is never the same depth twice", "the rift has not sealed", "the surveys disagree with each other", "the witnesses are the failure"), classification voice ("Recommended containment: do not breach"), self-referential paperwork ("filed a containment waiver that self-amended"). Tier-3: dread vocabulary (cosmic, void, ancient, ambient, spectral, non-Euclidean). Penalty for combat-action language.

Combined = sum (3-15). Cards in the 13-15 band are exemplars. Cards in the 3-9 band are rewrite candidates.

## Aggregate Stats

- **N scored:** 300 / 300 (no failures)
- **Mean combined:** 11.75 / 15
- **Mean bureau:** 4.85 / 5 (very strong house voice)
- **Mean MTG fidelity:** 3.64 / 5 (uneven -- carried by 3 archetypes)
- **Mean dread density:** 3.25 / 5 (the weakest axis; this is where rewrites pay)

**Distribution of combined scores (1=score, 2=count):**

| Score | Count | Share |
|------:|------:|------:|
| 8     |   4   | 1.3%  |
| 9     |  18   | 6.0%  |
| 10    |  59   | 19.7% |
| 11    |  70   | 23.3% |
| 12    |  29   | 9.7%  |
| 13    |  69   | 23.0% |
| 14    |  39   | 13.0% |
| 15    |  12   | 4.0%  |

The shape is bimodal -- a "named SCP-FBN-XXXX boss/spell" cohort piles around 13-14, and a "Class-A Operative / Researcher / Containment Vault" filler cohort piles around 10-11. The dip at 12 is the seam between named anomalies (which carry rich SCP designations) and supporting personnel (which do not). The dread axis is the bottleneck: 70+% of cards score 3 there, while 80+% score 5 on bureau.

## Top 20 Exemplars (highest combined score, anchor the tone bar)

| # | Score (B/M/D) | Card | Archetype |
|---|---|---|---|
| 1  | 15 (5/5/5) | Atraxa Specimen Containment Cell | phyrexian_strain |
| 2  | 15 (5/5/5) | SCP-FBN-2273: Apollyon-Class Reality-Eater (Emrakul) | eldrazi_apex |
| 3  | 15 (5/5/5) | SCP-FBN-2279: Void Eel | eldrazi_apex |
| 4  | 15 (5/5/5) | SCP-FBN-3001: Nicol Bolas, Class-V Apex Dracoform | dragon_conclave |
| 5  | 15 (5/5/5) | SCP-FBN-4001: Jace, Class-III Cognitive Manipulator | planeswalker_detention |
| 6  | 15 (5/5/5) | SCP-FBN-4003: Chandra, Class-III Thaumic Ignition | planeswalker_detention |
| 7  | 15 (5/5/5) | SCP-FBN-4007: Karn, Class-V Artifact Vector | planeswalker_detention |
| 8  | 15 (5/5/5) | SCP-FBN-4011: Kaya, Class-IV Spectral Investigator | planeswalker_detention |
| 9  | 15 (5/5/5) | SCP-FBN-6001: Marit Lage, Dormant Class-V Ambient | leyline_anomaly |
| 10 | 15 (5/5/5) | SCP-FBN-6010: Eldrazi Temple, Cross-Class Vector | leyline_anomaly |
| 11 | 15 (5/5/5) | SCP-FBN-8001: Liliana, Class-V Lich-Form | lich_phylactery |
| 12 | 15 (5/5/5) | SCP-FBN-9007: Yargle, Vile Containment Subject | wurm_apex |
| 13 | 14 (5/5/4) | SCP-FBN-1140: Yawgmoth-Pattern Strain | phyrexian_strain |
| 14 | 14 (5/5/4) | SCP-FBN-2271: Apollyon-Class Void Eater (Ulamog) | eldrazi_apex |
| 15 | 14 (5/5/4) | SCP-FBN-2272: Apollyon-Class Hedron-Tilt (Kozilek) | eldrazi_apex |
| 16 | 14 (5/5/4) | SCP-FBN-2280: Eldrazi Conscription Pattern | eldrazi_apex |
| 17 | 14 (5/5/4) | SCP-FBN-2281: Hedron-Caged Titan | eldrazi_apex |
| 18 | 14 (5/5/4) | SCP-FBN-2276: Void Drone, Apollyon-Adjacent | eldrazi_apex |
| 19 | 14 (5/5/4) | SCP-FBN-2277: Hedron Network Fragment | eldrazi_apex |
| 20 | 14 (5/5/4) | SCP-FBN-2278: Brood Tyrant Specimen | eldrazi_apex |

Eldrazi Apex dominates the top because the archetype's house voice is naturally dread-coded ("It doesn't look at you. It doesn't look at anything. The radar shows three dozen more.") and its named-entity hits (Ulamog/Kozilek/Emrakul) score MTG fidelity 5 automatically. The Jace/Chandra/Karn/Kaya block in Planeswalker Detention shows the cleanest recipe for a 15: named MTG specimen + SCP designation + classification + recursive flavor closer.

## Bottom 30 Rewrite Candidates

These cards are mechanically wired but tonally generic. Most are personnel cards (Operatives, Researchers, Doctors, Specialists) and bonded facilities (Vaults, Bureaus, Chambers) where the writer leaned on filler-template wording instead of naming an MTG hook. Demonic Pact Bureau accounts for 13 of the 30 -- see archetype audit below.

| # | Score | Card | Archetype | Why it falls |
|---|---|---|---|---|
| 1  | 8 (3/2/3) | Operative "Bottleneck" | leyline_anomaly | Personnel card with no MTG hook and no SCP designation. |
| 2  | 8 (4/2/2) | Pact Containment Vault | demonic_pact_bureau | Generic "vault" facility, "demon" used unspecifically. |
| 3  | 8 (4/2/2) | Class-A Operative 'Soul-Auditor' | demonic_pact_bureau | "soul ledger" is generic; no named demon, no recursion. |
| 4  | 8 (4/2/2) | Dr. Faust, Pact Interpreter | demonic_pact_bureau | Faust is public-domain horror, not MTG. |
| 5  | 9 (4/2/3) | Saturation Reactor Core | leyline_anomaly | Generic facility; no leyline-specific MTG entity. |
| 6  | 9 (3/2/4) | Ambient Containment Site Delta-7 | leyline_anomaly | Generic site card; "ambient thaumic" is filler. |
| 7  | 9 (3/3/3) | Leyline Containment Grid | leyline_anomaly | Mechanic-tag card with no MTG specificity. |
| 8  | 9 (3/3/3) | SCP-FBN-6006: Mishra's Workshop, Class-III Thaumic Forge | leyline_anomaly | Good MTG hook in name -- but text never uses it. |
| 9  | 9 (3/3/3) | SCP-FBN-6005: Maze of Ith, Class-III Spatial Distortion | leyline_anomaly | Strong land name; text drifts into generic dimensions. |
| 10 | 9 (5/2/2) | Diabolic Audit Bureau | demonic_pact_bureau | "audit/audit/audit" loop with no demon named. |
| 11 | 9 (5/2/2) | Demonic Tutor Audit | demonic_pact_bureau | Squanders the MTG name -- text doesn't reference Tutor. |
| 12 | 9 (4/3/2) | Class-V Pact Sweep | demonic_pact_bureau | Action-spell with low dread density. |
| 13 | 9 (5/2/2) | Soul-Broker Audit | demonic_pact_bureau | "Soul-Broker" is bland; no MTG specificity. |
| 14 | 9 (4/3/2) | Pact Recall | demonic_pact_bureau | Effect verb ("memory-hole") reads as gameplay slang. |
| 15 | 9 (5/2/2) | Faustian Re-Audit | demonic_pact_bureau | Generic "Faustian"; relies entirely on filing flavor. |
| 16 | 9 (4/3/2) | Dr. Marlowe, Containment Theologian | demonic_pact_bureau | Marlowe is literary reference, not MTG. |
| 17 | 9 (4/3/2) | Operative 'Mark,' Pact Negotiator | demonic_pact_bureau | "Mark" is too anonymous. |
| 18 | 9 (4/3/2) | Researcher Bargainer 'Hand' | demonic_pact_bureau | Two-hands gag is cute; no MTG entity. |
| 19 | 9 (5/2/2) | Operative O5-9, Ethics Officer | demonic_pact_bureau | All bureau, no demon. |
| 20 | 9 (4/3/2) | SCP-FBN-5013: Soul-Broker Apprentice | demonic_pact_bureau | Has SCP-FBN-#, but no MTG anchor in text. |
| 21 | 9 (4/3/2) | SCP-FBN-5012: Junior Pact-Imp | demonic_pact_bureau | "imp" is generic MTG type; no named MTG demon. |
| 22 | 9 (4/3/2) | SCP-FBN-5007: Lord of the Pit, Containment Specimen | demonic_pact_bureau | Strong MTG name -- but text only uses "the contract". |
| 23 | 10 (5/2/3) | Ectoplasmic Containment Chamber | spirit_archive | Generic chamber; no Geist/Unburial reference. |
| 24 | 10 (5/2/3) | Operative "Phantom-Hand" | spirit_archive | Personnel filler. |
| 25 | 10 (5/2/3) | Operative "Ghosthand" | spirit_archive | Near-duplicate of #24 -- two adjacent filler operatives. |
| 26 | 10 (5/2/3) | Researcher Aleko, Ecto-thaumic Surveyor | spirit_archive | No MTG hook, no recursion. |
| 27 | 10 (5/2/3) | Megafauna Audit Bureau | wurm_apex | Joke about paperwork loops; no Worldspine/Wurmcoil reference. |
| 28 | 10 (5/2/3) | Containment Pit Vault | wurm_apex | "expensive lid" gag; no MTG anchor. |
| 29 | 10 (5/2/3) | Operative "Wurmtongue" | wurm_apex | Tolkien reference flagged as Tolkien; no MTG redirect. |
| 30 | 10 (5/2/3) | Class-A Megafauna Specialist | wurm_apex | Generic disclaimer-humor personnel card. |

**Common fix patterns for the bottom 30:**

1. Replace generic "demon"/"imp"/"vault" nouns with named MTG entities (Ob Nixilis, Rakdos, Kuldotha, Volrath's Stronghold).
2. When the card name already has an MTG hook ("Mishra's Workshop", "Maze of Ith", "Lord of the Pit", "Demonic Tutor"), force the flavor text to deliver on it -- not drift into generic Foundation copy.
3. Personnel/researcher cards need at least one tier-5 dread marker (recursion, classification voice, surveillance) or one tier-5 MTG marker (a named plane, planeswalker, or mechanic) -- not both filler-personnel and filler-flavor.
4. Two adjacent operatives named "Phantom-Hand" and "Ghosthand" in spirit_archive read as parallel-codegen artifacts. One should be renamed.

## Per-Archetype Tone Audit

Archetypes ranked worst-to-best by mean combined score:

| Archetype | Mean B | Mean M | Mean D | Mean Combined | Diagnosis |
|---|---:|---:|---:|---:|---|
| demonic_pact_bureau     | 4.50 | 3.13 | 2.27 |  9.90 | **WEAKEST.** Relies on Faustian-contract humor; almost no named MTG demons cited; dread axis collapses into transactional/legal gags. |
| multiverse_rift         | 5.00 | 2.53 | 3.13 | 10.67 | MTG fidelity is the lowest of any archetype -- "rift/Omenpath" is invoked but specific planes (Mirrodin, Dominaria, Zendikar) rarely named in text. |
| leyline_anomaly         | 4.10 | 3.03 | 3.57 | 10.70 | Bureau axis dips -- many cards describe "ambient saturation" abstractly rather than as a Foundation file. |
| wurm_apex               | 5.00 | 3.03 | 3.13 | 11.17 | MTG hook missing -- "wurm" type cited but Worldspine/Impervious Greatwurm/Carnifex only appear in the top tier. |
| lich_phylactery         | 5.00 | 3.40 | 3.13 | 11.53 | Solid but undifferentiated; Liliana carries the archetype. Other liches go unnamed. |
| spirit_archive          | 5.00 | 3.10 | 3.53 | 11.63 | Personnel-heavy; recycles "ectoplasmic" without a specific MTG geist beyond Saint Traft. |
| dragon_conclave         | 5.00 | 3.57 | 3.17 | 11.73 | The Dragonlords (Ojutai, Atarka, etc.) carry it; the supporting personnel are filler. |
| phyrexian_strain        | 4.97 | 5.00 | 3.10 | 13.07 | Strong: every card mentions Compleation/Yawgmoth/Phyrexian. |
| planeswalker_detention  | 5.00 | 4.63 | 3.43 | 13.07 | Strong: each Class-III/IV/V designation pairs with a real planeswalker. |
| eldrazi_apex            | 4.97 | 5.00 | 4.07 | 14.03 | **STRONGEST.** Eldrazi naturally fit Apollyon-class containment voice -- effect text and flavor both deliver dread. |

**Bottom-of-class diagnosis:** demonic_pact_bureau is the rewrite target. 13 of the bottom 30 are in this archetype. The dread axis mean of 2.27 is more than half a point below the next-worst archetype (multiverse_rift at 3.13). The pattern: contract/audit/ethics-debt language is mechanically interesting but reads as bureaucratic comedy, not horror. Specific fix: introduce named MTG demons (Griselbrand only appears at the top; Ob Nixilis, Rakdos, Sengir, Demonlord Belzenlok, Lord of the Pit, Shauku, Razaketh are absent or buried), and pair them with recursive-dread closers ("the contract pre-dates the Foundation" exists once and should be the template, not the exception).

## Mechanic-Flavor Coherence

Cards reference the 8 named FBN mechanics in their printed text as follows:

| Mechanic | Primary Archetype | Secondary | Tertiary | Distinct? |
|---|---|---|---|---|
| Compleation Vector | phyrexian_strain (14) | -- | -- | YES - clean |
| Phylactery Audit | lich_phylactery (22) | demonic_pact_bureau (15) | spirit_archive (12) | **BLEEDS** |
| Spark Containment | planeswalker_detention (20) | dragon_conclave (5) | -- | mostly clean |
| Annihilation Wave | eldrazi_apex (12) | wurm_apex (4) | leyline_anomaly (3) | **BLEEDS** |
| Dragon Hoard | dragon_conclave (12) | -- | -- | YES - clean |
| Leyline Saturation | leyline_anomaly (16) | spirit_archive (15) | -- | **BLEEDS** |
| Planar Rift | multiverse_rift (17) | -- | -- | YES - clean |
| Wurm Devourer | wurm_apex (22) | -- | -- | YES - clean |

**Three mechanics bleed:**

1. **Phylactery Audit** appears on liches, demons, AND spirits. The thematic justification (any "soul-bound object" being audited) is coherent, but in practice it makes lich_phylactery and demonic_pact_bureau feel mechanically indistinct -- both archetypes pay ethics_debt to resolve the same trigger. Recommend: have lich Phylactery Audits scale with graveyard count, while demon Phylactery Audits scale with ethics_debt, so the two archetypes diverge mechanically even though the keyword is shared.

2. **Annihilation Wave** appears on Eldrazi, Wurms, and ambient leylines (Marit Lage). The Eldrazi association is canonical; the Wurm and Leyline overlap dilutes it. Recommend: rename the Wurm version (e.g. "Devourer Tide") or restrict Annihilation Wave to eldrazi_apex.

3. **Leyline Saturation** is roughly 50/50 between leyline_anomaly and spirit_archive. This is the most concerning bleed because spirit_archive is supposed to be the "Geist of Saint Traft / unburial rites" plane -- not a second leyline plane. The 15 spirit cards using Leyline Saturation muddy the archetype identity. Recommend: introduce a spirit-specific keyword (e.g. "Veil Saturation" or "Spectral Saturation") and migrate the spirit cards off the leyline keyword. Alternatively, lean the spirit_archive archetype explicitly into "ambient spectral leyline" and rebrand it.

**Five mechanics are distinct:** Compleation Vector, Dragon Hoard, Planar Rift, Spark Containment, Wurm Devourer all stay in their home archetype. Spark Containment leaks 5 cards to dragon_conclave (probably for elder dragon planeswalker hybrids), which is defensible.

## Summary

The set has a strong house voice (mean bureau 4.85) and good named-entity fidelity in three archetypes (eldrazi_apex, planeswalker_detention, phyrexian_strain). The flat axis is dread density (mean 3.25): most cards score points by saying "Containment integrity: holding" but few earn a 5 by making the rules text itself dread-coded -- the unfailing top-20 trick is to make the trigger condition or the consequence itself read like a containment failure (e.g. SCP-2273 Emrakul: "On contain, opposing breach +2 anyway" -- the contain action causes the breach, which is the SCP horror in mechanical form).

**Highest-leverage follow-up actions, in order:**

1. Rewrite the 13 demonic_pact_bureau cards in the bottom 30. Add named MTG demons; replace transactional gags with recursive-dread closers.
2. Resolve the Leyline Saturation / spirit_archive bleed. Either rebrand spirit_archive or split the keyword.
3. Rewrite the 4 leyline_anomaly cards in the bottom 30 to deliver on their MTG-name hooks (Mishra's Workshop, Maze of Ith).
4. Pass over the personnel/operative filler cards (filler count ranges 6-11 per archetype) and ensure each carries at least one tier-5 marker on either MTG or dread axis.
5. Reconcile the two adjacent spirit_archive operatives "Phantom-Hand" and "Ghosthand" (likely codegen duplication).

No source-file rewrites were performed. The score data is in `/tmp/fbn_judge/results.json` (scratch) and can be regenerated from `/tmp/fbn_judge/score.py`. The `card_def` files under `src/cards/scp/foundations_beyond/` were not modified.
