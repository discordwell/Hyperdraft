/**
 * ManaCurveChart Component — lab-posture bar chart.
 *
 * Per HD-ART-04 `.curve` block: 8-column grid, ink bars (sodium pivot for
 * the peak), serif tick numerals, hairline base rule. The heading + average
 * caption now live in `<DeckStats>` (the wrapping ledger) so this is just
 * the chart — paper-on-paper, no rounded card.
 */

interface ManaCurveChartProps {
  manaCurve: Record<string, number>;
  averageCmc: number;
}

export function ManaCurveChart({ manaCurve }: ManaCurveChartProps) {
  // Get max count for scaling
  const maxCount = Math.max(1, ...Object.values(manaCurve));

  // CMC labels — HD-ART-04 uses 0..7+ (8 bars). The bucket "7+" rolls up
  // anything >=7 from the backend so a high-cost outlier still shows.
  const cmcLabels = ['0', '1', '2', '3', '4', '5', '6', '7+'];

  // Identify the peak bucket so it can take the sodium accent (per the
  // artboard's emphasis on the curve's center of mass).
  let peakIndex = 0;
  let peakValue = 0;
  cmcLabels.forEach((_, i) => {
    const value =
      i === cmcLabels.length - 1
        ? (manaCurve[i.toString()] || 0) +
          Object.entries(manaCurve)
            .filter(([k]) => Number.parseInt(k, 10) >= i)
            .reduce((sum, [, v]) => sum + v, 0) -
          (manaCurve[i.toString()] || 0)
        : manaCurve[i.toString()] || 0;
    if (value > peakValue) {
      peakValue = value;
      peakIndex = i;
    }
  });

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${cmcLabels.length}, 1fr)`,
        gap: 4,
        alignItems: 'end',
        height: 90,
        padding: '6px 0',
        borderBottom: '1px solid var(--rule-2)',
      }}
      data-testid="deckbuilder-curve"
    >
      {cmcLabels.map((label, index) => {
        // Roll up everything at or beyond the last bucket so 7+ aggregates.
        const count =
          index === cmcLabels.length - 1
            ? Object.entries(manaCurve)
                .filter(([k]) => Number.parseInt(k, 10) >= index)
                .reduce((sum, [, v]) => sum + v, 0)
            : manaCurve[index.toString()] || 0;
        const height = maxCount > 0 ? (count / maxCount) * 100 : 0;
        const isPeak = index === peakIndex && count > 0;

        return (
          <div
            key={label}
            style={{
              background: isPeak ? 'var(--sodium)' : 'var(--ink)',
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'end',
              alignItems: 'center',
              color: 'var(--paper)',
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              fontWeight: 500,
              height: `${Math.max(height, count > 0 ? 8 : 2)}%`,
              minHeight: 4,
            }}
            title={`${count} cards at CMC ${label}`}
          >
            <span
              style={{
                position: 'absolute',
                top: '100%',
                marginTop: 4,
                color: 'var(--ink-3)',
                fontSize: 9,
                letterSpacing: '.04em',
              }}
            >
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
