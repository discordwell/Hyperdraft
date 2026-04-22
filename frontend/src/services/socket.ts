/**
 * Socket.IO Client Service
 *
 * Manages real-time WebSocket connections to the game server.
 */

import { io, Socket } from 'socket.io-client';
import type { GameState, PlayerActionRequest } from '../types';

// Socket instance
let socket: Socket | null = null;

// Event handlers
type GameStateHandler = (state: GameState) => void;
type ErrorHandler = (error: { message: string; code?: string }) => void;
type ConnectionHandler = (data: { sid: string }) => void;
type PlayerEventHandler = (data: { player_id: string; match_id?: string }) => void;

interface SocketHandlers {
  onGameState?: GameStateHandler;
  onError?: ErrorHandler;
  onConnect?: ConnectionHandler;
  onDisconnect?: () => void;
  onPlayerJoined?: PlayerEventHandler;
  onPlayerLeft?: PlayerEventHandler;
  onPlayerDisconnected?: PlayerEventHandler;
  onActionError?: (data: { success: boolean; message: string }) => void;
}

let handlers: SocketHandlers = {};

/**
 * Initialize the socket connection
 */
export function initSocket(customHandlers: SocketHandlers = {}): Socket {
  if (socket?.connected) {
    return socket;
  }

  handlers = customHandlers;

  // Create socket connection
  socket = io({
    path: '/socket.io',
    transports: ['websocket', 'polling'],
    autoConnect: true,
  });

  // Set up event listeners
  socket.on('connect', () => {
    if (import.meta.env.DEV) console.log('Socket connected:', socket?.id);
    // Mark connected on the built-in event. The custom 'connected' event from
    // the server (below) was the only path updating state, which left the UI
    // stuck on "Disconnected" whenever the server-side handler dropped or
    // raced with the reconnect, even though the socket was fully alive.
    handlers.onConnect?.({ sid: socket?.id ?? '' });
  });

  socket.on('disconnect', (reason) => {
    if (import.meta.env.DEV) console.log('Socket disconnected:', reason);
    handlers.onDisconnect?.();
  });

  socket.on('connected', (data: { sid: string }) => {
    if (import.meta.env.DEV) console.log('Server acknowledged connection:', data.sid);
    handlers.onConnect?.(data);
  });

  socket.on('game_state', (state: GameState) => {
    handlers.onGameState?.(state);
  });

  socket.on('error', (error: { message: string; code?: string }) => {
    console.error('Socket error:', error);
    handlers.onError?.(error);
  });

  socket.on('player_joined', (data: { player_id: string; match_id: string }) => {
    handlers.onPlayerJoined?.(data);
  });

  socket.on('player_left', (data: { player_id: string }) => {
    handlers.onPlayerLeft?.(data);
  });

  socket.on('player_disconnected', (data: { player_id: string }) => {
    handlers.onPlayerDisconnected?.(data);
  });

  socket.on('action_error', (data: { success: boolean; message: string }) => {
    handlers.onActionError?.(data);
  });

  return socket;
}

/**
 * Get the current socket instance
 */
export function getSocket(): Socket | null {
  return socket;
}

/**
 * Update event handlers
 */
export function setHandlers(newHandlers: SocketHandlers): void {
  handlers = { ...handlers, ...newHandlers };
}

/**
 * Join a match room
 */
export function joinMatch(matchId: string, playerId: string): void {
  if (!socket?.connected) {
    console.error('Socket not connected');
    return;
  }

  socket.emit('join_match', { match_id: matchId, player_id: playerId });
}

/**
 * Leave a match room
 */
export function leaveMatch(matchId: string): void {
  if (!socket?.connected) return;

  socket.emit('leave_match', { match_id: matchId });
}

/**
 * Send a player action via WebSocket
 */
export function sendAction(matchId: string, action: PlayerActionRequest): void {
  if (!socket?.connected) {
    console.error('Socket not connected');
    return;
  }

  socket.emit('player_action', {
    match_id: matchId,
    ...action,
  });
}

/**
 * Start spectating a bot game
 */
export function spectateGame(gameId: string): void {
  if (!socket?.connected) {
    console.error('Socket not connected');
    return;
  }

  socket.emit('spectate_game', { game_id: gameId });
}

/**
 * Stop spectating a game
 */
export function stopSpectating(gameId: string): void {
  if (!socket?.connected) return;

  socket.emit('stop_spectating', { game_id: gameId });
}

/**
 * Disconnect the socket
 */
export function disconnectSocket(): void {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}

/**
 * Check if socket is connected
 */
export function isConnected(): boolean {
  return socket?.connected ?? false;
}
