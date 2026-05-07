# box_of_horrors — Plan

## Composition summary

60-card horror tribal deck (30 unique × 2). Post-patch composition (2026-05-07)
removed all diamond-cost cards (the original deck had Elder Phantom S1+R1+D1
and other diamond cards that were uncastable without a diamond source) and
added Workers + Bed + a cheaper Block to fix the deck's bootstrap and
redstone bottleneck. The deck is built around a redstone-economy bootstrap
(Strip Mine + Sculk Catalyst + Allay Courier) feeding mid-cost horrors,
with Cave Dweller as the lone solo finisher.

### Full card inventory (60 cards = 30 unique × 2)

#### Workers + bootstrap (8 cards)
- 2x Strip Mine (S1 → +1I +1R) — the redstone-economy enabler
- 2x Allay Courier (R1, 1/2 Worker) — mining yields +1 Redstone
- 2x Steve's Helper (W1, 1/2 Worker) — mining yields +1 Wood
- 2x Villager Mason (W1+S1, 1/3 Worker) — mining yields +1 Stone

#### Mana / draw structures (10 cards)
- 2x Cursed Bed (W1, /2) — Bed (respawn protection); cheap and fragile (free
  on Day via day-craft discount)
- 2x Lectern of Whispers (W2, /3) — draw 1/turn (W1 on Day via day-craft discount)
- 2x Sculk Catalyst (S1+R1, /3) — +1 Redstone/turn (R1 on Day via day-craft discount)
- 2x Soul Forge (S2, /4) — +1 Iron/turn (S1 on Day via day-craft discount)
- 2x Eldritch Altar (W1+S1+I1+R1, /4) — +1 Redstone/turn AND draw 1 on play
  (S1+I1+R1 on Day via day-craft discount)

#### Defensive grid (6 cards)
- 2x Fog Wall (S2, /6 Block) — 6HP wall
- 2x Soul Sand Trap (S1+R1, /2 Block) — Deathrattle: 3/2 Wither Skeleton token
- 2x Stalker's Den (W1+S1+R1, /4) — other Stalkers get +1 ATK

#### Cheap stalkers + spirits (Mobs, ~16 cards)
- 2x Lost Soul (W1, 1/1 Horror Spirit) — Deathrattle: draw 1
- 2x Whispering Wraith (W1+S1, 2/2 Aerial Horror Spirit) — on block: deal 1 to attacker
- 2x Shadow Crawler (W1+S1, 3/1 Climb Stalker)
- 2x Sleep-Stealer (W2, 2/3 Aerial Spirit) — on play: 1 dmg to opponent avatar
- 2x Endermite Cluster (R1, 1/1 End) — Deathrattle: 1/1 Endermite token
- 2x Phantom Wing (W2, 2/2 Aerial Hostile) — +1 ATK at Night
- 2x Cave Crawler (W1+S1+I1, 4/2 Climb Stalker)
- 2x Ratman (W1+S1+R1, 3/2 Climb Stalker) — on play: opponent discards 1

#### Mid-range threats (6 cards)
- 2x Wither Skeleton (S1+I1+R1, 4/3 Hostile Nether Undead) — wither rot: attack a mob, mob loses 1 toughness permanently
- 2x Sculk Stalker (S1+I1+R1, 4/3 Hostile Stalker) — on attack: gain 1 redstone
- 2x The Old Watcher (W1+S1+I1+R1, 4/5 Horror Boss) — Lord: other Horrors +1 ATK

#### Solo boss (2 cards)
- 2x Cave Dweller (W2+I2+R1, 6/4 Climb+Haste Stalker Boss) — on attack: opp discards 1

#### Removal / utility (8 cards)
- 2x Whispering Curse (R1) — opp discards 1
- 2x Drag to the Dark (W1+R1) — destroy mob with ≤3 HP
- 2x Wither Skull (S1+R1) — 3 dmg to target
- 2x Goatman's Hex (W1+R1) — 1 dmg to ALL enemy mobs (kills 1/1s, weakens larger)

#### Gear (2 cards)
- 2x Eldritch Bow (W2+R1) — avatar attacks 4 (Ranged)

