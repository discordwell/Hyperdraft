/**
 * Reusable stacked-bar component for resource/type distributions.
 *
 * Each game uses this to render its own breakdown (materials, energy types,
 * attributes, classes, …) with a per-segment color and a legend underneath.
 */

interface Segment {
  key: string;
  label: string;
  value: number;
  color: string;
}

export function StackedBar({ title, segments }: { title: string; segments: Segment[] }) {
  const filtered = segments.filter((s) => s.value > 0);
  const total = filtered.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) return null;

  return (
    <div className="mt-3">
      <div className="text-xs text-gray-500 uppercase mb-1">{title}</div>
      <div className="flex h-2 rounded overflow-hidden bg-gray-800">
        {filtered.map((s) => (
          <div
            key={s.key}
            style={{
              backgroundColor: s.color,
              width: `${(s.value / total) * 100}%`,
            }}
            title={`${s.label}: ${s.value}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px] text-gray-400">
        {filtered.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1">
            <span
              className="inline-block w-2 h-2 rounded-sm"
              style={{ backgroundColor: s.color }}
            />
            {s.label}: {s.value}
          </span>
        ))}
      </div>
    </div>
  );
}
