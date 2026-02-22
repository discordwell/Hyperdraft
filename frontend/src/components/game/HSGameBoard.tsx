/**
 * HSGameBoard - Main Hearthstone-style game board layout.
 *
 * Layout (top to bottom):
 * - Opponent hero portrait + stats
 * - Opponent hand (face-down card backs)
 * - Opponent battlefield (minions)
 * - Center divider (turn indicator, mana)
 * - Player battlefield (minions)
 * - Player hand (face-up cards)
 * - Player hero portrait + hero power + end turn
 */

import { useState, useCallback, useMemo } from 'react';
import { HSHeroPortrait } from './HSHeroPortrait';
import { HSMinionCard } from './HSMinionCard';
import { HSHandCard } from './HSHandCard';
import type { GameState, CardData } from '../../types';

interface HSGameBoardProps {
  gameState: GameState;
  playerId: string;
  isMyTurn: boolean;
  canPlayCard: (card: CardData) => boolean;
  canAttuneCard: (card: CardData) => boolean;
  canAttack: (card: CardData) => boolean;
  canUseHeroPower: boolean;
  getAttackableTargets: (attackerId: string) => string[];
  onPlayCard: (cardId: string) => void;
  onAttuneCard: (cardId: string) => void;
  onAttack: (attackerId: string, targetId: string) => void;
  onHeroPower: () => void;
  onEndTurn: () => void;
}

type InteractionMode = 'none' | 'select_attacker' | 'select_target';

