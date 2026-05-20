import type { PipelineEventDef } from '../../data/pipelineEvents';

interface EventCardProps {
  event: PipelineEventDef;
  index: number;
  total: number;
}

export function EventCard({ event, index, total }: EventCardProps) {
  return (
    <div
      role="img"
      aria-label={`Event ${index + 1} of ${total}: ${event.name}`}
      style={{
        width: 240,
        padding: 14,
        background: 'var(--ink)',
        color: 'var(--paper)',
        position: 'relative',
        borderRadius: 0,
        boxShadow: '0 0 0 4px color-mix(in oklab, var(--sodium) 18%, transparent)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: 6,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '0.16em',
            color: 'var(--sodium)',
          }}
        >
          EVENT · {String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
        </span>
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: 'var(--sodium)',
            display: 'inline-block',
          }}
        />
      </div>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 22,
          lineHeight: 1.05,
          marginBottom: 6,
        }}
      >
        {event.name}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--paper-2)',
          lineHeight: 1.5,
          opacity: 0.85,
        }}
      >
        {event.payload}
      </div>
      <div
        style={{
          marginTop: 8,
          paddingTop: 8,
          borderTop: '1px solid var(--ink-2)',
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          letterSpacing: '0.14em',
          color: 'var(--sodium)',
          textTransform: 'uppercase',
        }}
      >
        type · {event.type}
      </div>
    </div>
  );
}
