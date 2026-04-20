"""Pokemon TCG AI vs AI stress test with difficulty differentiation analysis."""
import asyncio
from dataclasses import dataclass, field
from src.engine.game import Game
from src.engine.types import EventType
from src.ai.pokemon_adapter import PokemonAIAdapter
from src.cards.pokemon.sv_starter import make_fire_deck, make_water_deck


@dataclass
class PlayerMetrics:
    total_attacks: int = 0
    total_kos: int = 0
    energy_attachments: int = 0
    trainer_plays: int = 0
    turns_played: int = 0
    idle_turns: int = 0
    retreat_count: int = 0
    evolution_count: int = 0

    @property
    def attack_rate(self) -> float:
        return self.total_attacks / max(self.turns_played, 1)

    @property
    def energy_rate(self) -> float:
        return self.energy_attachments / max(self.turns_played, 1)

    @property
    def trainer_rate(self) -> float:
        return self.trainer_plays / max(self.turns_played, 1)

    @property
    def idle_rate(self) -> float:
        return self.idle_turns / max(self.turns_played, 1)


async def run_game(game_num, p1_diff='medium', p2_diff='medium'):
    game = Game(mode='pokemon')
    p1 = game.add_player('P1')
    p2 = game.add_player('P2')

    game.setup_pokemon_player(p1, make_fire_deck())
    game.setup_pokemon_player(p2, make_water_deck())

    ai = PokemonAIAdapter(difficulty=p1_diff)
    ai.player_difficulties[p2.id] = p2_diff
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)

    game.turn_manager.turn_order = [p1.id, p2.id]
    await game.turn_manager.setup_game()

    max_turns = 200
    p1_metrics = PlayerMetrics()
    p2_metrics = PlayerMetrics()

    for turn in range(max_turns):
        if game.is_game_over():
            break
        # Track which player's turn
        current_player = game.turn_manager.turn_order[
            game.turn_manager.current_player_index]
        metrics = p1_metrics if current_player == p1.id else p2_metrics
        metrics.turns_played += 1

        events = await game.turn_manager.run_turn()
        turn_had_action = False
        for e in events:
            if e.type == EventType.PKM_ATTACK_DECLARE:
                metrics.total_attacks += 1
                turn_had_action = True
            elif e.type == EventType.PKM_KNOCKOUT:
                metrics.total_kos += 1
            elif e.type == EventType.PKM_ATTACH_ENERGY:
                metrics.energy_attachments += 1
                turn_had_action = True
            elif e.type in (EventType.PKM_PLAY_ITEM, EventType.PKM_PLAY_SUPPORTER,
                            EventType.PKM_PLAY_STADIUM):
                metrics.trainer_plays += 1
                turn_had_action = True
            elif e.type == EventType.PKM_RETREAT:
                metrics.retreat_count += 1
                turn_had_action = True
            elif e.type == EventType.PKM_EVOLVE:
                metrics.evolution_count += 1
                turn_had_action = True
        if not turn_had_action:
            metrics.idle_turns += 1

    winner = None
    win_reason = ''
    for pid, p in game.state.players.items():
        if p.prizes_remaining == 0:
            winner = 'P1' if pid == p1.id else 'P2'
            win_reason = 'prizes'
        if hasattr(p, 'has_lost') and p.has_lost:
            for oid, op in game.state.players.items():
                if oid != pid:
                    winner = 'P1' if oid == p1.id else 'P2'
            if not win_reason:
                lib_key = f"library_{pid}"
                lib_ct = len(game.state.zones[lib_key].objects) if lib_key in game.state.zones else 0
                active_key = f"active_spot_{pid}"
                bench_key = f"bench_{pid}"
                active_ct = len(game.state.zones[active_key].objects) if active_key in game.state.zones else 0
                bench_ct = len(game.state.zones[bench_key].objects) if bench_key in game.state.zones else 0
                if lib_ct == 0:
                    win_reason = 'deck_out'
                elif active_ct == 0 and bench_ct == 0:
                    win_reason = 'no_pokemon'
                else:
                    win_reason = 'unknown'

    turn_count = game.turn_manager.pkm_turn_state.turn_number
    game_over = game.is_game_over()
    if not game_over:
        win_reason = 'TIMEOUT'

    return {
        'game_num': game_num, 'turns': turn_count, 'over': game_over,
        'winner': winner, 'reason': win_reason,
        'p1_prizes': p1.prizes_remaining, 'p2_prizes': p2.prizes_remaining,
        'p1_metrics': p1_metrics, 'p2_metrics': p2_metrics,
    }


