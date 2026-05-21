"""CATS — Tournament archetype decks (4 decks × 30 cards).

Each deck is a mechanically-distinct pinnacle of its archetype, built entirely
from the existing CATS 60-card pool (no card creation, only remixing). Decks
are tested in `tests/test_cats_decks.py` and play each other round-robin via
`scripts/play/cats_tournament.py`.

Archetypes
==========

1. Couch Empire (Territory Control)
   Commander : Karen the Dignified Calico  (3 trinkets/pile cap, instead of 2)
   Plan      : Stack Territory pile to >=6 cards for the +5 bonus, with two
               Territory trinkets (Yarn Ball, Window Perch) plus Cardboard Box.
               Karen's +1 trinket cap means Yarn Ball + Window Perch + Heated
               Blanket can stuff a single pile. High-Value Sleek cats dominate
               the default "highest wins" rule.

2. Naptime Tyrants (Nap Stuffing)
   Commander : Sir Reginald Loafington     (Nap cap 8 instead of 6)
   Plan      : Sunbeam (+nap cap=8, +2 score) + Heated Blanket (+1 per nap card,
               up to +4) layered on top of Reginald's 8-deep Nap. Mid-high
               Fluffy cats reliably take tricks; dump them into Nap. Nap caps
               at 12pts in vanilla rules but trinket bonuses stack on top.

3. Snack Rush (Snack Forcing + small-pile bonus)
   Commander : Princess Mayhem the Third   (+1 pt/snack-card while pile <5)
   Plan      : All 8 unique Snacks + Cardboard Box; force every trick into
               the Snack pile and ride the small-pile bonus. Princess Mayhem
               doubles down on staying under 5 cards.

4. Shadow Cats (Sneaky + Mood chaos)
   Commander : Gary the One-Eyed Tabby     (Sneaky uses printed Value for Gary's player)
   Plan      : All 7 Sneakies + heavy Moods to swap the trick rule mid-round.
               Gary nullifies the Sneaky downside for our side while opponents
               still play under hidden values. Madam Inkblot and Whispertoes
               are the bluff core; Moods reshape the rule when we'd otherwise
               lose.

Each deck is a (commander, list[CardDefinition]) tuple in CATS_DECKS.
"""

from __future__ import annotations

# -----------------------------------------------------------------------------
# Imports — explicit, one card each, so the deck contents are easy to inspect.
# -----------------------------------------------------------------------------
from src.cards.cats.CATS.commanders import (
    KAREN_THE_DIGNIFIED_CALICO,
    SIR_REGINALD_LOAFINGTON,
    PRINCESS_MAYHEM_THE_THIRD,
    GARY_THE_ONE_EYED_TABBY,
    GREG,
    LORD_FLUFFINBOTTOM,
)
from src.cards.cats.CATS.sleek_cats import (
    MISTER_WHISKERS,
    DUCHESS_VELVET,
    MITTENS_MCSOPHISTICATED,
    LORD_TUFTS,
    THE_BRIGADIER,
    TABITHA,
    CRUMPET,
    THE_MAGNIFICENT_BARTHOLOMEW,
)
from src.cards.cats.CATS.fluffy_cats import (
    SIR_REGINALD_LOAFINGTON_II,
    CINNAMON_BUN,
    MARSHMALLOW,
    SERGEANT_SNUGGLES,
    PILLOW_PRINCESS,
    BISCUIT,
    TOBY_THE_TUBSTER,
    EMPRESS_POMF,
)
from src.cards.cats.CATS.scrappy_cats import (
    GARY_JUNIOR,
    THE_ALLEY_PHANTOM,
    ONE_TOOTH_EDUARDO,
    PRINCESS_MAYHEM_THE_FOURTH,
    THE_YOWLING_STRANGER,
    THE_BEDRAGGLED_EARL,
    MAXIMUM_CARNAGE,
)
from src.cards.cats.CATS.sneaky_cats import (
    WHISPERTOES,
    THE_SHADOW_LOAF,
    MIDNIGHT_PANCAKE,
    MADAM_INKBLOT,
    KNIVES,
    THE_PENUMBRA_TWIN,
    THE_UNOBSERVED,
)
from src.cards.cats.CATS.moods import (
    THE_3AM_ZOOMIES,
    SITTING_IN_THE_BOX,
    AGGRESSIVE_LOAFING,
    KNOCKING_THINGS_OFF_TABLES,
    THE_QUIET_INTERROGATION,
    WET_FOOD_O_CLOCK,
    THE_DIGNIFIED_SULK,
    SUDDEN_SUSPICION,
    THE_DRAMATIC_RECOVERY,
    THE_INSCRUTABLE_STARE,
)
from src.cards.cats.CATS.snacks import (
    CATNIP_MOUSE,
    TUNA_CAN,
    THE_FORBIDDEN_HOUSEPLANT,
    A_SINGLE_CRUMB,
    THE_WHOLE_ROAST_CHICKEN,
    EMPTY_YOGURT_CUP,
    THE_DISPUTED_SLICE_OF_CHEESE,
    THAT_ONE_THING_OFF_THE_COUNTER,
)
from src.cards.cats.CATS.trinkets import (
    YARN_BALL,
    SUNBEAM,
    WINDOW_PERCH,
    THE_CARDBOARD_BOX,
    THE_STOLEN_HAIR_TIE,
    THE_HEATED_BLANKET,
)


