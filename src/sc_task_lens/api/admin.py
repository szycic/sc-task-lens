"""Admin System Settings REST API Endpoint Router for SC Task Lens."""

import os
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from sc_task_lens.database import get_db
from sc_task_lens.models import SystemSettings, NotionConfig, NotionFieldMapping, AISettings, TaskCandidate, Screenshot
from sc_task_lens.schemas import (
    SystemSettingsOut, SystemSettingsUpdate, SystemDiagnosticsResponse,
    DiagnosticCheckResult, ConfigExportPayload, ConfigImportRequest
)
from sc_task_lens.services.notion_service import NotionService
from sc_task_lens.services.ai_service import AIService
from sc_task_lens.services.screenshot_service import ScreenshotService

router = APIRouter(prefix="/api/admin", tags=["Admin Settings"])


def get_or_create_system_settings(db: Session) -> SystemSettings:
    sys_set = db.query(SystemSettings).first()
    if not sys_set:
        sys_set = SystemSettings(
            ui_auto_refresh_enabled=True,
            ui_auto_refresh_interval_seconds=30,
            auto_purge_synced_enabled=False,
            purge_synced_days=30,
            auto_purge_ignored_enabled=False,
            purge_ignored_days=30
        )
        db.add(sys_set)
        db.commit()
        db.refresh(sys_set)
    return sys_set


@router.get("/settings", response_model=SystemSettingsOut)
def get_admin_settings(db: Session = Depends(get_db)):
    """Fetch current system administrative settings."""
    return get_or_create_system_settings(db)


@router.put("/settings", response_model=SystemSettingsOut)
def update_admin_settings(payload: SystemSettingsUpdate, db: Session = Depends(get_db)):
    """Update system administrative settings (UI auto-refresh and auto-purge retention)."""
    sys_set = get_or_create_system_settings(db)

    if payload.ui_auto_refresh_enabled is not None:
        sys_set.ui_auto_refresh_enabled = payload.ui_auto_refresh_enabled

    if payload.ui_auto_refresh_interval_seconds is not None:
        sys_set.ui_auto_refresh_interval_seconds = payload.ui_auto_refresh_interval_seconds

    if payload.auto_purge_synced_enabled is not None:
        sys_set.auto_purge_synced_enabled = payload.auto_purge_synced_enabled

    if payload.purge_synced_days is not None:
        sys_set.purge_synced_days = payload.purge_synced_days

    if payload.auto_purge_ignored_enabled is not None:
        sys_set.auto_purge_ignored_enabled = payload.auto_purge_ignored_enabled

    if payload.purge_ignored_days is not None:
        sys_set.purge_ignored_days = payload.purge_ignored_days

    db.commit()
    db.refresh(sys_set)
    return sys_set


@router.post("/diagnostics/run", response_model=SystemDiagnosticsResponse)
def run_system_diagnostics(db: Session = Depends(get_db)):
    """Run health & connection diagnostics across DB, Disk storage, Notion, and AI settings."""
    start_total = time.perf_counter()
    results = {}
    has_failed = False
    has_warning = False

    # 1. Database Check
    t0 = time.perf_counter()
    try:
        db.execute(text("PRAGMA integrity_check")).fetchone()
        t_db = round((time.perf_counter() - t0) * 1000, 2)
        results["db"] = DiagnosticCheckResult(
            name="SQLite Database",
            status="success",
            latency_ms=t_db,
            details="Database is healthy. Integrity check passed."
        )
    except Exception as e:
        has_failed = True
        results["db"] = DiagnosticCheckResult(
            name="SQLite Database",
            status="failed",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            details=f"Database integrity check failed: {str(e)}"
        )

    # 2. Local File System Check
    t0 = time.perf_counter()
    screenshot_dir = ScreenshotService.get_screenshot_dir()
    t_fs = round((time.perf_counter() - t0) * 1000, 2)
    try:
        test_file = screenshot_dir / ".diagnostics_write_test"
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        results["storage"] = DiagnosticCheckResult(
            name="Screenshot Storage",
            status="success",
            latency_ms=t_fs,
            details=f"Write permissions verified for directory: {screenshot_dir}"
        )
    except Exception as e:
        has_failed = True
        results["storage"] = DiagnosticCheckResult(
            name="Screenshot Storage",
            status="failed",
            latency_ms=t_fs,
            details=f"Failed to write to screenshot directory {screenshot_dir}: {str(e)}"
        )

    # 3. Notion API Check
    t0 = time.perf_counter()
    notion_cfg = db.query(NotionConfig).first()
    if not notion_cfg or not notion_cfg.api_token or not notion_cfg.database_id:
        results["notion"] = DiagnosticCheckResult(
            name="Notion API Authentication",
            status="warning",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            details="Notion API Token or Database ID is not configured."
        )
        has_warning = True
    else:
        notion_res = NotionService.fetch_database_schema(str(notion_cfg.api_token), str(notion_cfg.database_id))
        t_notion = round((time.perf_counter() - t0) * 1000, 2)
        if notion_res.get("success"):
            db_title = notion_res.get("database_title", "Target Database")
            results["notion"] = DiagnosticCheckResult(
                name="Notion API Authentication",
                status="success",
                latency_ms=t_notion,
                details=f"Notion API authenticated successfully (Connected to '{db_title}')."
            )
        else:
            results["notion"] = DiagnosticCheckResult(
                name="Notion API Authentication",
                status="failed",
                latency_ms=t_notion,
                details=f"Notion connection failed: {notion_res.get('error', 'Invalid token or DB ID')}"
            )
            has_failed = True

    # 4. AI Provider Check
    t0 = time.perf_counter()
    ai_set = db.query(AISettings).first()
    if not ai_set or ai_set.provider == "mock":
        results["ai"] = DiagnosticCheckResult(
            name="AI Extraction Engine",
            status="success",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            details="Offline Mock Engine active (Connection check bypassed)."
        )
    else:
        res_ai = AIService.test_ai_connection(
            str(ai_set.provider),
            str(ai_set.api_key or ""),
            str(ai_set.model_name or "")
        )
        t_ai = round((time.perf_counter() - t0) * 1000, 2)
        if res_ai.get("success"):
            results["ai"] = DiagnosticCheckResult(
                name="AI Extraction Engine",
                status="success",
                latency_ms=t_ai,
                details=res_ai.get("message", "AI provider test completed successfully.")
            )
        else:
            results["ai"] = DiagnosticCheckResult(
                name="AI Extraction Engine",
                status="failed",
                latency_ms=t_ai,
                details=f"AI connection failed: {res_ai.get('error', 'API test error')}"
            )
            has_failed = True

    overall = "error" if has_failed else ("warning" if has_warning else "ok")
    duration = round((time.perf_counter() - start_total) * 1000, 2)

    return SystemDiagnosticsResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        overall_status=overall,
        total_duration_ms=duration,
        results=results
    )


