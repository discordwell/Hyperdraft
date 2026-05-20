# Cats — A Trick-Taking, Pile-Building Card Game

## 1. Theme & Pitch

Cats is a charming, irreverent card game about household cats competing for the things household cats actually care about: **territory** (the warm spot on the couch), **naps** (the sunbeam moving across the floor), **snacks** (whatever you were trying to eat), and **attention** (which they pretend not to want until you stop giving it). The cast skews absurd-domestic: Mister Whiskers, Sir Reginald Loafington, Princess Mayhem the Third, Greg, Gary the One-Eyed Tabby, Lord Fluffinbottom, and a single Dignified Calico named Karen. Card types include real things like **Knocking Things Off Tables**, **Sitting In The Box**, **The 3 a.m. Zoomies**, and **Aggressive Loafing**. The vibe is "cats committee meeting with no agenda."

Mechanically the game is a **trick-taking + pile-building hybrid**: each round both players play one card, the trick resolves under a *category-specific* comparison rule, the winner takes the trick into one of four scoring piles, and the contents of those piles double as the **resource pool** for activated abilities. There is no mana, no attacking, no blockers, no stack. There is only the question that defines a cat's day: *do I want this thing now, or am I saving it for later?*

Cats is meant to play in 9 short rounds — "a day in the life of a cat." It is genuinely distinct from every existing Hyperdraft engine because the **core decision** isn't "what card do I cast" — it's "I won this trick; which pile do I put it in?" That single choice carries the entire strategic load, because each pile both **scores differently** and **activates differently**, and you can't have everything in one pile.

## 2. Win Condition

The game ends when **9 rounds have been played**. Each round drains one card from each player's hand; hands refresh from the deck when both hands are empty (see Section 11 for cycling). The game-over check is concrete:

> `state.cats_round_number >= 9 AND all players have empty hands` → `game_over = True` is set, and a `GAME_END` event is emitted with `payload.reason = "day_complete"`.

At game end each player **scores** across their three scoring piles:

- **Territory pile**: 1 point per card, +2 per Trinket attached, +5 bonus if pile has ≥6 cards (you claimed the couch).
- **Nap pile**: 2 points per card, but capped at 12 points total (a nap can only be so long).
- **Snack pile**: 3 points per card if pile has fewer than 5 cards, 1 point per card otherwise (you got greedy).

Highest total **wins**. On a tie, the player with **more cards in the attention pile** wins (the cat that demanded the most attention triumphs). On a further tie (same attention count), the game is a **draw** — explicitly allowed, because cats.

The scoring routine is a pure function over final pile contents, runs in the engine's CLEANUP-equivalent step after round 9 ends, and emits `PLAYER_WINS` / `PLAYER_LOSES` / a tie-marker. A smoke test asserts `game.is_game_over() == True` and `state.cats_round_number == 9` and exactly one of {one winner, declared draw}.

## 3. Turn / Round Structure

A **round** is the atomic unit, not a turn. Each round has six phases, all of which fire `PHASE_START` / `PHASE_END` events so card interceptors can hook them:

| Phase | Name | What happens |
|---|---|---|
| 1 | **Stretch** (open) | Round-start triggers fire. Trinket and Commander passives recompute. The "lead player" for this round is set (alternates each round; round 1 = player 1). |
| 2 | **Pounce** (lead) | The non-active player (the "follower" — see note below) plays one card from hand **face-up**. This is intentionally backwards from intuition: the follower commits first, then the lead reacts. |
| 3 | **Counter-pounce** (follow) | The lead player plays one card from hand, face-up. |
| 4 | **Resolve trick** | Both cards are compared under the **current trick rule** (default: highest Value wins; see Section 7). Moods and Snacks may transform the rule. The winner is determined. |
| 5 | **Claim pile** | The **trick winner** chooses one of their three scoring piles to receive both cards (or the attention pile, see Snack rules). Pile caps and Snack-overrides apply. Cards enter the pile face-up and may trigger on-enter effects. |
| 6 | **Curl up** (end) | End-of-round triggers fire. Pile caps re-checked. Round number increments. |

**On terminology**: the player who plays **second** in a round (Counter-pounce) is the "lead" because they get to react to what the other player committed to. This is deliberate — it creates the *bait* dynamic that makes the trick interesting. The lead role alternates each round so over 9 rounds each player leads either 4 or 5 times.

**Why phases not turns**: there is no concept of "your turn." Both players act every round. This is what makes Cats mechanically distinct from every Hyperdraft engine — it is *symmetric per round* rather than *alternating per turn*.

