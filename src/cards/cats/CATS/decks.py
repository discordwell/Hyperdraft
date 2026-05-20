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
# Deck 3 — Snack Rush (Snack Forcing)  [v2 buff after first tournament]
# -----------------------------------------------------------------------------
# Pinnacle plan: Snacks force every trick they touch into the WINNER'S Snack
# pile, so we MUST win the snack tricks ourselves — otherwise we're feeding
# the opponent. Princess Mayhem (+1 pt/card while <5) + Cardboard Box (+1 score
# while <5) means 4 snack cards under both bonuses score 4×(3+1+1) = 20 pts.
#
# First-tournament finding: too many low-value baits caused us to LOSE snack
# tricks and gift opp's Snack pile. v2 buff swaps baits for high-Value Sleek
# bombs (Bartholomew, Brigadier, Pomf) so we win the snack tricks directly.
# Lowest-Wins Moods are kept as a flexible escape valve when opp opens with
# something we'd otherwise lose to.
SNACK_RUSH: list = [
    # --- All 8 Snacks ---
    THE_WHOLE_ROAST_CHICKEN,       # 3 (draws 2 on snack-entry)
    THAT_ONE_THING_OFF_THE_COUNTER,# 3 (gain 2 score on snack-entry)
    CATNIP_MOUSE,                  # 2 (draws 1)
    THE_DISPUTED_SLICE_OF_CHEESE,  # 2
    THE_FORBIDDEN_HOUSEPLANT,      # 2 (attn marker)
    TUNA_CAN,                      # 1
    A_SINGLE_CRUMB,                # 1
    EMPTY_YOGURT_CUP,              # 1

    # --- Duplicate best snacks (3) ---
    THE_WHOLE_ROAST_CHICKEN,
    THAT_ONE_THING_OFF_THE_COUNTER,
    CATNIP_MOUSE,

    # --- Cardboard Box ---  +1 per snack-card while <5
    THE_CARDBOARD_BOX,

    # --- Snack-synergy support ---
    THE_BEDRAGGLED_EARL,           # Scrappy 5, draws on snack-entry

    # --- High-Value bombs (5) ---  WIN the snack tricks
    THE_MAGNIFICENT_BARTHOLOMEW,   # Sleek 10
    THE_BRIGADIER,                 # Sleek 9
    MISTER_WHISKERS,               # Sleek 7
    DUCHESS_VELVET,                # Sleek 6
    EMPRESS_POMF,                  # Fluffy 9 (draw+life on win)

    # --- Sneaky bombs (3) ---  Whispertoes/Inkblot trick wins
    WHISPERTOES,                   # 2/9 — wins under Sneaky, draws on win
    THE_UNOBSERVED,                # 9/10 vanilla high
    THE_PENUMBRA_TWIN,             # 6/7

    # --- Mid Scrappies that are still good under highest-wins (3) ---
    MAXIMUM_CARNAGE,               # Scrappy 10 (win+life or lose+draw)
    THE_YOWLING_STRANGER,          # Scrappy 8
    PRINCESS_MAYHEM_THE_FOURTH,    # Scrappy 3 (draw on win)

    # --- Moods (4) ---  rule-distortion to flip losing tricks into wins
    THE_3AM_ZOOMIES,               # lowest wins (when we lead with a Snack)
    KNOCKING_THINGS_OFF_TABLES,    # lowest wins
    WET_FOOD_O_CLOCK,              # lowest wins
    SITTING_IN_THE_BOX,            # fewer-hand wins

    # --- More snack-engine reliability + tiebreak (2) ---
    THE_BEDRAGGLED_EARL,           # repeat — Scrappy 5, draws on snack-entry
    THE_STOLEN_HAIR_TIE,           # Attention drip (tiebreak)
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


# -----------------------------------------------------------------------------
# Aggregate
# -----------------------------------------------------------------------------

CATS_DECKS: dict = {
    "Couch Empire":   (KAREN_THE_DIGNIFIED_CALICO,   COUCH_EMPIRE),
    "Naptime Tyrants":(SIR_REGINALD_LOAFINGTON,      NAPTIME_TYRANTS),
    "Snack Rush":     (PRINCESS_MAYHEM_THE_THIRD,    SNACK_RUSH),
    "Shadow Cats":    (GARY_THE_ONE_EYED_TABBY,      SHADOW_CATS),
}

__all__ = [
    "CATS_DECKS",
    "COUCH_EMPIRE",
    "NAPTIME_TYRANTS",
    "SNACK_RUSH",
    "SHADOW_CATS",
]
