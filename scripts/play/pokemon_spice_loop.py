#!/usr/bin/env python3
"""Run compact Pokemon spice/deck/tournament/mirror validation loops.

This runner is intentionally model-free. The mirror pass uses the deterministic
Codex referee fallback path from ``pokemon_codex_match.py`` and records enough
seed/deck/action data for reproduction without adding API dependencies.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.play.pokemon_codex_match import (  # noqa: E402
    public_summary,
    run_fallback_match,
)
from scripts.play.pokemon_deck_quality_report import build_report as build_svs_quality_report  # noqa: E402
from scripts.play.ravnica_balance_report import build_report as build_brv_balance_report  # noqa: E402
from scripts.play.variant_tournament import (  # noqa: E402
    ENGINES,
    aggregate,
    render_report,
    run_variant_tournament,
)
from src.cards.pokemon.beyond.ravnica import (  # noqa: E402
    BRV_SYNERGY_PACKAGES,
    build_ravnica_guild_deck,
    brv_synergy_package_errors,
    list_ravnica_guild_decks,
)
from src.cards.pokemon.beyond.ravnica.balance import ravnica_guild_profile  # noqa: E402
from src.engine.types import CardDefinition  # noqa: E402


ITERATION_PLANS: list[dict[str, Any]] = [
    {
        "guild": "izzet",
        "focal": "Niv-Mizzet, Parun ex",
        "matchup": ("brv:izzet", "brv:rakdos"),
        "suspicion": "Izzet's cheaper Firemind line against Rakdos pressure.",
        "patterns": ["snowball value engine", "compression / threat-and-answer"],
    },
    {
        "guild": "boros",
        "focal": "Aurelia, the Warleader ex",
        "matchup": ("brv:boros", "brv:selesnya"),
        "suspicion": "Boros bench-scaling pressure into Selesnya wide boards.",
        "patterns": ["disproportionate efficiency", "tempo theft"],
    },
    {
        "guild": "simic",
        "focal": "Vannifar, Evolved Enigma ex",
        "matchup": ("brv:simic", "brv:azorius"),
        "suspicion": "Simic evolution toolbox against Azorius tempo control.",
        "patterns": ["tutoring and consistency", "build-around payoff"],
    },
    {
        "guild": "golgari",
        "focal": "Jarad, Golgari Lich Lord ex",
        "matchup": ("brv:golgari", "brv:orzhov"),
        "suspicion": "Golgari recursion and discard pressure against Orzhov drain.",
        "patterns": ["recursion / persistence", "snowball value engine"],
    },
    {
        "guild": "gruul",
        "focal": "Borborygmos ex",
        "matchup": ("brv:gruul", "brv:dimir"),
        "suspicion": "Gruul raw pressure into Dimir disruption.",
        "patterns": ["disproportionate efficiency", "hard to interact with"],
    },
    {
        "guild": "rakdos",
        "focal": "Rakdos, Lord of Riots ex",
        "matchup": ("brv:rakdos", "brv:boros"),
        "suspicion": "Rakdos damaged-active payoff against Boros race starts.",
        "patterns": ["tempo theft", "two-card combo enablement"],
    },
    {
        "guild": "selesnya",
        "focal": "Trostani, Selesnya's Voice ex",
        "matchup": ("brv:selesnya", "brv:golgari"),
        "suspicion": "Selesnya go-wide healing into Golgari attrition.",
        "patterns": ["asymmetric prison", "snowball value engine"],
    },
    {
        "guild": "azorius",
        "focal": "Isperia, Supreme Judge ex",
        "matchup": ("brv:azorius", "brv:orzhov"),
        "suspicion": "Azorius switch/control pressure against Orzhov prize racing.",
        "patterns": ["tempo theft", "hard to interact with"],
    },
    {
        "guild": "orzhov",
        "focal": "Teysa Karlov ex",
        "matchup": ("brv:orzhov", "brv:dimir"),
        "suspicion": "Orzhov drain engines against Dimir hand/library pressure.",
        "patterns": ["recursion / persistence", "asymmetric prison"],
    },
    {
        "guild": "dimir",
        "focal": "Lazav, Dimir Mastermind ex",
        "matchup": ("brv:dimir", "brv:izzet"),
        "suspicion": "Dimir disruption against Izzet draw-and-burst turns.",
        "patterns": ["tutoring and consistency", "tempo theft"],
    },
    # Spice-pack v1 second Orzhov focal (Karlov-line Stage 2 ex). Sits
    # alongside the Teysa plan so every focal in BRV_SYNERGY_PACKAGES is
    # exercised by the loop.
    {
        "guild": "orzhov",
        "focal": "Obzedat, Ghost Council ex",
        "matchup": ("brv:orzhov", "brv:rakdos"),
        "suspicion": "Orzhov modal KO-bench / prize-tax against Rakdos chip damage.",
        "patterns": ["asymmetric prison", "tempo theft"],
    },
]


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug[:44] or "pokemon"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _card_name_counts(deck: list[CardDefinition]) -> Counter[str]:
    return Counter(card.name for card in deck)


def summarize_brv_deckbuilding_pass(guild: str, focal: str) -> dict[str, Any]:
    """Summarize whether the current guild deck supports its focal ex."""
    deck, strategy = build_ravnica_guild_deck(guild, enforce_balance=True)
    profile = ravnica_guild_profile(guild, deck)
    counts = _card_name_counts(deck)
    partners = BRV_SYNERGY_PACKAGES[focal]
    missing_partners = [name for name in partners if counts.get(name, 0) == 0]
    partner_copies = {name: counts.get(name, 0) for name in partners}

    partners_present = sum(1 for name in partners if counts.get(name, 0) > 0)

    if profile["balance_flags"]:
        action = "fix_static_balance_flags"
    elif partners_present < 8:
        action = "increase_synergy_partner_coverage"
    elif counts.get(focal, 0) < 2:
        action = "restore_focal_density"
    elif profile["energy_alignment_score"] < 8:
        action = "tune_energy_package"
    else:
        action = "hold_current_deck_shape"

    return {
        "guild": guild,
        "focal": focal,
        "strategy": strategy,
        "action": action,
        "focal_copies": counts.get(focal, 0),
        "partner_count": len(partners),
        "partners_present": partners_present,
        "missing_partners": missing_partners,
        "partner_copy_counts": partner_copies,
        "profile": profile,
        "top_card_counts": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:16]),
    }


async def _run_variant_pass(
    *,
    decks: list[str],
    variants: list[str],
    games: int,
    max_turns: int,
    seed: int,
    out_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    random.seed(seed)
    deck_pool = ENGINES["pokemon"]["deck_resolver"](decks)
    outcomes = await run_variant_tournament(
        "pokemon",
        deck_pool,
        variants,
        games_per_pair_per_deck=games,
        max_turns=max_turns,
    )
    aggregated = aggregate(outcomes, variants)
    report_text = render_report(aggregated)
    payload = {
        "schema_version": "hyperdraft.pokemon_variant_tournament.v1",
        "engine": "pokemon",
        "seed": seed,
        "variants": variants,
        "decks": decks,
        "games_per_pair_per_deck": games,
        "max_turns": max_turns,
        "outcomes": [outcome.__dict__ for outcome in outcomes],
        "aggregated": aggregated,
    }
    write_json(out_path, payload)
    report_path.write_text(report_text + "\n", encoding="utf-8")
    return {
        "path": str(out_path),
        "report_path": str(report_path),
        "totals": aggregated["totals"],
        "ranking": aggregated["ranking"],
    }


async def _run_mirror_pass(
    *,
    p1_deck: str,
    p2_deck: str,
    seed: int,
    max_actions: int,
    match_id: str,
    out_path: Path,
) -> dict[str, Any]:
    referee = await run_fallback_match(
        p1_deck=p1_deck,
        p2_deck=p2_deck,
        seed=seed,
        max_actions=max_actions,
        match_id=match_id,
    )
    validation_failures = [
        entry for entry in referee.transcript
        if not entry.get("validation") or not entry.get("engine_ok")
    ]
    payload = {
        "schema_version": "hyperdraft.pokemon_codex_match.v1",
        "match_id": match_id,
        "mode": "deterministic_fallback_smoke",
        "seed": seed,
        "decks": referee.deck_ids,
        "summary": public_summary(referee),
        "validation_failure_count": len(validation_failures),
        "transcript": referee.transcript,
    }
    write_json(out_path, payload)
    return {
        "path": str(out_path),
        "mode": payload["mode"],
        "actions": len(referee.transcript),
        "validation_failure_count": len(validation_failures),
        "summary": payload["summary"],
    }


def _iteration_errors(
    *,
    spice: dict[str, Any],
    deckbuilding: dict[str, Any],
    tournament: dict[str, Any],
    mirror: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if spice["synergy_errors"]:
        errors.append(f"synergy registry errors: {spice['synergy_errors']}")
    if spice["balance_report"]["quality_gate"]["passed"] is not True:
        errors.append("Beyond Ravnica balance report failed")
    if deckbuilding["action"] in {"fix_static_balance_flags", "increase_synergy_partner_coverage", "restore_focal_density"}:
        errors.append(f"deckbuilding action requires fix: {deckbuilding['action']}")
    if tournament["totals"].get("errors", 0):
        errors.append(f"variant tournament errors: {tournament['totals']['errors']}")
    if mirror["validation_failure_count"]:
        errors.append(f"mirror validation failures: {mirror['validation_failure_count']}")
    return errors


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Pokemon Spice Loop Summary",
        "",
        f"- Iterations: {summary['iterations_requested']}",
        f"- Seed: {summary['seed']}",
        f"- Variants: {', '.join(summary['variants'])}",
        f"- Tournament games per pair/deck: {summary['tournament_games']}",
        f"- Mirror max actions: {summary['mirror_max_actions']}",
        f"- Live subagent mirrors: {summary.get('live_subagent_validation_count', 0)}",
        f"- Fallback mirrors: {summary.get('fallback_validation_count', 0)}",
        "",
        "| Iter | Focal | Matchup | Tournament | Mirror actions | Action |",
        "| ---: | --- | --- | --- | ---: | --- |",
    ]
    for item in summary["iterations"]:
        ranking = item["tournament"]["ranking"]
        best = ranking[0]["variant"] if ranking else "n/a"
        lines.append(
            f"| {item['iteration']} | {item['focal']} | "
            f"{item['matchup'][0]} vs {item['matchup'][1]} | "
            f"best={best}, errors={item['tournament']['totals'].get('errors', 0)} | "
            f"{item['mirror']['actions']} | {item['deckbuilding']['action']} |"
        )
    lines.extend([
        "",
        f"Mirror mode: {summary.get('mirror_execution_mode', 'deterministic_fallback_smoke')} through the Codex referee harness; no API or SDK calls.",
        summary.get("subagent_status_note", ""),
    ])
    return "\n".join(lines) + "\n"


def run_loop(
    *,
    iterations: int,
    seed: int,
    out_dir: Path,
    variants: list[str],
    tournament_games: int,
    max_turns: int,
    mirror_max_actions: int,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if tournament_games <= 0:
        raise ValueError("tournament_games must be positive")
    if mirror_max_actions <= 0:
        raise ValueError("mirror_max_actions must be positive")

    guilds = set(list_ravnica_guild_decks())
    unknown_guilds = [plan["guild"] for plan in ITERATION_PLANS if plan["guild"] not in guilds]
    if unknown_guilds:
        raise ValueError(f"Iteration plan references unknown guilds: {unknown_guilds}")

    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": "hyperdraft.pokemon_spice_loop.v1",
        "seed": seed,
        "iterations_requested": iterations,
        "variants": variants,
        "tournament_games": tournament_games,
        "max_turns": max_turns,
        "mirror_max_actions": mirror_max_actions,
        "mirror_request": "codex_player_subagents_when_available",
        "mirror_execution_mode": "deterministic_fallback_smoke",
        "live_subagent_validation_count": 0,
        "fallback_validation_count": 0,
        "subagent_status_note": (
            "This runner is model-free and cannot invoke Codex subagents itself. "
            "For live mirrors, use scripts/play/pokemon_codex_match.py init, "
            "packet, and apply from a parent Codex session that has a callable "
            "subagent surface; pass each player only the current packet."
        ),
        "started_at": int(time.time()),
        "iterations": [],
    }
    write_json(out_dir / "run_config.json", summary)

    for index in range(1, iterations + 1):
        plan = ITERATION_PLANS[(index - 1) % len(ITERATION_PLANS)]
        guild = plan["guild"]
        focal = plan["focal"]
        slug = f"iteration_{index:02d}_{guild}_{_safe_slug(focal)}"
        iteration_seed = seed + index
        p1_deck, p2_deck = plan["matchup"]
        decks = [p1_deck, p2_deck]

        print(f"\n=== Pokemon spice loop iteration {index}/{iterations}: {guild} ===", flush=True)

        balance_report = build_brv_balance_report(guild)
        svs_quality = build_svs_quality_report()
        spice = {
            "guild": guild,
            "focal": focal,
            "patterns": plan["patterns"],
            "suspicion": plan["suspicion"],
            "synergy_errors": brv_synergy_package_errors(),
            "balance_report": balance_report,
        }
        deckbuilding = summarize_brv_deckbuilding_pass(guild, focal)
        write_json(out_dir / f"{slug}.balance.json", balance_report)
        write_json(out_dir / f"{slug}.starter_deck_quality.json", svs_quality)

        tournament = asyncio.run(_run_variant_pass(
            decks=decks,
            variants=variants,
            games=tournament_games,
            max_turns=max_turns,
            seed=iteration_seed,
            out_path=out_dir / f"{slug}.variant.json",
            report_path=out_dir / f"{slug}.variant.report.txt",
        ))

        mirror_path = REPO_ROOT / "logs" / f"pokemon_codex_iter{index:02d}_{_safe_slug(p1_deck)}_vs_{_safe_slug(p2_deck)}.json"
        mirror = asyncio.run(_run_mirror_pass(
            p1_deck=p1_deck,
            p2_deck=p2_deck,
            seed=iteration_seed,
            max_actions=mirror_max_actions,
            match_id=f"pokemon-spice-loop-{index:02d}-{guild}",
            out_path=mirror_path,
        ))
        if mirror["mode"] == "deterministic_fallback_smoke":
            summary["fallback_validation_count"] += 1
        else:
            summary["live_subagent_validation_count"] += 1

        iteration_payload = {
            "iteration": index,
            "seed": iteration_seed,
            "guild": guild,
            "focal": focal,
            "matchup": decks,
            "custom_set_spice_pass": spice,
            "deckbuilding": deckbuilding,
            "tournament": tournament,
            "mirror": mirror,
        }
        errors = _iteration_errors(
            spice=spice,
            deckbuilding=deckbuilding,
            tournament=tournament,
            mirror=mirror,
        )
        iteration_payload["errors"] = errors

        write_json(out_dir / f"{slug}.json", iteration_payload)
        summary["iterations"].append({
            "iteration": index,
            "guild": guild,
            "focal": focal,
            "matchup": decks,
            "suspicion": plan["suspicion"],
            "deckbuilding": {
                "action": deckbuilding["action"],
                "focal_copies": deckbuilding["focal_copies"],
                "partners_present": deckbuilding["partners_present"],
                "partner_count": deckbuilding["partner_count"],
            },
            "tournament": tournament,
            "mirror": mirror,
            "errors": errors,
        })
        write_json(out_dir / "summary.json", summary)
        (out_dir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")

        print(
            f"  deck={deckbuilding['action']} "
            f"tournament_errors={tournament['totals'].get('errors', 0)} "
            f"mirror_actions={mirror['actions']} "
            f"mirror_failures={mirror['validation_failure_count']}",
            flush=True,
        )
        if errors and not continue_on_error:
            summary["stopped_at_iteration"] = index
            summary["stop_reason"] = errors
            write_json(out_dir / "summary.json", summary)
            (out_dir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
            raise RuntimeError(f"Iteration {index} found errors; fix before continuing: {errors}")

    summary["finished_at"] = int(time.time())
    write_json(out_dir / "summary.json", summary)
    (out_dir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
    print(f"\nPokemon spice loop logs -> {out_dir}", flush=True)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260510)
    parser.add_argument("--variants", default="hard,ultra")
    parser.add_argument("--tournament-games", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=16)
    parser.add_argument("--mirror-max-actions", type=int, default=16)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args(argv)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else REPO_ROOT / "logs" / f"pokemon_spice_loop_{timestamp}"
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir

    variants = [value.strip() for value in args.variants.split(",") if value.strip()]
    run_loop(
        iterations=args.iterations,
        seed=args.seed,
        out_dir=out_dir,
        variants=variants,
        tournament_games=args.tournament_games,
        max_turns=args.max_turns,
        mirror_max_actions=args.mirror_max_actions,
        continue_on_error=args.continue_on_error,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
