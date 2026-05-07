# miner — Plan

## Composition summary

50-card ramp deck. Card-type inventory: 5 Workers (Panda Forager, Steve's Helper,
Alex's Scout, Villager Mason, Allay Courier — 10 copies), 4 Bosses/Finishers (Shulker
Sentry, Elder Guardian, Warden, Ender Dragon — 8 copies), 8 Structures (Bed, Crafting
Table, Furnace, Chest, Enchanting Table, Nether Portal, End Portal Frame, Beacon — 16
copies), 4 Tools (Wooden/Iron/Diamond Pickaxe, Diamond Armor — 8 copies), 4 Actions
(Chop Trees, Strip Mine, Find Diamonds, Explore Map — 8 copies). Notable ratio: 10 Worker
copies (20%) — comparable to builder density — but all Workers are 2/3 or smaller;
sustained mining rather than combat bodies. Structure count (16 copies, 32%) is heavy —
the economy engine is wider than builder's. Full card-by-card inventory below.

### Full card inventory (50 cards)

### Structures (economy engine)
- 2x Bed (W2, /4) — mandatory respawn protection
- 2x Crafting Table (W1, /3) — +1 Wood/turn
- 2x Furnace (S2, /5) — +1 Iron/turn
- 2x Chest (W2, /3) — draw 1/turn
- 2x Enchanting Table (S2+D1, /5) — +1 Diamond/turn + weapon enchant on play
- 2x Nether Portal (S3+R2, /6) — +1 Redstone/turn
- 2x End Portal Frame (S3+D2, /7) — +1 Diamond/turn
- 2x Beacon (I2+R1+D2, /7) — +1 Iron +1 Redstone/turn + Worker buff

### Workers (mining tribe)
- 2x Steve's Helper (W1, 1/2) — mining yields +1 Wood
- 2x Alex's Scout (W1, 2/1, Haste) — mining yields +1 (can act turn played)
- 2x Villager Mason (W1+S1, 1/3) — mining yields +1 Stone
- 2x Allay Courier (R1, 1/2) — mining yields +1 Redstone
- 2x Panda Forager (W2, 2/3) — mining yields +1 Wood

### Bosses / Finishers
- 2x Shulker Sentry (R2+D1, 3/5) — on block: summon 0/2 Shulker Bullet
- 2x Elder Guardian (S2+I1, 4/6) — Boss; when any Worker mines, all Workers gain +1 mining
- 2x Warden (I4+R2+D1, 7/8) — on play: deal 4 dmg to ALL enemy mobs
- 2x Ender Dragon (I1+D2, 6/6, Aerial) — on play: deal 2 dmg to opponent per other creature you control

### Tools
- 2x Wooden Pickaxe (W1) — avatar mines +1 Stone
- 2x Iron Pickaxe (W1+I2) — avatar mines +1 Iron
- 2x Diamond Pickaxe (W1+D2) — avatar mines +1 Diamond
- 2x Diamond Armor (I1+D3) — avatar takes 4 less damage

### Actions
- 2x Chop Trees (free) — gain 2 Wood
- 2x Strip Mine (S1) — gain 1 Iron + 1 Redstone
- 2x Find Diamonds (I2) — gain 1 Diamond
- 2x Explore Map (W1) — upgrade a biome

---

## Win condition

**Mining acceleration into late-game bosses.** The miner deck is NOT an aggro deck — it is a ramp deck. The plan:

1. **T1-3**: Establish Workers (Steve's Helper, Alex's Scout) + Bed. Mine Cave for stone+iron.
2. **T3-6**: Deploy Furnace (iron/turn), Strip Mine (iron+redstone ramp), Crafting Table (wood/turn). Begin structure economy.
3. **T6-10**: Elder Guardian unlocks (S2+I1) — when ANY Worker mines, ALL Workers get +1 mining yield. With 3 Workers + Elder Guardian, a single mining step generates massive multi-material hauls.
4. **T10-15**: Warden (I4+R2+D1) or Ender Dragon (I1+D2) as finishers. Ender Dragon scales with creature count — deploy other mobs first, then Dragon for maximum ETB damage.
5. **Target kill turn**: ~T15-20 (slower than builder/raider, but more resilient).

## Target turns

- **T1-3**: Establish Workers (Steve's Helper, Alex's Scout) + Bed. Mine Cave for
  stone+iron. If Chop Trees in hand, play T1 for free 2W to afford Bed + Worker same turn.
