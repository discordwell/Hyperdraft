import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useSCPGame } from '../hooks/useSCPGame';
import { useGameStore } from '../stores/gameStore';
import { matchAPI } from '../services/api';
import { ChoiceModal } from '../components/actions/ChoiceModal';
import { usePendingChoice } from '../hooks/usePendingChoice';
import { GameViewLayout } from '../components/brand';
import { useDiscoveryStore } from '../stores/discoveryStore';
import {
  SCPCardPanel,
  SCPEmpty,
  SCPSection,
  SCPSitePanel,
  SCPStat,
} from '../components/game/SCPBoard';
import { useCardInspector } from '../hooks/useCardInspector';
import type { InspectorAction } from '../hooks/useCardInspector';
import { useHandCard } from '../hooks/useHandCard';
import { useCardZone } from '../hooks/useCardZone';
import ZoneHighlight from '../components/cards/ZoneHighlight';
import type { CardData, SCPIncident } from '../types';

// ---- Shared card-zone primitive ----------------------------------------
//
// SCP wires two drop zones for the viewer's side:
//   - SCP_ACTIVE_ANOMALY_ZONE — the universal "Open" intake. Any dossier
//     (anomaly, personnel, facility, etc.) can be dropped here; the engine
//     decides whether it actually enters as an active anomaly or routes
//     through Pending. This mirrors the existing inline "Open" button.
//   - SCP_CONTAINED_ZONE — anomaly-only "Seal" lane. Dropping fires the
//     same action as the inline "Seal" button (`openDossier(card.id,
//     false, true)`).
//
// Drop dispatches the FIRST step of the play; any follow-up flow (protocol
// picker, personnel assignment) is still driven by the existing chrome
// below — same "drop then engine resolves" pattern as Clankers.

const SCP_ENGINE_ID = 'scp';
const SCP_ACCENT = '#f97316'; // orange — anomaly warning
const SCP_ACTIVE_ANOMALY_ZONE = 'scp-active-anomaly-me';
const SCP_CONTAINED_ZONE = 'scp-contained-me';

// SCPGameView is the *interactive* SCP match page. The pure visual primitives
// (SCPSitePanel / SCPCardPanel / SCPSection / SCPStat / SCPEmpty) live in
// `components/game/SCPBoard.tsx` so spectator + replay dispatch can render
// the same slate/cyan dossier identity without depending on `useSCPGame`.
// This page composes those primitives with its own action chrome (hand,
// action buttons, protocol picker, incident resolver, end turn).

const PROTOCOLS = ['mirror_box', 'no_eye_contact', 'feed_it_lies', 'ritual_diagram'];
const MOODS = ['docile', 'agitated', 'cryptic', 'cooperative'];

function formatLabel(value: string | null | undefined): string {
  if (!value) return 'none';
  return value.replace(/_/g, ' ');
}

/**
 * Compute the legal drop-zone IDs for a hand card. Empty when the viewer
 * can't act — that keeps the zones dim and the card non-draggable.
 *
 * Anomaly cards get both lanes: the universal Open lane (active anomaly
 * intake) and the anomaly-only Seal lane (contained archive). Non-anomaly
 * cards only get the Open lane — the engine handles whether they actually
 * land in Active or in Pending after the play resolves.
 */
