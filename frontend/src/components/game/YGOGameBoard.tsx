/**
 * YGOGameBoard Component
 *
 * Renders the Yu-Gi-Oh! duel field:
 * - Opponent back row (spell/trap), monster row, field spell
 * - Center: phase indicator, LP display
 * - Player monster row, back row, field spell
 * - Hand
 * - Action bar
 */

import { useState, useCallback } from 'react';
import { YGOCard } from './YGOCard';
import type { CardData, PlayerData, GameState, GameLogEntry } from '../../types';

const PHASE_LABELS: Record<string, string> = {
  DRAW: 'Draw',
  STANDBY: 'Standby',
  MAIN1: 'Main 1',
  BATTLE_START: 'Battle',
  BATTLE_STEP: 'Battle',
  DAMAGE_STEP: 'Damage',
  DAMAGE_CALC: 'Damage',
  BATTLE_END: 'Battle End',
  MAIN2: 'Main 2',
  END: 'End',
};

interface YGOGameBoardProps {
  gameState: GameState;
  playerId: string;
  isMyTurn: boolean;
  myPlayer: PlayerData | null;
  opponentPlayer: PlayerData | null;
  myMonsterZones: (CardData | null)[];
  oppMonsterZones: (CardData | null)[];
  mySpellTrapZones: (CardData | null)[];
  oppSpellTrapZones: (CardData | null)[];
  myFieldSpell: CardData | null;
  oppFieldSpell: CardData | null;
  hand: CardData[];
  myGraveyard: CardData[];
  oppGraveyard: CardData[];
  ygoPhase: string;
  gameLog?: GameLogEntry[];
  // Actions
  onNormalSummon: (cardId: string) => void;
  onSetMonster: (cardId: string) => void;
  onFlipSummon: (cardId: string) => void;
  onChangePosition: (cardId: string) => void;
  onActivateCard: (cardId: string, targetId?: string) => void;
  onSetSpellTrap: (cardId: string) => void;
  onDeclareAttack: (attackerId: string, targetId: string) => void;
  onDirectAttack: (attackerId: string) => void;
  onEndPhase: () => void;
  onEndTurn: () => void;
}

