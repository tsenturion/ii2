"""Безопасные обработчики инструментов разработки."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, BinaryIO

PLUGIN_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PLUGIN_DIR.parents[2]
PYTHON_EXECUTABLE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
LOG_DIR = PROJECT_ROOT / "rag" / "logs"
LOG_FILE = LOG_DIR / "dev-tools.log"
LOG_RETENTION_SECONDS = 30 * 24 * 60 * 60
DIAGNOSTIC_LIMIT = 20_000


def _configure_logger() -> logging.Logger:
    """Настраивает журнал с ротацией и безопасной деградацией при ошибке."""

    logger = logging.getLogger("dev_tools_plugin")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - LOG_RETENTION_SECONDS
        for log_path in LOG_DIR.glob("dev-tools.log*"):
            if log_path.is_file() and log_path.stat().st_mtime < cutoff:
                log_path.unlink()
        handler = TimedRotatingFileHandler(
            LOG_FILE, when="midnight", backupCount=30, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger


LOGGER = _configure_logger()


def _json(data: dict[str, Any]) -> str:
    """Сериализует ответ инструмента с поддержкой русского текста."""

    return json.dumps(data, ensure_ascii=False)


def _error(message: str) -> str:
    """Возвращает согласованный JSON-ответ об ошибке."""

    return _json({"error": message})


def _validate_args(args: Any, operation: str) -> dict[str, Any] | None:
    """Принимает только объект аргументов Hermes."""

    if isinstance(args, dict):
        return args
    LOGGER.warning("operation=%s rejected=arguments_not_object", operation)
    return None


def _safe_relative_path(raw_path: str | None) -> tuple[Path | None, str | None]:
    """Возвращает путь внутри проекта, не допуская обход через ссылки и ``..``."""

    if raw_path is None:
        return None, None
    if not isinstance(raw_path, str):
        return None, "Параметр path должен быть строкой."

    value = raw_path.strip()
    if not value:
        return None, None

    try:
        supplied = Path(value)
        if supplied.is_absolute() or supplied.drive or ".." in supplied.parts:
            return None, "Путь выходит за пределы проекта."
        root = PROJECT_ROOT.resolve()
        candidate = (root / supplied).resolve()
        relative = candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None, "Путь выходит за пределы проекта."
    return relative, None


def _read_limited(stream: BinaryIO, limit: int) -> tuple[str, bool]:
    """Читает временный файл в память не более ``limit + 1`` байта."""

    stream.seek(0)
    data = stream.read(limit + 1)
    truncated = len(data) > limit
    if truncated:
        data = data[:limit]
    return data.decode("utf-8", errors="replace"), truncated


@dataclass(frozen=True)
class _ProcessResult:
    """Ограниченный результат внешней программы."""

    returncode: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool


def _run_bounded(command: list[str], timeout: int, stdout_limit: int = DIAGNOSTIC_LIMIT) -> _ProcessResult:
    """Запускает программу без shell, сохраняя неограниченный вывод только во временный файл."""

    environment = dict(os.environ)
    environment["PYTHONUTF8"] = "1"
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=stdout_file,
            stderr=stderr_file,
            timeout=timeout,
            env=environment,
            shell=False,
            check=False,
        )
        stdout, stdout_truncated = _read_limited(stdout_file, stdout_limit)
        stderr, stderr_truncated = _read_limited(stderr_file, DIAGNOSTIC_LIMIT)
    return _ProcessResult(
        process.returncode, stdout, stderr, stdout_truncated, stderr_truncated
    )


def _log_finish(operation: str, started: float, outcome: str, **details: Any) -> None:
    """Записывает метаданные операции без содержимого diff и поискового шаблона."""

    detail_text = " ".join(f"{key}={value}" for key, value in details.items())
    LOGGER.info(
        "operation=%s outcome=%s duration_ms=%s %s",
        operation,
        outcome,
        round((time.monotonic() - started) * 1000),
        detail_text,
    )


def git_diff(args: dict[str, Any], **kwargs: Any) -> str:
    """Возвращает ограниченный обычный или staged Git diff."""

    del kwargs
    started = time.monotonic()
    values = _validate_args(args, "git_diff")
    if values is None:
        return _error("Аргументы инструмента должны быть JSON-объектом.")
    staged = values.get("staged", False)
    if not isinstance(staged, bool):
        LOGGER.warning("operation=git_diff rejected=invalid_staged")
        return _error("Параметр staged должен быть логическим значением.")
    relative_path, path_error = _safe_relative_path(values.get("path"))
    if path_error:
        LOGGER.warning("operation=git_diff rejected=path")
        return _error(path_error)

    command = ["git", "diff", "--no-ext-diff", "--no-textconv"]
    if staged:
        command.append("--cached")
    if relative_path is not None:
        command.extend(["--", str(relative_path)])
    try:
        result = _run_bounded(command, timeout=30)
    except subprocess.TimeoutExpired:
        _log_finish("git_diff", started, "timeout", staged=staged)
        return _error("git diff превысил лимит времени.")
    except (OSError, ValueError):
        _log_finish("git_diff", started, "execution_error", staged=staged)
        return _error("Не удалось выполнить git diff.")
    if result.returncode != 0:
        _log_finish("git_diff", started, "exit_error", exit_code=result.returncode)
        return _error("git diff завершился с ошибкой.")

    _log_finish("git_diff", started, "ok", staged=staged, path=relative_path or ".")
    return _json({
        "staged": staged,
        "path": str(relative_path) if relative_path is not None else ".",
        "diff": result.stdout or "Изменений нет.",
        "truncated": result.stdout_truncated,
    })


def grep_search(args: dict[str, Any], **kwargs: Any) -> str:
    """Ищет совпадения ``git grep`` с ограниченным выводом."""

    del kwargs
    started = time.monotonic()
    values = _validate_args(args, "grep_search")
    if values is None:
        return _error("Аргументы инструмента должны быть JSON-объектом.")
    pattern = values.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        LOGGER.warning("operation=grep_search rejected=pattern")
        return _error("Параметр pattern не может быть пустым.")
    pattern = pattern.strip()
    if len(pattern) > 500:
        LOGGER.warning("operation=grep_search rejected=pattern_length")
        return _error("Поисковый шаблон слишком длинный.")
    raw_max_results = values.get("max_results", 30)
    if isinstance(raw_max_results, bool) or not isinstance(raw_max_results, int):
        LOGGER.warning("operation=grep_search rejected=max_results_type")
        return _error("Параметр max_results должен быть целым числом от 1 до 100.")
    if not 1 <= raw_max_results <= 100:
        LOGGER.warning("operation=grep_search rejected=max_results_range value=%s", raw_max_results)
        return _error("Параметр max_results должен быть в диапазоне от 1 до 100.")
    relative_path, path_error = _safe_relative_path(values.get("path"))
    if path_error:
        LOGGER.warning("operation=grep_search rejected=path")
        return _error(path_error)

    command = ["git", "grep", "-n", "-I", "-e", pattern, "--"]
    if relative_path is not None:
        command.append(str(relative_path))
    try:
        result = _run_bounded(command, timeout=30)
    except subprocess.TimeoutExpired:
        _log_finish("grep_search", started, "timeout", max_results=raw_max_results)
        return _error("Поиск превысил лимит времени.")
    except (OSError, ValueError):
        _log_finish("grep_search", started, "execution_error", max_results=raw_max_results)
        return _error("Не удалось выполнить поиск.")
    if result.returncode not in {0, 1}:
        _log_finish("grep_search", started, "exit_error", exit_code=result.returncode)
        return _error("git grep завершился с ошибкой.")

    lines = result.stdout.splitlines()
    if result.stdout_truncated and lines and not result.stdout.endswith(("\n", "\r")):
        lines.pop()
    matches = lines[:raw_max_results]
    truncated = result.stdout_truncated or len(lines) > raw_max_results
    response: dict[str, Any] = {
        "path": str(relative_path) if relative_path is not None else ".",
        "shown_matches": len(matches),
        "matches": matches,
        "truncated": truncated,
    }
    if not result.stdout_truncated:
        response["total_matches"] = len(lines)
    _log_finish("grep_search", started, "ok", path=relative_path or ".", max_results=raw_max_results)
    return _json(response)


def run_linter(args: dict[str, Any], **kwargs: Any) -> str:
    """Запускает Ruff без изменений файлов и возвращает результат проверки."""

    del kwargs
    started = time.monotonic()
    values = _validate_args(args, "run_linter")
    if values is None:
        return _error("Аргументы инструмента должны быть JSON-объектом.")
    relative_path, path_error = _safe_relative_path(values.get("path"))
    if path_error:
        LOGGER.warning("operation=run_linter rejected=path")
        return _error(path_error)
    if not PYTHON_EXECUTABLE.is_file():
        LOGGER.error("operation=run_linter outcome=python_not_found")
        return _error("Не найден Python виртуального окружения проекта.")

    target = str(relative_path) if relative_path is not None else "."
    command = [
        str(PYTHON_EXECUTABLE), "-m", "ruff", "check", target,
        "--output-format", "concise", "--no-cache",
    ]
    try:
        result = _run_bounded(command, timeout=60)
    except subprocess.TimeoutExpired:
        _log_finish("run_linter", started, "timeout", path=target)
        return _error("Ruff превысил лимит времени.")
    except (OSError, ValueError):
        _log_finish("run_linter", started, "execution_error", path=target)
        return _error("Не удалось запустить Ruff.")
    if result.returncode >= 2:
        _log_finish("run_linter", started, "exit_error", exit_code=result.returncode, path=target)
        return _error("Ruff завершился с ошибкой выполнения.")

    _log_finish("run_linter", started, "ok" if result.returncode == 0 else "lint_found", exit_code=result.returncode, path=target)
    diagnostics = result.stdout or result.stderr
    return _json({
        "passed": result.returncode == 0,
        "exit_code": result.returncode,
        "path": target,
        "diagnostics": diagnostics,
        "truncated": result.stdout_truncated or result.stderr_truncated,
    })
