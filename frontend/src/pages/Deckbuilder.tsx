/**
 * Deckbuilder Page — lab-port wrapper (Phase C / buildplan item 9).
 *
 * Per `docs/design/brand.md` "On the laboratory archetype": the Deckbuilder
 * is *ambiguous* — you're between matches but you're working in one specific
 * engine's vocabulary. The split is visual:
 *
 *   - LAB CHROME (ported here): the page caption rail + masthead strip, the
 *     deck-name / archetype / format / description inputs, the right-rail
 *     stats sidebar, the AI Assist / Hybrid Build footer, the modal chrome.
 *   - PER-ENGINE BODY (untouched): the card grid, filter pills, mana-symbol /
 *     energy-icon / per-engine vocabulary inside `<CardBrowser>` and `<DeckList>`.
 *     `<CardBrowser>` and `<DeckList>` keep their current chrome on purpose —
 *     when you're building an MTG deck the grid still looks MTG; the pokemon
 *     deck still surfaces energy types in pokemon colors.
 *
 * The seam lives at the `<main>` body — the lab-styled chrome wraps the
 * `<CardBrowser>` (left column) and the `<DeckList>` (inside the right
 * column under the lab-posture deck header + stats). Outer wrapper is
 * paper-on-paper; the per-engine sub-components remain in their current
 * vocabulary.
 *
 * HD-ART-04 reference proportions: 1fr search/grid on the left, 360px
 * deck rail on the right (room for the lab stats + deck list). Mirrors
 * the artboard's "spec-sheet chrome · real card art" caption.
 */

import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useDeckbuilderStore } from '../stores/deckbuilderStore';
import { CardBrowser } from '../components/deckbuilder/CardBrowser';
import { DeckPanel } from '../components/deckbuilder/DeckPanel';
import { AIAssistPanel } from '../components/deckbuilder/AIAssistPanel';
import { LoadDeckModal } from '../components/deckbuilder/LoadDeckModal';
import { ImportModal } from '../components/deckbuilder/ImportModal';
import { GAMES, GAME_LABELS } from '../types/deckbuilder';
import type { Game } from '../types/deckbuilder';

function isGame(value: string | undefined): value is Game {
  return !!value && (GAMES as readonly string[]).includes(value);
}

