# CATS Engine — Polish-Pass Punchlist

Iteration 1 @ 2026-05-20. Open engine and design-doc gaps captured after Phase 3
(60-card set, 4 decks, hard-vs-medium 71.9% post-AI-fix).

Priority legend: **P0** blocks real play, **P1** blocks polish, **P2** nice-to-have.

---

## P0 — Trick-resolve REACT events are dead-letter

**Symptom**: cards with `on_win` / `on_lose` triggers (e.g. Duchess Velvet, Mister
Whiskers, Lord Tufts) register interceptors but those interceptors never fire,
because `resolve_trick` dispatches only TRANSFORM priority for
`CATS_TRICK_RULE_QUERY` — the `CATS_TRICK_RESOLVE` events with `phase=on_win` /
`phase=on_lose` are emitted but never re-fed into `_dispatch_interceptors`.

**Evidence**: minimal repro — a card whose on_win React emits a DRAW event runs
the trick, the engine reports `resolve emitted 3 events` (master + on_win +
on_lose) but the player's hand size does not change. Compare to `claim_pile`
which DOES dispatch REACT at the per-card CATS_CLAIM_PILE phase event.

**Fix**: in `src/engine/cats.py:resolve_trick`, after appending the per-card
on_win/on_lose phase events, call `_dispatch_interceptors(state, ev,
priorities=(InterceptorPriority.REACT,))` for each phase event and extend the
result list with the returned `reactions`. Mirrors how `claim_pile` already
handles its phase events.

**Test to add**: `tests/test_cats_engine_patches.py::test_on_win_trigger_fires`
— register a Cat whose on_win emits a `DRAW`, run a trick, assert that the
returned event list includes that DRAW (the engine doesn't have to *process*
the DRAW yet — just route the trigger to its handler).

---

## P0 — `DRAW` and `LOOK_AT_HAND` events emitted by cards are unhandled

**Symptom**: 14+ cards across the 60-card set emit `EventType.DRAW` or
`EventType.LOOK_AT_HAND` from on_win / on_enter triggers (Duchess Velvet, Lord
Tufts, Bartholomew, the Sneaky on-win droppers, Trinkets with draw effects).
The cats engine has no handler for either event — even if Issue 1 is fixed,
nothing actually draws cards or peeks at hands.

**Evidence**: `grep -n "EventType.DRAW\|EventType.LOOK_AT_HAND"
src/cards/cats/CATS/` shows 10+ emitters; `grep -n "DRAW\|LOOK_AT_HAND"
src/engine/cats.py` shows 0 handlers. The mode adapter inherits MTG defaults
but the cats turn loop never invokes the pipeline.

**Fix**: add a minimal cats-side handler. Either (a) extend
`_dispatch_interceptors` to recognise `EventType.DRAW` and call into
`_refill_hand_if_empty`-style draw mechanics, or (b) handle them inside
`resolve_trick` / `claim_pile` after dispatching the REACT priority. Lift one
card per pile (a single draw) into the test harness first.

**Note**: at minimum, route `LOOK_AT_HAND` to a no-op log so cards don't
silently swallow the trigger. The AI doesn't read the result yet anyway.

---

## P1 — `make_pile_activated` / pile knock-over abilities are unimplemented

**Symptom**: `docs/games/cats.md` §4 + §8.7 describe activated abilities that
exhaust pile cards: "knocked over" cards in your scoring piles pay for
peek/draw/buff effects. Section 8 calls for a `make_pile_activated(obj,
pile_required, effect_fn)` helper. **No code in the repo defines or uses such
a helper.** No `CATS_KNOCK_OVER` event type exists either; cards reference
`CATS_PILE_ACTIVATE` instead.

**Evidence**:
- `grep -rn "make_pile_activated"` = 1 hit (the design doc).
- `grep -rn "CATS_KNOCK_OVER"` = 0 hits.
- `src/engine/cats.py` has no pile-activation function.
- `CatsAIAdapter._hard_choose_activations` has a TODO at line 720+ saying
  "Activated abilities… until Agent 3 wires that into the turn manager,
  return []".

