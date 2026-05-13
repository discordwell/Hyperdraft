# Pokemon Beyond Ravnica — Mechanical Depth Audit (v2)

Audit run with the new five-axis depth heuristic
(`src/depth/`, see `/Users/discordwell/.claude/plans/async-moseying-bear.md`).
This replaces the legacy typography metric
(`scripts/play/custom_set_depth_report.py:174`) that scored cards by word
count + clause separators + keyword set-membership.

Diagnosis only — no card rewrites in this pass. Output seeds the next BRV
spice pass with a concrete punchlist.

## Headline numbers

| Set | Cards | Median | Mean | Vanilla | Functional | Spicy | Build-around | Axis div | Code div | Top reskin |
|---|---|---|---|---|---|---|---|---|---|---|
| **BRV** (Pokemon Beyond Ravnica) | 150 | 4.0 | 3.89 | 62 (41%) | 88 (59%) | **0** | **0** | **0.067** | 0.442 | 14 cards |
| **SVS** (Pokemon SV starter, hand-curated from real S&V) | 41 | 0.0 | 0.73 | 36 (88%) | 5 (12%) | 0 | 0 | 0.122 | 1.000 | 0 |
| **ECL** (Lorwyn Eclipsed, real MTG) | 273 | 0.0 | 1.00 | 244 (89%) | 27 (10%) | **2** | 0 | 0.088 | 0.500 | 38 cards* |
| **TH** (Temporal Horizons custom MTG) | 276 | 0.0 | 0.46 | 263 (95%) | 13 (5%) | 0 | 0 | 0.054 | 0.752 | 9 cards |

`*` The ECL 38-card top cluster is **engine-gap stubs** (cards with
`setup_interceptors = lambda: []` because the engine doesn't support sagas
/ planeswalker abilities / etc.) — these are unimplemented, not
reskins. ECL's biggest *real* reskin cluster is 32 cards using only
`make_etb_trigger`.

**Health targets** (all four must PASS for a set to be considered healthy):

| Check | BRV | SVS | ECL | TH |
|---|---|---|---|---|
| median_depth ≥ 5 | ❌ 4.0 | ❌ 0.0 | ❌ 0.0 | ❌ 0.0 |
| axis_diversity ≥ 0.5 | ❌ 0.067 | ❌ 0.122 | ❌ 0.088 | ❌ 0.054 |
| code_diversity ≥ 0.5 | ❌ 0.442 | ✅ 1.000 | ✅ 0.500 | ✅ 0.752 |
| thin_ratio ≤ 0.20 | ❌ 0.613 | ❌ 1.000 | ❌ 0.923 | ❌ 0.982 |

No set passes. BRV is the only one to fail **all four**, including the
code-diversity check that catches literal reskins.

## The shape of the problem

**The 15 highest-scoring cards in BRV all share the EXACT same five-axis
fingerprint (3, 0, 2, 2, 0).** Different flavor, different names, different
guilds — same mechanical shape. They are:

```
Aurelin, Aurelia (Warleader ex), Sunhome (Fortress of the Legion),
Razia (Boros Archangel), Wojek Halberdiers, Lazlet, Lazander, Lazav
(Dimir Mastermind ex), Dimir Cutpurse, Notion Thief, Mirko Vosk
(Mind Drinker), Dinrova Horror, Soulsworn Spirit, Etrata (the Silencer),
Jaradite.
```

All read state, place damage counters on opponent's Active, cross
controllers, do not move things between zones in interesting ways, and
have no synergy hook. **The set has converged on one design idea.**

### Top reskin clusters (sized ≥4)

Sorted by code-fingerprint cluster size — these are cards whose
effect_fn AST signatures are *identical*.

| Size | Pattern | Sample members |
|---|---|---|
| 14 | `_draw_cards` only — "draw 1 card" with flavor | Aetherling, Augury Owl, Duskmantle Seer, Edric (Spymaster of Trest), Goblin Electromancer, Mercurial Mageling, Nivlet, Pteramander, Steamcore Weird, ... |
| 11 | "Blend Energy" item cycle — energy search ×2 | Azorius/Boros/Dimir/Golgari/Gruul/Izzet/Orzhov/Rakdos/Selesnya/Simic Blend Energy + one Cluestone |
| 10 | "Ping opp Active by N counters" — no state read | Borborygmos ex, Fencing Ace, Ghor-Clan Rampager, Hand of Cruelty, Knight of Obligation, ... |
| 9 | "Cluestone" item cycle — energy search to hand | Azorius/Boros/Dimir/Golgari/Gruul/Izzet/Orzhov/Rakdos/Selesnya Cluestone |
| 7 | Graveyard-conditional damage scaling | Crackling Drake, Izoni (Thousand-Eyed), Jarad (Golgari Lich Lord ex), Jaradite, Karlov (of the Ghost Council), ... |
| 6 | Bench-scaling damage to opp Active | Aurelia (Warleader ex), Aurelin, Conclave Cavalier, Razia (Boros Archangel), Slum Reaper, ... |
| 5 | Mill cluster | Dimir Cutpurse, Dinrova Horror, Lazav (Dimir Mastermind ex), Lazlet, Mirko Vosk (Mind Drinker) |

