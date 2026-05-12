#!/usr/bin/env python3
"""Run a compact MTG spice/deck/tournament/balance/mirror loop.

The runner uses the model-free MTG Codex referee for mirror validation. When
this parent process does not have a callable Codex subagent interface, mirror
validation falls back to the referee's deterministic legal-action smoke path:

* capability test for the focal spice card,
* synergy-aware deck construction around that focal,
* a two-pilot AI tournament between the tuned synergy deck and the baseline,
* a hidden-info-safe MTG Codex packet validation transcript,
* a balance classification with the next recommended action.
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
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.ai import AIEngine  # noqa: E402
from src.ai.strategies import AggroStrategy, ControlStrategy, MidrangeStrategy  # noqa: E402
from src.cards.custom import CUSTOM_SETS  # noqa: E402
from src.engine.types import CardType  # noqa: E402

from scripts.play.capability_test import (  # noqa: E402
    _load_synergy_registry,
    build_synergy_deck,
    run_capability_test,
)
from scripts.play.custom_set_tournament import (  # noqa: E402
    aggregate,
    build_set_deck,
    card_types,
    get_cmc,
    play_one_game,
    render_tier_report,
)
from scripts.play.mtg_codex_match import (  # noqa: E402
    public_summary as codex_public_summary,
    run_fallback_match_from_decks,
    write_transcript as write_codex_transcript,
)


SPICE_DESIGN_NOTES: dict[str, dict[str, Any]] = {
    "Charizard, Mega Evolved": {
        "patterns": ["snowball value engine", "compression / threat-and-answer"],
        "action": "Validate red-spell chaining as the focal build-around.",
    },
    "Moltres, Phoenix Reborn": {
        "patterns": ["recursion / persistence", "hard to interact with"],
        "action": "Validate recursive hasty pressure in a low-curve red shell.",
    },
    "Pikachu, Thunder Champion": {
        "patterns": ["snowball value engine", "build-around payoff"],
        "action": "Validate team-combat counters as the deck's scaling threat.",
    },
    "Eevee, Evolution Vessel": {
        "patterns": ["tutoring and consistency", "compression / threat-and-answer"],
        "action": "Validate one-mana creature tutoring against baseline PKH.",
    },
    "Master Ball": {
        "patterns": ["build-around payoff", "tempo theft"],
        "action": "Validate cheap-creature ETB counters and haste support.",
    },
    "Volcanic Mantle": {
        "patterns": ["asymmetric prison", "snowball value engine"],
        "action": "Validate automatic red attack buffs without equip friction.",
    },
    "Reshiram, Truth Aspect": {
        "patterns": ["recursion / persistence", "build-around payoff"],
        "action": "Validate graveyard-enabled cost reduction and ETB removal.",
    },
    "Hyper Beam": {
        "patterns": ["disproportionate efficiency", "tempo theft"],
        "action": "Validate curve-friendly burn as a red finisher.",
    },
}


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug[:36] or "deck"


def _card_name_counts(deck: Iterable[Any]) -> Counter[str]:
    return Counter(card.name for card in deck)


def _is_land(card_def: Any) -> bool:
    return CardType.LAND in card_types(card_def)


def _functional_nonland(card_def: Any) -> bool:
    if _is_land(card_def):
        return False
    return bool(getattr(card_def, "setup_interceptors", None) or getattr(card_def, "resolve", None))


def summarize_deckbuilding_pass(
    *,
    set_code: str,
    focal: str,
    partners: list[str],
    baseline_deck: list[Any],
    synergy_deck: list[Any],
) -> dict[str, Any]:
    """Describe what the synergy-aware deckbuilding pass changed."""
    baseline_counts = _card_name_counts(baseline_deck)
    synergy_counts = _card_name_counts(synergy_deck)
    partner_counts = {name: synergy_counts.get(name, 0) for name in partners}

    additions = {
        name: count - baseline_counts.get(name, 0)
        for name, count in synergy_counts.items()
        if count > baseline_counts.get(name, 0)
    }
    removals = {
        name: count - synergy_counts.get(name, 0)
        for name, count in baseline_counts.items()
        if count > synergy_counts.get(name, 0)
    }

    curve = Counter(
        get_cmc(card)
        for card in synergy_deck
        if not _is_land(card)
    )
    nonlands = [card for card in synergy_deck if not _is_land(card)]
    functional = sum(1 for card in nonlands if _functional_nonland(card))

    return {
        "set": set_code,
        "focal": focal,
        "action": (
            "Build the measured deck as 4x focal, curated partner copies, "
            "mono-primary filler, and 24 lands instead of the generic set deck."
        ),
        "baseline_focal_copies": baseline_counts.get(focal, 0),
        "synergy_focal_copies": synergy_counts.get(focal, 0),
        "partners_requested": len(partners),
        "partners_in_synergy_deck": sum(1 for count in partner_counts.values() if count > 0),
        "partner_copy_counts": partner_counts,
        "spell_count": len(nonlands),
        "land_count": len(synergy_deck) - len(nonlands),
        "unique_spells": len({card.name for card in nonlands}),
        "functional_nonland_ratio": round(functional / len(nonlands), 3) if nonlands else 0.0,
        "curve": {str(k): curve[k] for k in sorted(curve)},
        "top_additions_vs_baseline": dict(sorted(additions.items(), key=lambda kv: (-kv[1], kv[0]))[:12]),
        "top_cuts_vs_baseline": dict(sorted(removals.items(), key=lambda kv: (-kv[1], kv[0]))[:12]),
    }


def detect_llm_deckbuilder() -> dict[str, Any]:
    """Return local LLM deckbuilder status without making a generation call."""
    try:
        from src.server.services.llm_deckbuilder import LLMDeckBuilderService

        service = LLMDeckBuilderService()
        provider = getattr(service, "provider", None)
        model = getattr(provider, "model_name", None) or getattr(provider, "model", None)
        available = bool(service.is_available)
        return {
            "available": available,
            "provider": provider.__class__.__name__ if provider else None,
            "model": model,
            "note": (
                "LLM deckbuilder provider is available; this runner still uses the "
                "repo's local two-pilot tournament substitute because no automated "
                "LLM-vs-LLM MTG match harness exists."
                if available
                else "LLM deckbuilder provider unavailable; using hard heuristic two-pilot substitute."
            ),
        }
    except Exception as exc:
        return {
            "available": False,
            "provider": None,
            "model": None,
            "note": f"LLM deckbuilder check failed; using hard heuristic substitute: {type(exc).__name__}: {exc}",
        }


def make_pilot(strategy_name: str, difficulty: str) -> AIEngine:
    if strategy_name == "aggro":
        return AIEngine(strategy=AggroStrategy(), difficulty=difficulty)
    if strategy_name == "control":
        return AIEngine(strategy=ControlStrategy(), difficulty=difficulty)
    if strategy_name == "ultra":
        return AIEngine.create_ultra_bot()
    return AIEngine(strategy=MidrangeStrategy(), difficulty=difficulty)


def _winner_label(results: list[dict[str, Any]], label: str) -> float:
    completed = [r for r in results if not r.get("error") and r.get("winner_domain") is not None]
    if not completed:
        return 0.0
    wins = sum(1 for r in completed if r.get("winner_domain") == label)
    return wins / len(completed)


def run_two_pilot_substitute(
    *,
    synergy_deck: list[Any],
    baseline_deck: list[Any],
    set_code: str,
    focal: str,
    games: int,
    max_turns: int,
    difficulty: str,
    per_turn_timeout_s: float,
    wall_deadline_s: float,
    llm_status: dict[str, Any],
) -> dict[str, Any]:
    """Run a local two-pilot substitute for missing LLM-vs-LLM automation."""
    synergy_label = f"{set_code}_syn_{_safe_slug(focal)}"
    baseline_label = f"{set_code}_baseline"

    if llm_status.get("available"):
        synergy_pilot = baseline_pilot = "ultra"
        substitute = "ultra-pilot local substitute; no repo LLM-vs-LLM match harness"
    else:
        synergy_pilot = "aggro"
        baseline_pilot = "midrange"
        substitute = "hard heuristic aggro-vs-midrange substitute; LLM unavailable"

    raw_results: list[dict[str, Any]] = []
    for game_index in range(games):
        synergy_is_p1 = game_index % 2 == 0
        p1_deck = synergy_deck if synergy_is_p1 else baseline_deck
        p2_deck = baseline_deck if synergy_is_p1 else synergy_deck
        p1_label = synergy_label if synergy_is_p1 else baseline_label
        p2_label = baseline_label if synergy_is_p1 else synergy_label
        p1_pilot = synergy_pilot if synergy_is_p1 else baseline_pilot
        p2_pilot = baseline_pilot if synergy_is_p1 else synergy_pilot

        result = asyncio.run(
            play_one_game(
                p1_deck,
                p2_deck,
                make_pilot(p1_pilot, difficulty),
                make_pilot(p2_pilot, difficulty),
                p1_label,
                p2_label,
                max_turns=max_turns,
                per_turn_timeout_s=per_turn_timeout_s,
                wall_deadline_s=wall_deadline_s,
            )
        )
        raw_results.append(result.__dict__)

    result_dict = {
        "domains": [synergy_label, baseline_label],
        "games_per_pair": games,
        "max_turns": max_turns,
        "difficulty": difficulty,
        "pilot_map": {
            synergy_label: synergy_pilot,
            baseline_label: baseline_pilot,
        },
        "substitution": substitute,
        "results": raw_results,
    }
    agg = aggregate(result_dict)
    return {
        **result_dict,
        "aggregate": agg,
        "report": render_tier_report(agg),
        "synergy_label": synergy_label,
        "baseline_label": baseline_label,
        "synergy_match_winrate": round(_winner_label(raw_results, synergy_label), 3),
    }


def run_mirror_validation(
    *,
    synergy_deck: list[Any],
    baseline_deck: list[Any],
    set_code: str,
    focal: str,
    seed: int,
    max_actions: int,
    out_path: Path,
    live_subagents_available: bool = False,
) -> dict[str, Any]:
    """Run the per-iteration MTG Codex mirror validation pass.

    The harness is live-subagent-ready through ``mtg_codex_match init/packet/apply``.
    This in-process loop uses deterministic fallback when no subagent tool is
    available in the current Codex session.
    """
    if max_actions <= 0:
        raise ValueError("mirror max_actions must be positive")

    match_id = f"mtg-codex-{set_code.lower()}-{_safe_slug(focal)}-{seed}"
    referee = asyncio.run(
        run_fallback_match_from_decks(
            p1_deck=synergy_deck,
            p2_deck=baseline_deck,
            p1_deck_id=f"{set_code}:synergy:{focal}",
            p2_deck_id=f"{set_code}:baseline",
            seed=seed,
            max_actions=max_actions,
            match_id=match_id,
        )
    )
    write_codex_transcript(referee, out_path)
    engine_errors = [
        entry for entry in referee.transcript
        if not entry.get("engine_ok", False)
    ]
    invalid_actions = [
        entry for entry in referee.transcript
        if not entry.get("validation", False)
    ]
    return {
        "schema_version": "hyperdraft.mtg_spice_loop.mirror.v1",
        "mode": "live_subagent" if live_subagents_available else "deterministic_fallback",
        "live_subagents_used": bool(live_subagents_available),
        "fallback_actions": 0 if live_subagents_available else len(referee.transcript),
        "actions": len(referee.transcript),
        "invalid_actions": len(invalid_actions),
        "engine_errors": len(engine_errors),
        "transcript_path": str(out_path),
        "summary": codex_public_summary(referee),
        "note": (
            "Live Codex subagent interface unavailable in this session; "
            "repo-internal model/API/shell model calls are intentionally not used."
            if not live_subagents_available
            else "Live Codex player subagents chose action ids from hidden-info-safe packets."
        ),
    }


def classify_balance_action(
    *,
    capability: dict[str, Any],
    tournament: dict[str, Any],
    deckbuilding: dict[str, Any],
) -> dict[str, Any]:
    """Turn noisy run metrics into a concrete balance-pass recommendation."""
    errors = int(capability.get("errors", 0) or 0)
    tournament_errors = sum(1 for r in tournament.get("results", []) if r.get("error"))
    score = float(capability.get("capability_score", 0.0) or 0.0)
    cast_per_game = float(capability.get("focal_cast_per_game", 0.0) or 0.0)
    synergy_wr = float(tournament.get("synergy_match_winrate", 0.0) or 0.0)
    focal_copies = int(deckbuilding.get("synergy_focal_copies", 0) or 0)
    functional_ratio = float(deckbuilding.get("functional_nonland_ratio", 0.0) or 0.0)

    if errors or tournament_errors:
        action = "fix_harness_or_card_bug_before_more_balance"
        reason = f"Capability errors={errors}, tournament errors={tournament_errors}."
    elif focal_copies < 4:
        action = "fix_deckbuilder_package"
        reason = "The tuned deck did not keep four focal copies."
    elif cast_per_game < 0.25:
        action = "lower_cost_or_add_mana_support"
        reason = f"Focal cast/game is {cast_per_game:.2f}, below the 0.25 floor."
    elif score < 0.30 and synergy_wr < 0.45:
        action = "buff_focal_or_partner_package"
        reason = f"Capability score {score:.2f} and match WR {synergy_wr:.0%} are both low."
    elif synergy_wr >= 0.70 and score >= 0.30:
        action = "nerf_focal_or_reduce_partner_density"
        reason = f"Match WR {synergy_wr:.0%} is above the 70% broken band."
    elif functional_ratio < 0.35:
        action = "replace_cosmetic_filler_with_wired_support"
        reason = f"Only {functional_ratio:.0%} of nonlands have setup or resolve hooks."
    else:
        action = "hold_and_continue_sampling"
        reason = (
            f"Capability score {score:.2f}, cast/game {cast_per_game:.2f}, "
            f"match WR {synergy_wr:.0%}; no immediate code tuning from this small sample."
        )

    return {
        "action": action,
        "reason": reason,
        "capability_score": round(score, 3),
        "focal_cast_per_game": round(cast_per_game, 3),
        "synergy_match_winrate": round(synergy_wr, 3),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# MTG Spice Loop Summary",
        "",
        f"- Set: {summary['set']}",
        f"- Iterations: {summary['iterations_requested']}",
        f"- Capability games per iteration: {summary['capability_games']}",
        f"- Tournament games per iteration: {summary['tournament_games']}",
        f"- Mirror actions per iteration: {summary['mirror_actions']}",
        f"- LLM status: {summary['llm_status']['note']}",
        f"- Mirror mode: {summary['mirror_mode']}",
        "",
        "| Iter | Focal | Cap | Cast/G | Match WR | Mirror | Balance action |",
        "| ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summary["iterations"]:
        cap = item["capability"]
        bal = item["balance"]
        mirror = item.get("mirror", {})
        lines.append(
            f"| {item['iteration']} | {item['focal']} | "
            f"{cap.get('capability_score', 0):.2f} | "
            f"{cap.get('focal_cast_per_game', 0):.2f} | "
            f"{bal.get('synergy_match_winrate', 0):.0%} | "
            f"{mirror.get('actions', 0)} | "
            f"{bal['action']} |"
        )
    lines.extend([
        "",
        "Notes:",
        "- Match WR is the tuned synergy deck's winrate against the generic PKH baseline in that iteration's local substitute tournament.",
        "- Mirror validation uses hidden-info-safe MTG Codex packets. This run records deterministic fallback when no live subagent tool is available.",
        "- These compact iterations are intentionally noisy; use repeated low-sample runs to identify which cards deserve deeper games.",
    ])
    return "\n".join(lines) + "\n"


def run_loop(
    *,
    set_code: str,
    iterations: int,
    capability_games: int,
    tournament_games: int,
    max_turns: int,
    difficulty: str,
    seed: int,
    out_dir: Path,
    mirror_dir: Optional[Path] = None,
    focals: Optional[list[str]] = None,
    per_turn_timeout_s: float = 4.0,
    wall_deadline_s: float = 25.0,
    mirror_actions: int = 8,
    skip_llm_check: bool = False,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    if set_code not in CUSTOM_SETS:
        raise ValueError(f"Unknown custom set '{set_code}'. Available: {sorted(CUSTOM_SETS)}")
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if capability_games <= 0:
        raise ValueError("capability_games must be positive")
    if tournament_games <= 0:
        raise ValueError("tournament_games must be positive")
    if mirror_actions <= 0:
        raise ValueError("mirror_actions must be positive")

    random.seed(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    if mirror_dir is None:
        mirror_dir = out_dir.parent / f"mtg_codex_{out_dir.name}"
    mirror_dir.mkdir(parents=True, exist_ok=True)
    set_cards = CUSTOM_SETS[set_code]
    registry = _load_synergy_registry(set_code)
    focal_cycle = focals or list(registry.keys())
    unknown = [name for name in focal_cycle if name not in registry]
    if unknown:
        raise ValueError(f"Focal(s) missing from {set_code} synergy registry: {unknown}")

    llm_status = (
        {
            "available": False,
            "provider": None,
            "model": None,
            "note": "LLM check skipped; using hard heuristic two-pilot substitute.",
        }
        if skip_llm_check
        else detect_llm_deckbuilder()
    )

    summary: dict[str, Any] = {
        "schema_version": "hyperdraft.mtg_spice_loop.v2",
        "set": set_code,
        "seed": seed,
        "iterations_requested": iterations,
        "capability_games": capability_games,
        "tournament_games": tournament_games,
        "mirror_actions": mirror_actions,
        "max_turns": max_turns,
        "difficulty": difficulty,
        "mirror_dir": str(mirror_dir),
        "mirror_mode": "deterministic_fallback",
        "llm_status": llm_status,
        "started_at": int(time.time()),
        "iterations": [],
    }
    write_json(out_dir / "run_config.json", summary)

    baseline_deck, baseline_info = build_set_deck(set_code, set_cards)

    for index in range(1, iterations + 1):
        focal = focal_cycle[(index - 1) % len(focal_cycle)]
        partners = registry[focal]
        random.seed(seed + index)

        print(f"\n=== MTG spice loop iteration {index}/{iterations}: {focal} ===", flush=True)
        capability = run_capability_test(
            focal_name=focal,
            synergy_partners=partners,
            set_cards=set_cards,
            set_code=set_code,
            games=capability_games,
            max_turns=max_turns,
            per_turn_timeout_s=per_turn_timeout_s,
            wall_deadline_s=wall_deadline_s,
        )

        synergy_deck = build_synergy_deck(focal, partners, set_cards)
        deckbuilding = summarize_deckbuilding_pass(
            set_code=set_code,
            focal=focal,
            partners=partners,
            baseline_deck=baseline_deck,
            synergy_deck=synergy_deck,
        )

        tournament = run_two_pilot_substitute(
            synergy_deck=synergy_deck,
            baseline_deck=baseline_deck,
            set_code=set_code,
            focal=focal,
            games=tournament_games,
            max_turns=max_turns,
            difficulty=difficulty,
            per_turn_timeout_s=per_turn_timeout_s,
            wall_deadline_s=wall_deadline_s,
            llm_status=llm_status,
        )
        balance = classify_balance_action(
            capability=capability,
            tournament=tournament,
            deckbuilding=deckbuilding,
        )
        mirror_path = mirror_dir / f"iteration_{index:02d}_{_safe_slug(focal)}.json"
        mirror = run_mirror_validation(
            synergy_deck=synergy_deck,
            baseline_deck=baseline_deck,
            set_code=set_code,
            focal=focal,
            seed=seed + 1000 + index,
            max_actions=mirror_actions,
            out_path=mirror_path,
            live_subagents_available=False,
        )

        iteration_payload = {
            "iteration": index,
            "set": set_code,
            "focal": focal,
            "design": SPICE_DESIGN_NOTES.get(
                focal,
                {
                    "patterns": ["build-around / synergy-dependent payoff"],
                    "action": "Validate focal card with curated partners.",
                },
            ),
            "baseline_deck_info": baseline_info,
            "capability": capability,
            "deckbuilding": deckbuilding,
            "tournament": {
                key: value for key, value in tournament.items()
                if key != "report"
            },
            "balance": balance,
            "mirror": mirror,
        }
        summary["iterations"].append({
            "iteration": index,
            "focal": focal,
            "design": iteration_payload["design"],
            "capability": capability,
            "deckbuilding": deckbuilding,
            "tournament": {
                "substitution": tournament["substitution"],
                "pilot_map": tournament["pilot_map"],
                "synergy_match_winrate": tournament["synergy_match_winrate"],
                "result_count": len(tournament["results"]),
            },
            "balance": balance,
            "mirror": {
                "mode": mirror["mode"],
                "actions": mirror["actions"],
                "invalid_actions": mirror["invalid_actions"],
                "engine_errors": mirror["engine_errors"],
                "transcript_path": mirror["transcript_path"],
                "live_subagents_used": mirror["live_subagents_used"],
                "fallback_actions": mirror["fallback_actions"],
            },
        })

        iter_prefix = out_dir / f"iteration_{index:02d}_{_safe_slug(focal)}"
        write_json(iter_prefix.with_suffix(".json"), iteration_payload)
        iter_prefix.with_suffix(".report.txt").write_text(tournament["report"], encoding="utf-8")
        print(
            f"  capability={capability['capability_score']:.2f} "
            f"cast/g={capability['focal_cast_per_game']:.2f} "
            f"match_wr={balance['synergy_match_winrate']:.0%} "
            f"mirror_actions={mirror['actions']} "
            f"balance={balance['action']}",
            flush=True,
        )

        should_stop = (
            balance["action"] == "fix_harness_or_card_bug_before_more_balance"
            or mirror["engine_errors"] > 0
        )
        if should_stop and not continue_on_error:
            summary["stopped_at_iteration"] = index
            summary["stop_reason"] = (
                balance["reason"]
                if balance["action"] == "fix_harness_or_card_bug_before_more_balance"
                else f"Mirror validation produced engine_errors={mirror['engine_errors']}."
            )
            write_json(out_dir / "summary.json", summary)
            (out_dir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
            raise RuntimeError(
                f"Iteration {index} produced an error; fix before continuing: {summary['stop_reason']}"
            )

    summary["finished_at"] = int(time.time())
    write_json(out_dir / "summary.json", summary)
    (out_dir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
    print(f"\nMTG spice loop logs -> {out_dir}", flush=True)
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run compact MTG spice loop iterations.")
    parser.add_argument("--set", default="PKH", choices=sorted(CUSTOM_SETS.keys()))
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--capability-games", type=int, default=1)
    parser.add_argument("--tournament-games", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--difficulty", default="hard", choices=["easy", "medium", "hard"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--per-turn-timeout", type=float, default=4.0)
    parser.add_argument("--wall-deadline", type=float, default=25.0)
    parser.add_argument("--mirror-actions", type=int, default=8)
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="record error iterations and keep going; default stops so harness/card bugs get fixed first",
    )
    parser.add_argument("--focals", default="", help="optional comma-separated focal list")
    parser.add_argument("--skip-llm-check", action="store_true")
    parser.add_argument(
        "--out-dir",
        default="",
        help="output directory; default logs/mtg_spice_loop_<timestamp>",
    )
    parser.add_argument(
        "--mirror-dir",
        default="",
        help="mirror transcript directory; default logs/mtg_codex_<timestamp>",
    )
    args = parser.parse_args(argv)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else REPO_ROOT / "logs" / f"mtg_spice_loop_{timestamp}"
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    mirror_dir = Path(args.mirror_dir) if args.mirror_dir else REPO_ROOT / "logs" / f"mtg_codex_{timestamp}"
    if not mirror_dir.is_absolute():
        mirror_dir = REPO_ROOT / mirror_dir
    focals = [f.strip() for f in args.focals.split(",") if f.strip()] or None

    run_loop(
        set_code=args.set,
        iterations=args.iterations,
        capability_games=args.capability_games,
        tournament_games=args.tournament_games,
        max_turns=args.max_turns,
        difficulty=args.difficulty,
        seed=args.seed,
        out_dir=out_dir,
        mirror_dir=mirror_dir,
        focals=focals,
        per_turn_timeout_s=args.per_turn_timeout,
        wall_deadline_s=args.wall_deadline,
        mirror_actions=args.mirror_actions,
        skip_llm_check=args.skip_llm_check,
        continue_on_error=args.continue_on_error,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
