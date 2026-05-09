# Minecraft TCG — Strategy Doc

This file is the persistent strategic memory for Minecraft TCG.
A fresh Claude instance piloting the format reads this BEFORE every
game and consults it during play. Update it whenever a game reveals
a non-obvious truth — write down WHAT and WHY, not just WHAT.

The doc is paired with `src/ai/minecraft_adapter.py` (heuristic bias
presets) — when you find a blind spot in the heuristic AI, patch
both: write the lesson here AND tighten the relevant preset.

---

## Format fundamentals (the meta as currently understood)

### Resources

- **5 materials**: wood < stone < iron < redstone < diamond (rough premium order).
- Mining yield per turn is the bottleneck. Compounding mining > raw card power.
- **Day-bonus** (first mine of the day, per player): +1 of the biome's first yield.
  Don't waste it on a low-tier biome unless that biome enables your next play.
- **Day-craft discount** (first STRUCTURE or BLOCK played per Day phase, per
  player): -1W OR -1S off the cost (engine checks wood first, then stone).
  Applies to structures and blocks only — NOT mobs, actions, or tools. Does
  NOT apply on Night turns. Per-player flag `mc_day_craft_discount_used_<pid>`
  fires after first use; second structure on the same Day pays full cost.
  Engine: `_discounted_cost` in `src/engine/minecraft.py:201`. Examples:
  Cursed Bed (W1) → 0 (free), Bed (W2) → W1, Lectern of Whispers (W2) → W1,
  Soul Forge (S2) → S1, Eldritch Altar (W1+S1+I1+R1) → S1+I1+R1,
  Cobblestone Wall (S2) → S1, Sculk Catalyst (S1+R1) → R1. Strategic
  implication: schedule structure deployments to land on Day turns whenever
  possible — a 4-cost structure on Day saves 1 material vs Night.

### Biome upgrades

- Forest 1W → Old Growth Forest 2W → Woodland Mansion 2W + 1R.
- Hills 1S → Stony Peaks 2S+1I → Ancient Mountain 2S + 1D.
- Cave 1S+1I → Deep Cave 1S+1I+1R → Diamond Depths 1S+1I+1D.
- Explore Map costs **1W** — unlimited compounding ramp. If any biome can
  still be upgraded, Explore Map is almost always the highest-EV play.

### Card-type intuitions

- **Workers** (1W cost, mining tribe): compound. First three are always good.
  After 3-4, diminishing returns — start deploying threats.
- **Turn-bonus structures** (Crafting Table 1W, Furnace 2S, Chest 2W,
  Redstone Engine 1S+2R): each is a permanent +1/turn of one material.
  Stack 2-3 to dominate the long game.
- **Blocks** (Oak Planks 1W, Cobblestone Wall 2S, etc.): protect a column
  but cost a card and a turn. Only useful if the avatar is at risk.
- **Tools** (weapons, armor, pickaxes): equipping a weapon lets the avatar
  attack each turn without using a mob. Iron Sword 2I = 4 dmg/turn — strong.
- **Hostiles** (Zombie 2/2 1W, Spider 2/3 1W+1S, Skel Archer 3/1 1W+1S
  ranged+reach, Creeper 4/1 2S w/ deathrattle): the offensive curve.
- **Bosses** (Warden 7/8, Wither 4/4, Iron Golem 3/4, etc.): finishers
  but cost real materials. Don't deploy until their context (counters,
  workers, hostile count) is set up.

### Critical infrastructure: Bed

- **Bed is mandatory.** Without a Bed, lethal damage = instant loss
  (no respawn). With a Bed, dying respawns at 20 HP — only the avatar's
  **gear is discarded; the Bed itself is NOT consumed.** A single Bed
  therefore protects an unbounded number of respawns until the Bed
  structure is destroyed. This is an engine fact (see
  `handle_avatar_deaths` in `src/engine/minecraft.py`), confirmed by
  the iter-2 night_rush pilot and pinned by
  `test_minecraft_bed_persists_across_multiple_respawns`. Multiple Beds
  give no extra "respawn capacity" per se (the respawn re-checks
  `has_bed`, which is true if **any** Bed is on the grid), but they
  multiply the work needed to clear: you must destroy **every** Bed
  AND deal lethal in the same combat step before the respawn check
  re-runs.
- Play Bed turn 1-2 if it's in opening hand. If it's not, **mulligan
  toward it** if rules allow, or prioritize drawing/tutoring it.
- An opponent without a Bed is a loss waiting to happen — apply lethal
  pressure. Track opponent's Bed **count** every turn (not just
  presence). Two Beds = two structures to break before lethal can land.
- Bed-killer attack ordering: when attacking a Bed-protected opponent,
  allocate one 4+ ATK attacker (Skel Archer Night 4, Pillager Night 4,
  Wolf Pack with ≥1 Worker = 4, Creeper Night 5) **per Bed column FIRST**.
  The combat code re-resolves attack target per-attacker, so once attacker
  1 destroys the Bed, attacker 2's column resolves to the avatar instead.
  Don't waste lethal-overkill damage on stand-alone face attacks while
  Beds are up — the AI just respawns and you've burned a swing turn.

---

## Combat heuristics

### Attack column priority

The default heuristic is `bed > avatar > structure > block > other`.
Adjust based on game state:

- **Opponent has no Bed**: ignore everything else, hit the avatar.
- **Opponent's Bed protected by a wall in same column**: TNT Blast the wall
  first (4 dmg + Block destroyed), then attack.
- **Aerial mob (Ghast, Ender Dragon)**: ignores blocks. Always attack
  the column with the highest-value front (Bed > Structure > Avatar).
- **Climb mob (Spider)**: ignores Walls. Attack column with the wall.
- **Ranged mob (Skel Archer, Bow, Crossbow)**: takes no counter-damage,
  so even chump-blocking it just kills the chump. Spam ranged attackers.

### Block decisions

- Block to prevent **lethal** to the avatar (when no Bed).
- Block when the trade is favorable: blocker survives + attacker dies.
- DO NOT chump-block with a Worker. Workers compound — a Worker absorbing
  2 damage is worse than just taking 2 damage. The heuristic AI's
  `passive_econ` violates this; humans should not.
- Block aerial-target columns when Bed is at risk and you have any flier
  with `reach` (Snow Golem, Skel Archer).

### Avatar attacks

- Once a weapon is equipped, the avatar swings every turn for its damage.
  Iron Sword 4, Diamond Sword 6, Bow 3 (ranged), Crossbow 5 (ranged).
- Don't equip a weapon if the avatar is at risk (the avatar costs your
  whole turn's combat output if it dies). Ensure Bed first.
- **Weapons without Workers are a trap.** With one avatar action per
  turn, an avatar that mines cannot also attack. A Bow you can only
  swing every other turn (because the off turn must mine) is averaging
  ~1.5 damage/turn — worse than a 2/2 Zombie that mines for free via a
  Worker partner. Equip only when you have ≥1 Worker handling mining
  duty, or you will burn the equip turn AND the next turn's tempo.
- **Equip-turn ordering**: the turn you play a weapon is a tempo loss
  (the avatar action is consumed by either the equip-mine or the equip-
  swing, never both). Schedule the equip turn for a turn you would not
  have mined anyway — i.e., when your hand is dry and you only need to
  deploy the weapon.
- **avatar_attack hits ONE target only — no overkill propagation.** Each
  avatar_attack resolves against the single frontmost structure in the
  chosen column. Any damage exceeding that structure's remaining HP is
  lost; it does NOT carry through to the next structure behind it. A
  3-deep column (front + mid + back + avatar) requires 4 separate Night
  turns to reach face at 1 hit/Night = 8 game-turns minimum. Plan your
  weapon line accordingly: use mob attackers to clear layers in parallel
  while the avatar attacks a different layer. Never plan for avatar alone
  to chain through a column in fewer turns than the depth allows.
- **Water Bucket Moat blocks mob attacks but NOT avatar weapon attacks.**
  Mob-lane attacks (mob targeting a structure) pass through Moat
  blocking logic; avatar weapon attacks bypass it entirely. If the AI
  has Water Bucket Moats sealing all 3 columns, mob attackers are all
  absorbed — but avatar_attack proceeds unimpeded to the front structure
  in any column. Use the avatar for lane-clearing when Moats are present;
  use mobs for structure-less columns or to chump-block AI attackers.
- **Empty-column avatar_attack routes to opponent face — but "empty" means
  ALL three y-depths (y=0, y=1, y=2).** If ANY slot in the column contains
  a structure at any depth, avatar_attack hits the front-most (highest-y)
  occupied slot. Face damage only occurs when column_target returns None
  across all three rows. This is confirmed in engine code
  (`avatar_attack` line 489: `column_target(...) or opponent`) and verified
  by a live test (empty col 0 → P2 HP 20→19). Pilot display bug in iter-5:
  columns that appeared as "all dots" in the grid display had structures at
  y=0 or y=1 that were not visually prominent — the avatar_attack hit those
  structures (producing real damage to structure HP but no HP readout change
  visible in the log), and the pilot misread this as "zero damage". The
  engine does NOT silently no-op on empty columns. When planning face turns,
  confirm the column is clear at ALL depths before expecting HP damage.

