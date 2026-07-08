"""In-app notifications: list, mark read, mark all read."""
from fastapi import APIRouter, Depends, Request

from db import notifications_col
from helpers import now_iso
from security import get_current_user, limiter

router = APIRouter()


@router.get("/notifications")
@limiter.limit("60/minute")
async def list_notifications(request: Request, user=Depends(get_current_user)):
    out = []
    async for n in notifications_col.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50):
        out.append(n)
    unread = await notifications_col.count_documents({"user_id": user["id"], "read": False})
    return {"notifications": out, "unread": unread}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user=Depends(get_current_user)):
    await notifications_col.update_one(
        {"id": notification_id, "user_id": user["id"]},
        {"$set": {"read": True, "read_at": now_iso()}},
    )
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(user=Depends(get_current_user)):
    await notifications_col.update_many(
        {"user_id": user["id"], "read": False},
        {"$set": {"read": True, "read_at": now_iso()}},
    )
    return {"ok": True}
