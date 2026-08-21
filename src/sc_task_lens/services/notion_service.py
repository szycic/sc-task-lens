import httpx
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sc_task_lens.models import TaskCandidate, Screenshot, NotionConfig, NotionFieldMapping

logger = logging.getLogger(__name__)
NOTION_API_VERSION = "2022-06-28"

def extract_notion_id(val: str) -> str:
    """Extract a 32-character hexadecimal Notion ID from a raw ID, UUID, or full Notion URL."""
    if not val:
        return ""
    val_clean = val.strip()
    match = re.search(r'([0-9a-fA-F]{8})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{12})', val_clean)
    if match:
        return match.group(0).replace("-", "").lower()
    return val_clean.replace("-", "").strip().lower()


class NotionService:
    @staticmethod
    def upload_file(client: httpx.Client, api_token: str, file_path: Path, filename: str) -> Optional[str]:
        """
        Upload a local file to Notion file server using 2-step Notion file upload API:
        1. POST /v1/file_uploads with {"mode": "single_part", "filename": filename}
        2. POST /v1/file_uploads/{id}/send with multipart/form-data
        Returns the file_upload_id if successful, or None if failed.
        """
        if not file_path or not file_path.exists():
            logger.warning(f"File does not exist for Notion upload: {file_path}")
            return None

        headers = {
            "Authorization": f"Bearer {api_token.strip()}",
            "Notion-Version": NOTION_API_VERSION,
        }

        # Step 1: Create Notion upload
        create_url = "https://api.notion.com/v1/file_uploads"
        try:
            init_res = client.post(
                create_url,
                headers={**headers, "Content-Type": "application/json"},
                json={"mode": "single_part", "filename": filename}
            )
            if init_res.status_code not in (200, 201):
                logger.error(f"Failed to create Notion file upload ({init_res.status_code}): {init_res.text}")
                return None

            init_data = init_res.json()
            upload_id = init_data.get("id")
            if not upload_id:
                logger.error(f"Notion file upload creation returned no ID: {init_data}")
                return None

            # Step 2: Send file content via multipart/form-data
            send_url = init_data.get("upload_url") or f"https://api.notion.com/v1/file_uploads/{upload_id}/send"
            
            # Determine content type
            ext = file_path.suffix.lower()
            content_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

            with open(file_path, "rb") as f:
                files = {"file": (filename, f, content_type)}
                send_res = client.post(send_url, headers=headers, files=files)

            if send_res.status_code not in (200, 201):
                logger.error(f"Failed to send file content to Notion ({send_res.status_code}): {send_res.text}")
                return None

            logger.info(f"Successfully uploaded file '{filename}' to Notion with file_upload_id: {upload_id}")
            return upload_id
        except Exception as err:
            logger.error(f"Exception during Notion file upload: {err}")
            return None

    @staticmethod
    def get_headers(api_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {api_token.strip()}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json"
        }

    @staticmethod
    def fetch_database_schema(api_token: str, database_id: str) -> Dict[str, Any]:
        """Fetch database properties and schema from Notion API."""
        clean_db_id = extract_notion_id(database_id)
        candidate_ids = [clean_db_id, clean_db_id.replace("-", "")]
        last_res = None
        
        try:
            with httpx.Client(timeout=10.0) as client:
                for target_id in candidate_ids:
                    url = f"https://api.notion.com/v1/databases/{target_id}"
                    res = client.get(url, headers=NotionService.get_headers(api_token))
                    if res.status_code == 200:
                        last_res = res
                        break
                    last_res = res

                if not last_res or last_res.status_code != 200:
                    error_msg = last_res.json().get("message", last_res.text) if last_res else "Unknown error"
                    return {"success": False, "error": f"Notion API error ({last_res.status_code if last_res else '400'}): {error_msg}"}
                
                data = last_res.json()
                db_title = ""
                if data.get("title") and len(data["title"]) > 0:
                    db_title = data["title"][0].get("plain_text", "")

                properties_out = []
                for prop_name, prop_data in data.get("properties", {}).items():
                    p_type = prop_data.get("type")
                    options = []
                    
                    if p_type == "select" and "select" in prop_data:
                        options = [opt["name"] for opt in prop_data["select"].get("options", [])]
                    elif p_type == "multi_select" and "multi_select" in prop_data:
                        options = [opt["name"] for opt in prop_data["multi_select"].get("options", [])]
                    elif p_type == "status" and "status" in prop_data:
                        options = [opt["name"] for opt in prop_data["status"].get("options", [])]
                    elif p_type == "relation" and "relation" in prop_data:
                        rel_db_id = prop_data["relation"].get("database_id")
                        if rel_db_id:
                            options = NotionService.fetch_related_pages(client, api_token, rel_db_id)

                    properties_out.append({
                        "name": prop_name,
                        "type": p_type,
                        "options": options
                    })

                return {
                    "success": True,
                    "database_title": db_title or "Untitled Database",
                    "properties": properties_out,
                    "raw_schema": data.get("properties", {})
                }
        except Exception as e:
            return {"success": False, "error": f"Failed to connect to Notion: {str(e)}"}

    @staticmethod
    def fetch_related_pages(client: httpx.Client, api_token: str, database_id: str) -> List[Dict[str, str]]:
        """Query related Notion database to fetch page titles and IDs for relation properties."""
        clean_db_id = extract_notion_id(database_id)
        url = f"https://api.notion.com/v1/databases/{clean_db_id}/query"
        try:
            res = client.post(url, headers=NotionService.get_headers(api_token), json={"page_size": 100})
            if res.status_code == 200:
                results = res.json().get("results", [])
                pages = []
                for page in results:
                    page_id = page.get("id")
                    title = ""
                    for p_val in page.get("properties", {}).values():
                        if p_val.get("type") == "title" and p_val.get("title"):
                            title = p_val["title"][0].get("plain_text", "")
                            break
                    if page_id:
                        pages.append({"name": title or "Untitled Page", "id": page_id})
                return pages
        except Exception as e:
            print(f"Error fetching related pages for db {database_id}: {e}")
        return []

    @staticmethod
    def create_notion_task(candidate: TaskCandidate, db: Session) -> Dict[str, Any]:
        """Dynamically create Notion page based on active custom field mappings."""
        config = db.query(NotionConfig).first()
        if not config or not config.api_token or not config.database_id:
            return {"success": False, "error": "Notion API key or Database ID is not configured."}

        mappings = db.query(NotionFieldMapping).all()
        if not mappings:
            return {"success": False, "error": "No Notion field mappings configured. Please set up custom field mappings in settings."}

        screenshot = candidate.screenshot
        screenshot_filename = screenshot.filename if screenshot else "screenshot.png"
        screenshot_path = Path(screenshot.file_path) if screenshot else None

        from sc_task_lens.services.screenshot_service import ScreenshotService
        screenshot_url = ScreenshotService.get_screenshot_url(screenshot_filename) if screenshot else ""

        candidate_values = {
            "title": candidate.title,
            "summary": candidate.summary or "",
            "priority": candidate.priority or "MEDIUM",
            "start_date": candidate.start_date or "",
            "deadline": candidate.deadline or "",
            "source_url": candidate.source_url or "",
            "project": candidate.project or "",
            "attachment": screenshot_url
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                file_upload_id = None
                if screenshot_path and screenshot_path.exists():
                    file_upload_id = NotionService.upload_file(client, config.api_token, screenshot_path, screenshot_filename)

                notion_properties = {}

                for mapping in mappings:
                    if not mapping.notion_property_name or mapping.notion_property_name == "-- Ignore / None --":
                        continue

                    raw_val = candidate_values.get(mapping.task_field, "")
                    
                    if mapping.value_mappings_json and raw_val:
                        try:
                            val_map = json.loads(mapping.value_mappings_json)
                            if isinstance(val_map, dict) and raw_val in val_map and val_map[raw_val]:
                                raw_val = val_map[raw_val]
                        except Exception:
                            pass

                    p_type = mapping.notion_property_type
                    p_name = mapping.notion_property_name

                    if p_type == "title":
                        notion_properties[p_name] = {
                            "title": [{"text": {"content": str(raw_val)[:2000]}}]
                        }
                    elif p_type == "rich_text":
                        if raw_val:
                            notion_properties[p_name] = {
                                "rich_text": [{"text": {"content": str(raw_val)[:2000]}}]
                            }
                    elif p_type == "select":
                        if raw_val:
                            notion_properties[p_name] = {
                                "select": {"name": str(raw_val)[:100]}
                            }
                    elif p_type == "status":
                        if raw_val:
                            notion_properties[p_name] = {
                                "status": {"name": str(raw_val)[:100]}
                            }
                    elif p_type == "date":
                        if raw_val:
                            date_iso = NotionService._format_date_string(str(raw_val))
                            if date_iso:
                                notion_properties[p_name] = {
                                    "date": {"start": date_iso}
                                }
                    elif p_type == "url":
                        if raw_val and (str(raw_val).startswith("http://") or str(raw_val).startswith("https://")):
                            notion_properties[p_name] = {
                                "url": str(raw_val)[:1000]
                            }
                    elif p_type == "files":
                        if file_upload_id:
                            notion_properties[p_name] = {
                                "files": [{
                                    "type": "file_upload",
                                    "file_upload": {
                                        "id": file_upload_id
                                    },
                                    "name": screenshot_filename
                                }]
                            }
                        elif raw_val and (str(raw_val).startswith("http://") or str(raw_val).startswith("https://")):
                            notion_properties[p_name] = {
                                "files": [{
                                    "name": screenshot_filename,
                                    "type": "external",
                                    "external": {"url": str(raw_val)[:1000]}
                                }]
                            }
                    elif p_type == "checkbox":
                        notion_properties[p_name] = {
                            "checkbox": bool(raw_val)
                        }

                # Construct creation payload
                payload = {
                    "parent": {"database_id": extract_notion_id(config.database_id)},
                    "properties": notion_properties
                }

                # Create the task page in Notion
                url = "https://api.notion.com/v1/pages"
                res = client.post(url, headers=NotionService.get_headers(config.api_token), json=payload)
                
                if res.status_code == 200:
                    data = res.json()
                    page_id = data.get("id", "")
                    notion_url = data.get("url", "")
                    
                    candidate.status = "CREATED"
                    candidate.notion_page_id = page_id
                    candidate.notion_url = notion_url
                    db.commit()

                    return {
                        "success": True,
                        "page_id": page_id,
                        "notion_url": notion_url
                    }
                else:
                    err_msg = res.json().get("message", res.text)
                    return {"success": False, "error": f"Notion API error ({res.status_code}): {err_msg}"}

        except Exception as e:
            return {"success": False, "error": f"Notion page creation failed: {str(e)}"}

    @staticmethod
    def _format_date_string(date_str: str) -> Optional[str]:
        """Convert standard dates (YYYY-MM-DD) or parsed strings to clean Notion ISO-8601 strings."""
        if not date_str or date_str.lower() in ("null", "none"):
            return None
        date_str = date_str.strip()
        
        # Matches YYYY-MM-DD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # Matches YYYY-MM-DD HH:MM:SS
        if re.match(r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}$', date_str):
            return date_str.replace(" ", "T")

        # Fallback raw string try parsing
        try:
            for fmt in ("%d %b", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    dt = datetime.strptime(date_str, fmt)
                    if "%Y" not in fmt:
                        dt = dt.replace(year=datetime.now().year)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        except Exception:
            pass
            
        return None
