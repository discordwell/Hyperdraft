"""Tests for scripts/play/diagnose_card_fire.py — the /card-fire-debug skill.

Run directly:
    python tests/test_card_fire_debug.py
"""

import asyncio
import os
import sys

# Repo-root insertion so direct invocation works.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip(
        "Run directly: `python tests/test_card_fire_debug.py`",
        allow_module_level=True,
    )

from scripts.play.diagnose_card_fire import (
    _run_pokemon_diagnostic_game,
    _run_scp_diagnostic_game,
    CardTelemetry,
    diagnose,
    diagnose_scp,
)


# Seed the global RNG so the Pokemon probe (which uses random.shuffle for
# library order + mulligans) is deterministic across runs — otherwise Voidmage's
# draw is luck-dependent and Test 1/2 flake. The SCP probe seeds itself per game.
import random
random.seed(20260529)

passed = 0
failed = 0


def check(name, condition, hint=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} ({hint})")
        failed += 1


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Test 1: Voidmage Apprentice — known PASS after BRV gap-closure
# =============================================================================

print("\n=== Test 1: Voidmage Apprentice (PASS expected) ===")

aggregate = CardTelemetry(card_name="Voidmage Apprentice")
# Use 5 games to absorb variance from heuristic randomness.
for i in range(5):
    tele = run(_run_pokemon_diagnostic_game(
        card_name="Voidmage Apprentice",
        p1_deck_name="dimir",
        p2_deck_name="golgari",
        p1_bias="lz_engine",
        p2_bias="lz_engine",
        max_turns=30,
    ))
    aggregate.merge(tele)
if aggregate.games_run > 0:
    aggregate.deck_count_p1 //= aggregate.games_run
    aggregate.deck_count_p2 //= aggregate.games_run

steps, verdict, patch = diagnose(aggregate)
print(f"  verdict: {verdict}")
print(f"  steps: {len(steps)}")
for st in steps:
    flag = "OK" if st.passed else "X"
    print(f"    [{flag}] {st.name}")

check(
    "Voidmage diagnostic runs",
    aggregate.games_run == 5,
    f"only {aggregate.games_run}/5 games completed",
)
check(
    "Voidmage in dimir deck",
    aggregate.deck_count_p1 == 2,
    f"deck count P1={aggregate.deck_count_p1}",
)
check(
    "Voidmage drawn across games",
    aggregate.drawn_count > 0,
    f"drawn {aggregate.drawn_count} turns",
)
primary_scores = aggregate.primary_scores()
check(
    "Voidmage scorer returns positive somewhere",
    primary_scores and max(primary_scores) > 0,
    f"primary scores max {max(primary_scores) if primary_scores else 'n/a'}",
)
check(
    "Voidmage diagnosis reaches PASS or WARN verdict",
    verdict in ("PASS", "WARN"),
    f"got {verdict}",
)


# =============================================================================
# Test 2: Monkey-patched scorer that returns -100 — Step 3 must catch it
# =============================================================================

print("\n=== Test 2: Broken scorer (Step 3 catches -100) ===")

# Patch _score_basic_play before running so Voidmage gets -100.
from src.ai.pokemon import scoring as scoring_mod

original_score_basic = scoring_mod._score_basic_play


def patched_score_basic(adapter, card, state, player_id):
    if getattr(card, "name", "") == "Voidmage Apprentice":
        return -100.0
    return original_score_basic(adapter, card, state, player_id)


scoring_mod._score_basic_play = patched_score_basic

