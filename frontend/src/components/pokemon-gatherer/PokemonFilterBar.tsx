/**
 * PokemonFilterBar
 *
 * Filtering / sorting controls for the Pokemon card grid.
 */

import { useState } from 'react';
import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import {
  POKEMON_TYPE_INFO,
  POKEMON_TYPE_ORDER,
  POKEMON_SORT_FIELDS,
  hasActivePokemonFilters,
} from '../../types/pokemonGatherer';
import type {
  PokemonEvolutionStage,
  PokemonSortField,
  PokemonSupertype,
  PokemonTrainerSubtype,
} from '../../types/pokemonGatherer';

const SUPERTYPES: PokemonSupertype[] = ['Pokemon', 'Trainer', 'Energy'];
const TRAINER_SUBTYPES: PokemonTrainerSubtype[] = ['Item', 'Supporter', 'Stadium', 'Tool'];
const STAGES: PokemonEvolutionStage[] = ['Basic', 'Stage 1', 'Stage 2'];

export function PokemonFilterBar() {
  const {
    currentSet,
    cardsTotal,
    filter,
    sortBy,
    sortOrder,
    setFilter,
    clearFilter,
    setSortBy,
    toggleSortOrder,
  } = usePokemonGathererStore();

  const [textSearch, setTextSearch] = useState(filter.textSearch ?? '');

  if (!currentSet) return null;

  const hasActiveFilters = hasActivePokemonFilters(filter);

  const handleTextSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFilter({ textSearch: textSearch || undefined });
  };

  const showPokemonOnlyFilters = !filter.supertype || filter.supertype === 'Pokemon';
  const showTrainerSubtype = filter.supertype === 'Trainer';
  const guilds = currentSet.guilds ?? [];

  return (
    <div className="bg-gray-800 border-b border-gray-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold text-white">{currentSet.name}</h2>
          <p className="text-sm text-gray-400">
            {cardsTotal} card{cardsTotal !== 1 ? 's' : ''} found
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as PokemonSortField)}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-game-accent"
          >
            {POKEMON_SORT_FIELDS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <button
            onClick={toggleSortOrder}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded text-white text-sm hover:bg-gray-600 transition-colors"
          >
            {sortOrder === 'asc' ? '↑ Asc' : '↓ Desc'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <form onSubmit={handleTextSearchSubmit} className="flex-1 min-w-[180px] max-w-[260px]">
          <div className="relative">
            <input
              type="text"
              value={textSearch}
              onChange={(e) => setTextSearch(e.target.value)}
              placeholder="Search Pokemon..."
              className="w-full px-3 py-1.5 pr-8 bg-gray-700 border border-gray-600 rounded text-white text-sm placeholder-gray-400 focus:outline-none focus:border-game-accent"
            />
            {textSearch && (
              <button
                type="button"
                onClick={() => {
                  setTextSearch('');
                  setFilter({ textSearch: undefined });
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
              >
                ×
              </button>
            )}
          </div>
        </form>

        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400 mr-1">Category:</span>
          {SUPERTYPES.map((s) => (
            <button
              key={s}
              onClick={() => {
                const next = filter.supertype === s ? undefined : s;
                const switchedAway = next !== 'Pokemon';
                setFilter({
                  supertype: next,
                  trainerSubtype: undefined,
                  // Pokemon-only filters get cleared when leaving the Pokemon
                  // supertype — otherwise an old hp_min strands the user on
                  // a zero-result Energy/Trainer view with no UI to reset it.
                  evolutionStage: switchedAway ? undefined : filter.evolutionStage,
                  isEx: switchedAway ? undefined : filter.isEx,
                  hpMin: switchedAway ? undefined : filter.hpMin,
                  hpMax: switchedAway ? undefined : filter.hpMax,
                  retreatCostMin: switchedAway ? undefined : filter.retreatCostMin,
                  retreatCostMax: switchedAway ? undefined : filter.retreatCostMax,
                });
              }}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                filter.supertype === s
                  ? 'bg-game-accent text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {showTrainerSubtype && (
          <div className="flex items-center gap-1">
            <span className="text-xs text-gray-400 mr-1">Trainer:</span>
            {TRAINER_SUBTYPES.map((s) => (
              <button
                key={s}
                onClick={() =>
                  setFilter({ trainerSubtype: filter.trainerSubtype === s ? undefined : s })
                }
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  filter.trainerSubtype === s
                    ? 'bg-game-accent text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400 mr-1">Type:</span>
          {POKEMON_TYPE_ORDER.map((t) => {
            const info = POKEMON_TYPE_INFO[t];
            const active = filter.pokemonType === t;
            return (
              <button
                key={t}
                onClick={() =>
                  setFilter({ pokemonType: active ? undefined : t })
                }
                className={`w-6 h-6 rounded-full border-2 transition-all flex items-center justify-center text-[10px] font-bold ${
                  active ? 'border-white scale-110' : 'border-gray-600 hover:border-gray-400'
                }`}
                style={{ background: info.color, color: '#000' }}
                title={info.label}
              >
                {info.symbol}
              </button>
            );
          })}
        </div>

        {showPokemonOnlyFilters && (
          <>
            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-400 mr-1">Stage:</span>
              {STAGES.map((s) => (
                <button
                  key={s}
                  onClick={() =>
                    setFilter({ evolutionStage: filter.evolutionStage === s ? undefined : s })
                  }
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    filter.evolutionStage === s
                      ? 'bg-game-accent text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-400 mr-1">EX:</span>
              <button
                onClick={() =>
                  setFilter({ isEx: filter.isEx === true ? undefined : true })
                }
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  filter.isEx === true
                    ? 'bg-yellow-500 text-black'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                ex only
              </button>
              <button
                onClick={() =>
                  setFilter({ isEx: filter.isEx === false ? undefined : false })
                }
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  filter.isEx === false
                    ? 'bg-game-accent text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                non-ex
              </button>
            </div>

            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-400 mr-1">HP:</span>
              <input
                type="number"
                min={0}
                max={400}
                step={10}
                placeholder="min"
                value={filter.hpMin ?? ''}
                onChange={(e) =>
                  setFilter({ hpMin: e.target.value ? parseInt(e.target.value) : undefined })
                }
                className="w-16 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm"
              />
              <span className="text-gray-500">-</span>
              <input
                type="number"
                min={0}
                max={400}
                step={10}
                placeholder="max"
                value={filter.hpMax ?? ''}
                onChange={(e) =>
                  setFilter({ hpMax: e.target.value ? parseInt(e.target.value) : undefined })
                }
                className="w-16 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm"
              />
            </div>

            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-400 mr-1">Retreat:</span>
              <input
                type="number"
                min={0}
                max={5}
                placeholder="min"
                value={filter.retreatCostMin ?? ''}
                onChange={(e) =>
                  setFilter({
                    retreatCostMin: e.target.value ? parseInt(e.target.value) : undefined,
                  })
                }
                className="w-14 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm"
              />
              <span className="text-gray-500">-</span>
              <input
                type="number"
                min={0}
                max={5}
                placeholder="max"
                value={filter.retreatCostMax ?? ''}
                onChange={(e) =>
                  setFilter({
                    retreatCostMax: e.target.value ? parseInt(e.target.value) : undefined,
                  })
                }
                className="w-14 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm"
              />
            </div>
          </>
        )}

        {guilds.length > 0 && (
          <div className="flex items-center gap-1">
            <span className="text-xs text-gray-400 mr-1">Guild:</span>
            <select
              value={filter.guild ?? ''}
              onChange={(e) => setFilter({ guild: e.target.value || undefined })}
              className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm"
            >
              <option value="">All</option>
              {guilds.map((g) => (
                <option key={g} value={g}>
                  {g.charAt(0).toUpperCase() + g.slice(1)}
                </option>
              ))}
            </select>
          </div>
        )}

        {hasActiveFilters && (
          <button
            onClick={() => {
              setTextSearch('');
              clearFilter();
            }}
            className="px-3 py-1 text-xs bg-red-600 hover:bg-red-500 text-white rounded transition-colors"
          >
            Clear Filters
          </button>
        )}
      </div>
    </div>
  );
}

export default PokemonFilterBar;
