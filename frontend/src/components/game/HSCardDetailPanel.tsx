/**
 * HSCardDetailPanel
 *
 * Fixed-position detail panel showing enlarged Hearthstone card info on
 * hover / pin. Dark + gold theme to match HS aesthetic.
 *
 * Renders full card text (no truncation) so redesigned legendary effects are
 * always readable. Shows minion runtime state (current HP, damage, frozen,
 * divine shield, stealth, summoning sickness) when displaying a minion on the
 * battlefield.
 */

import { useEffect, useMemo, useState } from 'react';
import { useActivePreviewCard, useCardPreviewStore } from '../../hooks/useCardPreview';
import { getHearthstoneArtPaths } from '../../utils/cardArt';

function parseMana(manaCost: string | null): number {
  if (!manaCost) return 0;
  const match = manaCost.match(/\{(\d+)\}/);
  return match ? parseInt(match[1], 10) : 0;
}

interface HSCardDetailPanelProps {
  /** Optional override so callers can pass a variant from their gameState. */
  variant?: string | null;
}

export default function HSCardDetailPanel({ variant }: HSCardDetailPanelProps = {}) {
  const card = useActivePreviewCard();
  const pinnedCard = useCardPreviewStore((s) => s.pinnedCard);
  const unpin = useCardPreviewStore((s) => s.unpin);

  const artPaths = useMemo(
    () => (card ? getHearthstoneArtPaths(card.name, variant) : []),
    [card?.name, variant],
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
  const manaValue = parseMana(card.mana_cost);
  const isMinion = card.types.includes('MINION') || card.types.includes('CREATURE');
  const isWeapon = card.types.includes('WEAPON');

  const cardTypeLabel = isMinion ? 'MINION' : isWeapon ? 'WEAPON' : 'SPELL';

  // Strip affinity marker from displayed text but show it as badges separately
  const displayText = (card.text || '').replace(/\[AF:\d+\/\d+\/\d+\]\s*/i, '');
  const affinityMatch = card.text?.match(/\[AF:(\d+)\/(\d+)\/(\d+)\]/i);
  const affinity = affinityMatch
    ? {
        azure: Number.parseInt(affinityMatch[1] || '0', 10) || 0,
        ember: Number.parseInt(affinityMatch[2] || '0', 10) || 0,
        verdant: Number.parseInt(affinityMatch[3] || '0', 10) || 0,
      }
    : null;

  // Minion runtime state
  const maxHealth = card.toughness ?? 0;
  const currentHealth = maxHealth - (card.damage || 0);
  const isDamaged = currentHealth < maxHealth;

  return (
    <div
      className="fixed right-4 top-1/2 -translate-y-1/2 z-[60] w-[280px] bg-gradient-to-b from-gray-900 via-gray-950 to-black border-2 border-yellow-600/60 rounded-xl shadow-2xl shadow-black/70 overflow-hidden pointer-events-auto"
      onMouseEnter={(e) => e.stopPropagation()}
    >
      {/* Header: name + cost gem */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-yellow-900/40 to-gray-900/20 border-b border-yellow-600/30">
        <div className="w-9 h-9 rounded-full bg-blue-600 border-2 border-blue-400 flex items-center justify-center shadow-md flex-shrink-0">
          <span className="text-white font-bold text-base">{manaValue}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-bold text-white text-base truncate">{card.name}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide">
            {cardTypeLabel}
            {card.subtypes.length > 0 && <> · {card.subtypes.join(' ')}</>}
          </div>
        </div>
      </div>

      {/* Art */}
      <div className="px-3 pt-3">
        <div className="w-full h-[140px] rounded border border-yellow-700/40 bg-gradient-to-br from-gray-700 to-gray-900 overflow-hidden flex items-center justify-center">
          {!artFailed && artPaths.length > 0 ? (
            <img
              src={artPaths[artIndex]}
              alt={card.name}
              className="w-full h-full object-cover"
              onError={() => {
                if (artIndex < artPaths.length - 1) {
                  setArtIndex((i) => i + 1);
                } else {
                  setArtFailed(true);
                }
              }}
            />
          ) : (
            <span className="text-gray-500 text-xs italic">No art</span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="p-3 space-y-2 text-sm">
        {/* Affinity badges */}
        {affinity && (affinity.azure > 0 || affinity.ember > 0 || affinity.verdant > 0) && (
          <div className="flex gap-1">
            {affinity.azure > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-cyan-900/70 text-cyan-200 text-[10px] font-bold">
                Azure {affinity.azure}
              </span>
            )}
            {affinity.ember > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-orange-900/70 text-orange-200 text-[10px] font-bold">
                Ember {affinity.ember}
              </span>
            )}
            {affinity.verdant > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-emerald-900/70 text-emerald-200 text-[10px] font-bold">
                Verdant {affinity.verdant}
              </span>
            )}
          </div>
        )}

        {/* Keywords */}
        {card.keywords && card.keywords.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {card.keywords.map((kw, i) => (
              <span
                key={i}
                className="px-1.5 py-0.5 rounded bg-purple-900/70 text-purple-200 text-[10px] font-bold uppercase"
              >
                {kw}
              </span>
            ))}
          </div>
        )}

        {/* Full card text (NO TRUNCATION) */}
        <div className="px-2 py-2 rounded bg-gray-800/60 text-gray-200 text-xs leading-relaxed border border-gray-700 min-h-[3rem] whitespace-pre-line">
          {displayText || <span className="italic opacity-50">No ability text</span>}
        </div>

        {/* Stats for minions / weapons */}
        {(isMinion || isWeapon) && (
          <div className="flex items-center justify-between gap-3 pt-1">
            <div className="flex items-center gap-2 text-xs">
              <div className="w-8 h-8 rounded-full bg-yellow-600 border-2 border-yellow-400 flex items-center justify-center">
                <span className="text-white font-bold text-sm">{card.power ?? 0}</span>
              </div>
              <span className="text-gray-400 text-[10px] uppercase">Atk</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-400 text-[10px] uppercase">
                {isWeapon ? 'Dur' : 'HP'}
              </span>
              <div
                className={`w-8 h-8 rounded-full border-2 flex items-center justify-center ${
                  isDamaged ? 'bg-red-700 border-red-400' : 'bg-red-600 border-red-400'
                }`}
              >
                <span
                  className={`font-bold text-sm ${isDamaged ? 'text-yellow-300' : 'text-white'}`}
                >
                  {isMinion ? currentHealth : card.toughness ?? 0}
                  {isMinion && isDamaged && (
                    <span className="text-[9px] text-gray-300">/{maxHealth}</span>
                  )}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Battlefield state badges (minion only) */}
        {isMinion && (
          <div className="flex flex-wrap gap-1 text-[10px]">
            {card.divine_shield && (
              <span className="px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-300 font-bold border border-yellow-500/40">
                Divine Shield
              </span>
            )}
            {card.stealth && (
              <span className="px-1.5 py-0.5 rounded bg-purple-600/30 text-purple-300 font-bold border border-purple-500/40">
                Stealth
              </span>
            )}
            {card.frozen && (
              <span className="px-1.5 py-0.5 rounded bg-blue-600/30 text-blue-300 font-bold border border-blue-500/40">
                Frozen
              </span>
            )}
            {card.summoning_sickness && (
              <span className="px-1.5 py-0.5 rounded bg-gray-600/30 text-gray-300 font-bold border border-gray-500/40">
                Exhausted
              </span>
            )}
          </div>
        )}

        {/* Pin control */}
        {isPinned && (
          <button
            type="button"
            onClick={unpin}
            className="w-full mt-1 px-2 py-1 rounded bg-yellow-700 hover:bg-yellow-600 text-white text-[11px] font-bold uppercase tracking-wide shadow"
          >
            📌 Pinned · Click to dismiss
          </button>
        )}
      </div>
    </div>
  );
}