# -----------------------------------------------------------------------------
# Deck 1 — Couch Empire (Territory Control)
# -----------------------------------------------------------------------------
# Pinnacle plan: high-value Sleek presence with Territory-trinket pile-stacking.
# Karen lets us cram 3 Trinkets per pile (vs the default 2); Yarn Ball gives
# +1 score per Sleek in Territory, Window Perch gives +1 at >=4 cards and a
# draw-2 when capped, Heated Blanket fattens Nap, Cardboard Box softens Snack.
# Mostly Sleek+Fluffy mid-high so we win tricks under the default rule.
COUCH_EMPIRE: list = [
    # --- Trinkets (5) ---  Karen lets multiple trinkets share a pile.
    YARN_BALL,                     # Territory: +1 per Sleek
    WINDOW_PERCH,                  # Territory: +1 at >=4, draw 2 at cap
    THE_HEATED_BLANKET,            # Nap: +1 per card up to +4
    THE_CARDBOARD_BOX,             # Snack: +1 score while <5
    THE_STOLEN_HAIR_TIE,           # Attention drip (tiebreak insurance)

    # --- Sleek heavy hitters (8) ---  win-by-Value engine
    THE_MAGNIFICENT_BARTHOLOMEW,   # 10  (Sleek bomb)
    THE_BRIGADIER,                 # 9
    MISTER_WHISKERS,               # 7   (peek opp hand on win)
    DUCHESS_VELVET,                # 6   (draw on win)
    MITTENS_MCSOPHISTICATED,       # 5   (attn marker on territory entry)
    CRUMPET,                       # 4
    LORD_TUFTS,                    # 3   (draw on lose; consolation)
    TABITHA,                       # 2

    # --- Fluffy mid (5) ---  more "highest wins" anchors
    EMPRESS_POMF,                  # 9   (draw + life on win)
    SERGEANT_SNUGGLES,             # 8
    BISCUIT,                       # 7
    PILLOW_PRINCESS,               # 6   (draw if behind, end of round)
    MARSHMALLOW,                   # 3   (draw on territory entry)

    # --- Scrappy padding (3) ---  high values that win Sleek default rule too
    MAXIMUM_CARNAGE,               # 10  (win=+score, lose=draw — incredible)
    THE_YOWLING_STRANGER,          # 8
    THE_BEDRAGGLED_EARL,           # 5   (snack-pile draw)

    # --- Moods (3) ---  defensive rule swaps if a Scrappy/Sneaky opens
    THE_QUIET_INTERROGATION,       # highest wins (locks Sleek)
    SUDDEN_SUSPICION,              # highest wins
    AGGRESSIVE_LOAFING,            # whoever has more piles wins (snowball)

    # --- Snacks (3) ---  forcing tools when we don't want to be Snack-locked
    THAT_ONE_THING_OFF_THE_COUNTER,   # +2 life on snack-entry, V3
    THE_WHOLE_ROAST_CHICKEN,          # draw 2 on snack-entry, V3
    THE_FORBIDDEN_HOUSEPLANT,         # attn marker on snack-entry, V2

    # --- Pomf v2 padding (3) ---  rounding to 30
    EMPRESS_POMF,                  # repeat — winning tricks scales
    MISTER_WHISKERS,               # repeat — peek-on-win again
    DUCHESS_VELVET,                # repeat
]
assert len(COUCH_EMPIRE) == 30, f"Couch Empire: {len(COUCH_EMPIRE)}"


