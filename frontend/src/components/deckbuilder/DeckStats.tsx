/**
 * DeckStats Component
 *
 * Displays deck statistics including counts and validation status.
 */

import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { ManaCurveChart } from './ManaCurveChart';
import { COLORS, type ColorSymbol } from '../../types/deckbuilder';

export function DeckStats() {
  const { currentDeck, deckStats } = useDeckbuilderStore();

  const mainboardCount = currentDeck.mainboard.reduce((sum, e) => sum + e.qty, 0);
  const sideboardCount = currentDeck.sideboard.reduce((sum, e) => sum + e.qty, 0);

  return (
    <div className="p-4 border-b border-gray-700">
      {/* Deck Colors */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-gray-500 uppercase">Colors:</span>
        <div className="flex gap-1">
          {currentDeck.colors.length > 0 ? (
            currentDeck.colors.map((color) => {
              const colorKey = color as ColorSymbol;
              return (
                <div
                  key={color}
                  className="w-5 h-5 rounded-full border border-white/30"
                  style={{ backgroundColor: COLORS[colorKey]?.hex || '#666' }}
                  title={COLORS[colorKey]?.name}
                />
              );
            })
          ) : (
            <span className="text-gray-500 text-xs">Colorless</span>
          )}
        </div>
      </div>

      {/* Mana Curve */}
      {deckStats && (
        <ManaCurveChart
          manaCurve={deckStats.mana_curve}
          averageCmc={deckStats.average_cmc}
        />
      )}

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-2 mt-3">
        <div className="text-center">
          <div className="text-lg font-bold text-white">{mainboardCount}</div>
          <div className="text-xs text-gray-500">Main</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-white">
            {deckStats?.land_count ?? 0}
          </div>
          <div className="text-xs text-gray-500">Lands</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-white">
            {deckStats?.creature_count ?? 0}
          </div>
          <div className="text-xs text-gray-500">Creatures</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-white">
            {deckStats?.spell_count ?? 0}
          </div>
          <div className="text-xs text-gray-500">Spells</div>
        </div>
      </div>

      {/* Validation Status */}
      {deckStats?.validation && (
        <div className={`mt-3 text-xs ${
          deckStats.validation.is_valid ? 'text-green-400' : 'text-yellow-400'
        }`}>
          {deckStats.validation.is_valid ? (
            <span>Deck is valid</span>
          ) : (
            <div>
              <span className="block">Deck validation issues:</span>
              <ul className="list-disc list-inside mt-1">
                {deckStats.validation.errors.map((error, i) => (
                  <li key={i}>{error}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Sideboard Count */}
      {sideboardCount > 0 && (
        <div className="mt-2 text-xs text-gray-500">
          Sideboard: {sideboardCount}/15
        </div>
      )}
    </div>
  );
}
