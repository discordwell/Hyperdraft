/**
 * DeckStats Component — lab-posture stats sidebar (Phase C / buildplan
 * item 9).
 *
 * Mirrors HD-ART-04's `.dbk-side` block: hairline-ruled headings, mono
 * telemetry, ink bars, serif numerics. Color swatches (MTG only) keep
 * the engine's W/U/B/R/G hexes because that *is* the per-engine vocabulary
 * for color identity — `docs/design/brand.md` says per-engine semantic
 * filter pills stay in the game's idiom.
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
    <div
      style={{
        padding: 18,
        borderBottom: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
      data-testid="deckbuilder-stats"
    >
      {/* Deck Colors — MTG only. The W/U/B/R/G swatches keep their per-engine
          color encoding by design (per the brand doc: filter pills that
          encode per-engine semantics stay in their game's vocabulary). */}
      {gameModule.showColors && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={ledgerHeadingStyle}>Colors</span>
          <div style={{ display: 'flex', gap: 4 }}>
            {currentDeck.colors.length > 0 ? (
              currentDeck.colors.map((color) => {
                const colorKey = color as ColorSymbol;
                return (
                  <div
                    key={color}
                    style={{
                      width: 18,
                      height: 18,
                      borderRadius: '50%',
                      border: '1px solid var(--rule)',
                      background: COLORS[colorKey]?.hex || 'var(--ink-3)',
                    }}
                    title={COLORS[colorKey]?.name}
                    aria-label={COLORS[colorKey]?.name}
                  />
                );
              })
            ) : (
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--ink-3)',
                  letterSpacing: '.04em',
                }}
              >
                colorless
              </span>
            )}
          </div>
        </div>
      )}

      {/* Cost Curve (mana / material / level depending on game) */}
      {deckStats && (
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              marginBottom: 6,
            }}
          >
            <span style={ledgerHeadingStyle}>
              {currentGame === 'mtg' ? 'Mana curve' : 'Cost curve'}
            </span>
            <span style={ledgerValueStyle}>avg {averageCost.toFixed(1)}</span>
          </div>
          <ManaCurveChart manaCurve={curve} averageCmc={averageCost} />
        </div>
      )}

      {/* Quick Stats — composition tiles, lab posture */}
      <div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            marginBottom: 6,
          }}
        >
          <span style={ledgerHeadingStyle}>Composition</span>
          <span style={ledgerValueStyle}>
            {mainboardCount}
            {sideboardCount > 0 ? ` / ${sideboardCount}` : ''}
          </span>
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: tiles.length === 3 ? 'repeat(4, 1fr)' : 'repeat(2, 1fr)',
            gap: 8,
          }}
        >
          <StatTile label="Main" value={mainboardCount} />
          {tiles.map((t) => (
            <StatTile key={t.label} label={t.label} value={t.value} />
          ))}
        </div>
      </div>

      {/* Per-game polish: material curve / energy mix / attribute breakdown */}
      {deckStats && StatsExtras && <StatsExtras stats={deckStats} />}

      {/* Validation Status — lab posture (acid for valid, sodium for warn) */}
      {deckStats?.validation && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.04em',
            color: deckStats.validation.is_valid ? 'var(--acid)' : 'var(--sodium)',
            paddingTop: 6,
            borderTop: '1px solid var(--rule-2)',
          }}
        >
          {deckStats.validation.is_valid ? (
            <span>· deck is valid</span>
          ) : (
            <div>
              <span style={{ display: 'block', marginBottom: 4 }}>· validation issues</span>
              <ul style={{ margin: 0, paddingLeft: 14, color: 'var(--ink-2)' }}>
                {deckStats.validation.errors.map((error, i) => (
                  <li key={i} style={{ marginTop: 2 }}>
                    {error}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Sideboard count, mono caption */}
      {sideboardCount > 0 && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.04em',
            color: 'var(--ink-3)',
          }}
        >
          Sideboard: {sideboardCount}/15
        </div>
      )}
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 22,
          fontWeight: 400,
          letterSpacing: '-.01em',
          color: 'var(--ink)',
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          letterSpacing: '.1em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          marginTop: 4,
        }}
      >
        {label}
      </div>
    </div>
  );
}

const ledgerHeadingStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10.5,
  fontWeight: 500,
  letterSpacing: '.14em',
  textTransform: 'uppercase',
  color: 'var(--ink-3)',
};

const ledgerValueStyle: React.CSSProperties = {
  fontFamily: 'var(--font-serif)',
  fontSize: 13,
  color: 'var(--ink)',
};
