/**
 * PokemonSetSidebar
 *
 * Pokemon-only set list (parallel to MTG SetSidebar). Two set types:
 * starter and beyond.
 */

import { useEffect } from 'react';
import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import { POKEMON_SET_TYPE_INFO } from '../../types/pokemonGatherer';
import type { PokemonSetInfo } from '../../types/pokemonGatherer';

type PokemonSetType = 'starter' | 'beyond';

const SET_TYPES: PokemonSetType[] = ['starter', 'beyond'];

interface SetItemProps {
  set: PokemonSetInfo;
  isSelected: boolean;
  onClick: () => void;
}

function SetItem({ set, isSelected, onClick }: SetItemProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 rounded transition-all ${
        isSelected ? 'bg-game-accent text-white' : 'hover:bg-gray-700 text-gray-300'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium truncate">{set.name}</span>
        <span className="text-xs text-gray-400 ml-2">{set.card_count}</span>
      </div>
      <div className="text-xs text-gray-500">{set.code}</div>
    </button>
  );
}

export function PokemonSetSidebar() {
  const {
    sets,
    setsLoading,
    setsError,
    currentSet,
    setTypeFilter,
    loadSets,
    selectSet,
    setSetTypeFilter,
  } = usePokemonGathererStore();

  useEffect(() => {
    loadSets();
  }, [loadSets]);

  const grouped = sets.reduce(
    (acc, s) => {
      const t = s.set_type as PokemonSetType;
      if (!acc[t]) acc[t] = [];
      acc[t].push(s);
      return acc;
    },
    {} as Record<PokemonSetType, PokemonSetInfo[]>
  );

  return (
    <div className="w-64 bg-gray-900 border-r border-gray-700 flex flex-col h-full">
      <div className="p-4 border-b border-gray-700">
        <h2 className="text-lg font-bold text-white">Pokemon Sets</h2>
        <p className="text-xs text-gray-400 mt-1">
          {sets.length} sets, {sets.reduce((sum, s) => sum + s.card_count, 0).toLocaleString()} cards
        </p>
      </div>

      <div className="p-2 border-b border-gray-700">
        <div className="flex flex-wrap gap-1">
          <button
            onClick={() => setSetTypeFilter(null)}
            className={`px-2 py-1 text-xs rounded ${
              !setTypeFilter
                ? 'bg-game-accent text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            All
          </button>
          {SET_TYPES.map((type) => (
            <button
              key={type}
              onClick={() => setSetTypeFilter(type)}
              className={`px-2 py-1 text-xs rounded ${
                setTypeFilter === type
                  ? 'bg-game-accent text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {POKEMON_SET_TYPE_INFO[type].label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {setsLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-game-accent" />
          </div>
        ) : setsError ? (
          <div className="p-4 text-red-400 text-sm">{setsError}</div>
        ) : setTypeFilter ? (
          <div className="space-y-1">
            {sets.map((s) => (
              <SetItem
                key={s.code}
                set={s}
                isSelected={s.code === currentSet?.code}
                onClick={() => selectSet(s.code)}
              />
            ))}
          </div>
        ) : (
          SET_TYPES.map((type) => {
            const list = grouped[type] ?? [];
            if (list.length === 0) return null;
            const info = POKEMON_SET_TYPE_INFO[type];
            return (
              <div key={type} className="mb-4">
                <div
                  className="px-3 py-2 text-xs font-bold uppercase tracking-wider"
                  style={{ color: info.color }}
                >
                  {info.label}
                </div>
                <div className="space-y-1">
                  {list.map((s) => (
                    <SetItem
                      key={s.code}
                      set={s}
                      isSelected={s.code === currentSet?.code}
                      onClick={() => selectSet(s.code)}
                    />
                  ))}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default PokemonSetSidebar;
