# SC Task Lens

`sc-task-lens` is a self-hosted FastAPI application and Progressive Web App (PWA) dashboard that automatically ingests visual screenshots, extracts actionable task candidates using Vision AI (Groq, OpenAI, or Google Gemini), and creates structured tasks directly in Notion databases with custom property mappings, attaching the original screenshot for context.

Designed for lightning-fast visual task capture, SC Task Lens provides a complete screenshot-to-task pipeline with drag-and-drop ingestion, Vim-style hotkey navigation, real-time WebSocket dashboard sync, and offline PWA installation support.

---

## Key Features

- **Drag-and-Drop & Clipboard Paste Ingestion**: Paste screenshots directly from the clipboard (`Ctrl+V` / `Cmd+V`) anywhere on the page, or drag files into the responsive touch-optimized dropzone.
- **Vision-Based AI Extraction**: Process visual text, code, mockups, or reminders using state-of-the-art vision models (e.g. Groq `qwen/qwen3.8-27b`, OpenAI `gpt-4o-mini`, or Google Gemini Flash).
- **Notion Database Integration & Dynamic Syncing**: Map screenshot metadata and AI-extracted fields (Title, Description, Priority, Start Date, Due Date, Source URL, and Image Attachment) to custom Notion database properties. Sync new tasks or update existing Notion pages directly using the integrated `Update in Notion` PATCH sync mechanism.
- **Progressive Web App (PWA)**: Installable directly to your Desktop or mobile home screen via custom Service Worker (`sw.js`) and web manifest configurations.
- **Power-User Keyboard Shortcuts**: Manage your inbox at the speed of thought with global hotkeys:
  - `j`/`k` for scrolling cards.
  - `Space` to check/select cards.
  - `o`/`Enter` to Process & Review focused task candidate (or open review).
  - `i` to ignore, `r` to analyze, and `p` to push directly to Notion.
  - `Ctrl + S` to save progress and `Ctrl + Enter` to sync/update tasks to Notion (inside the modal).
- **Real-Time WebSocket Updates**: Live WebSocket updates sync state (upload success, extraction completions) instantly across all open browser tabs.
- **Diagnostics & Backup Utility**: Verify configuration keys and database connections with health metrics, and export or restore configurations via JSON backups.

---

## Project Structure

```text
sc-task-lens/
├── data/                    # SQLite database storage & local screenshot files
│   └── screenshots/         # Serves uploaded screenshots statically
├── src/
│   └── sc_task_lens/
│       ├── api/             # FastAPI REST & WebSocket endpoint routers
│       │   ├── admin.py         # Diagnostic tools, settings, and backups export/import
│       │   ├── ai.py            # AI Settings & providers connectivity tests
│       │   ├── inbox.py         # Upload endpoints, candidate reviews, and WebSockets
│       │   └── notion.py        # Database schema query & custom property mapping
│       ├── services/        # Business logic & integrations
│       │   ├── ai_service.py    # Groq, OpenAI, Gemini Vision API & mock logic
│       │   ├── notion_service.py# Notion page constructor & multipart files uploader
│       │   └── screenshot_service.py # Screenshot file writes and cleanup managers
│       ├── static/          # Static assets served to the browser
│       │   ├── assets/          # Icons, apple-touch-logos, PWA favicons
│       │   ├── css/
│       │   │   └── style.css        # Premium dark-theme styling & responsive rules
│       │   ├── js/
│       │   │   ├── admin.js         # Config forms, danger triggers, diagnostics
│       │   │   ├── ai_settings.js   # Provider toggles & validation tests
│       │   │   ├── app.js           # Bootstrap register, global Vim hotkeys
│       │   │   ├── inbox.js         # Upload dropzone, selections, list managers
│       │   │   ├── navigation.js    # Responsive sidebar drawer toggles
│       │   │   ├── sw.js            # Offline service worker & push handler
│       │   │   ├── task_review.js   # Modal controllers, Notion syncing, edits
│       │   │   └── utils.js         # Date formatting, escape, and toast helpers
│       │   └── site.webmanifest # PWA app installer manifest configs
│       ├── templates/       # HTML layouts
│       │   ├── index.html       # Master layout wrapper
│       │   ├── modals/          # Popup reviewer, config import, and help sheets
│       │   └── tabs/            # SPA navigation sub-views
│       ├── config.py        # Environment variables loader
│       ├── database.py      # SQLite session handler and default mappings seeder
│       ├── main.py          # FastAPI startup and static serving routing context
│       ├── models.py        # SQLAlchemy ORM schemas
│       └── schemas.py       # Pydantic JSON request/response schema specifications
├── tests/                   # Pytest API validation files
│   ├── conftest.py          # SQLite in-memory override helper
│   └── test_inbox.py        # Inbox endpoints and Service Worker test suites
├── pyproject.toml           # Setuptools properties & testing packages path
├── requirements.txt         # Project requirements list
└── README.md                # This documentation
```

---

## Environment Variables

Configure settings via `.env` file in the project root:

| Variable | Purpose | Default |
|---|---|---|
| `DB_PATH` | Path to the local SQLite database file | `data/sc_task_lens.db` |
| `DB_URL` | SQLAlchemy connection URL for the database | `sqlite:///{DB_PATH}` |
| `HOST` | Bind host address for the FastAPI server | `0.0.0.0` |
| `PORT` | Bind port for the FastAPI server | `8000` |
| `BASE_URL` | Base URL used for resolving static screenshot resources | `http://localhost:8000` |
| `NOTION_API_KEY` | Notion integration API secret key | `""` |
| `NOTION_DATABASE_ID` | Notion database ID | `""` |
| `GROQ_API_KEY` | Groq Cloud API key for Llama 3.2 Vision | `""` |
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o mini | `""` |
| `GEMINI_API_KEY` | Google Gemini API key for Gemini 1.5 Flash | `""` |

