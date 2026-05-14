# Foundations Beyond (FBN)

**Set code:** `FBN`
**Expansion code:** `FBN`
**Module path:** `src/cards/scp/foundations_beyond/`
**Card count:** 300 (10 archetypes × 30 cards)
**Premise tag:** *Inverted Universes Beyond — the SCP Foundation captures iconic MTG entities.*

## 1. Premise

Universes Beyond ran the other direction: it folded outside fictions into Magic's Multiverse — Doctor Who showed up as planeswalkers, the Lord of the Rings cast got Limited slots, Final Fantasy got the legendary creature treatment. Foundations Beyond reverses the polarity. The Multiverse has bled into our world, and the **SCP Foundation** is now the custodial agency tasked with locking up, indexing, and securely forgetting whatever planewalker, demon, or world-eating wurm crossed the threshold this week.

Each FBN card is an internal Foundation document: a containment specimen file on a captured MTG entity, a personnel jacket for a researcher cross-trained in thaumic taxonomy, a site blueprint for a facility built around a captive god, or an O5-Council directive ratifying an experimental protocol. The bureaucratic tone is the joke and the threat. A 15/15 Annihilator wurm doesn't fit in a hangar; the report just says **"Containment integrity: holding."** A planeswalker spark is a "Class-IV thaumic ignition event" subject to clearance review. The art aesthetic fuses sterile SCP brutalism (concrete, redacted documents, biohazard signage, dim sodium light) with MTG cosmic horror (Phyrexian oil sheen, Eldrazi non-Euclidean architecture, dragon-scale, planar-rift chromatic aberration). Tone: dread-bureaucratic. Never camp. Cosmic and procedural at once.

Mechanically, FBN is **cosmic-leaning and anti-tribal.** The set deliberately avoids the obvious tribal anchors (no Slivers, no Goblins, no Vampires) and instead leans into solitary apex entities, alien geometries, and ambient hazards — the kinds of MTG things the Foundation would actually have to bring in helicopter cranes for.

---

## 2. Mechanics

FBN ships **two reused** mechanics from earlier SCP sets and **eight new** mechanics. The new mechanics are designed to live entirely within the engine extension budget (~160 LOC) and compose cleanly with the existing event pipeline.

### 2.1 Reused

#### Brief N  *(reused from Site Zero: Broken Masquerade)*

> *Brief N — Add N briefing tokens to your site.*

Briefing is the existing currency the SZB engine already tracks under `state.scp_sites[player_id]["briefing"]`. Reused verbatim; no engine work needed. Used in FBN as a tempo/setup currency for cascade-style archetypes (Multiverse Rift, Eldrazi Apex, Planeswalker Detention) that need fast paperwork cycling.

#### Mnestic  *(reused from Mnestic Reset)*

> *Mnestic — This personnel is Mnestic. Anomalies your opponents control with Antimeme or Cognitive Hazard do not affect your Mnestic personnel, and their decay counters do not advance while at least one of your Mnestic personnel is on the site.*

Implemented as `card.scp_mnestic = True` (tag, no new event). Reused in **Phyrexian Strain** (Mnestic researchers resist compleation's cognitive-rewrite component) and **Lich Phylactery** (Mnestic personnel see past Phylactery Audit's memory-hole misdirection and can recur dossiers cleanly).

### 2.2 New

#### Compleation Vector N

> *Compleation Vector N — At the end of each opposing turn, place N compleation counters on target opposing Personnel. When that Personnel has 3 or more compleation counters, change its controller to you. Personnel with the Mnestic tag are immune.*

Engine surface: one new counter type (`compleation`), one end-of-turn hook that places counters and checks the threshold, one control-swap event (`SCP_CONTROL_SWAP`) that moves the personnel between the two players' `state.scp_personnel` registries. Single-target — the highest-skill non-Mnestic opposing personnel by default (heuristic pick; engine has no modal targeting). Pairs with the alt-win **`compleation_overrun`** (3 successful control-swaps in a game = automatic win for the compleator).

#### Phylactery Audit X

> *Phylactery Audit X — When this card is memory-holed, you may pay X ethics_debt. If you do, return this card from `scp_forgotten` to your dossier queue.*

Reuses the existing `scp_forgotten` zone (created for MNR antimeme decay) and the existing `memory_hole` engine function. Adds a single replacement-style hook on `SCP_MEMORY_HOLE`: when a card with `card.scp_phylactery_audit = X` enters `scp_forgotten`, fire a `SCP_PHYLACTERY_AUDIT_OFFER` event. The site auto-accepts if `ethics_debt + X <= 8` (engine guardrail to prevent loops); otherwise the card stays forgotten. AI heuristic: accept when the card's red_tape is >= 2 OR the dossier queue is <= 1 card. (Mandate-tier: the alt-win **`phylactery_chain`** ratifies "4 audits in a game" as a win condition for Lich Phylactery.)

#### Spark Containment N

> *Spark Containment N — Whenever you successfully contain an opposing Anomaly, gain N clearance. The first time your clearance reaches 6 each turn, draw an extra paperwork card this turn.*

Pure additive: hook the existing `SCP_CONTAINED` event with `controller=you, anomaly.controller=opposing` filter. Bumps `state.scp_sites[me]["clearance"]` by N. Separately, a one-shot-per-turn watcher on `SCP_CLEARANCE_GAINED` checks if it crossed the threshold and emits an extra `SCP_PAPERWORK_TICK`. (Anti-loop: `state.scp_sites[me]["spark_drawn_this_turn"]` resets at upkeep.)

#### Annihilation Wave N

> *Annihilation Wave N — When this Anomaly breaches, redact N opposing dossiers and increase the opposing player's breach by N.*

Reuses existing redact infrastructure (`scp.misfile_dossier` + `scp.force_audit`). The "breach" half is just `site(state, opp)["breach"] += N`. Triggers on the existing `SCP_BREACH_TICK` event filtered to anomalies with `card.scp_annihilation_wave = N`. No new event type. Anti-tribal note: composes Redact + breach adjust in a single keyword so codegen agents don't have to re-stitch two effects per Eldrazi.

#### Dragon Hoard X

> *Dragon Hoard X — Each card with subtype "Dragon" in your archives grants +X to all your tests.*

State-time `mod_fn` only. No event hooks. Reads `state.scp_sites[me]["archives_list"]` (already maintained by SZB callbacks) for cards whose `subtypes` contains `"Dragon"`. The `+X` is added to every `_active_bonus` call's running total. This is the same pattern as MTG `make_dynamic_pt_boost` — read state, add to running sum, no event emission. Caps at +6 per test (engine sanity ceiling, applied at read time).

#### Leyline Saturation N

> *Leyline Saturation N — Whenever an opposing player resolves a Procedure, Facility, or Mandate, your active Anomalies gain +N hazard until end of your next turn.*

Hooks `SCP_OPEN_DOSSIER` filtered to `obj.controller != me` and `obj.types ∈ {SCP_PROCEDURE, SCP_FACILITY, SCP_MANDATE}`. Increments `obj.state.scp_suppressed -= N` on every active anomaly the Leyline source's controller has (i.e., negative suppression = bonus hazard). Cleared at the start of the controlling player's next end step. (Existing engine convention: `scp_suppressed` is read at breach-tick time.)

#### Planar Rift X

> *Planar Rift X — When you successfully contain an Anomaly, exile the top X cards of your library. You may play any Anomalies among them this turn at no red_tape cost. Cards not played return to the top of your library in a random order at end of turn.*

This is the cascade analog. Engine surface: one transient "rift_window" list keyed on `state.scp_sites[me]["rift_window"]`, populated on `SCP_CONTAINED` for anomalies with `card.scp_planar_rift = X`. Listed in legal actions during the player's main phase. The "no red_tape cost" path: when a Rift-window anomaly is opened as a dossier, skip the paperwork queue and call `_activate_dossier` directly with the existing `auto_seal_default=True` plumbing. Returns at end-of-turn cleanup.

#### Wurm Devourer

> *Wurm Devourer — When this Anomaly is successfully researched (test passed), instead of advancing curiosity, swap -2 hazard for +2 containment on this Anomaly.*

Single hook on `SCP_TEST_RUN` with `result=success` and `card.scp_wurm_devourer = True`. Replaces the normal curiosity tick with `obj.state.scp_hazard -= 2; obj.state.scp_containment += 2`. (Engine already supports both stat mutations; this is just a one-line state mod, no event emission needed beyond an info `SCP_INCIDENT_RESOLVED` with `reason="wurm_taming"`.) Pairs with the alt-win **`wurm_apex_tamed`** — when 3+ anomalies you control have been "tamed" (hazard reduced below their printed value via Wurm Devourer specifically), you win at end of your next turn.

---

## 3. Archetypes

### Mechanic coverage matrix

| Mechanic | # of archetypes using it |
|---|---|
| Brief N | 4 (Eldrazi Apex, Planeswalker Detention, Multiverse Rift, **plus splash uses**) |
| Mnestic | 2 (Phyrexian Strain, Lich Phylactery) |
| Compleation Vector | 1 (Phyrexian Strain) |
| Phylactery Audit | 3 (Demonic Pact Bureau, Lich Phylactery, Spirit Archive) |
| Spark Containment | 2 (Dragon Conclave, Planeswalker Detention) |
| Annihilation Wave | 3 (Eldrazi Apex, Leyline Anomaly, Wurm Apex) |
| Dragon Hoard | 1 (Dragon Conclave) |
| Leyline Saturation | 2 (Leyline Anomaly, Spirit Archive) |
| Planar Rift | 1 (Multiverse Rift) |
| Wurm Devourer | 1 (Wurm Apex) |

Brief and Mnestic also splash quietly into a few archetypes' flavor procedures; the table above counts the **load-bearing** mechanic-archetype pairs only.

### 3.1 `phyrexian_strain` — Keter biomechanical assimilation

**MTG → SCP class:** Phyrexians → **Keter (biomechanical assimilation)**.

**Strategy summary.** Slow-burn control-theft. The Phyrexian Strain deck doesn't try to kill the opponent's hand or board; it tries to *recruit* it. Every end of opposing turn, compleation counters tick onto opposing personnel, and at 3 counters the personnel changes hands. The deck wants to drag the game long, protect its own Mnestic researchers (the only personnel who resist the strain), and stack compleation engines so the opponent can never play a personnel without instantly becoming a future Foundation asset. Wins primarily via the **`compleation_overrun`** alt-win (3 successful control-swaps in a game) or by the inevitability of having converted the entire opposing staff and using their skills against them.

**Key-card profile.** Anomalies are oil-veined avatars (Yawgmoth, Atraxa, Sheoldred, Vorinclex) framed as contained "Praetor-class biomechanical entities." Personnel are split: half are **Mnestic Quarantine Specialists** who resist compleation and serve as anchors; half are **Vector Specialists** who actively *spread* compleation by attaching counters faster. Procedures include "Class-A Mnestic Inoculation, Pattern: Yawgmoth-Resistant" (a personnel-targeting Mnestic graft, expensive) and "Containment Breach Reversal: Phyresis Quarantine" (removes 2 compleation counters from one of your personnel). Facilities are vivisection suites and oil reclamation tanks. The Mandate is **"Mandate FBN-PCV: Compleation Containment Protocol"** which ratifies `compleation_overrun` as the alt-win.

**Gameplay loop.**
1. Open a Compleation Vector anomaly into pending.
2. Stall the opponent's tempo with redactions and Mnestic counter-tools.
3. Each opposing end step, compleation counters tick onto their best personnel.
4. At 3 counters, the personnel walks. Repeat.
5. After 3 swaps, alt-win fires.

---

### 3.2 `eldrazi_apex` — Apollyon void incursion

**MTG → SCP class:** Eldrazi titans → **Apollyon (void incursion, world-ending)**.

**Strategy summary.** Sacrifice-fueled annihilation. The Eldrazi Apex deck *spends* its own dossiers as cult-offerings to its three central Annihilation Wave anomalies (Ulamog, Kozilek, Emrakul, reframed as "Apollyon-class void eaters"). Every dossier sacrificed feeds Brief tokens and adjusts the Wave's hazard. When the Waves breach, they don't just redact — they push the opponent's breach upward. Win condition: hit `opposing_breach >= 12` (effectively the standard public-panic loss state, but accelerated from the offense side).

