/**
 * LabSetSidebar — Gatherer set rack (Phase C / follow-up 11a).
 *
 * The lab-styled, hairline-ruled list of MTG sets that lives in the left
 * column of the Gatherer body. Sets group under their type heading
 * (`standard`, `universes_beyond`, `custom`) unless a single set type is
 * already filtered, in which case the rack flattens to one list.
 *
 * Replaces the deleted `SetSidebar.tsx` wrapper — the chrome is inlined
 * here in lab posture (paper-2 panel, mono eyebrow, serif set names) so
 * the prior slate/zinc tailwind chrome doesn't leak back in. Reads
 * straight from `useGathererStore`; emits `selectSet` on click.
 */

import { useMemo } from 'react';
import { useGathererStore } from '../../stores/gathererStore';
import { SET_TYPE_INFO } from '../../types/gatherer';
import type { SetInfo, SetType } from '../../types/gatherer';
import { Eyebrow } from './_labChrome';

const SET_TYPE_ORDER: SetType[] = ['standard', 'universes_beyond', 'custom'];

export function LabSetSidebar() {
  const {
    sets,
    setsLoading,
    setsError,
    currentSet,
    setTypeFilter,
    selectSet,
  } = useGathererStore();

  // Group sets by type for the sidebar rack
  const groupedSets = useMemo(() => {
    return sets.reduce(
      (acc, set) => {
        const t = (set.set_type as SetType) ?? 'custom';
        if (!acc[t]) acc[t] = [];
        acc[t].push(set);
        return acc;
      },
      {} as Record<SetType, SetInfo[]>,
    );
  }, [sets]);

  return (
    <aside
      data-testid="gatherer-set-rack"
      style={{
        border: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        minHeight: 420,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          padding: '12px 14px',
          borderBottom: '1px solid var(--rule)',
        }}
      >
        <Eyebrow>Sets</Eyebrow>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {sets.length}
        </span>
      </div>

      {setsLoading && (
        <div
          style={{
            padding: '24px 14px',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: 'var(--sodium)',
              animation: 'gatherer-pulse 1.6s ease-in-out infinite',
            }}
          />
          Loading sets…
        </div>
      )}

      {setsError && (
        <div
          style={{
            margin: 14,
            padding: '10px 12px',
            border: '1px solid var(--halt)',
            background: 'color-mix(in oklab, var(--halt) 8%, transparent)',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--halt)',
          }}
        >
          {setsError}
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto', maxHeight: '70vh' }}>
        {setTypeFilter ? (
          <SetList
            sets={sets}
            currentCode={currentSet?.code ?? null}
            onSelect={selectSet}
          />
        ) : (
          SET_TYPE_ORDER.map((t) => {
            const list = groupedSets[t] || [];
            if (list.length === 0) return null;
            return (
              <div key={t}>
                <div
                  style={{
                    padding: '12px 14px 6px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    fontWeight: 500,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: 'var(--ink-3)',
                    borderTop: '1px solid var(--rule-2)',
                  }}
                >
                  {SET_TYPE_INFO[t].label}
                </div>
                <SetList
                  sets={list}
                  currentCode={currentSet?.code ?? null}
                  onSelect={selectSet}
                />
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

// === Sidebar set list ====================================================

function SetList({
  sets,
  currentCode,
  onSelect,
}: {
  sets: SetInfo[];
  currentCode: string | null;
  onSelect: (code: string) => void;
}) {
  return (
    <div role="list">
      {sets.map((s) => {
        const active = s.code === currentCode;
        return (
          <button
            key={s.code}
            type="button"
            role="listitem"
            onClick={() => onSelect(s.code)}
            aria-current={active ? 'true' : undefined}
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr auto',
              gap: 8,
              alignItems: 'baseline',
              width: '100%',
              textAlign: 'left',
              padding: '10px 14px',
              border: 'none',
              borderTop: '1px solid var(--rule-2)',
              background: active
                ? 'color-mix(in oklab, var(--sodium) 12%, var(--paper))'
                : 'transparent',
              color: 'var(--ink)',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
            }}
            onMouseEnter={(ev) => {
              if (!active) {
                ev.currentTarget.style.background =
                  'color-mix(in oklab, var(--sodium) 6%, var(--paper-2))';
              }
            }}
            onMouseLeave={(ev) => {
              if (!active) {
                ev.currentTarget.style.background = 'transparent';
              }
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: 15,
                  lineHeight: 1.2,
                  color: 'var(--ink)',
                  letterSpacing: '-.01em',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {s.name}
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  letterSpacing: '.1em',
                  textTransform: 'uppercase',
                  color: active ? 'var(--sodium)' : 'var(--ink-3)',
                  marginTop: 2,
                }}
              >
                {s.code}
              </div>
            </div>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--ink-3)',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {s.card_count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