def check_regressions(results: list[dict], difficulty: str) -> list[str]:
    """Check for AI regressions. Returns list of issues.

    Thresholds are per-game (both players combined) since in Pokemon TCG,
    a dominated player may rarely attack (their active keeps getting KO'd).
    """
    issues = []
    for r in results:
        m1, m2 = r['p1_metrics'], r['p2_metrics']
        total_turns = m1.turns_played + m2.turns_played
        if total_turns == 0:
            continue
        # Combined energy rate
        combined_energy = (m1.energy_attachments + m2.energy_attachments) / max(total_turns, 1)
        if combined_energy < 0.4:
            issues.append(f"CRITICAL: {difficulty} G{r['game_num']} combined energy rate {combined_energy:.0%} < 40%")
        # Combined attack rate (many setup turns have no attacks - 20% is reasonable)
        combined_attacks = (m1.total_attacks + m2.total_attacks) / max(total_turns, 1)
        if combined_attacks < 0.10:
            issues.append(f"CRITICAL: {difficulty} G{r['game_num']} combined attack rate {combined_attacks:.0%} < 10%")
        # Combined idle rate
        combined_idle = (m1.idle_turns + m2.idle_turns) / max(total_turns, 1)
        if combined_idle > 0.4:
            issues.append(f"CRITICAL: {difficulty} G{r['game_num']} combined idle rate {combined_idle:.0%} > 40%")
        # At least some trainer plays across both players
        if m1.trainer_plays + m2.trainer_plays == 0 and total_turns > 6:
            issues.append(f"CRITICAL: {difficulty} G{r['game_num']} neither player played trainers")
    return issues


async def main():
    print('Pokemon TCG AI vs AI Stress Test (Enhanced)')
    print('=' * 70)
    games_per = 10
    all_issues = []

    # Same-difficulty matchups
    for diff in ['easy', 'medium', 'hard', 'ultra']:
        print(f'\n{diff.upper()} vs {diff.upper()} ({games_per} games):')
        results = []
        for i in range(games_per):
            r = await run_game(i + 1, diff, diff)
            results.append(r)
            status = r['winner'] or 'Draw'
            m1, m2 = r['p1_metrics'], r['p2_metrics']
            print(f"  G{r['game_num']:>2}: {r['turns']:>3}t | {status:<4} | "
                  f"P:{r['p1_prizes']}/{r['p2_prizes']} | "
                  f"Atk:{m1.total_attacks+m2.total_attacks:>2} "
                  f"KO:{m1.total_kos+m2.total_kos} "
                  f"Evo:{m1.evolution_count+m2.evolution_count} | {r['reason']}")

        wins = {'P1': 0, 'P2': 0}
        total_attacks = 0
        total_kos = 0
        total_turns = 0
        for r in results:
            if r['winner']:
                wins[r['winner']] = wins.get(r['winner'], 0) + 1
            total_attacks += r['p1_metrics'].total_attacks + r['p2_metrics'].total_attacks
            total_kos += r['p1_metrics'].total_kos + r['p2_metrics'].total_kos
            total_turns += r['turns']

        avg_energy = sum(
            m.energy_rate for r in results
            for m in [r['p1_metrics'], r['p2_metrics']]
            if m.turns_played > 0) / max(1, sum(
            1 for r in results for m in [r['p1_metrics'], r['p2_metrics']]
            if m.turns_played > 0))
        avg_attack = sum(
            m.attack_rate for r in results
            for m in [r['p1_metrics'], r['p2_metrics']]
            if m.turns_played > 0) / max(1, sum(
            1 for r in results for m in [r['p1_metrics'], r['p2_metrics']]
            if m.turns_played > 0))

        print(f"  ---")
        print(f"  Wins: P1={wins.get('P1',0)} P2={wins.get('P2',0)}")
        print(f"  Avg turns: {total_turns/games_per:.0f} | "
              f"Avg attacks: {total_attacks/games_per:.1f} | "
              f"Avg KOs: {total_kos/games_per:.1f}")
        print(f"  Avg energy rate: {avg_energy:.0%} | "
              f"Avg attack rate: {avg_attack:.0%}")

        issues = check_regressions(results, diff)
        all_issues.extend(issues)

    # Cross-difficulty matchups
    cross_matchups = [('easy', 'hard'), ('medium', 'ultra')]
    for d1, d2 in cross_matchups:
        print(f'\n{d1.upper()} vs {d2.upper()} ({games_per} games):')
        results = []
        for i in range(games_per):
            r = await run_game(i + 1, d1, d2)
            results.append(r)
            print(f"  G{r['game_num']:>2}: {r['turns']:>3}t | {r['winner'] or 'Draw':<4} | "
                  f"P:{r['p1_prizes']}/{r['p2_prizes']} | {r['reason']}")

        p1_wins = sum(1 for r in results if r['winner'] == 'P1')
        p2_wins = sum(1 for r in results if r['winner'] == 'P2')
        print(f"  ---")
        print(f"  {d1}: {p1_wins} wins | {d2}: {p2_wins} wins")
        if p1_wins > p2_wins * 1.5:
            all_issues.append(
                f"WARNING: {d1} beating {d2} {p1_wins}-{p2_wins} (expected {d2} to win more)")

    # Summary
    print(f'\n{"=" * 70}')
    if all_issues:
        print(f'ISSUES ({len(all_issues)}):')
        for issue in all_issues:
            print(f'  {issue}')
    else:
        print('ALL CHECKS PASSED')


if __name__ == '__main__':
    asyncio.run(main())