export function Deckbuilder() {
  const navigate = useNavigate();
  const { game: gameParam } = useParams<{ game?: string }>();
  const urlGame: Game = isGame(gameParam) ? gameParam : 'mtg';

  const {
    currentGame,
    error,
    hasUnsavedChanges,
    isSaving,
    newDeck,
    saveDeck,
    setGame,
    clearError,
  } = useDeckbuilderStore();

  const [showLoadModal, setShowLoadModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showExportText, setShowExportText] = useState<string | null>(null);

  // Sync game from URL → store. setGame handles loading saved decks + cards.
  useEffect(() => {
    if (currentGame !== urlGame) {
      setGame(urlGame);
    } else {
      // Same game on remount — kick off the initial fetches.
      const store = useDeckbuilderStore.getState();
      store.loadSavedDecks();
      store.searchCards();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlGame]);

  const handleGameChange = (next: Game) => {
    if (next === currentGame) return;
    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Switch games anyway?')) return;
    }
    navigate(`/deckbuilder/${next}`);
  };

  const handleNew = () => {
    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Create a new deck anyway?')) {
        return;
      }
    }
    newDeck();
  };

  const handleSave = async () => {
    await saveDeck();
  };

  const handleExport = async () => {
    const store = useDeckbuilderStore.getState();
    try {
      const text = await store.exportDeck();
      setShowExportText(text);
    } catch (err) {
      console.error('Export failed:', err);
    }
  };

  return (
    <div
      style={{
        background: 'var(--paper)',
        color: 'var(--ink)',
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* ─── Caption rail — printed-book header, top-centered ─────────── */}
      <div
        style={{
          position: 'fixed',
          top: 14,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          background: 'var(--paper)',
          padding: '6px 14px',
          border: '1px solid var(--rule)',
          zIndex: 40,
        }}
        data-testid="deckbuilder-caption"
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-DECKBUILDER</b>
        &nbsp;·&nbsp; LIBRARY &nbsp;·&nbsp; v4.7
      </div>

      {/* ─── Lab masthead — top bar with lobby link + actions =========== */}
      <header
        style={{
          borderTop: '1.5px solid var(--ink)',
          borderBottom: '1.5px solid var(--ink)',
          padding: '18px 32px',
          marginTop: 44,
          background: 'var(--paper)',
          display: 'flex',
          alignItems: 'center',
          gap: 18,
          flexWrap: 'wrap',
        }}
        data-testid="deckbuilder-masthead"
      >
        <button
          onClick={() => navigate('/')}
          style={labMonoLinkStyle}
          aria-label="Back to lobby"
        >
          ← Lobby
        </button>

        <h1
          style={{
            margin: 0,
            fontFamily: 'var(--font-serif)',
            fontSize: 28,
            fontWeight: 400,
            letterSpacing: '-.015em',
            color: 'var(--ink)',
          }}
        >
          Deckbuilder
        </h1>

        <span
          aria-hidden
          style={{
            display: 'inline-block',
            width: 1,
            height: 22,
            background: 'var(--rule)',
            margin: '0 4px',
          }}
        />

        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.12em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          Engine
          <select
            value={currentGame}
            onChange={(e) => handleGameChange(e.target.value as Game)}
            style={labSelectStyle}
            aria-label="Game"
          >
            {GAMES.map((g) => (
              <option key={g} value={g}>
                {GAME_LABELS[g]}
              </option>
            ))}
          </select>
        </label>

        {/* Action cluster on the right */}
        <div
          style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          {hasUnsavedChanges && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.1em',
                color: 'var(--sodium)',
                textTransform: 'uppercase',
                marginRight: 4,
              }}
            >
              · unsaved
            </span>
          )}
          <button onClick={handleNew} style={labButtonStyle()}>
            New
          </button>
          <button onClick={() => setShowLoadModal(true)} style={labButtonStyle()}>
            Load
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            style={labPrimaryButtonStyle(isSaving)}
          >
            {isSaving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </header>

      {/* ─── Error Banner — lab posture, halt accent =================== */}
      {error && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 32px',
            background: 'color-mix(in oklab, var(--halt) 8%, transparent)',
            borderBottom: '1px solid var(--halt)',
            fontFamily: 'var(--font-mono)',
            fontSize: 11.5,
            color: 'var(--halt)',
            letterSpacing: '.06em',
          }}
        >
          <span>{error}</span>
          <button
            onClick={clearError}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--halt)',
              cursor: 'pointer',
              fontSize: 16,
              lineHeight: 1,
              padding: '0 4px',
            }}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {/* ─── Main Content ─────────────────────────────────────────────
            The seam: lab-paper border + paper-2 panels wrap two columns.
            The LEFT column hosts `<CardBrowser>` whose interior (search,
            filter pills with W/U/B/R/G semantics, card grid cells with
            real art) stays per-engine. The RIGHT column is the lab-posture
            deck rail — header inputs + stats are ported tokens; the
            `<DeckList>` block underneath keeps per-engine card rows.
            ============================================================== */}
      <div
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: '1fr 360px',
          minHeight: 0,
          overflow: 'hidden',
        }}
        data-testid="deckbuilder-body"
      >
        {/* LEFT — per-engine body. Outer panel uses lab paper-2 background +
            a hairline rule so the seam reads visually, but the interior
            (CardBrowser → SearchBar + FilterPanel + CardGrid) is untouched. */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--paper-2)',
            borderRight: '1px solid var(--rule)',
            minHeight: 0,
            overflow: 'hidden',
          }}
          data-testid="deckbuilder-grid-section"
        >
          <CardBrowser />
        </div>

        {/* RIGHT — lab-posture deck rail. Header (name + archetype +
            format + description) and stats sidebar are ported to lab
            tokens; the deck-list block delegates to <DeckPanel> which
            now renders its lab-styled header + the per-engine deck list. */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--paper-2)',
            minHeight: 0,
            overflow: 'hidden',
          }}
          data-testid="deckbuilder-deck-rail"
        >
          <DeckPanel />
        </div>
      </div>

      {/* ─── AI Assist + Hybrid Build footer — lab posture ============= */}
      <AIAssistPanel
        onImport={() => setShowImportModal(true)}
        onExport={handleExport}
      />

      {showLoadModal && <LoadDeckModal onClose={() => setShowLoadModal(false)} />}
      {showImportModal && <ImportModal onClose={() => setShowImportModal(false)} />}

      {/* Export Text Modal — lab posture: paper plate, ink-outlined */}
      {showExportText && (
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
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
              }}
            >
              Export
            </span>
            <h2
              style={{
                margin: '6px 0 16px',
                fontFamily: 'var(--font-serif)',
                fontSize: 24,
                fontWeight: 400,
                letterSpacing: '-.015em',
                color: 'var(--ink)',
              }}
            >
              Export deck
            </h2>
            <textarea
              readOnly
              value={showExportText}
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
              onClick={(e) => (e.target as HTMLTextAreaElement).select()}
            />
            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 8,
                marginTop: 16,
              }}
            >
              <button
                onClick={() => navigator.clipboard.writeText(showExportText)}
                style={labPrimaryButtonStyle(false)}
              >
                Copy to clipboard
              </button>
              <button onClick={() => setShowExportText(null)} style={labButtonStyle()}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// === Lab style helpers — kept inline (Deckbuilder-local) ===============

const labMonoLinkStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  fontWeight: 500,
  letterSpacing: '.12em',
  textTransform: 'uppercase',
  color: 'var(--ink-3)',
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  padding: '4px 0',
};

const labSelectStyle: React.CSSProperties = {
  background: 'var(--paper)',
  color: 'var(--ink)',
  border: '1px solid var(--rule)',
  padding: '6px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  outline: 'none',
};

function labButtonStyle(): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    padding: '8px 14px',
    background: 'var(--paper)',
    color: 'var(--ink)',
    border: '1px solid var(--ink)',
    cursor: 'pointer',
  };
}

function labPrimaryButtonStyle(loading: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    padding: '8px 16px',
    background: loading ? 'var(--ink-2)' : 'var(--ink)',
    color: 'var(--paper)',
    border: '1px solid var(--ink)',
    cursor: loading ? 'wait' : 'pointer',
    opacity: loading ? 0.7 : 1,
  };
}

export default Deckbuilder;
