import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { deckbuilderAPI } from '../services/deckbuilderApi';
import type { CardDefinitionData } from '../types/deckbuilder';

const SCP_TYPES = [
  'SCP_ANOMALY',
  'SCP_PERSONNEL',
  'SCP_FACILITY',
  'SCP_PROCEDURE',
  'SCP_MANDATE',
] as const;

const TYPE_TONES: Record<string, string> = {
  SCP_ANOMALY: 'border-red-500/50 bg-red-950/40 text-red-100',
  SCP_PERSONNEL: 'border-cyan-500/50 bg-cyan-950/40 text-cyan-100',
  SCP_FACILITY: 'border-amber-500/50 bg-amber-950/40 text-amber-100',
  SCP_PROCEDURE: 'border-violet-500/50 bg-violet-950/40 text-violet-100',
  SCP_MANDATE: 'border-emerald-500/50 bg-emerald-950/40 text-emerald-100',
};

type SortKey = 'name' | 'expansion' | 'red_tape' | 'hazard' | 'clearance';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function extras(card: CardDefinitionData): Record<string, unknown> {
  return card.extras ?? {};
}

function num(card: CardDefinitionData, key: string): number {
  const value = extras(card)[key];
  return typeof value === 'number' ? value : 0;
}

function str(card: CardDefinitionData, key: string, fallback = ''): string {
  const value = extras(card)[key];
  return typeof value === 'string' ? value : fallback;
}

