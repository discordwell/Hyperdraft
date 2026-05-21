/**
 * LoadDeckModal Component — lab posture (Phase C / buildplan item 9).
 *
 * Modal chrome ports to lab tokens (paper plate, hairline rules, mono
 * captions, ink-outlined buttons). The colour pips for MTG decks keep
 * their W/U/B/R/G hexes — per-engine vocabulary.
 */

import { useEffect } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { COLORS, type ColorSymbol } from '../../types/deckbuilder';

interface LoadDeckModalProps {
  onClose: () => void;
}

export function LoadDeckModal({ onClose }: LoadDeckModalProps) {
  const {
    savedDecks,
    loadSavedDecks,
    loadDeck,
    deleteDeck,
    isLoading,
    hasUnsavedChanges,
  } = useDeckbuilderStore();

  useEffect(() => {
    loadSavedDecks();
  }, [loadSavedDecks]);

  const handleLoad = async (deckId: string) => {
    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Load a different deck anyway?')) {
        return;
      }
    }
    await loadDeck(deckId);
    onClose();
  };

  const handleDelete = async (deckId: string, deckName: string) => {
    if (confirm(`Delete deck "${deckName}"? This cannot be undone.`)) {
      await deleteDeck(deckId);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'color-mix(in oklab, var(--ink) 30%, transparent)',
        backdropFilter: 'blur(2px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 60,
        padding: 16,
      }}
    >
      <div
        style={{
          background: 'var(--paper)',
          border: '1px solid var(--rule)',
          boxShadow: 'var(--shadow-plate)',
          maxWidth: 560,
          width: '100%',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          padding: 24,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            marginBottom: 18,
            paddingBottom: 12,
            borderBottom: '1px solid var(--rule)',
          }}
        >
          <div>
            <span
              style={{
                display: 'block',
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
                marginBottom: 4,
              }}
            >
              Library
            </span>
            <h2
              style={{
                margin: 0,
                fontFamily: 'var(--font-serif)',
                fontSize: 24,
                fontWeight: 400,
                letterSpacing: '-.015em',
                color: 'var(--ink)',
              }}
            >
              Load deck
            </h2>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--ink-3)',
              fontSize: 22,
              lineHeight: 1,
              cursor: 'pointer',
              padding: 4,
            }}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {isLoading ? (
          <div
            style={{
              padding: 32,
              textAlign: 'center',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.12em',
              color: 'var(--ink-3)',
              textTransform: 'uppercase',
            }}
          >
            Loading…
          </div>
        ) : savedDecks.length === 0 ? (
          <div
            style={{
              padding: 32,
              textAlign: 'center',
              fontFamily: 'var(--font-sans)',
              fontSize: 13,
              color: 'var(--ink-3)',
              lineHeight: 1.5,
            }}
          >
            No saved decks yet. Create a new deck to start.
          </div>
        ) : (
          <div style={{ overflowY: 'auto', flex: 1, margin: '0 -4px', padding: '0 4px' }}>
            {savedDecks.map((deck) => (
              <div
                key={deck.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 14px',
                  borderBottom: '1px solid var(--rule-2)',
                  background: 'var(--paper)',
                }}
              >
                <div
                  style={{ flex: 1, cursor: 'pointer' }}
                  onClick={() => handleLoad(deck.id)}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      marginBottom: 4,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: 'var(--font-serif)',
                        fontSize: 17,
                        fontWeight: 400,
                        color: 'var(--ink)',
                        letterSpacing: '-.005em',
                      }}
                    >
                      {deck.name}
                    </span>
                    <div style={{ display: 'flex', gap: 2 }}>
                      {deck.colors.map((color) => {
                        const colorKey = color as ColorSymbol;
                        return (
                          <div
                            key={color}
                            style={{
                              width: 14,
                              height: 14,
                              borderRadius: '50%',
                              border: '1px solid var(--rule)',
                              background:
                                COLORS[colorKey]?.hex || 'var(--ink-3)',
                            }}
                            title={COLORS[colorKey]?.name}
                          />
                        );
                      })}
                    </div>
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--ink-3)',
                      letterSpacing: '.04em',
                    }}
                  >
                    {deck.archetype} · {deck.mainboard_count} cards · {deck.format}
                  </div>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(deck.id, deck.name);
                  }}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    letterSpacing: '.1em',
                    textTransform: 'uppercase',
                    color: 'var(--halt)',
                    background: 'transparent',
                    border: '1px solid transparent',
                    padding: '4px 8px',
                    cursor: 'pointer',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--halt)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'transparent';
                  }}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--rule)' }}>
          <button
            onClick={onClose}
            style={{
              width: '100%',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              fontWeight: 500,
              letterSpacing: '.12em',
              textTransform: 'uppercase',
              padding: '10px 16px',
              background: 'var(--paper)',
              color: 'var(--ink)',
              border: '1px solid var(--ink)',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
