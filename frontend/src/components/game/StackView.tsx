/**
 * StackView Component
 *
 * Displays items on the stack (spells and abilities waiting to resolve).
 */

import clsx from 'clsx';
import type { StackItemData } from '../../types';

interface StackViewProps {
  items: StackItemData[];
  playerId?: string;
}

export function StackView({ items, playerId }: StackViewProps) {
  if (items.length === 0) {
    return (
      <div className="p-3 rounded-lg bg-game-surface border border-gray-700 text-center">
        <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">
          The Stack
        </div>
        <div className="text-gray-500 text-sm italic">Empty</div>
      </div>
    );
  }

  return (
    <div className="p-3 rounded-lg bg-game-surface border border-purple-700 shadow-lg shadow-purple-500/20">
      <div className="text-xs text-purple-400 uppercase tracking-wide mb-2">
        The Stack ({items.length})
      </div>

      <div className="flex flex-col gap-2">
        {items.map((item, index) => {
          const isYours = item.controller === playerId;
          const isTopOfStack = index === items.length - 1;

          return (
            <div
              key={item.id}
              className={clsx(
                'p-2 rounded border transition-all',
                {
                  'bg-purple-900/50 border-purple-500 animate-pulse': isTopOfStack,
                  'bg-gray-800/50 border-gray-600': !isTopOfStack,
                  'border-l-4 border-l-blue-500': isYours,
                  'border-l-4 border-l-red-500': !isYours,
                }
              )}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-semibold text-white">
                    {item.source_name}
                  </span>
                  <span className="text-xs text-gray-400 ml-2">
                    ({item.type.replace('_', ' ')})
                  </span>
                </div>
                {isTopOfStack && (
                  <span className="text-xs bg-purple-500 text-white px-2 py-0.5 rounded-full">
                    Resolving Next
                  </span>
                )}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Controlled by: {isYours ? 'You' : 'Opponent'}
              </div>
            </div>
          );
        })}
      </div>

      {/* Resolution order hint */}
      <div className="mt-2 text-xs text-gray-500 text-center">
        ↑ Resolves first (LIFO)
      </div>
    </div>
  );
}

export default StackView;
