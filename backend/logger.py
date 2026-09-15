import logging
import sys
from logging.handlers import RotatingFileHandler
from backend.config import get_settings

def setup_logger(name: str = "surveillance") -> logging.Logger:
    settings = get_settings()
    logger = logging.getLogger(name)
    
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    log_format = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # File Handler with Rotation (10MB max, 5 backups)
    log_file = settings.logs_dir / "surveillance.log"
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()
