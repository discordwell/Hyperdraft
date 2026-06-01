"""Fire gate for scp — full AI-vs-AI self-play across the whole deck matrix.

The effect gate (test_scp_cards.py) proves each card's effect *works*; this proves the AI
actually *fires* the mechanics in real games (CLAUDE.md: a card/ability isn't done until the
AI fires it in self-play — the scp analogue of /card-fire-debug). It runs every Foundation ×
Insurgency pairing over a few seeds, asserts games terminate with a winner, and censuses that
every core verb fired at least once across the matrix.

It also prints the win-reason / per-faction split — informational here; Phase 4 tunes it.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python3 -m pytest tests/test_scp_selfplay.py -q -s
"""

import asyncio
import random
from collections import Counter

import pytest

from src.engine.game import Game
from src.engine import scp
from src.cards.scp import decks as D
from src.ai.scp_adapter import SCPAIAdapter

TURN_CAP = 160  # 80 turns/side; healthy games close well under this


async def _play_game(foundation_label, insurgency_label, seed, difficulty="medium"):
    g = Game(mode="scp")
    f = g.add_player("Foundation")
    i = g.add_player("Insurgency")
    fident, fbuild = D.SCP_FOUNDATION_DECKS[foundation_label]
    iident, ibuild = D.SCP_INSURGENCY_DECKS[insurgency_label]
    scp.setup_scp_game(g, f, i, foundation_deck=fbuild(), insurgency_deck=ibuild(),
                         foundation_identity=fident, insurgency_identity=iident,
                         rng=random.Random(seed))
    adapter = SCPAIAdapter(difficulty)
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
            # Track the rez/break mini-game: a rezzed layer is either broken or eaten (subroutine fires).
            if e.type.name == "SCP_LAYER_ENCOUNTER" and e.payload.get("rezzed"):
                census["_encounter_broken" if e.payload.get("broken") else "_encounter_eaten"] += 1
            if e.type.name == "SCP_WIN":
                win = e.payload
    return {
        "foundation": foundation_label, "insurgency": insurgency_label, "seed": seed,
        "f_id": f.id, "i_id": i.id, "census": census, "win": win, "turns": turns,
        "over": g.is_game_over(),
    }


def _run_matrix(seeds=(1, 2, 3)):
    results = []
    for fl in D.SCP_FOUNDATION_DECKS:
        for il in D.SCP_INSURGENCY_DECKS:
            for s in seeds:
                results.append(asyncio.run(_play_game(fl, il, s)))
    return results


@pytest.fixture(scope="module")
def matrix():
    return _run_matrix()


def test_all_games_terminate_with_a_winner(matrix):
    stalls = [(r["foundation"], r["insurgency"], r["seed"], r["turns"]) for r in matrix if not r["over"]]
    assert not stalls, f"games stalled past the turn cap (AI can't close): {stalls}"
    assert all(r["win"] for r in matrix), "every finished game must record an SCP_WIN"


def test_core_verbs_all_fire_in_selfplay(matrix):
    agg = Counter()
    for r in matrix:
        agg.update(r["census"])
    required = [
        "SCP_INSTALL",        # cards get installed
        "SCP_ADVANCE",        # Foundation advances anomalies
        "SCP_CONTAIN",        # Foundation locks points
        "SCP_INFILTRATE",     # Insurgency runs
        "SCP_LAYER_ENCOUNTER",  # runs meet defenses
        "SCP_FREE",           # anomalies get stolen
        "SCP_SABOTAGE",       # central runs (HQ/Research/Archives) actually happen — the disruption axis
        "SCP_ACTIVATE",       # asset/tool abilities get used
        "SCP_BREACH",         # the Total Breach clock moves
        "SCP_WIN",            # games resolve
    ]
    missing = [v for v in required if agg.get(v, 0) == 0]
    assert not missing, f"core verbs never fired across the whole matrix: {missing}\ncensus={dict(agg)}"
    # Some punishment surface (sentry/sensor/trap) must engage too.
    assert agg.get("SCP_DAMAGE", 0) + agg.get("SCP_EXPOSE", 0) > 0, "no defensive punishment ever fired"
    # The rez/break mini-game must actually be *played*: runs both break layers and eat subroutines.
    assert agg.get("_encounter_broken", 0) > 0, "no rezzed layer was ever broken (break path dead)"
    assert agg.get("_encounter_eaten", 0) > 0, "no rezzed layer was ever eaten (subroutine choice dead)"


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
    print("\n[scp self-play matrix]",
          f"{len(matrix)} games | faction split = {dict(by_faction)} | reasons = {dict(by_reason)}")
    avg_turns = sum(r["turns"] for r in matrix) / max(1, len(matrix))
    print(f"[scp self-play matrix] avg turns/game = {avg_turns:.1f}")
    assert sum(by_faction.values()) == len(matrix)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-s"]))