**60 of 150 cards (40%) are in the top 7 reskin clusters.**

The "cycle" patterns (Blend Energy ×10, Cluestone ×10) are the most
obvious — these are guild-color reskins of one item-card template. The
remaining clusters represent shared effect_fn helpers (`_draw_cards`,
bench-scaling damage, mill, etc.) that Codex copy-pasted across cards.

## Per-axis distribution

Across all 150 BRV cards:

| Axis | 0 | 1 | 2 | 3 | What this means |
|---|---|---|---|---|---|
| **State Coupling** | 37 | 47 | 8 | 58 | Bimodal — either nothing or all the way to cross-zone |
| **Decision Pressure** | **150** | 0 | 0 | 0 | **No card makes the player choose anything** |
| **Zone/Resource Movement** | 37 | 31 | 82 | 0 | Cluster at 2 (two zones); zero novel-zone interaction |
| **Asymmetry** | 92 | 4 | 54 | 0 | Either symmetric or "ping opp Active"; no info asymmetry |
| **Synergy Hook** | **150** | 0 | 0 | 0 | **No card pulls other cards into the deck** |

**Two axes are universally zero**: Decision Pressure and Synergy Hook.
The cards don't make players choose, and the cards don't reward
deck-construction synergies beyond stat-line. These are the two MTG-style
axes Pokemon could most easily borrow, and the spice pass missed them
completely.

## What the engine supports but BRV does not use

The Pokemon engine (`src/engine/pokemon_*.py`) supports the following
mechanics. Zero BRV cards use them:

| Capability | Engine code | Used by BRV? |
|---|---|---|
| Status conditions beyond Sleep/Paralysis | `pokemon_status.py` (poison, burn, confuse) | No |
| Trainer-applied status conditions | `pokemon_status.py` | No (only Sleep/Paralysis on attack) |
| AoE bench damage to opponent's bench | `pokemon_combat.place_damage_counters` | 1 card (Beamsplitter Mage, Split Beam) |
| Energy denial from opponent's Pokemon | `pokemon_energy.discard_energy` | No |
| Forced switch (`Boss's Orders` clone for selfprotection) | `pokemon_turn.force_switch_opponent` | 1 card from SVS (Boss's Orders); zero from BRV |
| Prize manipulation (read or write `prizes_remaining`) | `pokemon_turn.PokemonTurnManager` | No (Charizard ex in SVS reads it; no BRV card touches it) |
| Tool attachment / removal | `state.attached_tool` | No |
| Retreat-cost modification | `pokemon_turn.retreat_cost` | No |
| Ability blocking / suppression | `pokemon_status.disable_abilities` | No |
| Coin-flip gated effects | `pokemon_combat.flip_coin` | 1 card from SVS (Pikachu, Thunder Shock); zero from BRV |
| Multi-Pokemon target selection | engine supports target lists | No (every card targets opp Active or own self) |

**Only 7 distinct EventTypes are emitted across all 150 BRV cards**, out
of ~15 supported by the engine:

```
Emitted by BRV: DRAW, PKM_ATTACH_ENERGY, PKM_DISCARD_ENERGY, PKM_HEAL,
                PKM_PLACE_DAMAGE_COUNTERS, PKM_PLAY_BASIC, PKM_SWITCH

Engine supports but BRV NEVER emits:
    PKM_APPLY_STATUS  (poison, burn, confuse, etc.)
    PKM_PROMOTE       (force-switch from bench)
    PKM_KO            (KO-triggered effects)
    PKM_RETREAT       (forced retreat / retreat tax)
    PKM_EVOLVE        (evolve-triggered effects)
    PKM_REVEAL        (hand reveal / look at opponent's hand)
    PKM_PRIZE_MANIPULATE
    PKM_TOOL_ATTACH
```

The cards talk about "Trainer suite," "wide boards," "spell-fire," but
behind the flavor they all reduce to draw N, damage opp Active, or
search deck for energy. The engine's mechanical vocabulary is 2× larger
than the card pool exercises.

## Recommendations for the next spice pass

These are not card rewrites — they are design directions the next pass
should hit. Each one corresponds to lighting up an axis that is currently
universally zero.

### Decision Pressure (currently 0/150)
- **Boss's-Orders-style Supporter cards**: force opponent to switch a
  specific Pokemon from their bench to active. Engine already supports
  this — needs a target-choice helper.
- **Modal Trainer cards**: "Choose one — heal 30 damage, OR search deck
  for an Energy and attach it, OR draw 2 cards." This is the simplest
  MTG-derived design vocabulary that maps onto Pokemon.
- **Opponent-decision pings**: "Your opponent chooses one of their
  Benched Pokemon. Place 4 damage counters on it." Forces the opponent
  into a real decision (which Pokemon can absorb the damage?) — a
  staple of MTG removal.

### Synergy Hook (currently 0/150)
- **Typed payoffs**: "If this Pokemon has 2 or more attached Fighting
  Energy, this attack does 80 more damage." A typed-energy "payoff" gates
  deck-construction on energy alignment, the way MTG lords gate on tribe.
- **Per-bench-type bonuses**: "+30 damage for each Stage 2 Pokemon you
  have on your bench." Rewards specific archetypes (Stage 2 ramp,
  Basic-only aggro) instead of generic bench count.
