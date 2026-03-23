"""
WebSocket endpoint for real-time updates of conversation threads.
Uses Redis pub/sub to broadcast events from agent nodes to connected clients.
"""

import json
import asyncio
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect
from src.core.logging import get_logger
from src.services.redis_client import get_redis_client
from src.api.dependencies import get_pool, get_thread_repo, get_project_repo, get_current_user_id

logger = get_logger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections per thread.
    Each thread has a set of active connections.
    """
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, thread_id: str):
        await websocket.accept()
        if thread_id not in self.active_connections:
            self.active_connections[thread_id] = set()
        self.active_connections[thread_id].add(websocket)
        logger.debug("WebSocket connected", extra={"thread_id": thread_id})

    def disconnect(self, websocket: WebSocket, thread_id: str):
        if thread_id in self.active_connections:
            self.active_connections[thread_id].discard(websocket)
            if not self.active_connections[thread_id]:
                del self.active_connections[thread_id]
        logger.debug("WebSocket disconnected", extra={"thread_id": thread_id})

    async def broadcast(self, thread_id: str, message: dict):
        """Send message to all clients subscribed to this thread."""
        if thread_id not in self.active_connections:
            return
        data = json.dumps(message, default=str)
        for connection in self.active_connections[thread_id]:
            try:
                await connection.send_text(data)
            except Exception as e:
                logger.warning("Failed to send WebSocket message", extra={"error": str(e), "thread_id": thread_id})


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """
    WebSocket endpoint for real-time updates of a specific thread.
    Authentication: first message must contain a JWT token.
    """
    # Accept connection and wait for auth message
    await websocket.accept()
    try:
        # First message must be JSON with token
        auth_data = await websocket.receive_text()
        try:
            auth = json.loads(auth_data)
            token = auth.get("token")
        except json.JSONDecodeError:
            await websocket.send_text(json.dumps({"error": "Invalid auth format"}))
            await websocket.close(code=1008)
            return

        if not token:
            await websocket.send_text(json.dumps({"error": "Token required"}))
            await websocket.close(code=1008)
            return

        # Validate JWT and extract user_id
        try:
            user_id = await get_current_user_id(authorization=f"Bearer {token}")
        except Exception as e:
            logger.warning("WebSocket auth failed", extra={"error": str(e)})
            await websocket.send_text(json.dumps({"error": "Invalid token"}))
            await websocket.close(code=1008)
            return

        # Verify that the user has access to this thread (belongs to their project)
        pool = get_pool()
        thread_repo = get_thread_repo(pool)
        thread = await thread_repo.get_thread_with_project(thread_id)
        if not thread:
            await websocket.send_text(json.dumps({"error": "Thread not found"}))
            await websocket.close(code=1008)
            return

        # Check if user is owner of the project
        project_repo = get_project_repo(pool)
        project = await project_repo.get_project_by_id(thread["project_id"])
        if not project or project.get("user_id") != user_id:
            await websocket.send_text(json.dumps({"error": "Access denied"}))
            await websocket.close(code=1008)
            return

        # Successfully authenticated
        await websocket.send_text(json.dumps({"status": "connected", "thread_id": thread_id}))
        logger.info("WebSocket authenticated", extra={"thread_id": thread_id, "user_id": user_id})

        # Register connection
        await manager.connect(websocket, thread_id)

        # Get Redis client and start listener
        redis = await get_redis_client()

        async def listen_redis():
            """Subscribe to Redis channel for this thread and broadcast messages."""
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"thread:{thread_id}")
            logger.debug("Subscribed to Redis channel", extra={"channel": f"thread:{thread_id}"})
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode()
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            payload = {"raw": data}
                        await manager.broadcast(thread_id, payload)
            except asyncio.CancelledError:
                logger.debug("Redis listener cancelled", extra={"thread_id": thread_id})
            finally:
                await pubsub.unsubscribe(f"thread:{thread_id}")
                logger.debug("Unsubscribed from Redis channel", extra={"channel": f"thread:{thread_id}"})

        redis_task = asyncio.create_task(listen_redis())

        # Keep connection alive, handle incoming messages (not used for now)
        try:
            while True:
                # Just keep connection open; we don't expect messages from client
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            redis_task.cancel()
            manager.disconnect(websocket, thread_id)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WebSocket error", extra={"thread_id": thread_id, "error": str(e)})
        try:
            await websocket.close()
        except:
            pass