## 4. Resource Model

**No mana, no costs at play-time.** A player simply plays one card per round, no payment required. Instead, **piles are the resource**.

After cards enter a pile, they may be **exhausted** ("knocked over" — flavor for tap) to pay for activated abilities printed on those cards or on Trinkets. A card knocked over remains in the pile (it still scores) but cannot be knocked over again until it untaps. Cards untap at the start of each round (Stretch phase).

This means pile composition is a genuine strategic choice during the Claim phase:

- **Sending a trick to Territory** scores 1pt per card + bonuses, AND each card in Territory can be knocked over to activate "Territory-tap" effects (typically: peek at opponent's hand, lock a pile cap, reroute next trick's winner choice).
- **Sending a trick to Nap** scores 2pt per card (capped 12), AND each card can knock over for "Nap-tap" effects (typically: skip a round's effects, gain +1 to a played card's Value, force a draw).
- **Sending a trick to Snack** scores 3pt or 1pt (greed penalty), AND each card knocks over for "Snack-tap" effects (typically: combo triggers — "if Snack pile has ≥3 cards, gain X").

So a "tall scoring pile" is also a "deep utility battery," but only of *one type*. You can't have everything.

Critically: **the pile a card lives in matters for its activated abilities, not its printed type.** A Cat card in your Nap pile activates the Nap effect; the same Cat in your Snack pile activates the Snack effect. This is the most important resource design choice: it makes pile-choice during Claim a meaningful, irreversible decision.

## 5. Zones

| Zone (per-player unless noted) | Purpose |
|---|---|
| `hand` | Current playable cards. Starts at 5, refills when empty (see §11). |
| `deck` (library) | Draw pile. |
| `discard` | Used cards (round-end card cycling, ability discards). When deck empties, discard reshuffles into deck. |
| `pile_territory` | Scoring pile #1. Holds trick-winnings claimed here. Cap: 8 cards. |
| `pile_nap` | Scoring pile #2. Cap: 6 cards (naps are short). |
| `pile_snack` | Scoring pile #3. Cap: 5 cards (the greed penalty applies above this). |
| `pile_attention` | Tiebreaker pile. Cards land here when a card-specific "demands attention" trigger fires (e.g. winning a trick that contained a Mood). Cap: unlimited. |
| `claw` (exile) | Permanently removed from game. Some effects send cards here. |
| `command` (shared structure, per-player slot) | Pre-game **Commander Cat** lives here. One per player, always-on passive. Cannot be removed by card effects. |

Pile caps are **hard**: if you win a trick and your only legal target pile is full, the trick is dumped into the **attention pile** instead. This makes "filling up your scoring piles" both a goal and a hazard — overflow rewards the *opponent's* tiebreaker count if they're ahead on score.

All piles are **public information** including order of entry (it matters for some Trinket triggers like "the first Sleek cat in this pile").

## 6. Card Types

Five card types. The first four are playable from hand. The fifth is chosen pre-game.

| Type | Role |
|---|---|
| **Cat** | The core unit. Has a numeric **Value** (1–10) and exactly one **Category** (Sleek / Fluffy / Scrappy / Sneaky). May have an effect that triggers on-play, on-win-trick, on-lose-trick, on-enter-pile, or on activate. |
| **Mood** | A modifier card. When played, replaces the current round's trick-comparison rule (e.g. "Sneaky cats win the trick on lowest value this round"). Moods themselves have a Value of 0 — they almost always lose the value comparison, but they distort the rule before comparison happens. |
| **Snack** | A wildcard. If a trick contains a Snack from either player, the trick winner is **forced to send the trick to their Snack pile** regardless of preference (or to attention if Snack is full). Snacks have a Value too (typically low) and contribute to comparison normally. |
| **Trinket** | A persistent attachment. Played from hand, attaches to one of your scoring piles, and grants a passive (e.g. "This pile scores +1pt per card if it contains a Sleek cat"). Stays attached until end of game. Each pile can hold at most 2 Trinkets. |
| **Commander Cat** | Pre-game-only. Chosen from a pool before the game starts. Lives in the command zone. Provides one always-on passive (e.g. "Your snack pile cap is 7 instead of 5"). Cannot be played, destroyed, or moved. |

Note that **Mood**, **Snack**, and **Trinket** are still played as "the one card from hand this round" — playing a Trinket consumes your round's card play and you do not contribute a Cat to the trick (so you almost certainly lose that trick — Trinkets are a tempo investment). Snacks and Moods *do* compete in the trick comparison.

## 7. Trick Resolution (The Load-Bearing Rule)

