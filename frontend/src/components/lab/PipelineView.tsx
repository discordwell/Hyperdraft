/**
 * PipelineView — HD-CRIT-018 "Pipeline view" toggle on the board.
 *
 * Replaces the cards with their event stream. Four columns, one per
 * interceptor priority stage of the rules engine:
 *
 *     TRANSFORM → PREVENT → RESOLVE → REACT
 *
 * Each event line carries a timestamp, the event-type chip, a one-line
 * description, and the source object. Clicking a line highlights related
 * events across the columns. The active column auto-scrolls to the bottom
 * on new events.
 *
 * Engine reference: `src/engine/types.py` declares the four-stage
 * `InterceptorPriority` enum and the `EventType` vocabulary that backs
 * this view. The frontend receives events from the Socket.IO bridge as
 * `game_log` entries; this component takes them already-shaped as
 * `PipelineEvent`.
 */

import { useEffect, useMemo, useRef } from 'react';

export type PipelineStage = 'transform' | 'prevent' | 'resolve' | 'react';

export interface PipelineEvent {
  id: string;
  stage: PipelineStage;
  /** Engine event-type, e.g. "LIFE_CHANGE", "ZONE_CHANGE", "DAMAGE". */
  type: string;
  /** Source object name (or controller). Rendered in ink-3. */
  source: string;
  /** Single-line, human-readable description of the event. */
  description: string;
  /** Pseudo-clock string (mono). Free-form — "T1 +03", "00:04", etc. */
  t: string;
  /** Turn number for grouping / future replay slicing. */
  turn: number;
  /** Optional sibling id — events that fired together share this. */
  relatedId?: string;
}

export interface PipelineViewProps {
  events: PipelineEvent[];
  /** The current pipeline stage; highlights the column header. */
  activeStage?: PipelineStage;
  /** Fires when a user clicks an event row. */
  onSelect?: (eventId: string) => void;
  /** Controlled selected event id (otherwise PipelineView manages it itself). */
  selectedEventId?: string | null;
}

const STAGES: PipelineStage[] = ['transform', 'prevent', 'resolve', 'react'];

const STAGE_LABEL: Record<PipelineStage, string> = {
  transform: 'TRANSFORM',
  prevent: 'PREVENT',
  resolve: 'RESOLVE',
  react: 'REACT',
};

const STAGE_ACCENT: Record<PipelineStage, string> = {
  transform: 'var(--sodium)',
  prevent: 'var(--halt)',
  resolve: 'var(--plasma)',
  react: 'var(--acid)',
};

const STAGE_BLURB: Record<PipelineStage, string> = {
  transform: 'mutate the event',
  prevent: 'cancel the event',
  resolve: 'apply to state',
  react: 'queue new events',
};

