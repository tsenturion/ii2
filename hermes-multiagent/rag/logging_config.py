from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import time


LOG_DIR = Path(__file__).resolve().parent / "logs"
RETENTION_DAYS = 30


def remove_expired_logs(
    log_dir: Path = LOG_DIR,
    retention_days: int = RETENTION_DAYS,
) -> None:
    """Удаляет журналы старше установленного срока хранения."""

    if retention_days < 1 or not log_dir.exists():
        return

    cutoff = time.time() - retention_days * 24 * 60 * 60

    for path in log_dir.glob("*.log*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def get_logger(name: str, filename: str) -> logging.Logger:
    """Создаёт файловый журнал с ежедневной ротацией."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    remove_expired_logs()

    log_path = LOG_DIR / filename
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if any(
        getattr(handler, "_rag_log_path", None) == str(log_path)
        for handler in logger.handlers
    ):
        return logger

    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=RETENTION_DAYS,
        encoding="utf-8",
    )
    handler._rag_log_path = str(log_path)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    )
    logger.addHandler(handler)

    return logger
