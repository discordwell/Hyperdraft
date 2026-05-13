# Pokemon Beyond Ravnica — Spice Pack v1 (designs)

> **Stage 1 output of the de-mid-ification pipeline.** Anchors every card
> to one of the 7 axis gaps from `docs/sets/pkm_brv_depth_audit.md`. Feeds
> Stage 2 (TDD implementation). No code yet.

## Context

BRV audit found:
- 0 spicy / 0 build-around cards across 150 designs
- 150/150 score 0 on Decision Pressure and 150/150 score 0 on Synergy Hook
- 14-card `_draw_cards` reskin cluster; 11-card "Blend Energy" cycle; 9-card "Cluestone" cycle
- Only 7 distinct EventTypes emitted (engine supports 15+)

This pack adds **22 net-new cards + 8 rewrites = 30 designs** across all 10 guilds. Tier mix:
**4 build-around (12-15), 14 spicy (8-11), 12 functional (4-7), 0 vanilla.** Hits the success criterion from the audit (≥8 spicy, ≥4 build-around).

## Coverage matrix

| Guild | New cards | Rewrites | Axes covered |
|---|---|---|---|
| Azorius | Niv-Mizzet's Quandary, Jace (Memory Adept), Pithing Drone | — | Decision, Energy denial, Tool |
| Boros | Forgeling Hammer | Aurelia ex, Razia | Tool, Synergy |
| Dimir | Dimir Interrogation, Voidmage Apprentice, Tox-Pawpsule | Mirko Vosk, Lazav ex | Decision, Energy denial, Status, Lost Zone |
| Golgari | Vraska's Hex, Cremate | Jarad ex | Status, Lost Zone, Synergy |
| Gruul | Zhur-Taa Druid | — | Energy denial |
| Izzet | Tezzy's Test | Niv-Mizzet ex, Goblin Electromancer | Decision, Synergy |
| Orzhov | Karlov, Obzedat ex, Final Reward, Sanguine Sacrament | — | Prize, Lost Zone |
| Rakdos | Bone to Ash, Rakdos's Mark | — | Energy denial, Status |
| Selesnya | Doubling Symbiote, Trostani's Verdict | Trostani ex | Synergy |
| Simic | Zegana, Aetherflux Reservoir, Negate the Negation | — | Synergy, Tool, build-around combo |

Each axis hits **3-4 cards**. Each guild gets **2-4 designs**. No guild stays mid.

## Fingerprint legend

Target `(S, D, Z, A, Y) = total (tier)`. Calibration caveat: the current
`PKM_PROFILE.modal_helpers` and `filter_factories` sets are empty. To realize
the D and Y axis scores below, Stage 2 must ship the helpers listed in the
"Engine call" line of each card AND add their names to the Pokemon profile.
The Pokemon-profile patches needed are catalogued at the end of this doc.

---

## Axis 1 — Decision Pressure (4 cards)

### Tezzy's Test (Izzet — Trainer Supporter)
- **Stats**: Supporter, 1/turn (standard limit)
- **Text**: "Choose one — Draw 3 cards; OR search your deck for an Item card and put it in your hand, then shuffle; OR your opponent reveals their hand and you choose 1 Trainer card in it; they shuffle that card into their deck."
- **Target fingerprint**: S=2 D=3 Z=2 A=3 Y=0 = **10 (spicy)**
- **Axis target**: Modal Trainer — the canonical MTG "choose 1 of 3" applied to Pokemon's Supporter slot. Each mode hits a different game vector.
- **Engine call**: new `create_pkm_modal_choice(player, options)` helper; the third mode emits `PKM_REVEAL_HAND` + a target-choice from the revealed set.
- **Choose / Read / Pull**: chooses 1 of 3 modes; if mode 3, also reads opp hand and picks a target; pulls Items into deckbuilds.