try:
    # Run enough games to reliably draw Voidmage and exercise step 3.
    broken_aggregate = CardTelemetry(card_name="Voidmage Apprentice")
    for i in range(8):
        tele = run(_run_pokemon_diagnostic_game(
            card_name="Voidmage Apprentice",
            p1_deck_name="dimir",
            p2_deck_name="golgari",
            p1_bias="lz_engine",
            p2_bias="lz_engine",
            max_turns=30,
        ))
        broken_aggregate.merge(tele)
    if broken_aggregate.games_run > 0:
        broken_aggregate.deck_count_p1 //= broken_aggregate.games_run
        broken_aggregate.deck_count_p2 //= broken_aggregate.games_run

    broken_steps, broken_verdict, broken_patch = diagnose(broken_aggregate)
    print(f"  verdict: {broken_verdict}")
    for st in broken_steps:
        flag = "OK" if st.passed else "X"
        print(f"    [{flag}] {st.name}")
    print(f"  primary scores (sample): "
          f"{broken_aggregate.primary_scores()[:5]}")

    # Locate the Step 3 result.
    step3 = next(
        (s for s in broken_steps if s.name.startswith("Step 3")),
        None,
    )
    check(
        "Patched scorer captured -100 in primary bucket",
        broken_aggregate.primary_scores()
        and min(broken_aggregate.primary_scores()) <= -100,
        f"min score {min(broken_aggregate.primary_scores()) if broken_aggregate.primary_scores() else 'n/a'}",
    )
    check(
        "Patched scorer makes diagnosis FAIL",
        broken_verdict == "FAIL",
        f"got {broken_verdict}",
    )
    check(
        "Step 3 result is present",
        step3 is not None,
    )
    check(
        "Step 3 fails (scorer returns <=0)",
        step3 is not None and not step3.passed,
        f"step3 detail: {step3.detail if step3 else 'n/a'}",
    )
    # Suggested patch should mention the scorer.
    check(
        "Suggested patch references scorer fix",
        broken_patch and ("scorer" in broken_patch.lower()
                          or "_score_" in broken_patch),
        f"patch was: {broken_patch[:120]}",
    )
finally:
    scoring_mod._score_basic_play = original_score_basic


# =============================================================================
# Test 3: Card not in any deck — Step 0 catches it
# =============================================================================

print("\n=== Test 3: Card not in deck — Step 0 catches it ===")

missing_aggregate = CardTelemetry(card_name="Made Up Card 999")
tele = run(_run_pokemon_diagnostic_game(
    card_name="Made Up Card 999",
    p1_deck_name="dimir",
    p2_deck_name="golgari",
    p1_bias="lz_engine",
    p2_bias="lz_engine",
    max_turns=10,
))
missing_aggregate.merge(tele)
if missing_aggregate.games_run > 0:
    missing_aggregate.deck_count_p1 //= missing_aggregate.games_run
    missing_aggregate.deck_count_p2 //= missing_aggregate.games_run

missing_steps, missing_verdict, missing_patch = diagnose(missing_aggregate)
print(f"  verdict: {missing_verdict}")
for st in missing_steps:
    flag = "OK" if st.passed else "X"
    print(f"    [{flag}] {st.name}")

check(
    "Missing-card diagnosis returns FAIL",
    missing_verdict == "FAIL",
)
check(
    "Step 0 (card in deck) fails",
    missing_steps and missing_steps[0].name.startswith("Step 0")
    and not missing_steps[0].passed,
)
check(
    "Suggested patch suggests verifying spelling/deck builder",
    missing_patch and any(
        token in missing_patch.lower()
        for token in ("spelling", "deck builder", "deck")
    ),
    f"patch was: {missing_patch[:120]}",
)


# =============================================================================
# Test 4: SCP diagnose_scp decision tree (synthetic telemetry — deterministic)
# =============================================================================

print("\n=== Test 4: SCP diagnose_scp decision tree (synthetic) ===")


def _scp_tele(**kw) -> CardTelemetry:
    t = CardTelemetry(card_name="Synthetic SCP Card", games_run=3)
    for k, v in kw.items():
        setattr(t, k, v)
    return t


# Step 0 — not in any deck.
s, v, p = diagnose_scp(_scp_tele(deck_count_p1=0, deck_count_p2=0))
check("scp Step 0: not in deck -> FAIL",
      v == "FAIL" and s[0].name.startswith("Step 0"), f"verdict {v}")

# Step 1 — in deck but never drawn.
s, v, p = diagnose_scp(_scp_tele(deck_count_p1=1, drawn_count=0))
check("scp Step 1: never drawn -> FAIL",
      v == "FAIL" and any(st.name.startswith("Step 1") and not st.passed for st in s),
      f"verdict {v}")

# Step 2 — drawn but never deployed (the deploy-race failure).
s, v, p = diagnose_scp(_scp_tele(deck_count_p1=1, drawn_count=5, scp_on_battlefield_turns=0))
check("scp Step 2: never deployed -> FAIL", v == "FAIL" and "deploy" in p.lower(),
      f"verdict {v} patch {p[:60]}")