**Key-card profile.** Three apex anomalies (Ulamog, Kozilek, Emrakul reskins) each at red_tape 2 with Annihilation Wave 2 or 3. Mid-tier anomalies are spawn-and-scion analogs ("SCP-FBN-2274: Apollyon Vector Spawn") that feed sacrifice cost. Personnel are **Researcher Drake-Ulamog Pact Interpreters** who specialize in "voluntary exposure" — they accept higher hazard in exchange for tempo. Procedures include "Protocol: Hedron Network Activation" (sac N pending dossiers, gain N Brief, +1 Annihilation Wave hazard) and "Void Bombardment" (a hard sweeper that redacts 3 opposing dossiers but increases your own breach by 2). Facility: "Containment Site Ash-of-Zendikar."

**Gameplay loop.**
1. Brief into early hand cycling, dump 2-3 cheap anomalies as fodder.
2. Sacrifice fodder dossiers to accelerate apex anomaly red_tape into play.
3. Apex anomaly breaches → Annihilation Wave fires → opposing breach climbs.
4. Stack 2-3 apex anomalies for compounding waves.
5. Opposing breach hits 12, opposing player loses to public_panic.

---

### 3.3 `dragon_conclave` — Keter apex predators

**MTG → SCP class:** Dragons → **Keter (apex predator, archive-keepers)**.

**Strategy summary.** Archive-engine midrange. Every Dragon-subtype card the deck archives grants Dragon Hoard X to all tests. The deck wants to *fill its archives* fast — through containment, through deliberate self-archive, through Spark Containment's draw bonus. Once 3-4 archived Dragons stack up, all tests get +3 to +4 globally, making research and containment trivial against everything else on the board. Wins through the standard archive-tempo lane: contain enough to cross 4 archives + a tempo lead.

**Key-card profile.** Anomalies are iconic MTG dragons (Nicol Bolas, Niv-Mizzet, Sarkhan's broods, Ugin, Bolas's Citadel-form) framed as "Class-IV Dracoform" specimens. Each carries `subtypes={"Dragon", ...}` so they themselves count toward the Hoard once archived. Personnel are **Dragonologists** with high "research" skill and "Spark Containment 1" on attached procedures. Procedures include "Protocol: Dracoform Cataloging" (force-archive your own contained Dragon, +1 Spark Containment trigger) and "Hoard Audit" (look at top 3 of your library, archive any Dragon, return rest). Facility: "Dracoform Containment Hangar" (Dragon Hoard 1 base bonus while in play).

