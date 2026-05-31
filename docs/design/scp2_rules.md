# SCP — SECURE / CONTAIN / SUBVERT (rules spec v0.1)

> Working title. The engine code namespace is `scp2`. Final user-facing name is open (see
> §11). This is the **Phase-0 sign-off artifact** for the asymmetric SCP rebuild — approve or
> redline this before any engine code is written. Plan: `~/.claude/plans/cosmic-dancing-pearl.md`.

A two-player **asymmetric** card game in the SCP universe, modeled on Netrunner. One player is
the **Foundation** (build & contain — owns the primary win/lose condition); the other is the
**Chaos Insurgency** (infiltrate & subvert — wins through conflict). SCP stays dossier-coded per
the brand doc; the Insurgency gets a redacted/black-file visual treatment.

The design exists to fix a verified flaw in the current SCP engine: it is two games of solitaire
racing in parallel (the only loss conditions are self-inflicted; the dominant win is the opponent
breaching *himself* out). This rebuild makes the two players actually fight.

---

## 1. The two seats

| | **Foundation** ("the builder") | **Chaos Insurgency** ("the disruptor") |
|---|---|---|
| Fantasy | Secure, Contain, Protect | Steal, Free, Weaponize |
| Plays | builds a board of hidden, defended sites; advances anomalies into containment | builds a "rig" of operatives & tools; infiltrates the Foundation's sites |
| Owns | the **primary win & lose con** | nothing self-destructs; everything is earned by acting on the Foundation |
| Wins by | **Containment** points ≥ 6 (primary); burning out the Insurgency (soft kill, secondary) | **Liberation** points ≥ 7 (primary); **Total Breach** ≥ 14 (secondary) |

Each side's win is the other's loss. There is no self-inflicted loss — the old engine's core sin.

---

## 2. Shared core (economy & turn)

