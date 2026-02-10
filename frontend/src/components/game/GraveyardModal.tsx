/**
 * GraveyardModal Component
 *
 * Lets the player inspect their graveyard and cast spells that are currently legal
 * to cast from the graveyard (flashback, harmonize, etc.).
 */

import { useMemo } from 'react';
import clsx from 'clsx';
import { Card } from '../cards';
import type { CardData, LegalActionData } from '../../types';

interface GraveyardModalProps {
  isOpen: boolean;
  title?: string;
  cards: CardData[];
  legalActions: LegalActionData[];
  canAct: boolean;
  onClose: () => void;
  onCast: (action: LegalActionData) => void;
}

function getCastButtonLabel(cardName: string, description: string): string {
  const prefix = `Cast ${cardName}`;
  if (description.startsWith(prefix)) {
    const rest = description.slice(prefix.length).trim();
    return rest.length > 0 ? `Cast ${rest}` : 'Cast';
  }
  return description;
}

export function GraveyardModal({
  isOpen,
  title = 'Graveyard',
  cards,
  legalActions,
  canAct,
  onClose,
  onCast,
}: GraveyardModalProps) {
  const castActionsByCardId = useMemo(() => {
    const ids = new Set(cards.map((c) => c.id));
    const map: Record<string, LegalActionData[]> = {};

    for (const action of legalActions) {
      if (action.type !== 'CAST_SPELL' || !action.card_id) continue;
      if (!ids.has(action.card_id)) continue;
      if (!map[action.card_id]) map[action.card_id] = [];
      map[action.card_id].push(action);
    }

    for (const cardId of Object.keys(map)) {
      map[cardId].sort((a, b) => a.description.localeCompare(b.description));
    }

    return map;
  }, [cards, legalActions]);

  const castableCount = useMemo(() => {
    return Object.values(castActionsByCardId).reduce((sum, actions) => sum + actions.length, 0);
  }, [castActionsByCardId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/80 backdrop-blur-md"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-gradient-to-b from-slate-800 to-slate-900 border-2 border-slate-600 rounded-2xl p-6 shadow-2xl max-w-5xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-4 pb-4 border-b border-slate-700">
          <div>
            <h2 className="text-xl font-bold text-white">{title}</h2>
            <p className="text-sm text-slate-400">
              {cards.length} {cards.length === 1 ? 'card' : 'cards'}
              {castableCount > 0 ? `, ${castableCount} cast option${castableCount === 1 ? '' : 's'}` : ''}
            </p>
            {!canAct && (
              <p className="text-xs text-amber-400 mt-1">
                You can only cast from graveyard while you have priority.
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="w-10 h-10 bg-slate-800 hover:bg-slate-700 text-white rounded-full flex items-center justify-center shadow-lg transition-colors"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {cards.length === 0 ? (
            <div className="text-slate-500 text-center py-10 italic border border-dashed border-slate-700 rounded-lg">
              No cards in graveyard
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              {cards.map((card) => {
                const actions = castActionsByCardId[card.id] || [];
                const isCastable = actions.length > 0;
                return (
                  <div
                    key={card.id}
                    className={clsx(
                      'rounded-xl p-2 border transition-colors',
                      isCastable ? 'border-cyan-500/50 bg-cyan-900/10' : 'border-slate-700 bg-slate-800/40'
                    )}
                  >
                    <Card
                      card={card}
                      size="small"
                      showDetails={true}
                      isHighlighted={isCastable}
                    />

                    {/* Cast buttons */}
                    <div className="mt-2 flex flex-col gap-1">
                      {actions.length === 0 ? (
                        <span className="text-[11px] text-slate-500 italic text-center py-1">
                          Not castable
                        </span>
                      ) : (
                        actions.map((action, idx) => (
                          <button
                            key={`${action.type}:${action.card_id ?? 'none'}:${action.ability_id ?? 'none'}:${action.source_id ?? 'none'}:${idx}`}
                            className={clsx(
                              'px-2 py-1 rounded text-[11px] font-semibold transition-all border',
                              canAct
                                ? 'bg-cyan-600/80 hover:bg-cyan-500 text-white border-cyan-400/60'
                                : 'bg-slate-700 text-slate-300 border-slate-600 cursor-not-allowed opacity-60'
                            )}
                            disabled={!canAct}
                            title={action.description}
                            onClick={() => onCast(action)}
                          >
                            {getCastButtonLabel(card.name, action.description)}
                            {action.requires_targets ? ' (target)' : ''}
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default GraveyardModal;

