"""AI Task Extraction Service for SC Task Lens.

Integrates with OpenAI, Gemini, Groq, and a mock fallback engine
to extract actionable tasks, summaries, priorities, dates, and links from screenshots.
"""

import base64
import json
import httpx
import re
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from pathlib import Path
from sc_task_lens.models import Screenshot, TaskCandidate, AISettings


class AIService:
    @staticmethod
    def ensure_candidate_from_screenshot(screenshot: Screenshot, db: Session, title: Optional[str] = None) -> TaskCandidate:
        """Create or refresh a lightweight candidate without calling paid AI APIs."""
        existing_candidate = db.query(TaskCandidate).filter(TaskCandidate.screenshot_id == screenshot.id).first()

        if existing_candidate:
            candidate = existing_candidate
        else:
            candidate = TaskCandidate(
                screenshot_id=screenshot.id,
                title=title or screenshot.filename,
                summary="",
                is_task=True,
                priority=None,
                start_date=None,
                deadline=None,
                status="PENDING"
            )
            db.add(candidate)

        db.commit()
        db.refresh(candidate)
        return candidate

    @staticmethod
    def test_ai_connection(provider: str, api_key: str, model_name: str) -> Dict[str, Any]:
        """Test API connectivity for the configured AI provider."""
        provider = (provider or "mock").lower()
        if provider == "mock":
            return {"success": True, "message": "Offline Mock Engine is active and operational (100% offline)."}

        if not api_key:
            return {"success": False, "error": f"API key is required to test {provider.upper()} connection."}

        # Use a dummy tiny image (2x2 pixel base64) to test vision capabilities
        dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=="

        if provider == "openai":
            model = model_name or "gpt-4o-mini"
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Respond with: OK"},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{dummy_base64}"}
                                }
                            ]
                        }
                    ],
                    "max_tokens": 10
                }
                res = httpx.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=12.0)
                if res.status_code == 200:
                    return {"success": True, "message": f"OpenAI Vision API connection successful! (Model: {model})"}
                else:
                    err_detail = res.json().get("error", {}).get("message", res.text)
                    return {"success": False, "error": f"OpenAI API Error ({res.status_code}): {err_detail}"}
            except Exception as e:
                return {"success": False, "error": f"OpenAI Connection Failed: {str(e)}"}

        elif provider == "gemini":
            model = model_name or "gemini-1.5-flash"
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": "Respond with: OK"},
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": dummy_base64
                                }
                            }
                        ]
                    }]
                }
                res = httpx.post(url, json=payload, timeout=12.0)
                if res.status_code == 200:
                    return {"success": True, "message": f"Google Gemini Vision API connection successful! (Model: {model})"}
                else:
                    err_detail = res.json().get("error", {}).get("message", res.text) if "application/json" in res.headers.get("content-type", "") else res.text
                    return {"success": False, "error": f"Gemini API Error ({res.status_code}): {err_detail}"}
            except Exception as e:
                return {"success": False, "error": f"Gemini Connection Failed: {str(e)}"}

        elif provider == "groq":
            model = model_name or "qwen/qwen3.6-27b"
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Respond with: OK"},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{dummy_base64}"}
                                }
                            ]
                        }
                    ],
                    "max_tokens": 10
                }
                res = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=12.0)
                if res.status_code == 200:
                    return {"success": True, "message": f"Groq Cloud Vision API connection successful! (Model: {model})"}
                else:
                    err_detail = res.json().get("error", {}).get("message", res.text) if "application/json" in res.headers.get("content-type", "") else res.text
                    return {"success": False, "error": f"Groq API Error ({res.status_code}): {err_detail}"}
            except Exception as e:
                return {"success": False, "error": f"Groq Connection Failed: {str(e)}"}

        return {"success": False, "error": f"Unsupported AI provider: {provider}"}

    @staticmethod
    def get_priority_options_from_notion(db: Session) -> list[str]:
        """Fetch allowed priority select options from Notion database schema or configuration."""
        from sc_task_lens.models import NotionConfig, NotionFieldMapping
        from sc_task_lens.services.notion_service import NotionService

        config = db.query(NotionConfig).first()
        if not config or not config.database_id or not config.api_token:
            return ["HIGH", "MEDIUM", "LOW"]

        field_mapping = db.query(NotionFieldMapping).filter(NotionFieldMapping.task_field == "priority").first()
        target_prop_name = field_mapping.notion_property_name if field_mapping else "Priority"

        if config.last_schema_json:
            try:
                props = json.loads(config.last_schema_json)
                for p in props:
                    p_name = p.get("name", "")
                    if p_name.lower() == target_prop_name.lower() or p_name.lower() == "priority":
                        options = p.get("options", [])
                        if options:
                            return options
            except Exception:
                pass

        schema_res = NotionService.fetch_database_schema(config.api_token, config.database_id)
        if schema_res.get("success"):
            props = schema_res.get("properties", [])
            for p in props:
                p_name = p.get("name", "")
                if p_name.lower() == target_prop_name.lower() or p_name.lower() == "priority":
                    options = p.get("options", [])
                    if options:
                        return options

        if field_mapping and field_mapping.value_mappings_json:
            try:
                val_map = json.loads(field_mapping.value_mappings_json)
                mapped_vals = list(val_map.values())
                if mapped_vals:
                    return mapped_vals
            except Exception:
                pass

        return ["HIGH", "MEDIUM", "LOW"]

    @staticmethod
    def analyze_screenshot(screenshot: Screenshot, db: Session, allow_fallback: bool = False) -> TaskCandidate:
        """Analyze screenshot using configured Vision AI provider or fallback mockup engine."""
        ai_settings = db.query(AISettings).first()
        provider = ai_settings.provider if ai_settings else "mock"
        api_key = ai_settings.api_key if ai_settings else ""

        priority_options = AIService.get_priority_options_from_notion(db)
        analysis = None

        if provider in ["openai", "gemini", "groq"]:
            if not api_key:
                if not allow_fallback:
                    raise RuntimeError(f"AI Provider '{provider}' is enabled but no API Key is set in Settings.")
            else:
                try:
                    if provider == "openai":
                        analysis = AIService._analyze_openai(screenshot.file_path, api_key, ai_settings.model_name, priority_options)
                    elif provider == "gemini":
                        analysis = AIService._analyze_gemini(screenshot.file_path, api_key, ai_settings.model_name, priority_options)
                    elif provider == "groq":
                        analysis = AIService._analyze_groq(screenshot.file_path, api_key, ai_settings.model_name, priority_options)
                except Exception as e:
                    if not allow_fallback:
                        raise RuntimeError(f"AI Provider '{provider}' error: {str(e)}")
                    analysis = None

        if not analysis:
            if provider in ["openai", "gemini", "groq"] and not allow_fallback:
                raise RuntimeError(f"AI Provider '{provider}' failed to return analysis.")
            analysis = AIService._analyze_heuristic(screenshot, priority_options)

        existing_candidate = db.query(TaskCandidate).filter(TaskCandidate.screenshot_id == screenshot.id).first()
        if existing_candidate:
            existing_candidate.title = analysis["title"]
            existing_candidate.summary = analysis["summary"]
            existing_candidate.is_task = analysis["is_task"]
            existing_candidate.priority = analysis["priority"]
            existing_candidate.start_date = analysis.get("start_date")
            existing_candidate.deadline = analysis["deadline"]
            existing_candidate.project = analysis.get("project")
            existing_candidate.status = "AI_PROCESSED"
            candidate = existing_candidate
        else:
            candidate = TaskCandidate(
                screenshot_id=screenshot.id,
                title=analysis["title"],
                summary=analysis["summary"],
                is_task=analysis["is_task"],
                priority=analysis["priority"],
                start_date=analysis.get("start_date"),
                deadline=analysis["deadline"],
                project=analysis.get("project"),
                status="AI_PROCESSED"
            )
            db.add(candidate)

        screenshot.is_processed = True
        db.commit()
        db.refresh(candidate)
        return candidate

    @staticmethod
    def _analyze_heuristic(screenshot: Screenshot, priority_options: list[str] = None) -> Dict[str, Any]:
        """Offline simple mock OCR helper when no LLM key is configured."""
        if not priority_options:
            priority_options = ["HIGH", "MEDIUM", "LOW"]
        return {
            "title": f"Task from {screenshot.filename}",
            "summary": "AI Vision analysis was skipped or offline mock engine was used. Review the attached screenshot to input details.",
            "is_task": True,
            "priority": priority_options[1] if len(priority_options) > 1 else priority_options[0],
            "start_date": None,
            "deadline": None,
            "project": "Inbox"
        }

    @staticmethod
    def _build_analysis_prompt(priority_options: Optional[list[str]] = None) -> str:
        options_str = ", ".join(f'"{opt}"' for opt in (priority_options or ["HIGH", "MEDIUM", "LOW"]))
        return f"""Analyze the provided screenshot.
Extract any actionable task, requirement, message request, or bug report visible in the image.
If there are multiple tasks, combine them or focus on the most prominent one.

Allowed Priority Options synced from Notion Database: [{options_str}]

Output must be a JSON object matching this schema:
{{
  "is_task": boolean,
  "priority": MUST be one of [{options_str}],
  "title": "A short, descriptive, actionable task title (maximum 80 characters)",
  "summary": "A concise 2-3 sentence description of the task requirements extracted from the image",
  "start_date": "Extracted start date in ISO YYYY-MM-DD format (e.g. 2026-08-04) or null",
  "deadline": "Extracted due date / deadline in ISO YYYY-MM-DD format (e.g. 2026-08-04) or null"
}}
Return ONLY valid JSON. Keep response clean without markdown formatting tags.
"""

    @staticmethod
    def _analyze_openai(image_path: str, api_key: str, model_name: str = None, priority_options: list[str] = None) -> Optional[Dict[str, Any]]:
        model = model_name or "gpt-4o-mini"
        prompt = AIService._build_analysis_prompt(priority_options)
        
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
            
        mime_type = "image/jpeg" if Path(image_path).suffix.lower() in [".jpg", ".jpeg"] else "image/png"

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2
            }
            response = httpx.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=20.0)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                return json.loads(content)
            else:
                err_detail = response.json().get("error", {}).get("message") or response.text[:150]
                raise RuntimeError(f"OpenAI (HTTP {response.status_code}): {err_detail}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"OpenAI call failed: {e}")

    @staticmethod
    def _analyze_gemini(image_path: str, api_key: str, model_name: str = None, priority_options: list[str] = None) -> Optional[Dict[str, Any]]:
        model = model_name or "gemini-1.5-flash"
        prompt = AIService._build_analysis_prompt(priority_options)
        
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
            
        mime_type = "image/jpeg" if Path(image_path).suffix.lower() in [".jpg", ".jpeg"] else "image/png"

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": base64_image
                                }
                            }
                        ]
                    }
                ]
            }
            response = httpx.post(url, json=payload, timeout=20.0)
            if response.status_code == 200:
                text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text.startswith("```"):
                    text = re.sub(r'^```(?:json)?\s*', '', text)
                    text = re.sub(r'\s*```$', '', text)
                return json.loads(text)
            else:
                err_detail = response.json().get("error", {}).get("message") or response.text[:150]
                raise RuntimeError(f"Gemini (HTTP {response.status_code}): {err_detail}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Gemini call failed: {e}")

    @staticmethod
    def _analyze_groq(image_path: str, api_key: str, model_name: str = None, priority_options: list[str] = None) -> Optional[Dict[str, Any]]:
        model = model_name or "qwen/qwen3.6-27b"
        prompt = AIService._build_analysis_prompt(priority_options)
        
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
            
        mime_type = "image/jpeg" if Path(image_path).suffix.lower() in [".jpg", ".jpeg"] else "image/png"

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2
            }
            response = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=20.0)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                return json.loads(content)
            else:
                err_detail = response.json().get("error", {}).get("message") or response.text[:150]
                raise RuntimeError(f"Groq (HTTP {response.status_code}): {err_detail}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Groq call failed: {e}")
