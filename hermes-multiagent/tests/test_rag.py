import importlib.util
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from demo_codebase.auth.session import create_session
from demo_codebase.notifications.email import send_order_email
from demo_codebase.orders.checkout import checkout
from demo_codebase.payments.gateway import PaymentGatewayV2
from demo_codebase.payments.service import get_payment_provider_name
from rag.build_index import build_index, create_chunks, should_index
from rag.logging_config import remove_expired_logs
from rag.search_index import rank_chunks, search


class FakeEncoder:
    def encode(self, texts, **kwargs):
        del kwargs
        vectors = []

        for text in texts:
            lowered = text.lower()

            if "сесси" in lowered or "session" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            elif any(
                marker in lowered
                for marker in ("оплат", "payment", "gateway", "charge")
            ):
                vectors.append([1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])

        return vectors


class RagBuildTests(unittest.TestCase):
    def test_chunks_use_expected_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "module.py"
            source.write_text(
                "\n".join(f"line {number}" for number in range(1, 101)),
                encoding="utf-8",
            )

            chunks = create_chunks(source, root)

        self.assertEqual(
            [(chunk["start_line"], chunk["end_line"]) for chunk in chunks],
            [(1, 60), (46, 100)],
        )

    def test_should_index_excludes_generated_and_service_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            included = root / "demo.py"
            excluded = [
                root / ".venv" / "module.py",
                root / ".hermes" / "plugin.py",
                root / "rag" / "index" / "chunks.json",
                root / "rag" / "logs" / "search.log",
            ]
            included.parent.mkdir(parents=True, exist_ok=True)
            included.write_text("print('ok')", encoding="utf-8")

            for path in excluded:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("data", encoding="utf-8")

            self.assertTrue(should_index(included, root))
            self.assertTrue(all(not should_index(path, root) for path in excluded))

    def test_build_index_accepts_fake_encoder_without_heavy_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payment = root / "demo_codebase" / "payments" / "service.py"
            session = root / "demo_codebase" / "auth" / "session.py"
            payment.parent.mkdir(parents=True)
            session.parent.mkdir(parents=True)
            payment.write_text("def process_payment():\n    pass", encoding="utf-8")
            session.write_text("def create_session():\n    pass", encoding="utf-8")

            chunks, vectors, metadata = build_index(
                project_root=root,
                model_name="fake-model",
                encoder_factory=lambda name: FakeEncoder(),
            )

        self.assertEqual(metadata["files_count"], 2)
        self.assertEqual(metadata["chunks_count"], 2)
        self.assertEqual(metadata["vector_dimension"], 3)
        self.assertEqual(len(chunks), len(vectors))


class RagSearchTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            {
                "path": "demo_codebase/payments/service.py",
                "start_line": 1,
                "end_line": 20,
                "content": "process_payment использует старый gateway",
            },
            {
                "path": "demo_codebase/payments/gateway.py",
                "start_line": 1,
                "end_line": 30,
                "content": "LegacyPaymentGateway и charge_legacy",
            },
            {
                "path": "demo_codebase/orders/checkout.py",
                "start_line": 1,
                "end_line": 20,
                "content": "checkout вызывает process_payment",
            },
            {
                "path": "demo_codebase/auth/session.py",
                "start_line": 1,
                "end_line": 12,
                "content": "create_session создаёт сессию",
            },
        ]
        self.vectors = [
            [1.0, 0.0, 0.0],
            [0.95, 0.05, 0.0],
            [0.8, 0.2, 0.0],
            [0.0, 1.0, 0.0],
        ]
        self.metadata = {
            "model": "fake-model",
            "chunks_count": 4,
            "vector_dimension": 3,
        }

    def test_payment_query_returns_payment_flow_first(self):
        result = search(
            "Где происходит списание оплаты?",
            top_k=3,
            encoder_factory=lambda name: FakeEncoder(),
            index_loader=lambda: (self.chunks, self.vectors, self.metadata),
        )

        self.assertEqual(
            [item["path"] for item in result["results"]],
            [
                "demo_codebase/payments/service.py",
                "demo_codebase/payments/gateway.py",
                "demo_codebase/orders/checkout.py",
            ],
        )

    def test_session_query_returns_session_first(self):
        result = search(
            "Где создаётся пользовательская сессия?",
            top_k=1,
            encoder_factory=lambda name: FakeEncoder(),
            index_loader=lambda: (self.chunks, self.vectors, self.metadata),
        )

        self.assertEqual(
            result["results"][0]["path"],
            "demo_codebase/auth/session.py",
        )

    def test_top_k_is_limited_to_supported_range(self):
        maximum = rank_chunks(self.chunks, self.vectors, [1.0, 0.0, 0.0], 99)
        minimum = rank_chunks(self.chunks, self.vectors, [1.0, 0.0, 0.0], 0)

        self.assertEqual(len(maximum), 4)
        self.assertEqual(len(minimum), 1)

    def test_empty_query_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "запрос пуст"):
            search("   ", index_loader=lambda: None)

    def test_non_integer_top_k_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "целым числом"):
            rank_chunks(self.chunks, self.vectors, [1.0, 0.0, 0.0], 1.5)


