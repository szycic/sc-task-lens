"""Database Initialization and Session Management for SC Task Lens.

Configures SQLAlchemy engine, sessionmaker, base declarative model.
"""

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base
from sc_task_lens.config import settings


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    """Ensure the parent directory for a file-based SQLite database exists."""
    parsed = make_url(database_url)
    if not parsed.drivername.startswith("sqlite"):
        return

    db_file = parsed.database
    if not db_file or db_file == ":memory:":
        return

    Path(db_file).expanduser().parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent_dir(settings.DB_URL)

connect_args = {"check_same_thread": False} if settings.DB_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DB_URL,
    connect_args=connect_args,
    echo=False
)

if settings.DB_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        finally:
            cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """Initialize database tables and seeds defaults."""
    from sc_task_lens import models  # Ensure models are imported
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI Dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