**Fix**:
1. Add `EventType.CATS_KNOCK_OVER` to `src/engine/types.py`.
2. Implement `make_pile_activated(obj, pile, effect_fn) -> Interceptor` in
   `src/engine/cats.py` that filters CATS_KNOCK_OVER events matching the
   card's pile and calls `effect_fn`.
3. Add `state.activate_pile_card(player_id, card_id)` that taps the card
   (sets `obj.state.tapped = True`) and emits the CATS_KNOCK_OVER.
4. Untap rule: at Stretch (round start), iterate piles and set
   `obj.state.tapped = False` for all owner-controlled cards.

**Priority**: P1 because no current card uses pile-activated abilities (they're
all triggers). When cards start using them, this becomes P0.

---

## P1 — Trinket play / attach mechanic is missing

**Symptom**: design §6 says "Trinket … attaches to one of your scoring piles
… stays attached until end of game." The engine has a `state.cats_pile_trinkets`
dict and `make_trinket_card(attaches_to=...)`, but **no function attaches a
Trinket to a pile**. If a player plays a Trinket via `play_card_to_trick`, it
goes into the trick as a value-0 card and gets claimed into a regular pile —
which means it's mis-scored as a normal card and its passive never registers
against `cats_pile_trinkets`.

**Evidence**: `grep -n "cats_pile_trinkets"` shows initialization in
`_init_cats_state` and `setup_cats_player`, plus a read in `score_cats_player`
— but nothing ever **writes** to `cats_pile_trinkets[player_id][pile_name]`.

**Fix**: add `attach_trinket(state, player_id, trinket_card_id, target_pile)`
that:
1. Verifies the pile has < 2 trinkets (the design's per-pile cap).
2. Removes the trinket from hand.
3. Appends to `state.cats_pile_trinkets[player_id][target_pile]`.
4. Sets the trinket object's zone to a new `CATS_TRINKET_ATTACHED` zone (or
   reuses one of the pile zones with a marker).
5. Runs setup_interceptors so static score-modifiers register.

Then wire `play_card_to_trick` (or a new public `play_trinket_round`) to
detect Trinket cards and route to `attach_trinket` instead of trick play. The
design says "playing a Trinket consumes your round's card play and you do not
contribute a Cat to the trick (so you almost certainly lose that trick)."

---

## P1 — Sneaky-value reveal mechanic is half-wired

**Symptom**: design §7 + open-question 5 describe Sneaky cards whose hidden
value can be revealed by specific cards: "Discoverable via cards that 'reveal
sneaky values.'" Gary the One-Eyed Tabby's commander text says he "sees
through bluffs" — but his interceptor emits `EventType.PKM_REVEAL` (a Pokemon
engine event!) and the cats engine has no handler.

**Evidence**:
- `src/cards/cats/CATS/commanders.py:211` — `type=EventType.PKM_REVEAL`.
  Wrong engine namespace.
- No `CATS_REVEAL` EventType exists.
- The design's intent ("approximate by emitting a reveal so AI can learn") is
  un-actioned: the AI doesn't read the reveal.

**Fix**:
1. Add `EventType.CATS_REVEAL` to `src/engine/types.py`.
2. Re-point Gary's interceptor to emit `CATS_REVEAL`.
3. Store the revealed sneaky value on a per-player tracker
   (`state.cats_sneaky_known[player_id][opp_card_id] = sneaky_value`) so AI
   `_card_value` / lookahead can consult it.
4. Update `sneaky_rule` to optionally honour Gary's "see printed value, not
   sneaky" override when `state.cats_gary_sleeks_sneaky[ctrl]` is set (Gary's
   setup already flips that flag — currently unused by the rule callable).

---

## P1 — `CatsGame` frontend board has no route

**Symptom**: `frontend/src/games/cats.tsx` exports a default `CatsGame`
component (board with 4 piles, trick zone, phase indicator) but it is not
mounted in `frontend/src/App.tsx`. Visiting `/cats` returns "No routes matched
location /cats" in the console; visiting `/deckbuilder/cats` renders only the
deckbuilder module.

