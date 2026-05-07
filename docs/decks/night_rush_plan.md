# night_rush — Plan

## Composition summary

50-card pure aggro list. Counts (4-of unless noted):

- **Workers (8)**: 4 Steve's Helper (1W, mines wood), 4 Alex's Scout (1W,
  haste, mines wood). Both wood-yield Workers — no stone/iron/redstone
  Workers in the deck.
- **Hostiles ≤2-cost (16)**: 4 Zombie (2/2 1W), 4 Spider (2/3 1W+1S
  climb), 4 Skeleton Archer (3/1 1W+1S ranged+reach), 4 Creeper (4/1 2S
  deathrattle: 3 to column).
- **Raider lord (4)**: Pillager Patrol (3/3 1W+2I, "Other Raiders +1 ATK").
- **Token / midrange Hostiles (4)**: 2 Wolf Pack (3/2 1W+1I, +1/Worker —
  scales with the 8 Workers), 2 Creeper Ambush (2S sorcery, summons 4/1
  Creeper token). Effectively 4 more Hostile bodies.
- **Removal (4)**: 2 TNT Blast (1S+1R, 4 to target + destroy if Block),
  2 TNT Trap (2-toughness Block, deathrattle: 4 to opponent avatar).
- **Weapons (4)**: 2 Iron Sword (2I, +4/turn), 2 Bow (2W+1I, +3/turn
  ranged).
- **Utility (8)**: 2 Bed (2W), 2 Chop Trees (free, +2W), 2 Strip Mine
  (1S → 1I+1R), 2 Oak Planks (1W block).
- **Late aggression (2)**: Piglin Raider (3/2 1I+1R, Hostile/Nether/
  Raider — gets +1 from Pillager Patrol).

**Hostile density**: 16 + 4 (Wolf/Ambush) + 2 (Piglin) + 4 (Pillager) =
**26 mobs in 50 cards (52%)**. Twice the typical raider density.

**Cost curve**: 14 cards at 1-cost, 18 cards at 2-cost, 10 cards at
3-cost, 6 cards at higher (Pillager Patrol ×4 at 1W+2I, Piglin ×2 at
1I+1R). The deck is front-loaded by design.

**Deliberate omissions**: no Crafting Table / Furnace / Chest (no
turn-bonus structures) — opponents running `structure_first` attack
priority will fall through to avatar/empty (see strategy doc point 3).
No Bow's-cousin Crossbow, no diamond cards, no bosses. Once the
clock starts, the deck commits.

## Win condition

Flood the board with cheap Hostiles so Pillager Patrol's lord makes
every Raider attack +1 stronger, then close on a Night turn for the +1
Hostile ATK swing. Realistic target: **lethal T10-12** by stacking
Pillager(+1 Patrol)+Creeper(+1 Night)+Skel-Archer (ranged, in a 3rd
column to evade single-blocker chumping) for 3-wide swings of ~10-13
face on Night turns. T6-7 lethal is only achievable on a snap-keep
(Worker + Bed + ≤2-cost Hostile + Strip Mine in opener) AND the AI
fails to deploy any blocker for the first 4 play-turns. Iter-1 vs
`passive_econ` showed the AI accumulates blockers (even bad
chumps) which slows kill turns by 4-6 turns vs the optimistic plan.

## Target turns

- **T1**: Mine Forest with day bonus (+2W). Play Steve's Helper or
  Alex's Scout (1W). If Bed in hand, save the W; play Bed T2 instead.
  Worker-less openings are extremely rare in this deck (8/50 = 16% of
  the deck, expected ~1.6 Workers in opening hand of 7 + 4 turn draws
  by T2 = high probability of seeing 2+).
- **T2**: **Strip Mine first if you have stone** (1S → 1I+1R unlocks
  Piglin Raider and TNT Trap). Worker mines Forest or Cave. Avatar
  mines Cave (1S+1I day-bonused = 2S+1I) for the rest of the early
  game. Only cast Creeper Ambush on T2 if Strip Mine is not in hand
  AND a Worker isn't queued behind a 2-cost stone spend — Creeper
  Ambush is a 4/1 token that trades 1-for-1 with any 2/2 chump and
  doesn't unlock other cards in hand.