function scpValidZonesFor(canAct: boolean, isAnomalyCard: boolean): string[] {
  if (!canAct) return [];
  if (isAnomalyCard) return [SCP_ACTIVE_ANOMALY_ZONE, SCP_CONTAINED_ZONE];
  return [SCP_ACTIVE_ANOMALY_ZONE];
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

/**
 * Hand-card wrapper that adds drag/click-prime behavior to an SCPCardPanel.
 * The card stays click-to-inspect via `onInspect` (the inspector's Play
 * actions are unchanged) — this only adds the secondary drag + prime path
 * so the user can drop directly onto the Active or Contained zone instead
 * of having to roundtrip through the modal.
 */
function SCPHandDossier({
  card,
  canAct,
  isAnomalyCard,
  onInspect,
  children,
}: {
  card: CardData;
  canAct: boolean;
  isAnomalyCard: boolean;
  onInspect: () => void;
  children?: ReactNode;
}) {
  const validZones = scpValidZonesFor(canAct, isAnomalyCard);
  const handCard = useHandCard({
    cardId: card.id,
    cardName: card.name,
    engineId: SCP_ENGINE_ID,
    accent: SCP_ACCENT,
    validZones,
    disabled: !canAct,
  });
  return (
    <div
      draggable={handCard.draggable}
      onDragStart={handCard.onDragStart}
      onDragEnd={handCard.onDragEnd}
      style={{
        cursor: handCard.draggable ? 'grab' : undefined,
        transform: handCard.isPrimed ? 'translateY(-6px)' : undefined,
        filter: handCard.isPrimed ? `drop-shadow(0 0 8px ${SCP_ACCENT})` : undefined,
        transition: 'transform 120ms ease, filter 120ms ease',
      }}
    >
      <SCPCardPanel
        card={card}
        onClick={() => {
          handCard.onClick();
          onInspect();
        }}
      >
        {children}
      </SCPCardPanel>
    </div>
  );
}

/**
 * Drop-zone wrapper used by the Active Anomalies and Contained Archive
 * sections. Renders a ZoneHighlight inside a position:relative container,
 * binds the useCardZone handlers, and lets its children render the panel
 * contents (the SCPCardPanel list + SCPEmpty fallback). The zone IS the
 * SCPSection wrapper — we add a thin extra container so the highlight can
 * lift the whole pile.
 */
function SCPDropZone({
  zoneId,
  onPlay,
  children,
}: {
  zoneId: string;
  onPlay: (cardId: string) => void;
  children: ReactNode;
}) {
  const zone = useCardZone({ zoneId, engineId: SCP_ENGINE_ID, onPlay });
  return (
    <div
      onClick={zone.onClick}
      onDragOver={zone.onDragOver}
      onDragLeave={zone.onDragLeave}
      onDrop={zone.onDrop}
      style={{
        position: 'relative',
        borderRadius: 4,
        cursor: zone.isValid ? 'pointer' : undefined,
      }}
    >
      <ZoneHighlight
        isValid={zone.isValid}
        isHovered={zone.isHovered}
        hasActiveCard={zone.hasActiveCard}
        activeAccent={zone.activeAccent}
      />
      {children}
    </div>
  );
}

export function SCPGameView() {
  useEffect(() => useDiscoveryStore.getState().markPlayed('scp'), []);
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

  // Shared "click to inspect, then act" modal. Additive — the inline action
  // buttons on each hand card (Open / Fast-track / Seal) still work, and so
  // does the existing selection + protocol picker chrome below.
  const inspector = useCardInspector();

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

  // Open the shared CardInspector for a hand-card. Surfaces the same set of
  // actions the inline buttons offer (Open / Fast-track / Seal). The inline
  // buttons stay so quick-action keyboard / muscle-memory flows are preserved.
  const openHandCardInspector = (card: CardData) => {
    const actions: InspectorAction[] = [];
    const redTape = card.scp_red_tape ?? 0;
    const anomaly = isAnomaly(card);

    // openDossier returns Promise<void> (it's a socket send); we don't want
    // to leak the promise into the inspector — wrap in a block body so the
    // return type stays void and the modal closes immediately on click.
    actions.push({
      label: 'Open',
      variant: 'primary',
      disabled: !canAct,
      disabledReason: !canAct ? 'Not your turn' : undefined,
      onClick: () => {
        void openDossier(card.id);
      },
    });
    if (redTape > 0) {
      actions.push({
        label: 'Fast-track',
        variant: 'secondary',
        disabled: !canAct,
        disabledReason: !canAct ? 'Not your turn' : undefined,
        onClick: () => {
          void openDossier(card.id, true);
        },
      });
    }
    if (anomaly) {
      actions.push({
        label: 'Seal',
        variant: 'secondary',
        disabled: !canAct,
        disabledReason: !canAct ? 'Not your turn' : undefined,
        onClick: () => {
          void openDossier(card.id, false, true);
        },
      });
    }

    const typeLabel = card.types.join(' / ');
    const subtitle = card.scp_status ? `${typeLabel} · ${card.scp_status}` : typeLabel;
    const metaRows: { label: string; value: string }[] = [
      { label: 'RT', value: String(card.scp_red_tape ?? 0) },
      { label: 'CL', value: String(card.scp_clearance ?? 0) },
    ];
    if (anomaly) {
      metaRows.push({
        label: 'C/R/H',
        value: `${card.scp_containment ?? 0} / ${card.scp_curiosity ?? 0} / ${card.scp_hazard ?? 0}`,
      });
    } else if (card.types.includes('SCP_PERSONNEL')) {
      const skills = card.scp_skills ?? {};
      metaRows.push({
        label: 'C/R/S',
        value: `${skills.contain ?? 0} / ${skills.research ?? 0} / ${skills.suppress ?? 0}`,
      });
    }
    if (card.scp_mood) metaRows.push({ label: 'Mood', value: formatLabel(card.scp_mood) });

    inspector.open(
      {
        id: card.id,
        name: card.name,
        text: card.text ?? undefined,
        subtitle,
        artUrl: card.image_url ?? null,
        engine: 'scp',
        meta: metaRows,
      },
      actions,
    );
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
          <SCPSitePanel title={myPlayer?.name || 'Your Site'} site={mySite} />
          <div className="grid grid-cols-2 gap-2">
            <ActionButton onClick={() => spendEthics(2)} disabled={!canAct || (mySite.ethics_debt ?? 0) < 2} tone="warn">
              Spend Ethics
            </ActionButton>
            <ActionButton onClick={endTurn} disabled={!canAct} tone="good">End Turn</ActionButton>
          </div>

          <SCPSection title={`Hand (${hand.length})`}>
            {hand.length === 0 && <SCPEmpty label="No cards in hand" />}
            {hand.map((card) => (
              <SCPHandDossier
                key={card.id}
                card={card}
                canAct={canAct}
                isAnomalyCard={isAnomaly(card)}
                onInspect={() => openHandCardInspector(card)}
              >
                <ActionButton onClick={() => openDossier(card.id)} disabled={!canAct}>Open</ActionButton>
                {(card.scp_red_tape ?? 0) > 0 && (
                  <ActionButton onClick={() => openDossier(card.id, true)} disabled={!canAct} tone="warn">Fast-track</ActionButton>
                )}
                {isAnomaly(card) && (
                  <ActionButton onClick={() => openDossier(card.id, false, true)} disabled={!canAct}>Seal</ActionButton>
                )}
              </SCPHandDossier>
            ))}
          </SCPSection>
        </aside>

        <section className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <SCPStat label="Assignments" value={assignmentSlots} tone="text-cyan-300" />
            <SCPStat label="Active Anomalies" value={activeAnomalies.length} tone="text-red-300" />
            <SCPStat label="Contained" value={containedAnomalies.length} tone="text-emerald-300" />
            <SCPStat label="Incidents" value={incidents.length} tone="text-amber-300" />
          </div>

          <SCPDropZone
            zoneId={SCP_ACTIVE_ANOMALY_ZONE}
            onPlay={(cardId) => {
              // Drop fires the same first step the inline "Open" button does.
              // Any follow-up flow (personnel assignment, protocol picker)
              // is still driven by the chrome below.
              void openDossier(cardId);
            }}
          >
            <SCPSection title="Active Anomalies">
              {activeAnomalies.length === 0 && <SCPEmpty label="No active anomalies" />}
              {activeAnomalies.map((card) => (
                <SCPCardPanel
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
                </SCPCardPanel>
              ))}
            </SCPSection>
          </SCPDropZone>

          <div className="grid gap-4 lg:grid-cols-2">
            <SCPSection title="Available Personnel">
              {personnel.length === 0 && <SCPEmpty label="No active personnel" />}
              {personnel.map((card) => (
                <SCPCardPanel
                  key={card.id}
                  card={card}
                  selected={selectedStaffIds.includes(card.id)}
                  onClick={() => !card.scp_exhausted && toggleStaff(card)}
                >
                  <span className={`text-xs ${card.scp_exhausted ? 'text-red-300' : 'text-emerald-300'}`}>
                    {card.scp_exhausted ? 'Exhausted' : selectedStaffIds.includes(card.id) ? 'Assigned' : 'Ready'}
                  </span>
                </SCPCardPanel>
              ))}
            </SCPSection>

            <SCPSection title="Protocols and Site Tools">
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
                <SCPEmpty label="Select an active anomaly" />
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
            </SCPSection>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <SCPSection title="Pending and Sealed Dossiers">
              {myPending.length === 0 && <SCPEmpty label="No queued dossiers" />}
              {myPending.map((card) => (
                <SCPCardPanel key={card.id} card={card}>
                  {card.scp_status === 'sealed' && (
                    <ActionButton onClick={() => revealDossier(card.id)} disabled={!canAct} tone="warn">Reveal</ActionButton>
                  )}
                  <ActionButton onClick={() => memoryHole(card.id)} disabled={!canAct} tone="danger">Memory hole</ActionButton>
                </SCPCardPanel>
              ))}
            </SCPSection>

            <SCPDropZone
              zoneId={SCP_CONTAINED_ZONE}
              onPlay={(cardId) => {
                // Seal lane — fires the same action as the inline "Seal"
                // button (openDossier with sealed=true). Only anomaly hand
                // cards list this zone in their validZones, so non-anomaly
                // drops can't accidentally land here.
                void openDossier(cardId, false, true);
              }}
            >
              <SCPSection title="Contained Archive">
                {containedAnomalies.length === 0 && <SCPEmpty label="No contained anomalies" />}
                {containedAnomalies.map((card) => (
                  <SCPCardPanel key={card.id} card={card}>
                    <ActionButton onClick={() => memoryHole(card.id)} disabled={!canAct} tone="danger">Memory hole</ActionButton>
                  </SCPCardPanel>
                ))}
              </SCPSection>
            </SCPDropZone>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <SCPSection title="Facilities">
              {facilities.length === 0 && <SCPEmpty label="No facilities active" />}
              {facilities.map((card) => <SCPCardPanel key={card.id} card={card} />)}
            </SCPSection>
            <SCPSection title="Mandates">
              {mandates.length === 0 && <SCPEmpty label="No mandate active" />}
              {mandates.map((card) => <SCPCardPanel key={card.id} card={card} />)}
            </SCPSection>
          </div>
        </section>

        <aside className="space-y-4">
          <SCPSitePanel title={opponentPlayer?.name || 'Opposing Site'} site={opponentSite} />

          <SCPSection title="Opposing Active Anomalies">
            {opponentAnomalies.length === 0 && <SCPEmpty label="No public active anomalies" />}
            {opponentAnomalies.map((card) => <SCPCardPanel key={card.id} card={card} />)}
          </SCPSection>

          <SCPSection title="Opposing Pending Dossiers">
            {opponentPending.length === 0 && <SCPEmpty label="No public queued dossiers" />}
            {opponentPending.map((card) => <SCPCardPanel key={card.id} card={card} />)}
          </SCPSection>

          <SCPSection title="Opposing Containment">
            {opponentContained.length === 0 && <SCPEmpty label="No contained anomalies" />}
            {opponentContained.map((card) => <SCPCardPanel key={card.id} card={card} />)}
          </SCPSection>

          <SCPSection title="Opposing Personnel">
            {opponentPersonnel.length === 0 && <SCPEmpty label="No personnel active" />}
            {opponentPersonnel.map((card) => <SCPCardPanel key={card.id} card={card} />)}
          </SCPSection>
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
