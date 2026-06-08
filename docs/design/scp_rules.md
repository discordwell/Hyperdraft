# SCP — SECURE / CONTAIN / SUBVERT (rules spec v0.1)

> Working title. The engine code namespace is `scp`. Final user-facing name is open (see
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
| Wins by | **Containment** points ≥ 6 (primary); burning out the Insurgency (soft kill, secondary) | **Liberation** points ≥ 7 (primary); **Total Breach** ≥ 24 (secondary); **Foundation collapse** (the Foundation can no longer reach Containment) |

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

**Foundation actions (4 AP):** play a card · **Advance** · **Secure Funding (+2)** · draw · activate
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
   - **HQ →** trash 1 random card from the Foundation's hand (espionage / hand attrition).
   - **Research →** trash the top 2 of the Foundation's deck (sabotage / mill).
   - **Archives →** the Insurgency draws 1 (intel). *(v0.1: centrals never grant Liberation — their
     payoff is tempo/disruption, deliberately no Breach so they don't over-feed the breach-rush axis.
     They give the steal deck a non-cell line to grind when a kill build walls it out.)*

**Insurgency actions (4 AP):** play a card · **Raise Cells (+2)** · draw · **Infiltrate** · activate
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
| Total Breach ≥ **24** | **Insurgency wins** (secondary — "unleash") |
| Foundation can **no longer reach Containment 6** — its current points plus the Value of every anomaly it can still contain (uncontained-and-unfreed, in library/hand/on a cell) fall short | **Insurgency wins** (**collapse** — the Foundation failed its mandate) |

No self-inflicted loss exists. Checked after every state-changing action (a single
`check_scp_win(game)` analogous to `check_scp_victory`, but symmetric across the two win axes).
The **collapse** clause makes the game decisive: when the Insurgency has loosed so many anomalies
that the Foundation's quota is mathematically out of reach (and the Insurgency isn't itself one
damage from a soft-kill — guarded by Insurgency hand ≥ 2), it wins by default rather than the game
spinning to a no-contest. This is *not* a self-inflicted loss: the arbiter recognizes a failed win
condition, exactly as it recognizes a met one.

---

## 8. Card-type taxonomy & example cards

New `CardType.SCP_*` members (Phase 1). ~10 examples per type below; reuse existing SCP **art and
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

**Identities (optional, give archetypes a base).** *As shipped (v0.1) — the sketched bonus actions
were dropped in favour of simpler passives that don't distort the AP economy:*
- Foundation *Site-19 Command* — maximum hand size 6 (a bigger ops room).
- Insurgency *Black Queen Cell* — begin with +2 Cells; each anomaly you free banks **+1 bonus
  Liberation** (the steal-engine identity that makes the liberation axis a real win path).

---

## 9. Starter decks (sketch; built in Phase 2)

- **Foundation A — "Site-19 Containment"** (glacier/build): dense anomalies (e.g. 4×Safe + 5×Euclid
  + 2×Keter = 20 Containment pts), tall layers, Funding engine. Wins by out-defending the run.
- **Foundation B — "Black-File Bait"** (trap/kill): traps + Sentry walls + expose/trash; pursues the
  soft-kill axis, punishing reckless runs.
- **Foundation C — "Reliquary Recontainment"** (grind/control): engine is **Containment Recovery**
  (×4) — re-secure a milled/freed anomaly from the discard straight onto a cell *1 advance from
  locking*, so every lost anomaly comes back near-locked. Hard to mill out or steal from; it
  **hard-counters Black Lodge denial** (~57–62%) and beats breach, but its predator is pure
  steal-tempo (~40% vs Black Queen, which races before the grind comes online — a clean RPS). The
  re-secure must land *near-locked*: re-securing part-way just gets the anomaly re-freed before it
  locks (a liberation-donating treadmill — measured 22% vs 49% near-locked). Identity: Site-19
  Command (its big hand holds the wall + Recovery grind). Recovery is **cost 3** — a premium: at 2
  it's a +5pt auto-include in *every* Foundation deck (homogenizing); 3 keeps the funded build-around
  a pinnacle while making a casual splash a real *choice* (+3pt situational tech vs mill/steal,
  a dead-ish cantrip otherwise), so it's freely splashable without becoming mandatory.
- **Insurgency A — "Black Queen Cell"** (criminal/tempo): cheap breakers + econ tools + central
  pressure; steals anomalies efficiently.
- **Insurgency B — "Containment Breach"** (anarch/breach-rush): pushes the **Total Breach** axis
  (Leak to the Press, on-free breach anomalies) for the secondary win. Identity: Sarkic Cult.
- **Insurgency C — "Black Lodge"** (denial/mill): doesn't race liberation or breach — it *destroys
  the Foundation's containment supply* (heavy Sabotage/Data Heist mill + freeing) until the
  Foundation can no longer reach Containment 6 and loses by **collapse**. Identity: Black Lodge Cell
  (every mill trashes +1). This is the archetype that turns the collapse clause into a primary plan.

