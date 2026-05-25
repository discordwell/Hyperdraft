/**
 * DropChoicePopup
 *
 * Mounted once near the App root, this component renders the post-drop
 * action picker driven by `useDropChoiceStore`. Engines fire it after
 * a drag-drop or click-prime commit when the chosen zone has multiple
 * possible interpretations (YGO Normal Summon vs Set, Activate vs Set,
 * MTG cast vs hold-priority, etc.).
 *
 * Compared to the full inspector modal, this is a tight popup anchored
 * near the cursor — designed not to block the rest of the board.
 */

import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

import {
  useDropChoiceStore,
  type DropChoiceOption,
} from '../../stores/dropChoiceStore';

function buttonStyle(variant: DropChoiceOption['variant'], disabled: boolean): React.CSSProperties {
  const base: React.CSSProperties = {
    fontFamily: 'JetBrains Mono, ui-monospace, monospace',
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    padding: '8px 18px',
    borderRadius: 5,
    border: '1px solid transparent',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    transition: 'transform 80ms ease, background 120ms ease',
  };
  if (variant === 'danger') {
    return { ...base, background: '#7f1d1d', borderColor: '#ef4444', color: '#fee2e2' };
  }
  if (variant === 'secondary') {
    return { ...base, background: 'transparent', borderColor: '#475569', color: '#e2e8f0' };
  }
  return {
    ...base,
    background: '#1e293b',
    borderColor: '#64748b',
    color: '#f1f5f9',
    boxShadow: '0 0 0 1px rgba(96, 165, 250, 0.3)',
  };
}

export default function DropChoicePopup() {
  const card = useDropChoiceStore((s) => s.card);
  const options = useDropChoiceStore((s) => s.options);
  const position = useDropChoiceStore((s) => s.position);
  const close = useDropChoiceStore((s) => s.close);
  const popupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!card) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === 'Escape') close();
    }
    function onPointerDown(ev: PointerEvent) {
      if (!popupRef.current) return;
      if (!popupRef.current.contains(ev.target as Node)) close();
    }
    document.addEventListener('keydown', onKey);
    // defer so the click that opened us doesn't immediately close us
    const t = setTimeout(() => document.addEventListener('pointerdown', onPointerDown), 0);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointerDown);
      clearTimeout(t);
    };
  }, [card, close]);

  if (!card) return null;

  const positioning: React.CSSProperties = position
    ? {
        position: 'fixed',
        // Clamp away from the screen edge so the popup is always visible.
        top: Math.min(Math.max(position.y - 20, 16), window.innerHeight - 200),
        left: Math.min(Math.max(position.x + 12, 16), window.innerWidth - 280),
      }
    : {
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
      };

  const handle = (option: DropChoiceOption) => {
    if (option.disabled) return;
    option.onClick();
    close();
  };

  return createPortal(
    <div
      ref={popupRef}
      role="dialog"
      aria-modal="false"
      aria-label={`${card.name} — choose an action`}
      style={{
        ...positioning,
        zIndex: 950,
        minWidth: 240,
        maxWidth: 320,
        background: '#0f172a',
        border: '1px solid #475569',
        borderRadius: 6,
        boxShadow: '0 16px 40px rgba(0, 0, 0, 0.55)',
        padding: '14px 16px 12px',
        color: '#e5e7eb',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        animation: 'drop-choice-pop-in 120ms ease-out',
      }}
    >
      <style>{`
        @keyframes drop-choice-pop-in {
          from { opacity: 0; transform: ${position ? 'translateY(-4px)' : 'translate(-50%, -50%) scale(0.95)'}; }
          to   { opacity: 1; transform: ${position ? 'translateY(0)' : 'translate(-50%, -50%) scale(1)'}; }
        }
      `}</style>

      <div
        style={{
          fontFamily: 'JetBrains Mono, ui-monospace, monospace',
          fontSize: 13,
          fontWeight: 700,
          color: '#fbbf24',
          letterSpacing: '-0.005em',
        }}
      >
        {card.name}
      </div>
      {card.subtitle && (
        <div
          style={{
            fontFamily: 'JetBrains Mono, ui-monospace, monospace',
            fontSize: 10,
            color: '#94a3b8',
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            marginTop: 2,
          }}
        >
          {card.subtitle}
        </div>
      )}

      <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {options.map((opt, idx) => (
          <button
            key={`${opt.label}-${idx}`}
            type="button"
            onClick={() => handle(opt)}
            disabled={opt.disabled}
            title={opt.disabledReason}
            style={buttonStyle(opt.variant ?? 'primary', !!opt.disabled)}
          >
            {opt.icon && <span style={{ marginRight: 6, display: 'inline-block' }}>{opt.icon}</span>}
            {opt.label}
          </button>
        ))}
        <button
          type="button"
          onClick={close}
          style={buttonStyle('secondary', false)}
        >
          Cancel
        </button>
      </div>
    </div>,
    document.body,
  );
}
