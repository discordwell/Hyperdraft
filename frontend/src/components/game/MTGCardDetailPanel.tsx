/**
 * MTGCardDetailPanel
 *
 * Fixed-position detail panel showing enlarged MTG card info on hover/pin.
 * Parchment / gold theme to match MTG aesthetic.
 *
 * Reads the active card from `useActivePreviewCard`. Players hover to peek;
 * right-click (desktop) or long-press (mobile) to pin. Clicking the pin close
 * button unpins.
 */

import { useEffect, useMemo, useState } from 'react';
import clsx from 'clsx';
import { useActivePreviewCard, useCardPreviewStore } from '../../hooks/useCardPreview';
import { parseManaSymbols } from '../../types/cards';
import { getPossibleArtPaths } from '../../utils/cardArt';

function ManaSymbol({ symbol }: { symbol: string }) {
  const colorMap: Record<string, string> = {
    W: 'bg-gradient-to-br from-amber-100 to-amber-200 text-amber-900 border-amber-400',
    U: 'bg-gradient-to-br from-blue-400 to-blue-600 text-white border-blue-700',
    B: 'bg-gradient-to-br from-gray-700 to-gray-900 text-gray-200 border-gray-950',
    R: 'bg-gradient-to-br from-red-500 to-red-700 text-white border-red-800',
    G: 'bg-gradient-to-br from-green-500 to-green-700 text-white border-green-800',
    C: 'bg-gradient-to-br from-gray-300 to-gray-400 text-gray-800 border-gray-500',
  };
  const isNumber = /^\d+$/.test(symbol);
  return (
    <span
      className={clsx(
        'w-6 h-6 text-xs rounded-full inline-flex items-center justify-center font-bold border shadow-sm flex-shrink-0',
        isNumber
          ? 'bg-gradient-to-br from-gray-200 to-gray-400 text-gray-800 border-gray-500'
          : colorMap[symbol] || 'bg-gray-400 text-white border-gray-500',
      )}
    >
      {symbol}
    </span>
  );
}

export default function MTGCardDetailPanel() {
  const card = useActivePreviewCard();
  const pinnedCard = useCardPreviewStore((s) => s.pinnedCard);
  const unpin = useCardPreviewStore((s) => s.unpin);

  const manaSymbols = useMemo(
    () => (card?.mana_cost ? parseManaSymbols(card.mana_cost) : []),
    [card?.mana_cost],
  );

  const possiblePaths = useMemo(
    () => (card ? getPossibleArtPaths(card.name) : []),
    [card?.name],
  );
  const [artIndex, setArtIndex] = useState(0);
  const [artFailed, setArtFailed] = useState(false);

  // Reset art state when card changes
  useEffect(() => {
    setArtIndex(0);
    setArtFailed(false);
  }, [card?.id]);

  if (!card) return null;

  const isPinned = pinnedCard?.id === card.id;
  const isCreature = card.types.includes('CREATURE');
  const isLand = card.types.includes('LAND');

  return (
    <div
      className="fixed right-4 top-1/2 -translate-y-1/2 z-[60] w-[300px] bg-gradient-to-b from-amber-100 via-amber-50 to-stone-200 border-2 border-amber-700/60 rounded-xl shadow-2xl shadow-black/60 overflow-hidden pointer-events-auto"
      // Don't let clicks/hover bleed to cards behind the panel
      onMouseEnter={(e) => e.stopPropagation()}
    >
      {/* Header: name + mana cost */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-amber-200/80 to-amber-100/60 border-b border-amber-700/40">
        <span className="font-serif font-bold text-gray-900 text-base truncate flex-1">
          {card.name}
        </span>
        {manaSymbols.length > 0 && (
          <div className="flex gap-0.5 flex-shrink-0">
            {manaSymbols.map((s, i) => (
              <ManaSymbol key={i} symbol={s} />
            ))}
          </div>
        )}
      </div>

      {/* Art */}
      <div className="px-3 pt-3">
        <div className="w-full h-[160px] rounded border-2 border-amber-800/40 bg-gradient-to-br from-stone-700 to-stone-900 flex items-center justify-center overflow-hidden">
          {!artFailed && possiblePaths.length > 0 ? (
            <img
              src={possiblePaths[artIndex]}
              alt={card.name}
              className="w-full h-full object-cover"
              onError={() => {
                if (artIndex < possiblePaths.length - 1) {
                  setArtIndex((i) => i + 1);
                } else {
                  setArtFailed(true);
                }
              }}
            />
          ) : (
            <span className="text-4xl opacity-60">
              {isCreature ? '⚔️' : isLand ? '🏔️' : '📜'}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="p-3 space-y-2 text-sm">
        {/* Type line */}
        <div className="px-2 py-1 rounded border border-amber-700/30 bg-white/60 text-gray-800 text-xs font-medium">
          {card.types.join(' ')}
          {card.subtypes.length > 0 && ` — ${card.subtypes.join(' ')}`}
        </div>

        {/* Full text — NO TRUNCATION */}
        <div className="px-2 py-2 rounded border border-amber-700/30 bg-white/80 text-gray-800 text-xs leading-relaxed min-h-[3rem] whitespace-pre-line">
          {card.text || <span className="italic opacity-50">No abilities</span>}
        </div>

        {/* Keywords */}
        {card.keywords && card.keywords.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {card.keywords.map((kw, i) => (
              <span
                key={i}
                className="px-1.5 py-0.5 bg-purple-700 text-purple-100 text-[10px] font-bold rounded uppercase"
              >
                {kw}
              </span>
            ))}
          </div>
        )}

        {/* P/T for creatures */}
        {isCreature && card.power !== null && card.toughness !== null && (
          <div className="flex items-center justify-end gap-2">
            <span className="text-[10px] uppercase tracking-wide text-gray-600">Power / Toughness</span>
            <span className="inline-block px-2 py-0.5 rounded bg-white border-2 border-amber-800/40 text-gray-900 font-bold text-base font-serif">
              {card.power}/{card.toughness}
              {card.damage > 0 && <span className="text-red-600 ml-1 text-sm">(-{card.damage})</span>}
            </span>
          </div>
        )}

        {/* Counters */}
        {Object.keys(card.counters).length > 0 && (
          <div className="flex flex-wrap gap-1">
            {Object.entries(card.counters).map(([type, count]) => (
              <span
                key={type}
                className="px-2 py-0.5 bg-purple-600 text-white text-[11px] rounded-full font-bold shadow-md border border-purple-400"
              >
                +{count} {type}
              </span>
            ))}
          </div>
        )}

        {/* Pin indicator / unpin control */}
        {isPinned && (
          <button
            type="button"
            onClick={unpin}
            className="w-full mt-1 px-2 py-1 rounded bg-amber-700 hover:bg-amber-600 text-white text-[11px] font-bold uppercase tracking-wide shadow"
          >
            📌 Pinned · Click to dismiss
          </button>
        )}
      </div>
    </div>
  );
}
