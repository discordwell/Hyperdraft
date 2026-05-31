/**
 * SCPCardViewer — browse the SCP: SECURE / CONTAIN / SUBVERT card pool
 * (asymmetric Foundation vs Chaos Insurgency).
 *
 * Reads the deckbuilder pool for game "scp" (game_registry → the new card
 * model) and groups by faction + kind, showing the new stat model: cost,
 * containment threshold + liberation value (anomalies), layer strength + type,
 * breaker power + type (operatives). Routes: /scp-cards, /cards/scp.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { deckbuilderAPI } from '../services/deckbuilderApi';
import type { CardDefinitionData } from '../types/deckbuilder';

const KINDS = [
  'SCP_ANOMALY', 'SCP_LAYER', 'SCP_ASSET', 'SCP_OPERATION',
  'SCP_OPERATIVE', 'SCP_TOOL', 'SCP_EVENT', 'SCP_IDENTITY',
] as const;

const KIND_LABEL: Record<string, string> = {
  SCP_ANOMALY: 'Anomaly', SCP_LAYER: 'Layer', SCP_ASSET: 'Asset', SCP_OPERATION: 'Operation',
  SCP_OPERATIVE: 'Operative', SCP_TOOL: 'Tool', SCP_EVENT: 'Event', SCP_IDENTITY: 'Identity',
};

const FACTION_TONE: Record<string, string> = {
  foundation: 'border-violet-500/50 bg-violet-950/40 text-violet-100',
  insurgency: 'border-red-500/50 bg-red-950/40 text-red-100',
};

function extras(card: CardDefinitionData): Record<string, unknown> {
  return (card.extras ?? {}) as Record<string, unknown>;
}
function num(card: CardDefinitionData, key: string): number {
  const v = extras(card)[key];
  return typeof v === 'number' ? v : 0;
}
function str(card: CardDefinitionData, key: string): string {
  const v = extras(card)[key];
  return typeof v === 'string' ? v : '';
}
function kindOf(card: CardDefinitionData): string {
  return str(card, 'scp_kind') || card.types[0] || '';
}
function factionOf(card: CardDefinitionData): string {
  return str(card, 'scp_faction') || '';
}

function statLine(card: CardDefinitionData): string {
  const kind = kindOf(card);
  if (kind === 'SCP_ANOMALY') {
    const trap = extras(card)['scp_trap'] === true ? ' · TRAP' : '';
    return `advance ${num(card, 'scp_threshold')} → lock · value ${num(card, 'scp_value')}${trap}`;
  }
  if (kind === 'SCP_LAYER') {
    return `${str(card, 'scp_ltype') || 'layer'} · strength ${num(card, 'scp_strength')} · rez ${num(card, 'scp_rez')}`;
  }
  if (kind === 'SCP_OPERATIVE') {
    return `breaks ${str(card, 'scp_breaks') || '—'} · power ${num(card, 'scp_power')} (+${num(card, 'scp_boost')}/credit)`;
  }
  return '';
}

function Card({ card }: { card: CardDefinitionData }) {
  const kind = kindOf(card);
  const faction = factionOf(card);
  const tone = FACTION_TONE[faction] ?? 'border-slate-600 bg-slate-900 text-slate-200';
  const sl = statLine(card);
  return (
    <div className={`rounded-lg border p-3 ${tone}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-semibold text-sm">{card.name}</span>
        <span className="shrink-0 font-mono text-xs opacity-80">⌑{num(card, 'scp_cost')}</span>
      </div>
      <div className="mt-0.5 text-[10px] uppercase tracking-widest opacity-70">
        {KIND_LABEL[kind] ?? kind}{faction ? ` · ${faction}` : ''}
      </div>
      {sl && <div className="mt-1 font-mono text-[11px] opacity-90">{sl}</div>}
      {card.text && <div className="mt-1 text-[11px] leading-snug opacity-80">{card.text}</div>}
    </div>
  );
}

export function SCPCardViewer() {
  const navigate = useNavigate();
  const [cards, setCards] = useState<CardDefinitionData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [factionFilter, setFactionFilter] = useState('all');
  const [kindFilter, setKindFilter] = useState('all');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const loaded: CardDefinitionData[] = [];
        let offset = 0;
        let hasMore = true;
        while (hasMore) {
          const response = await deckbuilderAPI.getAllCards('scp', 500, offset);
          loaded.push(...response.cards);
          offset += response.cards.length;
          hasMore = response.has_more && response.cards.length > 0;
        }
        if (!cancelled) setCards(loaded);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load SCP cards');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return cards
      .filter((c) => factionFilter === 'all' || factionOf(c) === factionFilter)
      .filter((c) => kindFilter === 'all' || kindOf(c) === kindFilter)
      .filter((c) => !q || c.name.toLowerCase().includes(q) || (c.text ?? '').toLowerCase().includes(q))
      .sort((a, b) => (factionOf(a)).localeCompare(factionOf(b)) || num(a, 'scp_cost') - num(b, 'scp_cost') || a.name.localeCompare(b.name));
  }, [cards, query, factionFilter, kindFilter]);

  const foundationCount = cards.filter((c) => factionOf(c) === 'foundation').length;
  const insurgencyCount = cards.filter((c) => factionOf(c) === 'insurgency').length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">SCP — SECURE / CONTAIN / SUBVERT</h1>
          <p className="text-[11px] uppercase tracking-widest text-slate-500">
            {cards.length} cards · {foundationCount} Foundation · {insurgencyCount} Chaos Insurgency
          </p>
        </div>
        <button onClick={() => navigate('/')} className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700">
          ← Home
        </button>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name or text…"
          className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm"
        />
        <select value={factionFilter} onChange={(e) => setFactionFilter(e.target.value)} className="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm">
          <option value="all">All factions</option>
          <option value="foundation">Foundation</option>
          <option value="insurgency">Chaos Insurgency</option>
        </select>
        <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} className="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm">
          <option value="all">All types</option>
          {KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
      </div>

      {loading && <div className="text-slate-500">Loading…</div>}
      {error && <div className="text-red-400">{error}</div>}
      {!loading && !error && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((c) => <Card key={c.name} card={c} />)}
        </div>
      )}
    </div>
  );
}

export default SCPCardViewer;