- **T3-6**: Deploy Furnace (iron/turn), Crafting Table (wood/turn), Strip Mine
  (S1 → I1+R1 ramp). Begin structure economy. Two structures + 2 Workers is the
  stable base required before Elder Guardian can be afforded.
- **T6-10**: Elder Guardian (S2+I1) — the deck's payoff. With 3+ Workers on board,
  every mining step cascades across the whole team.
- **T10-15**: Warden (I4+R2+D1) or Ender Dragon (I1+D2) as finishers. Deploy other
  mobs before Ender Dragon for maximum ETB damage (2×creature count).
- **Expected lethal turn**: ~T15-20 vs builder. Slower than builder's own clock,
  but the finisher package (Warden ETB board wipe + Dragon aerial ETB burst) is
  harder to survive once resolved. Miner does not have a clean clock — if Elder
  Guardian goes unanswered and Warden/Dragon resolve, the game ends; otherwise the
  miner risks losing to builder aggression in T6-12 before the ramp pays off.

## Key cards

- **Elder Guardian** (4/6, S2+I1): THE payoff of the Worker tribe. Once online with 3 Workers, each mining action cascades across the whole team. Priority deploy after establishing 2+ Workers.
- **Warden** (7/8, I4+R2+D1): Board wipe on entry, then a 7/8 threat. Clears builder's mob stacks.
- **Ender Dragon** (6/6, I1+D2, Aerial): ETB deals 2×N damage where N = other creatures you control. With 4 Workers on board, that's 8 face damage on entry. Aerial means it ignores blocks.
- **Strip Mine** (S1): Critical ramp spell. S1 → 1I+1R. Converts excess stone into iron and redstone, enabling the upper curve.
- **Diamond Pickaxe** (W1+D2): Avatar mines +1 Diamond per turn — massive late-game acceleration when diamond biomes are available.
- **Beacon** (I2+R1+D2): Ultimate structure — +1 Iron +1 Redstone per turn, PLUS Workers get enhanced mining. Cap at 1 if resources are tight.

## Mulligan policy

**Keep if**: Hand has ANY Worker (Steve's Helper, Alex's Scout, Villager Mason, Panda Forager) AND a Bed.
**Snap keep**: Worker + Bed + Chop Trees/Explore Map.
**Auto-mulligan**: 5 expensive boss cards with no Workers (can't mine into them fast enough).
**If Worker-less**: Keep if you have Chop Trees + Bed + at least one cheap action (Explore Map, Strip Mine). Otherwise mulligan.

## Play priorities (order)

1. **Bed if in hand** (T1-2). Miner's late game requires surviving long enough for
   Elder Guardian to matter — a Bed-less death by T8 means the ramp never paid off.
2. **First Worker** (Steve's Helper or Alex's Scout preferred over Panda Forager
   — cheaper, untaps sooner). Workers are the entire mining engine.
3. **Chop Trees** (free, T1 if available) — use to front-load wood and afford
   both Bed + Worker on T1 without burning a Cave mine turn.
4. **Strip Mine** (S1 → I1+R1) as soon as 1 stone is available. Stone-to-iron
   conversion is the gating resource for Furnace and Elder Guardian.
5. **Crafting Table / Furnace** — structure economy. Priority: Furnace once iron
   generation begins; Crafting Table any turn wood is plentiful.
6. **Second Worker** — don't stop at one. Elder Guardian needs 2+ Workers mining
   simultaneously for the cascade to be meaningful.
7. **Elder Guardian** once S2+I1 is accumulated. This is the inflection point of
   the entire plan; don't delay for a better board state that never comes.
8. **Explore Map** (whenever a biome is still upgradable) — permanent +1 yield per
   Worker mine action; highest EV in the late-mining phase.
9. **Warden** before Ender Dragon — Warden's board wipe clears the builder's
   Worker army, then Dragon's ETB damage counts your surviving creatures. Deploy
   in that order for maximum burst.
10. **Do NOT mine with Workers if they are needed to block this turn.** The miner
    deck can be pressed hard in T4-8; maintain ≥1 blocker to avoid lethal before
    Elder Guardian resolves.

## Opening line

- T1 (Day): Mine Forest (2W with day bonus). Play Chop Trees (free, +2W = 5W total). Play Bed (W2). Play Steve's Helper (W1). 2W remaining.
- T2 (Day): Worker mines Cave (+1S+1I day-bonus = 2S+1I). Avatar mines Hills (+1S = 3S). Play Crafting Table (W1). Play Villager Mason (W1+S1).
- T3: Strip Mine (S1 → 1I+1R). Mine Cave again. Begin iron accumulation.
- T4-5: Furnace (S2 → +1I/turn). Upgrade Cave biome via Explore Map.
- T6-8: Elder Guardian (S2+I1). All Workers mine +1 more each step.
- T10+: Warden or Ender Dragon.

## Anticipated weaknesses

- **Miner's T2 is structurally weak.** The auto-startup (Forest mine → Panda
  Forager W2) consumes avatar action + all wood on T0/T1. By T2, miner has 1
  Worker with summoning sickness, 0 materials, and nothing to do. Builder by
  contrast has 2 Workers untapped on T2. Builder wins the early economy race
  by ~2 turns; miner must not fall behind further or Elder Guardian never
  resolves in time.

