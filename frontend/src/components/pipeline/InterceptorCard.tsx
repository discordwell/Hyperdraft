import type { CSSProperties } from 'react';
import type { InterceptorCardDef, PipelineStage, ArtGlyph } from '../../data/pipelineCards';

const STAGE_COLOR: Record<PipelineStage, string> = {
  TRANSFORM: 'var(--plasma)',
  PREVENT: 'var(--halt)',
  RESOLVE: 'var(--ink)',
  REACT: 'var(--acid)',
};

interface InterceptorCardProps {
  card: InterceptorCardDef;
  dim?: boolean;
  sodium?: boolean;
  faceDown?: boolean;
  selected?: boolean;
  onClick?: () => void;
  width?: number;
  height?: number;
}

export function InterceptorCard({
  card,
  dim,
  sodium,
  faceDown,
  selected,
  onClick,
  width = 152,
  height = 212,
}: InterceptorCardProps) {
  if (faceDown) {
    return (
      <div
        style={{
          width,
          height,
          background: 'var(--ink)',
          border: '1px solid var(--ink-2)',
          position: 'relative',
          flexShrink: 0,
        }}
        aria-label="opponent card (face-down)"
      >
        <div style={{ position: 'absolute', inset: 6, border: '1px solid var(--ink-2)' }} />
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            color: 'var(--paper-2)',
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '0.16em',
          }}
        >
          HD
        </div>
      </div>
    );
  }

  const stageColor = STAGE_COLOR[card.stage];
  const bodyStyle: CSSProperties = {
    width,
    height,
    background: 'var(--paper)',
    border: '1px solid ' + (sodium || selected ? 'var(--sodium)' : 'var(--ink)'),
    outline: sodium || selected ? '2px solid var(--sodium)' : 'none',
    outlineOffset: 2,
    display: 'flex',
    flexDirection: 'column',
    opacity: dim ? 0.5 : 1,
    position: 'relative',
    flexShrink: 0,
    cursor: onClick ? 'pointer' : 'default',
    fontFamily: 'var(--font-sans)',
  };

  return (
    <button type="button" style={bodyStyle} onClick={onClick} aria-label={card.name}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          padding: '6px 8px',
          borderBottom: '1px solid var(--rule-2)',
          background: 'var(--paper-2)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '0.14em',
            color: 'var(--ink)',
          }}
        >
          {card.engine}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '0.12em',
            color: stageColor,
            fontWeight: 600,
          }}
        >
          {card.stage}
        </span>
      </div>
      <ArtPanel art={card.art} />
      <div style={{ padding: '6px 8px', textAlign: 'left' }}>
        <div
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: 14,
            lineHeight: 1,
            color: 'var(--ink)',
            marginBottom: 2,
          }}
        >
          {card.name}
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--ink-3)',
            lineHeight: 1.35,
          }}
        >
          {card.text}
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          top: 6,
          right: 6,
          width: 18,
          height: 18,
          background: 'var(--ink)',
          color: 'var(--paper)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          fontWeight: 600,
        }}
      >
        {card.cost}
      </div>
    </button>
  );
}

function ArtPanel({ art }: { art: ArtGlyph }) {
  let background: string;
  let clipPath: string | undefined;
  switch (art) {
    case 'tri':
      background = 'linear-gradient(135deg, var(--plasma) 50%, transparent 50%)';
      clipPath = 'polygon(50% 0, 100% 100%, 0 100%)';
      break;
    case 'bar':
      background = 'var(--halt)';
      clipPath = 'polygon(0 40%, 100% 40%, 100% 60%, 0 60%)';
      break;
    case 'square':
      background = 'var(--ink)';
      clipPath = undefined;
      break;
    case 'circle':
      background = 'var(--sodium)';
      clipPath = 'circle(45%)';
      break;
    case 'grid':
      background = 'var(--acid)';
      clipPath = undefined;
      break;
    default:
      background = 'var(--ink-2)';
      clipPath = undefined;
  }
  return (
    <div
      style={{
        background: 'var(--paper-3)',
        flex: 1,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: '10% 15%',
          background,
          clipPath,
        }}
      />
    </div>
  );
}
