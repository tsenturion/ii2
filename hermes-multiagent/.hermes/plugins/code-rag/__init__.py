from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any


PLUGIN_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PLUGIN_DIR.parents[2]
PYTHON_EXECUTABLE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
SEARCH_SCRIPT = PROJECT_ROOT / "rag" / "search_index.py"
LOG_DIR = PROJECT_ROOT / "rag" / "logs"
LOG_FILE = LOG_DIR / "code_rag_plugin.log"
LOG_RETENTION_SECONDS = 30 * 24 * 60 * 60


def _configure_logger() -> logging.Logger:
    """Настраивает журнал диагностики плагина без дублирования обработчиков."""

    logger = logging.getLogger("code_rag_plugin")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - LOG_RETENTION_SECONDS
        for log_path in LOG_DIR.glob("code_rag_plugin.log*"):
            if log_path.is_file() and log_path.stat().st_mtime < cutoff:
                log_path.unlink()

        handler = TimedRotatingFileHandler(
            LOG_FILE,
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        # Ошибки журнала не должны нарушать доступность поиска.
        logger.addHandler(logging.NullHandler())

    return logger


LOGGER = _configure_logger()


def _error(message: str) -> str:
    """Возвращает ошибку инструмента в согласованном JSON-формате."""

    return json.dumps({"error": message}, ensure_ascii=False)


def register(ctx: Any) -> None:
    """Регистрирует инструмент RAG-поиска."""

    schema = {
        "name": "codebase_search",
        "description": (
            "Выполняет семантический поиск по локальному векторному индексу "
            "кодовой базы текущего проекта. Используй перед ответом на вопросы "
            "о структуре, бизнес-логике, зависимостях, API и затрагиваемых файлах."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Непустой поисковый запрос естественным языком.",
                    "minLength": 1,
                },
                "top_k": {
                    "type": "integer",
                    "description": "Количество возвращаемых фрагментов от 1 до 8.",
                    "minimum": 1,
                    "maximum": 8,
                },
            },
            "required": ["query"],
        },
    }

    def handle_search(params: dict[str, Any], **kwargs: Any) -> str:
        """Запускает поиск в отдельном Python-процессе без оболочки."""

        del kwargs
        raw_query = params.get("query", "")
        query = raw_query.strip() if isinstance(raw_query, str) else ""

        if not query:
            LOGGER.warning("Отклонён пустой поисковый запрос")
            return _error("Поисковый запрос пуст.")

        raw_top_k = params.get("top_k", 4)
        if isinstance(raw_top_k, bool) or isinstance(raw_top_k, float):
            LOGGER.warning("Отклонён некорректный top_k")
            return _error("Параметр top_k должен быть целым числом от 1 до 8.")

        try:
            top_k = int(raw_top_k)
        except (TypeError, ValueError):
            LOGGER.warning("Отклонён некорректный top_k")
            return _error("Параметр top_k должен быть целым числом от 1 до 8.")

        if not 1 <= top_k <= 8:
            LOGGER.warning("Отклонён top_k вне допустимого диапазона: %s", top_k)
            return _error("Параметр top_k должен быть в диапазоне от 1 до 8.")

        if not PYTHON_EXECUTABLE.exists():
            LOGGER.error("Не найден Python виртуального окружения")
            return _error(f"Не найден Python виртуального окружения: {PYTHON_EXECUTABLE}")

        if not SEARCH_SCRIPT.exists():
            LOGGER.error("Не найден скрипт поиска")
            return _error(f"Не найден скрипт поиска: {SEARCH_SCRIPT}")

        environment = dict(os.environ)
        environment["PYTHONUTF8"] = "1"
        command = [
            str(PYTHON_EXECUTABLE),
            str(SEARCH_SCRIPT),
            "--query",
            query,
            "--top-k",
            str(top_k),
        ]
        LOGGER.info("Запущен поиск: длина_запроса=%s top_k=%s", len(query), top_k)

        try:
            process = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                env=environment,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            LOGGER.error("Поиск превысил лимит времени")
            return _error("Поиск превысил лимит времени выполнения.")
        except OSError as error:
            LOGGER.error("Не удалось запустить поиск: %s", error)
            return _error("Не удалось запустить скрипт поиска.")

        if process.returncode != 0:
            LOGGER.error("Поиск завершился с кодом %s", process.returncode)
            return _error("Скрипт поиска завершился с ошибкой.")

        result = process.stdout.strip()
        if not result:
            LOGGER.warning("Поиск завершился без данных")
            return _error("Поиск не вернул данные.")

        LOGGER.info("Поиск успешно завершён")
        return result

    ctx.register_tool(
        name="codebase_search",
        toolset="code_rag",
        schema=schema,
        handler=handle_search,
    )
