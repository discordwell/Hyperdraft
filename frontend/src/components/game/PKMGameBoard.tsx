/**
 * PKMGameBoard - Pokemon TCG game board layout.
 *
 * Layout (top to bottom):
 * - Opponent prizes + deck count
 * - Opponent bench (up to 5)
 * - Opponent active spot (1 Pokemon)
 * - Stadium card (shared)
 * - Player active spot (1 Pokemon)
 * - Player bench (up to 5)
 * - Player prizes + deck count
 * - Player hand
 * - Action bar
 */

import { useState, useCallback } from 'react';
import { PKMCard } from './PKMCard';
import type { CardData, PlayerData } from '../../types';

interface PKMGameBoardProps {
  gameState: any;
  playerId: string;
  isMyTurn: boolean;
  myPlayer: PlayerData | null;
  opponentPlayer: PlayerData | null;
  myActivePokemon: CardData | null;
  opponentActivePokemon: CardData | null;
  myBench: CardData[];
  opponentBench: CardData[];
  stadiumCard: CardData | null;
  hand: CardData[];
  canPlayCard: (card: CardData) => boolean;
  canAttachEnergy: (card: CardData) => boolean;
  onPlayCard: (cardId: string) => void;
  onAttachEnergy: (energyCardId: string, targetPokemonId: string) => void;
  onAttack: (attackIndex: number) => void;
  onRetreat: (benchPokemonId: string) => void;
  onEvolve: (evolutionCardId: string, targetPokemonId: string) => void;
  onUseAbility: (pokemonId: string) => void;
  onEndTurn: () => void;
}

type InteractionMode =
  | 'none'
  | 'select_energy_target'    // Picking a Pokemon to attach energy to
  | 'select_attack'           // Picking which attack to use
  | 'select_retreat_target'   // Picking bench Pokemon to swap in
  | 'select_evolution_target' // Picking which Pokemon to evolve
  ;

