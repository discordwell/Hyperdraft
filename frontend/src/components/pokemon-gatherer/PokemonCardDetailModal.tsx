/**
 * PokemonCardDetailModal
 *
 * Full-card overlay for the Pokemon gatherer. The modal *chrome* (scrim,
 * plate, close affordance, set caption) is lab posture — paper plate,
 * hairline rule, mono caption. The card body inside (`PKMCardDisplay`)
 * keeps its per-card identity and is untouched.
 */

import { useEffect } from 'react';
import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import { PKMCardDisplay } from './PKMCardDisplay';

export function PokemonCardDetailModal() {
  const { selectedCard, selectCard, currentSet } = usePokemonGathererStore();

  useEffect(() => {
    if (!selectedCard) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') selectCard(null);
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [selectedCard, selectCard]);

  if (!selectedCard) return null;

  return (
    <div
      onClick={() => selectCard(null)}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        background: 'color-mix(in oklab, var(--ink) 70%, transparent)',
        backdropFilter: 'blur(6px) saturate(1.05)',
        display: 'grid',
        placeItems: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: 440,
          maxHeight: '90vh',
          overflowY: 'auto',
          background: 'var(--paper)',
          border: '1px solid var(--ink)',
          boxShadow: '0 24px 64px -20px rgba(20,24,40,.45)',
          padding: 22,
          fontFamily: 'var(--font-sans)',
        }}
      >
        <button
          onClick={() => selectCard(null)}
          aria-label="Close"
          style={{
            position: 'absolute',
            top: -14,
            right: -14,
            width: 32,
            height: 32,
            background: 'var(--ink)',
            color: 'var(--paper)',
            border: '1px solid var(--ink)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
            fontSize: 14,
            lineHeight: 1,
          }}
        >
          ×
        </button>

        {currentSet && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--ink-3)',
              marginBottom: 10,
              paddingBottom: 8,
              borderBottom: '1px solid var(--rule)',
            }}
          >
            {currentSet.name} · {currentSet.code}
          </div>
        )}

        <PKMCardDisplay card={selectedCard} />
      </div>
    </div>
  );
}

export default PokemonCardDetailModal;
