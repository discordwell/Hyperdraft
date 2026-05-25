/**
 * TargetablePlayer Component
 *
 * Wrapper around PlayerInfo that can receive spell drops for player-targeting spells.
 * Used for burn spells, life gain targeting, etc.
 */

import { useCallback } from 'react';
import clsx from 'clsx';
import { PlayerInfo } from './PlayerInfo';
import { useCardZone } from '../../hooks/useCardZone';
import ZoneHighlight from '../cards/ZoneHighlight';
import type { PlayerData } from '../../types';

const MTG_ENGINE_ID = 'mtg';
const MTG_PLAYER_ZONE = (id: string) => `mtg-player-${id}`;

interface TargetablePlayerProps {
  player: PlayerData;
  playerId: string;
  isActivePlayer?: boolean;
  hasPriority?: boolean;
  isOpponent?: boolean;
  /** Called when a hand-card source is dropped on this player portrait
   *  (player-targeting spells: burn, life gain, etc.). GameBoard looks
   *  up the action via gameState.legal_actions from the source card id. */
  onDrop?: (sourceCardId: string, playerId: string) => void;
  // Phase 5b overlay-mode targeting: when set, render a glow ring and
  // wire a click handler so the player can be picked as a target.
  isTargetable?: boolean;
  onTargetClick?: (playerId: string) => void;
}

export function TargetablePlayer({
  player,
  playerId,
  isActivePlayer = false,
  hasPriority = false,
  isOpponent = false,
  onDrop,
  isTargetable = false,
  onTargetClick,
}: TargetablePlayerProps) {
  // Migrated to shared card-zone primitive. The player-portrait
  // registers as zoneId `mtg-player-<id>`. GameBoard.getValidDropZones
  // emits this id for spells that target players (Lightning Bolt to face,
  // Lava Spike, etc). GameBoard.handlePlayerDrop receives the source
  // card id and looks up the action from gameState.legal_actions.
  const zone = useCardZone({
    zoneId: MTG_PLAYER_ZONE(playerId),
    engineId: MTG_ENGINE_ID,
    onPlay: (handCardId) => {
      onDrop?.(handCardId, playerId);
    },
  });
  const isValidDropTarget = zone.isValid;
  const isActiveTarget = zone.isHovered;
  const isOver = zone.isHovered;

  // Click-to-target (overlay-mode pending choice). Drop interactions
  // still go through the drag-and-drop handlers above; this click
  // handler only fires when the player is wired as a legal target.
  // Overlay-mode click and card-zone click are distinct: overlay-mode
  // uses isTargetable + onTargetClick, card-zone uses zone.onClick
  // (active only when a primed card lists this zone valid).
  const handleClick = useCallback(() => {
    // Overlay-mode targeting first (existing pending_choice flow).
    if (isTargetable && onTargetClick) {
      onTargetClick(playerId);
      return;
    }
    // Card-zone click-prime path next.
    zone.onClick();
  }, [isTargetable, onTargetClick, playerId, zone]);

  return (
    <div
      data-testid={`targetable-player-${playerId}`}
      className={clsx(
        'relative transition-all duration-200 rounded-lg',
        {
          'ring-4 ring-cyan-400 ring-opacity-80 scale-105': isValidDropTarget && !isOver,
          'ring-4 ring-emerald-500 scale-110 bg-emerald-900/20': isActiveTarget || isOver,
          // Overlay-mode targetable glow (distinct from drag drop-target hint).
          'ring-4 ring-amber-400 ring-opacity-80 cursor-pointer hover:scale-105':
            isTargetable && !isValidDropTarget && !isActiveTarget && !isOver,
        }
      )}
      onClick={handleClick}
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
      <PlayerInfo
        player={player}
        isActivePlayer={isActivePlayer}
        hasPriority={hasPriority}
        isOpponent={isOpponent}
      />

      {/* Drop target indicator */}
      {isValidDropTarget && (
        <div className={clsx(
          'absolute inset-0 flex items-center justify-center pointer-events-none rounded-lg transition-opacity duration-200',
          isOver ? 'bg-emerald-500/30' : 'bg-cyan-500/10'
        )}>
          {isOver && (
            <div className="bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-sm font-bold shadow-lg">
              Target {isOpponent ? 'Opponent' : 'You'}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TargetablePlayer;
