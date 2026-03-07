/**
 * YGOActionBar - Extracted action bar for Yu-Gi-Oh! game board.
 *
 * Button categories: Gold (summon), Teal (spell), Pink (trap),
 * Red (attack), Indigo/Gold (phase). Pulsing End Turn.
 */

import { motion } from 'framer-motion';

interface YGOActionBarProps {
  isMyTurn: boolean;
  // Hand card state
  selectedHandCard: string | null;
  isMonster: boolean;
  isSpell: boolean;
  isTrap: boolean;
  // Field card state
  selectedFieldCard: string | null;
  isFieldMonster: boolean;
  isFaceDown: boolean;
  isDefPos: boolean;
  // Attack mode
  attackMode: string | null;
  // Actions
  onNormalSummon: () => void;
  onSetMonster: () => void;
  onFlipSummon: () => void;
  onChangePosition: () => void;
  onActivateCard: () => void;
  onSetSpellTrap: () => void;
  onAttack: () => void;
  onCancelAttack: () => void;
  onEndPhase: () => void;
  onEndTurn: () => void;
}

export function YGOActionBar({
  isMyTurn,
  selectedHandCard,
  isMonster,
  isSpell,
  isTrap,
  selectedFieldCard,
  isFieldMonster,
  isFaceDown,
  isDefPos,
  attackMode,
  onNormalSummon,
  onSetMonster,
  onFlipSummon,
  onChangePosition,
  onActivateCard,
  onSetSpellTrap,
  onAttack,
  onCancelAttack,
  onEndPhase,
  onEndTurn,
}: YGOActionBarProps) {
  if (!isMyTurn) return null;

  return (
    <div className="relative">
      {/* Attack mode indicator */}
      {attackMode && (
        <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-red-900/90 text-red-200 px-4 py-1.5 rounded-lg text-sm font-bold shadow-lg z-50 whitespace-nowrap border border-red-700/50">
          Select attack target...
          <span className="ml-2 text-red-400 text-xs cursor-pointer hover:text-red-300" onClick={onCancelAttack}>
            (cancel)
          </span>
        </div>
      )}

      <div className="bg-ygo-dark/80 backdrop-blur-sm border-t border-ygo-gold-dim/30 px-4 py-2 flex gap-2 justify-center flex-wrap items-center">
        {/* Hand card actions */}
        {selectedHandCard && isMonster && (
          <>
            <button
              onClick={onNormalSummon}
              className="px-3 py-1.5 bg-ygo-gold/90 hover:bg-ygo-gold text-ygo-dark text-xs font-bold rounded transition-colors"
            >
              Normal Summon
            </button>
            <button
              onClick={onSetMonster}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-bold rounded transition-colors"
            >
              Set
            </button>
          </>
        )}
        {selectedHandCard && isSpell && (
          <>
            <button
              onClick={onActivateCard}
              className="px-3 py-1.5 bg-teal-700 hover:bg-teal-600 text-white text-xs font-bold rounded transition-colors"
            >
              Activate
            </button>
            <button
              onClick={onSetSpellTrap}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-bold rounded transition-colors"
            >
              Set
            </button>
          </>
        )}
        {selectedHandCard && isTrap && (
          <button
            onClick={onSetSpellTrap}
            className="px-3 py-1.5 bg-pink-700 hover:bg-pink-600 text-white text-xs font-bold rounded transition-colors"
          >
            Set Trap
          </button>
        )}

        {/* Field card actions */}
        {selectedFieldCard && isFieldMonster && !isFaceDown && !isDefPos && (
          <button
            onClick={onAttack}
            className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white text-xs font-bold rounded transition-colors"
          >
            Attack
          </button>
        )}
        {selectedFieldCard && isFieldMonster && isFaceDown && (
          <button
            onClick={onFlipSummon}
            className="px-3 py-1.5 bg-ygo-gold/90 hover:bg-ygo-gold text-ygo-dark text-xs font-bold rounded transition-colors"
          >
            Flip Summon
          </button>
        )}
        {selectedFieldCard && isFieldMonster && !isFaceDown && (
          <button
            onClick={onChangePosition}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-bold rounded transition-colors"
          >
            {isDefPos ? 'To ATK' : 'To DEF'}
          </button>
        )}

        {/* Attack mode cancel */}
        {attackMode && (
          <button
            onClick={onCancelAttack}
            className="px-3 py-1.5 bg-gray-600 hover:bg-gray-500 text-white text-xs font-bold rounded transition-colors"
          >
            Cancel Attack
          </button>
        )}

        {/* Phase controls */}
        <div className="flex gap-1.5 ml-auto">
          <button
            onClick={onEndPhase}
            className="px-3 py-1.5 bg-indigo-800 hover:bg-indigo-700 text-white text-xs font-bold rounded transition-colors"
          >
            End Phase
          </button>
          <motion.button
            onClick={onEndTurn}
            animate={{ scale: [1, 1.03, 1] }}
            transition={{ repeat: Infinity, duration: 2, ease: 'easeInOut' }}
            className="px-4 py-1.5 bg-ygo-gold hover:bg-ygo-gold-bright text-ygo-dark text-xs font-bold rounded shadow-lg shadow-ygo-gold/20 transition-colors"
          >
            End Turn
          </motion.button>
        </div>
      </div>
    </div>
  );
}