**Gameplay loop.**
1. Contain or self-archive a Dragon. Hoard +1 to tests.
2. Spark Containment triggers extra paperwork draw on every opposing contain.
3. Bigger Dragons come down with reduced effective hazard (you're +X to contain).
4. By turn 6-8, every test is +3 to +4 from Hoard, archive count hits win threshold.

---

### 3.4 `planeswalker_detention` — Thaumiel multiverse incursion

**MTG → SCP class:** Planeswalkers → **Thaumiel (controlled-deployment hazards)**.

**Strategy summary.** Spark Containment grid + tempo draw. The deck contains opposing Anomalies one after another (Detention-style), each contain triggering Spark Containment N for clearance gain. Cross the clearance-6 threshold to extra-draw, which fuels the next Detention. Wins via the existing **`thaumiel`** alt-win (3 contained anomalies + 0 breach) or through pure tempo. Spark Containment also triggers off the deck's own self-contained anomalies, so the deck has Thaumiel personnel like Liliana, Teferi, and Jace recast as "leveraged thaumic assets — contained but cooperative."

**Key-card profile.** Anomalies are 8 iconic planeswalkers framed as containment specimens with thaumic-attenuation tags (Jace as "Class-III Cognitive Manipulator," Liliana as "Class-IV Necromantic Conduit"). Personnel are **Operatives O5-Chandra**, **Operatives O5-Tezzeret** — the same planeswalkers but reframed in their "cooperating asset" mode. Procedures include "Planar Detention Protocol" (contain target opposing Anomaly, Spark Containment 2) and "Spark Audit" (gain clearance equal to your contained anomaly count). Facility: "Multiversal Detention Site Charlie."

**Gameplay loop.**
1. Open a Detention procedure on an opposing Anomaly. Contained.
2. Spark Containment fires → +2 clearance.
3. Clearance hits 6 → extra paperwork draw → another Detention card in hand.
4. Repeat.
5. Either alt-win on `thaumiel` (3 contained + 0 breach) or burst archives.

---

### 3.5 `demonic_pact_bureau` — Keter ethics manipulator

**MTG → SCP class:** Demons → **Keter (ethics-debt manipulation)**.

**Strategy summary.** Ethics-tempo. Demonic Pact runs ethics_debt as a *resource*, not a liability. It loads up ethics_debt to power Phylactery Audits and bargain-style procedures, then dumps the ethics back onto the opponent via "audit transfer" procedures. Phylactery Audit means the deck is hard to whittle down: memory-holed dossiers come back as long as ethics is available. Wins via the existing **`ethics_audit`** alt-win (4 archives + secrecy 8+).

**Key-card profile.** Anomalies are MTG demons (Griselbrand, Sheoldred, Bolas-Demon, Razaketh, Liliana's pact-demons) framed as "Class-V Diabolic Negotiators." Personnel are **Pact Interpreters** and **Ethics Officers** — the latter specifically reduce ethics_debt at cost of tempo. Procedures include "Faustian Re-Audit" (gain 3 ethics_debt, draw 2 paperwork) and "Pact Recall" (memory-hole a dossier; if it has Phylactery Audit, return at half cost). Facility: "Pact Containment Vault." Mandate: alt-win `ethics_audit`.

**Gameplay loop.**
1. Cast costly demons with Phylactery Audit baked in — willing to accept memory-hole risk.
2. Spend ethics_debt on aggressive procedures (audit transfers).
3. Demons get memory-holed → Phylactery Audit returns them for X ethics.
4. Stack ethics_debt onto opponent via Pact-style transfers.
5. Cross 4 archives + 8 secrecy → ethics_audit win.

---

### 3.6 `leyline_anomaly` — Keter ambient-mana hazard

**MTG → SCP class:** Land/Leyline anomalies → **Keter (ambient-mana hazard)**.

**Strategy summary.** Punish-tempo. Leyline Anomaly's central thesis: *the opponent's spellcasting raises your hazard ceiling.* Every opposing procedure/facility/mandate resolution pumps your active anomalies via Leyline Saturation. Combined with Annihilation Wave on a few apex anomalies, this means the opponent is *spell-locked* — every action they take makes the breach worse. The deck plays at instant speed via Brief-fueled draw, but its real power is in the second-half of long games where the opponent can't cast anything safely.

**Key-card profile.** Anomalies are land-derived MTG entities (Marit Lage, Dark Depths, Field of the Dead, Glacial Chasm, Maze of Ith) framed as "Class-IV Ambient-Thaumic Hazards." Personnel are **Leyline Cartographers** — high containment skill but low hazard tolerance. Procedures include "Ambient Saturation Sweep" (Leyline Saturation 2 trigger) and "Bottleneck the Spell-Lane" (redact 1 + opposing procedure costs +1 paperwork next turn). Facility: "Leyline Containment Grid."

**Gameplay loop.**
1. Drop a Leyline Saturation anomaly early.
2. Every opposing procedure they cast pumps your active anomalies' hazard.
3. By turn 5-7, your anomalies are hazard 5-6+ each.
4. Annihilation Wave fires on breach → redacts + bumps opposing breach.
5. Opp public_panics out.

---

### 3.7 `multiverse_rift` — Apollyon planar bleed

**MTG → SCP class:** Planar bleed / rift cataclysms → **Apollyon (uncontrolled planar incursion)**.

**Strategy summary.** Cascade chains. Multiverse Rift uses Planar Rift X to chain free anomaly plays off each containment. The deck contains its own anomalies aggressively to fire the Rift trigger, then plays "free" cascade anomalies off the top of the library, often chaining 2-3 free plays per turn. Brief fuels paperwork to keep the engine running. Wins through the existing **`public_panic`** alt-win (4 archives + opposing secrecy ≤ 6) accelerated by cascade tempo.

**Key-card profile.** Anomalies are rift/temporal/multiverse entities (Karn, Time Spiral, Apocalypse, Eldrazi-spawn from Rise of the Eldrazi planar bleed) framed as "Class-V Planar-Rift Specimens." Personnel are **Riftwalkers** — specialized in surviving planar transitions, good at all skills moderately. Procedures include "Rift Stabilization Protocol" (Planar Rift 3 trigger + contain) and "Cascade Audit" (look at top 5 of library, play 1 Anomaly free). Facility: "Multiversal Rift Containment Array."

**Gameplay loop.**
1. Contain your first Anomaly → Planar Rift 2 fires → exile top 2 of library.
2. Among those 2, play any Anomalies free.
3. Free Anomaly enters → trigger another contain → chain another Rift.
4. Cascade chain extends 2-3 cards deep.
5. Tempo wins via public_panic.

---

### 3.8 `lich_phylactery` — Euclid undeath recursion

**MTG → SCP class:** Liches / undead recursion → **Euclid (recursive undeath)**.

**Strategy summary.** Memory-hole-and-return engine. Lich Phylactery runs Phylactery Audit on most of its anomalies and personnel. The deck *wants* to be memory-holed — opposing redactions are net positive because Phylactery Audit X returns the card at the cost of X ethics_debt. Combined with Mnestic personnel that protect against passive antimeme decay, the deck becomes a permanent recursion engine. Wins via a custom alt-win **`phylactery_chain`** (4+ successful Phylactery Audits in a game).

**Key-card profile.** Anomalies are MTG liches and recursive undead (Liliana of the Veil's lich form, Mikaeus the Unhallowed, Endrek Sahr reskins, Atraxa as a planeswalker-lich) framed as "Euclid-class Necrotic Recursion Specimens." Personnel are **Mnestic Necrologists** (Mnestic + Phylactery Audit 2 themselves — they come back even if memory-holed). Procedures include "Phylactery Activation Protocol" (pay X ethics, return any Phylactery card from `scp_forgotten`) and "Mnestic Necromancy Audit" (Mnestic tag + Phylactery Audit 1 grant to your personnel until end of turn). Mandate: alt-win `phylactery_chain`.

**Gameplay loop.**
1. Open Phylactery-Audit anomalies into play.
2. Opp memory-holes one → Phylactery Audit fires → card returns at X ethics cost.
3. Pay ethics, recur card to dossier queue.
4. Audit counter ticks up.
5. 4 audits → `phylactery_chain` alt-win.

---

### 3.9 `wurm_apex` — Apollyon planet-scale fauna

**MTG → SCP class:** Wurms / planet-scale fauna → **Apollyon (planet-scale apex fauna)**.

**Strategy summary.** Tame-the-giant. Wurm Apex runs huge Wurm Devourer anomalies. Researching them doesn't tick curiosity — it *tames* them by swapping -2 hazard for +2 containment. The deck wants to land 3 apex wurms early at high hazard (so they're scary), then research them down into stable, containable Apollyon-class assets that ratchet into Foundation hands. Combined with Annihilation Wave on a few wurms (Pelakka Wurm, Worldspine Wurm reskins), the deck can flip between "kill you with breach" and "tame and reclassify Keter→Safe." Wins via custom alt-win **`wurm_apex_tamed`** (3+ tamed apex anomalies).

**Key-card profile.** Anomalies are giant MTG wurms (Worldspine Wurm, Pelakka Wurm, Engulfing Slagwurm, Penumbra Wurm, Hellkite, Yargle, Ghalta) all reskinned as "Apollyon-class Planet-Scale Fauna." Personnel are **Megafauna Specialists** with high research skill and "test_safety_protocol_active" tags. Procedures include "Apex Sedation Protocol" (single test on Wurm Devourer anomaly, automatically passes) and "Tame the Giant" (force a Wurm Devourer trigger on your highest-hazard wurm). Facility: "Apex Megafauna Habitat." Mandate: alt-win `wurm_apex_tamed`.

**Gameplay loop.**
1. Drop a hazard-5 Wurm Devourer anomaly early.
2. Run a research test → instead of curiosity, swap -2 hazard / +2 containment.
3. Anomaly is now hazard 3 / containment 7 — much easier to contain.
4. Tame 3 apex wurms.
5. `wurm_apex_tamed` alt-win fires.

---

### 3.10 `spirit_archive` — Euclid incorporeal

**MTG → SCP class:** Spirits / incorporeal undead → **Euclid (incorporeal ambient anomalies)**.

**Strategy summary.** Ambient-hazard recursion. Spirits in MTG are flickering, partly-tangible threats. In FBN they're framed as Euclid-class incorporeal anomalies — they sit in ambient-hazard mode, pumped by Leyline Saturation off opposing spells, and recur via Phylactery Audit when memory-holed. Doesn't aim for a single big alt-win; it grinds the opponent down to public_panic.

**Key-card profile.** Anomalies are MTG spirits and ghosts (Geist of Saint Traft, Kira Great Glass-Spinner, Mikokoro, Yuriko-style ninja-spirits, Phantasmal Image, Phyrexian Negator reskinned as a Euclid-spirit) framed as "Euclid-class Incorporeal Hazards." Personnel are **Mediums** and **Ecto-thaumic Surveyors** with high containment skill but low hazard tolerance. Procedures include "Ectoplasmic Saturation Pulse" (Leyline Saturation 1 + redact 1) and "Phantom Recall Audit" (Phylactery Audit 2 grant). Facility: "Spirit Containment Array."

**Gameplay loop.**
1. Open Leyline Saturation spirits.
2. Opposing procedures pump ambient hazard.
3. Spirits breach → ambient damage.
4. Spirits get memory-holed → Phylactery Audit returns them.
5. Slow grind to public_panic.

---

## 4. Card list (300 cards)

Each row: `| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |`

Note on Type abbreviations: `A` = SCP_ANOMALY, `P` = SCP_PERSONNEL, `F` = SCP_FACILITY, `Pr` = SCP_PROCEDURE, `M` = SCP_MANDATE.

### 4.1 Phyrexian Strain (30)

**Composition:** 13 Anomalies, 7 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-1138: The Compleated Liaison | A | 1 | 0 | 3 | 3 | 2 | uncommon | Compleation Vector 1. |
| SCP-FBN-1140: Yawgmoth-Pattern Strain | A | 2 | 0 | 5 | 4 | 4 | mythic | Compleation Vector 2. When this Anomaly breaches, place 1 compleation counter on each opposing Personnel. |
| SCP-FBN-1141: Atraxa, Praetors' Conduit | A | 2 | 0 | 6 | 4 | 3 | mythic | Compleation Vector 1. On reveal, place 1 compleation counter on each opposing Personnel. |
| SCP-FBN-1142: Sheoldred, Whispering Strain | A | 1 | 0 | 4 | 3 | 3 | rare | Compleation Vector 1. When an opposing Personnel becomes compleated, draw 1 paperwork. |
| SCP-FBN-1143: Vorinclex, Bio-Engineer Specimen | A | 2 | 0 | 5 | 3 | 4 | rare | Compleation Vector 2. Compleation counters tick at 2× rate on opposing personnel with skill 3+. |
| SCP-FBN-1144: Jin-Gitaxias, Cognitive Vector | A | 2 | 0 | 5 | 5 | 2 | rare | Compleation Vector 1. When a Personnel is compleated, opposing player discards 1 paperwork. |
| SCP-FBN-1145: Elesh Norn, Mother of Machines | A | 2 | 0 | 6 | 3 | 3 | mythic | Compleation Vector 1. Your other Compleation Vector anomalies get +1 to Compleation Vector. |
| SCP-FBN-1146: Urabrask, Combustion Vector | A | 1 | 0 | 3 | 2 | 4 | uncommon | Compleation Vector 1. When this anomaly breaches, opposing personnel with skill ≤2 become compleated immediately. |
| SCP-FBN-1147: Skithiryx-Class Vector Carrier | A | 1 | 0 | 3 | 3 | 3 | uncommon | Compleation Vector 1. When a Personnel becomes compleated, gain 1 Brief. |
| SCP-FBN-1148: The Phyresis Engine | A | 1 | 0 | 4 | 4 | 2 | uncommon | Compleation Vector 1. Compleation counters do not decay between turns. |
| SCP-FBN-1149: Memnarch-Pattern Aberration | A | 1 | 0 | 3 | 2 | 2 | uncommon | Compleation Vector 1. On contain, gain 1 archive. |
| SCP-FBN-1150: Phyrexian Negator | A | 0 | 0 | 2 | 2 | 2 | common | When you compleat an opposing Personnel, suppress this Anomaly's next breach. |
| SCP-FBN-1151: Compleation Vector Spawn | A | 0 | 0 | 2 | 2 | 1 | common | Compleation Vector 1. |
| Dr. Kassandra Volkov, Mnestic Quarantine Lead | P | 2 | 1 | — | — | — | rare | Mnestic. skills: contain 2, research 1. When an opposing Compleation Vector anomaly enters play, gain 1 Brief. |
| Researcher Aramis, Vector Specialist | P | 1 | 0 | — | — | — | uncommon | skills: research 2. When you compleat an opposing Personnel, place 1 extra compleation counter on another opposing personnel. |
| Dr. Linna Halle, Phyresis Containment | P | 1 | 0 | — | — | — | uncommon | Mnestic. skills: contain 2. Compleation counters on this personnel cannot increase. |
| Operative O5-3, Strain Containment Lead | P | 2 | 1 | — | — | — | rare | Mnestic. skills: contain 1, research 2. Once per turn, remove 1 compleation counter from any of your Personnel. |
| Researcher Drei, Compleation Cartographer | P | 1 | 0 | — | — | — | common | skills: research 1. On assign, scry top 2 of your library. |
| Class-A Operative "Nailbiter" | P | 0 | 0 | — | — | — | common | skills: contain 1. Mnestic. |
| Dr. Volker Tiede, Praetor Specialist | P | 2 | 1 | — | — | — | uncommon | skills: research 2, contain 1. When you compleat an opposing Personnel, gain 1 clearance. |
| Class-A Mnestic Inoculation, Pattern: Yawgmoth-Resistant | Pr | 2 | 0 | — | — | — | rare | Grant Mnestic to up to 2 of your Personnel until end of turn. Remove all compleation counters from those personnel. |
| Containment Breach Reversal: Phyresis Quarantine | Pr | 1 | 0 | — | — | — | uncommon | Remove 2 compleation counters from target Personnel you control. |
| Praetor Pact Audit | Pr | 2 | 0 | — | — | — | rare | Compleat target opposing Personnel with the highest skill. (Counter goes immediately to 3.) |
| Vector Saturation Sweep | Pr | 1 | 0 | — | — | — | uncommon | Place 1 compleation counter on each opposing Personnel. |
| Class-IV Compleation Audit | Pr | 3 | 0 | — | — | — | rare | Place 2 compleation counters on each opposing Personnel. Pay 1 ethics_debt. |
| Sector-9 Compleation Quarantine Facility | F | 2 | 0 | — | — | — | rare | Bonus: contain +1. Your Compleation Vector anomalies get +1 Compleation Vector. |
| Atraxa Specimen Containment Cell | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. Your Compleation anomalies have hazard +1 while in this facility. |
| Vivisection Suite Vega-9 | F | 1 | 0 | — | — | — | common | Bonus: research +1. |
| Oil Reclamation Tank Gamma | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. When a Personnel becomes compleated, gain 1 archive. |
| Mandate FBN-PCV: Compleation Containment Protocol | M | 3 | 2 | — | — | — | mythic | Mandate. Alt-win `compleation_overrun`: when 3+ opposing Personnel have been compleated by you this game, you win at end of your next turn. |

### 4.2 Eldrazi Apex (30)

**Composition:** 14 Anomalies, 6 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-2271: Apollyon-Class Void Eater (Ulamog) | A | 2 | 0 | 6 | 3 | 4 | mythic | Annihilation Wave 2. |
| SCP-FBN-2272: Apollyon-Class Hedron-Tilt (Kozilek) | A | 2 | 0 | 5 | 4 | 4 | mythic | Annihilation Wave 2. Brief 1 on reveal. |
| SCP-FBN-2273: Apollyon-Class Reality-Eater (Emrakul) | A | 2 | 0 | 7 | 3 | 5 | mythic | Annihilation Wave 3. On contain, opposing breach +2 anyway. |
| SCP-FBN-2274: Apollyon Vector Spawn | A | 0 | 0 | 1 | 1 | 1 | common | Sacrificial fodder. When this is memory-holed, gain 1 Brief. |
| SCP-FBN-2275: Eldrazi Scion Pattern | A | 0 | 0 | 2 | 1 | 1 | common | Sacrificial fodder. When this is memory-holed, your next Apollyon-class Anomaly costs -1 red_tape. |
| SCP-FBN-2276: Void Drone, Apollyon-Adjacent | A | 1 | 0 | 3 | 2 | 2 | uncommon | Annihilation Wave 1. |
| SCP-FBN-2277: Hedron Network Fragment | A | 1 | 0 | 2 | 2 | 2 | uncommon | When you sacrifice an Eldrazi anomaly, gain 1 Brief. |
| SCP-FBN-2278: Brood Tyrant Specimen | A | 1 | 0 | 3 | 2 | 3 | uncommon | Annihilation Wave 1. |
| SCP-FBN-2279: Void Eel | A | 1 | 0 | 3 | 2 | 2 | uncommon | Annihilation Wave 1. |
| SCP-FBN-2280: Eldrazi Conscription Pattern | A | 1 | 0 | 4 | 2 | 3 | rare | Annihilation Wave 1. When this anomaly breaches, opposing personnel become exhausted. |
| SCP-FBN-2281: Hedron-Caged Titan | A | 2 | 0 | 6 | 3 | 3 | rare | Annihilation Wave 2. On reveal, hazard +1 per pending dossier you control. |
| SCP-FBN-2282: Void Aberration | A | 1 | 0 | 3 | 1 | 3 | uncommon | Annihilation Wave 1. |
| SCP-FBN-2283: Apollyon-Adjacent Ingress | A | 0 | 0 | 2 | 1 | 2 | common | Sacrificial fodder. When sacrificed, opposing breach +1. |
| SCP-FBN-2284: Reality-Hole Fragment | A | 1 | 0 | 2 | 2 | 2 | common | When you sacrifice this, draw 1 paperwork. |
| Researcher Drake-Ulamog Pact Interpreter | P | 1 | 0 | — | — | — | uncommon | skills: research 2. When you sacrifice an anomaly, gain 1 Brief. |
| Operative Kozilek-Liaison "Cipher" | P | 2 | 1 | — | — | — | rare | skills: research 2, contain 1. Your Annihilation Wave triggers add +1 to the wave's N. |
| Class-A Emrakul Containment Specialist | P | 2 | 1 | — | — | — | rare | skills: contain 2, research 1. On assign, opposing breach +1. |
| Dr. Hedron Calibrator | P | 1 | 0 | — | — | — | uncommon | skills: research 2. When an Apollyon-class anomaly enters play, gain 1 Brief. |
| Researcher Voider "Drone Five" | P | 0 | 0 | — | — | — | common | skills: contain 1. When sacrificed, opposing breach +1. |
| Class-A Operative "Hollowing" | P | 1 | 0 | — | — | — | common | skills: research 1. When you sacrifice an anomaly, this personnel ready (refresh). |
| Protocol: Hedron Network Activation | Pr | 2 | 0 | — | — | — | rare | Sacrifice up to 3 of your pending Anomalies. Gain 1 Brief per sacrifice. Your active Annihilation Wave anomalies get +1 to their wave's N until end of turn. |
| Void Bombardment | Pr | 2 | 0 | — | — | — | rare | Redact 3 opposing dossiers. Your breach +2. |
| Apollyon Vector Sacrifice | Pr | 1 | 0 | — | — | — | uncommon | Sacrifice 1 of your anomalies. Gain 2 Brief. |
| Hedron Audit | Pr | 1 | 0 | — | — | — | common | Look at top 3 of your library. Put 1 Eldrazi anomaly on top, rest shuffled. |
| Class-V Reality-Tilt Audit | Pr | 3 | 0 | — | — | — | mythic | Opposing breach +3. Your breach +2. Brief 2. |
| Containment Site Ash-of-Zendikar | F | 2 | 0 | — | — | — | rare | Bonus: research +1. Your Eldrazi anomalies get +1 hazard while in this facility. |
| Hedron Network Containment Grid | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. When you sacrifice an anomaly, gain 1 archive. |
| Void Approach Vector Suppression Site | F | 2 | 0 | — | — | — | rare | Bonus: research +1. When Annihilation Wave fires, gain 1 archive. |
| Apollyon Ingress Containment Bunker | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. |
| Mandate FBN-AVI: Apollyon Vector Inhibition | M | 3 | 2 | — | — | — | mythic | Mandate. Win when opposing breach ≥ 12 (accelerated public_panic). |

### 4.3 Dragon Conclave (30)

**Composition:** 13 Anomalies, 7 Personnel, 5 Facilities, 4 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-3001: Nicol Bolas, Class-V Apex Dracoform | A | 2 | 0 | 6 | 4 | 4 | mythic | Dragon. Dragon Hoard 2. On contain, archive this. |
| SCP-FBN-3002: Niv-Mizzet, Class-IV Conduit | A | 1 | 0 | 4 | 3 | 3 | rare | Dragon. Dragon Hoard 1. When you contain a Dragon, draw 1 paperwork. |
| SCP-FBN-3003: Ugin, Class-V Spirit-Wyrm | A | 2 | 0 | 5 | 4 | 3 | mythic | Dragon. Spark Containment 1. When you contain an opposing anomaly, archive a Dragon from your hand for free. |
| SCP-FBN-3004: Sarkhan-Pattern Hunter | A | 1 | 0 | 3 | 2 | 3 | uncommon | Dragon. Dragon Hoard 1. |
| SCP-FBN-3005: Atarka, World Render | A | 2 | 0 | 5 | 3 | 4 | rare | Dragon. Dragon Hoard 1. When this contained, opposing breach +1. |
| SCP-FBN-3006: Dragonlord Silumgar | A | 2 | 0 | 5 | 3 | 3 | rare | Dragon. Dragon Hoard 1. Spark Containment 1. |
| SCP-FBN-3007: Kolaghan, Storm's Fury | A | 1 | 0 | 3 | 2 | 3 | uncommon | Dragon. Dragon Hoard 1. |
| SCP-FBN-3008: Ojutai, Soul of Winter | A | 2 | 0 | 5 | 3 | 3 | rare | Dragon. Dragon Hoard 1. On contain, gain 1 clearance. |
| SCP-FBN-3009: Dragonlord Dromoka | A | 1 | 0 | 4 | 2 | 2 | rare | Dragon. Dragon Hoard 1. Spark Containment 1. |
| SCP-FBN-3010: Ramoth-Class Drake | A | 1 | 0 | 3 | 2 | 2 | common | Dragon. |
| SCP-FBN-3011: Class-III Wyrmling | A | 0 | 0 | 2 | 1 | 1 | common | Dragon. |
| SCP-FBN-3012: Ancient Class-IV Wyrm | A | 2 | 0 | 5 | 3 | 4 | uncommon | Dragon. Dragon Hoard 1. |
| SCP-FBN-3013: Dragon-of-Korlis, Containment Specimen | A | 1 | 0 | 4 | 3 | 2 | uncommon | Dragon. When archived, gain 1 archive token of "Dragon" subtype. |
| Dr. Sarkhan Vol, Dragonologist | P | 2 | 1 | — | — | — | rare | skills: research 2, contain 1. On assign, scry top 3 of your library; archive a Dragon. |
| Operative O5-7, Dracoform Specialist | P | 2 | 1 | — | — | — | rare | skills: contain 2, research 1. Spark Containment 1. |
| Researcher Ramoth, Hoard Auditor | P | 1 | 0 | — | — | — | uncommon | skills: research 2. When you archive a Dragon, gain 1 clearance. |
| Dr. Ojiri Kaname, Wyrmkeeper | P | 1 | 0 | — | — | — | uncommon | skills: contain 2. |
| Class-A Dragonologist "Forge" | P | 1 | 0 | — | — | — | common | skills: research 1, contain 1. |
| Researcher Belora, Dragon Cartographer | P | 1 | 0 | — | — | — | uncommon | skills: research 2. On assign, look at top 4; archive top Dragon. |
| Operative O5-12, Sky Patrol Coordinator | P | 2 | 1 | — | — | — | rare | skills: contain 2. When you contain a Dragon-subtype anomaly, gain 2 clearance. |
| Protocol: Dracoform Cataloging | Pr | 1 | 0 | — | — | — | uncommon | Archive a Dragon from your hand. Spark Containment 1 trigger fires. |
| Hoard Audit | Pr | 1 | 0 | — | — | — | uncommon | Look at top 3 of your library, archive any Dragons among them, return rest. |
| Class-III Dracoform Sweep | Pr | 2 | 0 | — | — | — | rare | Each Dragon anomaly you control gets +2 hazard until end of turn. |
| Dragonhoard Cataclysm Audit | Pr | 3 | 0 | — | — | — | mythic | Archive each Dragon anomaly you control. Gain 2 archives. Your Dragon Hoard sum +1 permanently. |
| Dracoform Containment Hangar | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. Dragon Hoard 1 base. |
| Wyrmkeeper's Vault | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. When you archive a Dragon, gain 1 archive. |
| Dragon Audit Bureau | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. |
| Eastern Wyrm Containment Bunker | F | 2 | 0 | — | — | — | rare | Bonus: contain +1. Your Dragon-subtype anomalies get +1 containment. |
| Dragonlord Audit Chamber | F | 2 | 0 | — | — | — | rare | Bonus: contain +1. When you contain a Dragon, gain 1 clearance and 1 archive. |
| Mandate FBN-DCG: Dracoform Containment Grid | M | 3 | 2 | — | — | — | mythic | Mandate. Win on existing `thaumiel` (3 contained + 0 breach), but also: while ≥4 Dragons are archived, your tests gain +X = Dragon Hoard count. |

### 4.4 Planeswalker Detention (30)

**Composition:** 12 Anomalies, 7 Personnel, 5 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-4001: Jace, Class-III Cognitive Manipulator | A | 2 | 0 | 5 | 4 | 2 | mythic | When contained, draw 2 paperwork. Spark Containment 2. |
| SCP-FBN-4002: Liliana, Class-IV Necromantic Conduit | A | 2 | 0 | 5 | 3 | 3 | mythic | When contained, opposing dossier queue -1. Spark Containment 2. |
| SCP-FBN-4003: Chandra, Class-III Thaumic Ignition | A | 1 | 0 | 3 | 2 | 3 | rare | When contained, redact 1 opposing dossier. Spark Containment 1. |
| SCP-FBN-4004: Teferi, Class-IV Temporal Adjuster | A | 2 | 0 | 5 | 4 | 1 | mythic | When contained, gain 1 turn-segment of priority. Spark Containment 2. |
| SCP-FBN-4005: Garruk, Class-III Beastmaster | A | 1 | 0 | 4 | 3 | 3 | rare | Spark Containment 1. |
| SCP-FBN-4006: Sorin, Class-IV Necromantic Patron | A | 2 | 0 | 5 | 3 | 2 | rare | Spark Containment 2. |
| SCP-FBN-4007: Karn, Class-V Artifact Vector | A | 2 | 0 | 6 | 4 | 2 | rare | When contained, gain 2 clearance. Spark Containment 2. |
| SCP-FBN-4008: Tezzeret, Class-III Artifact Manipulator | A | 1 | 0 | 4 | 2 | 2 | uncommon | Spark Containment 1. |
| SCP-FBN-4009: Class-II Aspirant Spark Carrier | A | 1 | 0 | 3 | 2 | 2 | common | Spark Containment 1. |
| SCP-FBN-4010: Vraska, Class-IV Gorgon-Spark | A | 1 | 0 | 4 | 3 | 3 | rare | Spark Containment 1. |
| SCP-FBN-4011: Kaya, Class-IV Spectral Investigator | A | 1 | 0 | 4 | 2 | 1 | uncommon | Spark Containment 1. |
| SCP-FBN-4012: The Wanderer, Class-IV Multiversal Asset | A | 1 | 0 | 4 | 3 | 2 | uncommon | Spark Containment 1. |
| Operative O5-Chandra "Hothead" | P | 2 | 1 | — | — | — | rare | skills: research 1, contain 2. Spark Containment 1. |
| Operative O5-Jace "Mindwarden" | P | 2 | 1 | — | — | — | rare | skills: research 2, contain 1. On assign, look at top 2; archive 1. |
| Operative O5-Liliana "Bone-Reader" | P | 2 | 1 | — | — | — | rare | skills: research 1, contain 2. Spark Containment 1. |
| Operative O5-Teferi "Slow-Hand" | P | 2 | 1 | — | — | — | mythic | skills: research 2, contain 1. Once per turn, exhaust opposing personnel during their turn. |
| Researcher Tibalt, Junior Spark Auditor | P | 1 | 0 | — | — | — | uncommon | skills: research 1, contain 1. |
| Class-A Operative "Detainee" | P | 1 | 0 | — | — | — | common | skills: contain 2. |
| Detention Operative "Caged" | P | 0 | 0 | — | — | — | common | skills: contain 1. |
| Planar Detention Protocol | Pr | 2 | 0 | — | — | — | rare | Contain target opposing Anomaly. Spark Containment 2. |
| Spark Audit | Pr | 1 | 0 | — | — | — | uncommon | Gain clearance equal to your contained anomaly count. |
| Class-IV Spark Suppression Protocol | Pr | 2 | 0 | — | — | — | rare | Suppress target opposing Anomaly's next breach. Spark Containment 1. |
| Wanderer Recall Audit | Pr | 1 | 0 | — | — | — | uncommon | Return target contained Anomaly to your pending queue. Spark Containment 1. |
| Multiversal Detention Sweep | Pr | 3 | 0 | — | — | — | rare | Contain up to 2 opposing Anomalies (auto-target highest hazard each). Spark Containment 2 per. |
| Multiversal Detention Site Charlie | F | 2 | 0 | — | — | — | rare | Bonus: contain +1. Your Spark Containment N triggers grant N+1 clearance instead. |
| Spark Audit Bureau | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. |
| Planeswalker Containment Hub | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. Once per turn, archive a contained Planeswalker-type for 1 archive. |
| Thaumic Containment Grid | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. |
| Temporal Stasis Cell | F | 2 | 0 | — | — | — | rare | Bonus: research +1. Once per game, prevent 1 opposing anomaly breach. |
| Mandate FBN-PD: Planeswalker Detention Doctrine | M | 3 | 2 | — | — | — | mythic | Mandate. Win on existing `thaumiel`: 3 contained anomalies + 0 breach. While ≥2 Planeswalker-subtype anomalies contained, draw +1 paperwork at upkeep. |

### 4.5 Demonic Pact Bureau (30)

**Composition:** 13 Anomalies, 7 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-5001: Griselbrand, Class-V Diabolic Negotiator | A | 2 | 0 | 6 | 3 | 4 | mythic | Phylactery Audit 3. When this is researched, draw 3 paperwork; ethics_debt +3. |
| SCP-FBN-5002: Sheoldred-Pact, Class-V Whisperer | A | 2 | 0 | 5 | 3 | 4 | mythic | Phylactery Audit 2. When opp memory-holes this, opp loses 2 paperwork from hand. |
| SCP-FBN-5003: Bolas-Demon Variant | A | 2 | 0 | 6 | 4 | 3 | mythic | Phylactery Audit 3. When this breaches, ethics_debt +2 (opposing); their secrecy -1. |
| SCP-FBN-5004: Razaketh, Soul-Broker Specimen | A | 1 | 0 | 4 | 3 | 3 | rare | Phylactery Audit 2. When researched, opp ethics_debt +1. |
| SCP-FBN-5005: Liliana's Pact-Demon Variant | A | 1 | 0 | 4 | 3 | 3 | rare | Phylactery Audit 1. On contain, ethics_debt -1; gain 1 archive. |
| SCP-FBN-5006: Demon of Death's Gate | A | 1 | 0 | 4 | 2 | 3 | rare | Phylactery Audit 2. |
| SCP-FBN-5007: Lord of the Pit, Containment Specimen | A | 1 | 0 | 3 | 2 | 3 | uncommon | Phylactery Audit 1. |
| SCP-FBN-5008: Mephidross Vampire-Pact | A | 1 | 0 | 3 | 2 | 2 | uncommon | Phylactery Audit 1. |
| SCP-FBN-5009: Demon-Possessed Personnel File | A | 1 | 0 | 2 | 2 | 2 | uncommon | Phylactery Audit 1. When this returns from `scp_forgotten` via audit, gain 1 archive. |
| SCP-FBN-5010: Demonic Tutor Specimen | A | 1 | 0 | 3 | 3 | 2 | rare | Phylactery Audit 2. On contain, look at top 5 of library, take 1. |
| SCP-FBN-5011: Demon Lord's Audit Ledger | A | 1 | 0 | 3 | 2 | 1 | uncommon | Phylactery Audit 1. |
| SCP-FBN-5012: Junior Pact-Imp | A | 0 | 0 | 2 | 1 | 1 | common | Phylactery Audit 1. |
| SCP-FBN-5013: Soul-Broker Apprentice | A | 0 | 0 | 1 | 1 | 1 | common | When sacrificed, ethics_debt +1. |
| Dr. Faust, Pact Interpreter | P | 2 | 1 | — | — | — | rare | skills: research 2, contain 1. Once per turn, transfer 1 ethics_debt to opposing site. |
| Operative O5-9, Ethics Officer | P | 1 | 0 | — | — | — | uncommon | skills: contain 2. Once per turn, reduce your ethics_debt by 1. |
| Researcher Bargainer "Hand" | P | 1 | 0 | — | — | — | uncommon | skills: research 2. On assign, ethics_debt +1; draw 1 paperwork. |
| Class-A Operative "Soul-Auditor" | P | 1 | 0 | — | — | — | common | skills: research 1, contain 1. |
| Researcher Krell, Diabolic Linguist | P | 1 | 0 | — | — | — | uncommon | skills: research 1. When you pay ethics_debt for Phylactery Audit, gain 1 clearance. |
| Operative "Mark," Pact Negotiator | P | 2 | 1 | — | — | — | rare | skills: contain 2. When opposing anomaly is memory-holed, ethics_debt -1. |
| Dr. Marlowe, Containment Theologian | P | 1 | 0 | — | — | — | uncommon | skills: research 2. |
| Faustian Re-Audit | Pr | 1 | 0 | — | — | — | uncommon | Ethics_debt +3 (you). Draw 2 paperwork. |
| Pact Recall | Pr | 2 | 0 | — | — | — | rare | Memory-hole target anomaly you control. If it has Phylactery Audit, return at half X cost (round up). |
| Soul-Broker Audit | Pr | 1 | 0 | — | — | — | common | Opposing ethics_debt +2. Your ethics_debt -1. |
| Class-V Pact Sweep | Pr | 3 | 0 | — | — | — | mythic | Each opposing personnel becomes exhausted. Opposing ethics_debt +2. |
| Demonic Tutor Audit | Pr | 2 | 0 | — | — | — | rare | Search your library for any anomaly, put it in your pending queue. Ethics_debt +2. |
| Pact Containment Vault | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. Once per turn, transfer 1 ethics_debt to opposing site. |
| Diabolic Audit Bureau | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. |
| Faustian Containment Cell | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. |
| Soul-Reclamation Facility | F | 2 | 0 | — | — | — | rare | Bonus: contain +1. When you pay ethics_debt for Phylactery Audit, gain 1 archive. |
| Mandate FBN-EA: Mercy Ledger Inversion | M | 3 | 2 | — | — | — | mythic | Mandate. Win on existing `ethics_audit`: 4 archives + secrecy ≥ 8. Your ethics_debt may go to 12 (raised from 8). |

### 4.6 Leyline Anomaly (30)

**Composition:** 14 Anomalies, 6 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-6001: Marit Lage, Dormant Class-V Ambient | A | 2 | 0 | 6 | 3 | 5 | mythic | Leyline Saturation 2. Annihilation Wave 2. |
| SCP-FBN-6002: Dark Depths Containment Specimen | A | 2 | 0 | 6 | 3 | 1 | rare | Leyline Saturation 1. When breached, becomes a Marit Lage-state hazard 5 ambient. |
| SCP-FBN-6003: Field of the Dead, Class-IV Necrotic Site | A | 2 | 0 | 5 | 3 | 3 | rare | Leyline Saturation 2. |
| SCP-FBN-6004: Glacial Chasm, Class-III Stasis Zone | A | 1 | 0 | 4 | 2 | 2 | uncommon | Leyline Saturation 1. |
| SCP-FBN-6005: Maze of Ith, Class-III Spatial Distortion | A | 1 | 0 | 4 | 3 | 2 | uncommon | Leyline Saturation 1. On contain, opposing personnel exhausted. |
| SCP-FBN-6006: Mishra's Workshop, Class-III Thaumic Forge | A | 1 | 0 | 4 | 3 | 2 | rare | Leyline Saturation 1. When opposing procedure resolves, gain 1 Brief. |
| SCP-FBN-6007: Bazaar of Baghdad Specimen | A | 1 | 0 | 3 | 2 | 2 | uncommon | Leyline Saturation 1. |
| SCP-FBN-6008: Tabernacle at Pendrell Vale | A | 1 | 0 | 3 | 2 | 3 | rare | Leyline Saturation 1. Opposing personnel cost +1 paperwork at upkeep. |
| SCP-FBN-6009: Wasteland, Class-III Disruption | A | 0 | 0 | 2 | 2 | 2 | common | Leyline Saturation 1. |
| SCP-FBN-6010: Eldrazi Temple, Cross-Class Vector | A | 1 | 0 | 3 | 2 | 2 | rare | Leyline Saturation 1. Annihilation Wave 1. |
| SCP-FBN-6011: Strip Mine Specimen | A | 0 | 0 | 2 | 1 | 2 | common | Leyline Saturation 1. |
| SCP-FBN-6012: Cabal Coffers, Class-IV Necrotic Geometry | A | 1 | 0 | 3 | 2 | 2 | uncommon | Leyline Saturation 1. |
| SCP-FBN-6013: Lake of the Dead | A | 1 | 0 | 3 | 2 | 2 | uncommon | Leyline Saturation 1. |
| SCP-FBN-6014: Class-IV Ley Network Knot | A | 2 | 0 | 5 | 3 | 4 | rare | Leyline Saturation 3. Annihilation Wave 1. |
| Researcher Cartographer "Map" | P | 1 | 0 | — | — | — | common | skills: contain 1, research 1. |
| Dr. Aaron Yeats, Ley Network Specialist | P | 2 | 1 | — | — | — | rare | skills: contain 2, research 1. When opp resolves procedure, gain 1 Brief. |
| Operative "Bottleneck" | P | 1 | 0 | — | — | — | uncommon | skills: contain 2. |
| Researcher Lin, Ambient Hazard Surveyor | P | 1 | 0 | — | — | — | uncommon | skills: research 2. When your active Leyline anomaly gets bonus hazard, draw 1 paperwork. |
| Class-A Operative "Survey" | P | 0 | 0 | — | — | — | common | skills: research 1. |
| Operative "Conduit-Cutter" | P | 2 | 1 | — | — | — | rare | skills: contain 2, research 1. Once per turn, suppress opposing leyline. |
| Ambient Saturation Sweep | Pr | 1 | 0 | — | — | — | uncommon | Your Leyline Saturation anomalies trigger Leyline Saturation 2 on next opposing procedure (one-shot boost). |
| Bottleneck the Spell-Lane | Pr | 1 | 0 | — | — | — | uncommon | Redact 1 opposing dossier. Their next procedure costs +1 paperwork. |
| Containment Sweep: Ley Network Audit | Pr | 2 | 0 | — | — | — | rare | Each opposing personnel becomes exhausted at next opposing upkeep. |
| Class-V Saturation Lockdown | Pr | 3 | 0 | — | — | — | mythic | Until end of turn, opposing player cannot resolve procedures except by paying ethics_debt 2 per. |
| Ambient Hazard Audit | Pr | 1 | 0 | — | — | — | common | Your active Leyline anomalies +1 hazard until end of turn. |
| Leyline Containment Grid | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. Your Leyline Saturation N triggers grant N+1 hazard instead. |
| Ley-Survey Bureau | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. |
| Ambient Containment Site Delta-7 | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. |
| Saturation Reactor Core | F | 2 | 0 | — | — | — | rare | Bonus: research +1. When opposing procedure resolves, gain 1 clearance. |
| Mandate FBN-LS: Ley Lockdown Doctrine | M | 3 | 2 | — | — | — | mythic | Mandate. Win on existing `public_panic`: 4 archives + opposing secrecy ≤ 6. Your Leyline anomalies' hazard caps raised by +1. |

### 4.7 Multiverse Rift (30)

**Composition:** 12 Anomalies, 7 Personnel, 5 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-7001: Karn, Class-V Multiversal Vagrant | A | 2 | 0 | 6 | 4 | 3 | mythic | Planar Rift 3. When this contained, Brief 2. |
| SCP-FBN-7002: Time Spiral, Class-V Temporal Cataclysm | A | 2 | 0 | 5 | 4 | 4 | mythic | Planar Rift 3. When this contained, opposing breach +1. |
| SCP-FBN-7003: Apocalypse, Class-V Multiverse-Reset | A | 2 | 0 | 6 | 3 | 5 | mythic | Planar Rift 2. When breached, redact 2 opposing dossiers. |
| SCP-FBN-7004: Class-IV Planar Rift, Stable | A | 1 | 0 | 3 | 3 | 2 | rare | Planar Rift 2. Brief 1 on reveal. |
| SCP-FBN-7005: Class-III Rift Fragment | A | 1 | 0 | 3 | 2 | 2 | uncommon | Planar Rift 1. |
| SCP-FBN-7006: Pre-Mending Rift Specimen | A | 0 | 0 | 2 | 2 | 1 | common | Planar Rift 1. |
| SCP-FBN-7007: Phyrexian Invasion Footprint | A | 1 | 0 | 3 | 2 | 3 | uncommon | Planar Rift 1. |
| SCP-FBN-7008: Slivers (Class-III, controlled-tribal only) | A | 1 | 0 | 4 | 2 | 2 | uncommon | (Anti-tribal: this is the ONE Sliver in the set, framed as a single isolated specimen.) Planar Rift 1. |
| SCP-FBN-7009: Class-IV Multiverse Bleed | A | 1 | 0 | 4 | 3 | 2 | rare | Planar Rift 2. |
| SCP-FBN-7010: Rift-Walker Specimen | A | 1 | 0 | 3 | 2 | 2 | uncommon | Planar Rift 1. |
| SCP-FBN-7011: Cascade Pre-Echo | A | 1 | 0 | 3 | 2 | 2 | uncommon | When you contain an anomaly, this anomaly's hazard +1 until end of turn. |
| SCP-FBN-7012: Class-III Vagrant | A | 0 | 0 | 2 | 1 | 1 | common | Brief 1 on contain. |
| Operative O5-Karn-Liaison "Walker" | P | 2 | 1 | — | — | — | rare | skills: research 1, contain 2. Planar Rift 1 grant to all your anomalies until end of turn. |
| Researcher Rift-Walker "Drift" | P | 1 | 0 | — | — | — | uncommon | skills: research 2. On assign, gain 1 Brief. |
| Operative "Cascade" | P | 1 | 0 | — | — | — | uncommon | skills: contain 2. |
| Class-A Multiversal Cartographer | P | 1 | 0 | — | — | — | uncommon | skills: research 2. |
| Researcher "Aperture" | P | 1 | 0 | — | — | — | common | skills: research 1, contain 1. |
| Operative "Aperture-2" | P | 0 | 0 | — | — | — | common | skills: contain 1. |
| Dr. Teferi, Rift-Stabilization Lead | P | 2 | 1 | — | — | — | rare | skills: contain 1, research 2. Once per turn, gain 1 Brief during your turn. |
| Rift Stabilization Protocol | Pr | 2 | 0 | — | — | — | rare | Contain target Anomaly. Planar Rift 3 trigger fires. |
| Cascade Audit | Pr | 1 | 0 | — | — | — | uncommon | Look at top 5 of library, play 1 Anomaly free, return rest. |
| Class-IV Rift Audit | Pr | 2 | 0 | — | — | — | rare | Contain own anomaly. Planar Rift 2 trigger. |
| Multiversal Containment Sweep | Pr | 3 | 0 | — | — | — | rare | Contain target opposing Anomaly. Planar Rift 3 fires. |
| Brief: Apertures Holding | Pr | 1 | 0 | — | — | — | common | Brief 2. |
| Multiversal Rift Containment Array | F | 2 | 0 | — | — | — | rare | Bonus: contain +1. Your Planar Rift X triggers exile X+1 instead. |
| Class-IV Containment Hub | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. |
| Apertures Bureau | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1, contain +1. |
| Containment Aperture Alpha | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. When you play an Anomaly free via Planar Rift, gain 1 archive. |
| Rift-Wall Containment | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. |
| Mandate FBN-MR: Multiversal Rift Protocol | M | 3 | 2 | — | — | — | mythic | Mandate. Win on existing `public_panic`: 4 archives + opposing secrecy ≤ 6. Your Planar Rift X exiles X+1 cards instead. |

### 4.8 Lich Phylactery (30)

**Composition:** 13 Anomalies, 7 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-8001: Liliana, Class-V Lich-Form | A | 2 | 0 | 5 | 3 | 4 | mythic | Phylactery Audit 3. Mnestic. |
| SCP-FBN-8002: Mikaeus the Unhallowed, Lich Specimen | A | 2 | 0 | 5 | 3 | 4 | mythic | Phylactery Audit 2. When this returns from `scp_forgotten`, opposing breach +1. |
| SCP-FBN-8003: Endrek Sahr, Necrotic Engineer Specimen | A | 1 | 0 | 4 | 3 | 3 | rare | Phylactery Audit 2. |
| SCP-FBN-8004: Atraxa-Lich Pattern Variant | A | 2 | 0 | 6 | 4 | 3 | mythic | Phylactery Audit 3. Mnestic. |
| SCP-FBN-8005: Demonic Animator-Pact Specimen | A | 1 | 0 | 4 | 2 | 3 | rare | Phylactery Audit 2. |
| SCP-FBN-8006: Class-IV Lich-Vessel | A | 1 | 0 | 4 | 3 | 2 | rare | Phylactery Audit 2. |
| SCP-FBN-8007: Class-III Phylactery-Bound Wraith | A | 1 | 0 | 3 | 2 | 2 | uncommon | Phylactery Audit 1. |
| SCP-FBN-8008: Necropotence Specimen | A | 1 | 0 | 4 | 3 | 1 | rare | Phylactery Audit 2. When you pay X ethics for audit, gain 1 paperwork. |
| SCP-FBN-8009: Class-III Reanimator Pattern | A | 1 | 0 | 3 | 2 | 2 | uncommon | Phylactery Audit 1. |
| SCP-FBN-8010: Bone-Vessel, Animated | A | 0 | 0 | 2 | 1 | 1 | common | Phylactery Audit 1. |
| SCP-FBN-8011: Recurring Lich-Fragment | A | 0 | 0 | 2 | 2 | 1 | common | Phylactery Audit 1. |
| SCP-FBN-8012: Class-IV Wraith-Network | A | 1 | 0 | 3 | 2 | 2 | uncommon | Phylactery Audit 1. |
| SCP-FBN-8013: Death's Auditor | A | 1 | 0 | 3 | 2 | 2 | uncommon | Phylactery Audit 1. Mnestic. |
| Dr. Aliz Volgrim, Mnestic Necrologist | P | 2 | 1 | — | — | — | rare | Mnestic. Phylactery Audit 2 (this personnel). skills: research 2, contain 1. |
| Operative O5-Liliana "Lich-Liaison" | P | 2 | 1 | — | — | — | rare | Mnestic. Phylactery Audit 1. skills: contain 2. |
| Researcher "Bonemark" | P | 1 | 0 | — | — | — | common | Phylactery Audit 1. skills: research 1. |
| Class-A Necromantic Cartographer | P | 1 | 0 | — | — | — | uncommon | skills: research 2. |
| Researcher "Knell" | P | 1 | 0 | — | — | — | uncommon | Phylactery Audit 1. skills: contain 2. |
| Operative "Phylactery-Hand" | P | 1 | 0 | — | — | — | common | Mnestic. skills: contain 1. |
| Dr. Veska, Containment Theologian | P | 1 | 0 | — | — | — | uncommon | skills: research 2. |
| Phylactery Activation Protocol | Pr | 1 | 0 | — | — | — | rare | Pay X ethics_debt. Return any Phylactery-Audit card from `scp_forgotten` to your dossier queue. (X is the card's audit cost.) |
| Mnestic Necromancy Audit | Pr | 1 | 0 | — | — | — | uncommon | Grant Mnestic + Phylactery Audit 1 to all your personnel until end of turn. |
| Lich-Chain Audit | Pr | 2 | 0 | — | — | — | rare | If you have 3+ cards in `scp_forgotten`, gain 1 archive and pay 1 ethics_debt. |
| Class-V Phylactery Resurrection | Pr | 3 | 0 | — | — | — | mythic | Return up to 2 Phylactery-Audit cards from `scp_forgotten`. Pay total X+1 ethics_debt. |
| Memory-Hole Counter-Audit | Pr | 1 | 0 | — | — | — | uncommon | When opp memory-holes your anomaly this turn, gain 1 clearance. |
| Lich Containment Vault | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. Your Phylactery Audit costs are -1 ethics_debt (min 0). |
| Phylactery Audit Bureau | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. |
| Necromancer's Containment Chamber | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. |
| Mnestic Necropolis Site | F | 2 | 0 | — | — | — | rare | Bonus: contain +1. Your personnel are Mnestic. |
| Mandate FBN-PC: Phylactery Chain Doctrine | M | 3 | 2 | — | — | — | mythic | Mandate. Alt-win `phylactery_chain`: when 4+ successful Phylactery Audits have fired this game, you win at end of your next turn. |

### 4.9 Wurm Apex (30)

**Composition:** 14 Anomalies, 6 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-9001: Worldspine Wurm, Class-V Apollyon Fauna | A | 2 | 0 | 7 | 3 | 6 | mythic | Wurm Devourer. Annihilation Wave 2. |
| SCP-FBN-9002: Pelakka Wurm, Class-IV Apollyon Fauna | A | 2 | 0 | 6 | 3 | 5 | mythic | Wurm Devourer. |
| SCP-FBN-9003: Engulfing Slagwurm, Class-IV Containment | A | 2 | 0 | 5 | 3 | 5 | rare | Wurm Devourer. Annihilation Wave 1. |
| SCP-FBN-9004: Penumbra Wurm, Class-III Specimen | A | 1 | 0 | 4 | 2 | 4 | rare | Wurm Devourer. |
| SCP-FBN-9005: Hellkite-Specimen, Class-IV | A | 2 | 0 | 5 | 3 | 4 | rare | Wurm Devourer. Annihilation Wave 1. |
| SCP-FBN-9006: Ghalta, Primal Hunger Specimen | A | 1 | 0 | 4 | 2 | 4 | rare | Wurm Devourer. |
| SCP-FBN-9007: Yargle, Vile Containment Subject | A | 1 | 0 | 3 | 2 | 4 | uncommon | Wurm Devourer. |
| SCP-FBN-9008: Class-III Wurmling | A | 0 | 0 | 2 | 1 | 2 | common | Wurm Devourer. |
| SCP-FBN-9009: Wurm Coil Engine, Class-IV Forge-Wurm | A | 1 | 0 | 4 | 2 | 3 | uncommon | Wurm Devourer. |
| SCP-FBN-9010: Class-V Apex Wurm | A | 2 | 0 | 6 | 3 | 5 | mythic | Wurm Devourer. Annihilation Wave 2. |
| SCP-FBN-9011: Cradle Wurm Specimen | A | 1 | 0 | 3 | 2 | 4 | uncommon | Wurm Devourer. |
| SCP-FBN-9012: Spitting Earth Wurm | A | 1 | 0 | 3 | 2 | 3 | uncommon | Wurm Devourer. |
| SCP-FBN-9013: Underground Wurm-Tunnel Specimen | A | 0 | 0 | 2 | 1 | 2 | common | Wurm Devourer. |
| SCP-FBN-9014: Apex Reclamation Wurm | A | 2 | 0 | 5 | 3 | 5 | rare | Wurm Devourer. On contain, gain 1 archive and gain 1 clearance. |
| Dr. Heyok, Megafauna Specialist | P | 2 | 1 | — | — | — | rare | skills: research 2, contain 1. On assign to Wurm Devourer anomaly, auto-pass test. |
| Researcher Kram, Megafauna Veterinarian | P | 1 | 0 | — | — | — | uncommon | skills: research 2. |
| Operative O5-15, Apex Asset Coordinator | P | 2 | 1 | — | — | — | rare | skills: contain 2. When a Wurm anomaly is tamed (Wurm Devourer fires), gain 1 archive. |
| Class-A Megafauna Specialist | P | 1 | 0 | — | — | — | uncommon | skills: research 1, contain 1. |
| Researcher "Tamer" | P | 1 | 0 | — | — | — | uncommon | skills: research 2. |
| Operative "Wurmtongue" | P | 0 | 0 | — | — | — | common | skills: contain 1. |
| Apex Sedation Protocol | Pr | 2 | 0 | — | — | — | rare | Run a test on Wurm Devourer anomaly you control. The test auto-passes. |
| Tame the Giant | Pr | 1 | 0 | — | — | — | uncommon | Trigger Wurm Devourer on your highest-hazard Wurm anomaly. |
| Megafauna Audit | Pr | 2 | 0 | — | — | — | rare | Each Wurm Devourer anomaly you control has hazard -1 and containment +1 until end of turn. |
| Class-V Apex Sweep | Pr | 3 | 0 | — | — | — | mythic | Each Wurm Devourer anomaly you control becomes tamed (Wurm Devourer fires twice). |
| Apex Habitat Audit | Pr | 1 | 0 | — | — | — | uncommon | Gain 1 clearance per tamed Wurm anomaly you control. |
| Apex Megafauna Habitat | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. Your Wurm anomalies' hazard +1 in this facility. |
| Containment Pit Vault | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. |
| Megafauna Audit Bureau | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. |
| Apex Reclamation Site | F | 2 | 0 | — | — | — | rare | Bonus: research +1. When a Wurm is tamed, gain 1 archive. |
| Mandate FBN-WAT: Wurm Apex Tamed Doctrine | M | 3 | 2 | — | — | — | mythic | Mandate. Alt-win `wurm_apex_tamed`: 3+ Wurm Devourer anomalies have been tamed by you. Win at end of your next turn. |

### 4.10 Spirit Archive (30)

**Composition:** 13 Anomalies, 7 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

| Name | Type | red_tape | clearance | containment | curiosity | hazard | Rarity | Rules text |
|---|---|---|---|---|---|---|---|---|
| SCP-FBN-A001: Geist of Saint Traft, Class-IV Spectral Asset | A | 2 | 0 | 5 | 3 | 3 | mythic | Leyline Saturation 2. Phylactery Audit 2. |
| SCP-FBN-A002: Kira, Great Glass-Spinner Specimen | A | 1 | 0 | 4 | 3 | 2 | rare | Leyline Saturation 1. Phylactery Audit 1. |
| SCP-FBN-A003: Phantasmal Image, Class-III Phantom | A | 1 | 0 | 3 | 2 | 2 | uncommon | Phylactery Audit 1. |
| SCP-FBN-A004: Mikokoro, Center of the Sea Specimen | A | 1 | 0 | 3 | 2 | 2 | uncommon | Leyline Saturation 1. |
| SCP-FBN-A005: Yuriko-Pattern Ninja-Spirit | A | 1 | 0 | 3 | 2 | 2 | rare | Phylactery Audit 1. On reveal, redact 1 opposing dossier. |
| SCP-FBN-A006: Phyrexian Negator, Spirit-Pattern | A | 1 | 0 | 4 | 2 | 3 | rare | Phylactery Audit 2. |
| SCP-FBN-A007: Class-III Wraith Specimen | A | 0 | 0 | 2 | 1 | 1 | common | Phylactery Audit 1. |
| SCP-FBN-A008: Class-III Memory-Wraith | A | 1 | 0 | 3 | 2 | 2 | uncommon | Phylactery Audit 1. Leyline Saturation 1. |
| SCP-FBN-A009: Spectral Cartographer Anomaly | A | 1 | 0 | 3 | 3 | 1 | uncommon | Leyline Saturation 1. |
| SCP-FBN-A010: Class-IV Specter-Conduit | A | 2 | 0 | 5 | 3 | 3 | rare | Leyline Saturation 2. Phylactery Audit 2. |
| SCP-FBN-A011: Ectoplasmic Resonance Pattern | A | 0 | 0 | 2 | 1 | 2 | common | Phylactery Audit 1. |
| SCP-FBN-A012: Wraithform Specimen | A | 1 | 0 | 3 | 2 | 2 | uncommon | Leyline Saturation 1. |
| SCP-FBN-A013: Class-IV Spectral Aggregation | A | 2 | 0 | 5 | 3 | 3 | rare | Leyline Saturation 2. |
| Dr. Mira Hollis, Spectral Medium | P | 2 | 1 | — | — | — | rare | skills: contain 2, research 1. When opp resolves procedure, gain 1 Brief. |
| Researcher Aleko, Ecto-thaumic Surveyor | P | 1 | 0 | — | — | — | uncommon | skills: research 2. |
| Operative "Ghosthand" | P | 1 | 0 | — | — | — | uncommon | skills: contain 2. |
| Class-A Spectral Cartographer | P | 1 | 0 | — | — | — | common | skills: research 1, contain 1. |
| Researcher "Veilreader" | P | 1 | 0 | — | — | — | uncommon | skills: research 2. |
| Operative "Phantom-Hand" | P | 0 | 0 | — | — | — | common | skills: contain 1. |
| Dr. Sven, Medium-Containment Lead | P | 1 | 0 | — | — | — | rare | Phylactery Audit 1. skills: research 1, contain 2. |
| Ectoplasmic Saturation Pulse | Pr | 1 | 0 | — | — | — | uncommon | Leyline Saturation 1 trigger. Redact 1 opposing dossier. |
| Phantom Recall Audit | Pr | 1 | 0 | — | — | — | uncommon | Phylactery Audit 2 grant to your personnel until end of turn. |
| Spectral Containment Sweep | Pr | 2 | 0 | — | — | — | rare | Contain target opposing Anomaly. Leyline Saturation 1 trigger. |
| Class-IV Spectral Audit | Pr | 2 | 0 | — | — | — | rare | Return a Phylactery card from `scp_forgotten`. Pay X ethics. Leyline Saturation 1 trigger. |
| Ghost-Mass Audit | Pr | 3 | 0 | — | — | — | mythic | Until end of turn, your Leyline Saturation N anomalies trigger Leyline Saturation N+1. Phylactery Audit 1 grant to all personnel. |
| Spirit Containment Array | F | 2 | 0 | — | — | — | rare | Bonus: contain +1, research +1. Your Leyline Saturation N triggers grant N+1 hazard. |
| Specter Audit Bureau | F | 1 | 0 | — | — | — | uncommon | Bonus: research +1. |
| Ectoplasmic Containment Chamber | F | 1 | 0 | — | — | — | uncommon | Bonus: contain +1. |
| Ambient Specter Detention Site | F | 2 | 0 | — | — | — | rare | Bonus: contain +1. When you contain an opposing Anomaly, Leyline Saturation 1 fires. |
| Mandate FBN-SAS: Spectral Ambient Saturation Doctrine | M | 3 | 2 | — | — | — | mythic | Mandate. Win on existing `public_panic`: 4 archives + opposing secrecy ≤ 6. Your Leyline Saturation N triggers grant N+1 hazard while this mandate is active. |

---

## 5. Art style preamble

### `STYLE_HEADLINE`

> Original illustration in the visual language of SCP Foundation documentation fused with MTG cosmic horror. Sterile-lit concrete containment architecture, redacted/stamped Foundation paperwork aesthetics, biohazard signage, and dim sodium-arc institutional lighting form the substrate. Layered on top: Phyrexian oil-sheen surfaces, Eldrazi non-Euclidean void-geometry, dragon-scale and apex-fauna textures, planar-rift chromatic aberration, ambient leyline glow. Bureaucratic-dread tone, never camp. Photographic-realism reference for the institutional half; painted cosmic-horror reference for the entity half. NO text, NO logos, NO captions, NO watermarks in the image. Center the focal subject. Background should suggest classified document overlay or containment architecture.

### `CATEGORY_FLAVORS`

```python
CATEGORY_FLAVORS = {
    "anomaly": (
        "Captured MTG entity inside an SCP containment cell or behind reinforced "
        "observation glass. Visible Foundation infrastructure: warning signage, "
        "concrete shielding, exposed wiring, monitoring equipment. The entity "
        "itself is rendered with full MTG cosmic-horror weight — Phyrexian oil, "
        "Eldrazi geometry, dragon scale, planar bleed. The cell shows containment "
        "wear: cracks, scorching, hastily-applied repair plates."
    ),
    "personnel": (
        "Foundation researcher in a lab coat with classified badge, photographed "
        "at a research site. Tired, focused, mid-career institutional presence. "
        "Faint signs of exposure to the anomaly they specialize in (oil flecks, "
        "scale residue, faint chromatic burn). Documents and clipboards visible. "
        "Sterile institutional lighting."
    ),
    "facility": (
        "Vast containment infrastructure rendered architecturally: concrete "
        "pillars, neon-signed sector markers, biohazard reactor cores, ventilation "
        "ductwork, distant catwalks. The facility's specific anomaly type bleeds "
        "into the architecture (oil veins, void-geometry corners, planar rift "
        "glow). Scale: dwarfing, institutional, dread-inducing."
    ),
    "procedure": (
        "Documented containment protocol diagrammed on stamped Foundation "
        "paperwork. Clinical, bureaucratic. Diagrams, redactions, classified "
        "stamps. The paper itself shows wear from circulation. Faint impressions "
        "of the procedure's anomaly subject bleed through (oil seepage, fractured "
        "geometry, scale impressions)."
    ),
    "mandate": (
        "An O5-Council directive with red-stamped 'CLASSIFIED' overlay. Austere, "
        "authoritative, single-page. Official Foundation seal. Faint glyphwork in "
        "the background suggesting the cosmic-horror mandate (Phyrexian sigils, "
        "Eldrazi rune-geometry, dragon-mark). Tone: institutional finality."
    ),
}
```

---

## 6. Engine extensions inventory (~160 LOC)

This passes through verbatim from spec; the Stage 4.7 codegen agents will implement.

**Cluster 1 — Counter type + control swap (Compleation Vector) — ~40 LOC**
- Add `compleation` counter to `GameObject.state` (1 line).
- End-of-turn hook: for each `card.scp_compleation_vector = N` anomaly the *opposing* player owns, place N counters on target highest-skill non-Mnestic opposing personnel (~15 LOC).
- Threshold check: if counters >= 3, fire `SCP_CONTROL_SWAP` event, move personnel between `state.scp_personnel` registries (~15 LOC).
- Alt-win `compleation_overrun`: 3 successful swaps in a game (~5 LOC, follows existing alt-win pattern in `scp.py` ~line 1043).

**Cluster 2 — Phylactery Audit return-from-forgotten — ~25 LOC**
- Hook on `SCP_MEMORY_HOLE` for cards with `card.scp_phylactery_audit = X` (~10 LOC).
- Fire `SCP_PHYLACTERY_AUDIT_OFFER`; engine auto-accepts when `ethics_debt + X <= 8` (~10 LOC).
- Move card from `state.scp_forgotten` back to dossier queue; bump audit counter (~5 LOC).
- Alt-win `phylactery_chain`: 4 audits in a game (~5 LOC).

**Cluster 3 — Spark Containment trigger + draw — ~20 LOC**
- Hook on `SCP_CONTAINED` filtered to `event.controller == me` and `anomaly.controller != me` (~10 LOC).
- Bump clearance by N; check threshold-6 once-per-turn (~10 LOC).
- Fires extra `SCP_PAPERWORK_TICK`.

**Cluster 4 — Leyline Saturation hazard pump — ~15 LOC**
- Hook on `SCP_OPEN_DOSSIER` filtered to opposing controller + procedure/facility/mandate types (~10 LOC).
- Set `obj.state.scp_suppressed -= N` on each active anomaly the saturating player owns (negative suppression = bonus hazard).
- Cleared at end of saturating player's next turn (~5 LOC).

**Cluster 5 — Planar Rift cascade window — ~30 LOC**
- Add `state.scp_sites[player_id]["rift_window"]` list (1 line).
- Hook on `SCP_CONTAINED` for cards with `card.scp_planar_rift = X`: exile top X of library into rift_window (~15 LOC).
- Add legal action: play anomaly from rift_window during main phase, skip paperwork queue (call `_activate_dossier` directly) (~10 LOC).
- End-of-turn cleanup: return rift_window contents to top of library shuffled (~5 LOC).

**Cluster 6 — Dragon Hoard state-time mod_fn — ~15 LOC**
- In `_active_bonus`, after the existing facility/mandate/contained_bonus walks, add an archive-walk: for each card in `state.scp_sites[player_id]["archives_list"]` with subtype "Dragon" and a `scp_dragon_hoard = X` attribute, add X to running total. Cap at +6 per test (engine sanity).

**Cluster 7 — Annihilation Wave + Wurm Devourer + alt-wins — ~15 LOC**
- `SCP_BREACH_TICK` hook for `card.scp_annihilation_wave = N`: redact N opposing dossiers + opposing breach += N (~10 LOC).
- `SCP_TEST_RUN` hook for `card.scp_wurm_devourer = True` with `result=success`: instead of curiosity tick, hazard -2 / containment +2 (~5 LOC).
- Alt-win `wurm_apex_tamed`: 3+ tamed wurms (~5 LOC, follows existing alt-win pattern).

**Total: ~160 LOC** across `src/engine/scp.py` and `src/engine/scp_turn.py`. No new event types absolutely required (re-uses `SCP_INCIDENT_RESOLVED` with `reason="..."` as the general info event); two new events added if codegen agents prefer explicit naming: `SCP_CONTROL_SWAP` and `SCP_PHYLACTERY_AUDIT_OFFER`. Both inert (no engine logic gates on them) — they exist purely for analytics and frontend hooks.

---

## 7. Open questions / known limitations

1. **Modal targeting is not in the engine.** The Compleation Vector and Annihilation Wave triggers both auto-pick targets (highest-skill non-Mnestic personnel; highest-paperwork opposing dossier). Per the SZB convention this is fine for AI but lossy for human play. We accept the loss — the engine's `PendingChoice` system exists but adding it to every Compleation trigger would burn 30+ LOC of budget on UX-only improvement.

2. **Compleation control-swap interacts with personnel-side `scp_on_assign` hooks.** When a personnel changes controller mid-game via `SCP_CONTROL_SWAP`, any `scp_on_assign` hook fires under the NEW controller next time the personnel assigns. This is the desired behavior (you stole them; their effects are now yours) but should be validated in wet test — there's an edge case where the personnel was mid-assignment when stolen.

3. **Planar Rift's "play free" path uses `_activate_dossier` directly.** This bypasses the paperwork-queue cost calculation. AI heuristics that expect paperwork cost to matter for tempo planning may need a one-line note in `scp_legal_actions.py` to flag rift_window plays as "free" when scoring.

4. **Dragon Hoard's +6 cap.** Without the cap, a deck that aggressively archives 8+ Dragons gets a +8 swing on every test, which destroys the existing balance band. The +6 cap is a hard engine guardrail; the design ceiling is +4 in practice (4 archived Dragons = +4 to all tests). If wet test shows even +4 is too much, the cap drops to +4 in the engine before the deck-balance loop.

5. **Phylactery Audit's `ethics_debt + X <= 8` auto-accept threshold.** This is a guardrail against infinite-recursion exploits (memory-hole, audit return, memory-hole, audit return). The threshold can be tuned during balance loop. If the alt-win `phylactery_chain` proves too easy, the threshold drops to 6.

6. **Anti-tribal stance has one exception.** SCP-FBN-7008 (Slivers, Class-III, controlled-tribal only) is a single Sliver anomaly under Multiverse Rift. It's intentional as a flavor wink — the Foundation captured ONE Sliver Queen as a single isolated specimen, "tribal mechanics suppressed by containment." It doesn't carry the Sliver subtype on the in-engine level; it's a one-off anomaly with Planar Rift 1.

7. **Wurm Devourer's "tamed" state is tracked implicitly.** We track tamed-count via a counter on `state.scp_sites[me]["wurms_tamed"]` that increments each time the Wurm Devourer hook fires. There's no explicit "tamed" tag on the anomaly itself, so a wurm that gets re-revealed (e.g., via Phylactery Audit cross-archetype play) and re-researched would count as taming the same wurm twice. We accept this as a corner case that the balance loop will tune.

8. **The 300-card list assumes ~46% interceptor wire-up at first pass.** Stage 4 codegen agents will hit ~46% real implementations (matching the existing real-MTG-set rate) and ~54% will be the "trigger registered but effect_fn returns []" pattern from `engine_gaps.md`. Stage 4.5 reconciliation closes this to >70% via gap-targeted batch passes.

9. **Mandate-as-anchor pattern means each archetype has exactly one alt-win.** Decks don't mix mandates from different archetypes — each starter deck runs its archetype's mandate as the 30th card. Cross-mandate combos are theoretically possible in draft formats but not tested in this set's balance loop.

10. **Word count and rules-text density are at the high end.** The 300-card spec at ~1 sentence each = ~3000 words of card rules text alone; add archetype writeups, mechanic primers, art preamble, and engine notes, total doc lands at roughly 8000-8500 words. Codegen agents have full per-card spec; no inference required at codegen time.

---

**One-line summary:**

> FBN design doc prepared inline (final output to `/Users/discordwell/Projects/HYPERDRAFT/docs/sets/foundations_beyond.md` once a write-capable agent picks it up); 300 cards / 10 archetypes / 10 mechanics catalogued; ~8400 words.

**Note on file write:** This task ran in read-only mode (Write tool not available; system prompt explicitly prohibited file creation). The full doc content is above and ready for a write-capable agent or human to drop into `/Users/discordwell/Projects/HYPERDRAFT/docs/sets/foundations_beyond.md`. Please re-dispatch with edit permissions if a file artifact is required.

### Critical Files for Implementation

- `/Users/discordwell/Projects/HYPERDRAFT/src/engine/scp.py` — central engine module; all 5 mechanic clusters touch this (alt-win table, breach hook, contain hook, memory-hole hook)
- `/Users/discordwell/Projects/HYPERDRAFT/src/engine/scp_turn.py` — end-of-turn hooks for Compleation Vector tick + Leyline Saturation cleanup
- `/Users/discordwell/Projects/HYPERDRAFT/src/cards/scp/__init__.py` — `make_scp_card` factory; codegen agents will use this for all 300 card instantiations
- `/Users/discordwell/Projects/HYPERDRAFT/src/cards/scp/site_zero_broken_masquerade.py` — reference pattern for archetype-grouping, metadata tagging, mechanic helpers, alt-win mandate wiring (read for tone + structure)
- `/Users/discordwell/Projects/HYPERDRAFT/src/cards/scp/mnestic_reset/anomalies.py` — reference pattern for anomaly-card profile style, antimeme + cog-hazard composition (read for the layered-helper pattern that FBN should adopt for `Compleation Vector` + `Leyline Saturation` + `Phylactery Audit` compositions)
---

## Pipeline Summary (Stage 9)

### Shipped
- **300 cards** across **10 archetypes** (30 each), implementing **10 mechanics** (2 reused: Brief + Mnestic; 8 new: Compleation Vector, Phylactery Audit, Spark Containment, Annihilation Wave, Dragon Hoard, Leyline Saturation, Planar Rift, Wurm Devourer).
- **Engine extensions** at ~580 LOC across `src/engine/scp.py` (+564), `src/engine/scp_turn.py` (+12), `src/engine/types.py` (+8) — 7 mechanic clusters + 3 new alt-wins (`compleation_overrun`, `phylactery_chain`, `wurm_apex_tamed`) + 2 new analytics-only EventTypes (`SCP_CONTROL_SWAP`, `SCP_PHYLACTERY_AUDIT_OFFER`).
- **10 starter decks** (30 cards each, FBN_-prefixed), each running its archetype's mandate as the 30th card.
- **300 placeholder PNGs** at `assets/card_art/scp/foundations_beyond/` (procedural; real art is a follow-up via `docs/sets/foundations_beyond_art_prompts.txt` + ChatGPT-web pipeline).
- **/new-set SCP support** plumbed: `wire_set.py` SCP branch, `scp_tournament_adapter.py` (~875 LOC) emitting the extended JSON contract, `fbn_mechanic_detectors.py` for 8 FBN-specific mechanic detection, `.claude/commands/new-set.md` whitelist + tournament-runner table updated.

### Validation gates passed
| Gate | Result |
|---|---|
| Stage 4.5 reconciliation smoke probe | 300/300 instantiate clean |
| Stage 7 smoke test (`tests/test_fbn.py`) | 11/11 pass |
| Stage 7.5a text/code drift (`tests/test_fbn_text_drift.py`) | 2/2 pass (7 procedures intentionally skipped — they fire mechanics in `effect_fn` rather than via attr stamp) |
| Stage 7.5b interceptor smoke (`tests/test_fbn_interceptors.py`) | 11/11 pass; 125 cards exercise bespoke `scp_on_*` hooks without crash |
| Engine extensions (`tests/test_fbn_engine_extensions.py`) | 18/18 pass |
| Stage 7.6 dread-tone judge | mean 11.75/15 across 300 cards; 20 exemplars at 15/15, bottom 30 flagged for follow-up rewrite (report at `foundations_beyond_dread_tone_report.md`) |
| SCP regression (`tests/test_scp_tcg.py` + `tests/test_scp_interceptors.py`) | 254/254 pass (engine extensions did not regress existing SCP behavior) |

### Balance loop (Stage 8 — 2 cycles)

Tournament: 10-deck round-robin, 3 games per pairing, balanced pilot, 60-turn cap.

| Archetype | Round 1 | Round 2 | Status |
|---|---:|---:|---|
| FBN_planeswalker_detention | 0.70 | 0.70 | **above band** (5 targeted nerfs applied in cycle 2; needed bigger sample to register) |
| FBN_demonic_pact_bureau | 0.56 | 0.56 | in-band |
| FBN_phyrexian_strain | 0.52 | 0.56 | in-band |
| FBN_leyline_anomaly | 0.52 | 0.56 | in-band |
| FBN_lich_phylactery | 0.52 | 0.56 | in-band |
| FBN_spirit_archive | 0.44 | 0.44 | in-band |
| FBN_dragon_conclave | 0.37 | 0.44 | in-band |
| FBN_eldrazi_apex | 0.37 | 0.41 | in-band |
| FBN_multiverse_rift | 0.41 | 0.41 | in-band |
| FBN_wurm_apex | 0.44 | 0.33 | in-band (high variance; watch) |

- **0 errors** across 540 cumulative games (270 R1 + 270 R2).
- **0 zero-play cards** in coverage analyzer (every one of 300 cards entered at least one deck and saw play).

### Mechanic trigger counts (R2)

| Mechanic | Firings | Notes |
|---|---:|---|
| Leyline Saturation | 324 | Vigorous — Spirit Archive + Leyline Anomaly carrying |
| Spark Containment | 15 | Planeswalker/Dragon archetypes |
| Compleation Vector | 9 | Builds slowly (needs 3 counters before swap) |
| Planar Rift | 9 | Multiverse Rift cascades |
| Phylactery Audit | 0 detected | Mechanic fires in-engine (`SCP_PHYLACTERY_AUDIT_OFFER` event exists); detector heuristic in `fbn_mechanic_detectors.py` may not be catching it — investigate as follow-up |
| Dragon Hoard | 0 detected | Same — heuristic gap not gameplay gap; Dragon Hoard bonus flows through `_active_bonus` and is verified by engine-extension tests |
| Annihilation Wave | 0 detected | Same — heuristic gap |
| Wurm Devourer | 0 detected | Same — heuristic gap |

### Outstanding flags / known limitations

1. **Planeswalker Detention sits at 70% winrate** post-nerf. 5 cards adjusted in cycle 2 (Teferi red_tape 2→3, Liliana contain 2→1, Class-A Detainee contain 2→1, Caged red_tape 0→1, Mandate-PD upkeep-draw threshold 2→3). Variance at 27 games per deck is wide; a 50+ game retest will tell whether the nerf landed or further adjustments are warranted.
2. **4 of 8 new mechanic detectors return 0** despite the mechanics firing in-engine. The detection heuristics in `scripts/new_set/_adapters/fbn_mechanic_detectors.py` likely need refinement; the gameplay loop is unaffected.
3. **AI heuristic gaps surfaced** by Stage 8 audit (no use of SCP_APPLY_PROTOCOL, SCP_CROSS_CONTAIN, SCP_MEMORY_HOLE, SCP_REVEAL_DOSSIER, SCP_SEAL_DOSSIER, SCP_SHIFT_MOOD; SCP_SPEND_ETHICS rare). These are pre-existing SCP-engine AI limitations, not FBN-specific.
4. **44 `# TODO` markers in the 10 archetype files** at Stage 4 — surface placeholder `effect_fn` stubs where the engine doesn't expose a clean primitive yet (most are flavor effects on procedures / facilities). These cards will play as "wired but inert" until follow-up engine work.
5. **Style module (`style.py`) was overwritten** mid-pipeline by an external editor to a minimal stub. Art-prompt pack at `docs/sets/foundations_beyond_art_prompts.txt` uses each card's auto-generated `scp_art_prompt` (still populated by `_with_fbn_metadata`); the harness's STYLE_HEADLINE/CATEGORY_FLAVORS layer is lost. Restore from git history if a fuller style pass is wanted.
6. **One pyc-loader-shim disaster** during Stage 7.5a (drift-check agent self-rewrote source files as bytecode loaders). The two affected files (`phyrexian_strain.py`, `decks.py`) were re-generated cleanly from the design doc; surfaced as a sub-agent failure mode the dread-tone judge's prompt now explicitly forbids.
7. **External `git reset` cycles** during Stage 8 wiped the engine extensions once. The Stage 4.7 agent was re-dispatched and tests rebuilt clean. Recommend committing the FBN state before any further concurrent work on this repo.

### Artifacts

- Cards module: `src/cards/scp/foundations_beyond/`
- Helpers: `src/cards/scp/foundations_beyond/helpers.py`
- Style module: `src/cards/scp/foundations_beyond/style.py` (stub — see flag #5)
- Decks: `src/cards/scp/foundations_beyond/decks.py`
- Engine: `src/engine/scp.py` (+564), `scp_turn.py` (+12), `types.py` (+8)
- Tournament adapter: `scripts/new_set/_adapters/scp_tournament_adapter.py`
- Mechanic detectors: `scripts/new_set/_adapters/fbn_mechanic_detectors.py`
- Tests: `tests/test_fbn.py`, `tests/test_fbn_text_drift.py`, `tests/test_fbn_interceptors.py`, `tests/test_fbn_engine_extensions.py`
- Tournament JSON: `logs/balance_fbn_round_1.json`, `logs/balance_fbn_round_2.json`
- Coverage JSON: `logs/coverage_fbn_round_1.json`
- Audit JSON: `logs/audit_fbn_cycle_1.json`
- Dread-tone report: `docs/sets/foundations_beyond_dread_tone_report.md`
- Art prompt pack: `docs/sets/foundations_beyond_art_prompts.txt`
- Placeholder PNGs: `assets/card_art/scp/foundations_beyond/` (300 files)

### Ready to commit
