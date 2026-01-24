/**
 * useSocket Hook
 *
 * Manages Socket.IO connection lifecycle and state synchronization.
 */

import { useEffect, useCallback, useRef } from 'react';
import { useGameStore } from '../stores/gameStore';
import {
  initSocket,
  setHandlers,
  joinMatch,
  leaveMatch,
  sendAction,
  spectateGame,
  stopSpectating,
  disconnectSocket,
} from '../services/socket';
import type { PlayerActionRequest, GameState } from '../types';

interface UseSocketOptions {
  matchId?: string;
  playerId?: string;
  isSpectator?: boolean;
  onError?: (message: string) => void;
}

export function useSocket(options: UseSocketOptions = {}) {
  const { matchId, playerId, isSpectator = false, onError } = options;

  const storeIsConnected = useGameStore((state) => state.isConnected);
  const setConnected = useGameStore((state) => state.setConnected);
  const setGameState = useGameStore((state) => state.setGameState);
  const setError = useGameStore((state) => state.setError);

  const initializedRef = useRef(false);
  const currentMatchRef = useRef<string | null>(null);

  // Handle game state updates
  const handleGameState = useCallback(
    (state: GameState) => {
      setGameState(state);
    },
    [setGameState]
  );

  // Handle errors
  const handleError = useCallback(
    (error: { message: string }) => {
      setError(error.message);
      onError?.(error.message);
    },
    [setError, onError]
  );

  // Initialize socket on mount
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    initSocket({
      onGameState: handleGameState,
      onError: handleError,
      onConnect: () => setConnected(true),
      onDisconnect: () => setConnected(false),
      onActionError: (data) => {
        if (!data.success) {
          setError(data.message);
        }
      },
    });

    return () => {
      disconnectSocket();
      setConnected(false);
    };
  }, [handleGameState, handleError, setConnected, setError]);

  // Update handlers when callbacks change
  useEffect(() => {
    setHandlers({
      onGameState: handleGameState,
      onError: handleError,
    });
  }, [handleGameState, handleError]);

  // Join/leave match when matchId changes
  useEffect(() => {
    // Leave previous match if any
    if (currentMatchRef.current && currentMatchRef.current !== matchId) {
      if (isSpectator) {
        stopSpectating(currentMatchRef.current);
      } else {
        leaveMatch(currentMatchRef.current);
      }
    }

    // Join new match
    if (matchId && storeIsConnected) {
      currentMatchRef.current = matchId;

      if (isSpectator) {
        spectateGame(matchId);
      } else if (playerId) {
        joinMatch(matchId, playerId);
      }
    }

    return () => {
      if (currentMatchRef.current) {
        if (isSpectator) {
          stopSpectating(currentMatchRef.current);
        } else {
          leaveMatch(currentMatchRef.current);
        }
        currentMatchRef.current = null;
      }
    };
  }, [matchId, playerId, isSpectator, storeIsConnected]);

  // Send action helper
  const sendGameAction = useCallback(
    (action: PlayerActionRequest) => {
      if (!matchId) {
        console.error('No match ID set');
        return;
      }
      sendAction(matchId, action);
    },
    [matchId]
  );

  return {
    isConnected: storeIsConnected,
    sendAction: sendGameAction,
  };
}