Three Foundation × three Insurgency archetypes keep the matrix honest (pooled ~50% Foundation over
540 games, all four win axes live incl. collapse and breach, 0 stalls). Recontainment is the
strongest Foundation deck (~49%) but in-band, with a clean RPS: it beats mill/breach, loses to
steal; steal in turn loses to a fast Sentry-Aggro build (both viable but not shipped as starters).

---

## 10. Numbers (Phase-4 tuned; Total Breach re-tuned in the asymmetry-rebuild pass)
AP **4** · start credits 5 · gain +2 · draw 1/turn · max hand 5 · deck 40 · anomaly density ≥18 ·
Containment target **6** · Liberation target 7 · Total Breach catastrophe **24** · anomaly lines
3/1, 4/2, 5/3 · layer strength 1–6 · breaker power 1–2 + boost. (Engine constants in
`src/engine/scp.py`; `BREACH_FREE_MULTIPLIER` left at 1.0.)

**Phase-4 result.** Baseline self-play was a 0%/100% Foundation/Insurgency sweep (breach
arrived in ~8 turns while containment needed ~3-4 locks). A runtime-probe sweep
(`scripts/play/scp_tournament.py`) showed the imbalance was multi-causal — single levers
barely moved it (removing breach-from-freeing entirely still lost 4%/96% as the Insurgency
pivoted to liberation). The adopted fix is **buff-leaning** (per the buff-before-nerf
principle): AP 3→4, containment target 7→6, breach catastrophe 10→14, *no* nerf to the value
of freeing. Result over 100 games: **51% / 49%**, all four win conditions live (containment
50, total_breach 42, liberation 7, burnout 1), avg ~21 turns, zero stalls. Guarded by
`tests/test_scp_balance.py`.

