"""Регистрация инструментов плагина dev-tools."""

from typing import Any

from . import schemas, tools


def register(ctx: Any) -> None:
    """Регистрирует безопасные инструменты анализа в Hermes."""

    ctx.register_tool(
        name="git_diff",
        toolset="dev_tools",
        schema=schemas.GIT_DIFF,
        handler=tools.git_diff,
    )
    ctx.register_tool(
        name="grep_search",
        toolset="dev_tools",
        schema=schemas.GREP_SEARCH,
        handler=tools.grep_search,
    )
    ctx.register_tool(
        name="run_linter",
        toolset="dev_tools",
        schema=schemas.RUN_LINTER,
        handler=tools.run_linter,
    )
