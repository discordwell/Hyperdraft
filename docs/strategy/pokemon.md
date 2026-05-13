# Pokemon TCG — Strategy Doc

This file is the persistent strategic memory for Pokemon TCG (Hyperdraft
implementation, focused on the Beyond Ravnica spice pack v1 cards).
A fresh Claude instance piloting the format reads this BEFORE every
game and consults it during play. Update it whenever a game reveals
a non-obvious truth — write down WHAT and WHY, not just WHAT.

The doc is paired with `src/ai/pokemon/biases.py` (`POKEMON_BIAS_PRESETS`)
— when you find a blind spot in the heuristic AI, patch both: write the
lesson here AND tighten the relevant preset.

---

## Format fundamentals

### Resources

- **Prizes**: 6 per player. Take prizes by KO'ing opponent's Pokemon.
  Whoever takes their last prize first wins. Standard KOs give 1 prize;
  ex Pokemon give 2.
- **Energy**: Manually attached, 1 per turn. Different attacks need
  different types — Fire R, Water W, Grass G, Lightning L, Psychic P,
  Fighting F, Darkness D, Metal M, Fairy Y, Colorless C.
- **Hand**: 7 starting cards. Mulligan if you have 0 Basic Pokemon
  (opponent draws a card per mulligan).
- **Deck**: 60 cards. Decking out (drawing from empty deck) loses the
  game.

### Per-turn limits

- 1 energy attachment per turn (except via specific cards).
- 1 Supporter per turn.
- 1 Stadium per turn (replaces existing).
- Multiple Items per turn.
- 1 retreat per turn (paying the active's retreat cost in energy).
- 1 evolution per Pokemon (cannot evolve same turn the Pokemon hits play).

### Type chart (weakness / resistance)

- **Fire R** > Grass G
- **Grass G** > Water W, Lightning L
- **Water W** > Fire R, Fighting F
- **Lightning L** > Water W
- **Psychic P** > Fighting F
- **Fighting F** > Lightning L, Darkness D, Metal M, Colorless C
- **Darkness D** > Psychic P
- **Metal M** > Grass G

Weakness multiplies damage 2×; resistance reduces by 30.

### Status conditions (mutually exclusive — Pokemon's "Special Condition")

- **Asleep**: can't attack/retreat; flip heads at end of turn to wake.
- **Burned**: 2 damage counters + flip; tails for 1 more counter.
- **Confused**: flip heads to attack (tails: 30 damage to self, attack fails).
- **Paralyzed**: can't attack/retreat for one turn.
- **Poisoned**: 1 damage counter between turns; persists.

---

## BRV archetypes

Six bias presets ship with the BRV set, each tuned for a distinct
archetype. The LLM coach updates per-card multipliers per iteration.

### LZ Engine (`lz_engine`)

**Core cards**: Mirklet → Mirko Vosk · Jarlet → Jaradite → Jarad ex ·
Cremate · Sanguine Sacrament.

**Win condition**: Build a stack of own Pokemon in the Lost Zone (5+),
then KO opp Active with Jarad ex's Necrosurge (places 2 damage counters
per Pokemon in own LZ).

**Play pattern**:
1. T1–2: Bench Mirklet + Jarlet. Attach Psychic / Darkness energy to
   establish either threat.
2. T2–3: Play Cremate to send 2-3 Pokemon/Energy from hand to LZ. Each
   Cremate = +20 to +40 future Necrosurge damage.
3. T3–4: Evolve to Jaradite, then Jarad ex (via Rare Candy if available).
   Or evolve Mirklet → Mirko Vosk for the mid-game Lost Recall (mill +
   LZ feed combined).
4. T5+: Necrosurge with 4-5 LZ Pokemon = 80+40 to 80+100 damage. Wins
   prize trades.

**Key decision point**: When to commit to evolution. Stage 2 Jarad ex
locks in the archetype but costs a turn; sometimes a Mirko Vosk attack
on T4 with 2-3 LZ Pokemon is enough.

