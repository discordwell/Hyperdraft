/**
 * Game State Store
 *
 * Zustand store for managing game state and player actions.
 */

import { create } from 'zustand';
import type {
  GameState,
  CardData,
  LegalActionData,
  ActionType,
  PlayerActionRequest,
} from '../types';

// UI State Types
export type TargetingMode = 'none' | 'single' | 'multiple';

export interface UIState {
  // Selected elements
  selectedCardId: string | null;
  selectedAction: LegalActionData | null;

  // Targeting
  targetingMode: TargetingMode;
  validTargets: string[];
  selectedTargets: string[];
  requiredTargetCount: number;

  // Combat
  selectedAttackers: string[];
  selectedBlockers: Map<string, string>; // blocker_id -> attacker_id

  // UI flags
  isLoading: boolean;
  error: string | null;
}

interface GameStore {
  // Connection state
  matchId: string | null;
  playerId: string | null;
  isConnected: boolean;
  isSpectator: boolean;

  // Game state
  gameState: GameState | null;

  // UI state
  ui: UIState;

  // Actions
  setConnection: (matchId: string, playerId: string, isSpectator?: boolean) => void;
  setConnected: (connected: boolean) => void;
  setGameState: (state: GameState) => void;
  clearGame: () => void;

  // Card selection
  selectCard: (cardId: string | null) => void;
  selectAction: (action: LegalActionData | null) => void;

  // Targeting
  startTargeting: (
    mode: TargetingMode,
    validTargets: string[],
    requiredCount?: number
  ) => void;
  addTarget: (targetId: string) => void;
  removeTarget: (targetId: string) => void;
  cancelTargeting: () => void;
  confirmTargets: () => string[];

  // Combat
  toggleAttacker: (creatureId: string) => void;
  setBlocker: (blockerId: string, attackerId: string | null) => void;
  clearCombatSelections: () => void;

  // Build action request
  buildActionRequest: () => PlayerActionRequest | null;

  // UI state
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Helpers
  getMyBattlefield: () => CardData[];
  getOpponentBattlefield: () => CardData[];
  getOpponentId: () => string | null;
  isMyTurn: () => boolean;
  canAct: () => boolean;
}

const initialUIState: UIState = {
  selectedCardId: null,
  selectedAction: null,
  targetingMode: 'none',
  validTargets: [],
  selectedTargets: [],
  requiredTargetCount: 1,
  selectedAttackers: [],
  selectedBlockers: new Map(),
  isLoading: false,
  error: null,
};

