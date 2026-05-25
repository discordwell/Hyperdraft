/**
 * CardInspector
 *
 * Shared full-card modal: rendered once near the app root, driven by
 * `useCardInspectorStore`. Each engine's hand component calls
 * `inspector.open(card, [{label: 'Play', onClick: () => ...}])` and this
 * component handles everything else — overlay, escape-to-close,
 * click-outside-to-close, focus trap entry, and the action button row.
 *
 * Engine-specific concerns (mana validation, target selection, etc.)
 * stay in the engine: the modal just calls back. Returning `false`
 * from an action keeps the modal open so the engine can drive a
 * follow-up flow (target picker, attach destination, etc.).
 */

import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

import {
  useCardInspectorStore,
  type InspectorAction,
  type InspectableCardType,
} from '../../hooks/useCardInspector';
import { useCardZoneStore } from '../../stores/cardZoneStore';

const ENGINE_ACCENT: Record<InspectableCardType, string> = {
  creature: '#86efac',
  spell: '#93c5fd',
  land: '#d4a373',
  minion: '#fbbf24',
  pokemon: '#fca5a5',
  energy: '#fde68a',
  trainer: '#a5b4fc',
  monster: '#c4b5fd',
  spell_trap: '#67e8f9',
  cats: '#fbbf24',
  clankers: '#60a5fa',
  depths: '#22d3ee',
  finance: '#86efac',
  minecraft: '#a3e635',
  scp: '#f97316',
  other: '#9ca3af',
};

function actionStyles(variant: InspectorAction['variant'], disabled: boolean): React.CSSProperties {
  const base: React.CSSProperties = {
    fontFamily: 'JetBrains Mono, ui-monospace, monospace',
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    padding: '10px 22px',
    borderRadius: 6,
    border: '1px solid transparent',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    transition: 'transform 80ms ease, background 120ms ease',
  };
  if (variant === 'danger') {
    return {
      ...base,
      background: '#7f1d1d',
      borderColor: '#ef4444',
      color: '#fee2e2',
    };
  }
  if (variant === 'secondary') {
    return {
      ...base,
      background: 'transparent',
      borderColor: '#475569',
      color: '#e2e8f0',
    };
  }
  // primary (default)
  return {
    ...base,
    background: '#1e293b',
    borderColor: '#64748b',
    color: '#f1f5f9',
    boxShadow: '0 0 0 1px rgba(96, 165, 250, 0.3)',
  };
}

