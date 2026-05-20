import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useSCPGame } from '../hooks/useSCPGame';
import { useGameStore } from '../stores/gameStore';
import { matchAPI } from '../services/api';
import { ChoiceModal } from '../components/actions/ChoiceModal';
import { usePendingChoice } from '../hooks/usePendingChoice';
import { GameViewLayout } from '../components/brand';
import type { CardData, SCPIncident, SCPSiteState } from '../types';

const PROTOCOLS = ['mirror_box', 'no_eye_contact', 'feed_it_lies', 'ritual_diagram'];
const MOODS = ['docile', 'agitated', 'cryptic', 'cooperative'];

function formatLabel(value: string | null | undefined): string {
  if (!value) return 'none';
  return value.replace(/_/g, ' ');
}

function Stat({ label, value, tone = 'text-slate-100' }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="rounded border border-slate-700 bg-slate-950/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${tone}`}>{value}</div>
    </div>
  );
}

function SitePanel({ title, site }: { title: string; site: SCPSiteState }) {
  return (
    <section className="border border-slate-700 bg-slate-900/80 p-3">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-200">{title}</h2>
        <span className="text-xs text-slate-500">CLR {site.clearance ?? 0}</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Secrecy" value={site.secrecy ?? 0} tone="text-emerald-300" />
        <Stat label="Breach" value={site.breach ?? 0} tone="text-red-300" />
        <Stat label="Archives" value={site.archives ?? 0} tone="text-amber-300" />
        <Stat label="Ethics" value={site.ethics_debt ?? 0} tone="text-violet-300" />
        <Stat label="Briefing" value={site.briefing ?? 0} tone="text-cyan-300" />
        <Stat label="Used" value={`${site.assignments_used ?? 0}/${site.assignment_slots ?? 0}`} />
      </div>
    </section>
  );
}

