/**
 * RulesSheet — Phase A2 rules-at-a-glance slide-over.
 *
 * Hit `?` anywhere in the app and the current engine's one-page rules
 * reference slides in from the right. Esc or click-outside to close. The
 * engine is derived from the React Router params (`mode`, `game`,
 * `matchId`-suffix), falling back to a `lastEngine` localStorage hint,
 * and finally to MTG.
 *
 * The panel is paper / ink / sodium per HD-PAL-01. The body renders a
 * tiny subset of markdown (h2, h3, p, strong, em, inline code) — that's
 * all the per-engine `.md` files use. No `react-markdown` dependency.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useQuestionMark } from '../../hooks/useQuestionMark';
import { LAB_ENGINES, getLabEngine, type LabEngineMeta } from './engineMeta';
import { type GameModeId } from '../brand/modes';

// Static markdown imports — Vite's `?raw` suffix returns the file body as a
// string at build time. This keeps the rules sheets in version control as
// plain `.md` files (easy to edit, easy to read in PR review) without a
// fetch round-trip.
import mtgMd from '../../data/rulesSheets/mtg.md?raw';
import hearthstoneMd from '../../data/rulesSheets/hearthstone.md?raw';
import pokemonMd from '../../data/rulesSheets/pokemon.md?raw';
import yugiohMd from '../../data/rulesSheets/yugioh.md?raw';
import minecraftMd from '../../data/rulesSheets/minecraft.md?raw';
import financeMd from '../../data/rulesSheets/finance.md?raw';
import depthsMd from '../../data/rulesSheets/depths.md?raw';
import scpMd from '../../data/rulesSheets/scp.md?raw';
import catsMd from '../../data/rulesSheets/cats.md?raw';

const SHEETS: Record<string, string> = {
  mtg: mtgMd,
  hearthstone: hearthstoneMd,
  pokemon: pokemonMd,
  yugioh: yugiohMd,
  minecraft: minecraftMd,
  finance: financeMd,
  depths: depthsMd,
  scp: scpMd,
  cats: catsMd,
};

const LAST_ENGINE_STORAGE_KEY = 'hd.lastEngine';

interface RulesSheetProps {
  /**
   * Explicit engine override. When provided, takes precedence over route
   * detection. Mainly used by tests + by power-user views that want to
   * peek at a non-current engine's rules.
   */
  engineId?: string;
  /**
   * Force-open the panel from a parent (testing + future header button).
   * When undefined, the panel manages its own open state via `?`.
   */
  initialOpen?: boolean;
}

// Order matches the URL→engine map below; checked in priority order.
const ROUTE_SUFFIX_TO_ENGINE: Array<[RegExp, GameModeId]> = [
  [/\/game\/[^/]+\/hs(?:\/|$)/, 'hearthstone'],
  [/\/game\/[^/]+\/pkm(?:\/|$)/, 'pokemon'],
  [/\/game\/[^/]+\/ygo(?:\/|$)/, 'yugioh'],
  [/\/game\/[^/]+\/mc(?:\/|$)/, 'minecraft'],
  [/\/game\/[^/]+\/fin(?:\/|$)/, 'finance'],
  [/\/game\/[^/]+\/depths(?:\/|$)/, 'depths'],
  [/\/game\/[^/]+\/scp(?:\/|$)/, 'scp'],
  // Cats lives on /cats and /game/:matchId/cats.
  [/\/game\/[^/]+\/cats(?:\/|$)/, 'cats'],
  [/^\/cats(?:\/|$)/, 'cats'],
  // Deckbuilder and per-engine card viewers carry the engine in :game.
  // We surface that below via useParams; keep this list focused on game
  // routes where the suffix is the only signal.
];

function engineFromPath(pathname: string): GameModeId | undefined {
  for (const [pattern, id] of ROUTE_SUFFIX_TO_ENGINE) {
    if (pattern.test(pathname)) return id;
  }
  return undefined;
}