**Default trick rule**: highest **Value** wins. Ties resolve to whoever played second (the lead player wins ties).

The trick rule is modified by **the round's Category Rule** — established by the **first card played** in that round (the Pounce card). Each Category sets a different comparison rule:

| Category | Trick rule installed when played as Pounce |
|---|---|
| **Sleek** | Highest Value wins. (Default rule; Sleek is the "normal" cats.) |
| **Fluffy** | Highest Value wins, but **ties go to the player with fewer total cards across all scoring piles** (the underdog cat wins social ties). |
| **Scrappy** | **Lowest Value wins.** The scrappy cat wins by being the underdog. |
| **Sneaky** | Both cards' values are **secret** during comparison: the winner is determined by reading a hidden suit-tag on the back of the card. (Implementation: each Cat carries a `sneaky_value` 1–10 that only the system reads. Played publicly but compared privately. The player sees the result, not the value.) |

**Then** Moods can override the rule:

- A Mood played as Pounce **replaces** the Category Rule for the round entirely (e.g. "Bored: ties win for whoever has the smallest hand" overrides whatever Sleek/Scrappy etc. would do).
- A Mood played as Counter-pounce installs the rule **before** the comparison runs, so the Pounce player's commitment can be retroactively reframed.

**Snacks** don't change the rule but they do change the Claim phase (force-Snack-pile).

### Worked Example: 3-Round Sequence

**Setup**: Player A's hand: `Mister Whiskers (Sleek, 7)`, `The 3 a.m. Zoomies (Mood)`, `Catnip Mouse (Snack, 2)`, `Sir Reginald Loafington (Fluffy, 6)`, `Greg (Scrappy, 4)`. Player B's hand: `Princess Mayhem (Sneaky, 9)`, `Lord Fluffinbottom (Fluffy, 5)`, `Tuna Can (Snack, 1)`, `Gary the One-Eyed Tabby (Scrappy, 3)`, `Karen (Sleek, 8)`.

**Round 1** — B leads (B is the follower-who-plays-first this round):
- **Pounce**: B plays Lord Fluffinbottom (Fluffy, 5). Category Rule installed: *Fluffy — highest wins, ties go to fewer-cards-in-piles*.
- **Counter-pounce**: A plays Mister Whiskers (Sleek, 7).
- **Resolve**: 7 > 5, A wins.
- **Claim**: A chooses Territory pile. Both cards enter `pile_territory_A`. Mister Whiskers' on-enter trigger fires: "Peek at opponent's hand."

**Round 2** — A leads:
- **Pounce**: A plays The 3 a.m. Zoomies (Mood). Mood text: *"Tonight everyone is unhinged. Lowest Value wins this trick."* Category Rule overridden.
- **Counter-pounce**: B plays Gary the One-Eyed Tabby (Scrappy, 3). B sees the Mood and dumps their lowest Cat.
- **Resolve**: 0 (Mood) vs 3. Wait — Moods have Value 0. Under "lowest wins," Mood wins (0 < 3). A wins the trick. B sees the trap.
- **Claim**: A chooses Nap pile. The Mood and Gary enter `pile_nap_A`. Mood's on-enter: "Demands attention" → also place a duplicate marker in `pile_attention_A`.

**Round 3** — B leads:
- **Pounce**: B plays Tuna Can (Snack, 1). Snack triggers force-claim.
- **Counter-pounce**: A plays Catnip Mouse (Snack, 2). Two snacks in one trick.
- **Resolve**: Under default Sleek rule, 2 > 1, A wins.
- **Claim**: Snack-force triggers — A must send the trick to `pile_snack_A` (no choice). Both Snacks enter `pile_snack_A`. Catnip Mouse's effect: "When this enters the Snack pile, draw a card." A draws.

After 3 rounds: A has 2 cards in Territory, 2 in Nap, 2 in Snack, 1 in Attention. B has nothing yet. A is dominating the day.

## 8. Engine Capabilities (The Contract)

This is the explicit list of capabilities the engine MUST natively support. Each maps to one or more new interceptor patterns. Stages 1–4 will implement these.

1. **Trick-time triggers** — `on_play` (card enters trick), `on_win_trick` (card was on winning side), `on_lose_trick` (card was on losing side). Implemented as `Interceptor` filtered on new `EventType.CATS_TRICK_RESOLVE`. Helper: `make_trick_trigger(obj, phase, effect_fn)` where `phase ∈ {'on_play', 'on_win', 'on_lose'}`.

