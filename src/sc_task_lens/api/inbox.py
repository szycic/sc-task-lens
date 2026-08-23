"""Inbox API Router for SC Task Lens.

Manages task candidate listing, stage transitions (PENDING, AI_PROCESSED, CREATED, IGNORED),
AI analysis execution, file uploads, Notion synchronization, and WebSocket status streaming.
"""

import asyncio
import uuid
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from sqlalchemy import func

from sc_task_lens.database import get_db, SessionLocal
from sc_task_lens.models import TaskCandidate, Screenshot
from sc_task_lens.schemas import TaskCandidateOut, TaskCandidateUpdate, PaginatedTaskCandidates, BatchCandidatesRequest
from sc_task_lens.services.screenshot_service import ScreenshotService
from sc_task_lens.services.ai_service import AIService
from sc_task_lens.services.notion_service import NotionService

router = APIRouter(prefix="/api/inbox", tags=["Inbox"])
LAST_SYNCED_AT: Optional[str] = None
IS_SYNCING: bool = False


class SyncWebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        disconnected = set()
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.active_connections.discard(conn)


sync_ws_manager = SyncWebSocketManager()


def set_last_synced_at() -> str:
    global LAST_SYNCED_AT
    LAST_SYNCED_AT = datetime.now(timezone.utc).isoformat()
    return LAST_SYNCED_AT


def compute_inbox_stats(db: Session) -> dict:
    global LAST_SYNCED_AT, IS_SYNCING
    counts_raw = db.query(TaskCandidate.status, func.count(TaskCandidate.id)).group_by(TaskCandidate.status).all()
    status_counts = {status: count for status, count in counts_raw}

    pending = status_counts.get("PENDING", 0)
    ai_processed = status_counts.get("AI_PROCESSED", 0)
    created = status_counts.get("CREATED", 0)
    ignored = status_counts.get("IGNORED", 0)
    total = sum(status_counts.values())

    last_synced = LAST_SYNCED_AT
    if not last_synced:
        latest = db.query(Screenshot).order_by(Screenshot.uploaded_at.desc()).first()
        if latest and latest.uploaded_at:
            dt = latest.uploaded_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            last_synced = dt.isoformat()

    return {
        "counts": {
            "PENDING": pending,
            "AI_PROCESSED": ai_processed,
            "CREATED": created,
            "IGNORED": ignored,
            "ALL": total
        },
        "last_synced_at": last_synced,
        "is_syncing": IS_SYNCING
    }


async def notify_inbox_updated_async():
    set_last_synced_at()
    db = SessionLocal()
    try:
        stats = compute_inbox_stats(db)
        await sync_ws_manager.broadcast({
            "event": "sync_completed",
            "stats": stats["counts"],
            "last_synced_at": stats["last_synced_at"],
            "is_syncing": False
        })
    except Exception:
        pass
    finally:
        db.close()


def notify_inbox_updated():
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(notify_inbox_updated_async())
    except RuntimeError:
        # Fallback if no running event loop in thread
        pass


def run_background_ai_analysis(candidate_id: int):
    """Run Vision LLM task candidate analysis in a background task."""
    db = SessionLocal()
    try:
        candidate = db.query(TaskCandidate).filter(TaskCandidate.id == candidate_id).first()
        if candidate and candidate.screenshot:
            AIService.analyze_screenshot(candidate.screenshot, db, allow_fallback=True)
            notify_inbox_updated()
    except Exception as e:
        print(f"Background AI extraction failed for candidate {candidate_id}: {e}")
    finally:
        db.close()


