import type { ReactNode } from 'react';

export interface LedgerRow {
  n: ReactNode;
  k: ReactNode;
  v: ReactNode;
}

interface LedgerProps {
  rows: LedgerRow[];
  className?: string;
}

export function Ledger({ rows, className }: LedgerProps) {
  return (
    <div className={`lab-ledger ${className ?? ''}`.trim()}>
      {rows.map((r, i) => (
        <div className="row" key={i}>
          <span className="n">{r.n}</span>
          <span className="k">{r.k}</span>
          <span className="v">{r.v}</span>
        </div>
      ))}
    </div>
  );
}