2. **Pile-time triggers** — `on_enter_pile(pile_name)`, `on_pile_cap_reached(pile_name)`, `on_activate_from_pile`. Fires when a card moves into a pile (via `CATS_CLAIM_PILE`), when a pile reaches its cap (`CATS_PILE_CAPPED`), or when a card is knocked over to activate (`CATS_PILE_ACTIVATE`). Helper: `make_pile_trigger(obj, pile, phase, effect_fn)`.

3. **Round-time triggers** — `on_round_start` (Stretch), `on_round_end` (Curl up). Implemented via existing `PHASE_START`/`PHASE_END` events, distinguishable by payload phase names `"cats_stretch"` and `"cats_curl_up"`. Helper: `make_round_trigger(obj, when, effect_fn)`.

4. **Static pile modifiers (Trinkets)** — TRANSFORM-priority `Interceptor`s on a new `EventType.CATS_QUERY_PILE_SCORE` (computed at game-end and during preview). Trinkets attached to a pile filter for that pile and rewrite the score payload. Helper: `make_trinket_score_mod(obj, pile, mod_fn)`.

5. **Mood interceptors (replace the trick rule)** — REPLACE-priority `Interceptor`s on `EventType.CATS_TRICK_RULE_QUERY` that fires when the engine asks "what comparison rule does this trick use?" A Mood card replaces the returned rule object. Helper: `make_mood_rule_override(obj, rule_fn)` where `rule_fn(card_a, card_b, state) -> winner_id`.

6. **Replacement effects ("can't go to pile X")** — PREVENT or TRANSFORM on `EventType.CATS_CLAIM_PILE`. When a card or Commander imposes "may not be claimed into Snack" or "must be claimed into Territory," the interceptor rewrites the target pile. Helper: `make_claim_restriction(source, restrict_fn)` returning either a transformed payload or PREVENT (which routes to attention as the fallback).

7. **Activated abilities that exhaust pile cards** — A subset of `make_activated_ability` (which already exists) but the cost is `cats_knock_over` (tap a card in a specific pile). Helper: `make_pile_activated(obj, pile_required, effect_fn)`. The action's legality is checked by reading the pile contents at activation time.