# -----------------------------------------------------------------------------
# Deck 2 — Naptime Tyrants (Nap Stuffing)
# -----------------------------------------------------------------------------
# Pinnacle plan: Reginald (Nap cap 8) + Sunbeam (cap=8, +2 to Nap score) +
# Heated Blanket (+1 per nap card up to +4) lets us potentially store 8 cards
# = 16 base nap pts (vanilla caps at 12 but trinket bonuses stack on top).
# Fluffy cats love the "ties to underdog" rule. Cinnamon Bun for ramp.
NAPTIME_TYRANTS: list = [
    # --- Trinkets (4) ---  Nap-stack + tiebreak insurance
    SUNBEAM,                       # Nap: cap=8, +2 score
    THE_HEATED_BLANKET,            # Nap: +1 per card up to +4
    WINDOW_PERCH,                  # Territory bonus (backup pile)
    THE_STOLEN_HAIR_TIE,           # Attention drip (tiebreak insurance)

    # --- Fluffy core (8) ---  every Fluffy in the pool
    EMPRESS_POMF,                  # 9   (draw+life on win)
    SERGEANT_SNUGGLES,             # 8
    BISCUIT,                       # 7
    PILLOW_PRINCESS,               # 6   (catch-up draw)
    SIR_REGINALD_LOAFINGTON_II,    # 5   (+3 score when Nap caps!)
    CINNAMON_BUN,                  # 4   (draw every 3 rounds)
    MARSHMALLOW,                   # 3   (draw on territory entry)
    TOBY_THE_TUBSTER,              # 1

    # --- Sleek high-rollers for raw value (6 → 5) ---  v4: trimmed 1 Bartholomew (was too much)
    THE_MAGNIFICENT_BARTHOLOMEW,   # 10  (draw 2 on Nap entry — *perfect*)
    THE_BRIGADIER,                 # 9
    MISTER_WHISKERS,               # 7
    DUCHESS_VELVET,                # 6
    EMPRESS_POMF,                  # repeat
    TABITHA,                       # 2 — vanilla padding to keep 30

    # --- Penumbra (Sneaky-but-fluffy with Nap entry) ---
    THE_PENUMBRA_TWIN,             # 6 (Sneaky, draw on Nap-entry)

    # --- Anti-bleed Scrappy ---
    MAXIMUM_CARNAGE,               # 10 (always trades up)
    THE_YOWLING_STRANGER,          # 8

    # --- Moods (4) ---  Aggressive Loafing snowballs once Nap is full
    AGGRESSIVE_LOAFING,            # more-piles wins
    THE_QUIET_INTERROGATION,       # highest wins (lock Sleek rule)
    SUDDEN_SUSPICION,              # highest wins
    THE_DIGNIFIED_SULK,            # fewer-hand wins (we burn cards faster)

    # --- Snacks (3) ---  Roast Chicken draws 2 to refuel the engine
    THE_WHOLE_ROAST_CHICKEN,
    THAT_ONE_THING_OFF_THE_COUNTER,
    THAT_ONE_THING_OFF_THE_COUNTER,

    # --- Sleek mid padding (2) ---  more reliable trick winners
    MITTENS_MCSOPHISTICATED,        # 5
    CRUMPET,                        # 4
]
assert len(NAPTIME_TYRANTS) == 30, f"Naptime Tyrants: {len(NAPTIME_TYRANTS)}"


# -----------------------------------------------------------------------------
# Deck 3 — Snack Rush  [v3 — promoted from candidate; replaces v2]
# -----------------------------------------------------------------------------
# Pinnacle plan: 4 high-value snacks + 14 bombs that reliably win snack tricks.
# Replaces the v2 11-snack spam (which feeds opponent's Snack pile by losing
# tricks). v3 was a build-decks candidate that beat the original by +12.2pp
# in the 8-deck tournament.
SNACK_RUSH: list = [
    # --- High-value Snacks only (4 unique, 6 with repeats) ---
    THE_WHOLE_ROAST_CHICKEN,       # 3 (draws 2 on snack-entry)
    THE_WHOLE_ROAST_CHICKEN,       # repeat — best snack twice
    THAT_ONE_THING_OFF_THE_COUNTER,# 3 (gain 2 score on snack-entry)
    THAT_ONE_THING_OFF_THE_COUNTER,# repeat
    CATNIP_MOUSE,                  # 2 (draws 1)
    THE_DISPUTED_SLICE_OF_CHEESE,  # 2

    # --- Cardboard Box ---  +1/card while <5
    THE_CARDBOARD_BOX,

    # --- Bedraggled Earls (2) ---  Scrappy 5, snack-entry draw
    THE_BEDRAGGLED_EARL,
    THE_BEDRAGGLED_EARL,

    # --- High-Value bombs (5) ---  WIN the snack tricks
    THE_MAGNIFICENT_BARTHOLOMEW,   # Sleek 10
    THE_BRIGADIER,                 # Sleek 9
    MISTER_WHISKERS,               # Sleek 7
    DUCHESS_VELVET,                # Sleek 6 (draw on win)
    EMPRESS_POMF,                  # Fluffy 9 (draw + life on win)

    # --- More Sleek/Fluffy mids (4) ---
    SERGEANT_SNUGGLES,             # Fluffy 8
    BISCUIT,                       # Fluffy 7
    MITTENS_MCSOPHISTICATED,       # Sleek 5
    CRUMPET,                       # Sleek 4

    # --- Sneaky bombs (3) ---
    THE_UNOBSERVED,                # 9/10
    WHISPERTOES,                   # 2/9 (draw on win)
    THE_PENUMBRA_TWIN,             # 6/7

    # --- Scrappy bomb (1) ---
    MAXIMUM_CARNAGE,               # 10 (lose: draw)

    # --- Moods (3) ---  rule-distortion when we'd otherwise lose
    THE_3AM_ZOOMIES,               # lowest wins
    KNOCKING_THINGS_OFF_TABLES,    # lowest wins
    SITTING_IN_THE_BOX,            # fewer-hand wins

    # --- Trinket (1) ---
    THE_STOLEN_HAIR_TIE,           # attention drip — tiebreak insurance

    # --- Vanilla padding + utility (4) ---
    TABITHA,                       # Sleek 2 — vanilla bait
    THE_YOWLING_STRANGER,          # Scrappy 8 vanilla
    PRINCESS_MAYHEM_THE_FOURTH,    # Scrappy 3 — draw on win
    THE_FORBIDDEN_HOUSEPLANT,      # Snack 2 — attn marker on snack-entry
]
assert len(SNACK_RUSH) == 30, f"Snack Rush: {len(SNACK_RUSH)}"