**Counter-archetypes**: Energy denial slows the {P}{D}{C} cost of
Necrosurge significantly. Hand disruption (Dimir Interrogation) can
yank our evolution line.

### Bench Swarm (`bench_swarm`)

**Core cards**: Borblet → Borborgrew → Aurelia ex · Sanguine Sacrament
· Pithing Drone.

**Win condition**: Fill bench with 3-5 Pokemon. Aurelia ex's Battalion
Mark places 1 damage counter per Benched Pokemon on opp Active — at
3 bench Pokemon, that's 30 chip per turn (low-cost {R}{F}). Mounts
pressure into Stage 2 KO range.

**Play pattern**:
1. T1: Bench 2 Basics. Pithing Drone onto Active.
2. T2: Bench 2 more Basics (4 total bench). Evolve where possible.
3. T3+: Aurelia ex hits play. Battalion Mark ticks 4 damage counters /
   turn into opp Active. Sanguine Sacrament saves any of these from KO
   by sacrificing a bench dud.

**Key decision point**: Don't over-commit bench (Niv-Mizzet's Quandary
or Boss-Orders KO us if 1-prize Pokemon stack up).

**Counter-archetypes**: AOE damage (rare in BRV but exists). Lost Zone
attacks that exile bench targets.

### Control / Disrupt (`control_disrupt`)

**Core cards**: Dimir Interrogation · Jace, Memory Adept · Niv-Mizzet's
Quandary · Tezzy's Test · Tox-Pawpsule.

**Win condition**: Strip opp hand and prevent opp from setting up.
Win on prize trades with Lazav ex (Stage 2 Dimir) or Obzedat ex
(Stage 2 Orzhov).

**Play pattern**:
1. T1–2: Build slowly; emphasize Trainer Items.
2. T3+: Dimir Interrogation (yank Pokemon from opp hand) and Jace's
   Mental Triage (discard opp Items) each turn. Tezzy's Test as a
   modal flex.
3. T5+: Niv-Mizzet's Quandary forces opp to switch a setup attacker
   off Active, then redistributes their energy elsewhere.

**Key decision point**: Tezzy's Test mode selection. Default heuristic:
mode 3 (disrupt) if opp hand has Trainer cards, mode 2 (tutor) if our
deck has Items we want, mode 1 (draw 3) otherwise.

**Counter-archetypes**: Aggro burn that ignores hand pressure and races
on damage.

### Energy Denial (`energy_denial`)

**Core cards**: Voidmage Apprentice · Pithing Drone · Niv-Mizzet's
Quandary · Tox-Pawpsule.

**Win condition**: Lock opp out of attacks by stripping their energy
attachments. While they fail to attack, we chip with cheap attackers
and close on prize math.

**Play pattern**:
1. T1: Voidmage to Active. Single energy attach.
2. T2+: Voidmage's Energy Drain (1 energy cost) discards 1 of opp's
   Active energy each turn. Cumulative — by T4, opp Active is bare.
3. Pithing Drone on a sticky Pokemon — when we lose it, opp loses all
   energy from the attacker.

**Key decision point**: When to retreat Voidmage out. If opp gets a
single hit through, the attack is lost; we want to retreat to bench
before opp KOs to preserve the engine.

**Counter-archetypes**: Decks with lots of attach cards (Iono refresh)
or Stage 2 evolution that doesn't care about energy stripping (rare).

### Aggro Burn (`aggro_burn`)

**Core cards**: Whichever Basic / Stage 1 attacker is fastest in deck.

**Win condition**: KO the first 4 opp Pokemon before opp sets up. Don't
bother with utility Trainers.

**Play pattern**: Aggressive Active commitment, ignore bench beyond
a single backup. Race prize math.

### Balanced (`balanced`)

Vanilla heuristic AI with no per-card multipliers. Used as control
matchup for new strategies and as the default when no archetype is
specified.

