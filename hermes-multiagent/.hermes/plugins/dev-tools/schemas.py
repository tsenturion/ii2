"""Схемы инструментов, которые получает языковая модель."""

GIT_DIFF = {
    "name": "git_diff",
    "description": (
        "Показывает текущий Git diff проекта без изменения репозитория. "
        "Используй для проверки незакоммиченных изменений, строк изменений "
        "и read-only ревью; поддерживается обычный и staged diff."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Необязательный путь внутри проекта; по умолчанию весь проект.",
            },
            "staged": {
                "type": "boolean",
                "description": "Если true, показать staged diff через git diff --cached.",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}

GREP_SEARCH = {
    "name": "grep_search",
    "description": (
        "Ищет текст или шаблон в отслеживаемых Git файлах без изменения проекта. "
        "Используй для поиска применений функций, классов, импортов и API."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "minLength": 1,
                "maxLength": 500,
                "description": "Непустая строка или шаблон для поиска.",
            },
            "path": {
                "type": "string",
                "description": "Необязательный путь внутри проекта для ограничения поиска.",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Максимум строк результата; по умолчанию 30.",
            },
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
}

RUN_LINTER = {
    "name": "run_linter",
    "description": (
        "Запускает Ruff только в режиме статической проверки, без автоматических "
        "исправлений. Используй для оценки качества Python-кода после изменений."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Необязательный путь к Python-файлу или каталогу внутри проекта.",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}
