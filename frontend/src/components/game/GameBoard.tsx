/**
 * GameBoard Component
 *
 * Main game board layout combining all game zones.
 * Manages drag and drop interactions between hand and battlefield.
 */

import { useMemo, useCallback } from 'react';
import { TargetablePlayer } from './TargetablePlayer';
import { PhaseIndicator } from './PhaseIndicator';
import { Battlefield } from './Battlefield';
import { HandView } from './HandView';
import { StackView } from './StackView';
import { MultiTargetModal } from '../actions/MultiTargetModal';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';
import type { GameState, CardData, LegalActionData } from '../../types';

interface GameBoardProps {
  gameState: GameState;
  playerId: string;
  selectedCardId?: string | null;
  validTargets?: string[];
  selectedAttackers?: string[];
  selectedBlockers?: Map<string, string>;
  onCardClick?: (card: CardData, zone: 'hand' | 'battlefield') => void;
  onPlayLand?: (cardId: string) => void;
  onCastSpell?: (cardId: string, targets?: string[]) => void;
  onCastMultiTargetSpell?: (cardId: string, targets: string[][]) => void;
}

export function GameBoard({
  gameState,
  playerId,
  selectedCardId,
  validTargets = [],
  selectedAttackers = [],
  selectedBlockers = new Map(),
  onCardClick,
  onPlayLand,
  onCastSpell,
  onCastMultiTargetSpell,
}: GameBoardProps) {
  const {
    multiTargetMode,
    multiTargetSpell,
    multiTargetCardId,
    firstTarget,
    secondTargetOptions,
    startMultiTargetMode,
    cancelMultiTarget,
  } = useDragDropStore();

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

  // Get the legal action for a card
  const getCardAction = useCallback((cardId: string): LegalActionData | undefined => {
    return gameState.legal_actions.find(
      (a) => (a.type === 'CAST_SPELL' || a.type === 'PLAY_LAND') && a.card_id === cardId
    );
  }, [gameState.legal_actions]);

  // Determine valid drop zones for a card being dragged
  const getValidDropZones = useCallback((card: CardData): string[] => {
    const zones: string[] = [];
    const action = getCardAction(card.id);

    if (!action) return zones;

    // Lands can be dropped on your battlefield
    if (action.type === 'PLAY_LAND') {
      zones.push('battlefield-self');
      return zones;
    }

    // Spells that require targets - each valid target is a drop zone
    if (action.type === 'CAST_SPELL') {
      if (action.requires_targets) {
        // Add all permanents as potential targets (server will validate)
        gameState.battlefield.forEach((perm) => {
          zones.push(`card-${perm.id}`);
        });
        // Add players as targets
        zones.push(`player-${playerId}`);
        zones.push(`player-${opponentId}`);
      } else {
        // Non-targeted spells can be dropped on your battlefield to cast
        zones.push('battlefield-self');
      }
    }

    return zones;
  }, [getCardAction, gameState.battlefield, playerId, opponentId]);

  // Handle dropping a land on the battlefield
  const handleBattlefieldDrop = useCallback((item: DragItem) => {
    if (!item.action || !item.card) return;

    if (item.action.type === 'PLAY_LAND') {
      onPlayLand?.(item.card.id);
    } else if (item.action.type === 'CAST_SPELL' && !item.action.requires_targets) {
      // Non-targeted spell
      onCastSpell?.(item.card.id);
    }
  }, [onPlayLand, onCastSpell]);

  // Check if a spell needs multiple targets based on card text
  const detectMultiTarget = useCallback((cardText: string): { needsSecond: boolean; secondTargetType: 'opponent_permanent' | 'any_permanent' | 'any_creature' | 'player' } => {
    const text = cardText.toLowerCase();

    // Auras that exile on ETB (like Sheltered by Ghosts)
    if ((text.includes('exile') && text.includes('enchanted')) ||
        (text.includes('when') && text.includes('enters') && text.includes('exile'))) {
      return { needsSecond: true, secondTargetType: 'opponent_permanent' };
    }

    // "Choose another target" patterns
    if (text.includes('choose another')) {
      return { needsSecond: true, secondTargetType: 'any_permanent' };
    }

    // Fight effects
    if (text.includes('target creature you control fights')) {
      return { needsSecond: true, secondTargetType: 'any_creature' };
    }

    return { needsSecond: false, secondTargetType: 'any_permanent' };
  }, []);

  // Handle dropping a spell on a target card
  const handleCardDrop = useCallback((item: DragItem, targetCard: CardData) => {
    if (!item.action || !item.card) return;

    if (item.action.type === 'CAST_SPELL' && item.action.requires_targets) {
      const { needsSecond, secondTargetType } = detectMultiTarget(item.card.text);

      if (needsSecond) {
        // Determine valid second targets based on type
        let secondTargets: string[] = [];

        switch (secondTargetType) {
          case 'opponent_permanent':
            secondTargets = gameState.battlefield
              .filter((p) => p.controller === opponentId && p.id !== targetCard.id)
              .map((p) => p.id);
            break;
          case 'any_permanent':
            secondTargets = gameState.battlefield
              .filter((p) => p.id !== targetCard.id)
              .map((p) => p.id);
            break;
          case 'any_creature':
            secondTargets = gameState.battlefield
              .filter((p) => p.types.includes('CREATURE') && p.id !== targetCard.id)
              .map((p) => p.id);
            break;
          case 'player':
            secondTargets = [playerId, opponentId];
            break;
        }

        if (secondTargets.length > 0) {
          startMultiTargetMode(item.action, item.card.id, targetCard.id, secondTargets);
          return;
        }
      }

      // Single target spell - cast immediately
      onCastSpell?.(item.card.id, [targetCard.id]);
    }
  }, [gameState.battlefield, playerId, opponentId, onCastSpell, startMultiTargetMode, detectMultiTarget]);

  // Handle dropping a spell on a player
  const handlePlayerDrop = useCallback((item: DragItem, targetPlayerId: string) => {
    if (!item.action || !item.card) return;

    if (item.action.type === 'CAST_SPELL' && item.action.requires_targets) {
      // Check if this spell might need a second target
      const { needsSecond, secondTargetType } = detectMultiTarget(item.card.text);

      if (needsSecond && secondTargetType === 'player') {
        // For spells that target two players
        const otherPlayer = targetPlayerId === playerId ? opponentId : playerId;
        startMultiTargetMode(item.action, item.card.id, targetPlayerId, [otherPlayer]);
        return;
      }

      // Single target spell targeting player - cast immediately
      onCastSpell?.(item.card.id, [targetPlayerId]);
    }
  }, [playerId, opponentId, onCastSpell, startMultiTargetMode, detectMultiTarget]);

  // Handle selecting the second target in multi-target mode
  const handleSecondTargetSelect = useCallback((targetId: string) => {
    if (!multiTargetCardId || !firstTarget) return;

    // Cast the spell with both targets
    onCastMultiTargetSpell?.(multiTargetCardId, [[firstTarget], [targetId]]);
  }, [multiTargetCardId, firstTarget, onCastMultiTargetSpell]);

  // Handle canceling multi-target selection
  const handleMultiTargetCancel = useCallback(() => {
    cancelMultiTarget();
  }, [cancelMultiTarget]);

  // Get cards for multi-target modal
  const multiTargetCards = useMemo(() => {
    return gameState.battlefield.filter((p) => secondTargetOptions.includes(p.id));
  }, [gameState.battlefield, secondTargetOptions]);

  // Get the first target card for display in modal
  const firstTargetCard = useMemo(() => {
    if (!firstTarget) return undefined;
    return gameState.battlefield.find((p) => p.id === firstTarget);
  }, [gameState.battlefield, firstTarget]);

  return (
    <div className="flex flex-col h-full gap-3 p-4 bg-game-bg">
      {/* Top Row: Opponent Info */}
      <div className="flex items-start gap-4">
        <div className="flex-1">
          {opponent && (
            <TargetablePlayer
              player={opponent}
              playerId={opponentId}
              isActivePlayer={gameState.active_player === opponentId}
              hasPriority={gameState.priority_player === opponentId}
              isOpponent
              onDrop={handlePlayerDrop}
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
        onCardDrop={handleCardDrop}
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
        onCardDrop={handleCardDrop}
        onBattlefieldDrop={handleBattlefieldDrop}
      />

      {/* Bottom Row: My Info + Hand */}
      <div className="flex items-end gap-4">
        <div className="flex-shrink-0">
          {player && (
            <TargetablePlayer
              player={player}
              playerId={playerId}
              isActivePlayer={gameState.active_player === playerId}
              hasPriority={canAct}
              onDrop={handlePlayerDrop}
            />
          )}
        </div>
        <div className="flex-1">
          <HandView
            cards={gameState.hand}
            selectedCardId={selectedCardId}
            castableCards={castableCards}
            playableLands={playableLands}
            legalActions={gameState.legal_actions}
            onCardClick={(card) => onCardClick?.(card, 'hand')}
            onGetValidDropZones={getValidDropZones}
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

      {/* Multi-Target Modal */}
      {multiTargetMode && (
        <MultiTargetModal
          availableTargets={multiTargetCards}
          firstTargetCard={firstTargetCard}
          targetPrompt={multiTargetSpell?.description || 'Select a permanent to target'}
          onSelect={handleSecondTargetSelect}
          onCancel={handleMultiTargetCancel}
        />
      )}
    </div>
  );
}

export default GameBoard;
