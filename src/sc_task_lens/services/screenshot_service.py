"""Screenshot File Management Service for SC Task Lens."""

import os
from pathlib import Path
from typing import Optional
from sc_task_lens.config import settings

class ScreenshotService:
    @staticmethod
    def get_screenshot_dir() -> Path:
        """Get or create the local screenshots storage directory."""
        path = Path(settings.DB_PATH).parent / "screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_screenshot_url(filename: str) -> str:
        """Generate static file access URL for an uploaded screenshot."""
        base = (settings.BASE_URL or "http://localhost:8000").rstrip("/")
        return f"{base}/static/screenshots/{filename}"

    @staticmethod
    def delete_screenshot(file_path: Optional[str]) -> bool:
        """Delete local screenshot file from disk."""
        if not file_path:
            return False
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                os.remove(path)
                return True
        except Exception:
            pass
        return False
