"""Pokemon TCG AI vs AI stress test."""
import asyncio
from src.engine.game import Game
from src.engine.types import EventType
from src.ai.pokemon_adapter import PokemonAIAdapter
from src.cards.pokemon.sv_starter import make_fire_deck, make_water_deck


async def run_game(game_num, difficulty='medium'):
    game = Game(mode='pokemon')
    p1 = game.add_player('Fire Player')
    p2 = game.add_player('Water Player')

    game.setup_pokemon_player(p1, make_fire_deck())
    game.setup_pokemon_player(p2, make_water_deck())

    ai = PokemonAIAdapter(difficulty=difficulty)
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)

    game.turn_manager.turn_order = [p1.id, p2.id]
    await game.turn_manager.setup_game()

    max_turns = 200
    attack_count = 0
    ko_count = 0
    for turn in range(max_turns):
        if game.is_game_over():
            break
        events = await game.turn_manager.run_turn()
        for e in events:
            if e.type == EventType.PKM_ATTACK_DECLARE:
                attack_count += 1
            elif e.type == EventType.PKM_KNOCKOUT:
                ko_count += 1

    winner = None
    win_reason = ''
    for pid, p in game.state.players.items():
        if p.prizes_remaining == 0:
            winner = p.name
            win_reason = 'prizes'
        if hasattr(p, 'has_lost') and p.has_lost:
            for oid, op in game.state.players.items():
                if oid != pid:
                    winner = op.name
            if not win_reason:
                active_key = f"active_spot_{pid}"
                bench_key = f"bench_{pid}"
                lib_key = f"library_{pid}"
                active_ct = len(game.state.zones[active_key].objects) if active_key in game.state.zones else 0
                bench_ct = len(game.state.zones[bench_key].objects) if bench_key in game.state.zones else 0
                lib_ct = len(game.state.zones[lib_key].objects) if lib_key in game.state.zones else 0
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
    return game_num, turn_count, game_over, winner, p1.prizes_remaining, p2.prizes_remaining, win_reason, attack_count, ko_count


async def main():
    print('Pokemon TCG AI vs AI Stress Test')
    print('=' * 60)

    for diff in ['medium', 'hard']:
        count = 5
        print(f'\n{diff.upper()} difficulty ({count} games):')
        wins = {'Fire Player': 0, 'Water Player': 0}
        reasons = {}
        total_turns = 0
        total_attacks = 0
        total_kos = 0

        for i in range(count):
            num, turns, over, winner, p1p, p2p, reason, attacks, kos = await run_game(i + 1, diff)
            status = f'{winner}' if winner else 'Draw'
            print(f'  Game {num}: {turns:>3}t | {status:<14} | P:{p1p}/{p2p} | Atk:{attacks:>2} KO:{kos} | {reason}')
            if winner:
                wins[winner] = wins.get(winner, 0) + 1
            reasons[reason] = reasons.get(reason, 0) + 1
            total_turns += turns
            total_attacks += attacks
            total_kos += kos

        print(f'  ---')
        print(f'  Wins: Fire={wins.get("Fire Player",0)} Water={wins.get("Water Player",0)}')
        print(f'  Avg turns: {total_turns/count:.0f} | Avg attacks: {total_attacks/count:.1f} | Avg KOs: {total_kos/count:.1f}')
        print(f'  End reasons: {reasons}')


if __name__ == '__main__':
    asyncio.run(main())