export function PKMGameBoard({
  gameState,
  playerId,
  isMyTurn,
  myPlayer,
  opponentPlayer,
  myActivePokemon,
  opponentActivePokemon,
  myBench,
  opponentBench,
  stadiumCard,
  hand,
  canPlayCard,
  canAttachEnergy,
  onPlayCard,
  onAttachEnergy,
  onAttack,
  onRetreat,
  onEvolve,
  onUseAbility,
  onEndTurn,
}: PKMGameBoardProps) {
  const [mode, setMode] = useState<InteractionMode>('none');
  const [selectedHandCardId, setSelectedHandCardId] = useState<string | null>(null);

  // Cancel current interaction
  const handleCancel = useCallback(() => {
    setMode('none');
    setSelectedHandCardId(null);
  }, []);

  // Handle clicking a card in hand
  const handleHandCardClick = useCallback((card: CardData) => {
    if (!isMyTurn) return;

    const types = card.types || [];

    // Energy card - select for attachment
    if (types.includes('ENERGY') && canAttachEnergy(card)) {
      setMode('select_energy_target');
      setSelectedHandCardId(card.id);
      // card selected via setSelectedHandCardId above
      return;
    }

    // Evolution card - select target
    if (types.includes('POKEMON') && (card.evolution_stage === 'Stage 1' || card.evolution_stage === 'Stage 2')) {
      setMode('select_evolution_target');
      setSelectedHandCardId(card.id);
      // card selected via setSelectedHandCardId above
      return;
    }

    // Basic Pokemon or Trainer - play directly
    if (canPlayCard(card)) {
      onPlayCard(card.id);
      handleCancel();
    }
  }, [isMyTurn, canPlayCard, canAttachEnergy, onPlayCard, handleCancel]);

  // Handle clicking a Pokemon on field (for energy attachment, evolution, ability)
  const handleFieldPokemonClick = useCallback((pokemonId: string, isOwn: boolean) => {
    if (!isMyTurn || !isOwn) return;

    if (mode === 'select_energy_target' && selectedHandCardId) {
      onAttachEnergy(selectedHandCardId, pokemonId);
      handleCancel();
      return;
    }

    if (mode === 'select_evolution_target' && selectedHandCardId) {
      onEvolve(selectedHandCardId, pokemonId);
      handleCancel();
      return;
    }

    if (mode === 'select_retreat_target') {
      onRetreat(pokemonId);
      handleCancel();
      return;
    }
  }, [isMyTurn, mode, selectedHandCardId, onAttachEnergy, onEvolve, onRetreat, handleCancel]);

  // Handle attack selection
  const handleAttackClick = useCallback((attackIndex: number) => {
    onAttack(attackIndex);
    handleCancel();
  }, [onAttack, handleCancel]);

  // Handle retreat button
  const handleRetreatClick = useCallback(() => {
    if (myBench.length === 0) return;
    if (myBench.length === 1) {
      onRetreat(myBench[0].id);
    } else {
      setMode('select_retreat_target');
    }
  }, [myBench, onRetreat]);

  // Handle ability use
  const handleAbilityClick = useCallback((pokemonId: string) => {
    onUseAbility(pokemonId);
  }, [onUseAbility]);

  if (!myPlayer || !opponentPlayer) return null;

  const myPrizes = myPlayer.prizes_remaining ?? 0;
  const oppPrizes = opponentPlayer.prizes_remaining ?? 0;

  return (
    <div
      className="h-full flex flex-col bg-gradient-to-b from-emerald-950 via-green-900 to-emerald-950 select-none"
      onClick={mode !== 'none' ? handleCancel : undefined}
    >
      {/* Opponent info bar */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-black/30">
        <div className="flex items-center gap-3">
          <span className="text-gray-300 text-sm font-bold">{opponentPlayer.name}</span>
          <span className="text-gray-500 text-xs">Deck: {opponentPlayer.library_size}</span>
          <span className="text-gray-500 text-xs">Hand: {opponentPlayer.hand_size}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-yellow-400 text-xs font-bold">Prizes: </span>
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className={`w-3 h-4 rounded-sm ${
                i < oppPrizes ? 'bg-yellow-500 border border-yellow-300' : 'bg-gray-700 border border-gray-600'
              }`}
            />
          ))}
        </div>
      </div>

      {/* Opponent hand (face-down) */}
      <div className="flex justify-center gap-1 px-4 py-1">
        {Array.from({ length: opponentPlayer.hand_size }).map((_, i) => (
          <div key={i} className="w-7 h-10 rounded bg-gradient-to-b from-red-800 to-red-900 border border-red-600" />
        ))}
      </div>

      {/* Opponent bench */}
      <div className="flex items-center justify-center gap-2 px-4 py-1 min-h-[48px]">
        {opponentBench.length === 0 ? (
          <div className="text-green-800 text-xs">Empty bench</div>
        ) : (
          opponentBench.map(card => (
            <PKMCard key={card.id} card={card} compact isOpponent />
          ))
        )}
      </div>

      {/* Opponent active spot */}
      <div className="flex items-center justify-center py-2 min-h-[160px]">
        {opponentActivePokemon ? (
          <PKMCard
            card={opponentActivePokemon}
            isActive
            isOpponent
          />
        ) : (
          <div className="w-32 h-44 rounded-lg border-2 border-dashed border-green-700 flex items-center justify-center">
            <span className="text-green-700 text-xs">No Active</span>
          </div>
        )}
      </div>

      {/* Stadium + center divider */}
      <div className="flex items-center justify-center gap-4 px-4 py-2 border-y border-green-800 bg-green-900/50">
        {stadiumCard ? (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-gray-400 uppercase">Stadium</span>
            <div className="bg-gray-700 rounded px-2 py-1 text-white text-[10px] font-bold">
              {stadiumCard.name}
            </div>
          </div>
        ) : (
          <div className="text-green-700 text-[10px]">No Stadium</div>
        )}

        <div className={`text-sm font-bold ${isMyTurn ? 'text-yellow-400' : 'text-gray-500'}`}>
          {isMyTurn ? 'Your Turn' : "Opponent's Turn"}
        </div>

        <div className="text-gray-500 text-xs">Turn {gameState.turn_number}</div>
      </div>

      {/* Player active spot */}
      <div className="flex items-center justify-center py-2 min-h-[160px]">
        {myActivePokemon ? (
          <div className="flex items-center gap-4" onClick={(e) => e.stopPropagation()}>
            <PKMCard
              card={myActivePokemon}
              isActive
              isSelected={mode === 'select_energy_target' || mode === 'select_evolution_target'}
              isValidTarget={mode === 'select_energy_target' || mode === 'select_evolution_target'}
              onClick={() => handleFieldPokemonClick(myActivePokemon.id, true)}
            />

            {/* Attack buttons */}
            {isMyTurn && myActivePokemon.attacks && mode === 'none' && (
              <div className="flex flex-col gap-1">
                {myActivePokemon.attacks.map((atk: any, i: number) => (
                  <button
                    key={i}
                    onClick={() => handleAttackClick(i)}
                    className="px-3 py-1.5 bg-red-700 text-white text-xs font-bold rounded hover:bg-red-600 transition-all whitespace-nowrap"
                  >
                    {atk.name} {atk.damage > 0 ? `(${atk.damage})` : ''}
                  </button>
                ))}
                {myActivePokemon.ability_name && (
                  <button
                    onClick={() => handleAbilityClick(myActivePokemon.id)}
                    className="px-3 py-1.5 bg-purple-700 text-white text-xs font-bold rounded hover:bg-purple-600 transition-all whitespace-nowrap"
                  >
                    {myActivePokemon.ability_name}
                  </button>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="w-32 h-44 rounded-lg border-2 border-dashed border-green-700 flex items-center justify-center">
            <span className="text-green-700 text-xs">No Active</span>
          </div>
        )}
      </div>

      {/* Player bench */}
      <div className="flex items-center justify-center gap-2 px-4 py-1 min-h-[48px]" onClick={(e) => e.stopPropagation()}>
        {myBench.length === 0 ? (
          <div className="text-green-800 text-xs">Empty bench</div>
        ) : (
          myBench.map(card => (
            <PKMCard
              key={card.id}
              card={card}
              compact
              isValidTarget={mode === 'select_energy_target' || mode === 'select_evolution_target' || mode === 'select_retreat_target'}
              onClick={() => handleFieldPokemonClick(card.id, true)}
            />
          ))
        )}
        {/* Bench slots */}
        {myBench.length < 5 && Array.from({ length: 5 - myBench.length }).map((_, i) => (
          <div key={`empty-${i}`} className="w-20 h-12 rounded border border-dashed border-green-800 opacity-30" />
        ))}
      </div>

      {/* Player info bar */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-black/30">
        <div className="flex items-center gap-3">
          <span className="text-white text-sm font-bold">{myPlayer.name}</span>
          <span className="text-gray-400 text-xs">Deck: {myPlayer.library_size}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-yellow-400 text-xs font-bold">Prizes: </span>
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className={`w-3 h-4 rounded-sm ${
                i < myPrizes ? 'bg-yellow-500 border border-yellow-300' : 'bg-gray-700 border border-gray-600'
              }`}
            />
          ))}
        </div>
      </div>

      {/* Player hand */}
      <div className="flex justify-center gap-2 px-4 py-2 overflow-x-auto" onClick={(e) => e.stopPropagation()}>
        {hand.map(card => (
          <PKMCard
            key={card.id}
            card={card}
            isSelected={selectedHandCardId === card.id}
            onClick={() => handleHandCardClick(card)}
          />
        ))}
        {hand.length === 0 && (
          <div className="text-green-800 text-sm py-4">No cards in hand</div>
        )}
      </div>

      {/* Action bar */}
      <div className="flex items-center justify-center gap-3 px-4 py-2 bg-black/40 border-t border-green-800">
        <button
          onClick={handleRetreatClick}
          disabled={!isMyTurn || myBench.length === 0}
          className={`px-4 py-2 rounded-lg font-bold text-sm transition-all ${
            isMyTurn && myBench.length > 0
              ? 'bg-blue-700 text-white hover:bg-blue-600'
              : 'bg-gray-700 text-gray-500 cursor-not-allowed'
          }`}
        >
          Retreat
        </button>

        <button
          onClick={(e) => { e.stopPropagation(); onEndTurn(); }}
          disabled={!isMyTurn}
          className={`px-6 py-2 rounded-lg font-bold text-sm transition-all ${
            isMyTurn
              ? 'bg-yellow-600 text-white hover:bg-yellow-500 shadow-lg'
              : 'bg-gray-700 text-gray-500 cursor-not-allowed'
          }`}
        >
          End Turn
        </button>
      </div>

      {/* Interaction mode indicator */}
      {mode !== 'none' && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-blue-900/90 text-blue-200 px-4 py-2 rounded-lg text-sm font-bold shadow-lg z-50">
          {mode === 'select_energy_target' && 'Select a Pokemon to attach energy (click empty to cancel)'}
          {mode === 'select_attack' && 'Select an attack'}
          {mode === 'select_retreat_target' && 'Select a bench Pokemon to swap in (click empty to cancel)'}
          {mode === 'select_evolution_target' && 'Select a Pokemon to evolve (click empty to cancel)'}
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
                ? 'You collected all your prize cards!'
                : 'Your opponent wins!'}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