export function PipelineView({
  events,
  activeStage,
  onSelect,
  selectedEventId: controlledSelectedId,
}: PipelineViewProps) {
  // Group events by stage. Stable order = insertion order = engine order.
  const byStage = useMemo(() => {
    const map: Record<PipelineStage, PipelineEvent[]> = {
      transform: [],
      prevent: [],
      resolve: [],
      react: [],
    };
    for (const ev of events) {
      if (ev.stage in map) {
        map[ev.stage].push(ev);
      }
    }
    return map;
  }, [events]);

  // Manage selection internally if uncontrolled — onSelect still fires
  // either way so the parent can hook into it.
  const selectedId = controlledSelectedId ?? null;
  const selectedEvent = useMemo(() => {
    if (!selectedId) return null;
    return events.find((e) => e.id === selectedId) ?? null;
  }, [events, selectedId]);

  // For visual cross-column highlighting: an event is "related" if it
  // shares the same `relatedId` as the selected event, or if it shares
  // the same source and turn (fallback when relatedId isn't set).
  const isRelated = (ev: PipelineEvent): boolean => {
    if (!selectedEvent) return false;
    if (ev.id === selectedEvent.id) return true;
    if (selectedEvent.relatedId && ev.relatedId === selectedEvent.relatedId) {
      return true;
    }
    return (
      ev.source === selectedEvent.source &&
      ev.turn === selectedEvent.turn &&
      ev.type === selectedEvent.type
    );
  };

  // Auto-scroll each column to the bottom whenever new events arrive
  // for that column. Refs per-stage so we don't yank columns the user
  // is reading mid-scroll.
  const columnRefs = useRef<Record<PipelineStage, HTMLDivElement | null>>({
    transform: null,
    prevent: null,
    resolve: null,
    react: null,
  });
  const lastCountRef = useRef<Record<PipelineStage, number>>({
    transform: 0,
    prevent: 0,
    resolve: 0,
    react: 0,
  });
  useEffect(() => {
    for (const stage of STAGES) {
      const next = byStage[stage].length;
      if (next > lastCountRef.current[stage]) {
        const el = columnRefs.current[stage];
        if (el) el.scrollTop = el.scrollHeight;
        lastCountRef.current[stage] = next;
      } else {
        lastCountRef.current[stage] = next;
      }
    }
  }, [byStage]);

  return (
    <div
      data-testid="pipeline-view"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 14,
        width: '100%',
        height: '100%',
        fontFamily: 'var(--font-sans)',
      }}
    >
      {STAGES.map((stage) => {
        const rows = byStage[stage];
        const isActive = activeStage === stage;
        return (
          <section
            key={stage}
            data-testid={`pipeline-column-${stage}`}
            style={{
              display: 'flex',
              flexDirection: 'column',
              border: '1px solid var(--rule)',
              background: 'var(--paper-2)',
              minHeight: 0,
            }}
          >
            {/* Sticky header — mono caps, sodium underline when active. */}
            <header
              style={{
                position: 'sticky',
                top: 0,
                padding: '12px 14px 10px',
                borderBottom: isActive
                  ? `2px solid ${STAGE_ACCENT[stage]}`
                  : '1px solid var(--rule)',
                background: 'var(--paper-2)',
                fontFamily: 'var(--font-mono)',
                color: 'var(--ink)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                gap: 8,
                zIndex: 1,
              }}
            >
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase',
                  color: isActive ? STAGE_ACCENT[stage] : 'var(--ink)',
                }}
              >
                {STAGE_LABEL[stage]}
              </span>
              <span
                style={{
                  fontSize: 10,
                  letterSpacing: '.1em',
                  textTransform: 'uppercase',
                  color: 'var(--ink-3)',
                }}
              >
                {rows.length.toString().padStart(2, '0')} · {STAGE_BLURB[stage]}
              </span>
            </header>

            {/* Event list. */}
            <div
              ref={(el) => {
                columnRefs.current[stage] = el;
              }}
              style={{
                flex: 1,
                overflowY: 'auto',
                minHeight: 0,
              }}
            >
              {rows.length === 0 ? (
                <div
                  style={{
                    padding: '14px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    letterSpacing: '.08em',
                    textTransform: 'uppercase',
                    color: 'var(--ink-3)',
                  }}
                >
                  No events
                </div>
              ) : (
                rows.map((ev) => {
                  const selected = ev.id === selectedId;
                  const related = isRelated(ev);
                  return (
                    <button
                      key={ev.id}
                      type="button"
                      data-testid={`pipeline-event-${ev.id}`}
                      data-related={related ? 'true' : 'false'}
                      data-selected={selected ? 'true' : 'false'}
                      onClick={() => onSelect?.(ev.id)}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr',
                        rowGap: 4,
                        width: '100%',
                        textAlign: 'left',
                        padding: '8px 10px 9px 12px',
                        borderTop: '1px solid var(--rule-2)',
                        borderLeft: `3px solid ${STAGE_ACCENT[stage]}`,
                        background: selected
                          ? `color-mix(in oklab, ${STAGE_ACCENT[stage]} 14%, var(--paper))`
                          : related
                            ? `color-mix(in oklab, ${STAGE_ACCENT[stage]} 7%, var(--paper-2))`
                            : 'var(--paper-2)',
                        color: 'var(--ink)',
                        cursor: 'pointer',
                        fontFamily: 'var(--font-sans)',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          gap: 8,
                          alignItems: 'center',
                          fontFamily: 'var(--font-mono)',
                          fontSize: 10.5,
                          letterSpacing: '.08em',
                          textTransform: 'uppercase',
                        }}
                      >
                        <span style={{ color: 'var(--ink-3)' }}>{ev.t}</span>
                        <span
                          style={{
                            color: 'var(--ink-2)',
                            border: '1px solid var(--rule)',
                            padding: '1px 5px',
                            background: 'var(--paper)',
                          }}
                        >
                          {ev.type}
                        </span>
                      </div>
                      <div
                        style={{
                          fontFamily: 'var(--font-sans)',
                          fontSize: 13,
                          lineHeight: 1.32,
                          color: 'var(--ink)',
                        }}
                      >
                        {ev.description}
                      </div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 10.5,
                          color: 'var(--ink-3)',
                          letterSpacing: '.06em',
                        }}
                      >
                        ← {ev.source}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
