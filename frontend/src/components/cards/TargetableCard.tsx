/**
 * TargetableCard Component
 *
 * A card on the battlefield that can be a drop target for spells.
 * Used for targeted spells like removal, auras, etc.
 */

import clsx from 'clsx';
import { Card } from './Card';
import { useCardZone } from '../../hooks/useCardZone';
import ZoneHighlight from './ZoneHighlight';
import { useCardPreviewBindings } from '../../hooks/useCardPreview';
import type { CardData } from '../../types';

const MTG_ENGINE_ID = 'mtg';
const MTG_CARD_ZONE = (id: string) => `mtg-card-${id}`;

interface TargetableCardProps {
  card: CardData;
  isSelected?: boolean;
  isTargetable?: boolean;
  isHighlighted?: boolean;
  isAttacking?: boolean;
  isBlocking?: boolean;
  onClick?: () => void;
  /** Called when a hand-card source is dropped on this permanent (cast-time
   *  target). GameBoard looks up the action via gameState.legal_actions
   *  from the source card id. */
  onDrop?: (sourceCardId: string, target: CardData) => void;
  size?: 'small' | 'medium' | 'large';
}

export function TargetableCard({
  card,
  isSelected = false,
  isTargetable = false,
  isHighlighted = false,
  isAttacking = false,
  isBlocking = false,
  onClick,
  onDrop,
  size = 'small',
}: TargetableCardProps) {
  // Migrated to shared card-zone primitive. Each permanent on the
  // battlefield registers as a drop target with its own zoneId. When a
  // hand-card's validZones includes this card's zoneId (computed by
  // GameBoard.getValidDropZones for targeted spells), the zone glows
  // arcane violet via <ZoneHighlight>. GameBoard.handleCardDrop receives
  // the source card id; it looks up the action from legal_actions.
  const zone = useCardZone({
    zoneId: MTG_CARD_ZONE(card.id),
    engineId: MTG_ENGINE_ID,
    onPlay: (handCardId) => {
      onDrop?.(handCardId, card);
    },
  });
  const isValidDropTarget = zone.isValid;
  const isActiveTarget = zone.isHovered;
  const isOver = zone.isHovered;

  // Preview (hover + pin) — disabled while being targeted by a drag so drop
  // interactions aren't disturbed.
  const previewProps = useCardPreviewBindings(card, { disabled: isValidDropTarget });

  return (
    <div
      {...previewProps}
      className={clsx(
        'relative transition-all duration-300',
        {
          'ring-4 ring-cyan-400 ring-opacity-80 rounded-xl scale-105 animate-pulse': isValidDropTarget && !isOver,
          'ring-4 ring-emerald-400 rounded-xl scale-110 shadow-lg shadow-emerald-500/30': isActiveTarget || isOver,
        }
      )}
      onClick={zone.onClick}
      onDragOver={zone.onDragOver}
      onDragLeave={zone.onDragLeave}
      onDrop={zone.onDrop}
    >
      <ZoneHighlight
        isValid={zone.isValid}
        isHovered={zone.isHovered}
        hasActiveCard={zone.hasActiveCard}
        activeAccent={zone.activeAccent}
      />
      <Card
        card={card}
        size={size}
        isSelected={isSelected || isAttacking || isBlocking}
        isTargetable={isTargetable || isValidDropTarget}
        isHighlighted={isHighlighted}
        onClick={onClick}
      />

      {/* Attack indicator */}
      {isAttacking && (
        <div className="absolute -top-1 -right-1 inline-flex items-center gap-1 bg-gradient-to-br from-red-500 to-red-700 text-white text-[10px] px-2 py-0.5 rounded-full font-bold shadow-lg border border-red-400 z-10">
          ATK
        </div>
      )}

      {/* Block indicator */}
      {isBlocking && (
        <div className="absolute -top-1 -right-1 inline-flex items-center gap-1 bg-gradient-to-br from-blue-500 to-blue-700 text-white text-[10px] px-2 py-0.5 rounded-full font-bold shadow-lg border border-blue-400 z-10">
          BLK
        </div>
      )}

      {/* Valid drop target indicator */}
      {isValidDropTarget && !isOver && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none rounded-xl bg-cyan-500/10">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-cyan-600 text-white px-2 py-0.5 rounded text-[10px] font-bold shadow-lg whitespace-nowrap">
            Valid Target
          </div>
        </div>
      )}

      {/* Active hover drop indicator */}
      {isOver && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none rounded-xl bg-emerald-500/25">
          <div className="bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-sm font-bold shadow-xl border border-emerald-400">
            Release to Target
          </div>
        </div>
      )}
    </div>
  );
}

export default TargetableCard;
