/**
 * Gatherer — lab-posture MTG card-database browser (Phase C / follow-up 11a).
 *
 * HYPERDRAFT is a cabinet of TCGs; the Gatherer is a *between-games* surface
 * — players use it to browse cards while not in a match. Per
 * `docs/design/brand.md` and `docs/design/buildplan.md`, that makes it a
 * meta-frame and full lab posture applies (paper / ink / sodium, Instrument
 * Serif masthead, Geist Mono telemetry, hairline rules).
 *
 * Lab chrome ends and per-card identity begins inside the card grid — each
 * `<SketchCard>` cell renders the real MTG card art (served from
 * `/api/card-art/` or Scryfall's `art_crop`) plus the card's parchment
 * face. The lab chrome lives in the body's `Lab*` sub-components
 * (`LabFilterToolbar`, `LabSetSidebar`, `LabFilterBar`, `LabCardGrid`,
 * `LabCardDetailModal`) which were factored out of this page so the file
 * stays small and the chrome stays in one place. This file is now just
 * the caption rail + masthead + section head + footer composer.
 *
 * Mirrors the Deckbuilder lab-port pattern (`pages/Deckbuilder.tsx` +
 * `components/deckbuilder/*`): outer page is the composer, body sections
 * live in `components/gatherer/Lab*.tsx` and pull state directly from
 * `useGathererStore`.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGathererStore } from '../stores/gathererStore';
import {
  LabSetSidebar,
  LabFilterBar,
  LabFilterToolbar,
  LabCardGrid,
  LabCardDetailModal,
} from '../components/gatherer';

export function Gatherer() {
  const navigate = useNavigate();
  const { sets, loadSets } = useGathererStore();

  useEffect(() => {
    loadSets();
  }, [loadSets]);

  const totalCards = sets.reduce((sum, s) => sum + s.card_count, 0);

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* ─── Caption rail ─────────────────────────────────────────────── */}
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
          zIndex: 30,
        }}
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-GATHERER</b>
        &nbsp;·&nbsp; MTG &nbsp;·&nbsp; LIBRARY &nbsp;·&nbsp; v4.7
      </div>

      <main
        style={{
          maxWidth: 1320,
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
            <button
              type="button"
              onClick={() => navigate('/')}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 500,
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
                marginRight: 4,
              }}
              aria-label="Back to lab home"
            >
              ← Lab
            </button>
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
                fontStyle: 'italic',
                color: 'var(--ink)',
                letterSpacing: '-.02em',
                lineHeight: 1,
              }}
            >
              / Gatherer
            </span>
          </div>
          <span
            data-testid="gatherer-card-count-stamp"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '.06em',
              color: 'var(--ink-2)',
              textAlign: 'right',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            v4.7 · {totalCards.toLocaleString()} cards · {sets.length} sets
          </span>
        </header>

        {/* ─── Section 01 · Card library ──────────────────────────────── */}
        <section>
          <SectionHead
            num="01"
            title={
              <>
                Card <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>library</em>.
              </>
            }
            meta="Every standard-legal printing across the cabinet's MTG sets. Pick a set on the left; filter by color, type, rarity, or mana value."
          />

          {/* Toolbar — set-type chips + sort */}
          <LabFilterToolbar />

          {/* Main grid: sidebar + content */}
          <div
            style={{
              marginTop: 24,
              display: 'grid',
              gridTemplateColumns: '260px 1fr',
              gap: 24,
              alignItems: 'start',
            }}
          >
            <LabSetSidebar />

            {/* Right pane: filters + grid */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
              <LabFilterBar />
              <LabCardGrid />
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
          <span style={{ letterSpacing: '.1em', textTransform: 'uppercase' }}>
            HYPERDRAFT · GATHERER
          </span>
        </footer>
      </main>

      {/* ─── Modal — lab chrome around the SketchCardDetail face ──────── */}
      <LabCardDetailModal />

      {/* Local keyframes — keep scoped to this surface so the dot pulse
          doesn't leak into other lab pages that don't define `gatherer-pulse`. */}
      <style>{`
        @keyframes gatherer-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.32; }
        }
      `}</style>
    </div>
  );
}

// === Lab composition helpers =============================================
// Mirrors Home.tsx + Replays.tsx so the three between-games surfaces read as
// one continuous lab. Kept local — page-specific numbering / metadata.

function SectionHead({
  num,
  title,
  meta,
}: {
  num: string;
  title: React.ReactNode;
  meta?: React.ReactNode;
}) {
  return (
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
          {num}
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
          {title}
        </h2>
        {meta && (
          <p
            style={{
              margin: '8px 0 0',
              fontFamily: 'var(--font-sans)',
              fontSize: 14,
              color: 'var(--ink-2)',
              maxWidth: '70ch',
            }}
          >
            {meta}
          </p>
        )}
      </div>
    </div>
  );
}

export default Gatherer;
