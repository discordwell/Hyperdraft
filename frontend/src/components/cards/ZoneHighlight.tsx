/**
 * ZoneHighlight — visual wrapper for drop zones.
 *
 * Renders an engine-tinted ring and lift when:
 *  - A card is primed or being dragged, AND
 *  - This zone accepts that card (valid), AND
 *  - (optionally brighter) the cursor is hovering this zone.
 *
 * The engine wraps its drop-zone container in this component and binds
 * the props from `useCardZone(...)`. The wrapper is a styled `<div>`
 * positioned absolutely above the zone's content — no layout impact.
 *
 * Compose this with `useCardZone` in the engine:
 *
 *   const zoneProps = useCardZone({ zoneId, engineId, onPlay });
 *   return (
 *     <div
 *       onClick={zoneProps.onClick}
 *       onDragOver={zoneProps.onDragOver}
 *       onDragLeave={zoneProps.onDragLeave}
 *       onDrop={zoneProps.onDrop}
 *       style={{ position: 'relative' }}
 *     >
 *       <ZoneHighlight {...zoneProps} />
 *       {... zone content ...}
 *     </div>
 *   );
 */

interface ZoneHighlightProps {
  isValid: boolean;
  isHovered: boolean;
  hasActiveCard: boolean;
  activeAccent: string | null;
}

export default function ZoneHighlight({
  isValid,
  isHovered,
  hasActiveCard,
  activeAccent,
}: ZoneHighlightProps) {
  if (!hasActiveCard) return null;
  if (!isValid) return null;

  const accent = activeAccent ?? '#60a5fa';
  const ringWidth = isHovered ? 5 : 3;
  const ringOpacity = isHovered ? 1.0 : 0.85;
  const outerGlow = isHovered ? 32 : 18;
  const animation = isHovered ? 'none' : 'card-zone-pulse 1.6s ease-in-out infinite';

  return (
    <>
      <style>{`
        @keyframes card-zone-pulse {
          0%, 100% { opacity: 0.85; }
          50%      { opacity: 1; }
        }
      `}</style>
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          borderRadius: 'inherit',
          boxShadow: `inset 0 0 0 ${ringWidth}px ${accent}${alphaHex(ringOpacity)}, 0 0 ${outerGlow}px ${accent}${alphaHex(ringOpacity * 0.55)}, inset 0 0 24px ${accent}${alphaHex(ringOpacity * 0.18)}`,
          transition: 'box-shadow 120ms ease',
          animation,
          zIndex: 5,
        }}
      />
    </>
  );
}

function alphaHex(opacity: number): string {
  const a = Math.round(Math.max(0, Math.min(1, opacity)) * 255);
  return a.toString(16).padStart(2, '0');
}
