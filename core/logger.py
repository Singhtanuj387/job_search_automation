"""
Structured JSON Lines Logger for the acquisition engine.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class JSONLinesFormatter(logging.Formatter):
    """Formats log records as valid JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            data.update(record.extra_data)
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data)


def get_structured_logger(name: str = "job_search_engine", log_dir: str = "logs") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    file_handler = logging.FileHandler(log_path / f"engine_{today}.jsonl")
    file_handler.setFormatter(JSONLinesFormatter())
    logger.addHandler(file_handler)

    # Console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%H:%M:%S"))
    logger.addHandler(console_handler)

    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    event_type: str,
    source: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Helper to emit structured log events with consistent schema."""
    extra_data = {
        "event_type": event_type,
        "source": source,
        **kwargs,
    }
    logger.log(level, message, extra={"extra_data": extra_data})
