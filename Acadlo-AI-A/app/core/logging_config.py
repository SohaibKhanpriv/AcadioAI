"""
Centralized logging configuration with date-based rotation.

This module sets up structured JSON logging for the Acadlo AI Core service.
Logs are organized by category (chat, ingestion, errors) with daily rotation.
"""

import logging
import logging.handlers
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict
import sys


class JsonFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs in structured JSON format.
    
    This makes logs easily parseable for analysis and monitoring tools.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present (from structured logging)
        if hasattr(record, "extra_fields") and record.extra_fields:
            log_data.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, default=str)


class StructuredLogger(logging.LoggerAdapter):
    """
    Logger adapter that supports structured logging with extra fields.
    
    Usage:
        logger.info("Chat request processed", extra_fields={
            "tenantId": "tenant-123",
            "userId": "user-456",
            "totalLatencyMs": 1500
        })
    """
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Inject extra_fields into log record."""
        extra_fields = kwargs.pop("extra_fields", {})
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"]["extra_fields"] = extra_fields
        return msg, kwargs


def setup_logging(
    log_dir: str = "logs",
    retention_days: int = 30,
    console_level: str = "INFO",
    file_level: str = "INFO"
) -> None:
    """
    Set up application-wide logging with date-based rotation.
    
    Args:
        log_dir: Directory to store log files (default: "logs")
        retention_days: Number of days to retain old logs (default: 30)
        console_level: Minimum level for console output (default: "INFO")
        file_level: Minimum level for file output (default: "INFO")
    
    Log Structure:
        logs/
        ├── chat/
        │   └── chat.YYYY-MM-DD.log      # All /v1/chat activity
        ├── ingestion/
        │   └── ingestion.YYYY-MM-DD.log # All ingestion jobs
        ├── errors/
        │   └── errors.YYYY-MM-DD.log    # Critical errors only
        └── app.log                       # General application logs (rolling)
    """
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create subdirectories for organized logs
    (log_path / "chat").mkdir(exist_ok=True)
    (log_path / "ingestion").mkdir(exist_ok=True)
    (log_path / "errors").mkdir(exist_ok=True)
    
    # Get today's date for filenames (YYYY-MM-DD format)
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    # JSON formatter for structured logs
    json_formatter = JsonFormatter()
    
    # Console formatter (human-readable for development)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # ===== Root Logger Configuration =====
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels, handlers filter
    
    # Remove any existing handlers (avoid duplicates)
    root_logger.handlers.clear()
    
    # ===== Console Handler (stdout) =====
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, console_level.upper()))
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # ===== General App Log (rolling, not date-based) =====
    app_handler = logging.handlers.RotatingFileHandler(
        filename=log_path / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    app_handler.setLevel(getattr(logging, file_level.upper()))
    app_handler.setFormatter(json_formatter)
    root_logger.addHandler(app_handler)
    
    # ===== Errors-Only Log (date-based filename) =====
    # Create filename with today's date: errors.2026-01-03.log
    error_filename = log_path / "errors" / f"errors.{today_date}.log"
    
    error_handler = logging.FileHandler(
        filename=str(error_filename),
        mode='a',
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)
    root_logger.addHandler(error_handler)
    
    # ===== Chat-Specific Logger (date-based rotation) =====
    chat_logger = logging.getLogger("chat_service")
    chat_logger.setLevel(logging.DEBUG)
    chat_logger.propagate = True  # Also send to root handlers
    
    # Create filename with today's date: chat.2026-01-03.log
    # A new file is created automatically each day when the app starts
    chat_filename = log_path / "chat" / f"chat.{today_date}.log"
    
    # Use regular FileHandler (not TimedRotating) with date in filename
    # This is simpler and ensures the date is always in the filename
    chat_handler = logging.FileHandler(
        filename=str(chat_filename),
        mode='a',  # Append mode
        encoding="utf-8"
    )
    chat_handler.setLevel(logging.INFO)
    chat_handler.setFormatter(json_formatter)
    chat_logger.addHandler(chat_handler)
    
    # ===== Ingestion-Specific Logger (date-based rotation) =====
    ingestion_logger = logging.getLogger("ingestion_service")
    ingestion_logger.setLevel(logging.DEBUG)
    ingestion_logger.propagate = True
    
    # Create filename with today's date: ingestion.2026-01-03.log
    ingestion_filename = log_path / "ingestion" / f"ingestion.{today_date}.log"
    
    ingestion_handler = logging.FileHandler(
        filename=str(ingestion_filename),
        mode='a',
        encoding="utf-8"
    )
    ingestion_handler.setLevel(logging.INFO)
    ingestion_handler.setFormatter(json_formatter)
    ingestion_logger.addHandler(ingestion_handler)
    
    # ===== Suppress noisy third-party loggers =====
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Log initialization message
    root_logger.info(
        f"✅ Logging system initialized | Directory: {log_path.absolute()} | "
        f"Retention: {retention_days} days"
    )


def get_structured_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance for the given module.
    
    Args:
        name: Logger name (typically __name__ from calling module)
    
    Returns:
        StructuredLogger instance with JSON formatting support
    
    Example:
        logger = get_structured_logger(__name__)
        logger.info("User logged in", extra_fields={"userId": "123"})
    """
    base_logger = logging.getLogger(name)
    return StructuredLogger(base_logger, {})

