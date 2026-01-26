/**
 * Set Sidebar Component
 *
 * Displays list of available sets grouped by type.
 */

import { useEffect } from 'react';
import { useGathererStore } from '../../stores/gathererStore';
import { SET_TYPE_INFO } from '../../types/gatherer';
import type { SetInfo, SetType } from '../../types/gatherer';

interface SetItemProps {
  set: SetInfo;
  isSelected: boolean;
  onClick: () => void;
}

function SetItem({ set, isSelected, onClick }: SetItemProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 rounded transition-all ${
        isSelected
          ? 'bg-game-accent text-white'
          : 'hover:bg-gray-700 text-gray-300'
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

interface SetGroupProps {
  type: SetType;
  sets: SetInfo[];
  currentSetCode: string | null;
  onSelectSet: (code: string) => void;
}

function SetGroup({ type, sets, currentSetCode, onSelectSet }: SetGroupProps) {
  const typeInfo = SET_TYPE_INFO[type];

  if (sets.length === 0) return null;

  return (
    <div className="mb-4">
      <div
        className="px-3 py-2 text-xs font-bold uppercase tracking-wider"
        style={{ color: typeInfo.color }}
      >
        {typeInfo.label}
      </div>
      <div className="space-y-1">
        {sets.map((set) => (
          <SetItem
            key={set.code}
            set={set}
            isSelected={set.code === currentSetCode}
            onClick={() => onSelectSet(set.code)}
          />
        ))}
      </div>
    </div>
  );
}

export function SetSidebar() {
  const {
    sets,
    setsLoading,
    setsError,
    currentSet,
    setTypeFilter,
    loadSets,
    selectSet,
    setSetTypeFilter,
  } = useGathererStore();

  useEffect(() => {
    loadSets();
  }, [loadSets]);

  // Group sets by type
  const groupedSets = sets.reduce(
    (acc, set) => {
      const type = set.set_type as SetType;
      if (!acc[type]) acc[type] = [];
      acc[type].push(set);
      return acc;
    },
    {} as Record<SetType, SetInfo[]>
  );

  const setTypes: SetType[] = ['standard', 'universes_beyond', 'custom'];

  return (
    <div className="w-64 bg-gray-900 border-r border-gray-700 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <h2 className="text-lg font-bold text-white">Sets</h2>
        <p className="text-xs text-gray-400 mt-1">
          {sets.length} sets, {sets.reduce((sum, s) => sum + s.card_count, 0).toLocaleString()} cards
        </p>
      </div>

      {/* Type Filter */}
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
          {setTypes.map((type) => (
            <button
              key={type}
              onClick={() => setSetTypeFilter(type)}
              className={`px-2 py-1 text-xs rounded ${
                setTypeFilter === type
                  ? 'bg-game-accent text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {SET_TYPE_INFO[type].label}
            </button>
          ))}
        </div>
      </div>

      {/* Set List */}
      <div className="flex-1 overflow-y-auto p-2">
        {setsLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-game-accent"></div>
          </div>
        ) : setsError ? (
          <div className="p-4 text-red-400 text-sm">{setsError}</div>
        ) : setTypeFilter ? (
          // Show flat list when filtered
          <div className="space-y-1">
            {sets.map((set) => (
              <SetItem
                key={set.code}
                set={set}
                isSelected={set.code === currentSet?.code}
                onClick={() => selectSet(set.code)}
              />
            ))}
          </div>
        ) : (
          // Show grouped when not filtered
          setTypes.map((type) => (
            <SetGroup
              key={type}
              type={type}
              sets={groupedSets[type] || []}
              currentSetCode={currentSet?.code || null}
              onSelectSet={selectSet}
            />
          ))
        )}
      </div>
    </div>
  );
}

export default SetSidebar;
