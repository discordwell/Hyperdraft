/**
 * ImportModal Component — lab posture (Phase C / buildplan item 9).
 *
 * Modal chrome for pasting a text decklist. Lab tokens — paper plate,
 * hairline rules, mono textarea, ink-outlined buttons.
 */

import { useState } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';

interface ImportModalProps {
  onClose: () => void;
}

export function ImportModal({ onClose }: ImportModalProps) {
  const { importDeck, isLoading, hasUnsavedChanges } = useDeckbuilderStore();
  const [deckText, setDeckText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleImport = async () => {
    if (!deckText.trim()) {
      setError('Please paste a deck list');
      return;
    }

    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Import a deck anyway?')) {
        return;
      }
    }

    try {
      setError(null);
      await importDeck(deckText);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import deck');
    }
  };

  const exampleFormat = `4 Lightning Bolt
4 Monastery Swiftspear
4 Goblin Guide
20 Mountain

Sideboard
2 Searing Blood
3 Smash to Smithereens`;

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
          padding: 24,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            marginBottom: 16,
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
              Import
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
              Import deck
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

        {error && (
          <div
            style={{
              padding: '10px 12px',
              border: '1px solid var(--halt)',
              background: 'color-mix(in oklab, var(--halt) 8%, transparent)',
              color: 'var(--halt)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              marginBottom: 14,
            }}
          >
            {error}
          </div>
        )}

        <label
          style={{
            display: 'block',
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
            marginBottom: 6,
          }}
        >
          Paste deck list
        </label>
        <textarea
          value={deckText}
          onChange={(e) => setDeckText(e.target.value)}
          placeholder={exampleFormat}
          style={{
            width: '100%',
            height: 240,
            padding: 12,
            background: 'var(--paper-2)',
            border: '1px solid var(--rule)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--ink)',
            outline: 'none',
            resize: 'vertical',
          }}
        />

        <div
          style={{
            marginTop: 12,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            lineHeight: 1.55,
            letterSpacing: '.04em',
          }}
        >
          <p style={{ margin: '0 0 4px' }}>Supported formats:</p>
          <ul style={{ margin: 0, paddingLeft: 14 }}>
            <li>4 Card Name</li>
            <li>4x Card Name</li>
            <li>Card Name x4</li>
          </ul>
          <p style={{ margin: '8px 0 0' }}>
            Use &ldquo;Sideboard&rdquo; on its own line to start the sideboard section.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
          <button
            onClick={onClose}
            style={{
              flex: 1,
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
          <button
            onClick={handleImport}
            disabled={isLoading || !deckText.trim()}
            style={{
              flex: 1,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              fontWeight: 500,
              letterSpacing: '.12em',
              textTransform: 'uppercase',
              padding: '10px 16px',
              background:
                isLoading || !deckText.trim() ? 'var(--ink-2)' : 'var(--ink)',
              color: 'var(--paper)',
              border: '1px solid var(--ink)',
              cursor: isLoading || !deckText.trim() ? 'not-allowed' : 'pointer',
              opacity: isLoading || !deckText.trim() ? 0.6 : 1,
            }}
          >
            {isLoading ? 'Importing…' : 'Import deck'}
          </button>
        </div>
      </div>
    </div>
  );
}
