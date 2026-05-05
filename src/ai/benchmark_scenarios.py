"""Fixed decision scenarios for trace-backed MTG AI benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.ai.benchmark import AIBenchmarkRun
from src.ai.engine import AIEngine
from src.ai.strategies import MidrangeStrategy
from src.engine import (
    ActionType,
    AttackDeclaration,
    CardType,
    Characteristics,
    Game,
    LegalAction,
    PendingChoice,
    ZoneType,
)


class _CardDef:
    def __init__(self, text: str = ""):
        self.text = text
        self.setup_interceptors = None
        self.setup_in_hand = None


@dataclass(frozen=True)
class ScenarioResult:
    """Outcome for one deterministic benchmark scenario."""

    name: str
    passed: bool
    expected: Any
    observed: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": self.expected,
            "observed": self.observed,
        }


def _game() -> tuple[Game, Any, Any]:
    game = Game()
    p1 = game.add_player("AI")
    p2 = game.add_player("Opponent")
    return game, p1, p2


def _obj(
    game: Game,
    owner: str,
    name: str,
    zone: ZoneType,
    types: set[CardType],
    text: str = "",
    power: int | None = None,
    toughness: int | None = None,
    mana_cost: str | None = None,
):
    abilities = []
    for keyword in [
        "flying",
        "trample",
        "deathtouch",
        "lifelink",
        "menace",
        "first strike",
        "double strike",
    ]:
        if keyword in text.lower():
            abilities.append({"name": keyword, "keyword": keyword})
    obj = game.create_object(
        name=name,
        owner_id=owner,
        zone=zone,
        characteristics=Characteristics(
            types=set(types),
            power=power,
            toughness=toughness,
            mana_cost=mana_cost,
            abilities=abilities,
        ),
        card_def=_CardDef(text),
    )
    if zone == ZoneType.BATTLEFIELD:
        obj.state.summoning_sickness = False
    return obj


def _play_land_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, _ = _game()
    land = _obj(game, p1.id, "Forest", ZoneType.HAND, {CardType.LAND})

    action = ai.get_action(
        p1.id,
        game.state,
        [
            LegalAction(type=ActionType.PASS),
            LegalAction(type=ActionType.PLAY_LAND, card_id=land.id),
        ],
    )

    observed = action.type.name
    expected = ActionType.PLAY_LAND.name
    return ScenarioResult("play_land_over_pass", observed == expected, expected, observed)


def _answer_large_threat_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, p2 = _game()
    for idx in range(3):
        _obj(game, p1.id, f"Swamp {idx}", ZoneType.BATTLEFIELD, {CardType.LAND})
    removal = _obj(
        game, p1.id, "Doom Blade", ZoneType.HAND,
        {CardType.INSTANT}, text="Destroy target creature.", mana_cost="{1}{B}"
    )
    small_creature = _obj(
        game, p1.id, "Small Creature", ZoneType.HAND,
        {CardType.CREATURE}, power=1, toughness=1, mana_cost="{1}"
    )
    _obj(
        game, p2.id, "Dragon", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Flying", power=6, toughness=6
    )

    action = ai.get_action(
        p1.id,
        game.state,
        [
            LegalAction(type=ActionType.CAST_SPELL, card_id=small_creature.id),
            LegalAction(type=ActionType.CAST_SPELL, card_id=removal.id),
        ],
    )
    observed = game.state.objects[action.card_id].name if action.card_id else None
    expected = "Doom Blade"
    return ScenarioResult("answer_large_threat_action", observed == expected, expected, observed)


def _cast_card_draw_over_pass_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, _ = _game()
    for idx in range(3):
        _obj(game, p1.id, f"Island {idx}", ZoneType.BATTLEFIELD, {CardType.LAND})
    draw_spell = _obj(
        game, p1.id, "Quick Study", ZoneType.HAND,
        {CardType.INSTANT}, text="Draw two cards.", mana_cost="{2}{U}"
    )

    action = ai.get_action(
        p1.id,
        game.state,
        [
            LegalAction(type=ActionType.PASS),
            LegalAction(type=ActionType.CAST_SPELL, card_id=draw_spell.id),
        ],
    )
    observed = game.state.objects[action.card_id].name if action.card_id else action.type.name
    expected = "Quick Study"
    return ScenarioResult("cast_card_draw_over_pass", observed == expected, expected, observed)


def _burn_target_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, p2 = _game()
    bolt = _obj(
        game, p1.id, "Lightning Bolt", ZoneType.HAND,
        {CardType.INSTANT}, text="Lightning Bolt deals 3 damage to any target.", mana_cost="{R}"
    )
    threat = _obj(
        game, p2.id, "Killable Threat", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=3, toughness=3
    )
    p2.life = 12
    choice = PendingChoice(
        choice_type="target",
        player=p1.id,
        prompt="Choose any target",
        options=[threat.id, p2.id],
        source_id=bolt.id,
        min_choices=1,
        max_choices=1,
    )

    selected = ai.make_choice(p1.id, choice, game.state)
    expected = [threat.id]
    return ScenarioResult("burn_killable_creature_over_face", selected == expected, expected, selected)


def _lethal_burn_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, p2 = _game()
    bolt = _obj(
        game, p1.id, "Lightning Bolt", ZoneType.HAND,
        {CardType.INSTANT}, text="Lightning Bolt deals 3 damage to any target.", mana_cost="{R}"
    )
    threat = _obj(
        game, p2.id, "Killable Threat", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=3, toughness=3
    )
    p2.life = 3
    choice = PendingChoice(
        choice_type="target",
        player=p1.id,
        prompt="Choose any target",
        options=[threat.id, p2.id],
        source_id=bolt.id,
        min_choices=1,
        max_choices=1,
    )

    selected = ai.make_choice(p1.id, choice, game.state)
    expected = [p2.id]
    return ScenarioResult("lethal_burn_targets_opponent", selected == expected, expected, selected)


def _attack_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, _ = _game()
    attacker = _obj(
        game, p1.id, "Clean Attacker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=3, toughness=3
    )

    attacks = ai.get_attack_declarations(p1.id, game.state, [attacker.id])
    observed = [attack.attacker_id for attack in attacks]
    expected = [attacker.id]
    return ScenarioResult("attack_with_unblocked_creature", observed == expected, expected, observed)


def _menace_attack_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, p2 = _game()
    attacker = _obj(
        game, p1.id, "Menace Attacker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Menace", power=2, toughness=2
    )
    _obj(
        game, p2.id, "Solo Blocker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=3, toughness=3
    )

    attacks = ai.get_attack_declarations(p1.id, game.state, [attacker.id])
    observed = [attack.attacker_id for attack in attacks]
    expected = [attacker.id]
    return ScenarioResult("attack_with_underblocked_menace", observed == expected, expected, observed)


def _block_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, p2 = _game()
    attacker = _obj(
        game, p2.id, "Attacker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=3, toughness=3
    )
    small = _obj(
        game, p1.id, "Small Blocker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=1, toughness=1
    )
    large = _obj(
        game, p1.id, "Large Blocker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=4, toughness=4
    )

    blocks = ai.get_block_declarations(
        p1.id,
        game.state,
        [AttackDeclaration(attacker_id=attacker.id, defending_player_id=p1.id)],
        [small.id, large.id],
    )
    observed = [block.blocker_id for block in blocks]
    expected = [large.id]
    return ScenarioResult("block_with_profitable_creature", observed == expected, expected, observed)


def _avoid_trample_chump_scenario(ai: AIEngine) -> ScenarioResult:
    game, p1, p2 = _game()
    attacker = _obj(
        game, p2.id, "Huge Trampler", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Trample", power=5, toughness=5
    )
    chump = _obj(
        game, p1.id, "Small Blocker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=1, toughness=1
    )
    p1.life = 20

    blocks = ai.get_block_declarations(
        p1.id,
        game.state,
        [AttackDeclaration(attacker_id=attacker.id, defending_player_id=p1.id)],
        [chump.id],
    )
    observed = [block.blocker_id for block in blocks]
    expected: list[str] = []
    return ScenarioResult("avoid_nonlethal_trample_chump", observed == expected, expected, observed)


def run_fixed_decision_benchmark(
    output_dir: str | Path,
    *,
    seed: int = 17,
    difficulty: str = "hard",
) -> dict[str, Any]:
    """Run a compact deterministic AI benchmark and write trace artifacts."""
    benchmark = AIBenchmarkRun.create(
        "fixed_decision_smoke",
        seed=seed,
        output_dir=output_dir,
    )
    ai = AIEngine(strategy=MidrangeStrategy(), difficulty=difficulty)
    benchmark.attach(ai)

    results = [
        _play_land_scenario(ai),
        _answer_large_threat_scenario(ai),
        _cast_card_draw_over_pass_scenario(ai),
        _burn_target_scenario(ai),
        _lethal_burn_scenario(ai),
        _attack_scenario(ai),
        _menace_attack_scenario(ai),
        _block_scenario(ai),
        _avoid_trample_chump_scenario(ai),
    ]
    passed = sum(1 for result in results if result.passed)
    extra = {
        "scenario_count": len(results),
        "scenario_pass_count": passed,
        "scenario_pass_rate": round(passed / len(results), 3) if results else 0.0,
        "scenario_results": [result.to_dict() for result in results],
    }
    return benchmark.finish(extra=extra)


__all__ = ["ScenarioResult", "run_fixed_decision_benchmark"]
