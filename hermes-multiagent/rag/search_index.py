from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

try:
    from rag.build_index import Encoder, EncoderFactory, create_encoder
    from rag.logging_config import get_logger
except ModuleNotFoundError:
    from build_index import Encoder, EncoderFactory, create_encoder
    from logging_config import get_logger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = PROJECT_ROOT / "rag" / "index"

IndexLoader = Callable[[], tuple[list[dict], Sequence[Sequence[float]], dict]]


def load_index(
    index_dir: Path = INDEX_DIR,
) -> tuple[list[dict], Sequence[Sequence[float]], dict]:
    """Загружает и проверяет метаданные, фрагменты и векторы."""

    chunks_path = index_dir / "chunks.json"
    vectors_path = index_dir / "vectors.npy"
    meta_path = index_dir / "meta.json"
    missing = [
        path.name
        for path in (chunks_path, vectors_path, meta_path)
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Индекс не найден или неполон: "
            f"{', '.join(missing)}. Сначала запустите build_index.py."
        )

    try:
        import numpy as np
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Не установлен NumPy. Запустите скрипт установки RAG-зависимостей."
        ) from error

    with chunks_path.open("r", encoding="utf-8") as file:
        chunks = json.load(file)

    vectors = np.load(vectors_path, allow_pickle=False)

    with meta_path.open("r", encoding="utf-8") as file:
        metadata = json.load(file)

    if not isinstance(chunks, list) or vectors.ndim != 2:
        raise ValueError("Индекс имеет некорректный формат.")

    if len(chunks) != vectors.shape[0]:
        raise ValueError("Количество фрагментов и векторов не совпадает.")

    if metadata.get("chunks_count") != len(chunks):
        raise ValueError("Метаданные не соответствуют числу фрагментов.")

    if metadata.get("vector_dimension") != vectors.shape[1]:
        raise ValueError("Метаданные не соответствуют размерности векторов.")

    if not isinstance(metadata.get("model"), str) or not metadata["model"].strip():
        raise ValueError("В метаданных отсутствует имя embedding-модели.")

    return chunks, vectors, metadata


def rank_chunks(
    chunks: list[dict],
    vectors: Sequence[Sequence[float]],
    query_vector: Sequence[float],
    top_k: int,
) -> list[dict]:
    """Ранжирует фрагменты по скалярному произведению векторов."""

    if not chunks or len(chunks) != len(vectors):
        raise ValueError("Фрагменты и векторы отсутствуют или не согласованы.")

    query_values = [float(value) for value in query_vector]

    if not query_values:
        raise ValueError("Вектор запроса пуст.")

    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise ValueError("Параметр top_k должен быть целым числом.")

    scores = []

    for index, vector in enumerate(vectors):
        values = [float(value) for value in vector]

        if len(values) != len(query_values):
            raise ValueError("Размерности векторов индекса и запроса не совпадают.")

        score = sum(value * query for value, query in zip(values, query_values))
        scores.append((score, index))

    result_count = max(1, min(top_k, len(chunks), 8))
    ranked = sorted(scores, key=lambda item: (-item[0], item[1]))[:result_count]
    results = []

    for score, index in ranked:
        chunk = chunks[index]
        results.append(
            {
                "score": round(score, 4),
                "path": chunk["path"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "content": chunk["content"][:4000],
            }
        )

    return results


def search(
    query: str,
    top_k: int = 4,
    encoder_factory: EncoderFactory = create_encoder,
    index_loader: IndexLoader | None = None,
) -> dict:
    """Ищет наиболее близкие фрагменты в локальном индексе."""

    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("Поисковый запрос пуст.")

    loader = index_loader or load_index
    chunks, vectors, metadata = loader()
    encoder: Encoder = encoder_factory(metadata["model"])
    encoded = encoder.encode(
        [normalized_query],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    if len(encoded) != 1:
        raise RuntimeError("Модель вернула некорректный вектор запроса.")

    results = rank_chunks(chunks, vectors, encoded[0], top_k)
    logger = get_logger("rag.search", "search-index.log")
    logger.info(
        "Поиск завершён: длина запроса=%d, top_k=%d, результаты=%s",
        len(normalized_query),
        len(results),
        [result["path"] for result in results],
    )

    return {"query": normalized_query, "results": results}


def main() -> None:
    """Запускает CLI векторного поиска."""

    parser = argparse.ArgumentParser(description="Поиск по локальному RAG-индексу.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=4)
    arguments = parser.parse_args()

    try:
        result = search(arguments.query, arguments.top_k)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        get_logger("rag.search", "search-index.log").exception(
            "Не удалось выполнить поиск"
        )
        print(
            json.dumps({"error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