class DemoCodebaseTests(unittest.TestCase):
    def test_checkout_uses_legacy_gateway(self):
        order = {"id": 17, "total": 249.5}

        result = checkout(order)

        self.assertEqual(result["order"], order)
        self.assertEqual(result["payment"]["gateway"], "legacy")
        self.assertEqual(result["payment"]["status"], "paid")

    def test_auxiliary_demo_modules(self):
        self.assertEqual(
            PaymentGatewayV2().charge(1, 10.0)["gateway"],
            "v2",
        )
        self.assertEqual(get_payment_provider_name(), "legacy-payment-provider")
        self.assertEqual(create_session(3), {"user_id": 3, "active": True})
        self.assertIn("order@example.com", send_order_email("order@example.com", 17))


class LoggingTests(unittest.TestCase):
    def test_expired_logs_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            expired = log_dir / "expired.log"
            current = log_dir / "current.log"
            expired.write_text("old", encoding="utf-8")
            current.write_text("new", encoding="utf-8")
            old_timestamp = time.time() - 31 * 24 * 60 * 60
            os.utime(expired, (old_timestamp, old_timestamp))

            remove_expired_logs(log_dir, retention_days=30)

            self.assertFalse(expired.exists())
            self.assertTrue(current.exists())


class FakePluginContext:
    def register_tool(self, **kwargs):
        self.registration = kwargs


class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plugin_path = (
            Path(__file__).resolve().parents[1]
            / ".hermes"
            / "plugins"
            / "code-rag"
            / "__init__.py"
        )
        specification = importlib.util.spec_from_file_location(
            "code_rag_plugin_for_tests",
            plugin_path,
        )
        if specification is None or specification.loader is None:
            raise RuntimeError("Не удалось загрузить тестируемый плагин.")
        cls.plugin = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cls.plugin)

    def setUp(self):
        context = FakePluginContext()
        self.plugin.register(context)
        self.registration = context.registration
        self.handler = self.registration["handler"]

    def test_plugin_registers_expected_tool(self):
        self.assertEqual(self.registration["name"], "codebase_search")
        self.assertEqual(self.registration["toolset"], "code_rag")
        parameters = self.registration["schema"]["parameters"]
        self.assertEqual(parameters["properties"]["top_k"]["maximum"], 8)

    def test_plugin_rejects_invalid_top_k_without_starting_process(self):
        with patch.object(self.plugin.subprocess, "run") as run:
            result = json.loads(self.handler({"query": "оплата", "top_k": "bad"}))

        self.assertIn("error", result)
        run.assert_not_called()

    def test_plugin_runs_search_with_safe_command(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"query": "оплата", "results": []}',
            stderr="",
        )

        with patch.object(self.plugin.subprocess, "run", return_value=completed) as run:
            result = json.loads(self.handler({"query": "оплата", "top_k": 3}))

        self.assertEqual(result["query"], "оплата")
        arguments, keywords = run.call_args
        self.assertIn("--query", arguments[0])
        self.assertIn("--top-k", arguments[0])
        self.assertFalse(keywords["shell"])
        self.assertEqual(keywords["timeout"], 120)

    def test_plugin_returns_json_error_on_timeout(self):
        with patch.object(
            self.plugin.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("search", 120),
        ):
            result = json.loads(self.handler({"query": "оплата"}))

        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