function resolveEngine(
  override: string | undefined,
  params: Record<string, string | undefined>,
  pathname: string,
): LabEngineMeta {
  // 1. Explicit override (tests, future deep-link cases)
  if (override) {
    const hit = getLabEngine(override);
    if (hit) return hit;
  }
  // 2. Route params — `:game` from /deckbuilder/:game, `:mode` if any view
  //    adopts it later.
  for (const key of ['game', 'mode', 'engine']) {
    const v = params[key];
    if (!v) continue;
    const hit = getLabEngine(v);
    if (hit) return hit;
  }
  // 3. URL suffix patterns (/game/:id/hs, /cats, …)
  const fromPath = engineFromPath(pathname);
  if (fromPath) {
    const hit = getLabEngine(fromPath);
    if (hit) return hit;
  }
  // 4. localStorage hint from the user's last picked engine
  try {
    const last = window.localStorage.getItem(LAST_ENGINE_STORAGE_KEY);
    if (last) {
      const hit = getLabEngine(last);
      if (hit) return hit;
    }
  } catch {
    // SSR / sandboxed environments — just fall through
  }
  // 5. Default
  return LAB_ENGINES[0]; // MTG
}

// ────────────────────────────────────────────────────────────────────────
// Tiny markdown renderer
//
// The per-engine sheets only ever use:
//   ## h2, ### h3, plain paragraphs, **strong**, *em*, `code`, ---
// so we hand-roll a renderer instead of pulling in `react-markdown`.
// Lines are split, blank lines separate blocks, headings are detected by
// prefix, everything else is a paragraph. Inline parsing handles the
// three emphasis forms — order matters (strong before em to avoid the
// `*em*` from eating one of the `**` markers).
// ────────────────────────────────────────────────────────────────────────

type Block =
  | { kind: 'h2'; text: string }
  | { kind: 'h3'; text: string }
  | { kind: 'p'; text: string }
  | { kind: 'hr' };

function parseBlocks(md: string): Block[] {
  const blocks: Block[] = [];
  // Split paragraphs on blank lines. Headings still occupy their own paragraph.
  const chunks = md.replace(/\r\n/g, '\n').split(/\n\s*\n/);
  for (const chunk of chunks) {
    const trimmed = chunk.trim();
    if (!trimmed) continue;
    if (trimmed === '---') {
      blocks.push({ kind: 'hr' });
      continue;
    }
    if (trimmed.startsWith('## ')) {
      blocks.push({ kind: 'h2', text: trimmed.slice(3).trim() });
      continue;
    }
    if (trimmed.startsWith('### ')) {
      blocks.push({ kind: 'h3', text: trimmed.slice(4).trim() });
      continue;
    }
    // Collapse interior single newlines into spaces — paragraph wrap.
    blocks.push({ kind: 'p', text: trimmed.replace(/\n/g, ' ') });
  }
  return blocks;
}

// Tokenise inline markdown into <strong>/<em>/<code>/text. Returns an array
// of React-friendly nodes (string | JSX). Strong is parsed first so the
// double-asterisk doesn't get split by the single-asterisk pass.
function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let key = 0;
  let i = 0;
  while (i < text.length) {
    // **strong**
    if (text.startsWith('**', i)) {
      const end = text.indexOf('**', i + 2);
      if (end !== -1) {
        nodes.push(
          <strong key={key++} style={{ color: 'var(--ink)', fontWeight: 600 }}>
            {text.slice(i + 2, end)}
          </strong>,
        );
        i = end + 2;
        continue;
      }
    }
    // *em*
    if (text[i] === '*') {
      const end = text.indexOf('*', i + 1);
      if (end !== -1) {
        nodes.push(
          <em key={key++} style={{ fontStyle: 'italic', color: 'var(--sodium)' }}>
            {text.slice(i + 1, end)}
          </em>,
        );
        i = end + 1;
        continue;
      }
    }
    // `code`
    if (text[i] === '`') {
      const end = text.indexOf('`', i + 1);
      if (end !== -1) {
        nodes.push(
          <code
            key={key++}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.9em',
              background: 'var(--paper-3)',
              padding: '1px 5px',
              border: '1px solid var(--rule-2)',
            }}
          >
            {text.slice(i + 1, end)}
          </code>,
        );
        i = end + 1;
        continue;
      }
    }
    // Plain run — read until the next inline marker.
    let next = i + 1;
    while (next < text.length && !'*`'.includes(text[next])) next++;
    nodes.push(text.slice(i, next));
    i = next;
  }
  return nodes;
}

