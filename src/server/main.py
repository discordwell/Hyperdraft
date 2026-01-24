"""
Hyperdraft API Server

FastAPI application with Socket.IO for real-time game updates.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from .routes import match_router, cards_router, bot_game_router
from .session import session_manager
from .models import WSJoinMatch, PlayerActionRequest


# =============================================================================
# Socket.IO Setup
# =============================================================================

# Create Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=False
)


@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    print(f"Client connected: {sid}")
    await sio.emit('connected', {'sid': sid}, to=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    print(f"Client disconnected: {sid}")

    # Find and clean up any sessions this socket was in
    result = session_manager.get_session_by_socket(sid)
    if result:
        session, player_id = result
        session.disconnect_socket(sid)

        # Notify other players
        for pid, other_sid in session.player_sockets.items():
            await sio.emit('player_disconnected', {
                'player_id': player_id
            }, to=other_sid)


@sio.event
async def join_match(sid, data):
    """
    Join a match room.

    Expected data: { match_id: string, player_id: string }
    """
    try:
        match_id = data.get('match_id')
        player_id = data.get('player_id')

        if not match_id or not player_id:
            await sio.emit('error', {
                'message': 'match_id and player_id required'
            }, to=sid)
            return

        session = session_manager.get_session(match_id)
        if not session:
            await sio.emit('error', {
                'message': 'Match not found'
            }, to=sid)
            return

        # Connect socket to session
        session.connect_socket(player_id, sid)

        # Join Socket.IO room for this match
        sio.enter_room(sid, f"match_{match_id}")

        # Set up state change callback
        async def on_state_change(pid, state):
            socket_id = session.player_sockets.get(pid)
            if socket_id:
                await sio.emit('game_state', state, to=socket_id)

        session.on_state_change = on_state_change

        # Send current game state
        state = session.get_client_state(player_id)
        await sio.emit('game_state', state.model_dump(), to=sid)

        # Notify room
        await sio.emit('player_joined', {
            'player_id': player_id,
            'match_id': match_id
        }, room=f"match_{match_id}")

    except Exception as e:
        print(f"Error in join_match: {e}")
        await sio.emit('error', {'message': str(e)}, to=sid)


@sio.event
async def leave_match(sid, data):
    """
    Leave a match room.

    Expected data: { match_id: string }
    """
    match_id = data.get('match_id')
    if match_id:
        sio.leave_room(sid, f"match_{match_id}")

        session = session_manager.get_session(match_id)
        if session:
            player_id = session.disconnect_socket(sid)
            if player_id:
                await sio.emit('player_left', {
                    'player_id': player_id
                }, room=f"match_{match_id}")


@sio.event
async def player_action(sid, data):
    """
    Handle a player action via WebSocket.

    Expected data: PlayerActionRequest format
    """
    try:
        match_id = data.get('match_id')
        if not match_id:
            await sio.emit('error', {'message': 'match_id required'}, to=sid)
            return

        session = session_manager.get_session(match_id)
        if not session:
            await sio.emit('error', {'message': 'Match not found'}, to=sid)
            return

        # Build action request
        action = PlayerActionRequest(
            action_type=data.get('action_type', 'PASS'),
            player_id=data.get('player_id', ''),
            card_id=data.get('card_id'),
            targets=data.get('targets', []),
            x_value=data.get('x_value', 0),
            ability_id=data.get('ability_id'),
            source_id=data.get('source_id'),
            attackers=data.get('attackers', []),
            blockers=data.get('blockers', [])
        )

        success, message = await session.handle_action(action)

        if success:
            # Broadcast updated state to all players in match
            for pid, socket_id in session.player_sockets.items():
                state = session.get_client_state(pid)
                await sio.emit('game_state', state.model_dump(), to=socket_id)
        else:
            await sio.emit('action_error', {
                'success': False,
                'message': message
            }, to=sid)

    except Exception as e:
        print(f"Error in player_action: {e}")
        await sio.emit('error', {'message': str(e)}, to=sid)


@sio.event
async def spectate_game(sid, data):
    """
    Start spectating a bot game.

    Expected data: { game_id: string }
    """
    game_id = data.get('game_id')
    if not game_id:
        await sio.emit('error', {'message': 'game_id required'}, to=sid)
        return

    # Join spectator room
    sio.enter_room(sid, f"spectate_{game_id}")

    # Get current state
    from .routes.bot_game import active_bot_games
    session = active_bot_games.get(game_id)
    if session:
        state = session.get_client_state()
        await sio.emit('game_state', state.model_dump(), to=sid)
    else:
        await sio.emit('error', {'message': 'Game not found'}, to=sid)


@sio.event
async def stop_spectating(sid, data):
    """Stop spectating a game."""
    game_id = data.get('game_id')
    if game_id:
        sio.leave_room(sid, f"spectate_{game_id}")


# =============================================================================
# FastAPI Application
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("Hyperdraft API Server starting...")
    yield
    # Shutdown
    print("Hyperdraft API Server shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Hyperdraft API",
    description="MTG Arena-style game API with real-time updates",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(match_router, prefix="/api")
app.include_router(cards_router, prefix="/api")
app.include_router(bot_game_router, prefix="/api")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "hyperdraft-api"}


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Hyperdraft API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# Mount Socket.IO
socket_app = socketio.ASGIApp(sio, app)


# For running with uvicorn directly
def create_app():
    """Create the ASGI application."""
    return socket_app


# Main entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.server.main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
