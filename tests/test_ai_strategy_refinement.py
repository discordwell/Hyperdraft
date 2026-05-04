"""Regression coverage for MTG AI tracing and strategy refinement."""

import json

from src.ai import AIBenchmarkRun, AIEngine, BoardEvaluator, Heuristics
from src.ai.layers import CardLayers, CardStrategy, DeckAnalysis, DeckRole, MatchupAnalysis, MatchupGuide
from src.ai.strategies import MidrangeStrategy, UltraStrategy
from src.engine import (
    ActionType,
    AttackDeclaration,
    CardType,
    Characteristics,
    Game,
    LegalAction,
    ZoneType,
    has_ability,
)


class _CardDef:
    def __init__(self, text: str = ""):
        self.text = text
        self.setup_interceptors = None
        self.setup_in_hand = None


def _game():
    game = Game()
    p1 = game.add_player("AI")
    p2 = game.add_player("Opponent")
    return game, p1, p2


def _obj(game, owner, name, zone, types, text="", power=None, toughness=None, mana_cost=None):
    abilities = []
    for keyword in [
        "flying",
        "trample",
        "deathtouch",
        "lifelink",
        "vigilance",
        "menace",
        "first strike",
        "double strike",
        "haste",
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


def _land(game, owner, name="Land"):
    land = _obj(game, owner, name, ZoneType.BATTLEFIELD, {CardType.LAND})
    land.state.tapped = False
    return land


def _layers(card_name, role="removal", target_priority=None, save_for=None, dont_use_on=None, our_role="midrange"):
    return CardLayers(
        card_strategy=CardStrategy(
            card_name=card_name,
            role=role,
            target_priority=target_priority or ["creature"],
            base_priority=0.7,
        ),
        deck_role=DeckRole(
            card_name=card_name,
            deck_hash="deck",
            role_weight=1.1,
            is_key_card=(role == "finisher"),
        ),
        matchup_guide=MatchupGuide(
            card_name=card_name,
            matchup_hash="matchup",
            save_for=save_for or [],
            dont_use_on=dont_use_on or [],
        ),
        deck_analysis=DeckAnalysis(deck_hash="deck", archetype="midrange"),
        matchup_analysis=MatchupAnalysis(matchup_hash="matchup", our_role=our_role),
    )


def test_trace_recorder_writes_jsonl_and_summary(tmp_path):
    game, p1, _ = _game()
    land = _obj(game, p1.id, "Forest", ZoneType.HAND, {CardType.LAND})
    benchmark = AIBenchmarkRun.create("smoke", seed=7, output_dir=tmp_path)
    ai = AIEngine(difficulty="ultra")
    benchmark.attach(ai)

    action = ai.get_action(
        p1.id,
        game.state,
        [
            LegalAction(type=ActionType.PASS),
            LegalAction(type=ActionType.PLAY_LAND, card_id=land.id),
        ],
    )

    assert action.type == ActionType.PLAY_LAND
    lines = (tmp_path / "decisions.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["schema_version"] == "hyperdraft.ai.decision.v1"
    assert payload["decision_type"] == "action"
    assert payload["candidates"]

    summary = benchmark.finish()
    assert summary["decision_count"] == 1
    assert summary["benchmark_name"] == "smoke"
    assert summary["seed"] == 7
    assert "PLAY_LAND" in summary["action_mix"]
    assert (tmp_path / "summary.json").exists()


def test_staged_scoring_prefers_answering_large_threat():
    game, p1, p2 = _game()
    for idx in range(3):
        _land(game, p1.id, f"Swamp {idx}")
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

    ai = AIEngine(strategy=MidrangeStrategy(), difficulty="hard")
    action = ai.get_action(
        p1.id,
        game.state,
        [
            LegalAction(type=ActionType.CAST_SPELL, card_id=small_creature.id),
            LegalAction(type=ActionType.CAST_SPELL, card_id=removal.id),
        ],
    )

    assert action.card_id == removal.id


def test_layer_aware_targeting_honors_save_for_and_dont_use_on():
    game, p1, p2 = _game()
    removal = _obj(
        game, p1.id, "Precise Answer", ZoneType.HAND,
        {CardType.INSTANT}, text="Exile target creature.", mana_cost="{1}{W}"
    )
    token = _obj(game, p2.id, "Token", ZoneType.BATTLEFIELD, {CardType.CREATURE}, power=4, toughness=4)
    bomb = _obj(game, p2.id, "Bomb", ZoneType.BATTLEFIELD, {CardType.CREATURE}, power=2, toughness=2)

    strategy = MidrangeStrategy()
    strategy.set_card_layers(
        "Precise Answer",
        _layers("Precise Answer", save_for=["Bomb"], dont_use_on=["Token"]),
    )
    ai = AIEngine(strategy=strategy, difficulty="hard")
    targets = ai._select_target_ids_for_spell(removal, p1.id, game.state)

    assert targets == [bomb.id]
    assert token.id not in targets


def test_any_target_burn_removes_threat_before_nonlethal_face_damage():
    game, p1, p2 = _game()
    bolt = _obj(
        game, p1.id, "Lightning Bolt", ZoneType.HAND,
        {CardType.INSTANT}, text="Lightning Bolt deals 3 damage to any target.", mana_cost="{R}"
    )
    threat = _obj(
        game, p2.id, "Serra Angel", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Flying", power=4, toughness=4
    )
    p2.life = 14

    ai = AIEngine(strategy=MidrangeStrategy(), difficulty="hard")

    assert ai._select_target_ids_for_spell(bolt, p1.id, game.state) == [threat.id]


def test_any_target_burn_still_points_lethal_at_opponent():
    game, p1, p2 = _game()
    bolt = _obj(
        game, p1.id, "Lightning Bolt", ZoneType.HAND,
        {CardType.INSTANT}, text="Lightning Bolt deals 3 damage to any target.", mana_cost="{R}"
    )
    _obj(
        game, p2.id, "Serra Angel", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Flying", power=4, toughness=4
    )
    p2.life = 3

    ai = AIEngine(strategy=MidrangeStrategy(), difficulty="hard")

    assert ai._select_target_ids_for_spell(bolt, p1.id, game.state) == [p2.id]


def test_damage_spell_prefers_killable_creature_over_unkillable_threat():
    game, p1, p2 = _game()
    bolt = _obj(
        game, p1.id, "Lightning Bolt", ZoneType.HAND,
        {CardType.INSTANT}, text="Lightning Bolt deals 3 damage to any target.", mana_cost="{R}"
    )
    _obj(
        game, p2.id, "Ancient Dragon", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Flying", power=6, toughness=6
    )
    killable = _obj(
        game, p2.id, "Seasoned Duelist", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, power=3, toughness=3
    )
    p2.life = 14

    ai = AIEngine(strategy=MidrangeStrategy(), difficulty="hard")

    assert ai._select_target_ids_for_spell(bolt, p1.id, game.state) == [killable.id]


def test_ultra_role_changes_attack_posture():
    game, p1, p2 = _game()
    attacker = _obj(game, p1.id, "Ground Attacker", ZoneType.BATTLEFIELD, {CardType.CREATURE}, power=3, toughness=3)
    _obj(game, p2.id, "Crack Back", ZoneType.BATTLEFIELD, {CardType.CREATURE}, power=10, toughness=10)
    p1.life = 10

    strategy = UltraStrategy()
    strategy.set_card_layers("Role Card", _layers("Role Card", our_role="control"))
    evaluator = BoardEvaluator(game.state)
    control_attacks = strategy.plan_attacks(game.state, p1.id, evaluator, [attacker.id])
    assert control_attacks == []

    p1.life = 30
    strategy.set_card_layers("Role Card 2", _layers("Role Card 2", our_role="beatdown"))
    beatdown_attacks = strategy.plan_attacks(game.state, p1.id, evaluator, [attacker.id])
    assert len(beatdown_attacks) == 1
    assert beatdown_attacks[0].attacker_id == attacker.id


def test_midrange_attacks_with_menace_when_behind_and_underblocked():
    game, p1, p2 = _game()
    menace_attacker = _obj(
        game, p1.id, "Menace Attacker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Menace", power=2, toughness=2
    )
    _obj(game, p2.id, "Large Blocker", ZoneType.BATTLEFIELD, {CardType.CREATURE}, power=5, toughness=5)

    strategy = MidrangeStrategy()
    attacks = strategy.plan_attacks(game.state, p1.id, BoardEvaluator(game.state), [menace_attacker.id])

    assert len(attacks) == 1
    assert attacks[0].attacker_id == menace_attacker.id


def test_keyword_queries_accept_space_and_underscore_aliases():
    game, p1, _ = _game()
    first_striker = _obj(
        game, p1.id, "First Striker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="First strike", power=2, toughness=2
    )

    assert has_ability(first_striker, "first strike", game.state)
    assert has_ability(first_striker, "first_strike", game.state)


def test_combat_keyword_pain_points_are_assertions():
    game, p1, p2 = _game()
    first_striker = _obj(
        game, p2.id, "First Striker", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="First strike", power=2, toughness=2
    )
    vanilla = _obj(game, p1.id, "Vanilla", ZoneType.BATTLEFIELD, {CardType.CREATURE}, power=2, toughness=2)
    assert not Heuristics.should_block(vanilla, first_striker, my_life=20, state=game.state)

    deathtouch = _obj(
        game, p1.id, "Deathtouch", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Deathtouch", power=1, toughness=1
    )
    big = _obj(game, p2.id, "Big", ZoneType.BATTLEFIELD, {CardType.CREATURE}, power=5, toughness=5)
    assert Heuristics.should_block(deathtouch, big, my_life=20, state=game.state)

    chump = _obj(game, p1.id, "Chump", ZoneType.BATTLEFIELD, {CardType.CREATURE}, power=1, toughness=1)
    trampler = _obj(
        game, p2.id, "Trampler", ZoneType.BATTLEFIELD,
        {CardType.CREATURE}, text="Trample", power=5, toughness=5
    )
    assert not Heuristics.should_block(chump, trampler, my_life=20, state=game.state)