function MarkdownView({ md }: { md: string }) {
  const blocks = useMemo(() => parseBlocks(md), [md]);
  return (
    <>
      {blocks.map((b, ix) => {
        if (b.kind === 'h2') {
          return (
            <h2
              key={ix}
              style={{
                margin: '24px 0 6px',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 500,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
              }}
            >
              {b.text}
            </h2>
          );
        }
        if (b.kind === 'h3') {
          return (
            <h3
              key={ix}
              style={{
                margin: '18px 0 4px',
                fontFamily: 'var(--font-serif)',
                fontSize: 22,
                fontWeight: 400,
                letterSpacing: '-.015em',
                color: 'var(--ink)',
              }}
            >
              {b.text}
            </h3>
          );
        }
        if (b.kind === 'hr') {
          return (
            <hr
              key={ix}
              style={{
                margin: '20px 0',
                border: 0,
                borderTop: '1px solid var(--rule)',
              }}
            />
          );
        }
        return (
          <p
            key={ix}
            style={{
              margin: '0 0 14px',
              fontFamily: 'var(--font-sans)',
              fontSize: 14.5,
              lineHeight: 1.55,
              color: 'var(--ink-2)',
            }}
          >
            {renderInline(b.text)}
          </p>
        );
      })}
    </>
  );
}

// ────────────────────────────────────────────────────────────────────────
// RulesSheet panel
// ────────────────────────────────────────────────────────────────────────

export function RulesSheet({ engineId, initialOpen = false }: RulesSheetProps = {}) {
  const params = useParams();
  const location = useLocation();
  const [open, setOpen] = useState(initialOpen);
  const scrimRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  const engine = useMemo(
    () => resolveEngine(engineId, params, location.pathname),
    [engineId, params, location.pathname],
  );

  const md = SHEETS[engine.id] ?? SHEETS.mtg;

  const toggle = useCallback(() => setOpen((v) => !v), []);
  useQuestionMark(toggle);

  // Esc to close while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  // Focus the close button when the panel opens — gives screen readers
  // and keyboard users a sensible anchor, and Tab cycles through panel
  // content from there.
  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div
      ref={scrimRef}
      role="presentation"
      onClick={(e) => {
        if (e.target === scrimRef.current) setOpen(false);
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'color-mix(in oklab, var(--ink) 22%, transparent)',
        backdropFilter: 'blur(4px) saturate(1.02)',
        display: 'flex',
        justifyContent: 'flex-end',
      }}
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${engine.name} rules sheet`}
        data-testid="lab-rules-sheet"
        style={{
          width: 'min(480px, 100%)',
          height: '100vh',
          background: 'var(--paper)',
          borderLeft: '1px solid var(--rule)',
          boxShadow: '0 0 60px -20px rgba(20,24,40,.40)',
          overflowY: 'auto',
          padding: '28px 32px 40px',
          fontFamily: 'var(--font-sans)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <header
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            borderBottom: '1px solid var(--rule)',
            paddingBottom: 14,
            marginBottom: 6,
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                fontWeight: 500,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
              }}
            >
              {engine.code} · rules sheet
            </span>
            <h1
              style={{
                margin: 0,
                fontFamily: 'var(--font-serif)',
                fontSize: 30,
                fontWeight: 400,
                lineHeight: 1.05,
                letterSpacing: '-.015em',
                color: 'var(--ink)',
              }}
            >
              {engine.title}
            </h1>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close rules sheet"
            style={{
              border: '1px solid var(--rule)',
              background: 'var(--paper)',
              color: 'var(--ink-2)',
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              padding: '5px 10px',
              cursor: 'pointer',
            }}
          >
            esc
          </button>
        </header>

        <MarkdownView md={md} />

        <footer
          style={{
            marginTop: 28,
            paddingTop: 14,
            borderTop: '1px solid var(--rule)',
            display: 'flex',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '.12em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          <span>? · toggle</span>
          <span>HD-RULES-SHEET</span>
        </footer>
      </aside>
    </div>
  );
}

export default RulesSheet;
