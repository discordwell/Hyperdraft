import type { ReactNode } from 'react';

interface PlateProps {
  id?: string;
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Plate({ id, title, meta, children, className }: PlateProps) {
  return (
    <section className={`lab-plate ${className ?? ''}`.trim()}>
      <header className="lab-plate-hd">
        <div className="font-serif text-[28px] leading-none tracking-tight text-[var(--ink)]">
          {id && (
            <small className="block font-mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--ink-3)] mb-2">
              {id}
            </small>
          )}
          {title}
        </div>
        {meta && (
          <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-[var(--ink-3)]">
            {meta}
          </div>
        )}
      </header>
      {children}
    </section>
  );
}