# -----------------------------------------------------------------------------
# Deck 4 — Shadow Cats (Sneaky + Mood chaos)  [v3 — post P0-fix rebalance]
# -----------------------------------------------------------------------------
# After Phase 4's P0 fix wired on_win/on_lose REACT events, Shadow Cats's
# Mood-rule-swaps + on-win draws compounded into a 76.7% dominance. v3 trims
# Mood count from 8 to 4 (right-sizing the rule-swap budget) and adds more
# vanilla Sneakies + Penumbra/Madam Inkblot repeats so the deck still has the
# Sneaky-asymmetry payoff but doesn't dominate via Mood spam.
SHADOW_CATS: list = [
    # --- All 7 unique Sneakies (no extra repeats) — 7 cards ---
    THE_UNOBSERVED,                # 9/10 (bomb)
    MADAM_INKBLOT,                 # 7/2  (draws 2 on lose)
    THE_PENUMBRA_TWIN,             # 6/7  (Nap draw on entry)
    KNIVES,                        # 5/6
    MIDNIGHT_PANCAKE,              # 4/5
    WHISPERTOES,                   # 2/9  (draw on win)
    THE_SHADOW_LOAF,               # 1/8

    # --- Moods (4) ---  the rule-swap toolkit
    THE_3AM_ZOOMIES,               # lowest wins
    AGGRESSIVE_LOAFING,            # more-piles wins
    SITTING_IN_THE_BOX,            # fewer-hand wins
    THE_INSCRUTABLE_STARE,         # equal wins

    # --- HIGH-VALUE BOMBS (3) ---  v4: trimmed from 5 to 3 (still loaded with Sneaky asymmetry)
    EMPRESS_POMF,                  # Fluffy 9 (draw + life on win)
    MISTER_WHISKERS,               # Sleek 7
    DUCHESS_VELVET,                # Sleek 6 (draw on win)

    # --- Catch-up + utility (3) ---
    PILLOW_PRINCESS,               # Fluffy 6 (round-end catch-up draw)
    SERGEANT_SNUGGLES,             # Fluffy 8
    BISCUIT,                       # Fluffy 7

    # --- Low-value bait (3) ---  v4: more bait, less raw power
    GARY_JUNIOR,                   # Scrappy 1 (vanilla)
    PRINCESS_MAYHEM_THE_FOURTH,    # Scrappy 3 (draw on win)
    THE_ALLEY_PHANTOM,             # Scrappy 2 (draw on lose)

    # --- Trinket (1) ---
    THE_STOLEN_HAIR_TIE,           # Attention drip (tiebreak)

    # --- Vanilla padding (3) ---  more vanilla, less bomb
    A_SINGLE_CRUMB,                # 1 — Snack-force grenade
    TABITHA,                       # Sleek 2 — vanilla bait
    CRUMPET,                       # Sleek 4 — vanilla

    # --- Extra vanilla padding (6) ---  v4: fill out the 6 slots removed from bombs/Sneaky-overflow
    LORD_TUFTS,                    # Sleek 3 (draw on lose)
    ONE_TOOTH_EDUARDO,             # Scrappy
    TOBY_THE_TUBSTER,              # Fluffy 1 vanilla
    TUNA_CAN,                      # Snack 1
    THAT_ONE_THING_OFF_THE_COUNTER,# Snack 3 (life on snack entry)
    MITTENS_MCSOPHISTICATED,       # Sleek 5 (attn on territory)
]
assert len(SHADOW_CATS) == 30, f"Shadow Cats: {len(SHADOW_CATS)}"