---

## Installation & Setup

### Requirements
- Python 3.10+
- Virtual environment tool (`venv` or `virtualenv`)

### 1. Clone & Setup Environment

```bash
git clone https://github.com/szycic/sc-task-lens.git
cd sc-task-lens

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables (Optional)

Create a `.env` file in the repository root:

```env
HOST=0.0.0.0
PORT=8000
GROQ_API_KEY=gsk_xxx
NOTION_API_KEY=secret_xxx
NOTION_DATABASE_ID=xxx
```

---

## Running the Application

Start the server using python:

```bash
PYTHONPATH=src python -m sc_task_lens.main
```

Once running, access the web dashboard in your browser:
- **Dashboard UI**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## Running Tests

Execute the automated test suite with `pytest`:

```bash
# Run tests
pytest

# Detailed output
pytest -v
```

---

## Keyboard Navigation Reference

| Key | Description |
|---|---|
| `?` | Toggle global Keyboard Shortcuts Help Modal |
| `j` / `k` or `ArrowDown` / `ArrowUp` | vim-style card focus navigation |
| `Space` | Toggle checkbox selection on focused card |
| `o` / `Enter` | Open the review dialog of the focused card |
| `a` | Select/deselect all visible cards |
| `i` | Mark focused card as Ignored |
| `r` | Trigger AI Vision re-extraction on focused candidate |
| `p` | Direct sync/push focused candidate to Notion |
| `Ctrl + S` | Save review modal changes (inside modal) |
| `Ctrl + Enter` | Sync / Update task to Notion (inside modal) |
| `Escape` | Close any open modal dialogs (works within input fields) |

---

## REST API Reference

All API routes are prefixed under `/api`:

### Inbox & Candidate Operations
| Endpoint | Method | Description |
|---|---|---|
| `/api/inbox/upload` | `POST` | Upload screenshot image multipart file and seed a pending candidate |
| `/api/inbox/stats` | `GET` | Fetch counts metrics for all status stages |
| `/api/inbox/candidates` | `GET` | List task candidates (supports `status`, `sort_by`, `search`, `page`) |
| `/api/inbox/candidates/{id}` | `GET` | Retrieve candidate fields and screenshot URL |
| `/api/inbox/candidates/{id}` | `PUT` | Save changes made during manual verification checks |
| `/api/inbox/candidates/{id}/prepare-task` | `POST` | Run AI Vision task extraction (OCR, summaries, and priority) |
| `/api/inbox/candidates/{id}/create-task` | `POST` | Push candidate details to Notion page (updates existing if already synced) |
| `/api/inbox/candidates/{id}/ignore` | `POST` | Ignore task candidate from list |
| `/api/inbox/candidates/{id}/unignore` | `POST` | Restore ignored task candidate |
| `/api/inbox/candidates/{id}` | `DELETE` | Permanently delete task candidate and screenshots |
| `/api/inbox/candidates/batch-process` | `POST` | Batch trigger AI Vision extraction on multiple cards |
| `/api/inbox/candidates/batch-ignore` | `POST` | Batch ignore multiple cards |
| `/api/inbox/candidates/batch-unignore` | `POST` | Batch restore multiple ignored cards |
| `/api/inbox/clear-all` | `DELETE` | Purge entire candidates and screenshots history |
| `/api/inbox/ws/sync-updates` | `WebSocket` | Stream real-time notifications for upload & sync updates |

### Notion Database Integration
| Endpoint | Method | Description |
|---|---|---|
| `/api/notion/config` | `GET` | Fetch Notion connection status and database properties |
| `/api/notion/config` | `POST` | Save Notion Integration API credentials and DB identifier |
| `/api/notion/fetch-schema` | `POST` | Force refresh and parse target Notion DB property schema types |
| `/api/notion/mapping` | `GET` | Fetch property mapping schema rows |
| `/api/notion/mapping` | `POST` | Save custom field and priority select option mappings |

### AI settings
| Endpoint | Method | Description |
|---|---|---|
| `/api/ai/settings` | `GET` | Fetch current AI provider, custom prompts, and active model names |
| `/api/ai/settings` | `POST` | Save provider details (Groq / OpenAI / Gemini / offline mock) |
| `/api/ai/test` | `POST` | Test connection and keys against the configured AI Vision endpoint |

### Admin Settings & Diagnostics
| Endpoint | Method | Description |
|---|---|---|
| `/api/admin/settings` | `GET` | Fetch UI refresh configurations and auto-purge details |
| `/api/admin/settings` | `PUT` | Save UI refresh configurations and auto-purge details |
| `/api/admin/diagnostics/run` | `POST` | Execute diagnostic tasks (Database, Vision API, Notion integration) |
| `/api/admin/config/export` | `GET` | Export complete system settings backup (JSON) |
| `/api/admin/config/import` | `POST` | Import configuration settings backup |
| `/api/admin/danger/purge-ignored` | `POST` | Purge ignored candidates and screenshots |
| `/api/admin/danger/reset-settings` | `POST` | Factory reset settings |