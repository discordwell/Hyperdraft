import asyncio


def test_llm_deck_analysis_prompt_includes_inferred_colors_and_curve():
    from src.ai.layers.generator import LayerGenerator
    from src.ai.llm.base import LLMProvider, LLMResponse
    from src.cards import ALL_CARDS

    class FakeProvider(LLMProvider):
        def __init__(self):
            self.prompts = []

        async def complete(self, prompt: str, system=None, temperature: float = 0.3) -> LLMResponse:
            raise AssertionError("Not used in this test")

        async def complete_json(self, prompt: str, schema: dict, system=None, temperature: float = 0.1) -> dict:
            self.prompts.append(prompt)
            return {
                "archetype": "control",
                "win_conditions": ["card advantage"],
                "key_cards": ["Negate"],
                "game_plan": "Survive and win late.",
            }

        @property
        def is_available(self) -> bool:
            return True

        @property
        def model_name(self) -> str:
            return "fake"

    provider = FakeProvider()
    gen = LayerGenerator(provider=provider, cache=None)

    # A tiny deck with clear UBR identity and known mana values.
    deck_cards = (
        ["Lightning Bolt"] * 4
        + ["Duress"] * 4
        + ["Negate"] * 4
        + ["Island"] * 10
        + ["Mountain"] * 10
        + ["Swamp"] * 10
    )

    analysis = asyncio.run(gen.generate_deck_analysis(deck_cards, card_defs=ALL_CARDS))

    assert provider.prompts, "Expected the fake provider to be called"
    prompt = provider.prompts[-1]
    assert "**Colors:** UBR" in prompt
    assert "**Mana Curve:** {1: 8, 2: 4}" in prompt
    assert analysis.curve == {1: 8, 2: 4}


def test_llm_matchup_guide_prompt_uses_matchup_analysis_threats_and_answers():
    from src.ai.layers.generator import LayerGenerator
    from src.ai.layers.types import DeckAnalysis, MatchupAnalysis
    from src.ai.llm.base import LLMProvider, LLMResponse
    from src.cards import ALL_CARDS

    class FakeProvider(LLMProvider):
        def __init__(self):
            self.prompts = []

        async def complete(self, prompt: str, system=None, temperature: float = 0.3) -> LLMResponse:
            raise AssertionError("Not used in this test")

        async def complete_json(self, prompt: str, schema: dict, system=None, temperature: float = 0.1) -> dict:
            self.prompts.append(prompt)
            return {
                "priority_modifier": 1.2,
                "save_for": ["Sheoldred, the Apocalypse"],
                "dont_use_on": ["1/1 token"],
                "matchup_role": "Important interaction.",
                "key_targets": "Big threats.",
                "timing_advice": "Hold if possible.",
            }

        @property
        def is_available(self) -> bool:
            return True

        @property
        def model_name(self) -> str:
            return "fake"

    provider = FakeProvider()
    gen = LayerGenerator(provider=provider, cache=None)

    our_deck = ["Lightning Bolt", "Negate", "Island", "Mountain"]
    opp_deck = ["Duress", "Swamp", "Sheoldred, the Apocalypse"]

    our_analysis = DeckAnalysis(deck_hash="h1", archetype="tempo")
    opp_analysis = DeckAnalysis(deck_hash="h2", archetype="midrange")
    matchup_analysis = MatchupAnalysis(
        matchup_hash="m1",
        our_role="control",
        their_threats=["Sheoldred, the Apocalypse"],
        their_answers=["Go for the Throat"],
        game_plan="Answer key threats and win late.",
        key_turns={},
    )

    card_def = ALL_CARDS["Lightning Bolt"]
    guide = asyncio.run(
        gen.generate_matchup_guide(
            card_def=card_def,
            our_deck=our_deck,
            opp_deck=opp_deck,
            our_analysis=our_analysis,
            opp_analysis=opp_analysis,
            matchup_analysis=matchup_analysis,
        )
    )

    assert provider.prompts, "Expected the fake provider to be called"
    prompt = provider.prompts[-1]
    assert "Threats to Watch: Sheoldred, the Apocalypse" in prompt
    assert "Their Answers: Go for the Throat" in prompt
    assert "save_for" in guide.to_dict()

