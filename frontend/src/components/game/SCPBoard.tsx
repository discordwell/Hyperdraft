/**
 * SCPBoard — read-only board view for the SCP Containment TCG.
 *
 * Extracted from SCPGameView.tsx so that spectator + replay dispatch can
 * render an SCP match from a plain `gameState` payload (no socket hook
 * required). Mirrors the live-match SCPGameView visuals exactly: same
 * slate/cyan dossier palette per `docs/design/brand.md` ("each game keeps
 * its own identity"), same SitePanel + CardPanel + Stat tiles, same
 * Phase B card-art thumb (64px square left of the name, falls back to
 * just-name when no `image_url` is present).
 *
 * The board accepts:
 *   - `gameState`  — the full GameState payload
 *   - `playerId`   — the viewer's POV (spectator gets a stable seat id)
 *   - `readOnly`   — defaults to true; even when false, this board does NOT
 *                    render interactive controls. SCPGameView wraps the
 *                    board with its own action chrome (action buttons,
 *                    incident resolution, end turn).
 *
 * The board renders, for both seats:
 *   - SitePanel (secrecy / breach / archives / ethics / briefing / used)
 *   - active anomalies
 *   - contained archive
 *   - personnel + facilities + mandates
 *   - pending / sealed dossiers
 *   - top-of-page summary stats (assignments, anomalies, contained, incidents)
 *
 * Hand is intentionally hidden in read-only mode — spectators don't get to
 * see the live player's hand by default. SCPGameView re-uses the same
 * CardPanel inline for hand rendering with its own action buttons.
 */
import type { ReactNode } from 'react';
import type { CardData, GameState, PlayerData, SCPIncident, SCPSiteState } from '../../types';

function formatLabel(value: string | null | undefined): string {
  if (!value) return 'none';
  return value.replace(/_/g, ' ');
}

export function SCPStat({
  label,
  value,
  tone = 'text-slate-100',
}: {
  label: string;
  value: number | string;
  tone?: string;
}) {
  return (
    <div className="rounded border border-slate-700 bg-slate-950/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${tone}`}>{value}</div>
    </div>
  );
}

export function SCPSitePanel({ title, site }: { title: string; site: SCPSiteState }) {
  return (
    <section className="border border-slate-700 bg-slate-900/80 p-3">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-200">{title}</h2>
        <span className="text-xs text-slate-500">CLR {site.clearance ?? 0}</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <SCPStat label="Secrecy" value={site.secrecy ?? 0} tone="text-emerald-300" />
        <SCPStat label="Breach" value={site.breach ?? 0} tone="text-red-300" />
        <SCPStat label="Archives" value={site.archives ?? 0} tone="text-amber-300" />
        <SCPStat label="Ethics" value={site.ethics_debt ?? 0} tone="text-violet-300" />
        <SCPStat label="Briefing" value={site.briefing ?? 0} tone="text-cyan-300" />
        <SCPStat label="Used" value={`${site.assignments_used ?? 0}/${site.assignment_slots ?? 0}`} />
      </div>
    </section>
  );
}