# =============================================================================
# Candidate decks (challengers) — added after baseline tournament.
#
# Each deck below tests a strategic hypothesis distinct from the original 4.
# They share the existing 60-card pool; only the build philosophy is new.
# =============================================================================


# -----------------------------------------------------------------------------
# Deck 5 — Greg's Diary (Card-Quality + Catch-Up)
# -----------------------------------------------------------------------------
# Commander: Greg. Passive: at round start, if Greg's controller has fewer
# total pile cards than opponent, draw 1.
#
# Hypothesis: STAY BEHIND deliberately. Tempo-trade losing tricks for draw
# triggers (Madam Inkblot loses → draw 2; Alley Phantom + Lord Tufts lose →
# draw 1; Pillow Princess round-end "behind" draw; Greg catch-up draw on
# round start). Convert that hand-size advantage into late-game bomb commits
# (Bartholomew, Brigadier, Pomf, Unobserved) when piles are still empty enough
# to fire pile-entry triggers. The Dignified Sulk reinforces the plan by
# letting the fewer-hand player win — except we WANT a big hand, so Sulk is
# situational counter-pounce.
#
# Key card-quality engine: Madam Inkblot loses → +2 draws is the best
# "intentional loss" payoff in the pool. We run 2 copies.
GREG_DIARY: list = [
    # --- Sleek bombs (4) ---  late-game commits
    THE_MAGNIFICENT_BARTHOLOMEW,   # 10 — draw 2 on Nap entry
    THE_BRIGADIER,                 # 9  — vanilla high
    MISTER_WHISKERS,               # 7  — peek = card-quality info
    DUCHESS_VELVET,                # 6  — draw on win

    # --- Lord Tufts x2 (2) ---  draw on lose, intentional bait
    LORD_TUFTS,                    # 3  — draw on lose
    LORD_TUFTS,                    # repeat

    # --- Fluffy catch-up engine (4) ---
    PILLOW_PRINCESS,               # 6  — round-end "behind" draw
    PILLOW_PRINCESS,               # repeat — double engine
    CINNAMON_BUN,                  # 4  — every 3 rounds draw
    EMPRESS_POMF,                  # 9  — draw + life on win

    # --- Sneaky high-quality (4) ---  Greg cares about quality not value
    THE_UNOBSERVED,                # 9/10 bomb
    MADAM_INKBLOT,                 # 7/2  — DRAW 2 ON LOSE (perfect Greg)
    MADAM_INKBLOT,                 # repeat — stack the lose-engine
    WHISPERTOES,                   # 2/9 — draw on win, looks low
    THE_PENUMBRA_TWIN,             # 6/7 — Nap entry draw

    # --- Scrappy "draw on lose" (3) ---
    THE_ALLEY_PHANTOM,             # 2  — draw on lose
    THE_ALLEY_PHANTOM,             # repeat
    MAXIMUM_CARNAGE,               # 10 — win+1 or lose+draw (both good)

    # --- Trinkets (3) ---
    WINDOW_PERCH,                  # Territory: cap → draw 2 (big payoff)
    THE_STOLEN_HAIR_TIE,           # Attention drip — every claim
    SUNBEAM,                       # Nap cap=8, +2 score

    # --- Moods (4) ---  Sulk + Stare = "be behind, still win"
    THE_DIGNIFIED_SULK,            # fewer-hand wins (situational)
    THE_INSCRUTABLE_STARE,         # equal wins (defensive)
    SITTING_IN_THE_BOX,            # fewer-hand wins
    THE_3AM_ZOOMIES,               # lowest wins — flip a bait

    # --- Snacks for draw (3) ---  pure draw engines
    THE_WHOLE_ROAST_CHICKEN,       # V3 — draw 2 on Snack entry
    THE_WHOLE_ROAST_CHICKEN,       # repeat
    CATNIP_MOUSE,                  # V2 — draw 1 on Snack entry

    # --- Sleek padding (2) ---  v1: dropped Biscuit (over by 1)
    MITTENS_MCSOPHISTICATED,       # 5 — attn marker on Territory
    THE_YOWLING_STRANGER,          # 8 — Scrappy high (junk vs Sleek default)
]
GREG_DIARY = list(GREG_DIARY)
assert len(GREG_DIARY) == 30, f"Greg's Diary: {len(GREG_DIARY)}"


