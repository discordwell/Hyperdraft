/**
 * ManaCurveChart Component
 *
 * Simple bar chart showing card distribution by mana value.
 */

interface ManaCurveChartProps {
  manaCurve: Record<string, number>;
  averageCmc: number;
}

export function ManaCurveChart({ manaCurve, averageCmc }: ManaCurveChartProps) {
  // Get max count for scaling
  const maxCount = Math.max(1, ...Object.values(manaCurve));

  // CMC labels
  const cmcLabels = ['0', '1', '2', '3', '4', '5', '6+'];

  return (
    <div className="bg-gray-900/50 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-500 uppercase">Mana Curve</span>
        <span className="text-xs text-gray-400">
          Avg: <span className="text-white font-semibold">{averageCmc.toFixed(1)}</span>
        </span>
      </div>

      {/* Bar Chart */}
      <div className="flex items-end justify-between gap-1 h-16">
        {cmcLabels.map((label, index) => {
          const count = manaCurve[index.toString()] || 0;
          const height = maxCount > 0 ? (count / maxCount) * 100 : 0;

          return (
            <div key={label} className="flex-1 flex flex-col items-center">
              {/* Bar */}
              <div
                className="w-full bg-game-accent/70 rounded-t transition-all duration-200"
                style={{ height: `${Math.max(height, count > 0 ? 10 : 0)}%` }}
                title={`${count} cards at CMC ${label}`}
              />
              {/* Count */}
              <div className="text-xs text-gray-400 mt-1">{count || ''}</div>
              {/* Label */}
              <div className="text-xs text-gray-500">{label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
