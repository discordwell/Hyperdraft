/**
 * PokemonGatherer — lab-port library surface (buildplan follow-up 11b).
 *
 * Between-games library surface — full lab posture (paper / ink / sodium,
 * Instrument Serif headings, Geist Mono telemetry, hairline rules). Mirrors
 * the C2 Replays port: caption rail at top, ink-ruled masthead, `01 SECTION`
 * head with a sodium italic word in the title, hairline-ruled set rack, an
 * inline filter row, and the existing card-cell grid below it.
 *
 * This file is the slim composer; the body sections live in sibling files
 * under `components/pokemon-gatherer/Lab*` (mirrors the Deckbuilder pattern
 * from commit `42bcb0c8`). Per docs/design/brand.md, lab chrome wraps the
 * per-card identity (PokemonCardCell + PokemonCardDetailModal own their own
 * internal chrome).
 */

import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePokemonGathererStore } from '../stores/pokemonGathererStore';
import {
  LabSetRack,
  LabFilterBar,
  LabCardGrid,
  LabPaginationFooter,
  PokemonCardDetailModal,
} from '../components/pokemon-gatherer';

export function PokemonGatherer() {
  const navigate = useNavigate();
  const { sets, setsError, loadSets } = usePokemonGathererStore();

  useEffect(() => {
    loadSets();
  }, [loadSets]);

  const totalSetCards = useMemo(
    () => sets.reduce((sum, s) => sum + s.card_count, 0),
    [sets],
  );

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* ─── Caption rail (fixed crumb at top, like a printed-book header) */}
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
          zIndex: 10,
        }}
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-PKM-GATHERER</b>
        &nbsp;·&nbsp; POKÉMON &nbsp;·&nbsp; LIBRARY &nbsp;·&nbsp; v4.7
      </div>

      <main
        style={{
          maxWidth: 1240,
          margin: '0 auto',
          padding: '88px 56px 160px',
          position: 'relative',
        }}
      >
        {/* ─── Masthead ───────────────────────────────────────────────── */}
        <header
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'end',
            borderTop: '1.5px solid var(--ink)',
            borderBottom: '1.5px solid var(--ink)',
            padding: '18px 0 22px',
            marginBottom: 40,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                fontWeight: 500,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: 'var(--ink-2)',
              }}
            >
              HYPERDRAFT
            </span>
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: 34,
                color: 'var(--ink)',
                letterSpacing: '-.02em',
                lineHeight: 1,
              }}
            >
              / Pokémon{' '}
              <em style={{ fontStyle: 'italic', color: 'var(--ink)' }}>Gatherer</em>
            </span>
          </div>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '.06em',
              color: 'var(--ink-2)',
              textAlign: 'right',
            }}
          >
            v4.7 · {sets.length} sets · {totalSetCards.toLocaleString()} cards
          </span>
        </header>

        {/* ─── Section 01 · Browse — head ──────────────────────────────── */}
        <section>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '160px 1fr',
              gap: 48,
              paddingTop: 28,
              borderTop: '1px solid var(--rule)',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 500,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
                paddingTop: 6,
              }}
            >
              <span
                style={{
                  display: 'block',
                  fontFamily: 'var(--font-serif)',
                  fontSize: 32,
                  fontWeight: 400,
                  lineHeight: 1,
                  color: 'var(--sodium)',
                  marginBottom: 6,
                  letterSpacing: '-.02em',
                }}
              >
                01
              </span>
              Section
            </div>
            <div>
              <h2
                style={{
                  margin: 0,
                  fontFamily: 'var(--font-serif)',
                  fontSize: 38,
                  fontWeight: 400,
                  lineHeight: 1.05,
                  letterSpacing: '-.015em',
                  color: 'var(--ink)',
                }}
              >
                Pokémon{' '}
                <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>library</em>.
              </h2>
              <p
                style={{
                  margin: '8px 0 0',
                  fontFamily: 'var(--font-sans)',
                  fontSize: 14,
                  color: 'var(--ink-2)',
                  lineHeight: 1.5,
                }}
              >
                The SV starter pack plus Beyond crossover sets. Pick a set on
                the left, narrow with type / stage / HP, tap a card to read it
                whole.
              </p>
            </div>
          </div>

          {/* Sets-error band */}
          {setsError && (
            <div
              style={{
                marginTop: 24,
                border: '1px solid var(--halt)',
                background: 'color-mix(in oklab, var(--halt) 8%, transparent)',
                padding: '12px 16px',
                fontSize: 13,
                color: 'var(--halt)',
                fontFamily: 'var(--font-mono)',
                letterSpacing: '.04em',
              }}
            >
              {setsError}
            </div>
          )}

          {/* Sets rack + cards body */}
          <div
            style={{
              marginTop: 24,
              display: 'grid',
              gridTemplateColumns: '260px 1fr',
              gap: 20,
              alignItems: 'start',
            }}
          >
            <LabSetRack />

            <div style={{ minWidth: 0 }}>
              <LabFilterBar />
              <LabCardGrid footer={<LabPaginationFooter />} />
            </div>
          </div>
        </section>

        {/* ─── Footer ──────────────────────────────────────────────────── */}
        <footer
          style={{
            marginTop: 96,
            paddingTop: 28,
            borderTop: '1.5px solid var(--ink)',
            display: 'flex',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            letterSpacing: '.06em',
          }}
        >
          <span>uvicorn src.server.main:socket_app · port 8030</span>
          <button type="button" onClick={() => navigate('/gatherer')} style={footerLinkStyle}>
            MTG Gatherer →
          </button>
          <button type="button" onClick={() => navigate('/')} style={footerLinkStyle}>
            ← Lab
          </button>
        </footer>
      </main>

      <PokemonCardDetailModal />

      {/* Inline keyframes for the loading dot — scoped to this surface. */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.35; }
        }
      `}</style>
    </div>
  );
}

const footerLinkStyle: React.CSSProperties = {
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  color: 'var(--ink-3)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  letterSpacing: '.08em',
  textTransform: 'uppercase',
  padding: 0,
};

export default PokemonGatherer;
