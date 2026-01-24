/**
 * PlayerInfo Component
 *
 * Displays player information: life total, hand size, library size.
 */

import clsx from 'clsx';
import type { PlayerData } from '../../types';

interface PlayerInfoProps {
  player: PlayerData;
  isActivePlayer?: boolean;
  hasPriority?: boolean;
  isOpponent?: boolean;
  manaPool?: Record<string, number>;
}

export function PlayerInfo({
  player,
  isActivePlayer = false,
  hasPriority = false,
  isOpponent = false,
}: PlayerInfoProps) {
  return (
    <div
      className={clsx(
        'flex items-center gap-4 p-3 rounded-lg transition-all',
        'bg-game-surface border',
        {
          'border-game-accent shadow-lg shadow-game-accent/30': hasPriority,
          'border-game-gold': isActivePlayer && !hasPriority,
          'border-gray-700': !isActivePlayer && !hasPriority,
          'flex-row-reverse': isOpponent,
        }
      )}
    >
      {/* Avatar/Name */}
      <div className="flex items-center gap-2">
        <div
          className={clsx(
            'w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold',
            isOpponent ? 'bg-red-600' : 'bg-blue-600'
          )}
        >
          {player.name[0].toUpperCase()}
        </div>
        <div>
          <div className="font-semibold text-white">{player.name}</div>
          {player.has_lost && (
            <div className="text-xs text-red-400">Defeated</div>
          )}
        </div>
      </div>

      {/* Life Total */}
      <div className="flex items-center gap-1">
        <span className="text-2xl">❤️</span>
        <span
          className={clsx('text-2xl font-bold', {
            'text-red-400': player.life <= 5,
            'text-yellow-400': player.life > 5 && player.life <= 10,
            'text-white': player.life > 10,
          })}
        >
          {player.life}
        </span>
      </div>

      {/* Hand Size */}
      <div className="flex items-center gap-1" title="Cards in hand">
        <span className="text-lg">🃏</span>
        <span className="text-lg font-semibold text-gray-300">
          {player.hand_size}
        </span>
      </div>

      {/* Library Size */}
      <div className="flex items-center gap-1" title="Cards in library">
        <span className="text-lg">📚</span>
        <span className="text-lg font-semibold text-gray-300">
          {player.library_size}
        </span>
      </div>

      {/* Status Indicators */}
      <div className="flex gap-1">
        {isActivePlayer && (
          <span
            className="px-2 py-0.5 bg-game-gold text-black text-xs rounded-full font-semibold"
            title="Active Player"
          >
            Active
          </span>
        )}
        {hasPriority && (
          <span
            className="px-2 py-0.5 bg-game-accent text-white text-xs rounded-full font-semibold animate-pulse"
            title="Has Priority"
          >
            Priority
          </span>
        )}
      </div>
    </div>
  );
}

export default PlayerInfo;
