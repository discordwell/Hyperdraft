/**
 * LabCardDetailModal — Gatherer card-detail modal (Phase C / follow-up 11a).
 *
 * Replaces the deleted `CardDetailModal.tsx` wrapper. The lab chrome here:
 *   - blurred ink-tint backdrop (`color-mix(var(--ink) 35%)` + `blur(4px)`),
 *   - hairline-ruled close button at the corner,
 *   - Escape-to-close + body-scroll lock side effects.
 *
 * The inner card face stays unchanged — that's `<SketchCardDetail>` with
 * its parchment / real art / mana symbols. Per `docs/design/brand.md`, the
 * lab chrome ends at the card body; per-card identity carries the rest.
 *
 * Renders only when `selectedCard` is non-null; null-otherwise so the
 * caller can mount it unconditionally without an extra guard.
 */

import { useEffect } from 'react';
import { useGathererStore } from '../../stores/gathererStore';
import { SketchCardDetail } from './SketchCardDetail';

export function LabCardDetailModal() {
  const { selectedCard, currentSet, selectCard } = useGathererStore();

  // Escape-to-close + body-scroll lock. Only active while the modal is open.
  useEffect(() => {
    if (!selectedCard) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') selectCard(null);
    };
    document.addEventListener('keydown', handleKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [selectedCard, selectCard]);

  if (!selectedCard) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Card detail: ${selectedCard.name}`}
      onClick={() => selectCard(null)}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'color-mix(in oklab, var(--ink) 35%, transparent)',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        zIndex: 40,
      }}
    >
      <div style={{ position: 'relative' }} onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          onClick={() => selectCard(null)}
          aria-label="Close card detail"
          style={{
            position: 'absolute',
            top: -14,
            right: -14,
            width: 32,
            height: 32,
            background: 'var(--paper)',
            color: 'var(--ink)',
            border: '1px solid var(--ink)',
            cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
            fontSize: 16,
            lineHeight: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
          }}
        >
          ×
        </button>
        <SketchCardDetail
          card={selectedCard}
          setCode={currentSet?.code}
          setName={currentSet?.name}
        />
      </div>
    </div>
  );
}
