from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, ForeignKey,
    Numeric, Enum as SQLEnum, BigInteger
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base
import enum


class PaymentStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    ILP_PREPARED = "ILP_PREPARED"
    ILP_FULFILLED = "ILP_FULFILLED"
    ILP_REJECTED = "ILP_REJECTED"
    NOTIFIED = "NOTIFIED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"


class BatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"  # Fixed typo
    FAILED = "FAILED"


class TriggeredBy(str, enum.Enum):
    ASE_INBOUND = "ASE_INBOUND"
    TRANSLATION_JOB = "TRANSLATION_JOB"
    RAFIKI_WEBHOOK = "RAFIKI_WEBHOOK"
    SETTLEMENT_JOB = "SETTLEMENT_JOB"
    SYSTEM = "SYSTEM"


class AseRegistry(Base):
    __tablename__ = "ase_registry"

    id = Column(Integer, primary_key=True, index=True)
    ase_name = Column(String(100), unique=True, nullable=False, index=True)
    api_key_hash = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    max_connections = Column(Integer, default=50)
    frame_length_type = Column(Integer, default=2)  # 2 or 4 bytes


class PaymentTranslation(Base):
    __tablename__ = "payment_translations"

    id = Column(Integer, primary_key=True, index=True)
    ase_name = Column(String(100), nullable=False, index=True)
    raw_message = Column(Text, nullable=True)  # hex encoded
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.RECEIVED, nullable=False, index=True)
    amount_value = Column(Numeric(20, 2), nullable=True)
    amount_ilp_uint64 = Column(BigInteger, nullable=True)  # Fixed: BigInteger for UInt64
    currency = Column(String(3), nullable=True)
    stan = Column(String(6), nullable=True, index=True)  # DE11
    rrn = Column(String(12), nullable=True, index=True)  # DE37 retrieval reference
    mti = Column(String(4), nullable=True)  # 0200 or 0400
    processing_code = Column(String(6), nullable=True)  # DE3
    terminal_id = Column(String(16), nullable=True)  # DE41
    wallet_address = Column(String(255), nullable=True)
    rafiki_payment_id = Column(String(255), nullable=True)
    response_code = Column(String(2), nullable=True)  # DE39
    failure_reason = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)  # For dead-letter retries
    next_retry_at = Column(DateTime(timezone=True), nullable=True)  # Next retry time
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    audit_logs = relationship("AuditLog", back_populates="payment")


class AccountWalletMapping(Base):
    __tablename__ = "account_wallet_mapping"

    id = Column(Integer, primary_key=True, index=True)
    ase_name = Column(String(100), nullable=False, index=True)
    account_number = Column(String(100), nullable=False, index=True)
    wallet_address = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class SettlementBatch(Base):
    __tablename__ = "settlement_batches"

    id = Column(Integer, primary_key=True, index=True)
    ase_name = Column(String(100), nullable=False, index=True)
    batch_date = Column(DateTime(timezone=True), server_default=func.now())
    total_amount = Column(Numeric(20, 2), nullable=False)
    payment_count = Column(Integer, nullable=False)
    status = Column(SQLEnum(BatchStatus), default=BatchStatus.PENDING, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payment_translations.id"), nullable=False, index=True)
    from_status = Column(SQLEnum(PaymentStatus), nullable=True)
    to_status = Column(SQLEnum(PaymentStatus), nullable=False)
    triggered_by = Column(SQLEnum(TriggeredBy), nullable=False)
    meta_data = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    payment = relationship("PaymentTranslation", back_populates="audit_logs")


class DeadLetter(Base):
    __tablename__ = "dead_letter"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payment_translations.id"), nullable=False, index=True)
    ase_name = Column(String(100), nullable=False, index=True)
    stan = Column(String(6), nullable=True, index=True)
    rrn = Column(String(12), nullable=True, index=True)
    failure_reason = Column(Text, nullable=True)
    error_type = Column(String(50), nullable=False)  # e.g. "RAFIKI_TIMEOUT", "PARSE_ERROR"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    retried_at = Column(DateTime(timezone=True), nullable=True)


class RawMessageLog(Base):
    __tablename__ = "raw_message_logs"

    id = Column(Integer, primary_key=True, index=True)
    ase_name = Column(String(100), nullable=False, index=True)
    stan = Column(String(6), nullable=True, index=True)
    rrn = Column(String(12), nullable=True, index=True)
    mti = Column(String(4), nullable=True)
    raw_bytes = Column(Text, nullable=False)  # Hex-encoded raw bytes
    parsed_successfully = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