**Liberation-axis buff (done).** The liberation axis was underpowered (7/100 wins) — the
*Black Queen Cell* steal/tempo deck couldn't close on its own axis. Fixed by making the
**Black Queen Cell identity** a steal-engine — each freed anomaly banks **+1 bonus
Liberation** (engine `free_bonus_lib`, set by the identity passive at setup) — and rebuilding
the deck into a focused steal pinnacle (deep breaker suite + econ + Sabotage mill, plus a
3-card breach *reach* package so a kill deck that walls it out can't grind to a stall). Over
120 games: 49%/51% faction split, **liberation now 34 wins** (containment 59, breach 27), 0
stalls; Black Queen Cell is competitive vs the build deck (≈47%).

**Asymmetry-rebuild pass (this pass).** Three pillars of the intended asymmetry were dead or on
autopilot in real play and got made live (each gated by a self-play fire-test, not just an effect
test):
- **Central access (HQ/Research/Archives) is live.** HQ trashes a Foundation hand card, Research
  mills 2, Archives draws 1; the InsurgencyAI grinds an undefended central when genuinely *walled*
  (a cell it can't crack), giving the steal deck a non-cell line. Effects deliberately grant no
  Liberation/Breach (so they don't feed breach-rush). `SCP_SABOTAGE` is asserted in the fire gate.
- **The rez/break mini-game is played, not auto-resolved.** The engine keeps greedy *defaults*
  (they back the Phase-1 unit tests), but the AI passes smart policies into `infiltrate`: the
  Foundation rezzes **to stop, not decorate** (only when the runner can't break it, or a Sentry
  would neutralise an operative), and the Insurgency **eats** cheap Sensor/Sentry subroutines to
  conserve Cells (breaking once exposure nears soft-kill range). The fire gate asserts both a
  *broken* and an *eaten* encounter occur. The server supplies the bot Foundation's rez policy on a
  human-Insurgency run; fully-interactive per-layer human rez is deferred (the run still resolves
  synchronously).
- **The soft-kill (burnout) axis has teeth.** New Foundation operation *Enhanced Interrogation*
  (deal damage = the Insurgency's `exposed` count, min 1) lets the *Black-File Bait* deck convert
  stacked tags into a flatline; the FoundationAI fires it on the threat (`exposed ≥ 2`). Burnout is
  a live *minority* win in self-play (it shapes Insurgency hand-management more than it wins games).

**Re-balance.** Once the mechanics went live, breach-rush ran ~72–76% of its matchups. A runtime
probe (`scripts/play/scp_breach_probe.py`) attributed the edge to the breach *threshold*, not the
free→breach double-dip (cutting `BREACH_FREE_MULTIPLIER` 1.0→0.5 only moved it 76→65%, and we kept
the clean 1.0 rule). Raising **Total Breach catastrophe 14→16** restored a ~45–50% / 50–55%
faction split with breach-rush a strong-but-fair ~62%. The *Black Queen Cell* steal deck — soft to
the kill deck's Sentry walls — got a targeted buff (+1 *Veteran Saboteur*, the load-bearing
anti-Sentry breaker; −1 *Ghost*, since smart-break now eats Sensor tags) lifting its worst matchup
from ~24% toward ~35–45%. All four win axes stay live. Guarded by `tests/test_scp_balance.py`
(band 35–65%); variance is ~15% run-to-run, so only ≥~15pt deltas are trusted.

**Foundation collapse — the stall, resolved (follow-up pass).** At the higher breach threshold
~0.4% of games (only the *Black-File Bait* vs *Black Queen Cell* matchup) ran to the turn cap as a
no-contest. A board dump showed why: the **Foundation exhausts its anomaly supply** (all contained
or freed) while still short of 6, and with no anomalies on the board the Insurgency has nothing left
to free — a *mutual-exhaustion drawn position*, not a near-win tiebreaker. So the §7 **collapse**
clause now resolves it decisively: when the Foundation can no longer reach Containment (current
points + remaining containable Value < 6) and the Insurgency isn't one damage from a soft-kill
(hand ≥ 2 guard), the Insurgency wins. A clean before/after over two 400-game batches shows the rule
is surgical — **Foundation winrate unchanged** (47.2/47.2, 42.9/42.9), burnout wins unchanged, the
only delta the former stalls becoming Insurgency wins — and **stalls drop to 0**. It also fixes the
matching human-play hang (a human Foundation that decks out of anomalies would otherwise End-Turn
forever). Engine `check_scp_win` + serializer mirror; covered by the `test_*collapse*` tests.

**Archetype-aligned identities + breach counterplay (improvement pass).** Two flaws surfaced on a
fresh census: (a) both decks of a faction shared one identity, and the breach-rush deck ran *Black
Queen Cell* — whose "+1 Liberation per free" it doesn't want — so the "breach" deck actually won by
**liberation** (the breach axis was hollow: ~15% of wins); (b) the Foundation had **no way to
interact with the Total Breach clock** at all. Fixes: each archetype now runs its own
win-condition-aligned **identity** — glacier→*Site-19 Command* (max hand 6), bait/kill→**Overseer
Council** (`damage_bonus`: +1 to all Foundation damage while the Insurgency is exposed), steal→*Black
Queen Cell*, breach→**Sarkic Cult** (`breach_event_bonus`: every Leak/Wetwork/Anonymous Tip +1).
Sarkic made breach a *real* engine — and explosive (~85% vs Foundation), which exposed flaw (b). New
Foundation operation **Containment Sweep** (−5 Total Breach, clamped at 0) is the answer; the
FoundationAI fires it when the clock nears catastrophe (verified live — 33 plays / 80 games). With a
real breach engine *and* counterplay, the bar rose: **Total Breach catastrophe 16 → 24**, restoring
~50/50 (mean Foundation **52%** over 480 games, all four axes live, 0 stalls) with breach a
live-but-fair ~¼ of wins. Each side now has two identity-distinct archetypes that answer each other.

---

## 11. Phase-0 decisions (RESOLVED — locked for Phase 1)
1. **Name.** Working **"SCP: SECURE / CONTAIN / SUBVERT"**. Code namespace `scp`. (Open to a
   rename later; not blocking.)
2. **Coexistence:** ✅ **Build alongside** the existing SCP engine in a new `scp` namespace; flip
   the default mode once proven; retire old SCP in a follow-up. The existing `scp.py` is untouched.
3. **Economy:** ✅ **Single credit pool per side** (Funding / Cells). No separate advance budget.
4. **Turn structure:** ✅ **Strict alternation, both draw 1** at start of turn. Asymmetry lives in
   the cards/verbs, not the turn shape.
5. **Identities:** ✅ Installed at game setup as the archetype anchor (a passive on the player
   record). v0.1 shipped one per faction; the improvement pass moved to **one identity per
   *archetype*** — Foundation: Site-19 Command (glacier) / Overseer Council (kill); Insurgency:
   Black Queen Cell (steal) / Sarkic Cult (breach) / Black Lodge Cell (denial-mill) — each aligned
   to its deck's win condition. The recontainment archetype reuses Site-19 Command (its big hand
   suits the grind); a dedicated identity is a possible follow-up.

---

## 12. Verification (how we'll know each phase is real)
- **Phase 1:** unit tests for every mechanic in §4–7 (`tests/test_scp.py`), incl. a fog-of-war test
  asserting the Insurgency payload never contains a face-down identity.
- **Phase 2:** `/test-interceptors` per card (the effect gate).
- **Phase 3:** `/card-fire-debug` (the fire gate — the AI must actually use each card in self-play).
- **Phase 4:** `scripts/play/scp_tournament.py` reports the win/lose-reason split and per-seat
  winrate; tune to the §10 goal.
- **Phase 5:** wet + hard-wet browser tests; fog of war holds against a hostile client.
- `scripts/ci_quick.sh` green (no new failures vs. baseline) before any "tests pass" claim.
