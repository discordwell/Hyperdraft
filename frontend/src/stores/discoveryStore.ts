/**
 * Discovery store — A1 of docs/design/buildplan.md.
 *
 * Tracks which engines the user has already played so the home page can
 * surface untouched engines ("the one you haven't played" — cabinet pitch
 * from docs/design/brand.md). The state is persisted to localStorage under
 * `hd.played_engines` as a JSON array of engine ids; the Wave 1 EnginePicker
 * already reads from this same key (see `EnginePicker.tsx::readPlayedEngines`)
 * so the two surfaces stay in sync without a cross-component subscription.
 *
 * The store accepts arbitrary string ids rather than the narrow GameModeId
 * union — CatsGameView and other not-yet-canonicalised engines need to mark
 * themselves played too, and the rack is the visibility filter anyway.
 */
import { create } from 'zustand';
import { LAB_ENGINES, type LabEngineMeta } from '../components/lab/engineMeta';

const STORAGE_KEY = 'hd.played_engines';

/**
 * Defensive read of the played-engines list from localStorage. Returns an
 * empty array on every failure mode (missing window, missing key, malformed
 * JSON, non-array payload, non-string entries) so callers never have to
 * try/catch. Matches the shim used by EnginePicker.
 */
function readFromStorage(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((v): v is string => typeof v === 'string');
  } catch {
    return [];
  }
}

function writeToStorage(ids: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // localStorage can throw (quota, disabled, etc.) — swallow, the
    // in-memory state still reflects the change for this session.
  }
}

interface DiscoveryStore {
  /** Ordered list of engine ids the user has played. */
  playedEngines: string[];
  /** Mark an engine as played. Idempotent — duplicates collapse. */
  markPlayed: (id: string) => void;
  /**
   * Return a random engine the user hasn't played yet, or `null` once
   * they've played every registered engine. The pool is sourced from
   * LAB_ENGINES, so it scales with the rack.
   */
  pickUnplayed: () => LabEngineMeta | null;
}

export const useDiscoveryStore = create<DiscoveryStore>((set, get) => ({
  playedEngines: readFromStorage(),

  markPlayed: (id) => {
    set((state) => {
      if (state.playedEngines.includes(id)) return state;
      const next = [...state.playedEngines, id];
      writeToStorage(next);
      return { playedEngines: next };
    });
  },

  pickUnplayed: () => {
    const { playedEngines } = get();
    const played = new Set(playedEngines);
    const candidates = LAB_ENGINES.filter((e) => !played.has(e.id));
    if (candidates.length === 0) return null;
    const idx = Math.floor(Math.random() * candidates.length);
    return candidates[idx];
  },
}));

/** Convenience hook — read the current set of played engine ids. */
export function usePlayedEngines(): string[] {
  return useDiscoveryStore((s) => s.playedEngines);
}