# -----------------------------------------------------------------------------
# Deck 6 — Fluffinbottom Attention (Pile-Inversion)
# -----------------------------------------------------------------------------
# Commander: Lord Fluffinbottom. Passive: at game end, +5 score if controller
# has the most Attention pile cards (and >0).
#
# Hypothesis: Cats's Attention pile is a designed tiebreaker — but with
# Fluffinbottom + the Stolen Hair Tie x2 + Mittens x2 + 10 Moods (each Mood
# drops an attn marker when claimed) + Forbidden Houseplant x2 (snack entry
# → attn) you can easily land 8+ attention markers and lock the +5 bonus
# AND the tiebreaker. We don't care if regular pile scoring is weak — the
# +5 bonus offsets a lot. Forbidden Houseplant + Hair Tie + Mittens =
# guaranteed attention drip on every claim regardless of trick outcome.
#
# Risk: Moods are Value 0 — we lose value comparisons unless the Mood rule
# helps us. Five lowest-wins Moods plus a hand of cheap low-value bait
# (Toby, Tabitha, Gary Junior, Whispertoes) means we can WIN those mood
# tricks ourselves and claim the attention marker.
FLUFFINBOTTOM_ATTENTION: list = [
    # --- ALL 10 Moods (10) ---  each Mood when claimed drops attn marker
    THE_3AM_ZOOMIES,               # lowest wins
    SITTING_IN_THE_BOX,            # fewer-hand wins
    AGGRESSIVE_LOAFING,            # more-piles wins
    KNOCKING_THINGS_OFF_TABLES,    # lowest wins
    THE_QUIET_INTERROGATION,       # highest wins
    WET_FOOD_O_CLOCK,              # lowest wins
    THE_DIGNIFIED_SULK,            # fewer-hand wins
    SUDDEN_SUSPICION,              # highest wins
    THE_DRAMATIC_RECOVERY,         # lowest wins
    THE_INSCRUTABLE_STARE,         # equal wins

    # --- Hair Tie x2 (2) ---  EVERY claim drips attn marker
    THE_STOLEN_HAIR_TIE,
    THE_STOLEN_HAIR_TIE,

    # --- Mittens x2 (2) ---  Territory entry → attn marker
    MITTENS_MCSOPHISTICATED,       # 5
    MITTENS_MCSOPHISTICATED,       # repeat

    # --- Forbidden Houseplant x2 (2) ---  Snack entry → attn marker
    THE_FORBIDDEN_HOUSEPLANT,      # V2
    THE_FORBIDDEN_HOUSEPLANT,      # repeat

    # --- Trinket: backup pile (1) ---
    YARN_BALL,                     # Territory: +1 per Sleek

    # --- Low-value bait (5) ---  win lowest-wins Moods with these
    TOBY_THE_TUBSTER,              # 1 Fluffy
    GARY_JUNIOR,                   # 1 Scrappy
    TABITHA,                       # 2 Sleek
    LORD_TUFTS,                    # 3 Sleek — also draw on lose
    THE_ALLEY_PHANTOM,             # 2 Scrappy — draw on lose

    # --- Sneaky bluffs (3) ---  hidden value matters less but Whispertoes
    # public V2 + S9 means we look weak but win
    WHISPERTOES,                   # 2/9 — draw on win
    THE_SHADOW_LOAF,               # 1/8
    MIDNIGHT_PANCAKE,              # 4/5

    # --- High-value insurance (4) ---  one or two normal trick wins
    THE_MAGNIFICENT_BARTHOLOMEW,   # 10
    EMPRESS_POMF,                  # 9 — draw + life
    MISTER_WHISKERS,               # 7
    DUCHESS_VELVET,                # 6 — draw on win

    # --- Catnip Mouse (1) ---  Snack entry draw for tempo
    CATNIP_MOUSE,                  # V2
]
FLUFFINBOTTOM_ATTENTION = list(FLUFFINBOTTOM_ATTENTION)
assert len(FLUFFINBOTTOM_ATTENTION) == 30, f"Fluffinbottom Attention: {len(FLUFFINBOTTOM_ATTENTION)}"


