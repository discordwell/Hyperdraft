"""
coverage — per-card play tracking + force-include deck builder.

The /new-set and /new-game pipelines must guarantee every card in a freshly
generated set is *exercised at least once* during testing, otherwise the
balance metrics for that card are NaN and the smoke test gives false
confidence. This module reads the JSON output of the existing tournament
runner (`scripts/play/custom_set_tournament.py::aggregate`) and reports
which cards never got cast.

JSON contract (input):

    {
      "card_scores": {
        "DOMAIN::Card Name": {
          "games": int,
          "deck_copies": int,
          "cast": int,
          "cast_per_copy": float,
          ...
        },
        ...
      },
      ...
    }

The "DOMAIN" prefix is set during deck-construction (`_card_ref` in the
tournament runner). For our purposes we treat anything matching
`<set_label>::<card>` as belonging to the set under test.

Usage from the slash command:

    python -m scripts.new_set.coverage \\
        --tournament logs/balance_round_3.json \\
        --set MYSET \\
        --card-list /tmp/myset_cards.txt \\
        --out /tmp/coverage_round_3.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


# Cast-coverage thresholds. A card is considered "played at least once"
# if any copy resolved (cast > 0). The "low play" threshold flags cards
# that resolve so rarely that win-contribution stats are unreliable.
MIN_CAST_FOR_COVERAGE = 1
LOW_PLAY_RATE_THRESHOLD = 0.05  # cast / copies-in-deck across all games


@dataclass
class CoverageReport:
    """Result of analyzing a tournament JSON for per-card coverage."""
    set_label: str
    total_cards: int
    cards_with_zero_plays: list[str]
    cards_with_low_play_rate: list[str]   # cast_per_copy < LOW_PLAY_RATE_THRESHOLD
    cards_never_in_deck: list[str]        # in card-list but no deck included them
    coverage_pct: float                   # fraction of cards with cast >= 1


# =============================================================================
# Public API
# =============================================================================

def parse_card_ref(ref: str) -> tuple[str, str] | None:
    """Split 'DOMAIN::CardName' → (domain, name). Returns None if malformed."""
    sep = "::"
    if sep not in ref:
        return None
    domain, name = ref.split(sep, 1)
    return domain.strip(), name.strip()


def domain_matches_set(domain: str, set_label: str) -> bool:
    """True if `domain` belongs to `set_label`.

    The tournament runner uses the *deck pool label* as the `::` prefix,
    not the set code — so a 4-archetype tournament for set "PIRT" emits
    keys under "PIRT_aggro", "PIRT_control", etc. (Convention enforced
    by the /new-set slash command: deck labels are `<SET>_<archetype>`.)

    We match either:
      - exact: domain == set_label              (mirror match, single pool)
      - prefix: domain.startswith(set_label + "_")   (per-archetype pools)

    The `_` separator prevents collisions like "PIRT" matching "PIRTANIA".
    """
    if domain == set_label:
        return True
    return domain.startswith(set_label + "_")


def stats_for_set(
    card_scores: dict[str, dict[str, Any]],
    set_label: str,
) -> dict[str, dict[str, Any]]:
    """Filter card_scores to entries whose domain matches `set_label`.

    A card may show up under multiple deck-label prefixes (e.g. a card
    appearing in both PIRT_aggro and PIRT_control decks). Stats from
    different prefixes are summed per-card so the analyzer sees the
    card's full footprint across all decks in the set, not just one
    archetype's data.

    When entries are summed, derived rates (`cast_per_copy`,
    `win_rate_in_play`) are re-computed from the summed counters —
    sum-of-rates ≠ rate-of-sums. For single-entry cards we leave the
    upstream-aggregator-provided rates alone.
    """
    out: dict[str, dict[str, Any]] = {}
    merge_counts: dict[str, int] = {}
    for ref, stats in card_scores.items():
        parsed = parse_card_ref(ref)
        if not parsed:
            continue
        domain, name = parsed
        if not domain_matches_set(domain, set_label):
            continue
        existing = out.get(name)
        if existing is None:
            # Copy so callers' mutations don't leak back to source.
            out[name] = dict(stats)
            merge_counts[name] = 1
        else:
            for k, v in stats.items():
                if isinstance(v, (int, float)) and isinstance(existing.get(k), (int, float)):
                    existing[k] += v
                # Non-numeric: leave the first-seen value.
            merge_counts[name] += 1
    # Re-derive rates ONLY when we actually summed across multiple
    # archetype-prefixed entries — for single-entry cards the original
    # rates from the upstream aggregator are correct as-is.
    for name, count in merge_counts.items():
        if count <= 1:
            continue
        s = out[name]
        copies = s.get("deck_copies") or 0
        casts = s.get("cast") or 0
        if copies:
            s["cast_per_copy"] = round(casts / copies, 3)
        in_play = s.get("in_play_at_end") or 0
        winning = s.get("on_winning_side") or 0
        if in_play:
            s["win_rate_in_play"] = round(winning / in_play, 3)
    return out


def analyze_coverage(
    tournament: dict[str, Any],
    set_label: str,
    card_list: list[str] | None = None,
) -> CoverageReport:
    """
    Compute coverage metrics for the cards belonging to `set_label`.

    Args:
        tournament: the dict produced by tournament aggregator
                    (must have a "card_scores" key).
        set_label:  the domain/label used when decks for this set were
                    registered (e.g. "MYSET" or the set code).
        card_list:  optional full list of card names that should exist in
                    the set. If provided, names absent from the tournament
                    JSON are reported as "never_in_deck".

    Returns:
        CoverageReport
    """
    card_scores = tournament.get("card_scores") or {}
    set_stats = stats_for_set(card_scores, set_label)

    zero_plays: list[str] = []
    low_rate: list[str] = []
    for name, stats in set_stats.items():
        cast = int(stats.get("cast", 0) or 0)
        rate = float(stats.get("cast_per_copy", 0.0) or 0.0)
        if cast < MIN_CAST_FOR_COVERAGE:
            zero_plays.append(name)
        elif rate < LOW_PLAY_RATE_THRESHOLD:
            low_rate.append(name)

    never_in_deck: list[str] = []
    if card_list is not None:
        # Dedupe the input — a card listed twice should not double-count
        # against the denominator and should not appear twice in the
        # never_in_deck output.
        unique_cards = list(dict.fromkeys(card_list))
        seen = set(set_stats.keys())
        for name in unique_cards:
            if name not in seen:
                never_in_deck.append(name)
        total = len(unique_cards)
    else:
        total = len(set_stats)

    played = max(total - len(zero_plays) - len(never_in_deck), 0)
    coverage_pct = (played / total) if total else 0.0

    return CoverageReport(
        set_label=set_label,
        total_cards=total,
        cards_with_zero_plays=sorted(zero_plays),
        cards_with_low_play_rate=sorted(low_rate),
        cards_never_in_deck=sorted(never_in_deck),
        coverage_pct=round(coverage_pct, 4),
    )


# =============================================================================
# Force-include deck builder
# =============================================================================

def build_force_include_spec(
    target_card_name: str,
    base_deck_names: list[str],
    deck_size: int = 30,
    copies_of_target: int = 4,
) -> list[str]:
    """
    Produce a deck spec that maximises odds the target card resolves.

    Strategy: target gets `copies_of_target` slots; the rest of the deck is
    filled (round-robin) from `base_deck_names` so the deck has a coherent
    mana base + filler that does not crowd out the target.

    The pipeline calls this with `base_deck_names` set to a known-functional
    starter deck for the engine (so mana fixing / energy / resources are
    handled), then drops the target into `copies_of_target` slots.

    This is a pure name-list generator — the caller resolves names to
    CardDefinitions in whatever way that engine expects.
    """
    if deck_size <= 0:
        return []
    if copies_of_target >= deck_size:
        return [target_card_name] * deck_size

    out: list[str] = [target_card_name] * copies_of_target
    if not base_deck_names:
        # No filler available — just pad with target copies.
        out.extend([target_card_name] * (deck_size - copies_of_target))
        return out

    i = 0
    while len(out) < deck_size:
        out.append(base_deck_names[i % len(base_deck_names)])
        i += 1
    return out


def force_include_specs_for_zero_plays(
    report: CoverageReport,
    base_deck_names: list[str],
    deck_size: int = 30,
    copies_of_target: int = 4,
) -> dict[str, list[str]]:
    """
    For every zero-play card in `report`, build a force-include deck spec.

    Returns a map { card_name -> [card_name, ...deck_size_total] } that the
    pipeline can hand to the engine's deck loader for a coverage retest
    round.
    """
    out: dict[str, list[str]] = {}
    for name in report.cards_with_zero_plays:
        out[name] = build_force_include_spec(
            name,
            base_deck_names,
            deck_size=deck_size,
            copies_of_target=copies_of_target,
        )
    return out


# =============================================================================
# CLI
# =============================================================================

def _load_card_list(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    text = path.read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tournament", type=Path, required=True,
                    help="Path to tournament aggregate JSON.")
    ap.add_argument("--set", dest="set_label", required=True,
                    help="Set domain label (e.g. MYSET).")
    ap.add_argument("--card-list", type=Path, default=None,
                    help="Optional newline-separated list of all card "
                         "names in the set, used to detect cards that "
                         "never made it into any deck.")
    ap.add_argument("--out", type=Path, default=None,
                    help="Write CoverageReport JSON here. Defaults to "
                         "stdout.")
    args = ap.parse_args()

    tournament = json.loads(args.tournament.read_text(encoding="utf-8"))
    card_list = _load_card_list(args.card_list)

    report = analyze_coverage(tournament, args.set_label, card_list)
    payload = json.dumps(asdict(report), indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(payload + "\n")

    if report.cards_with_zero_plays or report.cards_never_in_deck:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
