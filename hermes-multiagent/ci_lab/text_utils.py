"""Небольшие операции нормализации текста для CI-практики."""


def normalize_username(name: str) -> str:
    """Нормализует регистр и заменяет группы пробельных символов на `_`."""

    return "_".join(name.strip().lower().split())