- **Warden is the deck's strongest card AND its biggest coordination requirement.**
  Warden's ETB (4 damage to all enemy mobs) is devastating against a builder
  Worker board — but costs I4+R2+D1, realistically T12+. Timing Warden to land
  when the builder has ≤4-toughness mobs deployed is the kill move. If Warden
  arrives while the builder has an Iron Golem (3/4) anchoring its board, the
  wipe is blunted; if Warden resolves into an empty or 3/4+ board, the ETB does
  little. The miner must maintain pressure to prevent the builder from deploying
  Iron Golem before Warden lands.

- **Elder Guardian unanswered by T12 = miner win; answered = miner loses.**
  The entire ramp engine depends on Elder Guardian being alive on the field while
  Workers mine. Builder has no direct removal in the standard build — but a
  builder that races to lethal (T10-12) before Elder Guardian resolves starves
  the miner of its payoff entirely. Miner's biggest weakness: getting killed
  before the cascade starts.

- **No flexible removal against early aggro.** Miner has Warden (board wipe) but
  it costs too much to play early. Against a builder that deploys Village Guard
  (2/3) or Iron Golem (3/4) as early attackers T5-7, the miner has no cheap
  answer except blocking with Workers — which taps them and halts mining.

- **Opening hand without Bed + Worker is an auto-mulligan.** Hands with 5
  expensive boss cards (Elder Guardian, Warden, Ender Dragon, Enchanting Table,
  Beacon) and no Workers cannot mine into them fast enough. The miner also
  cannot afford to skip Bed as liberally as a raider deck — the late-game plan
  requires time to execute.

- **Panda Forager-before-Bed opening is high variance.** Deploying Panda Forager
  (W2) T0 without Bed leaves the miner Bed-less into T2 with 0 materials. Valid
  if hand contains Chop Trees + Panda Forager + Bed (play Forager T0, Bed T2),
  but risky without the Bed follow-up. If the builder applies lethal pressure
  T2-4, the miner has no respawn protection.

## Differences from builder

- Miner has NO Wolf Pack (no ATK scaling mob)
- Miner has NO Iron Golem (no I1+R1 3/4 mid-game threat)
- Miner's economy is deeper but slower to come online
- Miner's finishers (Warden, Ender Dragon) are more powerful but cost more
- Miner win relies on Elder Guardian multiplier, not structure stacking

## Iteration log

- 2026-05-07 (iter 1 / P2b): builder vs miner — STALL (two-pilot coordination
  failure). Pilot B reached T0 with Panda Forager deployed (auto-startup); T2
  was a mandatory pass (0 materials, SS on Forager, avatar action consumed).
  Pilot A stalled at T3 Night and never resumed. No combat, no HP damage, no
  winner. Key findings: (1) miner T2 is a dead turn after Panda Forager
  auto-deployment — plan accordingly; (2) Panda Forager-before-Bed opening is
  valid with Chop Trees + Bed in hand for T2 follow-up; (3) two-pilot harness
  needs turn acknowledgment signals — stall is an infrastructure bug, not a
  strategic observation.

## Hypothesis (to be refined by coach)

The miner deck likely wins against builder in the ~T20-25 range if Elder Guardian goes unanswered. The Warden's board wipe on entry can clear builder's mob army. The Ender Dragon's ETB damage scales with miner's Worker density. Against a passive_econ-style builder, the miner should be able to outlast the builder's 7-turn kill window and then alpha strike with Dragon+Warden.

The biggest risk: getting beaten before Elder Guardian resolves. Miner has weaker early board presence than builder.