export const useGameStore = create<GameStore>((set, get) => ({
  // Initial state
  matchId: null,
  playerId: null,
  isConnected: false,
  isSpectator: false,
  gameState: null,
  ui: { ...initialUIState },

  // Connection
  setConnection: (matchId, playerId, isSpectator = false) =>
    set({ matchId, playerId, isSpectator }),

  setConnected: (connected) => set({ isConnected: connected }),

  setGameState: (state) =>
    set((prev) => ({
      gameState: state,
      // Clear combat selections when phase changes
      ui:
        prev.gameState?.phase !== state.phase
          ? { ...prev.ui, selectedAttackers: [], selectedBlockers: new Map() }
          : prev.ui,
    })),

  clearGame: () =>
    set({
      matchId: null,
      playerId: null,
      isConnected: false,
      isSpectator: false,
      gameState: null,
      ui: { ...initialUIState },
    }),

  // Card selection
  selectCard: (cardId) =>
    set((state) => ({
      ui: {
        ...state.ui,
        selectedCardId: cardId,
        selectedAction: null,
      },
    })),

  selectAction: (action) =>
    set((state) => ({
      ui: {
        ...state.ui,
        selectedAction: action,
        selectedCardId: action?.card_id || state.ui.selectedCardId,
      },
    })),

  // Targeting
  startTargeting: (mode, validTargets, requiredCount = 1) =>
    set((state) => ({
      ui: {
        ...state.ui,
        targetingMode: mode,
        validTargets,
        requiredTargetCount: requiredCount,
        selectedTargets: [],
      },
    })),

  addTarget: (targetId) =>
    set((state) => {
      const { ui } = state;
      if (!ui.validTargets.includes(targetId)) return state;
      if (ui.selectedTargets.includes(targetId)) return state;

      const newTargets = [...ui.selectedTargets, targetId];

      // For single target mode, auto-confirm when we have one
      if (ui.targetingMode === 'single' && newTargets.length >= ui.requiredTargetCount) {
        return {
          ui: {
            ...ui,
            selectedTargets: newTargets,
          },
        };
      }

      return {
        ui: {
          ...ui,
          selectedTargets: newTargets,
        },
      };
    }),

  removeTarget: (targetId) =>
    set((state) => ({
      ui: {
        ...state.ui,
        selectedTargets: state.ui.selectedTargets.filter((t) => t !== targetId),
      },
    })),

  cancelTargeting: () =>
    set((state) => ({
      ui: {
        ...state.ui,
        targetingMode: 'none',
        validTargets: [],
        selectedTargets: [],
        requiredTargetCount: 1,
        selectedAction: null,
      },
    })),

  confirmTargets: () => {
    const targets = get().ui.selectedTargets;
    set((state) => ({
      ui: {
        ...state.ui,
        targetingMode: 'none',
        validTargets: [],
        requiredTargetCount: 1,
      },
    }));
    return targets;
  },

  // Combat
  toggleAttacker: (creatureId) =>
    set((state) => {
      const { selectedAttackers } = state.ui;
      const newAttackers = selectedAttackers.includes(creatureId)
        ? selectedAttackers.filter((id) => id !== creatureId)
        : [...selectedAttackers, creatureId];
      return {
        ui: {
          ...state.ui,
          selectedAttackers: newAttackers,
        },
      };
    }),

  setBlocker: (blockerId, attackerId) =>
    set((state) => {
      const newBlockers = new Map(state.ui.selectedBlockers);
      if (attackerId) {
        newBlockers.set(blockerId, attackerId);
      } else {
        newBlockers.delete(blockerId);
      }
      return {
        ui: {
          ...state.ui,
          selectedBlockers: newBlockers,
        },
      };
    }),

  clearCombatSelections: () =>
    set((state) => ({
      ui: {
        ...state.ui,
        selectedAttackers: [],
        selectedBlockers: new Map(),
      },
    })),

  // Build action request
  buildActionRequest: () => {
    const { playerId, ui, gameState } = get();
    const { selectedAction, selectedTargets, selectedAttackers, selectedBlockers } = ui;

    if (!playerId || !selectedAction) return null;

    const request: PlayerActionRequest = {
      action_type: selectedAction.type as ActionType,
      player_id: playerId,
    };

    // Add card_id if present
    if (selectedAction.card_id) {
      request.card_id = selectedAction.card_id;
    }

    // Add ability info if present
    if (selectedAction.ability_id) {
      request.ability_id = selectedAction.ability_id;
      request.source_id = selectedAction.source_id || undefined;
    }

    // Add targets if we have them
    if (selectedTargets.length > 0) {
      request.targets = [selectedTargets];
    }

    // Add combat declarations
    if (selectedAction.type === 'DECLARE_ATTACKERS' && selectedAttackers.length > 0) {
      const opponentId = get().getOpponentId();
      request.attackers = selectedAttackers.map((id) => ({
        attacker_id: id,
        defending_player: opponentId || '',
      }));
    }

    if (selectedAction.type === 'DECLARE_BLOCKERS' && selectedBlockers.size > 0) {
      request.blockers = Array.from(selectedBlockers.entries()).map(
        ([blockerId, attackerId]) => ({
          blocker_id: blockerId,
          attacker_id: attackerId,
        })
      );
    }

    return request;
  },

  // UI state
  setLoading: (loading) =>
    set((state) => ({ ui: { ...state.ui, isLoading: loading } })),

  setError: (error) =>
    set((state) => ({ ui: { ...state.ui, error } })),

  // Helpers
  getMyBattlefield: () => {
    const { gameState, playerId } = get();
    if (!gameState || !playerId) return [];
    return gameState.battlefield.filter((c) => c.controller === playerId);
  },

  getOpponentBattlefield: () => {
    const { gameState, playerId } = get();
    if (!gameState || !playerId) return [];
    return gameState.battlefield.filter((c) => c.controller !== playerId);
  },

  getOpponentId: () => {
    const { gameState, playerId } = get();
    if (!gameState || !playerId) return null;
    const opponents = Object.keys(gameState.players).filter((id) => id !== playerId);
    return opponents[0] || null;
  },

  isMyTurn: () => {
    const { gameState, playerId } = get();
    return gameState?.active_player === playerId;
  },

  canAct: () => {
    const { gameState, playerId, isSpectator } = get();
    if (isSpectator) return false;
    return gameState?.priority_player === playerId;
  },
}));