# -----------------------------------------------------------------------------
# Deck 7 — Snack Rush v3 (Tight Bomb Chain)
# -----------------------------------------------------------------------------
# Commander: Princess Mayhem the Third (unchanged). Passive: +1 pt/card while
# Snack pile <5 cards.
#
# Original Snack Rush ran ALL 8 unique Snacks — but the LLM tournament showed
# 33.3% win rate because low-value snacks (V1 baits) gave OPPONENTS the snack-
# force win and FED their pile. v3 keeps Princess Mayhem and the small-pile
# bonus plan but commits to FOUR snacks ONLY (the V3 ones + 1 utility V2),
# all of which we will win by surrounding them with raw-value bombs.
#
# Math: 4 cards in Snack pile = 4 * (3 base + 1 Cardboard Box + 1 Mayhem) = 20
# points, plus on-entry effects: Roast Chicken x2 = 4 draws, Counter Thing x2
# = +4 score, Catnip Mouse = 1 draw, Bedraggled Earl x2 = 2 draws. Net of
# tempo: ~28-30 points from snack package alone.
#
# Replacing 11 low-value snack baits with high-value bombs: this is the LLM
# tournament's diagnosed fix. Now we WIN snack tricks because we play V8-10
# cats alongside the snacks.
SNACK_RUSH_V3: list = [
    # --- 4 best snacks ONLY (6 with repeats) ---
    THE_WHOLE_ROAST_CHICKEN,       # V3 — draw 2 on Snack entry
    THE_WHOLE_ROAST_CHICKEN,       # repeat
    THAT_ONE_THING_OFF_THE_COUNTER,# V3 — +2 score on Snack entry
    THAT_ONE_THING_OFF_THE_COUNTER,# repeat
    CATNIP_MOUSE,                  # V2 — draw 1 on entry (utility)
    THE_DISPUTED_SLICE_OF_CHEESE,  # V2 — vanilla mid (not a bait, decent)

    # --- Cardboard Box (1) ---  +1 score while <5
    THE_CARDBOARD_BOX,

    # --- Bedraggled Earl x2 (2) ---  Scrappy V5, draws on Snack entry
    THE_BEDRAGGLED_EARL,
    THE_BEDRAGGLED_EARL,

    # --- Sleek high-value bombs (6) ---  WIN every snack trick
    THE_MAGNIFICENT_BARTHOLOMEW,   # 10
    THE_BRIGADIER,                 # 9
    MISTER_WHISKERS,               # 7 — peek for snack-pile cap awareness
    DUCHESS_VELVET,                # 6 — draw on win
    DUCHESS_VELVET,                # repeat
    MITTENS_MCSOPHISTICATED,       # 5

    # --- Fluffy bombs (3) ---
    EMPRESS_POMF,                  # 9 — draw + life on win
    EMPRESS_POMF,                  # repeat
    SERGEANT_SNUGGLES,             # 8 vanilla

    # --- Scrappy raw value (2) ---
    MAXIMUM_CARNAGE,               # 10 — win+1 or lose+draw
    THE_YOWLING_STRANGER,          # 8

    # --- Sneaky bombs (3) ---  bluffs that win
    THE_UNOBSERVED,                # 9/10
    WHISPERTOES,                   # 2/9 — draw on win
    THE_PENUMBRA_TWIN,             # 6/7

    # --- Moods (3) ---  lowest-wins flips when we hold a snack
    THE_3AM_ZOOMIES,               # lowest wins
    KNOCKING_THINGS_OFF_TABLES,    # lowest wins
    WET_FOOD_O_CLOCK,              # lowest wins

    # --- Trinket (1) ---  attention tiebreak
    THE_STOLEN_HAIR_TIE,

    # --- Vanilla padding (3) ---
    BISCUIT,                       # 7 Fluffy
    CRUMPET,                       # 4 Sleek
    TABITHA,                       # 2 Sleek
]
SNACK_RUSH_V3 = list(SNACK_RUSH_V3)
assert len(SNACK_RUSH_V3) == 30, f"Snack Rush v3: {len(SNACK_RUSH_V3)}"