- **T3**: First attack happens here. Zombie or Spider into the avatar
  column. Workers + avatar mine — stone+iron production lets a Skel
  Archer (1W+1S) drop alongside.
- **T4**: Pillager Patrol on curve (1W+2I — needs the iron from T2-3).
  Now every Raider attack is +1. Two attackers = ~6 face damage.
- **T5-T6**: Add Creeper (2S, prefer Night turn for +1 ATK = 5 dmg).
  First sustained 2-3 wide attacks land here — typical first damage
  swing window is **T6-8**, scoring ~6-9 face per turn. Opp 20 → ~10.
- **T8-T10**: 3-wide attack columns reach lethal range. Skel Archer
  in a separate column from Pillager+Creeper (multi-column-attack
  exploit — see strategy doc weakness #5) guarantees 1-2 unblocked
  hits per turn even when AI has a single blocker. Aim for face
  damage to outpace the AI's threat curve by ≥2 turns.
- **T10-T12**: **Lethal swing target**, ideally on a Night turn for
  the +1 Hostile ATK. Pillager(4) + Creeper(5) + Skel-Archer(4 ranged)
  on Night = 13 face — kills any Bed-less avatar near or below 10 HP.
- **T12+ backstop**: If still short, equip Iron Sword (2I — Bed is
  ideally down by now, so no suicide-equip problem). Avatar swings
  for +4. Or TNT Blast for 4 direct damage to face/Bed.

**Realistic expected lethal turn: T10-12** vs `passive_econ`. T6-7
is only reachable on a snap-keep opener (Worker + Bed + ≤2-cost
Hostile + Strip Mine) AND a non-blocking opponent. Anything past T13
means the deck whiffed on threats or the AI established a Wall stack
the deck can't break.

## Key cards

- **Pillager Patrol** — the centerpiece. +1 ATK to every other Raider
  (Pillager, Piglin Raider — note **Spider/Zombie/Skel/Creeper are
  NOT Raiders**, only Pillager and Piglin share the subtype). So the
  lord effect is narrow: 4 Pillager Patrols + 2 Piglin Raiders = 6
  Raider-eligible attackers. Critically, when **two Pillagers** are out,
  each buffs the other for +1 — a 4/3 Pillager lineup. Stack them.
  **The lord effect also fires when only Pillager is on board** —
  the body itself is a 3/3 attacker that absorbs a chump-block AND
  deals overkill face. Pillager is the deck's per-card EV champion
  even without partners.
- **Creeper** — 4/1 for 2S, +1 ATK at Night = 5 dmg. The deathrattle
  (3 to column when it dies) is also relevant: even if it trades, it
  hits a follow-up target. This is the deck's per-card EV champion
  before the lord shows up.
- **Wolf Pack** — 3/2 base, +1/Worker. With 8 Workers in the deck and
  ~3 down by T4, that's a 6/2. Strong tempo at 1W+1I.
  **Bed-killer (iter-2 finding)**: Wolf Pack with even 1 Worker on
  board lands at 4 ATK regardless of day/night — exactly Bed's 4 HP
  for a clean one-shot. Allocate Wolf Pack to a Bed column when
  initiating a multi-Bed breakthrough; the re-resolution rule means
  the next attacker behind it hits the avatar.
- **TNT Trap** — Block on the avatar's column. Deathrattle: 4 to
  opponent avatar. Doubly useful: the AI's `passive_econ` chump-blocks
  with Workers, so when AI attacks our TNT Trap and kills it, we eat
  a chump-trade AND deal 4 face. **Best use is letting it die to AI
  attacks**, so deploy it on a column the AI is likely to target.
- **TNT Blast** — 4 to a target. Two copies in deck. Save for: (a) AI's
  Bed (instant lethal vector if AI is bed-less), (b) a Wall protecting
  the Bed, (c) finishing 4 damage on the avatar when 4 short of lethal.
- **Bed** — mandatory. 2 copies; expect to see one by T3. T1-2 priority
  if affordable.
- **Iron Sword / Bow** — backup damage source. **Don't equip before
  Bed is down.** Iron Sword preferred (4 vs Bow's 3) and the deck
  generates plenty of iron via Strip Mine + Cave. Bow is fine if
  no iron available.

## Mulligan policy

- **Auto-mull**: Hands with zero Workers AND zero ≤2-cost mobs. The
  deck has 24 sub-Workers / cheap-mobs in 50 cards (48%) so this is
  rare; if it happens, ship it — the curve is broken without an early
  body.
- **Auto-keep (snap)**: Worker + Bed + ≤2-cost Hostile. This is the
  ideal opener. ~28% odds in any 7-card draw.
- **Auto-keep (good)**: 2× Worker, OR Worker + 2× ≤2-cost Hostile.
  The deck wants to deploy something every turn — this delivers.
- **Salvage keep (Worker-less)**: Bed + Chop Trees + ≤2-cost Hostile is
  salvageable per the strategy doc — the Hostile applies pressure
  while the velocity finds Workers.
- **Avoid keeping**: hands heavy on Pillager Patrol / Wolf Pack / Iron
  Sword without 1-drops. The mid-cost cards are dead before T4.

## Play priorities (order)

1. **Bed if not yet down AND wood available** (turn 1-2 only — by T3+
   the AI's clock makes it less time-sensitive than tempo).
2. **First Worker if 0-2 Workers on board** — compounding mine yield
   carries every subsequent turn.
3. **Cheap Hostile for tempo** — Zombie / Spider / Skel Archer / Creeper.
   Aim to have a board attacker by T2-3.
4. **Pillager Patrol on curve T4** if 1W+2I available. Plays as a 3/3
   without a partner; with a Piglin or another Pillager it scales.
5. **Mine Forest day-bonus T1, then Cave (S+I) the rest of the early
   game**. The deck lives on iron (Pillager 2I, Iron Sword 2I, Strip
   Mine effectively converts S→I).
6. **Strip Mine before any 2-cost stone spend** (Creeper, Creeper
   Ambush, etc.) on T1-T2. Strip Mine is the only cheap path to
   redstone, which unlocks Piglin Raider (1I+1R) and TNT Trap (2-cost
   block w/ deathrattle). Casting Creeper Ambush T2 instead of Strip
   Mine costs you the 1R and may brick Piglin/TNT Trap for the entire
   game (iter-1 lesson). **Hard rule**: T1-T2 Strip Mine > T1-T2
   Creeper Ambush whenever both are affordable. Cast Strip Mine on
   every subsequent available turn until Pillager and Iron Sword are
   both in hand or played — 1S → 1I+1R is unbeatable EV.
7. **TNT Trap on a "they will attack here" column** to bait a chump
   trade + deal 4 face. Don't deploy it on an empty column the AI is
   ignoring.
8. **Avatar attacks with weapon** only after Bed is down AND there's
   no day-bonus mine to take. Equip turn should be a turn the avatar
   wasn't going to mine anyway.
9. **TNT Blast** held for the kill turn — 4 to face is the
   tightest-EV finisher in the deck. **Or aim it at a Bed** if AI is
   Bed-protected and you can't muster a 4 ATK attacker per Bed column.

10. **Bed-killer attack ordering (vs Bed-protected opponent).** A Bed
    is not consumed by the avatar respawn (engine fact — see strategy
    doc). If the AI has 1+ Beds on the grid, ANY pure-face damage you
    deal beyond clearing each Bed is wasted on the respawn cycle. Plan
    your lethal swing to:
    - Allocate one 4+ ATK attacker per AI Bed (Skel Archer Night = 4,
      Wolf Pack with ≥1 Worker = 4, Creeper Night = 5, Pillager Night
      = 4, Pillager+lord Night = 5).
    - Place that attacker in the Bed's column; combat re-resolves the
      attack target per attacker, so once the Bed dies, the next
      attacker in that column hits the avatar.
    - Add the rest of your face attackers in any column.
    - Same combat step. Respawn re-checks `has_bed` only AFTER all
      damage resolves, so kill-the-Beds + lethal-face must land
      together. **A multi-turn drip plan does not work** against a
      Bed: each turn the AI respawns to 20.

11. **T8 Night swing rule (iter-2 lesson).** A Night attack turn vs a
    Bed-protected AI is the most common over-extension trap. If you
    have 4-5 attackers ready on T8 and the AI has 1+ Beds, do NOT
    just spread for max face — you'll deal 16+ to a 14 HP AI and
    the AI will respawn at 20 next combat. Instead, commit at least
    one Bed-killer per Bed column; deal whatever face damage the
    remainder allows. Save the lethal swing for the turn the AI is
    Bed-less.

## Anticipated weaknesses

- **No flexible answer to a wall-stack**. The deck has Spider (climb,
  ignores walls) and Skel Archer (ranged, no counter-damage) but
  both are 2-toughness — a chump-trade kills them. Against a Cobblestone
  Wall + Worker chump-block the deck has TNT Blast (×2) as the only
  hard answer.
- **No removal for big mobs**. TNT Blast deals 4; Warden (7/8), Iron
  Golem (3/4), Wither (4/4) all survive a single Blast. If the AI
  curves into a 3I+1R Iron Golem before we close, we're in trouble.
- **No card velocity beyond Chop Trees and library size**. With 50
  cards, the deck's draw curve is decent, but if the opening hand is
  bad the only recovery is Chop Trees (×2) — and that gives wood, not
  cards. A truly stuck hand can't dig out.
- **No diamond plan**. If the game goes to T10+ the deck is out of
  threats; opponent's late game wins.
- **Worker-of-the-wrong-color problem**. All 8 Workers mine wood. By
  T4 we have wood overflowing but stone/iron is rate-limited to (a)
  avatar mining a stone biome and (b) Strip Mine. Pillager Patrol
  (1W+2I) and Iron Sword (2I) demand iron we have to actively chase.
- **Heuristic AI counter**: `passive_econ` happily chump-blocks
  attacks, so each of our 2-toughness Hostiles trades with a
  1-toughness Worker. Net: we kill a Worker (good), they neutralize
  one of our attackers (bad). The deck's threat density is supposed
  to outpace this — verify in iter-1.

- **Piglin Raider is redstone-dependent.** Piglin Raider costs 1I+1R,
  and the deck's only redstone source is 2× Strip Mine. If neither
  Strip Mine is drawn, Piglin sits dead in hand the entire game (iter-1
  confirmed). **Hard rule**: count Strip Mine as the redstone-or-bust
  enabler. If no Strip Mine by T4, treat Piglin Raider as a brick and
  cycle aggressively (Chop Trees, library size) to find more options.

- **Pillager Patrol mirror**: when both decks have Pillager out, the
  lord effects cancel (each only buffs OWN Raiders). The mirror
  creates inefficient trades unless you stack 2× Pillager on your
  side first. Don't lead with Pillager into Pillager — try to deploy
  your second Raider first so your Pillager fires on EtB with a buff
  target ready.

- **Bed drought**: 2 copies in 50 cards = ~14% chance to see Bed in
  the opening hand of 7. With turn draws, ~50% chance by T5. **If no
  Bed by T5, accept the all-in plan** — don't equip Iron Sword/Bow
  under any circumstances, just race. Iter-1 and iter-2 both played
  this line and won at 18 / 17 HP respectively, so the all-in is
  viable when the AI is `passive_econ` (which doesn't apply early
  avatar pressure). **Iter-2 vindicated**: even with the AI deploying
  2 Beds, the Bed-drought all-in still hit its T10-12 target.

- **Multi-Bed scenario** (NEW after iter-2). `passive_econ`'s patched
  `bed_search_bonus=40` means the AI may deploy a 2nd Bed proactively
  when threatened (observed: 2nd Bed at HP 16 on T9). Combined with
  the engine's "Bed not consumed by respawn" fact, that's two
  structures you must clear before lethal can land. Plan answers:
  (a) Hold TNT Blast x2 for the lethal turn — 4 dmg per blast = one
      Bed each, then face attackers swing for face.
  (b) Lead each Bed column with a 4+ ATK attacker (Wolf Pack with
      Worker, Skel Archer Night, Pillager Night, Creeper Night) so
      re-resolution chains a face hit into the cleared column.
  (c) Don't waste a lethal Night swing on stand-alone face when 1+
      Beds are up — the AI respawns to 20 and you've burned a turn.
  See Play priorities #10-11 for the combat order rule.

## Iteration log

(Append after each game piloted with this deck.)

- **2026-05-06**: raider/passive_econ — **W in 12 turns** (final HP
  ME=18 AI=0). Plan predicted T6-7 lethal; actual T12 was 5 turns
  slow. Bed never drawn (whiff on 2/50 copies). Piglin Raider sat
  dead all game because the second Strip Mine never came in (1
  copy seen, used T4). Won via the predicted Pillager+Creeper+Skel
  Archer Night swing on T12 — 13 face into 6 HP. Key lessons:
  (a) Strip Mine T2 > Creeper Ambush T2 (the 4/1 token traded for
  net 0 face vs AI Zombie); (b) Multi-column attacks (Pillager
  col 0, Creeper col 1, Skel Archer col 2) structurally beat AI's
  `chump_anything` block mode → guaranteed 2 unblocked hits per
  turn from T8 onward; (c) `passive_econ` accumulates Workers
  reflexively (dropped 2nd Steve at 6 HP, never deployed a Block
  despite 9-10 stone unspent for 3 turns) — so the all-in race
  line is forgiving when no Bed shows. Plan revised: realistic
  lethal target T10-12 (was T6-7); added T2 Strip-Mine rule;
  flagged Piglin Raider as redstone-dependent brick.

- **2026-05-06 (iter-2)**: raider/passive_econ — **W in 12 turns**
  (final HP ME=17 AI=0). Same kill turn as iter-1, different
  bottleneck. T2 Strip-Mine rule (the iter-1 refinement) paid off:
  Piglin Raider deployed T10 instead of bricking. Iter-1's
  anticipated weaknesses were vindicated — Bed drought all-in
  plan worked even with the AI defending more aggressively.
  Two new findings dominated:
  (1) **Bed not consumed by respawn (engine fact).** T8 Night swing
  dealt 16 damage into a 16 HP AI expecting lethal — AI respawned at
  20 with the Bed still in play. Wasted a swing turn. Strategy doc
  and play priorities #10-11 now codify the Bed-killer attack
  ordering: 1 attacker per Bed column FIRST, then face. T10 fix
  worked: Wolf Pack 4 ATK one-shot Bed col 0, Creeper 4 ATK
  one-shot Bed col 1, remaining 8 face landed. Both Beds dead +
  AI HP 12. T12 lethal then landed into a Bed-less AI for 25
  face (6-mob Night swing).
  (2) **AI deployed 2 Beds.** `bed_search_bonus=40` (iter-1 patch)
  + AI drew both Bed copies → 2 Beds on grid by T9. New behavior
  pattern. Added "Multi-Bed scenario" to Anticipated weaknesses
  with three answers (TNT Blast tutoring, Bed-killer columns,
  don't-waste-lethal rule).
  Engine bug fixed: `declare_attackers(auto_block=True)` was
  bypassing the AI handler's `choose_blockers` — so the iter-1
  "chump_anything exploit" was actually exploiting smart-blocker's
  threat-score sort, not the bias preset. Patch routes
  `auto_block=True` through `game.turn_manager.minecraft_ai_handler`
  first, mirroring `_run_pending_block_prompt`. Pinned by
  `test_minecraft_declare_attackers_auto_block_consults_ai_handler`.
  Bias preset unchanged this iter — `bed_search_bonus=40` left at 40
  per the deferred-decision principle (next iter's data decides).