export function YGOGameBoard({
  gameState,
  playerId,
  isMyTurn,
  myPlayer,
  opponentPlayer,
  myMonsterZones,
  oppMonsterZones,
  mySpellTrapZones,
  oppSpellTrapZones,
  myFieldSpell,
  oppFieldSpell,
  hand,
  myGraveyard,
  oppGraveyard,
  ygoPhase,
  onNormalSummon,
  onSetMonster,
  onFlipSummon,
  onChangePosition,
  onActivateCard,
  onSetSpellTrap,
  onDeclareAttack,
  onDirectAttack,
  onEndPhase,
  onEndTurn,
}: YGOGameBoardProps) {
  const [selectedHandCard, setSelectedHandCard] = useState<string | null>(null);
  const [selectedFieldCard, setSelectedFieldCard] = useState<string | null>(null);
  const [attackMode, setAttackMode] = useState<string | null>(null); // attacker ID
  const [showGraveyard, setShowGraveyard] = useState<'mine' | 'opp' | null>(null);

  const handleHandCardClick = useCallback((card: CardData) => {
    if (!isMyTurn) return;
    setSelectedHandCard(prev => prev === card.id ? null : card.id);
    setSelectedFieldCard(null);
    setAttackMode(null);
  }, [isMyTurn]);

  const handleFieldCardClick = useCallback((card: CardData, isMine: boolean) => {
    // If in attack mode, this is a target selection
    if (attackMode && !isMine && card.id) {
      onDeclareAttack(attackMode, card.id);
      setAttackMode(null);
      return;
    }

    if (!isMine || !isMyTurn) return;
    setSelectedFieldCard(prev => prev === card.id ? null : card.id);
    setSelectedHandCard(null);
    setAttackMode(null);
  }, [isMyTurn, attackMode, onDeclareAttack]);

  const handleDirectAttackClick = useCallback(() => {
    if (attackMode) {
      onDirectAttack(attackMode);
      setAttackMode(null);
    }
  }, [attackMode, onDirectAttack]);

  const selectedHandCardData = hand.find(c => c.id === selectedHandCard);
  const isMonster = selectedHandCardData?.types?.includes('YGO_MONSTER');
  const isSpell = selectedHandCardData?.types?.includes('YGO_SPELL');
  const isTrap = selectedHandCardData?.types?.includes('YGO_TRAP');

  const selectedFieldCardData = (() => {
    if (!selectedFieldCard) return null;
    for (const card of myMonsterZones) {
      if (card?.id === selectedFieldCard) return card;
    }
    for (const card of mySpellTrapZones) {
      if (card?.id === selectedFieldCard) return card;
    }
    return null;
  })();

  const isFieldMonster = selectedFieldCardData?.types?.includes('YGO_MONSTER');
  const isFaceDown = selectedFieldCardData?.face_down;
  const isDefPos = selectedFieldCardData?.ygo_position === 'face_up_def' || selectedFieldCardData?.ygo_position === 'face_down_def';

  // Render a zone row of 5 slots
  const renderZoneRow = (zones: (CardData | null)[], isMine: boolean, isMonsterZone: boolean) => (
    <div className="flex gap-1.5 justify-center">
      {Array.from({ length: 5 }).map((_, i) => {
        const card = zones[i] || null;
        return (
          <div
            key={i}
            className={`
              w-20 h-28 border border-dashed rounded-md flex items-center justify-center
              ${isMonsterZone ? 'border-amber-800/40' : 'border-teal-800/40'}
              ${!card ? 'bg-gray-900/30' : ''}
            `}
          >
            {card ? (
              <YGOCard
                card={card}
                size="md"
                onClick={() => handleFieldCardClick(card, isMine)}
                selected={(isMine && selectedFieldCard === card.id) || (attackMode !== null && !isMine)}
                isDefensePosition={card.ygo_position === 'face_up_def' || card.ygo_position === 'face_down_def'}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="h-screen flex flex-col bg-gray-950 overflow-hidden">
      {/* Opponent info bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-indigo-900/50">
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-300 font-medium">{opponentPlayer?.name || 'Opponent'}</span>
          <span className="text-lg font-bold text-red-400">LP {opponentPlayer?.lp ?? 8000}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>Hand: {opponentPlayer?.hand_size ?? 0}</span>
          <span>Deck: {opponentPlayer?.library_size ?? 0}</span>
          <button onClick={() => setShowGraveyard('opp')} className="text-gray-400 hover:text-white">
            GY: {oppGraveyard.length}
          </button>
        </div>
      </div>

      {/* Opponent Field */}
      <div className="flex-1 flex flex-col justify-center items-center gap-1.5 py-2">
        {/* Opponent back row (spell/trap) */}
        <div className="flex items-center gap-2">
          {oppFieldSpell ? (
            <YGOCard card={oppFieldSpell} size="sm" />
          ) : (
            <div className="w-14 h-20 border border-dashed border-green-800/30 rounded-md" />
          )}
          {renderZoneRow(oppSpellTrapZones, false, false)}
        </div>

        {/* Opponent monster row */}
        <div className="flex items-center gap-2">
          <div className="w-14" /> {/* spacer for field spell alignment */}
          {renderZoneRow(oppMonsterZones, false, true)}
        </div>

        {/* Center: Phase indicator + direct attack target */}
        <div className="flex items-center gap-4 py-1">
          <div className="flex gap-1">
            {['DRAW', 'STANDBY', 'MAIN1', 'BATTLE_STEP', 'MAIN2', 'END'].map(phase => (
              <div
                key={phase}
                className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${
                  ygoPhase === phase || (phase === 'BATTLE_STEP' && ['BATTLE_START', 'BATTLE_STEP', 'DAMAGE_STEP', 'DAMAGE_CALC', 'BATTLE_END'].includes(ygoPhase))
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-500'
                }`}
              >
                {PHASE_LABELS[phase] || phase}
              </div>
            ))}
          </div>
          {attackMode && (
            <button
              onClick={handleDirectAttackClick}
              className="px-3 py-1 bg-red-700 hover:bg-red-600 text-white text-xs font-bold rounded animate-pulse"
            >
              Direct Attack
            </button>
          )}
        </div>

        {/* My monster row */}
        <div className="flex items-center gap-2">
          <div className="w-14" />
          {renderZoneRow(myMonsterZones, true, true)}
        </div>

        {/* My back row (spell/trap) */}
        <div className="flex items-center gap-2">
          {myFieldSpell ? (
            <YGOCard card={myFieldSpell} size="sm" onClick={() => {}} />
          ) : (
            <div className="w-14 h-20 border border-dashed border-green-800/30 rounded-md" />
          )}
          {renderZoneRow(mySpellTrapZones, true, false)}
        </div>
      </div>

      {/* My info bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-t border-indigo-900/50">
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-300 font-medium">{myPlayer?.name || 'You'}</span>
          <span className="text-lg font-bold text-green-400">LP {myPlayer?.lp ?? 8000}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>Deck: {myPlayer?.library_size ?? 0}</span>
          <button onClick={() => setShowGraveyard('mine')} className="text-gray-400 hover:text-white">
            GY: {myGraveyard.length}
          </button>
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${isMyTurn ? 'bg-yellow-600 text-white' : 'bg-gray-700 text-gray-400'}`}>
            {isMyTurn ? 'YOUR TURN' : 'WAITING'}
          </span>
        </div>
      </div>

      {/* Hand */}
      <div className="bg-gray-900/80 border-t border-indigo-900/50 px-4 py-2">
        <div className="flex gap-1.5 justify-center overflow-x-auto">
          {hand.map(card => (
            <YGOCard
              key={card.id}
              card={card}
              size="md"
              onClick={() => handleHandCardClick(card)}
              selected={selectedHandCard === card.id}
            />
          ))}
          {hand.length === 0 && (
            <div className="text-gray-600 text-sm py-6">No cards in hand</div>
          )}
        </div>
      </div>

      {/* Action bar */}
      {isMyTurn && (
        <div className="bg-gray-950 border-t border-indigo-900/50 px-4 py-2 flex gap-2 justify-center flex-wrap">
          {/* Hand card actions */}
          {selectedHandCard && isMonster && (
            <>
              <button
                onClick={() => { onNormalSummon(selectedHandCard); setSelectedHandCard(null); }}
                className="px-3 py-1.5 bg-amber-700 hover:bg-amber-600 text-white text-xs font-bold rounded"
              >
                Normal Summon
              </button>
              <button
                onClick={() => { onSetMonster(selectedHandCard); setSelectedHandCard(null); }}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-bold rounded"
              >
                Set
              </button>
            </>
          )}
          {selectedHandCard && isSpell && (
            <>
              <button
                onClick={() => { onActivateCard(selectedHandCard); setSelectedHandCard(null); }}
                className="px-3 py-1.5 bg-teal-700 hover:bg-teal-600 text-white text-xs font-bold rounded"
              >
                Activate
              </button>
              <button
                onClick={() => { onSetSpellTrap(selectedHandCard); setSelectedHandCard(null); }}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-bold rounded"
              >
                Set
              </button>
            </>
          )}
          {selectedHandCard && isTrap && (
            <button
              onClick={() => { onSetSpellTrap(selectedHandCard); setSelectedHandCard(null); }}
              className="px-3 py-1.5 bg-pink-700 hover:bg-pink-600 text-white text-xs font-bold rounded"
            >
              Set Trap
            </button>
          )}

          {/* Field card actions */}
          {selectedFieldCard && isFieldMonster && !isFaceDown && !isDefPos && (
            <button
              onClick={() => { setAttackMode(selectedFieldCard); setSelectedFieldCard(null); }}
              className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white text-xs font-bold rounded"
            >
              Attack
            </button>
          )}
          {selectedFieldCard && isFieldMonster && isFaceDown && (
            <button
              onClick={() => { onFlipSummon(selectedFieldCard); setSelectedFieldCard(null); }}
              className="px-3 py-1.5 bg-amber-700 hover:bg-amber-600 text-white text-xs font-bold rounded"
            >
              Flip Summon
            </button>
          )}
          {selectedFieldCard && isFieldMonster && !isFaceDown && (
            <button
              onClick={() => { onChangePosition(selectedFieldCard); setSelectedFieldCard(null); }}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-bold rounded"
            >
              {isDefPos ? 'To ATK' : 'To DEF'}
            </button>
          )}

          {/* Attack mode cancel */}
          {attackMode && (
            <button
              onClick={() => setAttackMode(null)}
              className="px-3 py-1.5 bg-gray-600 hover:bg-gray-500 text-white text-xs font-bold rounded"
            >
              Cancel Attack
            </button>
          )}

          {/* Phase controls */}
          <div className="flex gap-1.5 ml-auto">
            <button
              onClick={() => { onEndPhase(); setSelectedHandCard(null); setSelectedFieldCard(null); setAttackMode(null); }}
              className="px-3 py-1.5 bg-indigo-800 hover:bg-indigo-700 text-white text-xs font-bold rounded"
            >
              End Phase
            </button>
            <button
              onClick={() => { onEndTurn(); setSelectedHandCard(null); setSelectedFieldCard(null); setAttackMode(null); }}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded"
            >
              End Turn
            </button>
          </div>
        </div>
      )}

      {/* Game over overlay */}
      {gameState.is_game_over && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-gray-900 border-2 border-yellow-500 rounded-xl p-8 text-center">
            <h2 className="text-3xl font-bold text-yellow-400 mb-2">
              {gameState.winner === playerId ? 'VICTORY!' : 'DEFEAT'}
            </h2>
            <p className="text-gray-400 mb-4">
              {gameState.winner === playerId
                ? 'You won the duel!'
                : 'You lost the duel.'}
            </p>
            <button
              onClick={() => window.location.href = '/'}
              className="px-6 py-2 bg-yellow-600 hover:bg-yellow-500 text-white font-bold rounded-lg"
            >
              Return to Menu
            </button>
          </div>
        </div>
      )}

      {/* Graveyard modal */}
      {showGraveyard && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-40" onClick={() => setShowGraveyard(null)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-lg max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-white mb-3">
              {showGraveyard === 'mine' ? 'Your Graveyard' : "Opponent's Graveyard"}
            </h3>
            <div className="flex flex-wrap gap-2">
              {(showGraveyard === 'mine' ? myGraveyard : oppGraveyard).map((card, i) => (
                <YGOCard key={`${card.id}-${i}`} card={card} size="md" />
              ))}
              {(showGraveyard === 'mine' ? myGraveyard : oppGraveyard).length === 0 && (
                <p className="text-gray-500 text-sm">No cards in graveyard</p>
              )}
            </div>
            <button
              onClick={() => setShowGraveyard(null)}
              className="mt-4 px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
