import type { ReactNode } from 'react';
import type { PipelineStage } from '../../data/pipelineCards';

const STAGE_ACCENT: Record<PipelineStage, string> = {
  TRANSFORM: 'var(--plasma)',
  PREVENT: 'var(--halt)',
  RESOLVE: 'var(--ink)',
  REACT: 'var(--acid)',
};

interface PipelineColumnProps {
  stage: PipelineStage;
  opponentCard: ReactNode | null;
  playerCard: ReactNode | null;
  mandatory?: boolean;
  onPlayerSlotClick?: () => void;
}

export function PipelineColumn({
  stage,
  opponentCard,
  playerCard,
  mandatory,
  onPlayerSlotClick,
}: PipelineColumnProps) {
  const accent = STAGE_ACCENT[stage];

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          paddingBottom: 4,
          borderBottom: '1.5px solid ' + accent,
          width: '100%',
          justifyContent: 'center',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.16em',
            color: accent,
            fontWeight: 600,
          }}
        >
          {stage}
        </span>
      </div>

      <div
        style={{
          minHeight: 220,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {opponentCard ?? <EmptySlot label="awaiting" />}
      </div>

      <div
        style={{
          width: '100%',
          height: 1,
          background: accent,
          opacity: 0.4,
        }}
      />

      <button
        type="button"
        onClick={onPlayerSlotClick}
        disabled={!onPlayerSlotClick}
        style={{
          minHeight: 220,
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'transparent',
          border: 'none',
          cursor: onPlayerSlotClick ? 'pointer' : 'default',
          padding: 0,
        }}
      >
        {playerCard ?? (
          <EmptySlot
            label={mandatory ? 'YOU MUST SLOT' : 'slot here'}
            highlight={mandatory}
          />
        )}
      </button>
    </div>
  );
}

function EmptySlot({ label, highlight }: { label: string; highlight?: boolean }) {
  return (
    <div
      style={{
        width: 152,
        height: 212,
        border:
          '1.5px dashed ' +
          (highlight ? 'var(--sodium)' : 'var(--rule)'),
        background: highlight
          ? 'color-mix(in oklab, var(--sodium) 8%, transparent)'
          : 'transparent',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          letterSpacing: '0.18em',
          color: highlight ? 'var(--sodium)' : 'var(--ink-3)',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
    </div>
  );
}
