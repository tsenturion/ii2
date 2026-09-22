from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable, Protocol

try:
    from rag.logging_config import get_logger
except ModuleNotFoundError:
    from logging_config import get_logger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = PROJECT_ROOT / "rag" / "index"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

ALLOWED_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
}

EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    ".hermes",
    "__pycache__",
    "node_modules",
    "models",
}

CHUNK_SIZE_LINES = 60
CHUNK_OVERLAP_LINES = 15


class Encoder(Protocol):
    """Минимальный интерфейс embedding-модели."""

    def encode(self, texts: list[str], **kwargs: Any) -> Any:
        """Возвращает векторы для переданных текстов."""


EncoderFactory = Callable[[str], Encoder]


def create_encoder(model_name: str) -> Encoder:
    """Лениво загружает production-модель эмбеддингов."""

    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Не установлены зависимости RAG. Запустите "
            "scripts/Install-RagDependenciesAndBuildIndex.ps1."
        ) from error

    return SentenceTransformer(model_name)


def should_index(path: Path, project_root: Path = PROJECT_ROOT) -> bool:
    """Определяет, нужно ли добавлять файл в индекс."""

    if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False

    try:
        relative_path = path.relative_to(project_root)
    except ValueError:
        return False

    lowered_parts = {part.lower() for part in relative_path.parts}

    if lowered_parts.intersection(EXCLUDED_DIRECTORIES):
        return False

    if (
        len(relative_path.parts) >= 2
        and relative_path.parts[0].lower() == "rag"
        and relative_path.parts[1].lower() in {"index", "logs"}
    ):
        return False

    return True


def create_chunks(
    path: Path,
    project_root: Path = PROJECT_ROOT,
    chunk_size_lines: int = CHUNK_SIZE_LINES,
    chunk_overlap_lines: int = CHUNK_OVERLAP_LINES,
) -> list[dict]:
    """Разбивает текстовый файл на перекрывающиеся части."""

    if chunk_size_lines < 1:
        raise ValueError("Размер фрагмента должен быть положительным.")

    if not 0 <= chunk_overlap_lines < chunk_size_lines:
        raise ValueError(
            "Перекрытие должно быть неотрицательным и меньше размера фрагмента."
        )

    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    if not lines:
        return []

    chunks = []
    step = chunk_size_lines - chunk_overlap_lines
    start = 0

    while start < len(lines):
        end = min(start + chunk_size_lines, len(lines))
        content = "\n".join(lines[start:end]).strip()

        if content:
            chunks.append(
                {
                    "path": path.relative_to(project_root).as_posix(),
                    "start_line": start + 1,
                    "end_line": end,
                    "content": content,
                }
            )

        if end >= len(lines):
            break

        start += step

    return chunks


def collect_chunks(project_root: Path = PROJECT_ROOT) -> tuple[list[Path], list[dict]]:
    """Находит индексируемые файлы и формирует их фрагменты."""

    files = sorted(
        path for path in project_root.rglob("*") if should_index(path, project_root)
    )
    chunks = []

    for path in files:
        chunks.extend(create_chunks(path, project_root))

    return files, chunks


def build_index(
    project_root: Path = PROJECT_ROOT,
    model_name: str = MODEL_NAME,
    encoder_factory: EncoderFactory = create_encoder,
) -> tuple[list[dict], Any, dict]:
    """Формирует фрагменты, векторы и метаданные индекса."""

    logger = get_logger("rag.build", "build-index.log")
    logger.info("Начало индексации проекта: %s", project_root)

    files, chunks = collect_chunks(project_root)

    if not chunks:
        logger.error("Не найдено ни одного фрагмента для индексации")
        raise RuntimeError("Не найдено ни одного фрагмента для индексации.")

    texts = [
        (
            f"Путь файла: {chunk['path']}\n"
            f"Строки: {chunk['start_line']}-{chunk['end_line']}\n\n"
            f"{chunk['content']}"
        )
        for chunk in chunks
    ]

    encoder = encoder_factory(model_name)
    vectors = encoder.encode(
        texts,
        batch_size=16,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    if len(vectors) != len(chunks) or not len(vectors):
        raise RuntimeError("Модель вернула некорректное число векторов.")

    vector_dimension = len(vectors[0])

    if vector_dimension < 1:
        raise RuntimeError("Модель вернула векторы нулевой размерности.")

    metadata = {
        "model": model_name,
        "files_count": len(files),
        "chunks_count": len(chunks),
        "vector_dimension": vector_dimension,
        "chunk_size_lines": CHUNK_SIZE_LINES,
        "chunk_overlap_lines": CHUNK_OVERLAP_LINES,
    }

    logger.info(
        "Индексация завершена: файлов=%d, фрагментов=%d, размерность=%d",
        len(files),
        len(chunks),
        vector_dimension,
    )

    return chunks, vectors, metadata


def write_index(
    chunks: list[dict],
    vectors: Any,
    metadata: dict,
    index_dir: Path = INDEX_DIR,
) -> None:
    """Сохраняет готовый индекс на диск."""

    try:
        import numpy as np
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Не установлен NumPy. Запустите скрипт установки RAG-зависимостей."
        ) from error

    array = np.asarray(vectors, dtype=np.float32)

    if array.ndim != 2 or array.shape[0] != len(chunks):
        raise ValueError("Размер массива векторов не соответствует фрагментам.")

    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "vectors.npy", array)

    with (index_dir / "chunks.json").open("w", encoding="utf-8") as file:
        json.dump(chunks, file, ensure_ascii=False, indent=2)

    with (index_dir / "meta.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)


def main() -> None:
    """Строит локальный векторный индекс проекта."""

    try:
        print("Подготовка фрагментов и загрузка embedding-модели...")
        chunks, vectors, metadata = build_index()
        write_index(chunks, vectors, metadata)
    except (OSError, RuntimeError, ValueError) as error:
        get_logger("rag.build", "build-index.log").exception(
            "Не удалось построить индекс"
        )
        print(f"Ошибка построения индекса: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    print(f"Найдено файлов: {metadata['files_count']}")
    print(f"Создано фрагментов: {metadata['chunks_count']}")
    print(f"Модель: {metadata['model']}")
    print("Индекс успешно создан.")
    print(f"Каталог индекса: {INDEX_DIR}")


if __name__ == "__main__":
    main()
