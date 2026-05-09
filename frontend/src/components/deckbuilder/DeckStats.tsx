/**
 * DeckStats Component
 *
 * Displays deck statistics including counts and validation status.
 * Game-aware: tile labels and curve definitions adapt to the active game.
 */

import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { ManaCurveChart } from './ManaCurveChart';
import { COLORS, type ColorSymbol } from '../../types/deckbuilder';
import { getGameModule } from '../../games/registry';

export function DeckStats() {
  const { currentDeck, currentGame, deckStats } = useDeckbuilderStore();
  const gameModule = getGameModule(currentGame);

  const mainboardCount = currentDeck.mainboard.reduce((sum, e) => sum + e.qty, 0);
  const sideboardCount = currentDeck.sideboard.reduce((sum, e) => sum + e.qty, 0);
  const tiles = gameModule.tiles(deckStats);

  // The chart is mana-curve-flavored for MTG; for other games we show the
  // generic cost curve under a game-appropriate label below.
  const curve = deckStats?.mana_curve ?? deckStats?.cost_curve ?? {};
  const avgFromExtras = (deckStats?.extras as Record<string, unknown> | undefined)?.average_cost;
  const averageCost = deckStats?.average_cmc ?? (typeof avgFromExtras === 'number' ? avgFromExtras : 0);

  const StatsExtras = gameModule.StatsExtras;

  return (
    <div className="p-4 border-b border-gray-700">
      {/* Deck Colors — MTG only */}
      {gameModule.showColors && (
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
      )}

      {/* Cost Curve (mana / material / level depending on game) */}
      {deckStats && (
        <ManaCurveChart manaCurve={curve} averageCmc={averageCost} />
      )}

      {/* Quick Stats — count tiles adapt to the active game */}
      <div className={`grid gap-2 mt-3 ${tiles.length === 3 ? 'grid-cols-4' : 'grid-cols-2'}`}>
        <div className="text-center">
          <div className="text-lg font-bold text-white">{mainboardCount}</div>
          <div className="text-xs text-gray-500">Main</div>
        </div>
        {tiles.map((t) => (
          <div key={t.label} className="text-center">
            <div className="text-lg font-bold text-white">{t.value}</div>
            <div className="text-xs text-gray-500">{t.label}</div>
          </div>
        ))}
      </div>

      {/* Per-game polish: material curve / energy mix / attribute breakdown / class breakdown */}
      {deckStats && StatsExtras && <StatsExtras stats={deckStats} />}

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
