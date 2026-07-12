import asyncio
import json
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Dict, List
from app.database import get_db, get_tenant_db
from app.models.user import User
from app.dependencies import get_current_user
from app.services.auth_service import decode_access_token

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# In-memory WebSocket connection registry per user
_connections: Dict[str, List[WebSocket]] = {}


@router.websocket("/ws/{user_id}")
async def notification_ws(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time in-app notifications."""
    await websocket.accept()
    _connections.setdefault(user_id, []).append(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _connections[user_id].remove(websocket)


async def push_to_user(user_id: str, payload: dict) -> None:
    """Broadcast a notification to all active WebSocket connections for a user."""
    for ws in _connections.get(user_id, []):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


@router.get("/")
async def list_notifications(
    user: User = Depends(get_current_user),
):
    results = []
    async for tenant_db in get_tenant_db(user.schema_name):
        rows = await tenant_db.execute(text("""
            SELECT id, event_type, channel, subject, delivered, read, sent_at
            FROM notification_log ORDER BY sent_at DESC LIMIT 50
        """))
        results = [
            {
                "id": r[0], "event_type": r[1], "channel": r[2],
                "subject": r[3], "delivered": r[4], "read": r[5],
                "sent_at": str(r[6]),
            }
            for r in rows.fetchall()
        ]
    return results


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        await tenant_db.execute(
            text("UPDATE notification_log SET read=true WHERE id=:id"),
            {"id": notification_id},
        )
        await tenant_db.commit()
    return {"ok": True}