---

## Spice-card decision points

### Tezzy's Test (modal Supporter)

Choose 1 of 3 modes:

- **Mode 0 — Draw 3**: Default when hand is small (≤ 3 cards).
- **Mode 1 — Tutor Item**: Choose when we have evolution lines that
  want an Item (e.g., Rare Candy missing). Also strong when our deck
  is fat (probability of finding the right Item).
- **Mode 2 — Disrupt Trainer**: Opp reveals hand; pick a Trainer for
  them to shuffle back. Strong when opp hand has 4+ cards likely to
  include a Trainer.

**Heuristic AI default**: Mode 2 if opp has Trainers in hand, Mode 1 if
deck has Items, Mode 0 otherwise. LLM pilots can override per game state.

### Obzedat, Ghost Council ex — Spectral Decree (modal attack)

Choose 1 of 2 modes:

- **Mode A — KO Bench**: KO an opp Benched Pokemon with ≤ 30 HP. Strong
  late game when opp has low-HP setup Pokemon waiting on evolution.
- **Mode B — Prize Tax**: Opp takes 1 fewer Prize from their next KO
  against us. Strong when we're at risk of losing an ex (turning a
  2-prize loss into 1).

**Heuristic AI default**: Mode A if opp bench has a KO-eligible target,
else Mode B.

### Mirko Vosk's Lost Recall (build-around attack)

Look at top 4 of opp's deck, put 1 in Lost Zone, shuffle the rest back.
The "1 in LZ" choice is critical:

- **Prefer**: Opp's only copy of their Stage 2 evolution (high-impact
  removal).
- **Then**: Opp's last Energy of a specific type (if they're committed
  to a typed attacker).
- **Then**: Opp's Supporter (limits their future plays).
- **Default**: First Pokemon seen.

### Negate the Negation (build-around Item)

Useless unless opp has Tools attached. Hold in hand and don't play
until opp commits a Tool. When played:

- Discard all Tools on the chosen opp Pokemon.
- Per Tool discarded: opp reveals top card of deck; that card → Lost Zone.

**Heuristic AI**: Bias −100 when opp has no Tool. Once a Tool appears,
bias +40 plus +25 for each additional Tool.

---

## Common pitfalls

### Over-discarding into Cremate

Cremate moves up to 3 cards to the Lost Zone. The temptation is to
empty the hand for maximum LZ ramp. **Don't** — keep at least:

- 1 evolution piece if a Basic in play is waiting on it.
- 1 Supporter (we get 1/turn).
- 1 backup attacker (in case Active is KO'd).

### Wrong-time energy attachment

In LZ engine: Mirko Vosk's Lost Recall costs {P}{D}{C}. Splash the
energy types correctly — typically 8 Psychic + 5 Darkness. Don't
attach Darkness when Psychic is the bottleneck for Mirko's evolution
turn.

### Prize-trading into ex losses

ex Pokemon give 2 prizes when KO'd. Don't promote an ex Active when
opp can KO it next turn unless the trade is favorable (we KO their ex
back). Sanguine Sacrament can dodge an ex KO by sacrificing the ex to
Lost Zone (no prizes given — Pokemon in LZ don't count for prize math).

### Tezzy's Test wasted

Default Mode 0 (Draw 3) is the LOWEST EV mode in most game states.
Always check first:
1. Is opp's hand revealed-Trainer-rich? → Mode 2.
2. Is our deck fat AND we want a specific Item? → Mode 1.
3. Otherwise → Mode 0.

### Pithing Drone on the wrong attacker

The Tool only fires when its holder is KO'd by an attack. Putting it
on a bench Pokemon that won't get KO'd anytime soon wastes the slot.
Default: attach to Active when it's an ex (high-value target).

---

## Update log

This section is appended by LLM coaches after each iteration of
`/ultra-loop`. Each entry: date, matchup, key finding, preset patch
applied.

(no entries yet — Phase 4 will populate this)
