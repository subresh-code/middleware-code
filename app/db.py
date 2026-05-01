from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# Lazy-load engine to avoid import-time config errors
_engine = None
Base = declarative_base()

def get_engine():
    global _engine
    if _engine is None:
        from app.config import get_settings
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine

def get_session_local():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)

# For convenience, create a default SessionLocal
# This will be lazily initialized
SessionLocal = None

def get_db() -> Session:
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
