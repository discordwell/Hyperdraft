/**
 * GameBoard Component
 *
 * Main game board layout combining all game zones.
 */

import { useMemo } from 'react';
import { PlayerInfo } from './PlayerInfo';
import { PhaseIndicator } from './PhaseIndicator';
import { Battlefield } from './Battlefield';
import { HandView } from './HandView';
import { StackView } from './StackView';
import type { GameState, CardData } from '../../types';

interface GameBoardProps {
  gameState: GameState;
  playerId: string;
  selectedCardId?: string | null;
  validTargets?: string[];
  selectedAttackers?: string[];
  selectedBlockers?: Map<string, string>;
  onCardClick?: (card: CardData, zone: 'hand' | 'battlefield') => void;
}

export function GameBoard({
  gameState,
  playerId,
  selectedCardId,
  validTargets = [],
  selectedAttackers = [],
  selectedBlockers = new Map(),
  onCardClick,
}: GameBoardProps) {
  // Derive player info
  const player = gameState.players[playerId];
  const opponentId = useMemo(
    () => Object.keys(gameState.players).find((id) => id !== playerId) || '',
    [gameState.players, playerId]
  );
  const opponent = gameState.players[opponentId];

  // Split battlefield by controller
  const myBattlefield = useMemo(
    () => gameState.battlefield.filter((c) => c.controller === playerId),
    [gameState.battlefield, playerId]
  );
  const opponentBattlefield = useMemo(
    () => gameState.battlefield.filter((c) => c.controller === opponentId),
    [gameState.battlefield, opponentId]
  );

  // Get castable cards
  const castableCards = useMemo(
    () =>
      gameState.legal_actions
        .filter((a) => a.type === 'CAST_SPELL' && a.card_id)
        .map((a) => a.card_id!),
    [gameState.legal_actions]
  );

  const playableLands = useMemo(
    () =>
      gameState.legal_actions
        .filter((a) => a.type === 'PLAY_LAND' && a.card_id)
        .map((a) => a.card_id!),
    [gameState.legal_actions]
  );

  // Get attackers from combat state
  const combatAttackers = useMemo(
    () => gameState.combat?.attackers.map((a) => a.attacker_id) || [],
    [gameState.combat]
  );

  // Can act?
  const canAct = gameState.priority_player === playerId;

  return (
    <div className="flex flex-col h-full gap-3 p-4 bg-game-bg">
      {/* Top Row: Opponent Info */}
      <div className="flex items-start gap-4">
        <div className="flex-1">
          {opponent && (
            <PlayerInfo
              player={opponent}
              isActivePlayer={gameState.active_player === opponentId}
              hasPriority={gameState.priority_player === opponentId}
              isOpponent
            />
          )}
        </div>
        <PhaseIndicator
          turnNumber={gameState.turn_number}
          phase={gameState.phase}
          step={gameState.step}
          activePlayerName={
            gameState.active_player === playerId
              ? player?.name
              : opponent?.name
          }
        />
      </div>

      {/* Opponent's Battlefield */}
      <Battlefield
        permanents={opponentBattlefield}
        isOpponent
        selectedCardId={selectedCardId}
        validTargets={validTargets}
        combatAttackers={combatAttackers}
        onCardClick={(card) => onCardClick?.(card, 'battlefield')}
      />

      {/* Middle Row: Stack */}
      <div className="flex justify-center">
        <div className="w-80">
          <StackView items={gameState.stack} playerId={playerId} />
        </div>
      </div>

      {/* My Battlefield */}
      <Battlefield
        permanents={myBattlefield}
        selectedCardId={selectedCardId}
        validTargets={validTargets}
        selectedAttackers={selectedAttackers}
        selectedBlockers={selectedBlockers}
        combatAttackers={combatAttackers}
        onCardClick={(card) => onCardClick?.(card, 'battlefield')}
      />

      {/* Bottom Row: My Info + Hand */}
      <div className="flex items-end gap-4">
        <div className="flex-shrink-0">
          {player && (
            <PlayerInfo
              player={player}
              isActivePlayer={gameState.active_player === playerId}
              hasPriority={canAct}
            />
          )}
        </div>
        <div className="flex-1">
          <HandView
            cards={gameState.hand}
            selectedCardId={selectedCardId}
            castableCards={castableCards}
            playableLands={playableLands}
            onCardClick={(card) => onCardClick?.(card, 'hand')}
            disabled={!canAct}
          />
        </div>
      </div>

      {/* Game Over Overlay */}
      {gameState.is_game_over && (
        <div className="absolute inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="text-center">
            <h2 className="text-4xl font-bold text-white mb-4">
              {gameState.winner === playerId ? 'Victory!' : 'Defeat'}
            </h2>
            <p className="text-gray-300 text-lg">
              {gameState.winner === playerId
                ? 'You have won the game!'
                : 'Your opponent has won the game.'}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default GameBoard;