---

## Mulligan rules

A raider opening hand without **both** a Worker (Steve's Helper, Alex's
Scout, etc.) AND a cheap (≤2-cost) deployable (mob, Bed, or block) is a
guaranteed loss in the mirror. Auto-mulligan if rules permit.

- **Auto-mulligan**: 5+ expensive iron/redstone mobs and only free-cost
  utility (e.g., Oak Planks, Chop Trees) — you have no T1 board, no
  ramp, and no answers to a turn-1 4/4. Confirmed loss vector: hand
  with Wolf Pack + Blaze + Enderman + Pillager + Oak Planks lost in 6
  play-turns to a `passive_econ` mirror.
- **Keep**: any hand with at least one Worker OR at least one ≤2-cost
  mob that can block.
- **Snap-keep**: hands containing Bed + Worker + at least one ≤2-cost
  threat. This is the "actual opening" — everything else is salvage.
- **Marginal keep (Worker-less but Bed-positive)**: a hand with **Bed
  + a card-velocity action (Chop Trees / Villager Trade / Eyes of
  Ender) + at least one ≤2-cost deployable** is salvageable even
  without a Worker. Iter-2 confirmed: Bed + Chop Trees + drawing
  Creeper turn 2 was enough to win an 8-turn raider mirror. The Bed
  protects against the AI's weapon+1-mob race curve (preventing
  one-shot lethal), and the velocity action finds Workers later.
  Auto-mulliganing into a worse hand is not worth the EV trade if
  this profile is in your opener.
- If the harness exposes mulligan and you ship a hand: prioritize
  finding **a Worker** over finding a Bed; the deck cannot function
  without Workers because every avatar turn becomes either-mine-or-
  attack and never both.
- **Redstone-bottleneck deck rule**: decks where >50% of removal +
  mid-curve cards require redstone (e.g., box_of_horrors with ~70%
  redstone-gated cards) should treat redstone-source cards (Strip
  Mine, Allay Courier, Sculk Catalyst, or any redstone-mining
  structure) as Bed-equivalent in mulligan rules. Missing a redstone
  source by T6 in such a deck = unrecoverable (every removal/threat
  becomes uncastable). Auto-mulligan any redstone-bottleneck hand
  without a redstone source. Iter-1 box_of_horrors loss confirmed:
  pilot played Strip Mine T1 (only redstone seen all game), then
  bricked T10-T15 with hands that were 100% redstone-gated.

## Strategic patterns

### Opening (turns 1-2)

- T1: Mine Forest (2W with day bonus). Play Steve's Helper (1W) and
  Bed (2W) if both in hand. Otherwise: Worker first, save remaining wood.
- T2: Worker mines (Cave for stone+iron OR Hills for stone). Avatar
  mines whatever the day bonus benefits most. Play Bed if not yet down.
- **Worker-less openings**: if turns 1-2 produce no Worker, prioritize
  card velocity (Chop Trees, Villager Trade, Eyes of Ender) above all
  threats. The deck is non-functional until a Worker hits the table —
  every turn spent on a 3-cost mob without Workers is a turn the avatar
  cannot also attack.

### Mid game (turns 3-6)

- Establish redstone economy: Strip Mine (1S → 1I+1R) is the only cheap
  path to redstone. Run multiple copies.
- Deploy 2-3 turn-bonus structures (Crafting Table, Furnace, Chest).
- Apply chip damage with hostiles. Even 2 dmg/turn from a Zombie wins
  by turn 12 if uncontested.
- **Turn-bonus structure protection rule**: cheap (3-4 HP) turn-bonus
  structures (Soul Forge 4HP, Lectern 3HP, Sculk Catalyst, Eldritch Altar)
  cannot survive a single 4-ATK swing. Do NOT deploy them in unprotected
  columns. Required protection options: (a) deploy with a same-turn
  front-row defender, (b) deploy only in the Bed column (Bed forces the AI
  to attack through the 4HP Bed first), or (c) deploy behind a wall/block.
  A turn-bonus structure that ticks zero times before dying is a card-and-
  mana negative. Confirmed iter-1 box_of_horrors: Soul Forge T5 and Lectern
  T7 both died the turn AI attacked, ticking zero value.

### Late game (turns 7+)

- Diamond is unlocked via Find Diamonds (2I → 1D). Bosses (Warden, Wither,
  Iron Golem) become playable.
- Identify the kill turn: total power on board × turns to live > opponent HP.
- If behind, look for swing cards (TNT Blast, AoE bosses).

### Card-specific notes

- **TNT Blast (1S+1R)**: 4 damage to a target. If target is a Block, ALSO
  destroys it. This is the swing card — kills walls + small mobs in one
  card, or 4 direct damage. Often the highest-EV card in hand by turn 4.
- **Eyes of Ender (1R+1D)**: tutor for an End or Nether mob. Save for
  finding a specific finisher.
- **Bone Meal (1W)**: untaps a Worker, lets it mine again. Only valuable
  if the second mine yields ≥ 1 material (i.e., you have unmined biomes).
- **Strip Mine (1S)**: the redstone-economy enabler. Don't skip it.
- **Chop Trees (free)**: 2 wood from nothing. Always cast turn 1-2.
- **Creeper deathrattle ordering**: "deal 3 to frontmost in attacked column"
  resolves BEFORE other deathrattles' new tokens claim the frontmost slot.
  Concrete: when an Endermite Cluster (1/1, deathrattle: spawn 1/1 Endermite
  token) mutual-kills a Creeper, the Endermite token survives the Creeper
  deathrattle's 3 dmg because the token's "frontmost" status doesn't resolve
  in time. Useful for Endermite Cluster value math.

---

## Engine quirks affecting AI behavior

These are **engine facts**, not AI-bias-preset behavior. A piloted human
whose mental model is "the AI's `block_mode` is always honored" will
make wrong calls until they internalize the routing rules below.

1. **Bed is not consumed by respawn.** See "Critical infrastructure: Bed"
   above. `handle_avatar_deaths` only calls `discard_avatar_gear` on the
   avatar's tool slots; the Bed object on the grid is untouched. Pinned
   by `test_minecraft_bed_persists_across_multiple_respawns`.