function list(card: CardDefinitionData, key: string): string[] {
  const value = extras(card)[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function metricEntries(card: CardDefinitionData, key: string): Array<[string, number]> {
  const value = extras(card)[key];
  if (!isRecord(value)) return [];
  return Object.entries(value)
    .filter((entry): entry is [string, number] => typeof entry[1] === 'number' && entry[1] !== 0)
    .sort(([a], [b]) => a.localeCompare(b));
}

function label(value: string | null | undefined): string {
  if (!value) return 'Unknown';
  return value
    .replace(/^SCP_/, '')
    .replace(/[_-]/g, ' ')
    .replace(/\w\S*/g, (part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase());
}

function primaryType(card: CardDefinitionData): string {
  return card.types.find((type) => SCP_TYPES.includes(type as (typeof SCP_TYPES)[number])) ?? card.types[0] ?? 'SCP_CARD';
}

function classification(card: CardDefinitionData): string {
  const hazard = num(card, 'scp_hazard');
  const containment = num(card, 'scp_containment');
  if (hazard >= 4 || containment >= 6) return 'Keter';
  if (hazard >= 2 || containment >= 4) return 'Euclid';
  return 'Safe';
}

function compareCards(a: CardDefinitionData, b: CardDefinitionData, sort: SortKey): number {
  if (sort === 'expansion') {
    return `${str(a, 'scp_expansion_code')} ${a.name}`.localeCompare(`${str(b, 'scp_expansion_code')} ${b.name}`);
  }
  if (sort === 'red_tape') {
    return num(a, 'scp_red_tape') - num(b, 'scp_red_tape') || a.name.localeCompare(b.name);
  }
  if (sort === 'hazard') {
    return num(b, 'scp_hazard') - num(a, 'scp_hazard') || a.name.localeCompare(b.name);
  }
  if (sort === 'clearance') {
    return num(b, 'scp_clearance') - num(a, 'scp_clearance') || a.name.localeCompare(b.name);
  }
  return a.name.localeCompare(b.name);
}

function Badge({ children, tone = 'border-slate-700 bg-zinc-950 text-zinc-200' }: { children: string; tone?: string }) {
  return (
    <span className={`inline-flex items-center rounded-sm border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${tone}`}>
      {children}
    </span>
  );
}

function Metric({ label: metricLabel, value, tone = 'text-zinc-100' }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="border border-zinc-800 bg-black/35 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">{metricLabel}</div>
      <div className={`mt-1 text-lg font-semibold ${tone}`}>{value}</div>
    </div>
  );
}

function SCPArt({ card, compact = false }: { card: CardDefinitionData; compact?: boolean }) {
  const code = str(card, 'scp_expansion_code', 'SCP');
  const type = primaryType(card);
  const hasImage = Boolean(card.image_url);
  const typeClass = TYPE_TONES[type] ?? TYPE_TONES.SCP_MANDATE;

  return (
    <div className="relative h-full w-full overflow-hidden border border-zinc-800 bg-zinc-950">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_25%,rgba(220,38,38,0.22),transparent_34%),radial-gradient(circle_at_74%_76%,rgba(34,211,238,0.16),transparent_38%),linear-gradient(145deg,#09090b,#18181b_55%,#0f172a)]" />
      <div className="absolute inset-0 opacity-35 [background-image:linear-gradient(rgba(255,255,255,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] [background-size:18px_18px]" />
      <div className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-zinc-500/30" />
      <div className="absolute left-1/2 top-1/2 h-px w-3/4 -translate-x-1/2 bg-zinc-500/25" />
      <div className="absolute left-1/2 top-1/2 h-3/4 w-px -translate-y-1/2 bg-zinc-500/25" />
      <div className="absolute left-3 top-3 font-mono text-[10px] uppercase tracking-[0.28em] text-zinc-500">CLASSIFIED</div>
      <div className="absolute bottom-3 left-3 right-3 flex items-end justify-between gap-2">
        <div>
          <div className="font-mono text-xs uppercase tracking-[0.22em] text-zinc-300">{code}</div>
          {!compact && <div className="mt-1 text-[11px] text-zinc-500">{classification(card)} file</div>}
        </div>
        <span className={`border px-2 py-1 text-[10px] uppercase tracking-wide ${typeClass}`}>{label(type)}</span>
      </div>
      {hasImage && (
        <img
          src={card.image_url ?? undefined}
          alt={card.name}
          className="absolute inset-0 h-full w-full object-cover"
          decoding="async"
          onError={(event) => {
            event.currentTarget.style.display = 'none';
          }}
        />
      )}
    </div>
  );
}

function SmallCard({
  card,
  selected,
  onSelect,
}: {
  card: CardDefinitionData;
  selected: boolean;
  onSelect: () => void;
}) {
  const type = primaryType(card);
  const tone = TYPE_TONES[type] ?? TYPE_TONES.SCP_MANDATE;
  const keywords = list(card, 'scp_keywords');

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`group min-w-0 border p-2 text-left transition-colors ${
        selected ? 'border-cyan-400 bg-cyan-950/25' : 'border-zinc-800 bg-zinc-950/70 hover:border-zinc-600'
      }`}
    >
      <div className="flex min-w-0 gap-3">
        <div className="h-20 w-14 shrink-0">
          <SCPArt card={card} compact />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="truncate text-sm font-semibold text-zinc-100">{card.name}</h3>
            <span className="shrink-0 font-mono text-xs text-zinc-400">RT {num(card, 'scp_red_tape')}</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            <Badge tone={tone}>{label(type)}</Badge>
            {str(card, 'scp_expansion_code') && <Badge>{str(card, 'scp_expansion_code')}</Badge>}
          </div>
          <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-zinc-500">{card.text}</p>
          {keywords.length > 0 && (
            <div className="mt-2 truncate text-[11px] uppercase tracking-wide text-amber-300/80">
              {keywords.join(' / ')}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

function DetailCard({ card }: { card: CardDefinitionData }) {
  const type = primaryType(card);
  const tone = TYPE_TONES[type] ?? TYPE_TONES.SCP_MANDATE;
  const skills = metricEntries(card, 'scp_skills');
  const bonuses = metricEntries(card, 'scp_bonus');
  const keywords = list(card, 'scp_keywords');
  const altWin = str(card, 'scp_alt_win');
  const artPrompt = str(card, 'scp_art_prompt');
  const navigate = useNavigate();
  const [copied, setCopied] = useState(false);

  const copyPrompt = async () => {
    if (!artPrompt) return;
    await navigator.clipboard.writeText(artPrompt);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  return (
    <aside className="flex min-h-0 flex-col border-l border-zinc-800 bg-black/30 lg:w-[420px]">
      <div className="border-b border-zinc-800 px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.24em] text-zinc-500">SCP Dossier</div>
            <h2 className="mt-1 text-xl font-bold text-zinc-100">{card.name}</h2>
          </div>
          <button
            type="button"
            onClick={() => navigate('/deckbuilder/scp')}
            className="shrink-0 border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-zinc-300 hover:border-cyan-500 hover:text-cyan-100"
          >
            Build
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-sm border border-zinc-700 bg-zinc-950 shadow-2xl shadow-black/60">
          <div className="flex items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-900 px-3 py-2">
            <div className="min-w-0 truncate text-sm font-bold text-zinc-100">{card.name}</div>
            <div className="flex gap-1 font-mono text-xs">
              <span className="border border-red-500/40 bg-red-950/50 px-2 py-1 text-red-100">RT {num(card, 'scp_red_tape')}</span>
              <span className="border border-cyan-500/40 bg-cyan-950/50 px-2 py-1 text-cyan-100">CL {num(card, 'scp_clearance')}</span>
            </div>
          </div>
          <div className="aspect-[5/3]">
            <SCPArt card={card} />
          </div>
          <div className={`border-y px-3 py-2 text-xs font-semibold uppercase tracking-wide ${tone}`}>
            {label(type)}
            {card.subtypes.length > 0 ? ` - ${card.subtypes.join(' / ')}` : ''}
          </div>
          <div className={`min-h-40 px-4 py-3 ${tone}`}>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{card.text || 'No printed text.'}</p>
          </div>
          <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-400">
            <span>{str(card, 'scp_expansion') || 'SCP Core'}</span>
            <span className="uppercase">{str(card, 'scp_archetype') || 'foundation'}</span>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-2">
          <Metric label="Containment" value={num(card, 'scp_containment')} tone="text-emerald-300" />
          <Metric label="Curiosity" value={num(card, 'scp_curiosity')} tone="text-amber-300" />
          <Metric label="Hazard" value={num(card, 'scp_hazard')} tone="text-red-300" />
          <Metric label="Class" value={classification(card)} tone="text-cyan-300" />
        </div>

        {(skills.length > 0 || bonuses.length > 0) && (
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {skills.length > 0 && (
              <section className="border border-zinc-800 bg-zinc-950/70 p-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Personnel Skills</h3>
                <div className="mt-3 space-y-2">
                  {skills.map(([skill, value]) => (
                    <div key={skill} className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">{label(skill)}</span>
                      <span className="font-mono text-cyan-200">{value}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
            {bonuses.length > 0 && (
              <section className="border border-zinc-800 bg-zinc-950/70 p-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Site Bonuses</h3>
                <div className="mt-3 space-y-2">
                  {bonuses.map(([bonus, value]) => (
                    <div key={bonus} className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">{label(bonus)}</span>
                      <span className="font-mono text-emerald-200">+{value}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        {(keywords.length > 0 || altWin) && (
          <section className="mt-5 border border-zinc-800 bg-zinc-950/70 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Tags</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {keywords.map((keyword) => (
                <Badge key={keyword} tone="border-amber-500/40 bg-amber-950/40 text-amber-100">{keyword}</Badge>
              ))}
              {altWin && <Badge tone="border-emerald-500/40 bg-emerald-950/40 text-emerald-100">{label(altWin)}</Badge>}
            </div>
          </section>
        )}

        {artPrompt && (
          <section className="mt-5 border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Art Prompt</h3>
              <button
                type="button"
                onClick={copyPrompt}
                className="border border-zinc-700 bg-zinc-900 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-300 hover:border-amber-500 hover:text-amber-100"
              >
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-zinc-400">{artPrompt}</p>
          </section>
        )}
      </div>
    </aside>
  );
}

export function SCPCardViewer() {
  const navigate = useNavigate();
  const [cards, setCards] = useState<CardDefinitionData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [expansionFilter, setExpansionFilter] = useState('all');
  const [archetypeFilter, setArchetypeFilter] = useState('all');
  const [keywordFilter, setKeywordFilter] = useState('all');
  const [sort, setSort] = useState<SortKey>('name');
  const [selectedName, setSelectedName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadCards() {
      try {
        setLoading(true);
        setError(null);
        const loaded: CardDefinitionData[] = [];
        let offset = 0;
        let hasMore = true;
        const limit = 500;

        while (hasMore) {
          const response = await deckbuilderAPI.getAllCards('scp', limit, offset);
          loaded.push(...response.cards);
          offset += response.cards.length;
          hasMore = response.has_more && response.cards.length > 0;
        }

        if (!cancelled) {
          setCards(loaded);
          setSelectedName(loaded[0]?.name ?? null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load SCP cards');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadCards();

    return () => {
      cancelled = true;
    };
  }, []);

  const expansions = useMemo(
    () => Array.from(new Set(cards.map((card) => str(card, 'scp_expansion')).filter(Boolean))).sort(),
    [cards],
  );

  const archetypes = useMemo(
    () => Array.from(new Set(cards.map((card) => str(card, 'scp_archetype')).filter(Boolean))).sort(),
    [cards],
  );

  const keywords = useMemo(
    () => Array.from(new Set(cards.flatMap((card) => list(card, 'scp_keywords')))).sort(),
    [cards],
  );

  const filteredCards = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return cards
      .filter((card) => {
        if (typeFilter !== 'all' && !card.types.includes(typeFilter)) return false;
        if (expansionFilter !== 'all' && str(card, 'scp_expansion') !== expansionFilter) return false;
        if (archetypeFilter !== 'all' && str(card, 'scp_archetype') !== archetypeFilter) return false;
        if (keywordFilter !== 'all' && !list(card, 'scp_keywords').includes(keywordFilter)) return false;
        if (!needle) return true;
        const searchable = [
          card.name,
          card.text,
          card.types.join(' '),
          card.subtypes.join(' '),
          str(card, 'scp_expansion'),
          str(card, 'scp_expansion_code'),
          str(card, 'scp_archetype'),
          str(card, 'scp_art_prompt'),
          ...list(card, 'scp_keywords'),
        ].join(' ').toLowerCase();
        return searchable.includes(needle);
      })
      .sort((a, b) => compareCards(a, b, sort));
  }, [archetypeFilter, cards, expansionFilter, keywordFilter, query, sort, typeFilter]);

  useEffect(() => {
    if (filteredCards.length === 0) {
      setSelectedName(null);
      return;
    }
    if (!selectedName || !filteredCards.some((card) => card.name === selectedName)) {
      setSelectedName(filteredCards[0].name);
    }
  }, [filteredCards, selectedName]);

  const selectedCard = filteredCards.find((card) => card.name === selectedName) ?? filteredCards[0] ?? null;
  const anomalyCount = cards.filter((card) => card.types.includes('SCP_ANOMALY')).length;
  const siteZeroCount = cards.filter((card) => str(card, 'scp_expansion_code') === 'SZB').length;

  const resetFilters = () => {
    setQuery('');
    setTypeFilter('all');
    setExpansionFilter('all');
    setArchetypeFilter('all');
    setKeywordFilter('all');
    setSort('name');
  };

  return (
    <div className="min-h-screen bg-[#08090d] text-zinc-100">
      <header className="border-b border-zinc-800 bg-black/70 px-4 py-4 sm:px-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 hover:border-zinc-500 hover:text-white"
            >
              Home
            </button>
            <div>
              <div className="text-[11px] uppercase tracking-[0.28em] text-red-300/80">Foundation Archive</div>
              <h1 className="text-2xl font-bold text-zinc-100 sm:text-3xl">SCP Card Viewer</h1>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center sm:flex sm:text-left">
            <Metric label="Cards" value={cards.length} tone="text-zinc-100" />
            <Metric label="Anomalies" value={anomalyCount} tone="text-red-300" />
            <Metric label="Site Zero" value={siteZeroCount} tone="text-cyan-300" />
          </div>
        </div>
      </header>

      <main className="flex min-h-[calc(100vh-97px)] flex-col lg:flex-row">
        <section className="border-b border-zinc-800 bg-zinc-950/80 p-4 lg:w-80 lg:border-b-0 lg:border-r">
          <div className="space-y-4">
            <div>
              <label htmlFor="scp-card-search" className="block text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Search
              </label>
              <input
                id="scp-card-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="mt-2 w-full border border-zinc-700 bg-black px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500"
                placeholder="name, rules, tag"
              />
            </div>

            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Type</div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setTypeFilter('all')}
                  className={`border px-3 py-2 text-xs font-semibold uppercase tracking-wide ${
                    typeFilter === 'all' ? 'border-zinc-300 bg-zinc-100 text-zinc-950' : 'border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-zinc-500'
                  }`}
                >
                  All
                </button>
                {SCP_TYPES.map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setTypeFilter(type)}
                    className={`border px-3 py-2 text-xs font-semibold uppercase tracking-wide ${
                      typeFilter === type ? 'border-cyan-400 bg-cyan-950 text-cyan-100' : 'border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-zinc-500'
                    }`}
                  >
                    {label(type)}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
              <div>
                <label htmlFor="scp-expansion-filter" className="block text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Expansion
                </label>
                <select
                  id="scp-expansion-filter"
                  value={expansionFilter}
                  onChange={(event) => setExpansionFilter(event.target.value)}
                  className="mt-2 w-full border border-zinc-700 bg-black px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500"
                >
                  <option value="all">All expansions</option>
                  {expansions.map((expansion) => (
                    <option key={expansion} value={expansion}>{expansion}</option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="scp-archetype-filter" className="block text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Archetype
                </label>
                <select
                  id="scp-archetype-filter"
                  value={archetypeFilter}
                  onChange={(event) => setArchetypeFilter(event.target.value)}
                  className="mt-2 w-full border border-zinc-700 bg-black px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500"
                >
                  <option value="all">All archetypes</option>
                  {archetypes.map((archetype) => (
                    <option key={archetype} value={archetype}>{label(archetype)}</option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="scp-keyword-filter" className="block text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Keyword
                </label>
                <select
                  id="scp-keyword-filter"
                  value={keywordFilter}
                  onChange={(event) => setKeywordFilter(event.target.value)}
                  className="mt-2 w-full border border-zinc-700 bg-black px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500"
                >
                  <option value="all">All keywords</option>
                  {keywords.map((keyword) => (
                    <option key={keyword} value={keyword}>{keyword}</option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="scp-sort" className="block text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Sort
                </label>
                <select
                  id="scp-sort"
                  value={sort}
                  onChange={(event) => setSort(event.target.value as SortKey)}
                  className="mt-2 w-full border border-zinc-700 bg-black px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500"
                >
                  <option value="name">Name</option>
                  <option value="expansion">Expansion</option>
                  <option value="red_tape">Red Tape</option>
                  <option value="hazard">Hazard</option>
                  <option value="clearance">Clearance</option>
                </select>
              </div>
            </div>

            <button
              type="button"
              onClick={resetFilters}
              className="w-full border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-semibold uppercase tracking-wide text-zinc-300 hover:border-red-500 hover:text-red-100"
            >
              Reset
            </button>
          </div>
        </section>

        <section className="flex min-h-[560px] flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-950/60 px-4 py-3">
            <div className="text-sm text-zinc-400">
              <span className="font-semibold text-zinc-100">{filteredCards.length.toLocaleString()}</span> matches
            </div>
            {loading && <div className="text-sm text-zinc-500">Loading...</div>}
          </div>

          {error && (
            <div className="m-4 border border-red-700 bg-red-950/50 px-4 py-3 text-sm text-red-100">
              {error}
            </div>
          )}

          {!loading && !error && filteredCards.length === 0 && (
            <div className="m-4 border border-dashed border-zinc-700 px-4 py-10 text-center text-sm text-zinc-500">
              No SCP cards match the current filters.
            </div>
          )}

          <div className="grid flex-1 auto-rows-min grid-cols-1 gap-3 overflow-y-auto p-4 xl:grid-cols-2 2xl:grid-cols-3">
            {filteredCards.map((card) => (
              <SmallCard
                key={card.name}
                card={card}
                selected={card.name === selectedCard?.name}
                onSelect={() => setSelectedName(card.name)}
              />
            ))}
          </div>
        </section>

        {selectedCard && <DetailCard card={selectedCard} />}
      </main>
    </div>
  );
}

export default SCPCardViewer;