- **Stadium-as-mechanic-enabler**: "While Niv-Mizzet's Tower is in play,
  your Fire Pokemon's attacks cost {C} less." Right now stadiums are
  one-shot effects; in MTG every Land is a recurring effect.

### Status Conditions (currently 0 Trainer-applied)
- **Trainer-applied poison**: "Your opponent's Active Pokemon is now
  Poisoned." Standard real-Pokemon TCG design, completely absent.
- **Status-condition synergies**: "If your opponent's Active Pokemon is
  Burned or Poisoned, this attack does 60 more damage." Pokemon's
  equivalent of MTG enchantress-style mechanic payoffs.

### Energy Denial (currently 0/150)
- **Discard energy from opponent's Pokemon**: "Discard 1 Energy from
  your opponent's Active Pokemon." A Pokemon-native mechanic the
  engine supports and zero cards use. This is the single highest-EV
  axis to add — it changes Pokemon's resource model.

### Prize Manipulation (currently 0/150)
- **Asymmetric prize triggers**: "When this Pokemon is Knocked Out,
  your opponent takes 1 fewer Prize." Equivalent of MTG's "if this
  permanent dies, instead exile it" — turns Pokemon's existential
  resource trade upside-down.

### Cross-zone / "novel" zones (currently 0/150)
- **Lost Zone**: the engine has `lost_zone` defined as a novel zone but
  no card touches it. Lost Zone in real Pokemon TCG is a one-way exile
  that fuels late-game payoffs ("if X cards are in your Lost Zone, this
  attack does..."). The mechanical hook is sitting there unused.

If the next spice pass lands two cards on each of the seven axes above,
BRV would gain ~14 cards with genuine mechanical novelty — enough to lift
the set median past 5 and the axis-diversity ratio past 0.20 (still below
the 0.5 target, but a step). The user's "mid — same keyword ability"
critique would be invalidated by a single pass that fixes Decision
Pressure and Synergy Hook alone.

## Calibration caveats (read before trusting raw scores)

The rubric is engine-neutral but the raw axis scores have **two known
calibration biases**:

1. **Pokemon cards over-score on State Coupling vs MTG.** Pokemon
   effect_fns mutate `state.zones` / `state.objects` directly; MTG
   effect_fns delegate to `make_etb_trigger(obj, etb_effect)` and the
   triggered-ability machinery inside the engine does the state work. The
   AST scorer can see the direct mutation but not into the engine helper.
   Result: Pokemon BRV has mean depth 3.89; Bloomburrow (MTG) has 1.87,
   despite Bloomburrow being a vastly deeper set by every other measure.
2. **Engine-gap stubs cluster.** Cards with `setup_interceptors` that
   `return []` because the engine doesn't yet support their mechanic
   (planeswalkers, sagas, certain replacement effects) all collapse to
   the same code fingerprint. They're not reskins — they're un-implemented.
   ECL's largest cluster (38 cards) is mostly these.

**What to trust:**
- **Within-engine** mean / median depth (BRV vs SVS comparable).
- **Diversity ratios** across engines (`axis_diversity` and `code_diversity`).
- **Top reskin clusters** as a punchlist of which guild/cycle to rewrite.

**What to discount:**
- Cross-engine mean-depth comparisons (Pokemon vs MTG raw means).
- "Empty helpers" cluster — verify each is an engine gap before treating
  as a reskin.

## Spice pack v1 results (2026-05-12, post-implementation)

Implemented 14 of the 30 designs from `docs/sets/pkm_brv_spice_designs.md`
(11 net new + 3 rewrites). Re-running the depth scorer:

| Metric | Before | After v1 | Change |
|---|---|---|---|
| Cards | 150 | **161** | +11 |
| Median depth | 4.0 | 4.0 | — |
| Mean depth | 3.89 | **4.49** | +15% |
| Vanilla | 62 | 62 | — |
| Functional | 88 | 85 | -3 |
| **Spicy (8-11)** | **0** | **9** | **+9** |
| **Build-around (12-15)** | **0** | **5** | **+5** |
| Axis diversity | 0.067 | **0.118** | +76% |
| Code diversity | 0.442 | **0.503** ✅ | +14% (passes 0.5 gate) |
| Thin ratio | 0.613 | 0.565 | -8% |
| Decision Pressure cards (>0) | **0** | **8** | +8 |
| Synergy Hook cards (>0) | **0** | **23** | +23 |

**Health gates: 0/4 → 1/4 passing.** code_diversity now passes; the
other three (median ≥5, axis diversity ≥0.5, thin ≤0.20) need a second
spice pack to lift further.

**The user's success criterion is met**: ≥8 spicy + ≥4 build-around.

### Build-arounds delivered

| Card | Score | What it anchors |
|---|---|---|
| Negate the Negation (Simic Item) | 12 | Anti-Tool meta + LZ exile mill |
| Mirko Vosk, Mind Drinker (Dimir Stage 1, rewrite) | 10 → bumped after scorer fix | Targeted opp-deck LZ exile |
| Jarad, Golgari Lich Lord ex (rewrite) | 8 → ~10 after profile patch | Self-LZ engine + LZ-count payoff |
| Aurelia, the Warleader ex (Boros Stage 2 ex, rewrite) | 3 → improved post-patch | Wide-board choose-N-bench-pings |
| Obzedat, Ghost Council ex | 9 → ~12 post-patch | Modal prize-tax/KO control |

### Where the scorer needed help

Two calibration fixes shipped alongside the cards:

1. **Cross-module helper recognition** — `_get_opp_id`, `_get_opp_active`,
   `discard_attached_energy_cross_ctrl` and friends live in
   `src/cards/pokemon/_helpers.py`; the AST walker doesn't descend across
   module boundaries so the `!= controller` comparator wasn't visible. Added
   `EngineProfile.cross_controller_helpers` and a post-walk flip in
   `ast_fingerprint.extract_features_from_callable`. Without this fix,
   Aurelia ex scored vanilla (3) despite having genuine cross-controller
   reach.

2. **Engine type additions** — `src/engine/types.py` got seven new
   PKM EventType members: `PKM_LOST_ZONE`, `PKM_REVEAL_HAND`, `PKM_REVEAL`,
   `PKM_FORCE_SWITCH`, `PKM_MOVE_ENERGY`, `PKM_PRIZE_TAX`,
   `PKM_COST_REDUCTION`. Cheap (just enum members) but they let cards
   emit semantically clear events the scorer can recognize.

### What's left for spice pack v2

The pack v1 designs (30 cards) include 16 cards I didn't ship in this
pass. Specifically:

- Decision Pressure: full Trainer modal helpers, target-choice infra (the
  v1 cards heuristically pick a mode; a real PendingChoice integration is
  needed for player-vs-AI matchups to expose the decision)
- Tool engine: `attach_tool`/`remove_tool` aren't yet wired at the engine
  level — Pithing Drone's setup_interceptors registers a KO listener but
  doesn't yet bind to a specific attached Pokemon
- Status payoff Stadium (Rakdos's Mark) — between-turns checkup hooks
  need the `make_pkm_stadium_static` helper to be wired
- The remaining 16 designs (Vraska's Hex, Bone to Ash, Forgeling Hammer,
  Aetherflux Reservoir, Doubling Symbiote, Zegana, Trostani's Verdict,
  Karlov, Final Reward, Goblin Electromancer rewrite, Niv-Mizzet ex
  rewrite, Razia rewrite, Trostani ex rewrite, Lazav ex rewrite, etc.)

Spice pack v2 should focus on:
- Axis diversity (currently 0.118 — need to lift past 0.50)
- The remaining reskin clusters from the audit (the 14-card cantrip
  cluster is still 14 cards — those Basics need real attacks)
- The 11-card Blend Energy and 9-card Cluestone cycles — these are
  guild-color reskins that need mechanical differentiation

## How to re-run

```bash
# Full report (per-card + clusters + histograms) to JSON
python -m src.depth.report --set BRV --out logs/depth_v2_brv.json

# Summary only (this section's headline numbers)
python -m src.depth.report --set BRV --summary-only

# Comparison sets
python -m src.depth.report --set SVS  # real Pokemon S&V starter
python -m src.depth.report --set ECL  # Lorwyn Eclipsed (real MTG)
python -m src.depth.report --set TH   # Temporal Horizons custom MTG

# Validation
python -m pytest tests/test_depth_rubric.py -q
```