function CardPanel({
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
        <div>
          <div className="text-sm font-semibold text-slate-100">{card.name}</div>
          <div className="mt-1 text-[11px] uppercase tracking-wide text-slate-500">
            {card.types.join(' / ')}
            {card.scp_status ? ` · ${card.scp_status}` : ''}
          </div>
        </div>
        <div className="text-right text-xs text-slate-400">
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

      {card.text && <p className="mt-2 text-xs leading-relaxed text-slate-400">{card.text}</p>}
      {children && <div className="mt-3 flex flex-wrap gap-2">{children}</div>}
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="border border-dashed border-slate-800 px-3 py-6 text-center text-xs text-slate-600">{label}</div>;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function ActionButton({
  children,
  onClick,
  disabled,
  tone = 'neutral',
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  tone?: 'neutral' | 'danger' | 'good' | 'warn';
}) {
  const tones = {
    neutral: 'border-slate-600 text-slate-200 hover:bg-slate-800',
    danger: 'border-red-800 text-red-300 hover:bg-red-950/40',
    good: 'border-emerald-700 text-emerald-300 hover:bg-emerald-950/40',
    warn: 'border-amber-700 text-amber-300 hover:bg-amber-950/40',
  };
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      disabled={disabled}
      className={`rounded border px-2 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

function IncidentRow({
  incident,
  index,
  onResolve,
  disabled,
}: {
  incident: SCPIncident;
  index: number;
  onResolve: (index: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border border-slate-700 bg-slate-900/80 px-3 py-2">
      <div>
        <div className="text-sm font-medium text-slate-200">{formatLabel(incident.name || `incident ${index + 1}`)}</div>
        <div className="text-xs text-slate-500">Turn {String(incident.turn ?? '-')} · breach {String(incident.breach ?? '-')}</div>
      </div>
      <ActionButton onClick={() => onResolve(index)} disabled={disabled}>Resolve</ActionButton>
    </div>
  );
}

export function SCPGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    gameState,
    playerId,
    isConnected: _isConnected,
    myPlayer,
    opponentPlayer,
    mySite,
    opponentSite,
    hand,
    myPending,
    opponentPending,
    activeAnomalies,
    containedAnomalies,
    personnel,
    facilities,
    mandates,
    opponentAnomalies,
    opponentContained,
    opponentPersonnel,
    incidents,
    assignmentSlots,
    isMyTurn,
    isAnomaly,
    openDossier,
    revealDossier,
    research,
    contain,
    suppress,
    spendEthics,
    shiftMood,
    crossContain,
    memoryHole,
    applyProtocol,
    resolveIncident,
    endTurn,
    setError,
    error,
  } = useSCPGame();

  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string | null>(null);
  const [selectedStaffIds, setSelectedStaffIds] = useState<string[]>([]);
  const [selectedContainedId, setSelectedContainedId] = useState<string>('');

  const {
    pendingChoice,
    handleChoiceSubmit,
    isLoading: isSubmittingChoice,
  } = usePendingChoice();

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setGameState = useGameStore((state) => state.setGameState);
  const setConnection = useGameStore((state) => state.setConnection);

  useEffect(() => {
    if (!matchId) return;
    if (!storeMatchId || storeMatchId !== matchId) {
      const queryPlayerId = new URLSearchParams(location.search).get('player_id');
      if (!queryPlayerId) {
        navigate('/');
        return;
      }
      setConnection(matchId, queryPlayerId, false);
      return;
    }
    if (!gameState && storePlayerId) {
      matchAPI.getState(matchId, storePlayerId)
        .then(setGameState)
        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to fetch state'));
    }
  }, [matchId, storeMatchId, storePlayerId, gameState, location.search, navigate, setConnection, setGameState, setError]);

  const handleConcede = useCallback(async () => {
    if (!matchId || !playerId) return;
    if (!confirm('Concede?')) return;
    try {
      await matchAPI.concede(matchId, playerId);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to concede');
    }
  }, [matchId, playerId, navigate, setError]);

  const selectedAnomaly = useMemo(
    () => activeAnomalies.find((card) => card.id === selectedAnomalyId) || activeAnomalies[0] || null,
    [activeAnomalies, selectedAnomalyId],
  );

  useEffect(() => {
    if (!selectedAnomaly && selectedAnomalyId) setSelectedAnomalyId(null);
  }, [selectedAnomaly, selectedAnomalyId]);

  useEffect(() => {
    setSelectedStaffIds((ids) => ids.filter((id) => personnel.some((card) => card.id === id && !card.scp_exhausted)));
  }, [personnel]);

  const canAct = isMyTurn();
  const activeId = selectedAnomaly?.id || '';
  const selectedStaffCount = selectedStaffIds.length;

  const toggleStaff = (card: CardData) => {
    setSelectedStaffIds((ids) => (
      ids.includes(card.id) ? ids.filter((id) => id !== card.id) : [...ids, card.id]
    ));
  };

  if (!gameState || !playerId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="text-center">
          <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-slate-700 border-t-cyan-400" />
          <p className="text-sm uppercase tracking-widest text-slate-400">Opening dossier...</p>
        </div>
      </div>
    );
  }

  if (gameState.is_game_over) {
    const didWin = gameState.winner === playerId;
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="border border-slate-700 bg-slate-900 p-8 text-center">
          <p className={`mb-4 text-2xl font-semibold uppercase tracking-wide ${didWin ? 'text-emerald-300' : 'text-red-300'}`}>
            {didWin ? 'Archive Completed' : 'Site Lost'}
          </p>
          <button onClick={() => navigate('/')} className="rounded border border-slate-600 px-5 py-2 text-slate-200 hover:bg-slate-800">
            Return to Lobby
          </button>
        </div>
      </div>
    );
  }

  const opponentEntryScp =
    gameState?.players && Object.entries(gameState.players).find(([id]) => id !== playerId);
  const opponentNameScp = opponentEntryScp
    ? (opponentEntryScp[1] as { name?: string }).name
    : undefined;
  const meScp = gameState?.players?.[playerId] as { name?: string } | undefined;

  return (
    <GameViewLayout
      mode="scp"
      matchId={matchId}
      turn={gameState.turn_number}
      phase={canAct ? 'assignment' : 'awaiting'}
      opponentName={opponentNameScp}
      playerName={meScp?.name}
      onExit={handleConcede}
    >
    <div className="min-h-[calc(100vh-3.5rem)] bg-slate-950 text-slate-100">
      {error && <div className="border-b border-red-900 bg-red-950/40 px-4 py-2 text-sm text-red-300">{error}</div>}

      <main className="grid gap-4 p-4 xl:grid-cols-[340px_minmax(0,1fr)_340px]">
        <aside className="space-y-4">
          <SitePanel title={myPlayer?.name || 'Your Site'} site={mySite} />
          <div className="grid grid-cols-2 gap-2">
            <ActionButton onClick={() => spendEthics(2)} disabled={!canAct || (mySite.ethics_debt ?? 0) < 2} tone="warn">
              Spend Ethics
            </ActionButton>
            <ActionButton onClick={endTurn} disabled={!canAct} tone="good">End Turn</ActionButton>
          </div>

          <Section title={`Hand (${hand.length})`}>
            {hand.length === 0 && <Empty label="No cards in hand" />}
            {hand.map((card) => (
              <CardPanel key={card.id} card={card}>
                <ActionButton onClick={() => openDossier(card.id)} disabled={!canAct}>Open</ActionButton>
                {(card.scp_red_tape ?? 0) > 0 && (
                  <ActionButton onClick={() => openDossier(card.id, true)} disabled={!canAct} tone="warn">Fast-track</ActionButton>
                )}
                {isAnomaly(card) && (
                  <ActionButton onClick={() => openDossier(card.id, false, true)} disabled={!canAct}>Seal</ActionButton>
                )}
              </CardPanel>
            ))}
          </Section>
        </aside>

        <section className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <Stat label="Assignments" value={assignmentSlots} tone="text-cyan-300" />
            <Stat label="Active Anomalies" value={activeAnomalies.length} tone="text-red-300" />
            <Stat label="Contained" value={containedAnomalies.length} tone="text-emerald-300" />
            <Stat label="Incidents" value={incidents.length} tone="text-amber-300" />
          </div>

          <Section title="Active Anomalies">
            {activeAnomalies.length === 0 && <Empty label="No active anomalies" />}
            {activeAnomalies.map((card) => (
              <CardPanel
                key={card.id}
                card={card}
                selected={selectedAnomaly?.id === card.id}
                onClick={() => setSelectedAnomalyId(card.id)}
              >
                <ActionButton onClick={() => research(card.id, selectedStaffIds)} disabled={!canAct} tone="warn">
                  Research ({selectedStaffCount})
                </ActionButton>
                <ActionButton onClick={() => contain(card.id, selectedStaffIds)} disabled={!canAct} tone="good">
                  Contain ({selectedStaffCount})
                </ActionButton>
                <ActionButton onClick={() => suppress(card.id, selectedStaffIds)} disabled={!canAct}>
                  Suppress ({selectedStaffCount})
                </ActionButton>
              </CardPanel>
            ))}
          </Section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Available Personnel">
              {personnel.length === 0 && <Empty label="No active personnel" />}
              {personnel.map((card) => (
                <CardPanel
                  key={card.id}
                  card={card}
                  selected={selectedStaffIds.includes(card.id)}
                  onClick={() => !card.scp_exhausted && toggleStaff(card)}
                >
                  <span className={`text-xs ${card.scp_exhausted ? 'text-red-300' : 'text-emerald-300'}`}>
                    {card.scp_exhausted ? 'Exhausted' : selectedStaffIds.includes(card.id) ? 'Assigned' : 'Ready'}
                  </span>
                </CardPanel>
              ))}
            </Section>

            <Section title="Protocols and Site Tools">
              {selectedAnomaly ? (
                <div className="space-y-3 border border-slate-700 bg-slate-900/80 p-3">
                  <div className="text-sm font-medium text-slate-200">{selectedAnomaly.name}</div>
                  <div className="flex flex-wrap gap-2">
                    {PROTOCOLS.map((protocol) => (
                      <ActionButton key={protocol} onClick={() => applyProtocol(activeId, protocol)} disabled={!canAct}>
                        {formatLabel(protocol)}
                      </ActionButton>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {MOODS.map((mood) => (
                      <ActionButton key={mood} onClick={() => shiftMood(activeId, mood)} disabled={!canAct}>
                        {formatLabel(mood)}
                      </ActionButton>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <select
                      value={selectedContainedId}
                      onChange={(event) => setSelectedContainedId(event.target.value)}
                      className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
                    >
                      <option value="">Contained countermeasure</option>
                      {containedAnomalies.map((card) => <option key={card.id} value={card.id}>{card.name}</option>)}
                    </select>
                    <ActionButton
                      onClick={() => crossContain(selectedContainedId, activeId)}
                      disabled={!canAct || !selectedContainedId}
                      tone="good"
                    >
                      Bind
                    </ActionButton>
                  </div>
                </div>
              ) : (
                <Empty label="Select an active anomaly" />
              )}

              {incidents.length > 0 && (
                <div className="space-y-2">
                  {incidents.map((incident, index) => (
                    <IncidentRow
                      key={`${incident.name || 'incident'}-${index}`}
                      incident={incident}
                      index={index}
                      onResolve={resolveIncident}
                      disabled={!canAct}
                    />
                  ))}
                </div>
              )}
            </Section>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Pending and Sealed Dossiers">
              {myPending.length === 0 && <Empty label="No queued dossiers" />}
              {myPending.map((card) => (
                <CardPanel key={card.id} card={card}>
                  {card.scp_status === 'sealed' && (
                    <ActionButton onClick={() => revealDossier(card.id)} disabled={!canAct} tone="warn">Reveal</ActionButton>
                  )}
                  <ActionButton onClick={() => memoryHole(card.id)} disabled={!canAct} tone="danger">Memory hole</ActionButton>
                </CardPanel>
              ))}
            </Section>

            <Section title="Contained Archive">
              {containedAnomalies.length === 0 && <Empty label="No contained anomalies" />}
              {containedAnomalies.map((card) => (
                <CardPanel key={card.id} card={card}>
                  <ActionButton onClick={() => memoryHole(card.id)} disabled={!canAct} tone="danger">Memory hole</ActionButton>
                </CardPanel>
              ))}
            </Section>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Facilities">
              {facilities.length === 0 && <Empty label="No facilities active" />}
              {facilities.map((card) => <CardPanel key={card.id} card={card} />)}
            </Section>
            <Section title="Mandates">
              {mandates.length === 0 && <Empty label="No mandate active" />}
              {mandates.map((card) => <CardPanel key={card.id} card={card} />)}
            </Section>
          </div>
        </section>

        <aside className="space-y-4">
          <SitePanel title={opponentPlayer?.name || 'Opposing Site'} site={opponentSite} />

          <Section title="Opposing Active Anomalies">
            {opponentAnomalies.length === 0 && <Empty label="No public active anomalies" />}
            {opponentAnomalies.map((card) => <CardPanel key={card.id} card={card} />)}
          </Section>

          <Section title="Opposing Pending Dossiers">
            {opponentPending.length === 0 && <Empty label="No public queued dossiers" />}
            {opponentPending.map((card) => <CardPanel key={card.id} card={card} />)}
          </Section>

          <Section title="Opposing Containment">
            {opponentContained.length === 0 && <Empty label="No contained anomalies" />}
            {opponentContained.map((card) => <CardPanel key={card.id} card={card} />)}
          </Section>

          <Section title="Opposing Personnel">
            {opponentPersonnel.length === 0 && <Empty label="No personnel active" />}
            {opponentPersonnel.map((card) => <CardPanel key={card.id} card={card} />)}
          </Section>
        </aside>
      </main>
      {pendingChoice && (
        <ChoiceModal
          pendingChoice={pendingChoice}
          battlefield={[]}
          hand={[]}
          graveyard={{}}
          players={gameState.players}
          onSubmit={handleChoiceSubmit}
          isLoading={isSubmittingChoice}
        />
      )}
    </div>
    </GameViewLayout>
  );
}

export default SCPGameView;
