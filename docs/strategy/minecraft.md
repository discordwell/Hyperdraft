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
  (no respawn). With a Bed, dying respawns at 20 HP (with gear discarded).
- Play Bed turn 1-2 if it's in opening hand. If it's not, **mulligan
  toward it** if rules allow, or prioritize drawing/tutoring it.
- An opponent without a Bed is a loss waiting to happen — apply lethal
  pressure. Track opponent's Bed status every turn.

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

---

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

5. **Day/night blind:** AI doesn't time plays to day/night cycle.
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

6. **AI equips weapons without a Bed.** AI cheerfully equips Iron Sword
   despite no Bed protection — exactly the suicide line a human is told
   to avoid. Iter-2 confirmed `weapon_no_bed_penalty=18` was undersized
   (Iron Sword base = 15 + mc_attack=4 = 19, net +1 with the penalty,
   still equipped). Penalty has been raised to 28 (net -9 for Iron
   Sword, net -10 for Bow). If the AI's avatar dies in an unequipped
   state, it loses its biggest damage source; force pressure into the
   AI's avatar column when it has equipped without a Bed.

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

<!-- Append new sections below as the loop runs. Each entry: date, what
was learned, what was patched (strategy doc updates + heuristic AI
preset changes). -->
