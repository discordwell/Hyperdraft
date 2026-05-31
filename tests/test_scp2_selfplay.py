"""Fire gate for scp2 — full AI-vs-AI self-play across the whole deck matrix.

The effect gate (test_scp2_cards.py) proves each card's effect *works*; this proves the AI
actually *fires* the mechanics in real games (CLAUDE.md: a card/ability isn't done until the
AI fires it in self-play — the scp2 analogue of /card-fire-debug). It runs every Foundation ×
Insurgency pairing over a few seeds, asserts games terminate with a winner, and censuses that
every core verb fired at least once across the matrix.

It also prints the win-reason / per-faction split — informational here; Phase 4 tunes it.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python3 -m pytest tests/test_scp2_selfplay.py -q -s
"""

import asyncio
import random
from collections import Counter

import pytest

from src.engine.game import Game
from src.engine import scp2
from src.cards.scp2 import decks as D
from src.ai.scp2_adapter import SCP2AIAdapter

TURN_CAP = 160  # 80 turns/side; healthy games close well under this


async def _play_game(foundation_label, insurgency_label, seed, difficulty="medium"):
    g = Game(mode="scp2")
    f = g.add_player("Foundation")
    i = g.add_player("Insurgency")
    fident, fbuild = D.SCP2_FOUNDATION_DECKS[foundation_label]
    iident, ibuild = D.SCP2_INSURGENCY_DECKS[insurgency_label]
    scp2.setup_scp2_game(g, f, i, foundation_deck=fbuild(), insurgency_deck=ibuild(),
                         foundation_identity=fident, insurgency_identity=iident,
                         rng=random.Random(seed))
    adapter = SCP2AIAdapter(difficulty)
    g.turn_manager.set_ai_handler(adapter)
    g.turn_manager.set_ai_player(f.id)
    g.turn_manager.set_ai_player(i.id)

    census = Counter()
    win = None
    turns = 0
    for _ in range(TURN_CAP):
        if g.is_game_over():
            break
        events = await g.turn_manager.run_turn()
        turns += 1
        for e in events:
            census[e.type.name] += 1
            if e.type.name == "SCP2_WIN":
                win = e.payload
    return {
        "foundation": foundation_label, "insurgency": insurgency_label, "seed": seed,
        "f_id": f.id, "i_id": i.id, "census": census, "win": win, "turns": turns,
        "over": g.is_game_over(),
    }


def _run_matrix(seeds=(1, 2, 3)):
    results = []
    for fl in D.SCP2_FOUNDATION_DECKS:
        for il in D.SCP2_INSURGENCY_DECKS:
            for s in seeds:
                results.append(asyncio.run(_play_game(fl, il, s)))
    return results


@pytest.fixture(scope="module")
def matrix():
    return _run_matrix()


def test_all_games_terminate_with_a_winner(matrix):
    stalls = [(r["foundation"], r["insurgency"], r["seed"], r["turns"]) for r in matrix if not r["over"]]
    assert not stalls, f"games stalled past the turn cap (AI can't close): {stalls}"
    assert all(r["win"] for r in matrix), "every finished game must record an SCP2_WIN"


def test_core_verbs_all_fire_in_selfplay(matrix):
    agg = Counter()
    for r in matrix:
        agg.update(r["census"])
    required = [
        "SCP2_INSTALL",        # cards get installed
        "SCP2_ADVANCE",        # Foundation advances anomalies
        "SCP2_CONTAIN",        # Foundation locks points
        "SCP2_INFILTRATE",     # Insurgency runs
        "SCP2_LAYER_ENCOUNTER",  # runs meet defenses
        "SCP2_FREE",           # anomalies get stolen
        "SCP2_ACTIVATE",       # asset/tool abilities get used
        "SCP2_BREACH",         # the Total Breach clock moves
        "SCP2_WIN",            # games resolve
    ]
    missing = [v for v in required if agg.get(v, 0) == 0]
    assert not missing, f"core verbs never fired across the whole matrix: {missing}\ncensus={dict(agg)}"
    # Some punishment surface (sentry/sensor/trap) must engage too.
    assert agg.get("SCP2_DAMAGE", 0) + agg.get("SCP2_EXPOSE", 0) > 0, "no defensive punishment ever fired"


def test_report_win_split(matrix):
    # Informational: which faction wins, and why. Phase 4 tunes toward a healthy split.
    by_reason = Counter()
    by_faction = Counter()
    for r in matrix:
        w = r["win"]
        if not w:
            continue
        by_reason[w.get("reason")] += 1
        by_faction["Foundation" if w.get("winner") == r["f_id"] else "Insurgency"] += 1
    print("\n[scp2 self-play matrix]",
          f"{len(matrix)} games | faction split = {dict(by_faction)} | reasons = {dict(by_reason)}")
    avg_turns = sum(r["turns"] for r in matrix) / max(1, len(matrix))
    print(f"[scp2 self-play matrix] avg turns/game = {avg_turns:.1f}")
    assert sum(by_faction.values()) == len(matrix)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-s"]))
