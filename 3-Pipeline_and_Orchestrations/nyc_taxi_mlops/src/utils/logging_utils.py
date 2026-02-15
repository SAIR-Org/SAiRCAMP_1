"""
Logging utility for NYC Taxi ML Pipeline
Provides structured logging with file and console handlers
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    log_level: str = "INFO",
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5
) -> logging.Logger:
    """
    Setup logger with console and optional file handler.
    
    Args:
        name: Logger name
        log_file: Optional log file path
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log message format
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup log files to keep
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(log_format)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def log_section(logger: logging.Logger, title: str, char: str = "=", width: int = 70):
    """Log a section header."""
    logger.info("")
    logger.info(char * width)
    logger.info(title.center(width))
    logger.info(char * width)


def log_subsection(logger: logging.Logger, title: str, char: str = "-", width: int = 70):
    """Log a subsection header."""
    logger.info("")
    logger.info(title)
    logger.info(char * width)


def log_metrics(logger: logging.Logger, metrics: dict, prefix: str = ""):
    """Log metrics in a structured format."""
    if prefix:
        logger.info(f"{prefix}:")
    for key, value in metrics.items():
        if isinstance(value, float):
            logger.info(f"  • {key}: {value:.4f}")
        else:
            logger.info(f"  • {key}: {value}")


def log_config(logger: logging.Logger, config: dict):
    """Log configuration in a structured format."""
    logger.info("Configuration:")
    for section, params in config.items():
        logger.info(f"  [{section}]")
        if isinstance(params, dict):
            for key, value in params.items():
                logger.info(f"    • {key}: {value}")
        else:
            logger.info(f"    • {params}")