2. **`declare_attackers(auto_block=True)` and the AI handler.** Confirmed
   in iter-2 and now patched: the wet-test harness calls
   `declare_attackers(auto_block=True)` for human-attacker turns. Before
   the patch, that path called `mc.auto_blockers` directly, bypassing the
   defending seat's `block_mode` (so iter-1's "exploit" of
   `chump_anything` was actually exploiting the smart blocker's
   threat-score sort, not the chump rule). Post-patch (current code),
   `declare_attackers` first consults
   `game.turn_manager.minecraft_ai_handler.choose_blockers` and falls
   back to `mc.auto_blockers` only when no handler is attached — same
   shape as `_run_pending_block_prompt` in `minecraft_turn.py`. Pinned by
   `test_minecraft_declare_attackers_auto_block_consults_ai_handler`.
   **Implication for the strategy doc**: weaknesses keyed to
   `chump_anything` (e.g. "multi-column attack defeats first-attacker-
   first-blocker pairing") are now the genuine `chump_anything` exploit
   when piloting against `passive_econ`, not just a smart-blocker
   side-effect.

## Strengths of `passive_econ` in mirror matchups

These are things `passive_econ` does **well** — humans should not
underestimate the preset based on its name.

1. **The "passive" name lies in raider mirrors.** `passive_econ` will
   equip a weapon by turn ~5 and become the active aggressor when the
   opponent fails to apply pressure. The "passive" component (chump-
   blocking everything) only activates if the opponent attacks; against
   a stalled human, the AI plays a chip-damage race and usually wins.
   Plan for ≥4 dmg/turn from the AI avatar starting turn 5-6.

2. **Iron-sword race is self-stabilizing.** AI mines stone-heavy biomes
   and reaches a 1W+2I weapon spend on schedule. A human with no
   Workers cannot match this curve, because the AI's Workers handle
   mining while the avatar swings. The preset's worker focus isn't a
   defensive choice — it enables the offensive curve.

3. **`structure_first` collapses to `avatar_first` in raider mirror.**
   Because neither raider deck plays Crafting Tables / Furnaces, there
   are no structures to attack, so the AI's column choice falls through
   to avatar/empty. This means the preset name ("structure-disrupt")
   is misleading: in mirror, the AI is effectively `avatar_first`. Do
   not rely on AI hitting your blocks first as a way to protect the
   avatar — it won't, because there's nothing to disrupt and it goes
   straight for face.

4. **`passive_econ` becomes hyper-passive when Worker-less (v2-only,
   patched in v3).** Iter-2 observed the AI play **zero mobs across 8
   turns** because the v2 patches set `worker_bonus_under_3=80` while
   `early_big_mob_penalty=20` still penalised non-Worker mobs. With no
   Worker drawn, no card cleared the score-zero bar and the AI just
   passed every turn. v3 lowered `early_big_mob_penalty` to 10 in
   `passive_econ` only, so the AI now falls back to deploying a
   non-Worker mob when no Worker is in hand. Caveat for the human
   pilot: in the (rare) v2 build the AI's "defense" is meaningless
   because it has nothing on the board — chump_anything requires
   blockers it never deployed. Just attack every turn and the AI loses
   on chip damage alone. Post-v3 this hole should be closed; if a
   future iter still sees the AI passing with affordable cards in hand,
   the issue is elsewhere (likely a scoring-table interaction, not the
   Worker bonus).

## Known heuristic-AI weaknesses (exploitable when piloting)

These are gaps in the current `_choose_card_to_play` / `_best_attack_column`
/ `choose_blockers` heuristic. A piloted human/LLM should exploit them;
the **coach** loop should patch them in `MC_BIAS_PRESETS`.

1. **No-Bed plays:** AI's `passive_econ` doesn't prioritize Bed strongly enough
   when not in opening hand. If you can win before turn 8, AI often dies
   without a Bed and loses instantly. Both players running a Bed-free game
   for 13 turns is plausible because Bed copies are sparse (~2 per 30-card
   deck) — exploit by tutoring/cycling for Bed yourself, then chip the AI
   to lethal before it ever sees one.

2. **Chump-block with Workers:** `passive_econ`'s `chump_anything` block
   mode doesn't weigh blocker value. Sacrificing a 1W Worker to absorb
   2 damage from a 2W Zombie is a horrible trade. Force the AI into
   these trades by attacking with vanilla 2/2s while keeping your
   Workers on mining duty. NB: this only works if you actually attack —
   in the 13-turn loss above, the human never forced enough chump-trades
   to make the preset's defensive weakness matter.

3. **Single-threat density:** AI deploys ~1 mob per turn. By turn 6 you
   should have 4-5 attackers; the AI usually has 1-2. Apply max threat
   density — even with low-stat mobs, sheer count overwhelms.

4. **No targeted removal:** AI doesn't try to clear a recurring threat
   (e.g., a Skel Archer attacking for 3 every turn). TNT Blast on a
   resilient attacker isn't in the heuristic's vocabulary. Run multiple
   attackers and the AI can't answer them all.

5. **Multi-column attacks beat `chump_anything`.** The AI's
   `chump_anything` block mode pairs each declared attacker with the
   next-available legal blocker in declaration order — it does NOT
   compute the highest-EV block. Spreading 2-3 attackers across separate
   columns guarantees 1-2 unblocked hits even when the AI has a single
   blocker, because the AI commits its only blocker to the first
   declared attacker. Order your declaration so your highest-ATK or
   ranged attacker is in a column the AI's blocker can't reach (e.g.
   put Skel Archer in a third column when AI has one ground blocker).
   This is a structural exploit of `passive_econ`, not a tuning bug —
   the heuristic's vocabulary doesn't include "best block target."

6. **`passive_econ` doesn't proactively deploy non-Bed Blocks.** Even
   sitting on 9-10 stone for 3+ turns, the AI mines more stone instead
   of deploying Cobblestone Wall / Oak Planks. A human running aggro can
   plan around the AI never putting Walls in the way of attackers, even
   on Day turns when the AI is stone-heavy. Force the AI to spend stone
   reactively only — it won't shore up defense proactively, so sustained
   multi-turn pressure can't be answered with a Wall stack.
   **Iter-2 night_rush amendment**: the AI WILL proactively deploy a
   second Bed when threatened (observed: AI played a 2nd Bed at HP 16 on
   T9, driven by `bed_search_bonus=40` plus available wood). So "doesn't
   deploy structures" is too strong — the gap is specifically non-Bed
   Blocks (Cobblestone Wall 2S, Oak Planks 1W). The Bed-search bonus is
   wired; the Wall-deploy heuristic is not.

7. **Day/night blind:** AI doesn't time plays to day/night cycle.
   **Hostile mobs gain +1 ATK at Night** (Zombie text says so explicitly,
   and the bonus also applies to Creeper, Pillager Patrol, and other
   Hostile/Raider creatures). The AI doesn't time deployments around the
   night phase, so the human can stack the swing both ways: deploy a
   Hostile on a Day turn so it's ready for the Night attack; align
   Bed-less lethal turns to land on Night when the +1 ATK across two
   attackers can produce a +2-per-turn swing. **Concrete ceiling**:
   Creeper (4/1, 2S) + Pillager Patrol (3/?, W1+I2, Raider+Hostile) at
   Night = 4+1 + 3+1 = **9 face damage uncontested per turn** — enough
   to kill an unprotected (Bed-less) avatar in a single attack step.

8. **AI equips weapons without a Bed.** AI cheerfully equips Iron Sword
   despite no Bed protection — exactly the suicide line a human is told
   to avoid. Iter-2 confirmed `weapon_no_bed_penalty=18` was undersized
   (Iron Sword base = 15 + mc_attack=4 = 19, net +1 with the penalty,
   still equipped). Penalty has been raised to 28 (net -9 for Iron
   Sword, net -10 for Bow). If the AI's avatar dies in an unequipped
   state, it loses its biggest damage source; force pressure into the
   AI's avatar column when it has equipped without a Bed.

9. **AI places Bed in the most recently cleared front slot, not the safest
   column.** When the AI has no Bed and a front slot (y=2) is empty,
   `bed_search_bonus=40` causes the AI to deploy Bed there immediately —
   regardless of whether that column is contested (recently attacked) or
   safe (protected by Water Bucket Moats). Iter-4 confirmed: pilot cleared
   col 1 y=2 at T32, AI placed Bed in that exact slot at T34. This means
   clearing a front-row structure does NOT open a clean attack lane; within
   1-2 turns the slot contains a Bed (4 HP + respawn protection). Do NOT
   plan "clear front → exploit open lane" — the AI refills with a Bed
   faster than that. The same clearing action that opens the slot gives the
   AI a Bed slot, which can BACKFIRE: you've cleared a wall and handed the
   AI respawn protection. Only clear front structures if you can capitalize
   in the same turn or have enough combined ATK to one-shot through all
   remaining layers before the Bed lands.

---

## Strategy doc changelog

### v1 — 2026-05-06 (initial seed)
- Bootstrapped from one wet-test game (8-turn raider mirror win vs `passive_econ`)
- Documented format fundamentals, combat heuristics, and 5 known AI weaknesses.

### v2 — 2026-05-06 (raider mirror loss vs passive_econ, 13 turns)
- Pilot lost 20→0 in 6 play-turns with a worker-less, 5-expensive-mob
  opening hand. Lessons distilled into:
  - New **Mulligan rules** section: auto-mulligan worker-less hands;
    snap-keep Bed+Worker+cheap-threat; prioritize Worker over Bed when
    salvaging.
  - **Avatar attacks** updated: weapons without Workers are a trap;
    schedule equip-turn for a turn you would not have mined anyway.
  - **Worker-less openings** rule added under "Opening (turns 1-2)":
    prioritize card velocity (Chop Trees / Villager Trade / Eyes of
    Ender) over threats until a Worker hits.
  - New **Strengths of `passive_econ` in mirror matchups** section:
    the preset's `structure_first` priority collapses to `avatar_first`
    in mirrors with no structures, the iron-sword race is self-
    stabilizing because Workers handle mining, and the "passive" name
    is misleading — it's a chip-damage racer when uncontested.
  - Existing **Known heuristic-AI weaknesses** entries 1 and 2
    annotated with concrete failure mode (Bed sparsity ≈ 2/30,
    chump-block exploit only matters if you attack), and a new entry 6
    added: AI equips weapons without a Bed.
- Heuristic AI preset patches: see `MC_BIAS_PRESETS["passive_econ"]` in
  `src/ai/minecraft_adapter.py` — `worker_bonus_under_3` 60→80 to keep
  Workers ranked above 4/4 mobs early; new `weapon_no_bed_penalty=18`
  knob added to `_DEFAULTS` (default 0) and consumed in
  `_choose_card_to_play` to discourage the AI from equipping weapons
  while undefended; new `bed_search_bonus=40` knob added (default 0)
  applied to Eyes of Ender / Villager Trade when the AI has no Bed,
  to compensate for low Bed copy density.

### v3 — 2026-05-06 (raider mirror win vs passive_econ, 8 turns; v2 patch regression caught)

- Pilot won 20→AI=0 in 8 turns (4 play-turns) running raider vs
  raider with the v2-patched `passive_econ`. Net status of the v2
  patches:
  - **What helped (v2 patches that did their job):** the new mulligan
    rules served as a useful reality check during the opening — the
    pilot recognised the Worker-less hand and consciously played the
    salvage line (Bed turn 1 + Chop Trees + day-bonus Cave) instead of
    flailing. The "marginal keep" profile (Bed + velocity + cheap
    deployable) is now documented as a result.
  - **What regressed:** `worker_bonus_under_3` 60→80 and
    `early_big_mob_penalty=20` together turned `passive_econ` hyper-
    passive when no Worker was drawn — the AI played **zero mobs in
    8 turns**, holding its hand instead of falling back to a non-
    Worker threat. The pilot won uncontested by chipping with Creeper
    + Pillager Patrol while the AI mined Cave on repeat.
  - **What was undersized:** `weapon_no_bed_penalty=18` failed to
    suppress Iron Sword (base score 19 → net +1 with the penalty,
    still picked).
  - **New combat finding (un-flagged in v2):** Hostile mobs gain
    **+1 ATK at Night** (Zombie text states this explicitly; the
    bonus also lifts Creeper, Pillager Patrol, and other Hostile/
    Raider creatures). Two ≤2-cost Hostile attackers can deal **9
    face damage uncontested per Night turn** — enough to one-shot
    a Bed-less avatar. Documented under "Day/night blind".
- Strategy doc updates:
  - **Mulligan rules**: added "Marginal keep (Worker-less but Bed-
    positive)" — Bed + velocity action + cheap deployable is salvage-
    able without a Worker.
  - **Strengths of `passive_econ` in mirror matchups**: added entry 4
    on the v2-only hyper-passive failure mode (and noted that v3
    closes the hole).
  - **Known heuristic-AI weaknesses #5 (Day/night blind)**: expanded
    with the +1 Night ATK math and the 9-damage-per-Night-turn
    ceiling for two-Hostile attacks.
  - **Known heuristic-AI weaknesses #6 (weapons without Bed)**: noted
    that the v2 `weapon_no_bed_penalty=18` was undersized vs Iron
    Sword's base score of 19 and that v3 raised it to 28.
