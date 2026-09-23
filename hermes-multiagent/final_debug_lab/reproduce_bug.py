import logging
import sqlite3
import time
from datetime import date
from pathlib import Path

from final_debug_lab.legacy_orders import get_order
from testing_lab.refunds import RefundService, ReturnRepository

LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_RETENTION_DAYS = 30


def _remove_expired_logs() -> None:
    """Удаляет диагностические журналы старше установленного срока."""

    cutoff = time.time() - LOG_RETENTION_DAYS * 24 * 60 * 60

    for log_file in LOG_DIR.glob("*.log"):
        if log_file.stat().st_mtime < cutoff:
            log_file.unlink()


def configure_logging() -> logging.Logger:
    """Настраивает консольный и файловый журналы воспроизведения."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _remove_expired_logs()

    logger = logging.getLogger("final_debug_lab")
    logger.setLevel(logging.INFO)

    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    console_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def process_return(
    logger: logging.Logger,
    request_id: str,
    order_id: int,
) -> None:
    """Выполняет один сценарий возврата и записывает его результат."""

    logger.info(
        "request_id=%s событие=заявка_получена заказ=%s",
        request_id,
        order_id,
    )

    order = get_order(order_id)
    logger.info(
        "request_id=%s событие=заказ_загружен статус=%s delivered_at=%r",
        request_id,
        order["status"],
        order["delivered_at"],
    )

    connection = sqlite3.connect(":memory:")
    repository = ReturnRepository(connection)
    service = RefundService(repository)

    try:
        result = service.create_request(
            order=order,
            requested={101: 1},
            today=date(2026, 9, 20),
        )
        logger.info(
            "request_id=%s событие=возврат_создан return_id=%s сумма=%s статус=%s",
            request_id,
            result["id"],
            result["amount"],
            result["status"],
        )
    except Exception:
        logger.exception(
            "request_id=%s событие=ошибка_возврата заказ=%s",
            request_id,
            order_id,
        )
    finally:
        connection.close()


def main() -> None:
    """Воспроизводит успешный и ошибочный сценарии возврата."""

    logger = configure_logging()
    logger.info("событие=начало_воспроизведения")
    process_return(logger, request_id="REQ-OK-1001", order_id=1001)
    process_return(logger, request_id="REQ-BUG-1002", order_id=1002)
    logger.info("событие=конец_воспроизведения")


if __name__ == "__main__":
    main()
