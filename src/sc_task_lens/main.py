"""FastAPI Application Entry Point for SC Task Lens.

Sets up application routes, static file serving, HTML templates,
lifespan background tasks, and initial default configuration.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from sc_task_lens.config import settings
from sc_task_lens.database import engine, Base, init_db, SessionLocal
from sc_task_lens.models import NotionConfig, NotionFieldMapping, AISettings, SystemSettings, TaskCandidate, Screenshot
from sc_task_lens.services.screenshot_service import ScreenshotService
from sc_task_lens.api import inbox, notion, ai, admin

logger = logging.getLogger("sc_task_lens.main")
logging.basicConfig(level=logging.INFO)

# Initialize database schema
init_db()


def setup_defaults(db: Session):
    """Seed initial default configurations for Notion, AI, and System settings."""
    notion_cfg = db.query(NotionConfig).first()
    if not notion_cfg:
        notion_cfg = NotionConfig(
            api_token=settings.NOTION_API_KEY,
            database_id=settings.NOTION_DATABASE_ID,
            database_title="Tasks DB"
        )
        db.add(notion_cfg)
    
    ai_set = db.query(AISettings).first()
    if not ai_set:
        db.add(AISettings(
            provider="mock",
            api_key=settings.OPENAI_API_KEY or settings.GEMINI_API_KEY or settings.GROQ_API_KEY or "",
            model_name="qwen/qwen3.6-27b"
        ))
        
    sys_set = db.query(SystemSettings).first()
    if not sys_set:
        db.add(SystemSettings(
            ui_auto_refresh_enabled=True,
            ui_auto_refresh_interval_seconds=30
        ))

    # Seed Notion field mappings
    default_mappings = [
        ("title", "Task Name", "title"),
        ("summary", "Description", "rich_text"),
        ("priority", "Priority", "select"),
        ("start_date", "Start Date", "date"),
        ("deadline", "Due Date", "date"),
        ("source_url", "URL", "url"),
        ("attachment", "Attachment", "files")
    ]

    for field, name, p_type in default_mappings:
        exists = db.query(NotionFieldMapping).filter(NotionFieldMapping.task_field == field).first()
        if not exists:
            db.add(NotionFieldMapping(
                task_field=field,
                notion_property_name=name,
                notion_property_type=p_type
            ))

    # Delete project mapping from db if it exists
    db.query(NotionFieldMapping).filter(NotionFieldMapping.task_field == "project").delete()
    db.commit()


def purge_expired_candidates(db: Session):
    """Purge candidates synced to Notion or Ignored (and screenshots) older than configured retention days."""
    try:
        sys_set = db.query(SystemSettings).first()
        if not sys_set:
            return

        now = datetime.now(timezone.utc)

        def purge_status_items(status_code: str, retention_days: int):
            cutoff = now - timedelta(days=retention_days)
            expired_candidates = db.query(TaskCandidate).filter(
                TaskCandidate.status == status_code,
                TaskCandidate.updated_at <= cutoff
            ).all()

            for cand in expired_candidates:
                if cand.screenshot:
                    ScreenshotService.delete_screenshot(cand.screenshot.file_path)
                    db.delete(cand.screenshot)
                db.delete(cand)

        if sys_set.auto_purge_synced_enabled and sys_set.purge_synced_days > 0:
            purge_status_items("CREATED", sys_set.purge_synced_days)

        if sys_set.auto_purge_ignored_enabled and sys_set.purge_ignored_days > 0:
            purge_status_items("IGNORED", sys_set.purge_ignored_days)

        db.commit()
    except Exception as err:
        logger.error(f"Auto-purge execution error: {err}")


async def background_purge_scheduler():
    """Background task to run candidate purging rules every 12 hours."""
    while True:
        try:
            db = SessionLocal()
            try:
                purge_expired_candidates(db)
            finally:
                db.close()
            # Wait for 12 hours
            await asyncio.sleep(12 * 3600)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Purge scheduler exception: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application background lifecycle tasks on startup and shutdown."""
    db = SessionLocal()
    try:
        setup_defaults(db)
    finally:
        db.close()

    purge_task = asyncio.create_task(background_purge_scheduler())
    yield
    purge_task.cancel()
    try:
        await purge_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Mount screenshots directory to serve them statically to dashboard clients
screenshots_dir = ScreenshotService.get_screenshot_dir()
app.mount("/static/screenshots", StaticFiles(directory=str(screenshots_dir)), name="screenshots")

# Mount static files folder
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

# Add API routes
app.include_router(inbox.router)
app.include_router(notion.router)
app.include_router(ai.router)
app.include_router(admin.router)


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/inbox")


@app.get("/sw.js")
def get_sw():
    return FileResponse(os.path.join(static_dir, "js", "sw.js"), media_type="application/javascript")


@app.get("/inbox")
@app.get("/notion")
@app.get("/ai")
@app.get("/admin")
def index_page(request: Request):
    """Serve single-page app index HTML template."""
    return templates.TemplateResponse(request=request, name="index.html", context={"app_version": settings.VERSION})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sc_task_lens.main:app", host=settings.HOST, port=settings.PORT, reload=True)
