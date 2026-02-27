"""
Learning progress routes.

GET  /api/v1/learn/progress          → list all completed lesson IDs for the current user
POST /api/v1/learn/progress          → mark a lesson complete  { lesson_id }
DELETE /api/v1/learn/progress/{lesson_id} → unmark a lesson
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api import db
from api.models import LessonProgressItem, LessonProgressList, MarkLessonRequest
from api.routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/learn", tags=["learn"])


@router.get("/progress", response_model=LessonProgressList)
async def get_progress(user=Depends(get_current_user)):
    """Return all lesson IDs the authenticated user has marked complete."""
    rows = await db.get_pool().fetch(
        """
        SELECT lesson_id, activity_id, completed_at
        FROM learn_progress
        WHERE user_id = $1
        ORDER BY completed_at DESC
        """,
        user["sub"],
    )
    items = [
        LessonProgressItem(
            lesson_id=r["lesson_id"],
            activity_id=r["activity_id"],
            completed_at=r["completed_at"],
        )
        for r in rows
    ]
    return LessonProgressList(items=items, total=len(items))


@router.post("/progress", response_model=LessonProgressItem, status_code=status.HTTP_201_CREATED)
async def mark_complete(body: MarkLessonRequest, user=Depends(get_current_user)):
    """Mark a lesson as complete for the authenticated user (idempotent)."""
    lesson_id = body.lesson_id.strip()
    if not lesson_id:
        raise HTTPException(status_code=400, detail="lesson_id must not be empty")

    # Extract activity_id from the dot-path prefix
    activity_id = lesson_id.split(".")[0] if "." in lesson_id else lesson_id

    row = await db.get_pool().fetchrow(
        """
        INSERT INTO learn_progress (user_id, activity_id, lesson_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, lesson_id) DO UPDATE
            SET completed_at = NOW()
        RETURNING lesson_id, activity_id, completed_at
        """,
        user["sub"],
        activity_id,
        lesson_id,
    )
    return LessonProgressItem(
        lesson_id=row["lesson_id"],
        activity_id=row["activity_id"],
        completed_at=row["completed_at"],
    )


@router.delete("/progress/{lesson_id:path}", status_code=status.HTTP_204_NO_CONTENT)
async def unmark_complete(lesson_id: str, user=Depends(get_current_user)):
    """Remove a completion record (mark lesson as not done)."""
    result = await db.get_pool().execute(
        "DELETE FROM learn_progress WHERE user_id = $1 AND lesson_id = $2",
        user["sub"],
        lesson_id,
    )
    # asyncpg returns "DELETE N" — no error if row didn't exist (idempotent)
    _ = result