export function SCPCardPanel({
  card,
  selected,
  onClick,
  children,
}: {
  card: CardData;
  selected?: boolean;
  onClick?: () => void;
  children?: ReactNode;
}) {
  const isSealed = card.scp_status === 'sealed';
  return (
    <div
      onClick={onClick}
      className={`border p-3 transition-colors ${
        selected ? 'border-cyan-400 bg-cyan-950/30' : 'border-slate-700 bg-slate-900/80'
      } ${onClick ? 'cursor-pointer hover:border-cyan-500' : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          {card.image_url && (
            <img
              src={card.image_url}
              alt={card.name}
              loading="lazy"
              className="h-16 w-16 flex-shrink-0 border border-slate-700 object-cover"
            />
          )}
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-100 truncate">{card.name}</div>
            <div className="mt-1 text-[11px] uppercase tracking-wide text-slate-500">
              {card.types.join(' / ')}
              {card.scp_status ? ` · ${card.scp_status}` : ''}
            </div>
          </div>
        </div>
        <div className="text-right text-xs text-slate-400 flex-shrink-0">
          <div>RT {card.scp_red_tape ?? 0}</div>
          <div>CL {card.scp_clearance ?? 0}</div>
        </div>
      </div>

      {card.types.includes('SCP_ANOMALY') && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded bg-slate-950 px-2 py-1 text-emerald-300">C {card.scp_containment ?? 0}</div>
          <div className="rounded bg-slate-950 px-2 py-1 text-amber-300">R {card.scp_curiosity ?? 0}</div>
          <div className="rounded bg-slate-950 px-2 py-1 text-red-300">H {card.scp_hazard ?? 0}</div>
        </div>
      )}

      {card.types.includes('SCP_PERSONNEL') && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded bg-slate-950 px-2 py-1 text-emerald-300">C {card.scp_skills?.contain ?? 0}</div>
          <div className="rounded bg-slate-950 px-2 py-1 text-amber-300">R {card.scp_skills?.research ?? 0}</div>
          <div className="rounded bg-slate-950 px-2 py-1 text-cyan-300">S {card.scp_skills?.suppress ?? 0}</div>
        </div>
      )}

      {(card.scp_mood || card.scp_bound_to || (card.scp_protocols?.length ?? 0) > 0 || isSealed) && (
        <div className="mt-2 space-y-1 text-xs text-slate-400">
          {isSealed && <div>Public tags: {(card.scp_public_tags || []).join(', ') || 'unknown'}</div>}
          {card.scp_mood && <div>Mood: {formatLabel(card.scp_mood)}</div>}
          {card.scp_bound_to && <div>Bound to: {card.scp_bound_to.slice(0, 8)}</div>}
          {(card.scp_protocols?.length ?? 0) > 0 && <div>Protocols: {card.scp_protocols?.map(formatLabel).join(', ')}</div>}
        </div>
      )}

      {!isSealed && (card.scp_rules?.length ?? 0) > 0 && (
        <ul className="mt-2 space-y-1 border-l-2 border-cyan-500/40 pl-2 text-xs leading-relaxed text-slate-200">
          {card.scp_rules?.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}
      {card.text && <p className="mt-2 text-[11px] italic leading-relaxed text-slate-500">{card.text}</p>}
      {children && <div className="mt-3 flex flex-wrap gap-2">{children}</div>}
    </div>
  );
}

export function SCPEmpty({ label }: { label: string }) {
  return (
    <div className="border border-dashed border-slate-800 px-3 py-6 text-center text-xs text-slate-600">
      {label}
    </div>
  );
}

export function SCPSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

export function SCPIncidentRow({ incident, index }: { incident: SCPIncident; index: number }) {
  return (
    <div className="flex items-center justify-between gap-3 border border-slate-700 bg-slate-900/80 px-3 py-2">
      <div>
        <div className="text-sm font-medium text-slate-200">
          {formatLabel(incident.name || `incident ${index + 1}`)}
        </div>
        <div className="text-xs text-slate-500">
          Turn {String(incident.turn ?? '-')} · breach {String(incident.breach ?? '-')}
        </div>
      </div>
    </div>
  );
}

export interface SCPBoardProps {
  gameState: GameState;
  playerId: string;
  /**
   * Defaults to true. Even when false, SCPBoard never renders the
   * interactive action chrome — SCPGameView wraps the board with its
   * own action buttons. The flag is kept for parity with future
   * spectator features (highlight active anomaly, etc.).
   */
  readOnly?: boolean;
}

/**
 * The pure rendering surface for an SCP match. SCPGameView composes its
 * action chrome (hand panel + action buttons + protocol picker + incident
 * resolver + end turn) around this board.
 */
export function SCPBoard({ gameState, playerId }: SCPBoardProps) {
  const typeHas = (card: CardData, type: string) => card.types.includes(type);

  const myPlayer: PlayerData | null = gameState.players[playerId] || null;
  const opponentId =
    Object.keys(gameState.players).find((id) => id !== playerId) || null;
  const opponentPlayer: PlayerData | null = opponentId
    ? gameState.players[opponentId] || null
    : null;

  const mySite: SCPSiteState = gameState.scp_sites?.[playerId] || {};
  const opponentSite: SCPSiteState = opponentId
    ? gameState.scp_sites?.[opponentId] || {}
    : {};

  const activeAnomalies = gameState.scp_anomalies?.[playerId] || [];
  const containedAnomalies = gameState.scp_contained?.[playerId] || [];
  const personnel = gameState.scp_personnel?.[playerId] || [];
  const facilities = gameState.scp_facilities?.[playerId] || [];
  const mandates = gameState.scp_mandates?.[playerId] || [];
  const opponentAnomalies = opponentId ? gameState.scp_anomalies?.[opponentId] || [] : [];
  const opponentContained = opponentId ? gameState.scp_contained?.[opponentId] || [] : [];
  const opponentPersonnel = opponentId ? gameState.scp_personnel?.[opponentId] || [] : [];

  // Pending dossiers (battlefield cards in 'pending' or 'sealed' status)
  const myDossiers = (gameState.battlefield || []).filter(
    (card) => card.controller === playerId && card.types.some((t) => t.startsWith('SCP_')),
  );
  const opponentDossiers = opponentId
    ? (gameState.battlefield || []).filter(
        (card) => card.controller === opponentId && card.types.some((t) => t.startsWith('SCP_')),
      )
    : [];

  const myPending = myDossiers.filter(
    (card) => card.scp_status === 'pending' || card.scp_status === 'sealed',
  );
  const opponentPending = opponentDossiers.filter(
    (card) => card.scp_status === 'pending' || card.scp_status === 'sealed',
  );

  const incidents = (gameState.scp_incidents?.[playerId] || []) as SCPIncident[];
  const assignmentSlots = gameState.scp_assignment_slots?.[playerId] ?? 0;

  // Silence the unused-vars lint for the helper we keep around for parity.
  void typeHas;

  return (
    <main className="grid gap-4 p-4 xl:grid-cols-[340px_minmax(0,1fr)_340px] text-slate-100 bg-slate-950">
      <aside className="space-y-4">
        <SCPSitePanel title={myPlayer?.name || 'Your Site'} site={mySite} />
      </aside>

      <section className="space-y-4">
        <div className="grid gap-3 md:grid-cols-4">
          <SCPStat label="Assignments" value={assignmentSlots} tone="text-cyan-300" />
          <SCPStat label="Active Anomalies" value={activeAnomalies.length} tone="text-red-300" />
          <SCPStat label="Contained" value={containedAnomalies.length} tone="text-emerald-300" />
          <SCPStat label="Incidents" value={incidents.length} tone="text-amber-300" />
        </div>

        <SCPSection title="Active Anomalies">
          {activeAnomalies.length === 0 && <SCPEmpty label="No active anomalies" />}
          {activeAnomalies.map((card) => (
            <SCPCardPanel key={card.id} card={card} />
          ))}
        </SCPSection>

        <div className="grid gap-4 lg:grid-cols-2">
          <SCPSection title="Available Personnel">
            {personnel.length === 0 && <SCPEmpty label="No active personnel" />}
            {personnel.map((card) => (
              <SCPCardPanel key={card.id} card={card}>
                <span className={`text-xs ${card.scp_exhausted ? 'text-red-300' : 'text-emerald-300'}`}>
                  {card.scp_exhausted ? 'Exhausted' : 'Ready'}
                </span>
              </SCPCardPanel>
            ))}
          </SCPSection>

          <SCPSection title="Incidents">
            {incidents.length === 0 && <SCPEmpty label="No active incidents" />}
            {incidents.map((incident, index) => (
              <SCPIncidentRow
                key={`${incident.name || 'incident'}-${index}`}
                incident={incident}
                index={index}
              />
            ))}
          </SCPSection>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <SCPSection title="Pending and Sealed Dossiers">
            {myPending.length === 0 && <SCPEmpty label="No queued dossiers" />}
            {myPending.map((card) => (
              <SCPCardPanel key={card.id} card={card} />
            ))}
          </SCPSection>

          <SCPSection title="Contained Archive">
            {containedAnomalies.length === 0 && <SCPEmpty label="No contained anomalies" />}
            {containedAnomalies.map((card) => (
              <SCPCardPanel key={card.id} card={card} />
            ))}
          </SCPSection>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <SCPSection title="Facilities">
            {facilities.length === 0 && <SCPEmpty label="No facilities active" />}
            {facilities.map((card) => (
              <SCPCardPanel key={card.id} card={card} />
            ))}
          </SCPSection>
          <SCPSection title="Mandates">
            {mandates.length === 0 && <SCPEmpty label="No mandate active" />}
            {mandates.map((card) => (
              <SCPCardPanel key={card.id} card={card} />
            ))}
          </SCPSection>
        </div>
      </section>

      <aside className="space-y-4">
        <SCPSitePanel title={opponentPlayer?.name || 'Opposing Site'} site={opponentSite} />

        <SCPSection title="Opposing Active Anomalies">
          {opponentAnomalies.length === 0 && <SCPEmpty label="No public active anomalies" />}
          {opponentAnomalies.map((card) => (
            <SCPCardPanel key={card.id} card={card} />
          ))}
        </SCPSection>

        <SCPSection title="Opposing Pending Dossiers">
          {opponentPending.length === 0 && <SCPEmpty label="No public queued dossiers" />}
          {opponentPending.map((card) => (
            <SCPCardPanel key={card.id} card={card} />
          ))}
        </SCPSection>

        <SCPSection title="Opposing Containment">
          {opponentContained.length === 0 && <SCPEmpty label="No contained anomalies" />}
          {opponentContained.map((card) => (
            <SCPCardPanel key={card.id} card={card} />
          ))}
        </SCPSection>

        <SCPSection title="Opposing Personnel">
          {opponentPersonnel.length === 0 && <SCPEmpty label="No personnel active" />}
          {opponentPersonnel.map((card) => (
            <SCPCardPanel key={card.id} card={card} />
          ))}
        </SCPSection>
      </aside>
    </main>
  );
}

export default SCPBoard;