# -----------------------------------------------------------------------------
# Deck 8 — Naptime Denial (Anti-Naptime Counter-Deck)
# -----------------------------------------------------------------------------
# Commander: Gary the One-Eyed Tabby. Passive: our Sneaky cards use printed
# Value (not the hidden sneaky_value) — i.e. we ALWAYS win when our printed
# value is higher under Sleek default. Effectively the opposite of Sneaky:
# our bluffs become honest bombs.
#
# Hypothesis: Naptime Tyrants won 66.7% under LLM piloting via Reginald +
# Heated Blanket + Bartholomew nap-stuffing. To beat it we must:
#   (a) WIN trick exchanges so they can't stuff Nap — raw value bombs +
#       Gary-transparent Sneakies that win at printed value.
#   (b) DISRUPT their rule openings — 5 Moods to swap when Naptime opens
#       with Fluffy "highest wins, underdog ties." Lowest-wins Moods flip
#       Reginald's high-Value Fluffies into our low-Value wins.
#   (c) POISON their Nap stack — 4 Snacks ensure that EVERY trick containing
#       a snack forces the winner's claim into Snack (not Nap). We dump junk
#       snacks (Tuna Can, Single Crumb) when Reginald wants to claim into
#       Nap — they get forced into Snack instead, denying the nap pile cap.
#   (d) STEAL Nap for ourselves with Sunbeam (cap=8, +2) so when we do win
#       we still get our own nap engine.
#
# This is the only deck in the set that explicitly tries to break a SPECIFIC
# matchup rather than maximize its own scoring.
NAPTIME_DENIAL: list = [
    # --- 6 of 7 Sneakies (6) ---  Gary makes us win at printed value
    THE_UNOBSERVED,                # 9 (printed; sneaky 10) — pure bomb
    MADAM_INKBLOT,                 # 7 (printed; sneaky 2) — Gary turns
                                   #    her HIGH-value win + on-lose draw
    KNIVES,                        # 5
    THE_PENUMBRA_TWIN,             # 6 — Nap entry draw
    WHISPERTOES,                   # 2 — also draw on win
    THE_SHADOW_LOAF,               # 1 — sacrificial bait

    # --- Moods (5) ---  rule disruption — Counter-pounce Reginald
    THE_3AM_ZOOMIES,               # lowest wins (flips their Pomf 9)
    SITTING_IN_THE_BOX,            # fewer-hand wins
    AGGRESSIVE_LOAFING,            # more-piles wins (smug)
    THE_QUIET_INTERROGATION,       # highest wins (lock Sleek default)
    KNOCKING_THINGS_OFF_TABLES,    # lowest wins — second flip option

    # --- High-value bombs (7) ---  defeat Naptime's mid-Fluffies
    THE_MAGNIFICENT_BARTHOLOMEW,   # 10 — Bart in OUR nap = +2 draws
    THE_BRIGADIER,                 # 9
    EMPRESS_POMF,                  # 9 — draw + life
    MISTER_WHISKERS,               # 7 — peek their hand
    DUCHESS_VELVET,                # 6 — draw on win
    SERGEANT_SNUGGLES,             # 8 vanilla
    MAXIMUM_CARNAGE,               # 10 — lose:draw (post-nerf)

    # --- Snacks (4) ---  POISON: every winning trick → Snack, not Nap
    THE_WHOLE_ROAST_CHICKEN,       # V3 — when WE win, draws 2
    THAT_ONE_THING_OFF_THE_COUNTER,# V3 — when WE win, +2 score
    TUNA_CAN,                      # V1 — junk we DUMP when opp will win
    A_SINGLE_CRUMB,                # V1 — junk we DUMP when opp will win

    # --- Trinkets (3) ---  own-nap engine + scoring base
    SUNBEAM,                       # Nap cap=8, +2 score (we keep Nap viable)
    THE_CARDBOARD_BOX,             # Snack +1 while <5 (we benefit from forces)
    THE_STOLEN_HAIR_TIE,           # attention drip — tiebreak insurance

    # --- Catch-up + utility (3) ---
    PILLOW_PRINCESS,               # 6 — round-end behind draw
    THE_ALLEY_PHANTOM,             # 2 — draw on lose (junk dump)
    THE_YOWLING_STRANGER,          # 8 Scrappy vanilla

    # --- Filler (2) ---
    CRUMPET,                       # 4 vanilla
    MITTENS_MCSOPHISTICATED,       # 5 — attn marker on Territory
]
NAPTIME_DENIAL = list(NAPTIME_DENIAL)
assert len(NAPTIME_DENIAL) == 30, f"Naptime Denial: {len(NAPTIME_DENIAL)}"


# -----------------------------------------------------------------------------
# Aggregate
# -----------------------------------------------------------------------------

CATS_DECKS: dict = {
    # Canonical archetypes (post deckbuilding pass). Snack Rush is now the
    # v3 (high-value bomb chain). Fluffinbottom Attention was a rejected
    # hypothesis from /build-decks (15.1% in 8-deck tournament) and isn't
    # registered; the SNACK_RUSH_V3 alias is kept as a re-export for tests.
    "Couch Empire":          (KAREN_THE_DIGNIFIED_CALICO,   COUCH_EMPIRE),
    "Naptime Tyrants":       (SIR_REGINALD_LOAFINGTON,      NAPTIME_TYRANTS),
    "Snack Rush":            (PRINCESS_MAYHEM_THE_THIRD,    SNACK_RUSH),
    "Shadow Cats":           (GARY_THE_ONE_EYED_TABBY,      SHADOW_CATS),
    "Greg's Diary":          (GREG,                         GREG_DIARY),
    "Naptime Denial":        (GARY_THE_ONE_EYED_TABBY,      NAPTIME_DENIAL),
}

# Back-compat alias: the build-decks subagent named the new Snack archetype
# SNACK_RUSH_V3. It's now the canonical SNACK_RUSH; keep the alias so any
# external imports / tests still resolve.
SNACK_RUSH_V3 = SNACK_RUSH

__all__ = [
    "CATS_DECKS",
    "COUCH_EMPIRE",
    "NAPTIME_TYRANTS",
    "SNACK_RUSH",
    "SHADOW_CATS",
    "GREG_DIARY",
    "FLUFFINBOTTOM_ATTENTION",
    "SNACK_RUSH_V3",
    "NAPTIME_DENIAL",
]
