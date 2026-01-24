/**
 * Battlefield Component
 *
 * Displays permanents on the battlefield for one player.
 */

import clsx from 'clsx';
import { Card } from '../cards';
import type { CardData } from '../../types';

interface BattlefieldProps {
  permanents: CardData[];
  isOpponent?: boolean;
  selectedCardId?: string | null;
  validTargets?: string[];
  selectedAttackers?: string[];
  selectedBlockers?: Map<string, string>;
  combatAttackers?: string[];
  onCardClick?: (card: CardData) => void;
}

export function Battlefield({
  permanents,
  isOpponent = false,
  selectedCardId,
  validTargets = [],
  selectedAttackers = [],
  selectedBlockers = new Map(),
  combatAttackers = [],
  onCardClick,
}: BattlefieldProps) {
  // Group permanents by type
  const creatures = permanents.filter((p) => p.types.includes('CREATURE'));
  const lands = permanents.filter((p) => p.types.includes('LAND'));
  const others = permanents.filter(
    (p) => !p.types.includes('CREATURE') && !p.types.includes('LAND')
  );

  const renderCardGroup = (cards: CardData[], label: string, icon: string) => {
    if (cards.length === 0) return null;

    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
            {label}
          </span>
          <span className="text-xs text-slate-500">({cards.length})</span>
        </div>
        <div className="flex flex-wrap gap-3">
          {cards.map((card) => {
            const isSelected = selectedCardId === card.id;
            const isTargetable = validTargets.includes(card.id);
            const isAttacking = selectedAttackers.includes(card.id);
            const isBlockingAttacker = combatAttackers.includes(card.id);
            const isBlocking = selectedBlockers.has(card.id);

            return (
              <div key={card.id} className="relative">
                <Card
                  card={card}
                  size="small"
                  isSelected={isSelected || isAttacking || isBlocking}
                  isTargetable={isTargetable}
                  isHighlighted={isBlockingAttacker}
                  onClick={() => onCardClick?.(card)}
                />
                {/* Attack indicator */}
                {isAttacking && (
                  <div className="absolute -top-1 -right-1 bg-gradient-to-br from-red-500 to-red-700 text-white text-[10px] px-2 py-0.5 rounded-full font-bold shadow-lg border border-red-400">
                    ⚔️ ATK
                  </div>
                )}
                {/* Block indicator */}
                {isBlocking && (
                  <div className="absolute -top-1 -right-1 bg-gradient-to-br from-blue-500 to-blue-700 text-white text-[10px] px-2 py-0.5 rounded-full font-bold shadow-lg border border-blue-400">
                    🛡️ BLK
                  </div>
                )}
                {/* Being attacked indicator */}
                {isBlockingAttacker && (
                  <div className="absolute -top-1 left-1/2 -translate-x-1/2 bg-gradient-to-br from-orange-500 to-orange-700 text-white text-[10px] px-2 py-0.5 rounded-full font-bold shadow-lg border border-orange-400">
                    ⚔️ Target
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div
      className={clsx(
        'p-4 rounded-xl min-h-[140px]',
        'border-2',
        isOpponent
          ? 'bg-gradient-to-b from-red-950/30 via-slate-900/50 to-slate-900/30 border-red-900/40'
          : 'bg-gradient-to-b from-emerald-950/30 via-slate-900/50 to-slate-900/30 border-emerald-900/40',
        {
          'order-first': isOpponent,
        }
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-slate-700/50">
        <span className={clsx('text-lg', isOpponent ? 'text-red-400' : 'text-emerald-400')}>
          {isOpponent ? '👤' : '🎮'}
        </span>
        <span className="text-xs text-slate-300 uppercase tracking-wider font-semibold">
          {isOpponent ? "Opponent's Battlefield" : 'Your Battlefield'}
        </span>
        <span className="text-xs text-slate-500">
          ({permanents.length} {permanents.length === 1 ? 'permanent' : 'permanents'})
        </span>
      </div>

      {permanents.length === 0 ? (
        <div className="text-slate-600 text-sm italic text-center py-6 border border-dashed border-slate-700 rounded-lg">
          No permanents in play
        </div>
      ) : (
        <div
          className={clsx('flex gap-8', {
            'flex-row-reverse': isOpponent,
          })}
        >
          {/* Creatures - main area */}
          <div className="flex-1">{renderCardGroup(creatures, 'Creatures', '⚔️')}</div>

          {/* Other permanents */}
          {others.length > 0 && (
            <div className="flex-shrink-0">{renderCardGroup(others, 'Other', '🔮')}</div>
          )}

          {/* Lands - compact on the side */}
          {lands.length > 0 && (
            <div className="flex-shrink-0 max-w-[250px]">
              {renderCardGroup(lands, 'Lands', '🏔️')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Battlefield;