- **Actions (AP):** 4 per turn. Spent on the verbs in §4–5. (Netrunner "clicks"; Phase-4
  tuned 3→4 — the Foundation's plan is action-heavy and was starved at 3.)
- **Credits:** Foundation pool = **Funding**; Insurgency pool = **Cells**. Start at 5. A *gain*
  action grants **+2**. Cards cost credits to play; runs/advances/rezzes cost credits.
- **Hand / deck / discard:** per-faction deck. **Hand is hidden** from the opponent. Start of turn:
  draw 1. Max hand size 5 (discard down at end of turn).
- **Turn order:** players alternate full turns. Foundation goes first.
- **Deck size:** 40. **Anomaly-density rule (Foundation):** a legal Foundation deck must contain
  **≥ 18 Containment points** of anomalies (Netrunner's agenda-density rule — guarantees the
  Foundation actually draws win-con pieces; without it the Foundation can brick).

All numbers here are **initial values to tune in Phase 4** (§10).

---

## 3. The board

### Foundation side
- **Containment Cells** (remote servers): the Foundation builds numbered cells. Each cell =
  an optional **Anomaly** at the root (face-down) + a stack of **0–3 Containment Layers**
  (face-down) guarding it.
- **Central access points** (always present, can be layered): **HQ** (hand), **Research** (deck),
  **Archives** (discard). These give the Insurgency targets even when no anomaly is exposed —
  the espionage/sabotage surface.

### Insurgency side
- **Rig:** installed **Operatives** (breakers) + **Tools** (resource/utility). Persistent.
- **Banks:** Liberation points; the shared **Total Breach** counter.

### Hidden information (fog of war)
The Insurgency sees: that a cell exists, how many layers guard it, and the **advancement "heat"**
on its anomaly (token count is **public** — this is the telegraph). It does **not** see the
identity of any face-down card (anomaly stat line, trap-or-real, layer type/strength) until it is
**accessed** (anomaly) or **rezzed** (layer). This enables Foundation bluffs (§6). Enforced by a
viewer-aware serializer that redacts face-down identities for the non-owner (precedent:
`_serialize_cats_state`, session.py:2560).

---

## 4. Foundation mechanics

**Card types:** `ANOMALY` (the agenda), `LAYER` (the ICE), `ASSET` (installed econ/utility),
`OPERATION` (one-shot), optional `IDENTITY`.

**Anomalies (agendas).** Two numbers: **Threshold** (advancement to lock) / **Value** (points when
locked). Containment classes map to stat lines:

| Class | Threshold / Value | Flavor role |
|---|---|---|
| Safe | 3 / 1 | cheap, fast points |
| Euclid | 4 / 2 | the workhorse |
| Keter | 5 / 3 | big, slow, dangerous if freed |

- Installed **face-down** into a cell (1 AP + credit cost).
- **Advance** (1 AP + 1 Funding): place 1 advancement token. Token count is public.
- **Contain/Lock** (1 AP) when tokens ≥ Threshold: move to *Contained*, score **Value** points.
- If the Insurgency accesses it **before** it locks → they **free** it (§5): they bank Value as
  **Liberation**, it adds to **Total Breach**, and it's gone from the Foundation.

**Traps (decoys).** Face-down cards that *look* like anomalies (advanceable, same fog) but punish
on access (damage / trace / trash). The bluff engine.

**Containment Layers (ICE).** A **type** (one of three) + a **strength** (1–6) + a **rez cost**.
Installed face-down in front of a cell or central. On encounter (§5) the Foundation may **rez** it
(pay rez cost from Funding) to make its subroutine live; if it can't/won't pay, the layer is passed.

| Layer type | Flavor | Subroutine (on encounter, if unbroken) |
|---|---|---|
| **Barrier** | "Blast Door" | End the infiltration. |
| **Sentry** | "Response Team" | Neutralize 1 operative (or deal 1 damage). |
| **Sensor** | "Surveillance Grid" | Trace: if unbroken, **expose** the Insurgency (tag). |

**Foundation actions (3 AP):** play a card · **Advance** · **Secure Funding (+2)** · draw · activate
an asset ability · **Contain** a ready anomaly.

**Soft kill path.** "Expose" (tag) lets Foundation assets/operations punish the Insurgency
(trash a tool, drain Cells). **Damage** discards Insurgency cards at random; if damage would
discard from an **empty** hand, the Insurgency is **burned out** → **Foundation wins** (Netrunner
flatline). This is the secondary, aggressive Foundation win — real teeth, but harder than racing
containment.

---

## 5. Chaos Insurgency mechanics

**Card types:** `OPERATIVE` (breaker / body), `TOOL` (installed hardware/resource), `EVENT`
(one-shot), optional `IDENTITY`.

**Operatives (breakers).** Each breaks **one layer type**, with a **power** and a **boost** cost.
Streamlined break math: a layer is broken if `breaker power ≥ layer strength`; pay **boost** (Cells)
to temporarily raise power for the encounter.

| Operative | Breaks | Base power / boost |
|---|---|---|
| **Infiltrator** | Barrier | 2 / +1 power per 1 Cell |
| **Saboteur** | Sentry | 2 / +1 per 2 Cells |
| **Ghost** | Sensor | 1 / +1 per 1 Cell |

**Infiltration (run) — the core conflict loop.** Spend 1 AP to infiltrate a target (a cell, or HQ /
Research / Archives):
1. **Approach:** encounter layers outer→inner. For each, Foundation may **rez** (pay) it.
2. **Encounter:** if rezzed, the Insurgency **breaks** it (matching operative, power ≥ strength, pay
   boost) **or** suffers the subroutine (end-run / neutralize / expose). If "end the infiltration"
   resolves, the run stops with no access.
3. **Access** (if the Insurgency survives all layers):
   - **Cell w/ anomaly →** *free* it: bank **Value** as Liberation, add Value to **Total Breach**,
     remove it. If it's a **trap**, suffer the trap instead.
   - **HQ →** reveal a random card from Foundation hand; may trash it (espionage).
   - **Research →** look at top card; may trash it (sabotage / mill).
   - **Archives →** exploit the discard (recursion / intel).

**Insurgency actions (3 AP):** play a card · **Raise Cells (+2)** · draw · **Infiltrate** · activate
a tool ability.

**Risk (glass cannon).** Operatives and hand cards are spent by Sentry/expose punishment. Running
into rezzed defenses you can't break bleeds your rig — reckless infiltration gets you burned out.

---

## 6. The central tension (why this is a game)

The Foundation must **advance in the open** — every advancement token is public — so a cell that's
"heating up" screams *come stop me*. The Insurgency must decide each turn: **strike now** (spend
Cells to crack a defended cell before it locks) or **build the rig** (and risk the anomaly locking).
The Foundation, knowing this, can advance a **trap** to bait an expensive, punishing run — or
under-defend a real anomaly and dare the Insurgency to commit. Hidden installs + public advancement
= bluff, read, and tempo. That triangle is the whole game; everything else is texture.

---

## 7. Win / lose conditions (exhaustive)

| Trigger | Result |
|---|---|
| Foundation Containment points ≥ **6** | **Foundation wins** (primary) |
| Insurgency burned out (damage vs empty hand) | **Foundation wins** (soft kill, secondary) |
| Insurgency Liberation points ≥ **7** | **Insurgency wins** (primary) |
| Total Breach ≥ **14** | **Insurgency wins** (secondary — "unleash") |

No self-inflicted loss exists. Checked after every state-changing action (a single
`check_scp2_win(game)` analogous to `check_scp_victory`, but symmetric across the two win axes).

---

## 8. Card-type taxonomy & example cards

New `CardType.SCP2_*` members (Phase 1). ~10 examples per type below; reuse existing SCP **art and
lore** (`frontend/public/scp-art/`, the FBN/GOI card names) re-skinned onto these roles.

**Foundation — Anomalies** (Threshold/Value · on-lock / on-free):
- *Sentient Lockbox* — Safe 3/1 · on-lock: +2 Funding.
- *Reality Bender* — Euclid 4/2 · while installed: layers on this cell get +1 strength.
- *Worldspine Wurm* — Keter 5/3 · on-free: Total Breach +2 (extra dangerous loose).
- *Memetic Archive* — Euclid 4/2 · on-lock: Insurgency reveals hand.
- *Reliquary of Bad Ideas* (TRAP) — looks advanceable · on-access: deal 2 damage.
- *Cerebral Relay* (TRAP) — on-access: expose the Insurgency + trash 1 tool.

**Foundation — Layers** (type · strength / rez):
- *Blast Door* — Barrier 4/4 · end the infiltration.
- *Reinforced Bulkhead* — Barrier 6/6 · end the infiltration.
- *Response Team* — Sentry 3/3 · neutralize 1 operative.
- *Kill-on-Sight Order* — Sentry 5/5 · deal 2 damage.
- *Surveillance Grid* — Sensor 2/2 · trace → expose.
- *Amnestic Mist* — Sensor 3/4 · Insurgency discards 1 random card.

**Foundation — Assets / Operations:**
- *Containment Budget* (asset) — start of turn: +1 Funding.
- *Mobile Task Force* (asset) — 1 AP: trace the Insurgency.
- *Emergency Lockdown* (operation) — this run, a cell's layers get +2 strength.
- *Redaction Order* (operation) — if Insurgency is exposed: trash one of their tools.

**Insurgency — Operatives** (breaks · power/boost): the three breakers in §5, plus:
- *Skeleton Key* — breaks any one subroutine once (then trashed); expensive.
- *Field Medic* — body: prevents the first neutralize each turn.

**Insurgency — Tools:**
- *Black Budget* — 1 AP: +3 Cells.
- *Mole* (connection) — accessing HQ reveals 2 cards.
- *EMP Charge* (one-shot) — bypass one layer this run.
- *Forged Credentials* — 1 AP: expose (peek) one face-down card without running.

**Insurgency — Events:**
- *Smash & Grab* — infiltrate a cell; if you free an anomaly, +1 Liberation.
- *Sabotage* — infiltrate Research; trash top 3 (mill).
- *Leak to the Press* — Total Breach +2.
- *Extraction* — if you freed an anomaly this turn, draw 2.

**Identities (optional, give archetypes a base):**
- Foundation *Site-19 Command* — +1 max hand; first Advance each turn is free.
- Insurgency *Black Queen Cell* — first run each turn targeting a central costs 0 AP.

---

## 9. Starter decks (sketch; built in Phase 2)

- **Foundation A — "Site-19 Containment"** (glacier/build): dense anomalies (e.g. 4×Safe + 5×Euclid
  + 2×Keter = 20 Containment pts), tall layers, Funding engine. Wins by out-defending the run.
- **Foundation B — "Black-File Bait"** (trap/kill): traps + Sentry walls + expose/trash; pursues the
  soft-kill axis, punishing reckless runs.
- **Insurgency A — "Black Queen Cell"** (criminal/tempo): cheap breakers + econ tools + central
  pressure; steals anomalies efficiently.
- **Insurgency B — "Containment Breach"** (anarch/breach-rush): pushes the **Total Breach** axis
  (Leak to the Press, on-free breach anomalies) for the secondary win.

Two archetypes per side keeps the Phase-4 matrix honest (no single dominant line).

---

## 10. Numbers (Phase-4 tuned)
AP **4** · start credits 5 · gain +2 · draw 1/turn · max hand 5 · deck 40 · anomaly density ≥18 ·
Containment target **6** · Liberation target 7 · Total Breach catastrophe **14** · anomaly lines
3/1, 4/2, 5/3 · layer strength 1–6 · breaker power 1–2 + boost. (Engine constants in
`src/engine/scp2.py`; `BREACH_FREE_MULTIPLIER` left at 1.0.)

**Phase-4 result.** Baseline self-play was a 0%/100% Foundation/Insurgency sweep (breach
arrived in ~8 turns while containment needed ~3-4 locks). A runtime-probe sweep
(`scripts/play/scp2_tournament.py`) showed the imbalance was multi-causal — single levers
barely moved it (removing breach-from-freeing entirely still lost 4%/96% as the Insurgency
pivoted to liberation). The adopted fix is **buff-leaning** (per the buff-before-nerf
principle): AP 3→4, containment target 7→6, breach catastrophe 10→14, *no* nerf to the value
of freeing. Result over 100 games: **51% / 49%**, all four win conditions live (containment
50, total_breach 42, liberation 7, burnout 1), avg ~21 turns, zero stalls. Guarded by
`tests/test_scp2_balance.py`.

**Known follow-up (deck-pinnacle pass, not faction balance):** the Insurgency *Containment
Breach* (breach-rush) deck beats both Foundation decks; *Black Queen Cell* (liberation/tempo)
loses to both — the liberation axis is underpowered (only 7/100 wins). Buff the liberation
path / Black Queen Cell before shipping it as a pinnacle.

---

## 11. Phase-0 decisions (RESOLVED — locked for Phase 1)
1. **Name.** Working **"SCP: SECURE / CONTAIN / SUBVERT"**. Code namespace `scp2`. (Open to a
   rename later; not blocking.)
2. **Coexistence:** ✅ **Build alongside** the existing SCP engine in a new `scp2` namespace; flip
   the default mode once proven; retire old SCP in a follow-up. The existing `scp.py` is untouched.
3. **Economy:** ✅ **Single credit pool per side** (Funding / Cells). No separate advance budget.
4. **Turn structure:** ✅ **Strict alternation, both draw 1** at start of turn. Asymmetry lives in
   the cards/verbs, not the turn shape.
5. **Identities:** ✅ **One Identity per faction in v0.1** (Site-19 Command / Black Queen Cell) —
   base stats + a passive, installed at game setup as the archetype anchor.

---

## 12. Verification (how we'll know each phase is real)
- **Phase 1:** unit tests for every mechanic in §4–7 (`tests/test_scp2.py`), incl. a fog-of-war test
  asserting the Insurgency payload never contains a face-down identity.
- **Phase 2:** `/test-interceptors` per card (the effect gate).
- **Phase 3:** `/card-fire-debug` (the fire gate — the AI must actually use each card in self-play).
- **Phase 4:** `scripts/play/scp2_tournament.py` reports the win/lose-reason split and per-seat
  winrate; tune to the §10 goal.
- **Phase 5:** wet + hard-wet browser tests; fog of war holds against a hostile client.
- `scripts/ci_quick.sh` green (no new failures vs. baseline) before any "tests pass" claim.