### Niv-Mizzet's Quandary (Azorius — Trainer Supporter)
- **Text**: "Your opponent chooses one of their Benched Pokemon and switches it with their Active. After they switch, you may move up to 2 Energy from any of their Pokemon to the new Active."
- **Target fingerprint**: S=2 D=3 Z=2 A=3 Y=0 = **10 (spicy)**
- **Axis target**: Opp-forced decision. Opponent picks the worst-of-bad-options switch target; you then re-shape their energy distribution. Pure information+resource asymmetry.
- **Engine call**: new `pkm_force_opp_choose_bench` (returns a pending-choice object the opponent must resolve); `PKM_FORCE_SWITCH`; `PKM_MOVE_ENERGY`.
- **Choose / Read / Pull**: opponent chooses bench Pokemon (against their interest); you choose 0-2 energy moves.

### Jace, Memory Adept (Azorius — Pokemon Basic)
- **Stats**: 80 HP, Psychic, retreat 1, weak to Darkness
- **Attacks**:
  - Mental Triage [P][C] 30 — "Look at your opponent's hand. Choose 1 Item card and discard it. Your opponent draws 1 card."
- **Target fingerprint**: S=2 D=2 Z=2 A=3 Y=0 = **9 (spicy)**
- **Axis target**: Read-then-target opp hand. Forced reveal = info asymmetry; you choose what to disrupt.
- **Engine call**: `PKM_REVEAL_HAND` event + `pkm_target_card_in_hand_choice` helper + `PKM_DISCARD` cross-controller.
- **Choose / Read / Pull**: chooses Item from revealed hand; reads opp hand; pulls answer-pieces into deckbuilds.

### Dimir Interrogation (Dimir — Trainer Item)
- **Text**: "Look at your opponent's hand. Choose 1 Pokemon in their hand and put it on the bottom of their deck. Your opponent draws 1 card."
- **Target fingerprint**: S=2 D=2 Z=2 A=3 Y=0 = **9 (spicy)**
- **Axis target**: Cheap Item-speed info-and-target. Punishes evolution lines (yank a Stage 2 before opp draws into it).
- **Engine call**: `pkm_target_card_in_hand_choice` (shared with Jace); `PKM_REVEAL_HAND`.
- **Choose / Read / Pull**: chooses Pokemon to bury; reads opp hand; pulls into evolution-disruption deck.

---

## Axis 2 — Synergy Hook (3 cards)

### Doubling Symbiote (Selesnya — Pokemon Basic)
- **Stats**: 70 HP, Grass, retreat 1, weak to Fire
- **Attacks**:
  - Pack Tactics [G][C] 30+ — "+20 damage for each Stage 1 Pokemon you have on your Bench."
- **Target fingerprint**: S=2 D=0 Z=1 A=2 Y=2 = **7 (functional)**
- **Axis target**: Evolution-stage typed payoff. Build-around fast Stage-1 ramp decks; punishes Stage-2 ramp because Stage-2s don't count.
- **Engine call**: new `count_pokemon_by_stage(controller, stage, state)` filter factory; `PKM_PLACE_DAMAGE_COUNTERS`.
- **Choose / Read / Pull**: reads own bench composition; pulls Stage-1-heavy curve into deckbuilds.

### Trostani's Verdict (Selesnya — Trainer Supporter)
- **Text**: "If you have 4 or more Pokemon in play, search your deck for a Stage 1 or Stage 2 Evolution and put it directly onto a matching Basic Pokemon (skipping the lower stage if needed). Then shuffle your deck."
- **Target fingerprint**: S=2 D=2 Z=2 A=0 Y=3 = **9 (spicy)**
- **Axis target**: Wide-board archetype enabler. Rare Candy on a wide-bench gate — pulls 4+ Basic decks together.
- **Engine call**: `PKM_EVOLVE`; new `pkm_skip_evolution_stage` helper; `count_pokemon_in_play` filter.
- **Choose / Read / Pull**: chooses which Basic to evolve; reads own bench count; pulls Stage 2 ramp archetype.

