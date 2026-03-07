/**
 * PKMActionBar - Extracted action bar with attack/retreat/end turn buttons.
 *
 * Shows attack buttons with energy cost dots + damage,
 * retreat with cost indicator, pulsing End Turn, and ability button.
 */

import { motion } from 'framer-motion';
import type { CardData } from '../../types';

const TYPE_COLORS: Record<string, string> = {
  G: 'bg-green-600', R: 'bg-red-600', W: 'bg-blue-500', L: 'bg-yellow-400',
  P: 'bg-purple-500', F: 'bg-orange-700', D: 'bg-gray-800', M: 'bg-gray-400',
  N: 'bg-amber-600', C: 'bg-gray-300',
};

interface PKMActionBarProps {
  isMyTurn: boolean;
  activePokemon: CardData | null;
  benchCount: number;
  mode: string;  // Current interaction mode
  onAttack: (index: number) => void;
  onRetreat: () => void;
  onAbility: (pokemonId: string) => void;
  onEndTurn: () => void;
  onCancel: () => void;
}

export function PKMActionBar({
  isMyTurn,
  activePokemon,
  benchCount,
  mode,
  onAttack,
  onRetreat,
  onAbility,
  onEndTurn,
  onCancel,
}: PKMActionBarProps) {
  const showActions = isMyTurn && mode === 'none';

  return (
    <div className="flex items-center justify-center gap-3 px-4 py-2 bg-black/40 border-t border-green-800">
      {/* Attack buttons */}
      {showActions && activePokemon?.attacks && activePokemon.attacks.map((atk: any, i: number) => (
        <button
          key={i}
          onClick={() => onAttack(i)}
          className="group px-3 py-1.5 bg-red-700 text-white text-xs font-bold rounded hover:bg-red-600 transition-all whitespace-nowrap flex items-center gap-1.5"
        >
          {/* Energy cost dots */}
          {atk.cost && atk.cost.length > 0 && (
            <span className="flex gap-0.5">
              {atk.cost.map((c: any, j: number) => {
                const count = c.count || 1;
                return Array.from({ length: count }).map((_, k) => (
                  <span key={`${j}-${k}`} className={`w-2.5 h-2.5 rounded-full ${TYPE_COLORS[c.type] || TYPE_COLORS.C} border border-white/40 inline-block`} />
                ));
              })}
            </span>
          )}
          <span>{atk.name}</span>
          {atk.damage > 0 && (
            <span className="text-red-200">({atk.damage})</span>
          )}
        </button>
      ))}

      {/* Ability button */}
      {showActions && activePokemon?.ability_name && (
        <button
          onClick={() => onAbility(activePokemon.id)}
          className="px-3 py-1.5 bg-purple-700 text-white text-xs font-bold rounded hover:bg-purple-600 transition-all whitespace-nowrap"
        >
          {activePokemon.ability_name}
        </button>
      )}

      {/* Retreat */}
      <button
        onClick={onRetreat}
        disabled={!isMyTurn || benchCount === 0}
        className={`px-4 py-2 rounded-lg font-bold text-sm transition-all flex items-center gap-1.5 ${
          isMyTurn && benchCount > 0
            ? 'bg-blue-700 text-white hover:bg-blue-600'
            : 'bg-gray-700 text-gray-500 cursor-not-allowed'
        }`}
      >
        Retreat
        {activePokemon && (activePokemon.retreat_cost || 0) > 0 && (
          <span className="flex gap-0.5">
            {Array.from({ length: activePokemon.retreat_cost || 0 }).map((_, i) => (
              <span key={i} className="w-2 h-2 rounded-full bg-gray-300 border border-white/40 inline-block" />
            ))}
          </span>
        )}
      </button>

      {/* End Turn */}
      <motion.button
        onClick={(e) => { e.stopPropagation(); onEndTurn(); }}
        disabled={!isMyTurn}
        animate={isMyTurn ? { scale: [1, 1.03, 1] } : {}}
        transition={{ repeat: Infinity, duration: 2, ease: 'easeInOut' }}
        className={`px-6 py-2 rounded-lg font-bold text-sm transition-all ${
          isMyTurn
            ? 'bg-yellow-600 text-white hover:bg-yellow-500 shadow-lg shadow-yellow-600/30'
            : 'bg-gray-700 text-gray-500 cursor-not-allowed'
        }`}
      >
        End Turn
      </motion.button>

      {/* Mode indicator — click to cancel */}
      {mode !== 'none' && (
        <div
          onClick={onCancel}
          className="absolute bottom-16 left-1/2 -translate-x-1/2 bg-blue-900/90 text-blue-200 px-4 py-2 rounded-lg text-sm font-bold shadow-lg z-50 whitespace-nowrap cursor-pointer hover:bg-blue-800/90 transition-colors"
        >
          {mode === 'select_energy_target' && 'Select a Pokemon to attach energy'}
          {mode === 'select_attack' && 'Select an attack'}
          {mode === 'select_retreat_target' && 'Select a bench Pokemon to swap in'}
          {mode === 'select_evolution_target' && 'Select a Pokemon to evolve'}
          <span className="ml-2 text-blue-400 text-xs">(click to cancel)</span>
        </div>
      )}
    </div>
  );
}