8. **Commander passives (always-on, can't be removed)** — Interceptors registered at game-setup time with `duration='forever'` and a special source flag `is_commander=True` that exempts them from any silence/disenchant/destroy effects future cards might invent. Helper: `register_commander_passive(player_id, effect_fn, description)`.

**Required new EventTypes** (Stage 1 will add to `src/engine/types.py`):
- `CATS_ROUND_START`, `CATS_ROUND_END`
- `CATS_CARD_PLAYED` (Pounce or Counter-pounce played)
- `CATS_TRICK_RULE_QUERY` (synthetic query — what rule to use)
- `CATS_TRICK_RESOLVE` (winner determined)
- `CATS_CLAIM_PILE` (winner chooses pile)
- `CATS_PILE_CAPPED`, `CATS_PILE_ACTIVATE`, `CATS_KNOCK_OVER`
- `CATS_QUERY_PILE_SCORE` (synthetic query for end-of-game scoring)
- `CATS_GAME_OVER` (specific marker — round 9 ended)

**Required new CardTypes**: `CATS_CAT`, `CATS_MOOD`, `CATS_SNACK`, `CATS_TRINKET`, `CATS_COMMANDER`.

**Required new ZoneTypes**: `CATS_PILE_TERRITORY`, `CATS_PILE_NAP`, `CATS_PILE_SNACK`, `CATS_PILE_ATTENTION`.

**Required GameState fields** (extending GameState as Depths and Minecraft do): `cats_round_number: int`, `cats_lead_player: Optional[str]`, `cats_current_rule: Optional[Any]` (a callable installed by Pounce category), `cats_current_trick: dict` (transient — the two played cards while resolving), `cats_commanders: dict[str, str]` (player_id → commander object id).

## 9. AI Difficulty Model

- **Easy** — Plays a uniformly random legal card from hand. On Claim, picks a random non-full pile. On activation choices, never activates pile abilities. Approximate skill: passable kitten.

- **Medium** — Plays the highest-Value card available unless the round's installed Category Rule is Scrappy (then lowest). On Claim, always claims to the highest-scoring pile that isn't full (Snack > Nap > Territory > attention). Activates pile abilities only when an obvious win-now opportunity exists (e.g. "play +1 Value to my Cat to break a tie"). Doesn't bluff. Doesn't plan around Snack-forces.

- **Hard** — Performs **1-round lookahead**: simulates each legal card it could play against each card the opponent might play (filtered by what's likely from their visible piles + remaining-hand inference). For each candidate, scores:
  - Expected pile-score delta this round
  - Pile-cap pressure (claiming into a pile near cap is worse than into an empty pile)
  - Mood/Snack catastrophe risk (avoid handing opponent a free Snack-force into their own Snack pile)
  - Knock-over potential of the won cards (a high-value Cat in Territory is better than a low one)

  Hard plays Moods strategically (using them as Counter-pounce to reverse a losing Pounce). Hard will also **deliberately lose** tricks containing junk cards by dumping a 1-Value card when the opponent has clearly committed to winning — letting the opponent fill their pile cap with garbage. Hard activates pile abilities both reactively (rescue a losing trick) and proactively (set up an opponent-disrupting effect at Stretch).

Difficulty is selected at game start via `Game.set_ai_difficulty(player_id, 'easy'|'medium'|'hard')`, persisted on the Player. Implementation lives at `src/ai/cats_adapter.py:CatsAIAdapter(difficulty=str)`, following the per-mode adapter pattern already used by Pokemon/Minecraft/Depths.

## 10. Comparison with Existing Engines

Closest analogue is **Hearthstone**: no priority loop, no stack, all action happens within a small round-state machine, simplified resolution. But Cats differs from HS in three material ways:

1. **Symmetric rounds, not alternating turns.** Both players play every round. HS's "your turn vs my turn" doesn't exist here.
2. **Cards have no cost.** There is no mana, no auto-curve, no fatigue mechanic. The economy is entirely *post-play* via pile-tap activations.
3. **The won-cards-become-resources loop.** HS minions stay on the board and attack; Cats' won cards go into piles where they're scored AND consumed for activations. This double role for played cards is mechanically novel for this repo.

Things explicitly NOT borrowed from any engine:
- **No attacker/blocker combat** (MTG/HS). There is comparison, not combat.
- **No mana curve** (MTG/HS).
- **No graveyard recursion as core strategy** (MTG). Discard is just shuffle-fodder; nothing meaningful happens there.
- **No active/bench structure** (Pokemon). The "active card" is whichever card is currently in the trick, transient.
- **No depth/lanes/columns** (Depths/Minecraft). Piles are unordered (except for entry timestamp), not spatial.

The trick-taking + pile-building hybrid is genuinely absent from Hyperdraft today. Engines like Hearthstone and Depths share the no-priority simplicity but not the round-symmetric, comparison-driven, pile-as-resource core.

## 11. Open Questions (For Stage 1+ Implementation Team)

1. **Trick size: 2-card vs 3-card.** Recommend **2-card for v1**. The Pounce/Counter-pounce loop is already strategically dense. Hooks should be present in the engine (`CATS_TRICK_RESOLVE` payload should support a list of cards, not a 2-tuple) so a future "Reactive" phase or 3-player mode can extend to 3-card tricks.

2. **Hand size and deck size.** Recommend **5-card hand, 30-card deck**. Over 9 rounds × 2 cards per round = 18 cards drawn total per game pair; with hand refills you'll cycle the deck once. Deck shuffle from discard on empty is a hard requirement.

3. **Multi-player support.** Recommend **design for 2-player v1**, with a clear hook for 3-player as a stretch goal. In 3-player, tricks become 3-card and the comparison rule expands (Sleek = highest still wins; ties bounce). Pile structure stays per-player. The `cats_lead_player` rotates instead of binary-alternating.

4. **Should Moods be cumulative?** Open: if both players play Moods (Pounce-Mood and Counter-pounce-Mood), do we use both, the later, or the earlier? Recommend: **later replaces earlier** (Counter-pounce Mood wins). Card design should mostly avoid stacking Moods.

5. **Sneaky `sneaky_value` source.** Open: how is the hidden value decided? Recommend: stored as a CardDefinition field at card creation, fixed per printing. Not random per-game. Discoverable via cards that "reveal sneaky values."

6. **Pile cap = exactly that, or soft?** Recommend hard. Once full, overflow goes to attention. Some Trinkets may print "this pile's cap is +2" as a way to selectively soften caps.

7. **Should the Curl-up phase auto-activate something every round?** Open. Could keep symmetric (do nothing) or add a "free knock-over" at end of round. Recommend keep clean for v1; let cards introduce special end-of-round behavior.

8. **Tournament starter decks (Stage 4 set design).** Out of scope for this doc, but: design **6 Commander Cats** + **~40 unique Cat cards** + **~10 Moods** + **~10 Snacks** + **~10 Trinkets** for a first set. Names should be flavorful and the irreverence cap should be high.