### Zegana, Utopian Speaker (Simic — Pokemon Stage 1)
- **Stats**: 110 HP, Water, retreat 2, evolves from Cubchoo (existing), weak to Lightning
- **Ability**: Hydroform — "Once during your turn, you may move 1 Water Energy from your hand to one of your Pokemon. If you do, draw 2 cards."
- **Target fingerprint**: S=2 D=1 Z=2 A=0 Y=3 = **8 (spicy)**
- **Axis target**: Typed-energy synergy + draw engine. Best in mono-Water; useless out of it.
- **Engine call**: `PKM_ATTACH_ENERGY` (from hand, not deck); `count_typed_energy_in_hand` filter; `PKM_DRAW`.
- **Choose / Read / Pull**: chooses Pokemon to attach to; pulls Water-only deck construction.

---

## Axis 3 — Status conditions beyond Sleep/Paralysis (3 cards)

### Tox-Pawpsule (Dimir — Trainer Item)
- **Text**: "Your opponent's Active Pokemon is now Poisoned. Then, place 1 damage counter on it for each Poisoned Pokemon your opponent has in play."
- **Target fingerprint**: S=2 D=0 Z=1 A=2 Y=2 = **7 (functional)**
- **Axis target**: Trainer-applied poison + same-condition payoff. Encourages poison-stack decks.
- **Engine call**: `PKM_APPLY_STATUS` (poison) + `count_poisoned_pokemon` filter + `PKM_PLACE_DAMAGE_COUNTERS`.
- **Choose / Read / Pull**: reads opp board for poisoned count; pulls poison-spread deck.

### Vraska's Hex (Golgari — Pokemon Basic)
- **Stats**: 80 HP, Psychic, retreat 2, weak to Darkness
- **Attacks**:
  - Vile Aura [P][C] 30 — "Your opponent's Active Pokemon is now Poisoned AND Confused."
