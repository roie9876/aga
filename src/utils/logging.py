"""Logging configuration for the application."""
import logging
import sys
from typing import Any
import structlog
from pythonjsonlogger import jsonlogger

from src.config import settings


def setup_logging() -> None:
    """Configure structured logging with JSON output."""
    
    # Configure standard logging
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # JSON formatter for structured logs
    class CustomJsonFormatter(jsonlogger.JsonFormatter):
        def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
            super().add_fields(log_record, record, message_dict)
            log_record['level'] = record.levelname
            log_record['logger'] = record.name
            log_record['environment'] = settings.environment
    
    # Setup handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        CustomJsonFormatter('%(timestamp)s %(level)s %(logger)s %(message)s')
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = []
    root_logger.addHandler(handler)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance for the given name.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)