## Win condition

**Mid-range Horror grind.** This deck does NOT have an OTK finisher; instead it
attritions through chip damage from cheap stalkers (Shadow Crawler, Cave Crawler,
Ratman) and aerial chip (Phantom Wing, Sleep-Stealer), backed by removal
(Drag to the Dark, Wither Skull, Goatman's Hex). Cave Dweller (6/4 Haste+Climb)
is the one true finisher — 6 ATK with Haste means it swings the turn it
lands and ignores walls. Eldritch Bow gives the avatar 4 ATK (Ranged), and
Stalker's Den + The Old Watcher both pump the Stalker tribe.

The damage math: 2-3 Stalkers on board for 3-5 turns + Cave Dweller on T6-7
for the kill. Each turn we want to clear with Goatman's Hex / Wither Skull
to keep our chip alive while erasing AI blockers.

## Target turn

**T8-10 lethal** if the redstone bootstrap goes off cleanly. T10-12 if we
have to grind without Cave Dweller. The deck stalls badly without Strip
Mine in opener (no R for Sculk Catalyst → no R economy).

## Key cards

### Bootstrap (must hit T1-3)
- **Strip Mine**: only cheap path to redstone (S1 → I1+R1). Run 2 copies.
  Without this in opener, mulligan if rules permit.
- **Sculk Catalyst**: redstone engine. S1+R1 → +1R/turn. T2 deploy ideal.
- **Allay Courier**: Redstone Worker (R1 cost, mining yields +1R).
  Once down, every avatar mine doubles into +1R via worker_mine.

### Engine extension
- **Eldritch Altar**: W1+S1+I1+R1 for +1R/turn AND draws on play. Plays as
  a "Sculk Catalyst that replaces itself" once economy supports the cost.
- **Lectern of Whispers**: W2 for +1 card/turn — best draw engine in deck.
- **Soul Forge**: S2 for +1 iron/turn — needed for Wither Skeleton and
  later Cave Dweller.

### Pressure
- **Wither Skeleton (S1+I1+R1)**: 4/3 with wither rot. Attacking opponent mobs
  permanently shrinks them — very strong vs builder/raider chump-blockers.
- **Cave Dweller (W2+I2+R1)**: 6/4 Climb+Haste. The finisher.
- **Eldritch Bow (W2+R1)**: 4 ATK Ranged on avatar. Equip when avatar can mine
  with Workers (i.e. once Allay Courier or Steve's Helper is on board).

### Removal
- **Goatman's Hex (W1+R1)**: 1 dmg to all enemy mobs. Kills 1/1s, weakens
  Workers. Vs `passive_econ` raider this clears Worker chumps efficiently.
- **Drag to the Dark (W1+R1)**: hard removal on ≤3HP mobs (most raider mobs).
- **Wither Skull (S1+R1)**: flexible 3 dmg — kills small mobs OR hits a Bed
  for 3 of its 4 HP.

## Opening sequence

### Ideal opening (Strip Mine + Cursed Bed in hand, plus a Worker)
- T1 Day: mine Hills (+1S day bonus +1S = 2S). Play Strip Mine (S1 → +1I+1R).
  We end with 1S, 1I, 1R. Play Cursed Bed (W1) if we mined Forest day-bonus
  on a different priority; otherwise hold Bed for T2.
- T2 Day: mine Cave (+1S +1I). Play Sculk Catalyst (S1+R1). Now redstone
  ticks +1/turn. Save Cursed Bed for T3 — Bed deploy is fine through T3.
- T3 Day: Sculk Catalyst ticks +1R. Mine Hills (+1S). Play Allay Courier
  (R1 Worker). Worker_mine an unmined biome (Cave) → +1S +1I +1R.
- T4-5: deploy a Stalker (Shadow Crawler 3/1 W1+S1, Cave Crawler 4/2 W1+S1+I1).
  Start swinging at AI front structures. Equip Eldritch Bow when avatar
  has Worker support.
- T6-7: drop Cave Dweller (W2+I2+R1) on a clear column to start lethal pressure.
- T8-10: lethal. AI is at low HP from chip + Bow.

### No-bootstrap opening (no Strip Mine drawn)
- Auto-mulligan if rules permit. Without Strip Mine, the deck has only one
  source of redstone outside Allay Courier-via-Cave-mining, and the mid-range
  curve breaks.
- If rules don't permit mulligan: mine Cave aggressively for incidental
  iron+redstone, hold Cursed Bed for T2-3, deploy Lost Soul / Endermite
  Cluster / Lectern of Whispers as chip + draw, hope to topdeck Strip Mine
  by T6.

## Mulligan policy

- **Auto-mulligan**: hand with no Worker AND no Strip Mine AND no Cursed Bed.
  (Also: hand with 5+ cards costing ≥2 of any premium material — uncastable.)
- **Snap-keep**: Strip Mine + Cursed Bed + Worker + ≤2-cost stalker (Shadow
  Crawler, Lost Soul, Endermite Cluster).
- **Marginal keep**: Cursed Bed + Worker + draw card (Lectern of Whispers,
  Eldritch Altar) — bootstrap arrives via draw.
- **Priority order**: Worker > Strip Mine > Cursed Bed > Stalker > Removal > Gear.

## Anticipated weaknesses

1. **Redstone-economy single point of failure.** ~70% of removal +
   mid-curve cards (Drag to the Dark, Wither Skull, Whispering Curse,
   Goatman's Hex, Wither Skeleton, Sculk Stalker, Cave Dweller, Sculk
   Catalyst, Eldritch Altar, Stalker's Den, Soul Sand Trap, Endermite
   Cluster, Ratman, Eldritch Bow) require redstone. Only 4/60 cards
   (~6.7%) are redstone sources (2x Strip Mine, 2x Allay Courier).
   Without one in opener — or topdecked by T6 — the deck literally
   cannot interact. Treat redstone-source draw as Bed-equivalent
   in mulligan rules.

2. **Cheap turn-bonus structures (Soul Forge 4HP, Lectern 3HP, Sculk
   Catalyst 3HP) cannot survive an unprotected deploy turn into AI
   Wolf Pack / Creeper / weapon swings.** Iter-1 lost 2 such structures
   in back-to-back turns (Soul Forge T5, Lectern T7) — both ticked
   zero value before dying. Always deploy turn-bonus structures with
   either (a) same-turn front-row defender, (b) only in the Bed column
   (Bed forces AI to attack through the 4HP Bed first), or (c) behind
   a wall/block.

3. **No respawn redundancy.** Only 2 Cursed Beds (4HP each, the cheaper
   2HP variant). If both are destroyed the deck loses to AI weapon
   racing.

4. **Vulnerable to AoE.** With many 1/1 and 2/2 stalkers, Goatman's Hex
   from the opponent (or Warden ETB if AI plays it — but raider deck doesn't)
   would clear our board. Against `passive_econ raider` though, AoE isn't
   in their list, so this risk is low.

5. **No tribal payoff without redstone.** Both Stalker's Den (W1+S1+R1)
   and The Old Watcher (W1+S1+I1+R1) are redstone-gated. Even when the
   curve produces Stalkers (Shadow Crawler, Cave Crawler, Ratman), the
   lord effects come online only after the redstone bootstrap fires. If
   redstone is delayed, the tribal theme degrades to "vanilla 3/1 and 4/2
   Stalkers without buffs."

## Vs `passive_econ` raider specifically

`passive_econ` will:
- Stack Workers (worker_bonus_under_3=80, capped at 2 Workers).
- Equip a weapon by ~T5 only if a Bed is on board (weapon_no_bed_penalty=40 active).
- `chump_anything` block mode — pairs attackers with first-available blocker
  in declaration order, NOT highest-EV. **Multi-column attacks beat this.**
- Mine for stone primarily.

Box of Horrors counters:
- Multi-column stalker swings (Shadow Crawler col 0, Cave Crawler col 1,
  avatar Bow col 2) force the AI to commit its lone blocker to one
  attacker, leaving 2 unblocked hits.
- Goatman's Hex (1 dmg to all) erases AI Workers (1/2 Steve's Helper dies).
  After 2 Goatman's Hex resolutions, raider's Worker count is 0, and
  passive_econ falls into a no-economy loop.
- Wither rot (Wither Skeleton attacking) shrinks opponent mobs permanently;
  the chump_anything blockers slowly become 0/X non-threats.
- Cave Dweller's Climb defeats raider walls (if any deployed); Haste means
  it lands and swings same turn.

## Iteration log

### Iter 1 — 2026-05-07 (LOSS at T15 vs `passive_econ` raider)

**Outcome**: LOST. Final HP: ME=0 (dead at -2 on T15), AI=19. Total damage
dealt to AI = 1 chip (Sleep-Stealer ETB). AI won via sustained chip damage
(Zombie + Pillager + Alex's Scout + weapon) once Cursed Bed died T9.

**What worked**:
- T1 opening sequence (Strip Mine S1 → Cursed Bed W1 free via day-craft
  discount) was textbook. Got both redstone economy AND respawn protection
  on T1 simultaneously.
- Discovered the day-craft discount mechanic — Cursed Bed effectively free,
  Lectern W1 instead of W2, Soul Forge S1 instead of S2. This is now
  documented as a top-line strategy doc rule.
- Sleep-Stealer ETB (1 chip) was the only damage we dealt all game — but
  it confirmed the ETB chip works as expected.

**What didn't (deck-construction findings)**:
- **Redstone economy collapsed by T6.** Soul Forge died T5 (zero ticks).
  Lectern died T7 (zero ticks). Sculk Catalyst never castable. After T1
  Strip Mine spent the only redstone all game, T6-T15 was 100% redstone-
  starved with no Allay Courier, no second Strip Mine.
- **Redstone-economy single-point-of-failure confirmed.** With only 4/60
  redstone sources and ~70% of the deck redstone-gated, P(no redstone in
  ~10 draws) is high enough to be a recurring loss vector.
- **Defender layering didn't work** because front-row defenders died in 1
  turn. Sleep-Stealer (2/3) at y=2 took 4 dmg from Wolf Pack and died T9.
  No mid defender at y=1 → Wolf Pack killed front, then Zombie hit Bed in
  same combat.
- **Soul Forge and Lectern too fragile to deploy unprotected.** Both have
  3-4 HP and got destroyed the SAME TURN AI attacked, before ticking.
  Required: same-turn defender, Bed column, or behind a wall.

**Sections updated based on this iter**:
- Composition summary: noted post-patch composition (added Strip Mine,
  Allay Courier, Steve's Helper, Villager Mason; removed Elder Phantom
  D-cost card and other diamond cards). Total mid-range threats dropped
  from 8 to 6 cards.
- Mana / draw structures: added day-craft discount notes for each structure.
- Anticipated weaknesses: replaced "no diamond source" entry with
  "redstone-economy single-point-of-failure" entry; added new entries
  for "cheap turn-bonus structures fragile" and "no tribal payoff
  without redstone".

**Sections NOT changed (game did not contradict)**:
- Win condition (mid-range Horror grind via stalker chip + Cave Dweller).
  Game never reached the "post-bootstrap" state, so the win condition is
  untested but not contradicted.
- Mulligan policy structure. The auto-mulligan rule for "no Worker AND no
  Strip Mine AND no Cursed Bed" stands; iter 1 had Strip Mine + Bed in
  opener so the mulligan rule was not triggered.
- Vs `passive_econ` counters (multi-column swings, Goatman's Hex Worker
  clear, wither rot, Cave Dweller). All untested because we never assembled
  the mid-board to attempt them.

**Future iter 2 priorities**:
- Test if redstone-source redundancy via Eldritch Insight (cantrip R1) or
  cutting some redstone-gated cards for non-R cards would help — current
  build cannot recover from a single-Strip-Mine opener.
- Test the "deploy structure only in Bed column or behind defender" rule
  explicitly: T2 Sculk Catalyst should land in col 0 (Bed column), not in
  an undefended col 1 or col 2.
- Test if Eldritch Bow (W2+R1) is castable early enough to chip undefended
  AI col 0 / col 2 (the AI's confirmed weakness #6 — no proactive non-Bed
  Block deploy). Iter 1 never found redstone to cast it.