**Evidence**:
- `App.tsx:51-77` lists routes for hs / pkm / ygo / mc / fin / depths / scp /
  spectator etc., but no `/cats` or `/game/:matchId/cats` route.
- The cats.tsx file comment even says the board "is used by a future
  CatsGameView page" — never built.

**Fix**: add `<Route path="/game/:matchId/cats" element={<CatsGameView />} />`
plus the wrapper page. Until the server route exists this can keep using the
hook's mock data (the hook already returns mock state when no socket is
connected).

---

## P2 — Mood vs Mood stacking is ambiguous

**Symptom**: design §11 open-question 4 says "Open: if both players play Moods
(Pounce-Mood and Counter-pounce-Mood), do we use both, the later, or the
earlier?" Recommended `later replaces earlier` but never wired or tested.

**Evidence**: only one Mood interceptor can win the
`CATS_TRICK_RULE_QUERY` TRANSFORM cycle today, and which one wins is order-
dependent on `state.interceptors.values()` (insertion order of dicts in
CPython is by registration time). The design's "Counter-pounce Mood wins" is
*accidentally* honoured because the Counter card's interceptor is registered
later — but this is implicit, not enforced.

**Fix**: in `_dispatch_interceptors`, when multiple TRANSFORM handlers match a
`CATS_TRICK_RULE_QUERY`, prefer the one whose `source` matches the trick's
`counter_card`. Add a test that registers two Mood interceptors with different
rule_fns and asserts the counter one wins.

---

## P2 — 3+ player support is claimed but never tested

**Symptom**: design §11 open-question 3 + multiple "hooks for 3-player"
references in comments. The engine doesn't hard-code 2 players (it loops
`state.players.keys()`) but several functions assume the lead-rotation is
binary:
- `end_round` rotates lead via `(cur_idx + 1) % len(pids)` — works for N.
- `resolve_trick` assumes exactly one pounce + one counter card.
- `claim_pile` works per-winner — fine for N.

The hard blocker for 3+ players is `cats_current_trick` which stores a single
`pounce_card` + single `counter_card` (not a list).

**Evidence**: `state.cats_current_trick = {"pounce_card": None, "counter_card":
None, …}` — no third slot.

**Fix**: when a 3-player game is requested:
1. Convert trick to `cats_current_trick["cards"]: list[(player, card)]`.
2. Update each `rule_fn` to accept a list and return the winner.
3. Add a 3-player test setup helper.

This is P2 because v1 is shipped as 2-player and the design recommends
deferring 3-player to a stretch goal.

---

## P2 — Pile knock-over (tap state) untap path missing

**Symptom**: design §4 says "Cards untap at the start of each round (Stretch
phase)." `begin_round` doesn't iterate piles to clear `obj.state.tapped`.

**Evidence**: `grep -n "tapped" src/engine/cats.py` shows only one write —
`obj.state.tapped = False` on pile entry — and no untap loop in `begin_round`.

**Fix**: add an untap-all-piles step to `begin_round`. Blocked by P1 (pile-
activated abilities aren't wired so no card ever taps anything currently).

---

## P2 — Activation potential bonus in AI is fully bluffed

**Symptom**: `CatsAIAdapter._hard_choose_activations` returns at most 2
naively-scored activations with a flat `1.0` score per available ability. The
hard tier never actually fires utility activations because no card has a real
pile-activated ability wired (see P1 punchlist item).

**Fix**: dependency on P1. Once pile-activated abilities exist, replace the
`score 1.0` placeholder with a real EV evaluator (cost vs effect).

---

## Coverage notes

- **Tests added or improved in this pass**: 0 new tests. All 25 existing
  cats-related tests continue to pass after the AI fixes.
- **Hard AI vs Medium (post-fix)**: 71.9% across 160 games (40 per archetype,
  alternating seats). Previously 45%.
- **Verbose tournament**: every game across all 60 pairings shows 1-9
  distinct on_enter triggers fired. No regression.
- **Largest remaining design-vs-engine gap**: P0 #1 (on_win/on_lose REACT
  routing). Fixing it unlocks ~14 wired-but-dead card effects across the
  60-card set, which would significantly change the tournament balance.