# Fired — the happy path.
s, v, p = diagnose_scp(_scp_tele(deck_count_p1=1, drawn_count=5, scp_on_battlefield_turns=4,
                                 scp_has_ability=True, scp_times_fired=2))
check("scp fired -> PASS", v == "PASS", f"verdict {v}")

# Value below the fire bar (the calibration failure the inert bombs hit).
s, v, p = diagnose_scp(_scp_tele(deck_count_p1=1, drawn_count=5, scp_on_battlefield_turns=4,
                                 scp_has_ability=True, scp_times_fired=0,
                                 scp_gain=[1.0, 1.0], scp_cost=[0.5], scp_fire_threshold=0.5))
check("scp value below bar -> FAIL with fire-bar patch",
      v == "FAIL" and "fire bar" in p.lower(), f"verdict {v} patch {p[:60]}")

# Ability never scored (gated out before the value check — unaffordable / once_per_turn).
s, v, p = diagnose_scp(_scp_tele(deck_count_p1=1, drawn_count=5, scp_on_battlefield_turns=4,
                                 scp_has_ability=True, scp_times_fired=0, scp_gain=[]))
check("scp gated before scoring -> FAIL", v == "FAIL" and "gated out" in p.lower(),
      f"verdict {v} patch {p[:60]}")

# No activated ability — deploy IS the fire.
s, v, p = diagnose_scp(_scp_tele(deck_count_p1=1, drawn_count=5, scp_on_battlefield_turns=4,
                                 scp_has_ability=False))
check("scp no-ability deployed -> PASS", v == "PASS", f"verdict {v}")


# =============================================================================
# Test 5: SCP probe runs end-to-end on a real deck (Public Spectacle)
# =============================================================================

print("\n=== Test 5: SCP probe on site_zero_masquerade (integration) ===")

scp_agg = CardTelemetry(card_name="SZB Public Spectacle Suite")
for i in range(3):
    tele = run(_run_scp_diagnostic_game(
        card_name="SZB Public Spectacle Suite",
        p1_deck_name="site_zero_masquerade",
        p2_deck_name="site_zero_masquerade",
        difficulty="balanced",
        max_turns=25,
        seed=i,
    ))
    scp_agg.merge(tele)
if scp_agg.games_run > 0:
    scp_agg.deck_count_p1 //= scp_agg.games_run
    scp_agg.deck_count_p2 //= scp_agg.games_run

scp_steps, scp_verdict, scp_patch = diagnose_scp(scp_agg)
print(f"  verdict: {scp_verdict}")
for st in scp_steps:
    print(f"    [{'OK' if st.passed else 'X'}] {st.name}")

check("scp probe ran 3 games", scp_agg.games_run == 3, f"ran {scp_agg.games_run}")
check("scp deck presence detected (1 copy)", scp_agg.deck_count_p1 == 1,
      f"deck count {scp_agg.deck_count_p1}")
check("scp bomb reached the battlefield", scp_agg.scp_on_battlefield_turns > 0,
      f"bf turns {scp_agg.scp_on_battlefield_turns}")
check("scp bomb's activated ability detected", scp_agg.scp_has_ability)
check("scp probe yields a real verdict", scp_verdict in ("PASS", "WARN", "FAIL"),
      f"got {scp_verdict}")


# =============================================================================
# Test 6: missing SCP card — Step 0 catches it on the real probe
# =============================================================================

print("\n=== Test 6: missing SCP card — Step 0 ===")

miss_tele = run(_run_scp_diagnostic_game(
    card_name="Totally Made Up SCP 999",
    p1_deck_name="site_zero_masquerade",
    p2_deck_name="site_zero_masquerade",
    difficulty="balanced",
    max_turns=8,
    seed=0,
))
miss_steps, miss_verdict, miss_patch = diagnose_scp(miss_tele)
check("scp missing card -> FAIL", miss_verdict == "FAIL", f"got {miss_verdict}")
check("scp missing card -> Step 0 fails",
      miss_steps and miss_steps[0].name.startswith("Step 0") and not miss_steps[0].passed)


# =============================================================================
# Summary
# =============================================================================

print(f"\n{'=' * 50}")
print(f"  test_card_fire_debug: {passed} passed, {failed} failed")
print(f"{'=' * 50}")
sys.exit(0 if failed == 0 else 1)
