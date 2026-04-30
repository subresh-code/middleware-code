"""
Logging System for Middleware

Provides structured logging with different levels for monitoring,
debugging, and audit trails in a fintech environment.
"""

import logging
import logging.handlers
import json
from datetime import datetime
from typing import Dict, Any, Optional


class MiddlewareLogger:
    """
    Structured logger for the middleware system.
    Supports JSON formatting for log aggregation systems.
    """

    def __init__(self, name: str = "middleware", level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()

        # Create formatter
        formatter = MiddlewareFormatter()

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            "logs/middleware.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def log_transaction(self, transaction_id: str, action: str, details: Dict[str, Any]):
        """Log transaction-specific events."""
        self.logger.info("Transaction event", extra={
            "transaction_id": transaction_id,
            "action": action,
            "details": details
        })

    def log_error(self, error_type: str, message: str, transaction_id: Optional[str] = None):
        """Log errors with context."""
        self.logger.error("Error occurred", extra={
            "error_type": error_type,
            "message": message,
            "transaction_id": transaction_id
        })

    def log_api_call(self, endpoint: str, method: str, status_code: int, duration: float):
        """Log API call metrics."""
        self.logger.info("API call", extra={
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "duration": duration
        })


class MiddlewareFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs in JSON format for better parsing.
    """

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }

        # Add extra fields
        if hasattr(record, 'transaction_id'):
            log_entry["transaction_id"] = record.transaction_id
        if hasattr(record, 'action'):
            log_entry["action"] = record.action
        if hasattr(record, 'details'):
            log_entry["details"] = record.details
        if hasattr(record, 'error_type'):
            log_entry["error_type"] = record.error_type
        if hasattr(record, 'endpoint'):
            log_entry["endpoint"] = record.endpoint
        if hasattr(record, 'method'):
            log_entry["method"] = record.method
        if hasattr(record, 'status_code'):
            log_entry["status_code"] = record.status_code
        if hasattr(record, 'duration'):
            log_entry["duration"] = record.duration

        return json.dumps(log_entry)


# Global logger instance
logger = MiddlewareLogger()