@router.post("/upload")
async def upload_screenshot(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a screenshot file and seed a task candidate in PENDING state."""
    # Validate mime type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image.")

    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix or ".png"
    filename = f"{file_id}{ext}"
    screenshot_dir = ScreenshotService.get_screenshot_dir()
    file_path = screenshot_dir / filename

    # Save local copy
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Create Screenshot record
    screenshot = Screenshot(
        filename=filename,
        file_path=str(file_path),
        is_processed=False
    )
    db.add(screenshot)
    db.commit()
    db.refresh(screenshot)

    # Initialize candidate in PENDING state
    candidate = AIService.ensure_candidate_from_screenshot(screenshot, db, title=file.filename)
    
    notify_inbox_updated()

    return {
        "success": True,
        "candidate_id": candidate.id,
        "filename": filename
    }


@router.get("/stats")
def get_inbox_stats(db: Session = Depends(get_db)):
    """Fetch current inbox metrics counts and last updated timestamp."""
    return compute_inbox_stats(db)


@router.get("/candidates")
def get_task_candidates(
    status: str = Query("PENDING"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query("NEWEST"),
    db: Session = Depends(get_db)
):
    """Retrieve filtered, sorted, and paginated task candidates list."""
    query = db.query(TaskCandidate)

    if status.upper() != "ALL":
        query = query.filter(TaskCandidate.status == status.upper())

    candidates = query.all()
    result = []

    for c in candidates:
        out = TaskCandidateOut.model_validate(c)
        if c.screenshot:
            out.screenshot_filename = c.screenshot.filename
            out.screenshot_url = ScreenshotService.get_screenshot_url(c.screenshot.filename)
            out.created_at = c.screenshot.uploaded_at

        # Search filter
        if search and search.strip():
            q = search.strip().lower()
            haystack = f"{out.title or ''} {out.summary or ''} {out.priority or ''} {out.project or ''}".lower()
            if q not in haystack:
                continue

        result.append(out)

    # Sorting
    sort_mode = sort_by.upper()
    if sort_mode == "OLDEST":
        result.sort(key=lambda item: item.id)
    elif sort_mode == "UPDATED_NEWEST":
        result.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
    elif sort_mode == "UPDATED_OLDEST":
        result.sort(key=lambda item: item.updated_at or item.created_at)
    else:  # NEWEST
        result.sort(key=lambda item: item.id, reverse=True)

    total = len(result)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_items = result[start_idx:end_idx]

    return PaginatedTaskCandidates(
        items=paginated_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/candidates/{candidate_id}", response_model=TaskCandidateOut)
def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """Fetch details of a single task candidate."""
    candidate = db.query(TaskCandidate).filter(TaskCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    out = TaskCandidateOut.model_validate(candidate)
    if candidate.screenshot:
        out.screenshot_filename = candidate.screenshot.filename
        out.screenshot_url = ScreenshotService.get_screenshot_url(candidate.screenshot.filename)
    return out


@router.put("/candidates/{candidate_id}", response_model=TaskCandidateOut)
def update_candidate(candidate_id: int, payload: TaskCandidateUpdate, db: Session = Depends(get_db)):
    """Update task candidate attributes."""
    candidate = db.query(TaskCandidate).filter(TaskCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(candidate, field, val)

    db.commit()
    db.refresh(candidate)
    notify_inbox_updated()

    out = TaskCandidateOut.model_validate(candidate)
    if candidate.screenshot:
        out.screenshot_filename = candidate.screenshot.filename
        out.screenshot_url = ScreenshotService.get_screenshot_url(candidate.screenshot.filename)
    return out


@router.post("/candidates/{candidate_id}/prepare-task", response_model=TaskCandidateOut)
def prepare_task_with_ai(
    candidate_id: int,
    force: bool = Query(False),
    allow_fallback: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Run AI Vision task extraction analysis on candidate."""
    candidate = db.query(TaskCandidate).filter(TaskCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if (candidate.status == "PENDING" or force) and candidate.screenshot:
        try:
            candidate = AIService.analyze_screenshot(candidate.screenshot, db, allow_fallback=allow_fallback)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        notify_inbox_updated()

    out = TaskCandidateOut.model_validate(candidate)
    if candidate.screenshot:
        out.screenshot_filename = candidate.screenshot.filename
        out.screenshot_url = ScreenshotService.get_screenshot_url(candidate.screenshot.filename)
    return out


@router.post("/candidates/{candidate_id}/create-task")
def create_notion_task_endpoint(candidate_id: int, db: Session = Depends(get_db)):
    """Upload screenshot and push task parameters to connected Notion database."""
    candidate = db.query(TaskCandidate).filter(TaskCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    res = NotionService.create_notion_task(candidate, db)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Sync to Notion failed."))

    notify_inbox_updated()
    return res


@router.post("/candidates/{candidate_id}/ignore", response_model=TaskCandidateOut)
def ignore_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """Mark candidate as IGNORED and remove from standard review list."""
    candidate = db.query(TaskCandidate).filter(TaskCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate.previous_status = candidate.status
    candidate.status = "IGNORED"
    db.commit()
    db.refresh(candidate)
    notify_inbox_updated()

    out = TaskCandidateOut.model_validate(candidate)
    if candidate.screenshot:
        out.screenshot_filename = candidate.screenshot.filename
        out.screenshot_url = ScreenshotService.get_screenshot_url(candidate.screenshot.filename)
    return out


@router.post("/candidates/{candidate_id}/unignore", response_model=TaskCandidateOut)
def unignore_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """Restore ignored candidate back to review list."""
    candidate = db.query(TaskCandidate).filter(TaskCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidate.status == "IGNORED":
        candidate.status = candidate.previous_status or "PENDING"
        candidate.previous_status = None
        db.commit()
        db.refresh(candidate)
        notify_inbox_updated()

    out = TaskCandidateOut.model_validate(candidate)
    if candidate.screenshot:
        out.screenshot_filename = candidate.screenshot.filename
        out.screenshot_url = ScreenshotService.get_screenshot_url(candidate.screenshot.filename)
    return out


@router.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """Permanently delete task candidate and associated screenshot file."""
    candidate = db.query(TaskCandidate).filter(TaskCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidate.screenshot:
        ScreenshotService.delete_screenshot(candidate.screenshot.file_path)
        db.delete(candidate.screenshot)

    db.delete(candidate)
    db.commit()
    notify_inbox_updated()
    return {"success": True, "message": "Task candidate and screenshot deleted successfully."}


@router.post("/candidates/batch-process")
def batch_process(payload: BatchCandidatesRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Run AI analysis on multiple candidates in background."""
    for cid in payload.candidate_ids:
        background_tasks.add_task(run_background_ai_analysis, cid)
    return {"success": True, "message": f"Queued {len(payload.candidate_ids)} candidates for AI Vision analysis."}


@router.post("/candidates/batch-ignore")
def batch_ignore(payload: BatchCandidatesRequest, db: Session = Depends(get_db)):
    """Batch move candidates to IGNORED status."""
    candidates = db.query(TaskCandidate).filter(TaskCandidate.id.in_(payload.candidate_ids)).all()
    for c in candidates:
        c.previous_status = c.status
        c.status = "IGNORED"
    db.commit()
    notify_inbox_updated()
    return {"success": True, "message": f"Successfully ignored {len(candidates)} candidate(s)."}


@router.post("/candidates/batch-unignore")
def batch_unignore(payload: BatchCandidatesRequest, db: Session = Depends(get_db)):
    """Batch restore ignored candidates."""
    candidates = db.query(TaskCandidate).filter(TaskCandidate.id.in_(payload.candidate_ids)).all()
    for c in candidates:
        if c.status == "IGNORED":
            c.status = c.previous_status or "PENDING"
            c.previous_status = None
    db.commit()
    notify_inbox_updated()
    return {"success": True, "message": f"Successfully restored {len(candidates)} candidate(s)."}


@router.delete("/clear-all")
def clear_all_inbox(db: Session = Depends(get_db)):
    """Purge all screenshots, generated files, and candidate mappings."""
    candidates = db.query(TaskCandidate).all()
    for c in candidates:
        if c.screenshot:
            ScreenshotService.delete_screenshot(c.screenshot.file_path)
            db.delete(c.screenshot)
        db.delete(c)
    db.commit()
    notify_inbox_updated()
    return {"success": True, "message": "Inbox purged completely."}


@router.websocket("/ws/sync-updates")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket stream to push real-time inbox state updates to dashboard clients."""
    await sync_ws_manager.connect(websocket)
    try:
        # Send initial state
        db = SessionLocal()
        try:
            stats = compute_inbox_stats(db)
            await websocket.send_json({
                "event": "connected",
                "stats": stats["counts"],
                "last_synced_at": stats["last_synced_at"],
                "is_syncing": False
            })
        finally:
            db.close()

        while True:
            # Keep-alive heartbeat loop
            await websocket.receive_text()
    except WebSocketDisconnect:
        sync_ws_manager.disconnect(websocket)
    except Exception:
        sync_ws_manager.disconnect(websocket)