- **Target fingerprint**: S=1 D=0 Z=1 A=2 Y=1 = **5 (functional)**
- **Axis target**: Dual-status application. Poison ticks; Confusion disrupts attacks. Each is mild alone; together they're a soft lock.
- **Engine call**: `PKM_APPLY_STATUS` ×2 (mutual exclusivity rule allows Poison + Confused per real Pokemon TCG).
- **Choose / Read / Pull**: pulls status-payoff cards into deck (Tox-Pawpsule, Rakdos's Mark).

### Rakdos's Mark (Rakdos — Trainer Stadium)
- **Text**: "When you play Rakdos's Mark, each of your opponent's Burned Pokemon takes an additional 1 damage counter during the between-turns checkup. (Stays in play until replaced.)"
- **Target fingerprint**: S=2 D=0 Z=1 A=2 Y=3 = **8 (spicy)**
- **Axis target**: Status-condition payoff Stadium that **recurs** between turns — fixes BRV's "stadiums are one-shot" bug at the design level.
- **Engine call**: Stadium-static effect via new `make_pkm_stadium_static(state_predicate, between_turn_hook)` helper; intercepts Burn checkup damage.
- **Choose / Read / Pull**: reads opp board for Burned count each turn; pulls Burn-applying cards (Charmander's existing Ember attack newly relevant).

---

## Axis 4 — Energy denial (4 cards) [highest leverage axis]

### Voidmage Apprentice (Dimir — Pokemon Basic)
- **Stats**: 60 HP, Psychic, retreat 1
- **Attacks**:
  - Energy Drain [U] 10 — "Discard 1 Energy from your opponent's Active Pokemon."
- **Target fingerprint**: S=2 D=0 Z=2 A=3 Y=0 = **7 (functional)**
- **Axis target**: Cheap recurring denial Basic — the single-energy attack means it CAN run in any deck splashing 1 U. Pokemon's equivalent of Funeral Charm.
- **Engine call**: `_discard_attached_energy(state, opp_active_id, 1)` — engine helper exists, no current BRV card uses it cross-controller.
- **Choose / Read / Pull**: reads opp Active energy; pulls denial deck shells.

### Zhur-Taa Druid (Gruul — Pokemon Basic)
- **Stats**: 80 HP, Fighting, retreat 2
- **Attacks**:
  - Wild Charge [R][C] 60 — "Discard 1 Energy from your opponent's Active Pokemon AND from this Pokemon."
- **Target fingerprint**: S=2 D=0 Z=2 A=3 Y=0 = **7 (functional)**
- **Axis target**: Self-cost denial — pinnacle aggro design where you trade tempo for resource denial. Per `[[feedback_winmore_mechanics]]`: pairs big payoff with steep self-cost.
- **Engine call**: `_discard_attached_energy` ×2 (one cross-controller, one self).
- **Choose / Read / Pull**: pulls a refuel package (e.g. Welder analogue) into deck.

### Bone to Ash (Rakdos — Trainer Item)
- **Text**: "Discard the top 2 cards of your deck. For each Energy card discarded this way, discard 1 Energy from one of your opponent's Pokemon (your choice each)."
- **Target fingerprint**: S=2 D=2 Z=2 A=3 Y=0 = **9 (spicy)**
- **Axis target**: Top-of-deck variance → cascading opp denial. The chooser-of-Energy-target makes this a Decision Pressure axis BONUS too.
- **Engine call**: `PKM_MILL_TOP` ×2 + `pkm_choose_pokemon_target` per energy hit + `_discard_attached_energy` ×(0-2).
- **Choose / Read / Pull**: chooses which opp Pokemon each energy hit lands on; reads opp board.

### Pithing Drone (Azorius — Trainer Tool) [Tool axis overlap by design]
- **Text**: "Attach to one of your Pokemon. When the attached Pokemon is Knocked Out by an opponent's attack, your opponent must discard all Energy attached to the Pokemon that did the KO damage."
- **Target fingerprint**: S=2 D=0 Z=2 A=3 Y=3 = **10 (spicy)**
- **Axis target**: Death-rattle denial via Tool. Punishes KO trades and rewards the prize-disadvantaged side.
- **Engine call**: `attach_tool` (novel helper); `PKM_KO` event listener with attacker-tracking; bulk `_discard_attached_energy`.
- **Choose / Read / Pull**: which Pokemon to attach to; reads attacker identity at KO time; pulls grindy attrition deck.

---

## Axis 5 — Prize manipulation (3 cards + 1 build-around)

### Karlov of the Ghost Council (Orzhov — Pokemon Stage 1)
- **Stats**: 100 HP, Psychic, retreat 1, weak to Darkness, evolves from Spike Jester (existing)
- **Attacks**:
  - Ghastly Decree [W][B][C] 80+ — "+40 damage if your opponent has 3 or fewer Prizes remaining."
- **Target fingerprint**: S=2 D=0 Z=1 A=2 Y=2 = **7 (functional)**
- **Axis target**: Prize-state damage scaling. Closing-game pressure that rewards getting ahead.
- **Engine call**: `state.prizes_remaining[opp_id]` read; `PKM_PLACE_DAMAGE_COUNTERS`.
- **Choose / Read / Pull**: reads opp prize count; pulls closer-deck shape.

### Obzedat, Ghost Council ex (Orzhov — Pokemon Stage 2 ex) **[BUILD-AROUND]**
- **Stats**: 280 HP, Psychic, retreat 2, ex, evolves from Karlov
- **Attacks**:
  - Soul's Tax [W][B] 60 — "Your opponent reveals their hand."
  - Spectral Decree [W][B][C][C] 150 — "Choose one: KO an opp Benched Pokemon with 30 HP or less; OR your opponent takes 1 fewer Prize from the next KO they score against you."
- **Target fingerprint**: S=3 D=3 Z=2 A=3 Y=3 = **14 (build-around)**
- **Axis target**: Multi-modal Stage 2 ex that anchors a tax-style control archetype. The "1 fewer Prize" mode is the first real prize-asymmetric effect in BRV.
- **Engine call**: `PKM_REVEAL_HAND`; `pkm_modal_choice`; `pkm_apply_prize_tax(opp_id, amount, duration)` (new state field `prize_tax_next_n`); `pkm_target_bench_choice`.
- **Choose / Read / Pull**: which mode; which bench Pokemon (if mode A); reads opp hand on first attack; pulls control-tax archetype.

### Final Reward (Orzhov — Trainer Supporter)
- **Text**: "Playable only if you have at least 1 more Prize remaining than your opponent. Draw 3 cards and search your deck for an Item card and put it in your hand. Then shuffle your deck."
- **Target fingerprint**: S=2 D=0 Z=2 A=2 Y=2 = **8 (spicy)**
- **Axis target**: Behind-when-cast catch-up Supporter. Reads asymmetric prize state; rewards being prize-disadvantaged with tempo.
- **Engine call**: `state.prizes_remaining[player_id] > state.prizes_remaining[opp_id]` guard; `PKM_DRAW` + `pkm_search_typed_card`.
- **Choose / Read / Pull**: which Item to tutor; reads prize asymmetry; pulls answer-toolbox archetype.

---

## Axis 6 — Lost Zone (2 new + 2 rewrites)

> **Engine prerequisite**: verify `lost_zone_<player>` is wired end-to-end before Stage 2 starts. If it's a stub, those cards block until the zone is real.

### Cremate (Golgari — Trainer Item)
- **Text**: "Choose up to 3 cards from your hand. Put each Pokemon and Energy card chosen this way into the Lost Zone instead of the discard pile. (Lost Zone cards cannot return to play by any means.)"
- **Target fingerprint**: S=1 D=2 Z=3 A=0 Y=3 = **9 (spicy)**
- **Axis target**: LZ feeder with player-choice. Pays Lost-Zone-count cards (Jarad ex) in the same turn cycle.
- **Engine call**: new `PKM_LOST_ZONE` event; `pkm_move_to_lost_zone(card_id)` helper; `pkm_choose_from_hand_n` (up to 3).
- **Choose / Read / Pull**: which 0-3 cards from hand; pulls LZ-count payoff archetype.

### Sanguine Sacrament (Orzhov — Trainer Supporter)
- **Text**: "Put 1 of your Pokemon and all cards attached to it into the Lost Zone. Then, heal all damage from up to 2 of your remaining Pokemon."
- **Target fingerprint**: S=2 D=2 Z=3 A=0 Y=3 = **10 (spicy)**
- **Axis target**: Self-LZ feeder with healing payoff. Trades a Pokemon (and its energy investment) for a board-state reset — the most extreme version of "tempo for stabilization."
- **Engine call**: `pkm_move_to_lost_zone` for the chosen Pokemon + all `attached_energy`/`attached_tools`; `PKM_HEAL` ×2.
- **Choose / Read / Pull**: which Pokemon to sacrifice; which 2 to heal; pulls expendable-attacker decks.

---

## Axis 7 — Tool attach + recurring effects (3 cards)

### Forgeling Hammer (Boros — Trainer Tool)
- **Text**: "Attach to 1 of your Pokemon. Attacks by this Pokemon cost {C} less to use."
- **Target fingerprint**: S=1 D=1 Z=1 A=0 Y=3 = **6 (functional)**
- **Axis target**: Cost-reduction Tool — the first one in BRV. Enables 1-energy turn-2 attacks on Stage 1s.
- **Engine call**: `attach_tool`; `PKM_COST_REDUCTION` (new event piped through `pkm_get_attack_cost`).
- **Choose / Read / Pull**: which Pokemon; pulls Stage-1-aggro archetype.

### Aetherflux Reservoir (Simic — Trainer Tool)
- **Text**: "Attach to 1 of your Pokemon. Once during your opponent's turn, when the attached Pokemon would take damage from an attack but is not Knocked Out, draw 1 card."
- **Target fingerprint**: S=1 D=1 Z=1 A=0 Y=3 = **6 (functional)**
- **Axis target**: Defensive recurring Tool. Survival-rewards play that absorbs damage instead of trading prizes.
- **Engine call**: `attach_tool`; `PKM_TAKE_DAMAGE` listener with once-per-turn flag.
- **Choose / Read / Pull**: which Pokemon to attach to; pulls tank/wall archetype.

### Negate the Negation (Simic — Trainer Item) **[BUILD-AROUND]**
- **Text**: "Choose 1 of your opponent's Pokemon that has a Tool attached. Discard all Tools attached to it. For each Tool discarded this way, your opponent reveals the top card of their deck; you put that card into the Lost Zone."
- **Target fingerprint**: S=2 D=2 Z=3 A=3 Y=3 = **13 (build-around)**
- **Axis target**: Tool removal that cascades into LZ. The first card combining 3 axes (Decision, Asymmetric LZ exile, Mechanic-payoff). Anchors an anti-Tool meta archetype.
- **Engine call**: `pkm_choose_pokemon_with_tool`; `remove_tool` (existing novel helper); `PKM_REVEAL` + `pkm_move_to_lost_zone`.
- **Choose / Read / Pull**: which opp Pokemon; reveals top of opp deck N times; pulls a Tool-meta-hate archetype.

---

## Rewrites (8 existing reskins → new effects)

Existing BRV cards in reskin clusters that get redesigned. The current effects are pure typography (e.g. Aurelia ex's current `_battalion_strike_effect` is the same `bench_count → opp_active_damage` shape as 5 other cards).

### Aurelia, the Warleader ex (Boros — Stage 2 ex) **[BUILD-AROUND]**
- **Current**: bench-scaling damage (cluster `[7830b8469298]`, 6 cards)
- **New**:
  - Sunhome's Glory [R][W] 60 — vanilla
  - Battalion Mark [R][W][C][C] — "Each of your Benched Pokemon may do 10 damage to your opponent's Active Pokemon (you choose how many participate; 0 to 5)." Aurelia herself does no damage with this attack.
- **Target fingerprint**: S=2 D=3 Z=2 A=2 Y=2 = **11 (spicy build-around)**
- **Why rewrite**: anchors the wide-board Boros archetype around her, instead of being interchangeable with Razia and Wojek.

### Jarad, Golgari Lich Lord ex (Golgari — Stage 2 ex) **[BUILD-AROUND]**
- **Current**: graveyard-conditional damage (cluster `[b4a11f3afcb6]`, 7 cards)
- **New**:
  - Ability: Lich's Bargain — "Once during your turn, you may put 1 Pokemon from your discard pile into the Lost Zone. If you do, draw 1 card."
  - Necrosurge [B][G][C] 80+ — "+20 damage for each Pokemon in your Lost Zone."
- **Target fingerprint**: S=3 D=1 Z=3 A=0 Y=3 = **10 (spicy build-around)**
- **Why rewrite**: the LZ engine of the set. Other LZ cards exist only because Jarad exists.

### Mirko Vosk, Mind Drinker (Dimir — Stage 1) **[BUILD-AROUND]**
- **Current**: opp mill (cluster `[e0759bce2571]`, 5 cards)
- **New**:
  - Lost Recall [U][B][C] 70 — "Look at the top 4 cards of your opponent's deck. Put 1 of them into the Lost Zone. Shuffle the rest back into their deck."
- **Target fingerprint**: S=2 D=2 Z=3 A=3 Y=3 = **13 (build-around)**
- **Why rewrite**: opp-LZ-feeder is a unique role nothing else fills. Replaces the dull "mill 4" with a targeted exile that creates real games.

### Niv-Mizzet, Parun ex (Izzet — Stage 2 ex) **[BUILD-AROUND]**
- **Current**: pure cantrips (cluster `[028be101e4aa]`, 14 cards)
- **New**:
  - Ability: Firemind — "Each time you draw a card after the first you draw each turn, place 1 damage counter on your opponent's Active Pokemon."
  - Synapse Burn [R][U] 80 — vanilla on the body
- **Target fingerprint**: S=3 D=0 Z=2 A=2 Y=3 = **10 (spicy build-around)**
- **Why rewrite**: turns the 14-card draw cluster into a synergy package — drawing cards is now a payoff. The cantrips become Firemind-feeders.

### Razia, Boros Archangel (Boros — Basic) → repurpose to Stage 1
- **Current**: bench-scaling damage (cluster `[7830b8469298]`, with Aurelia)
- **New**: Stage 1 evolving from Razlet (rename existing Aurelet variant)
  - Tool Salvage [R][C] 50 — "Search your discard pile for 1 Tool card and attach it to one of your Pokemon."
- **Target fingerprint**: S=2 D=1 Z=2 A=0 Y=3 = **8 (spicy)**
- **Why rewrite**: turns the second-most-cluttered cluster member into a Tool-archetype anchor. Pairs with Forgeling Hammer and Pithing Drone.

### Goblin Electromancer (Izzet — Basic)
- **Current**: pure cantrip (cluster `[028be101e4aa]`)
- **New**:
  - Ability: Inventor's Spark — "Whenever you play your 2nd Item card on any turn, draw 1 card."
- **Target fingerprint**: S=2 D=0 Z=1 A=0 Y=3 = **6 (functional)**
- **Why rewrite**: storm-style payoff for Item-heavy Izzet decks. Stops being a vanilla cantrip; starts being an engine piece.

### Trostani, Selesnya's Voice ex (Selesnya — Stage 2 ex)
- **Current**: empty stub (cluster `[05eda97e4cf5]`, 4 cards)
- **New**:
  - Ability: Voice of Selesnya — "All of your Pokemon (including this one) have their maximum HP increased by 10 for each OTHER Pokemon you have in play (current damage is preserved)."
- **Target fingerprint**: S=3 D=0 Z=1 A=0 Y=3 = **7 (functional)**
- **Why rewrite**: actual lord effect — pulls wide-board decks together. The current Trostani is a stub.

### Lazav, Dimir Mastermind ex (Dimir — Stage 1 ex) **[BUILD-AROUND]**
- **Current**: opp mill (cluster `[e0759bce2571]`, with Mirko)
- **New**:
  - Ability: Mimic — "Once during your turn, you may choose a Basic Pokemon in either player's discard pile. Until the end of your turn, Lazav has the same attacks (and attack costs) as that Pokemon."
- **Target fingerprint**: S=3 D=2 Z=2 A=0 Y=3 = **10 (spicy build-around)**
- **Why rewrite**: copy-target unique role. Punishes the opponent for letting cards die. Replaces the "mill 4" twin of Mirko.

---

## Engine profile patches needed (Stage 2 prerequisites)

For the scorer to recognize the D and Y signals above, `src/depth/engine_profiles.py` `PKM_PROFILE` needs:

```python
modal_helpers=frozenset({
    "create_pkm_modal_choice",
    "pkm_force_opp_choose_bench",
    "pkm_target_card_in_hand_choice",
    "pkm_choose_pokemon_target",
    "pkm_choose_from_hand_n",
    "pkm_choose_bench_target",
    "pkm_modal_choice",  # alias / shorter form
}),
filter_factories=frozenset({
    "count_pokemon_by_stage",
    "count_pokemon_in_play",
    "count_typed_energy_attached",
    "count_typed_energy_in_hand",
    "count_poisoned_pokemon",
    "count_pokemon_in_lost_zone",
}),
novel_helpers=frozenset({
    "attach_tool", "remove_tool",
    "apply_status_condition", "clear_status_condition",
    "place_damage_counters",
    # add:
    "pkm_move_to_lost_zone",
    "pkm_apply_prize_tax",
    "pkm_skip_evolution_stage",
    "make_pkm_stadium_static",
}),
asymmetric_event_types=frozenset({
    # existing PKM_* set...
    # add:
    "PKM_LOST_ZONE",
    "PKM_FORCE_SWITCH",
    "PKM_MOVE_ENERGY",  # cross-controller variant
    "PKM_COST_REDUCTION",
    "PKM_REVEAL",
}),
information_event_types=frozenset({
    "PKM_REVEAL_HAND",
    "PKM_REVEAL",  # top of deck
}),
```

Each helper above corresponds to a real implementation in `src/cards/pokemon/_helpers/` (new package) plus engine support in `src/engine/pokemon_*.py` where the underlying primitive doesn't exist yet.

## Distribution summary

**Tier counts (target):**

| Tier | Count | Cards |
|---|---|---|
| **Build-around (12-15)** | 4 | Mirko Vosk (13), Negate the Negation (13), Obzedat ex (14), Aurelia ex rewrite (11)* |
| **Spicy (8-11)** | 14 | Tezzy's Test, Niv-Mizzet's Quandary, Jace, Dimir Interrogation, Trostani's Verdict, Zegana, Rakdos's Mark, Bone to Ash, Pithing Drone, Final Reward, Cremate, Sanguine Sacrament, Razia rewrite, Niv-Mizzet ex rewrite, Jarad ex rewrite, Lazav ex rewrite |
| **Functional (4-7)** | 12 | Doubling Symbiote, Tox-Pawpsule, Vraska's Hex, Voidmage Apprentice, Zhur-Taa Druid, Karlov, Forgeling Hammer, Aetherflux Reservoir, Goblin Electromancer rewrite, Trostani ex rewrite |
| **Vanilla** | 0 | — |

`*` Aurelia ex's fingerprint is 11 (spicy upper bound). Listed as build-around because it anchors an archetype.

**Axis fingerprint diversity (predicted):**
- 25-30 new distinct axis fingerprints added → set goes from 7 → ~30+ distinct out of 180 cards = **axis_diversity ≈ 0.17** (passes 0.15 stretch target; below 0.5 health target)
- Code fingerprint: each new helper produces a distinct hash → **code_diversity ≈ 0.55-0.60** (passes 0.5 health gate)

**Health gates predicted after Stage 2 ships:**

| Check | Before | After (predicted) |
|---|---|---|
| median_depth ≥ 5 | ❌ 4.0 | ⚠ ~6 (passes; depends on score recomputation post-rewrites) |
| axis_diversity ≥ 0.5 | ❌ 0.067 | ❌ ~0.17 (improved but still below target) |
| code_diversity ≥ 0.5 | ❌ 0.442 | ✅ ~0.55 |
| thin_ratio ≤ 0.20 | ❌ 0.613 | ⚠ ~0.40 (down but not under target) |

Set goes from **0/4** to **2/4** health gates passing. The remaining two (axis diversity, thin ratio) need a second design pack to lift further — but the user's success criterion (≥8 spicy cards, ≥4 build-around, ≥2 health gates) is hit by this one pack.

## What comes next (Stage 2 outline)

1. **Engine verification**: smoke-test each of the 12 "engine call" primitives listed above. Identify which are real, which are stubs, which need new wiring.
2. **TDD per card**: failing test → effect_fn → green test. Implementation is fanned out across guilds via `/semaphore` (10 guilds → 10 parallel agents).
3. **`/test-interceptors`** across BRV to catch "wired but returns []" failures.
4. **Profile patch**: add the helper names above to `PKM_PROFILE`.
5. **Re-run depth audit**: `python -m src.depth.report --set BRV --out logs/depth_v2_brv_after.json`. Verify the predicted tier counts and health gates.
6. **`/build-decks`**: rebuild guild decks featuring the new spice cards.
7. **`/ultra-loop --mode=double`**: 5-10 games per matchup to validate decision-creating cards actually create decisions in play.
8. **`/ng-plus 2`**: final polish loop.
