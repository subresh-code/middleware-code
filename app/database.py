"""
Database models and connection handling for payment middleware.
Uses SQLAlchemy with PostgreSQL.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import Generator

Base = declarative_base()


class Transaction(Base):
    """Transaction record for payment transfers between coops."""
    
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ISO 8583 Fields
    mti = Column(String(4), nullable=False)
    stan = Column(String(6), index=True)  # System Trace Audit Number
    rrn = Column(String(12), index=True)  # Retrieval Reference Number
    
    # Account and Coop Info
    source_account = Column(String(19), nullable=False)
    source_coop_id = Column(String(11))
    dest_coop_wallet = Column(String(255))
    
    # Transaction Details
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="840")
    
    # Rafiki Payment Info
    rafiki_payment_id = Column(String(255))
    rafiki_quote_id = Column(String(255))
    
    # Status
    status = Column(String(20), default="PENDING")  # PENDING, COMPLETED, FAILED
    response_code = Column(String(2), default="00")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Raw messages for debugging
    request_message = Column(Text)
    response_message = Column(Text)


class Database:
    """Database connection and session management."""
    
    def __init__(self, database_url: str = "postgresql://postgres:postgres@localhost:5432/payments"):
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def create_tables(self):
        """Create all tables."""
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self) -> Generator[Session, None, None]:
        """Get database session."""
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()


# Global database instance
db = Database()


def get_db():
    """Dependency for FastAPI to get DB session."""
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()
