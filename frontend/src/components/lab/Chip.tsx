import type { ReactNode } from 'react';

interface ChipProps {
  children: ReactNode;
  dot?: boolean;
  tone?: 'sodium' | 'plasma' | 'acid' | 'halt' | 'ink';
  className?: string;
}

const TONE_VAR: Record<NonNullable<ChipProps['tone']>, string> = {
  sodium: 'var(--sodium)',
  plasma: 'var(--plasma)',
  acid: 'var(--acid)',
  halt: 'var(--halt)',
  ink: 'var(--ink)',
};

export function Chip({ children, dot, tone = 'sodium', className }: ChipProps) {
  return (
    <span className={`lab-chip ${className ?? ''}`.trim()}>
      {dot && <span className="dot" style={{ background: TONE_VAR[tone] }} />}
      {children}
    </span>
  );
}
