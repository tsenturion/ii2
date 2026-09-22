import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from demo_codebase.quality.bad_example import normalize_name
from dev_lab import format_username

PLUGIN_DIR = (
    Path(__file__).resolve().parents[1]
    / ".hermes"
    / "plugins"
    / "dev-tools"
)


def load_plugin():
    """Загружает plugin как пакет, чтобы работали относительные импорты."""

    package_name = "dev_tools_plugin_for_tests"
    specification = importlib.util.spec_from_file_location(
        package_name,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )

    if specification is None or specification.loader is None:
        raise RuntimeError("Не удалось загрузить тестируемый plugin.")

    module = importlib.util.module_from_spec(specification)
    sys.modules[package_name] = module
    specification.loader.exec_module(module)
    return module


PLUGIN = load_plugin()
TOOLS = PLUGIN.tools


class FakePluginContext:
    def __init__(self):
        self.registrations = []

    def register_tool(self, **kwargs):
        self.registrations.append(kwargs)


class DevToolsRegistrationTests(unittest.TestCase):
    def test_plugin_registers_three_expected_tools(self):
        context = FakePluginContext()

        PLUGIN.register(context)

        self.assertEqual(
            [registration["name"] for registration in context.registrations],
            ["git_diff", "grep_search", "run_linter"],
        )
        self.assertTrue(
            all(
                registration["toolset"] == "dev_tools"
                for registration in context.registrations
            )
        )


class DevToolsPathTests(unittest.TestCase):
    def test_path_must_stay_inside_project(self):
        _, error = TOOLS._safe_relative_path("..\\..")
        self.assertEqual(error, "Путь выходит за пределы проекта.")

        _, error = TOOLS._safe_relative_path(42)
        self.assertEqual(error, "Параметр path должен быть строкой.")

    def test_symlink_outside_project_is_rejected(self):
        with (
            tempfile.TemporaryDirectory() as project_directory,
            tempfile.TemporaryDirectory() as outside_directory,
        ):
            project_root = Path(project_directory)
            link = project_root / "outside-link"

            try:
                link.symlink_to(Path(outside_directory), target_is_directory=True)
            except OSError as error:
                self.skipTest(f"Создание ссылки недоступно: {error}")

            with patch.object(TOOLS, "PROJECT_ROOT", project_root):
                _, path_error = TOOLS._safe_relative_path("outside-link")

        self.assertEqual(path_error, "Путь выходит за пределы проекта.")


class GitDiffToolTests(unittest.TestCase):
    def test_staged_accepts_only_boolean(self):
        with patch.object(TOOLS, "_run_bounded") as run:
            result = json.loads(TOOLS.git_diff({"staged": "false"}))

        self.assertIn("error", result)
        run.assert_not_called()

    def test_git_diff_uses_safe_flags_and_reports_truncation(self):
        process_result = TOOLS._ProcessResult(
            returncode=0,
            stdout="diff content",
            stderr="",
            stdout_truncated=True,
            stderr_truncated=False,
        )

        with patch.object(TOOLS, "_run_bounded", return_value=process_result) as run:
            result = json.loads(
                TOOLS.git_diff({"path": "dev_lab.py", "staged": False})
            )

        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["git", "diff", "--no-ext-diff", "--no-textconv"])
        self.assertEqual(command[-2:], ["--", "dev_lab.py"])
        self.assertTrue(result["truncated"])


class GrepToolTests(unittest.TestCase):
    def test_pattern_and_max_results_are_strictly_validated(self):
        invalid_arguments = [
            {"pattern": ""},
            {"pattern": "User", "max_results": True},
            {"pattern": "User", "max_results": 1.5},
            {"pattern": "User", "max_results": 0},
            {"pattern": "User", "max_results": 101},
        ]

        with patch.object(TOOLS, "_run_bounded") as run:
            results = [
                json.loads(TOOLS.grep_search(arguments))
                for arguments in invalid_arguments
            ]

        self.assertTrue(all("error" in result for result in results))
        run.assert_not_called()

    def test_results_are_limited_without_shell(self):
        process_result = TOOLS._ProcessResult(
            returncode=0,
            stdout="one\ntwo\nthree\n",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
        )

        with patch.object(TOOLS, "_run_bounded", return_value=process_result) as run:
            result = json.loads(
                TOOLS.grep_search(
                    {
                        "pattern": "LegacyPaymentGateway",
                        "path": "demo_codebase",
                        "max_results": 2,
                    }
                )
            )

        self.assertEqual(result["total_matches"], 3)
        self.assertEqual(result["shown_matches"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(run.call_args.args[0][0:2], ["git", "grep"])


class LinterToolTests(unittest.TestCase):
    def test_lint_findings_are_not_tool_errors_and_cache_is_disabled(self):
        process_result = TOOLS._ProcessResult(
            returncode=1,
            stdout="bad_example.py:1:8: F401",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
        )

        with patch.object(TOOLS, "_run_bounded", return_value=process_result) as run:
            result = json.loads(
                TOOLS.run_linter({"path": "demo_codebase/quality/bad_example.py"})
            )

        command = run.call_args.args[0]
        self.assertFalse(result["passed"])
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("--no-cache", command)
        self.assertNotIn("--fix", command)

    def test_ruff_execution_error_is_reported_as_tool_error(self):
        process_result = TOOLS._ProcessResult(
            returncode=2,
            stdout="",
            stderr="configuration error",
            stdout_truncated=False,
            stderr_truncated=False,
        )

        with patch.object(TOOLS, "_run_bounded", return_value=process_result):
            result = json.loads(TOOLS.run_linter({"path": "."}))

        self.assertIn("error", result)


class PracticeBehaviorTests(unittest.TestCase):
    def test_username_helpers(self):
        self.assertEqual(format_username("  Anna Smith  "), "anna_smith")
        self.assertEqual(normalize_name("  Anna Smith  "), "anna smith")


if __name__ == "__main__":
    unittest.main()