- Heuristic AI preset patches (passive_econ only — see
  `MC_BIAS_PRESETS["passive_econ"]` in `src/ai/minecraft_adapter.py`):
  - `weapon_no_bed_penalty` 18 → **28**: Iron Sword (15 + 4 = 19) net
    -9, Bow (15 + 3 = 18) net -10. Both should now lose to virtually
    any other affordable play.
  - `early_big_mob_penalty` 20 → **10** (in `passive_econ` only):
    keeps the +80 Worker bonus dominant when a Worker is in hand,
    while letting the AI fall back to a non-Worker mob (e.g. Zombie,
    Spider, Enderman) when no Worker is available — preventing the
    iter-2 "literally pass every turn" failure mode.
  - Other presets are unchanged.

### v3 addendum — 2026-05-06 (night_rush vs passive_econ, 12-turn W; T6-7 plan was 5 turns optimistic)

- Pilot ran the LLM-designed `night_rush` aggro deck against
  `passive_econ` raider. Won 18→0 in 12 turns (5 play-turns of
  attacks). The deck's plan predicted T6-7 lethal — actual was T12,
  five turns slow. Causes were a mix of deck-construction issues
  (no Bed drawn, no second Strip Mine drawn → Piglin Raider sat
  dead in hand all game) and AI-side heuristic gaps:
  - **AI hoarded materials.** `passive_econ` accumulated 9-10 stone
    over T7-T11 without spending on a Block (Cobblestone Wall 2S /
    Oak Planks 1W). A human running raider can plan around the AI
    never deploying Walls reactively. Documented as new weakness #6.
  - **AI dropped a 2nd Steve's Helper at 6 HP** while facing 4
    attackers on the board. The +80 `worker_bonus_under_3` keeps
    firing while the AI has <3 Workers — but at <3 Workers AND <50%
    HP under sustained pressure, the AI should pivot defensive
    instead of chasing more economy. Cheaper fix: cap Worker
    bonuses at 2 Workers on board so the third Worker doesn't
    out-score a defensive mob / Block.
  - **Multi-column attacks are a structural exploit of
    `chump_anything`.** The AI's block mode pairs attackers with
    blockers in declaration order — it doesn't compute best-EV
    blocks. Three-wide attacks force 2 unblocked hits per turn
    even when the AI has a blocker. Documented as new weakness #5.
- Strategy doc updates:
  - **Known heuristic-AI weaknesses #5 (NEW)**: multi-column attacks
    structurally beat `chump_anything`. Order declaration so the
    highest-ATK or ranged attacker is in a column the AI's blocker
    can't reach.
  - **Known heuristic-AI weaknesses #6 (NEW)**: `passive_econ` does
    not proactively deploy Blocks even when sitting on 9+ stone.
    Sustained multi-turn pressure can't be answered with a Wall
    stack, so aggro that breaches by T6 can ride the gap to lethal.
  - Existing entries 5 (Day/night blind) and 6 (weapons without
    Bed) renumbered to 7 and 8.
- Heuristic AI preset patches (passive_econ only):
  - New `worker_bonus_cap` knob (default `0` = disabled). When set
    to N, the +`worker_bonus_under_3` and +`worker_bonus_first`
    bonuses are suppressed once the AI controls ≥N Workers on the
    battlefield, even if the global Workers-under-3 condition still
    holds. Set to **2** in `passive_econ` so the AI naturally
    pivots to non-Worker mobs / Blocks once it has a 2-Worker base
    instead of stacking a 3rd Worker into a board on fire.
  - Other knobs unchanged. The 6-HP-pivot issue was the same root
    cause (Workers out-scoring everything else under the +80
    bonus) so a single cap closes both holes — no new low-HP-panic
    knob needed for this iter.

### v4 — 2026-05-06 (night_rush iter-2 vs passive_econ, 12-turn W; Bed-respawn lesson + engine fix)

- Pilot ran night_rush vs `passive_econ` (post v3 patches: cap=2,
  weapon_no_bed=28, bed_search=40). Won 17→0 in 12 turns. Same kill turn
  as iter-1 but for different reasons:
  - **AI deployed 2 Beds** (T1 from opener, T9 reactive deploy under
    pressure). `bed_search_bonus=40` paid off — AI *did* prioritize the
    Bed pivot when threatened.
  - **Bed-respawn engine fact**: a Bed is NOT consumed when the avatar
    respawns. Pilot dealt 16 damage on T8 expecting lethal, but AI
    respawned at 20 with the Bed still in play. To actually kill, you
    must destroy every Bed AND deal lethal in the same combat step
    (the respawn check re-runs `has_bed` after damage resolves). T10
    fix: 1 attacker per Bed column + 4 face = 8 face + 2 Beds dead;
    T12 lethal then landed into a Bed-less AI.
  - **`auto_block=True` path was bypassing the AI handler** — confirmed
    by reading `declare_attackers` (line 972 was calling
    `mc.auto_blockers` directly). Iter-1's "chump_anything exploit" was
    actually exploiting `auto_blockers`' smart threat-score sort, not
    the bias preset.
- Strategy doc updates:
  - **Critical infrastructure: Bed** — rewrote with the not-consumed
    fact, multi-Bed counting rule, and Bed-killer attack ordering.
  - **NEW Engine quirks affecting AI behavior** section — documents
    Bed-not-consumed and the `auto_block`/handler routing fact, both
    pinned by regression tests.
  - **Known heuristic-AI weaknesses #6** — annotated that the AI WILL
    proactively deploy a 2nd Bed under pressure (observed iter-2); the
    gap is specifically non-Bed Walls/Planks.
- Engine patch: `declare_attackers` now consults
  `game.turn_manager.minecraft_ai_handler.choose_blockers` on the
  `auto_block=True` path before falling back to `mc.auto_blockers`,
  mirroring `_run_pending_block_prompt`. So the defending seat's
  `block_mode` is honored regardless of which entry point the harness
  uses. New tests:
  - `test_minecraft_bed_persists_across_multiple_respawns` — three
    sequential lethal hits with one Bed, all survived; Bed destruction
    then loses on the next hit.
  - `test_minecraft_declare_attackers_auto_block_consults_ai_handler` —
    `block_mode="never"` handler attached, `auto_block=True` declared at
    avatar-lethal HP; Zombie face damage lands unblocked (without the
    fix, smart `auto_blockers` would chump to save the avatar).
- Heuristic AI preset: kept `bed_search_bonus=40` for now per the
  pilot's "let next iter's data decide" recommendation. The 2-Bed
  deploy is correct defensive behavior; the issue isn't AI tuning, it's
  that night_rush's plan didn't account for it. Refined the night_rush
  plan rather than walking the bonus back. Other knobs unchanged.

### v5 — 2026-05-07 (builder mirror vs passive_econ, Draw in 36 turns)

- Pilot ran builder vs builder (AI running `passive_econ`). Game drew at
  the 35-turn cap (T36). Neither player dealt a single point of direct
  avatar HP damage through combat targeting across 36 turns — all damage
  went to structures or was absorbed by respawn cycles. Format-level
  findings:
  - **Builder mirror is a structure war.** With both players fielding
    Chest+Furnace+Farm Plot+Village Watchtower stacks, the avatar is
    always behind 2-3 structure layers. Normal combat cannot reach the
    avatar without concentrating 10+ ATK in a single column in one turn.
  - **AI proactively blocks contested lane every turn with free or cheap
    structures.** Oak Planks (free) and Iron Door were played reactively
    into col 2 every time the pilot cleared it. Cycling a 5HP defensive
    block at ~zero cost is faster than destroying it — don't chase.
  - **AI rebuilds Village Watchtower (5 HP, W2+S2) in col 2 immediately
    after it's destroyed.** In a builder mirror with an econ lead, the AI
    can cycle this structure indefinitely. Clearing the same column 3+
    times is a zero-EV spiral.
  - **`weapon_no_bed_penalty=28` still fires in builder context (T6
    weapon equip with no Bed present).** Iron Sword scores above the
    penalty at builder scale (more structure-based score base).
    Penalty raised to 40.
  - **AI reached 4-5 Workers by endgame despite `worker_bonus_cap=2`.**
    The cap suppresses the score bonus but the Worker still has a base
    mob value (~22) and gets played anyway once Worker bonuses stop
    triggering. A 5th Worker + Wolf Pack = 7 effective ATK — the builder
    deck's intended finisher.
