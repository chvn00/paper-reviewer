from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from manzanares_agent.api import ApiApplication
from manzanares_agent.database import CRMDatabase
from manzanares_agent.orchestrator import ManzanaresOrchestrator, OrchestrationError
from tests.common import test_settings


class ManzanaresSystemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = CRMDatabase(Path(self.temp.name) / "test.db")
        self.db.initialize()
        self.db.seed_demo()
        self.settings = test_settings(self.db.path, api_token="secret")
        self.orchestrator = ManzanaresOrchestrator(self.db, self.settings)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_demo_flow_generates_idempotent_tasks_and_audit(self) -> None:
        first = self.orchestrator.run("Dame el briefing comercial de hoy")
        second = self.orchestrator.run("Dame el briefing comercial de hoy")
        self.assertGreaterEqual(len(first.contributions), 5)
        self.assertIn("brecha", first.executive_summary.lower())
        self.assertEqual(len(self.db.list_tasks()), len(self.db.priority_candidates()))
        self.assertEqual(second.contributions[3].metrics["unchanged"], 8)
        with self.db.session() as connection:
            runs = connection.execute("SELECT COUNT(*) FROM system_runs").fetchone()[0]
            audit = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        self.assertEqual(runs, 2)
        self.assertGreater(audit, 2)

    def test_invalid_question_is_rejected(self) -> None:
        with self.assertRaises(OrchestrationError):
            self.orchestrator.run("   ")

    def test_multi_intent_query_combines_required_agents(self) -> None:
        intent, agents = self.orchestrator.classify(
            "Dame la brecha y las prioridades de hoy"
        )
        self.assertEqual(intent, "diagnostico+priorizacion")
        self.assertIn("diagnostico", agents)
        self.assertIn("priorizador", agents)
        self.assertIn("seguimiento", agents)

    def test_api_auth_and_health(self) -> None:
        app = ApiApplication(self.db, self.orchestrator, self.settings)
        status, _ = app.dispatch(
            "GET", "/api/v1/dashboard", None, authorization=None
        )
        self.assertEqual(status, 401)
        status, payload = app.dispatch(
            "GET",
            "/api/v1/dashboard",
            None,
            authorization="Bearer secret",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["contacts"], 8)
        status, health = app.dispatch("GET", "/health", None, authorization=None)
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")


if __name__ == "__main__":
    unittest.main()
