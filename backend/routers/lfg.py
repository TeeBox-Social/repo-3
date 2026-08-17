"""Looking-for-Group interest workflow: request to join, organizer accept/decline.

Kept as its own router since it's a distinct sub-domain of ``rounds`` (an LFG
post is a ``rounds_col`` document with ``post_type == "lfg"``), but the
request/accept/decline lifecycle lives in its own ``lfg_interests`` collection
rather than being crammed into the round document itself.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from db import lfg_interests_col, rounds_col, users_col
from helpers import emit_notification, now_iso, public_user
from security import get_current_user

router = APIRouter()


async def _lfg_counts(round_id: str, looking_for_count) -> tuple[int, int, "int | None"]:
    accepted = await lfg_interests_col.count_documents({"round_id": round_id, "status": "accepted"})
    pending = await lfg_interests_col.count_documents({"round_id": round_id, "status": "pending"})
    remaining = max(0, looking_for_count - accepted) if looking_for_count else None
    return accepted, pending, remaining


@router.post("/rounds/{round_id}/lfg/interest")
async def toggle_interest(round_id: str, user=Depends(get_current_user)):
    """Express interest ("I'm in!"). Tapping again withdraws a pending request.
    A previously-declined request can be re-sent (resets to pending)."""
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Post not found")
    if r.get("post_type") != "lfg":
        raise HTTPException(status_code=400, detail="Not a Looking-for-Group post")
    if r["user_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="You can't join your own post")

    existing = await lfg_interests_col.find_one({"round_id": round_id, "user_id": user["id"]})

    if existing and existing["status"] == "accepted":
        raise HTTPException(status_code=400, detail="You're already confirmed for this round")

    if existing and existing["status"] == "pending":
        # Withdraw the request — no notification noise on withdrawal.
        await lfg_interests_col.delete_one({"id": existing["id"]})
        accepted, pending, remaining = await _lfg_counts(round_id, r.get("looking_for_count"))
        return {
            "status": None,
            "interest_id": None,
            "lfg_accepted_count": accepted,
            "lfg_pending_count": pending,
            "lfg_spots_remaining": remaining,
        }

    # Fresh request, or re-request after a decline.
    _, _, spots_remaining = await _lfg_counts(round_id, r.get("looking_for_count"))
    if spots_remaining == 0:
        raise HTTPException(status_code=400, detail="This round is already full")

    if existing:  # previously declined — reset to pending
        interest_id = existing["id"]
        await lfg_interests_col.update_one(
            {"id": interest_id},
            {"$set": {"status": "pending", "created_at": now_iso()}, "$unset": {"responded_at": ""}},
        )
    else:
        interest_id = str(uuid.uuid4())
        await lfg_interests_col.insert_one({
            "id": interest_id,
            "round_id": round_id,
            "user_id": user["id"],
            "status": "pending",
            "created_at": now_iso(),
        })

    await emit_notification(
        user_id=r["user_id"],
        pref_key="lfg_interest",
        type_="lfg_interest",
        title="Someone wants to join your round",
        body=f'{user.get("display_name") or "Someone"} said they\u2019re in for your round.',
        extra={
            "round_id": round_id,
            "interest_id": interest_id,
            "actor_id": user["id"],
            "actor_name": user.get("display_name"),
        },
    )
    accepted, pending, remaining = await _lfg_counts(round_id, r.get("looking_for_count"))
    return {
        "status": "pending",
        "interest_id": interest_id,
        "lfg_accepted_count": accepted,
        "lfg_pending_count": pending,
        "lfg_spots_remaining": remaining,
    }


@router.get("/rounds/{round_id}/lfg/interests")
async def list_interests(round_id: str, user=Depends(get_current_user)):
    """Organizer-only: list everyone who has asked to join, oldest first."""
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Post not found")
    if r["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the organizer can view join requests")
    out = []
    async for it in lfg_interests_col.find({"round_id": round_id}, {"_id": 0}).sort("created_at", 1):
        u = await users_col.find_one({"id": it["user_id"]}, {"_id": 0, "hashed_password": 0})
        out.append({**it, "user": public_user(u) if u else None})
    return out


async def _respond(round_id: str, interest_id: str, new_status: str, user: dict):
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Post not found")
    if r["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the organizer can respond to requests")
    it = await lfg_interests_col.find_one({"id": interest_id, "round_id": round_id})
    if not it:
        raise HTTPException(status_code=404, detail="Request not found")

    await lfg_interests_col.update_one(
        {"id": interest_id}, {"$set": {"status": new_status, "responded_at": now_iso()}},
    )
    accepted, pending, remaining = await _lfg_counts(round_id, r.get("looking_for_count"))
    await emit_notification(
        user_id=it["user_id"],
        pref_key="lfg_response",
        type_="lfg_response",
        title="You're confirmed!" if new_status == "accepted" else "Round update",
        body=(
            f'{user.get("display_name") or "The organizer"} confirmed you for the round at '
            f'{r.get("course_name") or "the meetup"}.'
            if new_status == "accepted" else
            f'{user.get("display_name") or "The organizer"} said this round is no longer available for you.'
        ),
        extra={
            "round_id": round_id,
            "interest_id": interest_id,
            "actor_id": user["id"],
            "actor_name": user.get("display_name"),
        },
    )
    return {
        "ok": True,
        "status": new_status,
        "lfg_accepted_count": accepted,
        "lfg_pending_count": pending,
        "lfg_spots_remaining": remaining,
    }


@router.post("/rounds/{round_id}/lfg/interests/{interest_id}/accept")
async def accept_interest(round_id: str, interest_id: str, user=Depends(get_current_user)):
    return await _respond(round_id, interest_id, "accepted", user)


@router.post("/rounds/{round_id}/lfg/interests/{interest_id}/decline")
async def decline_interest(round_id: str, interest_id: str, user=Depends(get_current_user)):
    return await _respond(round_id, interest_id, "declined", user)