export default function CardInspector() {
  const card = useCardInspectorStore((s) => s.card);
  const actions = useCardInspectorStore((s) => s.actions);
  const close = useCardInspectorStore((s) => s.close);
  // When the inspected card is primed in the shared card-zone store, dim
  // the backdrop and remove the blur so the primed/highlighted drop
  // zones underneath remain visible (click-prime → click-zone path).
  const primedCardId = useCardZoneStore((s) => s.primedCardId);
  const isPrimed = card !== null && primedCardId === card.id;
  const backdropRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!card) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === 'Escape') close();
    }
    document.addEventListener('keydown', onKey);
    // Focus the primary action so Enter confirms.
    requestAnimationFrame(() => {
      primaryRef.current?.focus();
    });
    return () => document.removeEventListener('keydown', onKey);
  }, [card, close]);

  if (!card) return null;

  const engineColor = ENGINE_ACCENT[card.engine ?? 'other'];

  const handleBackdropClick = (ev: React.MouseEvent) => {
    if (ev.target === backdropRef.current) close();
  };

  const handleActionClick = (action: InspectorAction) => {
    if (action.disabled) return;
    const result = action.onClick();
    // Default behavior: close after firing. Return `false` to keep open.
    if (result !== false) close();
  };

  return createPortal(
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="card-inspector-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: isPrimed ? 'rgba(2, 6, 23, 0.32)' : 'rgba(2, 6, 23, 0.78)',
        backdropFilter: isPrimed ? 'none' : 'blur(6px)',
        // When primed, the backdrop is transparent to clicks so the user
        // can hit the lit zones below. The modal panel itself
        // re-enables pointer events so its buttons still work.
        pointerEvents: isPrimed ? 'none' : 'auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        animation: 'card-inspector-fade-in 120ms ease-out',
      }}
    >
      <style>{`
        @keyframes card-inspector-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes card-inspector-slide-in {
          from { transform: translateY(8px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>

      <div
        style={{
          maxWidth: 480,
          width: '100%',
          background: '#0f172a',
          border: `1px solid ${engineColor}`,
          borderRadius: 10,
          overflow: 'hidden',
          boxShadow: `0 20px 60px rgba(0, 0, 0, 0.6), 0 0 0 1px ${engineColor}30`,
          animation: 'card-inspector-slide-in 180ms ease-out',
          color: '#e5e7eb',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          // Re-enable clicks on the modal panel itself, even when the
          // backdrop has pointerEvents: none for the primed pass-through.
          pointerEvents: 'auto',
        }}
        onClick={(ev) => ev.stopPropagation()}
      >
        {card.artUrl && (
          <div
            style={{
              width: '100%',
              aspectRatio: '1 / 1',
              background: '#0a0f1c',
              backgroundImage: `url("${card.artUrl}")`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
            }}
            aria-hidden="true"
          />
        )}

        <div style={{ padding: '18px 22px 22px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
            <h2
              id="card-inspector-title"
              style={{
                margin: 0,
                fontFamily: 'JetBrains Mono, ui-monospace, monospace',
                fontSize: 18,
                fontWeight: 700,
                color: engineColor,
                letterSpacing: '-0.01em',
              }}
            >
              {card.name}
            </h2>
            {card.cost && (
              <span
                style={{
                  fontFamily: 'JetBrains Mono, ui-monospace, monospace',
                  fontSize: 12,
                  fontWeight: 600,
                  color: '#94a3b8',
                  padding: '2px 8px',
                  border: '1px solid #334155',
                  borderRadius: 4,
                }}
              >
                {card.cost}
              </span>
            )}
          </div>

          {(card.subtitle || card.stats) && (
            <div
              style={{
                marginTop: 4,
                fontFamily: 'JetBrains Mono, ui-monospace, monospace',
                fontSize: 11,
                color: '#94a3b8',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                display: 'flex',
                gap: 12,
              }}
            >
              {card.subtitle && <span>{card.subtitle}</span>}
              {card.stats && <span style={{ color: '#cbd5e1' }}>{card.stats}</span>}
            </div>
          )}

          {card.text && (
            <p
              style={{
                marginTop: 14,
                marginBottom: 0,
                fontSize: 13.5,
                lineHeight: 1.55,
                color: '#e2e8f0',
                whiteSpace: 'pre-wrap',
              }}
            >
              {card.text}
            </p>
          )}

          {card.flavor && (
            <p
              style={{
                marginTop: 10,
                marginBottom: 0,
                fontSize: 11.5,
                lineHeight: 1.5,
                color: '#94a3b8',
                fontStyle: 'italic',
              }}
            >
              {card.flavor}
            </p>
          )}

          {card.meta && card.meta.length > 0 && (
            <dl
              style={{
                marginTop: 14,
                marginBottom: 0,
                display: 'grid',
                gridTemplateColumns: 'max-content 1fr',
                columnGap: 12,
                rowGap: 4,
                fontFamily: 'JetBrains Mono, ui-monospace, monospace',
                fontSize: 11,
                color: '#94a3b8',
              }}
            >
              {card.meta.map((row) => (
                <span key={row.label} style={{ display: 'contents' }}>
                  <dt style={{ textTransform: 'uppercase', letterSpacing: '0.04em' }}>{row.label}</dt>
                  <dd style={{ margin: 0, color: '#e2e8f0' }}>{row.value}</dd>
                </span>
              ))}
            </dl>
          )}

          <div
            style={{
              marginTop: 22,
              display: 'flex',
              gap: 10,
              flexWrap: 'wrap',
              justifyContent: 'flex-end',
            }}
          >
            {actions.map((action, idx) => (
              <button
                key={action.label}
                ref={idx === 0 && action.variant !== 'secondary' ? primaryRef : undefined}
                type="button"
                onClick={() => handleActionClick(action)}
                disabled={action.disabled}
                title={action.disabledReason}
                style={actionStyles(action.variant ?? (idx === 0 ? 'primary' : 'secondary'), !!action.disabled)}
              >
                {action.icon && <span style={{ marginRight: 6, display: 'inline-block' }}>{action.icon}</span>}
                {action.label}
              </button>
            ))}
            <button
              type="button"
              onClick={close}
              style={actionStyles('secondary', false)}
            >
              Close
            </button>
          </div>

          {actions.find((a) => a.disabled)?.disabledReason && (
            <p
              style={{
                marginTop: 8,
                marginBottom: 0,
                fontSize: 11,
                color: '#fbbf24',
                fontFamily: 'JetBrains Mono, ui-monospace, monospace',
                textAlign: 'right',
              }}
            >
              {actions.find((a) => a.disabled)?.disabledReason}
            </p>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