- Strategy doc additions (5 bullets in new section below):
  - Builder deck win condition clarification (structure war, not attrition)
  - Workers mine XOR attack rule (explicit)
  - Avatar action mine-vs-attack planning rule
  - Builder mirror lane strategy (don't cycle, build overwhelming ATK)
  - AI contested-lane block behavior documented
- Heuristic AI preset patches: `weapon_no_bed_penalty` 28 → 40 in
  `passive_econ`. See `MC_BIAS_PRESETS["passive_econ"]` in
  `src/ai/minecraft_adapter.py`. No other knob changes this iter.

---

## Builder-deck strategic notes

These lessons apply when piloting the builder archetype (Chest, Furnace,
Farm Plot, Crafting Table as primary structure economy) or when facing it.

- **Builder win condition is NOT attrition.** The builder deck is designed
  for economy dominance leading to an Iron Golem (3/4) + Wolf Pack
  (3+Workers ATK: at 4 Workers = 7 ATK) finisher that one-shots through
  a lightly-defended column. Playing builder like aggro — using Workers as
  attackers — is the wrong line entirely. Workers mine; dedicated mobs attack.

- **Workers mine XOR attack — never both in the same turn.** A Worker that
  uses its mining action is tapped and cannot attack that turn. If you need
  to attack with a mob, do NOT have it mine first. Dedicated attacker mobs
  (non-Workers) — Village Guard (2/3), Wolf Pack (3/2+), Iron Golem (3/4)
  — are the only reliable attackers in a Worker-heavy deck.

- **Avatar action: mine vs attack — plan ahead by turn.** If you want to
  avatar_attack this turn, do NOT mine with avatar (even for day bonus).
  The day bonus is worth ~1-2W; an Iron Sword attack is 4 direct damage.
  On turns you want to attack, mine exclusively with Workers and let the
  avatar swing.

- **Builder mirror is a structure war — build overwhelming ATK, don't
  cycle lanes.** In mirror, all 3 AI columns are fortified within 6-8
  turns. The AI refills col 2 with Oak Planks (free) or Iron Door next
  turn after every clear. Repeatedly punching through col 2 is a zero-EV
  spiral. Instead, accumulate Wolf Pack (with ≥3 Workers = 6 ATK) as a
  dedicated attacker; save Iron Golem (3/4) as the finisher once redstone
  is online. The correct kill turn concentrates 10+ ATK in ONE column to
  one-shot through 3 layers simultaneously.

- **`passive_econ` blocks contested lanes every turn with free structures.**
  Whenever a column front becomes empty, AI fills it next turn with
  Oak Planks (free, ~3 ATK to destroy) or Iron Door. This is faster than
  clearing — the AI rebuilds before you can exploit the opening. Build
  overwhelming single-column ATK to clear all layers in one turn rather
  than grinding the same lane repeatedly.

- **Respawn strips ALL gear slots (weapon AND armor).** When the avatar
  dies with a Bed up, both the weapon and armor tool slots are cleared.
  Budget I3 (Iron Armor) + I2 (Iron Sword) = 5 iron per respawn cycle if
  both are equipped. Avoid committing full gear into a fight where a
  respawn is likely without accounting for the re-equip cost in the
  following 2–3 turns.

- **AI Wolf Pack scales beyond 7 ATK.** With 8 Workers on board, Wolf
  Pack = 3+8=11 ATK — a one-turn-kill on a lightly defended avatar column
  (clears Oak Planks 3 HP + Bed 4 HP in one swing with 4 overkill damage
  left for the avatar). Once the AI has 5+ Workers in builder mirror,
  maintain at least 2 structural layers at your Bed column (front + Bed
  row) at all times. A single Oak Planks block is not sufficient.

- **Col 2 weapon-attack window: ~4 Night turns.** The AI leaves col 2
  undefended for approximately 4 Night turns. Timing varies: iter 2 saw
  T12–T20; iter 3 saw T24–T28. The window opens when both players'
  defensive structures stabilize and closes when AI plays Iron Door or
  Village Watchtower into col 2. **Do not plan for a fixed turn number.**
  Equip Iron Sword (4 ATK > Bow 3 ATK) and watch for the col-2 opening
  each Night. Iron Sword through an open col 2 = 4 direct HP/Night; Bow
  through open col 2 = 3 direct HP/Night. Iron Sword is preferred.

- **Wolf Pack + avatar kill-turn sequencing.** On the kill turn, declare
  Wolf Pack mob attack FIRST (clears the mid-row structure via higher ATK),
  then declare avatar_attack second through the now-vacated column for
  direct face damage. Iter 3 confirmed: Wolf Pack (5 ATK) cleared Village
  Watchtower (5 HP), avatar Iron Sword (4 ATK) hit AI avatar for 4 HP in
  the same Night turn. This is the confirmed 2-attacker kill-turn pattern.

- **Strip Mine (1S→1I+1R) is mandatory at 2× copies.** In builder mirror,
  neither player naturally generates redstone from biomes. Without Strip
  Mine, Iron Golem stays uncastable all game. If no Strip Mine is drawn
  by T10, the builder win condition (Iron Golem + Wolf Pack burst) is
  locked out. Mulligan hands with Bed+structures but no Worker AND no
  Strip Mine more aggressively than the plan suggests.

- **True Kill Sequence assembly is a 5-condition problem — Chest acceleration
  by T2-4 is mandatory.** The sequence (Iron Golem + Wolf Pack + Iron Sword
  in one Night) requires simultaneously: (1) Strip Mine drawn and played,
  (2) I1+R1 accumulated, (3) Iron Golem castable, (4) ≥4 Workers on board,
  (5) target column with Bed at front and empty mid/back. With only ~2 Strip
  Mine copies in a 30-card deck, P(not drawing either in 13 turns) ≈ 40%
  without a draw engine. Chest deployed by T2-4 adds draw each turn; by T10
  the pilot has drawn ~14 cards instead of 10, cutting the miss probability
  to ~38%. More importantly: Chest must be deployed EARLY — deploying at T20
  (as observed in iter-5) provides almost no benefit for finding Strip Mine
  before the kill window closes. Auto-mulligan any opener without Chest OR
  Worker when Bed is present; the kill sequence cannot be assembled without
  both Chest-acceleration and Worker density.

### v6 — 2026-05-07 (builder mirror vs passive_econ iter 2, Draw at T21 play-turns)

- Pilot ran builder vs builder (AI running `passive_econ` with v5 patches:
  `weapon_no_bed_penalty=40`, `bed_search_bonus=40`, `worker_bonus_cap=2`).
  Game stopped at my T21 play-turns (state T42). Neither player reached
  lethal; final HP was Me=20 (Bed-respawned twice), AI=14 HP. Different
  approach from iter 1: abandoned pure econ and committed to a Bow + Iron
  Sword weapon attack line targeting undefended col 2. Results:
  - **First time direct HP damage was dealt in a builder mirror.** 6 HP
    dealt to AI avatar (17→14 HP window) via col 2 Bow attacks across 4
    Night turns (T12–T20). Iter 1 dealt zero.
  - **Col 2 direct-face window is ~4 Night turns.** AI seals the third
    column with Iron Door or Cobblestone Wall by T19–20. The window for
    ranged-weapon direct HP damage is short — plan weapon deployment and
    Worker availability to front-load attacks into T12–T20. After that,
    all 3 columns are 3-deep and no unblocked path exists.
  - **Worker drought (zero Workers through T12) broke the weapon plan.**
    Without Workers mining, avatar must mine OR attack — not both. The
    "weapon + Workers" synergy never activated. All 4 Night turns of
    effective Bow attacks came from the avatar mining on Day and attacking
    on Night, but this forfeits econ every other turn.
  - **Respawn strips ALL gear slots (weapon + armor both).** Two
    respawns cost I2 (Iron Sword) + I3 (Iron Armor) = 5 iron each cycle.
    The strategy doc's "gear is discarded" language undersells the cost —
    armor is also stripped.
  - **AI Wolf Pack scales to 11 ATK with 8 Workers.** By T35 AI had 8
    Workers; Wolf Pack = 3+8=11 ATK. Current doc said "4 Workers = 7 ATK"
    as the ceiling — wrong. The AI can reach 11+ in builder mirror by T30.
    This is a one-turn-kill on a lightly defended avatar column.
  - **`passive_econ` iron mining (iter-2 run-specific): observed 0-5 iron
    across 42 turns.** The AI accumulated significant stone surplus without
    mining iron proportionally in this run. Tentatively flagged as a
    `mining_mode="premium_first"` blind spot — but see v7 correction below.
  - **Builder mirror is longer than T36.** Game ran to state T42 with no
    sign of resolution. Effective cap is ~T25 play-turns, not T18.
- Strategy doc updates:
  - **"Critical infrastructure: Bed"**: Added note that respawn strips
    BOTH weapon and armor slots. Budget I3+I2=5 iron per respawn cycle if
    both equipped; don't commit full gear into a fight without considering
    the re-equip cost after death.
  - **"Builder-deck strategic notes"**: Added Wolf Pack scaling note (AI
    can reach 11 ATK with 8 Workers by T30+). Added 2-layer Bed-column
    protection rule. Added "Col 2 Bow window" bullet and Strip Mine
    mandatory-2× rule.
- Heuristic AI preset: no knob changes this iter. The `mining_mode` blind
  spot (ignoring iron) was flagged for next iteration — conservative to
  change mid-loop without a variant tournament comparison.
  `weapon_no_bed_penalty=40` working. `bed_search_bonus=40` working.
  `worker_bonus_cap=2` working.
  **Coach correction (2026-05-07, after iter 3):** The iter-2 claim that
  `passive_econ` "ignores iron despite huge stone surplus" is NOT confirmed
  by iter-3 data. Iter-3 AI ended with 25 iron (avg 1.4/turn) via Cave
  mining with 5 Workers. The iter-2 result appears to be run-specific
  (fewer Workers or less Cave access). `mining_mode="premium_first"` does
  NOT skip iron — iron ranks 3rd in the priority order
  `(diamond, redstone, iron, stone, wood)`. The "blind spot" claimed in
  this entry is retracted.

### v7 — 2026-05-07 (builder mirror vs passive_econ iter 3, Draw at T36 / 18 play-turns)

- Pilot ran Iron Golem plan (Strip Mine x2 → I1+R1 for Iron Golem) but Strip Mine was never
  drawn in 18 player turns. Fell back to Iron Sword (T22) + Wolf Pack (T34) weapon line.
  Final: Me=7 HP, AI=12 HP. 8 direct HP dealt (vs 6 in iter 2). New findings:
  - **Iron Golem costs I1+R1, NOT I3+R1.** Confirmed from `src/cards/minecraft/alpha.py`:
    `_cost(iron=1, redstone=1)`. Prior builder_plan.md said "3I+1R" — that was wrong. A single
    Strip Mine immediately enables Iron Golem. Rewrote builder_plan.md Key cards section.
  - **`passive_econ` mines iron at normal Cave rates.** AI ended with 25 iron (avg 1.4/turn)
    via Cave mining with 5 Workers. The iter-2 "AI ignores iron despite 50+ stone surplus"
    finding is NOT confirmed here. Flagged as run-specific, not a reliable heuristic weakness.
    The `mining_mode="premium_first"` label does not mean "ignores iron."
  - **Wolf Pack + avatar double-attack kill-turn sequencing confirmed.** Wolf Pack (5 ATK)
    cleared Village Watchtower (5 HP), then avatar Iron Sword (4 ATK) hit AI avatar for 4 HP.
    Declare Wolf Pack mob attack first to clear mid-row structure; avatar_attack second through
    the vacated column. This is the confirmed 2-attacker kill-turn pattern.
  - **Col-2 window timing is NOT fixed at T12-T20.** In iter 3 the window appeared at T24-T28
    (shifted 12 turns vs iter 2). Window timing depends on both players' defensive stabilization,
    not a fixed turn number. Planning "equip weapon by T8" doesn't help if col-2 doesn't open
    until T24.
  - **Strip Mine sparsity (~2/30) makes Iron Golem plan unreliable as primary win condition.**
    Neither player drew Strip Mine in 18 turns. Any plan relying on Strip Mine needs a Chest
    or Eyes of Ender draw engine to find it by T6-8 at the latest.
  - **`weapon_no_bed_penalty=40` working in builder context.** AI held 2x Bow in hand for 10+
    turns without equipping. Confirmed effective suppression.
  - **Village Reinforcements (W2+I1) — RESOLVED.** Earlier iteration flagged that
    Guards might not appear after casting. End-to-end regression in
    `tests/test_minecraft_interceptors.py::test_village_reinforcements_full_play_lands_guard`
    confirms the 2/3 Village Guard reliably lands on the battlefield via `play_card`.
- Strategy doc updates:
  - **"Builder-deck strategic notes"**: Added Wolf Pack kill-turn sequencing note and
    col-2 window timing correction (not fixed at T12-T20).
  - **Known heuristic-AI weaknesses**: Qualified `passive_econ` iron-mining claim
    (now "run-specific observation" not confirmed weakness).
  - **Iron Golem cost**: Verified actual card cost as I1+R1 (not I3+R1); all doc
    references corrected.
  - **v6 changelog**: Added coach correction clarifying the iter-2 iron-mining claim
    was run-specific and is retracted; `mining_mode="premium_first"` does not skip iron.
- Heuristic AI preset: no changes this iter. All v5-v6 patches confirmed working. No new
  weakness patched because the iter-2 iron-mining blind spot is not confirmed as consistent.

### v8 — 2026-05-07 (builder mirror vs passive_econ iter 4, LOSS at T39)

- Pilot ran builder vs builder (AI running `passive_econ` with v5-v7 patches).
  LOSS at T39 — AI wins at 20 HP, pilot at 1 HP (no Bed). First loss in the
  builder mirror loop. Root causes: Worker drought (first Worker drawn T12),
  no Strip Mine drawn (Iron Golem path locked all game), Water Bucket Moats
  sealed all mob attacks from T8, AI Wolf Pack reached 11 ATK with 8 Workers.
  Despite the loss, four mechanically critical engine facts were discovered:

  **1. avatar_attack damage does NOT propagate past the first structure.**
  Prior docs implied overkill damage could chain through to the next
  structure. This is wrong. T28: Iron Sword (4 ATK) vs Cobblestone Wall
  (6 HP) → Wall takes 4 damage, drops to 2 HP. No damage reached the
  Crafting Table behind it. T32: Iron Sword vs Wall (2 HP) → Wall
  destroyed, column slot empty. No carry-through to rear structures.
  T36: Iron Sword (4 ATK) vs Bed (4 HP) → Bed destroyed, 0 overkill.
  Each avatar_attack hits ONE target only — the front occupied structure
  in the column. Any damage beyond that target's HP is lost. A 3-deep
  column (front + mid + back + avatar) requires 4 separate avatar_attack
  turns to reach face. At 1 avatar_attack per 2 game-turns (Night only),
  that is 8 game-turns minimum from a clear front — the weapon line is
  fundamentally too slow without mob attackers clearing layers in parallel.
  The "Wolf Pack clears mid-row, avatar goes face in same turn" pattern
  from iter 3 works ONLY because Wolf Pack is a SEPARATE mob attack
  clearing a SEPARATE structure — avatar_attack never chains through
  multiple structures itself.

  **2. AI reactively places Bed into cleared front slots (y=2).**
  At T32 the pilot destroyed the Cobblestone Wall at AI col 1 y=2, leaving
  the slot empty. At T34 (very next turn) the AI placed a NEW Bed in that
  exact slot. `bed_search_bonus=40` fires when the AI has no Bed AND a
  front slot is open, placing the Bed in the most vulnerable slot. Clearing
  a front-row structure does NOT open a clean attack lane — the AI fills it
  with a Bed (4 HP blocker + respawn protection) within 1 turn. You cannot
  "soften" a lane by clearing its front structure and expect an open path.
  Instead, you must have enough combined ATK to clear ALL layers
  simultaneously in one swing. Documented under "Known heuristic-AI
  weaknesses" as entry 9.

  **3. Water Bucket Moat blocks mob attacks only, NOT avatar weapon attacks.**
  AI placed Water Bucket Moats at all 3 columns. Mob attacks were absorbed
  by chump blockers — the Moat did not trigger on mob-vs-structure combat.
  Avatar_attack at T28 hit the Cobblestone Wall at col 1 y=2 directly,
  bypassing any Moat check. Confirmed engine routing: Water Bucket Moat
  intercepts mob-lane attacks (mob targeting structures), but NOT avatar
  weapon attacks. Avatar weapon attacks target structures directly and skip
  Moat blocking. Plan your offensive accordingly: use avatar_attack for
  lane-clearing, mobs for specific targets.

  **4. True kill sequence requires Iron Golem + Wolf Pack + Iron Sword
  simultaneously, assembled via Strip Mine by T6.**
  Minimum viable kill board state: Iron Golem (3/4, I1+R1) + Wolf Pack
  (4+ ATK with ≥4 Workers) + avatar Iron Sword (4 ATK) attacking in one
  Night turn = 3+4+4=11+ ATK minimum. Each attacker handles a separate
  layer: Wolf Pack hits front-row Bed (4 HP, needs ≥4 ATK = 4 Workers),
  Iron Golem hits mid-row structure (3 ATK), avatar_attack hits back-row
  or face directly. This only works if the target column is already
  partially cleared. Requires Strip Mine by T6 (via Chest draw engine) to
  unlock redstone for Iron Golem. Without Strip Mine, Iron Golem is
  inaccessible — the builder kill condition is locked out.

- Strategy doc additions: see "Known heuristic-AI weaknesses" (new entry
  9), avatar_attack section correction (no overkill propagation), and
  Water Bucket Moat routing rule under "Avatar attacks."
- Heuristic AI preset patches: **no changes to `passive_econ` bias knobs
  this iter.** The pilot LOST (could not find an exploitable weakness), so
  the coach has no confirmed gap to patch. One AI behavioral issue was
  flagged for future investigation: AI places Bed in the most recently
  cleared column (the contested lane) rather than in a column protected
  by Water Bucket Moats. A `bed_prefer_protected_column` knob is noted as
  a possible future addition — but requires a future iter to confirm it
  closes a real exploit before applying.

### v9 — 2026-05-07 (builder mirror vs passive_econ iter 5, LOSS at T27)

- Pilot ran builder vs builder (AI running `passive_econ` with v5-v8 patches).
  LOSS at T27 Night — AI wins at 20 HP, pilot at 11 HP with no Bed.
  **True kill sequence test**: goal was Iron Golem + Wolf Pack + Iron Sword in
  one Night. This failed completely: Strip Mine never drawn in 13 player turns
  (0/2 copies found), both Iron Golem copies uncastable all game. First Worker
  (Steve's Helper) deployed at T16 — 8 player turns in. Wolf Pack deployed T18
  with 1 Worker = 4 ATK, died to a blocker T24. Bed destroyed ~T20 with no
  replacement; HP attrition (5 HP + 4 HP = 9 HP in 2 Night turns) resulted
  in lethal at T27.

  **Critical finding: avatar_attack on empty columns DOES deal face damage —
  pilot claim was WRONG. (Code-verified 2026-05-07.)**

  The pilot reported that 3 avatar_attacks on columns displayed as fully empty
  (all dots in the grid) returned ok=True but dealt zero HP damage. The pilot
  concluded avatar_attack silently no-ops on empty columns. This is FALSE.
  Code trace through `src/engine/minecraft.py::avatar_attack` (line 489):

      resolved = column_target(state, opponent, target_column, weapon_keywords) or opponent

  `column_target` returns `None` when the column is clear. `None or opponent`
  resolves to `opponent` (the player ID string). The DAMAGE event fires with
  `target = opponent_player_id`. In `src/engine/pipeline/handlers/damage.py::_handle_damage`:

      if target_id in state.players:
          adapter.apply_player_damage(player, amount, state)

  `MinecraftModeAdapter.apply_player_damage` (mode_adapter.py:744) does:

      player.life -= max(0, amount - reduction)

  Live test confirmation: game instantiated, P2 life started at 20, avatar_attack
  on empty col 0, P2 life dropped to 19 (HP change = 1). The routing is correct.

  **What actually happened in the pilot game (most likely explanation):**
  The columns shown as "all dots" at T8 and T12 were NOT fully empty at all
  grid depths. The display dots may represent front-row (y=2) emptiness only,
  while y=0 or y=1 slots contained AI structures (Water Bucket Moat at y=2
  col 1 was placed by T8; other columns may have had structures at y=0/y=1).
  The avatar_attack struck those non-front structures, dealt HP to them, and
  since they didn't die (not enough damage to destroy), the visible HP display
  showed no destroyed card and pilot interpreted this as "zero HP damage".
  The 0 HP change was structure absorption, not engine no-op.

  **CORRECTION to v6/v7 col-2 face-damage claims:** The v6 and v7 changelogs
  describe "6 HP dealt to AI avatar via col 2 Bow attacks" and "8 direct HP
  dealt (20→12)". These claims are accurate — when col 2 was confirmed empty
  at all grid depths (no structures in ANY y slot), avatar_attack correctly
  routed to the opponent player's HP. The code routing is `column_target → None
  → fallback to opponent_player_id → apply_player_damage`. So those iter-2/3
  HP readings were genuine face damage, not structure absorption. The engine
  works as intended.

  **Clarifying note added to strategy doc "Avatar attacks" section:** The
  empty-column routing is explicit: if ALL grid slots in a column are empty
  (no structure at y=0, y=1, or y=2), avatar_attack routes to the opponent
  avatar (direct HP). If ANY slot contains a structure, avatar_attack hits
  the FRONT-MOST structure only. The key distinction for the pilot: check
  all three y-depths, not just the front row, before concluding a column is
  "empty" and expecting face damage.

- **Root causes of iter-5 loss (ranked):**
  1. Strip Mine never drawn in 13 player turns — Iron Golem path locked all
     game. P(not drawing Strip Mine in 13 draws) ≈ 40% without draw engine.
  2. Chest draw engine deployed too late (T20 instead of T2-4) — insufficient
     draw acceleration to find Strip Mine by the kill window.
  3. Worker drought — first Worker at T16, Wolf Pack at 1 Worker = 4 ATK max,
     died before scaling.
  4. Bed lost ~T20 with no replacement — HP attrition unavoidable for final 4
     Night turns. 9 HP in 2 Nights = lethal.
  5. Display misread: 3 avatar_attacks believed "wasted" were actually hitting
     structures (see above). No actual wasted engine actions.

- **Kill sequence assembly difficulty confirmed.** The True Kill Sequence
  (Iron Golem + Wolf Pack + Iron Sword in one Night) requires 5 simultaneous
  conditions: (1) Strip Mine drawn AND played, (2) I1+R1 accumulated,
  (3) Iron Golem castable, (4) ≥4 Workers on board, (5) target column at
  exactly Bed-front-only with mid/back empty. Natural draw variance makes
  this nearly impossible without deliberate Chest acceleration by T2-4.
  Auto-mulligan any hand without Chest OR Worker if Bed is present.

- **Strategy doc additions:**
  - "Avatar attacks" section: new clarifying note on empty-column routing
    (all y-depths must be empty for face damage; any structure = structure hit).
  - "Builder-deck strategic notes": added iter-5 kill-sequence assembly note
    (5 simultaneous conditions, Chest acceleration mandatory by T2-4).
- Heuristic AI preset patches: **no changes to `passive_econ` bias knobs.**
  Pilot lost again with no clear exploitable weakness observed — no bias surface
  to patch. AI behavior was consistent with v5-v8 patches (Bed placed reactively,
  `worker_bonus_cap=2` working, `weapon_no_bed_penalty=40` working).

### v10 — 2026-05-07 (P2b iter 1 — two-pilot mode, both pilots stalled)

**Format**: Two LLM pilots (Pilot A = builder/P1, Pilot B = miner/P2) in parallel
dispatch. Game stalled at Turn 2-3 Night; neither pilot saw the other take their
turn, both gave up after 10-30+ polls. No combat, no HP damage. No winner.

#### Infrastructure finding (not a strategic finding)

Two-pilot parallel dispatch is fragile. Each pilot polls the shared state file
(`/tmp/mc_wet_test_state.pkl`) to detect when it is their turn, but neither pilot
has visibility into the *other* pilot's "thinking / about to move" state. Result:
if Pilot A finishes its turn and Pilot B's agent loop doesn't wake up in time,
Pilot B stalls indefinitely — and vice versa. Both agents stalled in this iter
(Pilot A gave up at T2 waiting for Pilot B; Pilot B gave up at T3 Night waiting
for Pilot A). A `last_action_player` / `turn_ended_by` marker in the pkl payload
would allow each pilot to verify the opponent actually completed their turn before
declaring a stall. This is an infrastructure gap in the harness — not a strategic
or format finding — and should not affect AI bias presets.

#### Strategic findings (pre-stall observations)

1. **Warden ETB clears all Workers ≤4 toughness — major builder-matchup threat.**
   Warden's ETB deals 4 damage to ALL enemy mobs. Builder Workers (Steve's Helper
   1/2, Alex's Scout 2/1, Village Guard 2/3) all die instantly. Panda Forager
   (2/3) dies. Even Wolf Pack (3/2 base) dies. Only Iron Golem (3/4) survives
   (takes 4 damage, lives at 0 — confirm exact engine ruling — but is not
   one-shotted). If a miner pilot times Warden to land when the builder's board
   is Worker-heavy, the entire builder mob army collapses in one ETB. Builder
   counter: establish Iron Golem BEFORE the opponent plays Warden. See
   builder_plan.md "Anticipated weaknesses" for the line.

2. **Miner's T1 Panda Forager (skipping Bed) is an aggressive opening line.**
   Pilot B's T0 auto-setup (Forest mine → Panda Forager W2, skipping Bed) is a
   deliberate higher-variance ramp line distinct from the miner plan's standard
   opener (Chop Trees + Bed + Steve's Helper). The 2/3 body has better combat
   stats than Steve's Helper (1/2) and blocks more aggressively, but leaves miner
   Bed-less into T2 with 0 materials and SS on the only Worker. Risk: builder
   can deal pre-Bed lethal damage if it applies pressure T2-4 before miner's
   Panda Forager untaps. Reward: Panda Forager's extra HP (2/3 vs 1/2) makes
   it a more durable mining anchor once untapped.

3. **Miner has stronger late-game finishers than the builder mirror demonstrates.**
   Warden (7/8 + board wipe ETB) and Ender Dragon (6/6 Aerial + 2×creature-count
   ETB damage) outclass builder's Iron Golem (3/4) and Wolf Pack (≤11 ATK) in
   raw power ceiling. With 4 Workers on board, Ender Dragon ETB alone deals 8
   face damage before combat. The miner's kill window (~T15-20) is slower than
   builder's (~T18-25 vs mirror), but the finisher package is harder to survive
   once it resolves. Builder must establish Iron Golem as a 3/4 body that
   survives Warden ETB — otherwise the miner can time Warden to erase the
   builder's board and swing with Dragon immediately after.

### v11 — 2026-05-07 (box_of_horrors iter 1 vs passive_econ raider, LOSS at T15)

- Pilot ran box_of_horrors (60-card horror tribal) vs `passive_econ` raider.
  LOSS at T15 — AI=19 HP, pilot=0 HP. Final damage dealt to AI = 1 chip
  (Sleep-Stealer ETB). All four format-level findings below are deck-agnostic
  and not previously documented.

  **1. Day-craft discount mechanic (-1W or -1S on first structure/block per Day).**
  The first STRUCTURE or BLOCK played during a Day phase gets -1W OR -1S
  (whichever applies first to the cost; engine checks wood first, then stone).
  Applies only to structures/blocks, not mobs/actions/tools. Does NOT apply on
  Night turns. Per-player `mc_day_craft_discount_used_<pid>` flag is set after
  first use; second structure on the same Day pays full cost. Engine code:
  `_discounted_cost` in `src/engine/minecraft.py:201`. Concrete examples:
  Cursed Bed (W1) → 0, Bed (W2) → W1, Lectern of Whispers (W2) → W1,
  Soul Forge (S2) → S1, Eldritch Altar (W1+S1+I1+R1) → S1+I1+R1,
  Cobblestone Wall (S2) → S1, Sculk Catalyst (S1+R1) → R1.
  Strategic implication: schedule structure deployments to fall on Day turns
  whenever possible. A 4-cost structure built on Day saves 1 material vs
  Night. Documented under Format fundamentals as new "Day-craft discount" rule.

  **2. Cheap turn-bonus structures (3-4 HP) cannot survive a single 4+ ATK
  swing. Do NOT deploy them in unprotected columns.** Soul Forge (4 HP, S2)
  and Lectern of Whispers (3 HP, W2) both got destroyed the SAME TURN the AI
  attacked, before ticking ANY value. Wolf Pack at 4 ATK kills both in one
  swing. Rule: deploy turn-bonus structures only with (a) same-turn front-row
  defender, (b) only in the Bed column (Bed forces AI to attack through the
  4HP Bed first), or (c) behind a wall/block. A turn-bonus structure that
  ticks zero times is a card-and-mana negative. This applies across all
  decks, not just box_of_horrors.

  **3. Creeper deathrattle order-of-resolution quirk: "deal 3 to frontmost in
  attacked column" resolves BEFORE other deathrattles' new tokens claim the
  frontmost slot.** When an Endermite Cluster (1/1, deathrattle: spawn 1/1
  Endermite token) mutual-kills a Creeper, the Endermite token survives the
  Creeper deathrattle's 3 dmg because the token's "frontmost" status doesn't
  resolve in time. Edge case but useful for Endermite Cluster value
  calculations.

  **4. AI's confirmed weakness #6 (no proactive non-Bed Block deploy)
  re-confirmed in this matchup.** AI's col 0 and col 2 stayed empty all game;
  AI hoarded 6-9 stone but never built walls on undefended lanes. Only the
  AI's Bed column (col 1) got an Oak Planks block (T11). This means an
  aggressive weapon-line strategy can chip undefended lanes — but the
  exploiting deck must have a non-redstone-gated weapon (box_of_horrors
  could not exploit because Eldritch Bow is W2+R1, redstone-gated).

- Strategy doc updates:
  - **Format fundamentals**: NEW subsection "Day-craft discount" documents
    the -1W/-1S Day-only mechanic, examples, and per-player single-use flag.
  - **Strategic patterns / Mid game**: NEW "Turn-bonus structure protection
    rule" — cheap (3-4 HP) turn-bonus structures cannot survive an unprotected
    deploy turn into AI Wolf Pack / Creeper / weapon swings. Deploy with
    same-turn defender, in the Bed column, or behind a wall.
  - **Card-specific notes**: NEW Creeper deathrattle ordering note.
  - **Mulligan rules**: NEW "Redstone-bottleneck deck rule" — decks where
    >50% of removal/mid-curve is redstone-gated should treat redstone as
    Bed-equivalent in mulligan rules; missing a redstone source = a
    guaranteed loss vector. Auto-mulligan any redstone-bottleneck hand
    without Strip Mine, Allay Courier, or another redstone-mining structure.
- Heuristic AI preset patches: **no changes this iter.** The AI played its
  preset correctly throughout (Worker bonus capped at 2, weapon equip waited
  for Bed, chump_anything pairing in declaration order, no proactive non-Bed
  Block deploy — all consistent with v5-v10 patches). The loss was driven by
  deck-construction (redstone-economy single-point-of-failure on 4/60 cards),
  not by an exploitable AI gap. **No knobs to patch.**

  Future-iter consideration only (NOT for this iter): the AI's T7 weapon
  equip with only 2 mobs on board and no follow-up board development was
  super-aggressive — suggests the weapon equip score doesn't account for
  "do I have enough mob density to defend the avatar after equipping?" If
  repeated runs show the AI dying after equipping into a weakened board,
  consider a `weapon_with_low_mob_density_penalty` knob. But not based on
  this single game.

### v12 — 2026-05-07 (box_of_horrors deck repair + encoder session)

**Summary**: box_of_horrors went from 0% → 33.3% winrate in a 5-deck tournament
after structural repairs. The deck is now standard-format (50 cards / 25 distinct).

**Root causes diagnosed**:

1. **Redstone catch-22**: ~70% of boh cards cost R1, but no starting biome
   produces redstone. Bootstrap chain identified: Strip Mine (S1 → +W1+I1+R1)
   → Allay Courier (R1 ongoing) → or avatar_explore Cave → Deep Cave (R1/turn).

2. **Uncastable diamonds**: Elder Phantom (S1+R1+D1) and 4 other D-cost cards
   removed. Cave Dweller (2W+2I+R1) is the new boss finisher.

3. **Oversized deck**: 60 cards trimmed to 50 by removing Elder Phantom (D1
   uncastable), Lectern of Whispers (redundant draw), Fog Wall (dead defense),
   Phantom Wing (low synergy), Soul Sand Trap (slowest trap).

**Infrastructure added**:

- **avatar_explore harness command**: `mc_wet_test.py avatar_explore <biome_idx>`
  now exposes the biome upgrade mechanic to both pilots and testers. Cave → Deep
  Cave adds R1/turn permanently for 1 avatar action — the boh deck's critical
  T1/T2 ramp move.

- **Explore heuristic** (`_best_biome_to_explore` in adapter): scores biomes
  by new material unlocked (D=80, R=60, I=20, yield bumps=5). Fires when
  explore_map_bonus ≥ 40. Priority: attack > explore > mine. With redstone
  bottleneck detection, explore bias +40 on turns ≤ 2 if Cave → Deep Cave
  is available.

**Heuristic encoder changes** (encoding pilot optimal plays):

- `_is_redstone_bottlenecked()`: True when player has no redstone sources in
  structures or biomes. Used as a multiplier for early-game explore/bootstrap plays.
- Allay Courier +35 priority when bottlenecked (must play it before anything else).
- Strip Mine +25 when bottlenecked.
- Sculk Catalyst +30 when bottlenecked (turn-bonus redstone structure).
- Turn-bonus structures -15 when no protected columns (don't deploy naked).
- `_choose_cell_for_card()` prefers protected columns for turn-bonus structures.

**Deck-specific boh lessons** (see `docs/decks/box_of_horrors_plan.md`):

- T1: Mine Cave (S1+I1) + Hills (S1) → play Strip Mine (S1→free) → now have R1 →
  play Allay Courier. From T2, R1/turn guaranteed without explore.
- Alternatively: T1 mine, avatar_explore Cave → Deep Cave → from T2 R1/turn.
- The horror mid-curve (Wither Skeleton S1+I1+R1, Sculk Stalker S1+I1+R1) is
  strong once the redstone bootstrap is online. Game-plan is control-with-attrition:
  discard harassment + Stalker's Den lockdown + mid-range Horrors.

<!-- Append new sections below as the loop runs. Each entry: date, what
was learned, what was patched (strategy doc updates + heuristic AI
preset changes). -->