export function HSGameBoard({
  gameState,
  playerId,
  isMyTurn,
  canPlayCard,
  canAttuneCard,
  canAttack,
  canUseHeroPower,
  getAttackableTargets,
  onPlayCard,
  onAttuneCard,
  onAttack,
  onHeroPower,
  onEndTurn,
}: HSGameBoardProps) {
  const [mode, setMode] = useState<InteractionMode>('none');
  const [selectedAttackerId, setSelectedAttackerId] = useState<string | null>(null);
  const [validTargets, setValidTargets] = useState<string[]>([]);

  const opponentId = useMemo(() =>
    Object.keys(gameState.players).find(id => id !== playerId) || null,
    [gameState.players, playerId]
  );

  const myPlayer = gameState.players[playerId];
  const opponentPlayer = opponentId ? gameState.players[opponentId] : null;
  const isFrierenrift = gameState.variant === 'frierenrift';
  const variantResources = myPlayer?.variant_resources || {};

  const myMinions = useMemo(() =>
    gameState.battlefield.filter(c => c.controller === playerId),
    [gameState.battlefield, playerId]
  );

  const opponentMinions = useMemo(() =>
    gameState.battlefield.filter(c => c.controller !== playerId),
    [gameState.battlefield, playerId]
  );

  // Handle clicking own minion
  const handleMyMinionClick = useCallback((card: CardData) => {
    if (!isMyTurn) return;

    if (mode === 'select_attacker' || mode === 'none') {
      // Select this minion as attacker
      if (canAttack(card)) {
        const targets = getAttackableTargets(card.id);
        if (targets.length > 0) {
          setMode('select_target');
          setSelectedAttackerId(card.id);
          setValidTargets(targets);
        }
      }
    }
  }, [isMyTurn, mode, canAttack, getAttackableTargets]);

  // Handle clicking enemy minion or hero (attack target)
  const handleTargetClick = useCallback((targetId: string) => {
    if (mode === 'select_target' && selectedAttackerId && validTargets.includes(targetId)) {
      onAttack(selectedAttackerId, targetId);
      setMode('none');
      setSelectedAttackerId(null);
      setValidTargets([]);
    }
  }, [mode, selectedAttackerId, validTargets, onAttack]);

  // Cancel attack selection
  const handleCancel = useCallback(() => {
    setMode('none');
    setSelectedAttackerId(null);
    setValidTargets([]);
  }, []);

  // Handle card play from hand
  const handleHandCardClick = useCallback((card: CardData) => {
    if (!isMyTurn || !canPlayCard(card)) return;
    // Cancel any attack selection
    handleCancel();
    onPlayCard(card.id);
  }, [isMyTurn, canPlayCard, handleCancel, onPlayCard]);

  const handleAttuneClick = useCallback((card: CardData) => {
    if (!isMyTurn || !canAttuneCard(card)) return;
    handleCancel();
    onAttuneCard(card.id);
  }, [isMyTurn, canAttuneCard, handleCancel, onAttuneCard]);

  if (!myPlayer || !opponentPlayer) return null;

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-gray-900 via-gray-800 to-gray-900 select-none" onClick={mode === 'select_target' ? handleCancel : undefined}>
      {/* Opponent section */}
      <div className="px-4 py-2">
        <HSHeroPortrait
          player={opponentPlayer}
          isOpponent={true}
          isMyTurn={isMyTurn}
          canUseHeroPower={false}
          isValidTarget={mode === 'select_target' && opponentPlayer.hero_id != null && validTargets.includes(opponentPlayer.hero_id!)}
          onHeroClick={() => opponentPlayer.hero_id && handleTargetClick(opponentPlayer.hero_id)}
        />
      </div>

      {/* Opponent hand (face-down) */}
      <div className="flex justify-center gap-1 px-4 py-1">
        {Array.from({ length: opponentPlayer.hand_size }).map((_, i) => (
          <div key={i} className="w-8 h-11 rounded bg-gradient-to-b from-blue-800 to-blue-900 border border-blue-600" />
        ))}
      </div>

      {/* Opponent battlefield */}
      <div className="flex-1 flex items-center justify-center gap-2 px-4 py-2 min-h-[120px]">
        {opponentMinions.length === 0 ? (
          <div className="text-gray-600 text-sm">No minions</div>
        ) : (
          opponentMinions.map(card => (
            <HSMinionCard
              key={card.id}
              card={card}
              canAttack={false}
              isSelected={false}
              isValidTarget={mode === 'select_target' && validTargets.includes(card.id)}
              variant={gameState.variant}
              onClick={() => handleTargetClick(card.id)}
            />
          ))
        )}
      </div>

      {/* Center divider */}
      <div className="flex items-center justify-center gap-4 px-4 py-2 border-y border-gray-700 bg-gray-800/50">
        {/* Turn indicator */}
        <div className={`text-sm font-bold ${isMyTurn ? 'text-green-400' : 'text-gray-500'}`}>
          {isMyTurn ? 'Your Turn' : "Opponent's Turn"}
        </div>

        {/* Mana display */}
        <div className="flex items-center gap-1">
          {Array.from({ length: myPlayer.mana_crystals || 0 }).map((_, i) => (
            <div
              key={i}
              className={`w-4 h-4 rounded-full border ${
                i < (myPlayer.mana_crystals_available || 0)
                  ? 'bg-blue-500 border-blue-300'
                  : 'bg-gray-700 border-gray-600'
              }`}
            />
          ))}
          <span className="text-blue-300 text-sm font-bold ml-1">
            {myPlayer.mana_crystals_available}/{myPlayer.mana_crystals}
          </span>
        </div>

        {isFrierenrift && (
          <div className="flex items-center gap-2">
            <div className="text-[11px] font-semibold text-cyan-300">
              Azure {variantResources.azure || 0}
            </div>
            <div className="text-[11px] font-semibold text-orange-300">
              Ember {variantResources.ember || 0}
            </div>
            <div className="text-[11px] font-semibold text-emerald-300">
              Verdant {variantResources.verdant || 0}
            </div>
            <div className="text-[11px] font-semibold text-yellow-300">
              Attune {variantResources.attunes_left || 0}
            </div>
          </div>
        )}

        {/* Turn number */}
        <div className="text-gray-500 text-xs">
          Turn {gameState.turn_number}
        </div>

        {/* End Turn button */}
        <button
          onClick={(e) => { e.stopPropagation(); onEndTurn(); }}
          disabled={!isMyTurn}
          className={`
            px-4 py-1.5 rounded-lg font-bold text-sm transition-all
            ${isMyTurn
              ? 'bg-yellow-600 text-white hover:bg-yellow-500 shadow-lg'
              : 'bg-gray-700 text-gray-500 cursor-not-allowed'
            }
          `}
        >
          End Turn
        </button>
      </div>

      {/* Player battlefield */}
      <div className="flex-1 flex items-center justify-center gap-2 px-4 py-2 min-h-[120px]">
        {myMinions.length === 0 ? (
          <div className="text-gray-600 text-sm">No minions</div>
        ) : (
          myMinions.map(card => (
            <HSMinionCard
              key={card.id}
              card={card}
              canAttack={isMyTurn && canAttack(card)}
              isSelected={selectedAttackerId === card.id}
              isValidTarget={false}
              variant={gameState.variant}
              onClick={(e?: any) => { e?.stopPropagation?.(); handleMyMinionClick(card); }}
            />
          ))
        )}
      </div>

      {/* Player hand */}
      <div className="flex justify-center gap-2 px-4 py-2 overflow-x-auto">
        {gameState.hand.map(card => (
          <HSHandCard
            key={card.id}
            card={card}
            isPlayable={isMyTurn && canPlayCard(card)}
            variant={gameState.variant}
            showAttune={isFrierenrift}
            canAttune={isMyTurn && canAttuneCard(card)}
            onAttune={() => handleAttuneClick(card)}
            onClick={() => handleHandCardClick(card)}
          />
        ))}
        {gameState.hand.length === 0 && (
          <div className="text-gray-600 text-sm py-4">No cards in hand</div>
        )}
      </div>

      {/* Player hero section */}
      <div className="px-4 py-2 border-t border-gray-700">
        <HSHeroPortrait
          player={myPlayer}
          isOpponent={false}
          isMyTurn={isMyTurn}
          canUseHeroPower={canUseHeroPower}
          isValidTarget={false}
          onHeroPowerClick={onHeroPower}
        />
      </div>

      {/* Attack mode indicator */}
      {mode === 'select_target' && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-red-900/90 text-red-200 px-4 py-2 rounded-lg text-sm font-bold shadow-lg z-50">
          Select a target to attack (click empty space to cancel)
        </div>
      )}

      {/* Game Over overlay */}
      {gameState.is_game_over && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-600 rounded-xl p-8 text-center">
            <h2 className="text-3xl font-bold mb-4 text-white">
              {gameState.winner === playerId ? 'Victory!' : 'Defeat'}
            </h2>
            <p className="text-gray-400 mb-4">
              {gameState.winner === playerId
                ? 'You have defeated your opponent!'
                : 'Your hero has been destroyed.'}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