@router.get("/config/export")
def export_configuration(db: Session = Depends(get_db)):
    """Export system settings and Notion mappings as a JSON file backup."""
    sys_set = get_or_create_system_settings(db)
    mappings = db.query(NotionFieldMapping).all()
    
    sys_dict = {
        "ui_auto_refresh_enabled": sys_set.ui_auto_refresh_enabled,
        "ui_auto_refresh_interval_seconds": sys_set.ui_auto_refresh_interval_seconds,
        "auto_purge_synced_enabled": sys_set.auto_purge_synced_enabled,
        "purge_synced_days": sys_set.purge_synced_days,
        "auto_purge_ignored_enabled": sys_set.auto_purge_ignored_enabled,
        "purge_ignored_days": sys_set.purge_ignored_days
    }
    
    mapping_list = []
    for m in mappings:
        mapping_list.append({
            "task_field": m.task_field,
            "notion_property_name": m.notion_property_name,
            "notion_property_type": m.notion_property_type,
            "value_mappings_json": m.value_mappings_json
        })

    return {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "system_settings": sys_dict,
        "field_mappings": mapping_list
    }


@router.post("/config/import")
def import_configuration(payload: ConfigImportRequest, db: Session = Depends(get_db)):
    """Restore system configuration settings and database mappings from backup."""
    if payload.system_settings:
        sys_set = get_or_create_system_settings(db)
        d = payload.system_settings
        if "ui_auto_refresh_enabled" in d:
            sys_set.ui_auto_refresh_enabled = d["ui_auto_refresh_enabled"]
        if "ui_auto_refresh_interval_seconds" in d:
            sys_set.ui_auto_refresh_interval_seconds = d["ui_auto_refresh_interval_seconds"]
        if "auto_purge_synced_enabled" in d:
            sys_set.auto_purge_synced_enabled = d["auto_purge_synced_enabled"]
        if "purge_synced_days" in d:
            sys_set.purge_synced_days = d["purge_synced_days"]
        if "auto_purge_ignored_enabled" in d:
            sys_set.auto_purge_ignored_enabled = d["auto_purge_ignored_enabled"]
        if "purge_ignored_days" in d:
            sys_set.purge_ignored_days = d["purge_ignored_days"]

    if payload.field_mappings:
        for m in payload.field_mappings:
            task_field = m.get("task_field")
            if not task_field:
                continue
            mapping = db.query(NotionFieldMapping).filter(NotionFieldMapping.task_field == task_field).first()
            if not mapping:
                mapping = NotionFieldMapping(task_field=task_field)
                db.add(mapping)
            mapping.notion_property_name = m.get("notion_property_name", "")
            mapping.notion_property_type = m.get("notion_property_type", "rich_text")
            mapping.value_mappings_json = m.get("value_mappings_json")

    db.commit()
    return {"success": True, "message": "Configuration settings imported successfully!"}


@router.post("/danger/purge-ignored")
def purge_ignored_candidates(db: Session = Depends(get_db)):
    """Bulk delete all ignored candidates and clean up their screenshot images from disk."""
    ignored = db.query(TaskCandidate).filter(TaskCandidate.status == "IGNORED").all()
    count = 0
    for cand in ignored:
        if cand.screenshot:
            ScreenshotService.delete_screenshot(cand.screenshot.file_path)
            db.delete(cand.screenshot)
        db.delete(cand)
        count += 1
    db.commit()
    return {"success": True, "message": f"Successfully deleted {count} ignored candidate(s) and screenshot(s) from system."}


@router.post("/danger/reset-settings")
def reset_to_defaults(db: Session = Depends(get_db)):
    """Reset administrative system settings back to original defaults."""
    sys_set = get_or_create_system_settings(db)
    sys_set.ui_auto_refresh_enabled = True
    sys_set.ui_auto_refresh_interval_seconds = 30
    sys_set.auto_purge_synced_enabled = False
    sys_set.purge_synced_days = 30
    sys_set.auto_purge_ignored_enabled = False
    sys_set.purge_ignored_days = 30
    db.commit()
    return {"success": True, "message": "System administrative configuration reset to defaults."}
