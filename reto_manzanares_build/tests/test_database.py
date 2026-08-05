from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path

from manzanares_agent.database import CRMDatabase, DatabaseError


class DatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = CRMDatabase(Path(self.temp.name) / "test.db")
        self.db.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_schema_enables_integrity_controls(self) -> None:
        self.assertEqual(self.db.schema_version(), 2)
        health = self.db.health()
        self.assertEqual(health["status"], "ok")
        with self.db.session() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_legacy_database_is_migrated_without_losing_contacts(self) -> None:
        legacy_path = Path(self.temp.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.executescript(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT,
                    segment TEXT NOT NULL, status TEXT NOT NULL,
                    monthly_value REAL NOT NULL DEFAULT 0,
                    days_since_purchase INTEGER NOT NULL DEFAULT 0,
                    purchase_frequency INTEGER NOT NULL DEFAULT 0,
                    interest_score INTEGER NOT NULL DEFAULT 0,
                    last_contact_date TEXT, assigned_advisor TEXT
                );
                CREATE TABLE opportunities (
                    id INTEGER PRIMARY KEY, contact_id INTEGER NOT NULL,
                    stage TEXT NOT NULL, estimated_value REAL NOT NULL DEFAULT 0,
                    probability REAL NOT NULL DEFAULT 0, next_action TEXT,
                    next_action_date TEXT, status TEXT NOT NULL DEFAULT 'open'
                );
                CREATE TABLE interactions (
                    id INTEGER PRIMARY KEY, contact_id INTEGER NOT NULL,
                    channel TEXT NOT NULL, outcome TEXT NOT NULL, notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY, contact_id INTEGER NOT NULL,
                    priority TEXT NOT NULL, action TEXT NOT NULL,
                    due_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT NOT NULL
                );
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY, run_id TEXT NOT NULL,
                    agent TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO contacts
                (name, segment, status, monthly_value)
                VALUES ('Cliente legado', 'hotel', 'active', 1000);
                """
            )
            connection.commit()
        finally:
            connection.close()
        legacy = CRMDatabase(legacy_path)
        legacy.initialize()
        self.assertEqual(legacy.schema_version(), 2)
        self.assertEqual(len(legacy.contacts()), 1)
        with legacy.session() as migrated:
            columns = {
                row["name"] for row in migrated.execute("PRAGMA table_info(contacts)")
            }
        self.assertIn("external_id", columns)
        self.assertIn("consent_status", columns)

    def test_demo_seed_is_protected_against_accidental_reset(self) -> None:
        self.db.seed_demo()
        with self.assertRaises(DatabaseError):
            self.db.seed_demo()
        self.assertEqual(self.db.dashboard()["contacts"], 8)

    def test_task_sync_is_idempotent_and_preserves_history(self) -> None:
        self.db.seed_demo()
        contact_id = int(self.db.contacts()[0]["id"])
        task = (contact_id, "alta", "Llamar", "2030-01-01", "Prueba")
        first = self.db.sync_tasks([task], run_id="run-1")
        second = self.db.sync_tasks([task], run_id="run-2")
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(len(self.db.list_tasks()), 1)

    def test_interaction_can_complete_a_task(self) -> None:
        self.db.seed_demo()
        contact_id = int(self.db.contacts()[0]["id"])
        self.db.sync_tasks(
            [(contact_id, "alta", "Llamar", "2030-01-01", "Prueba")],
            run_id="run-1",
        )
        task_id = self.db.list_tasks()[0]["id"]
        interaction_id = self.db.record_interaction(
            contact_id,
            "telefono",
            "contactado",
            task_id=task_id,
        )
        self.assertGreater(interaction_id, 0)
        self.assertEqual(len(self.db.list_tasks("completed")), 1)

    def test_csv_import_supports_dry_run_and_upsert(self) -> None:
        csv_path = Path(self.temp.name) / "contacts.csv"
        csv_path.write_text(
            "external_id,name,segment,status,monthly_value,interest_score\n"
            "c-1,Cliente Uno,hotel,prospect,5000000,80\n"
            "c-2,Cliente Malo,hotel,invalid,1,1\n",
            encoding="utf-8",
        )
        preview = self.db.import_contacts_csv(csv_path, dry_run=True)
        self.assertEqual(preview["accepted"], 1)
        self.assertEqual(preview["rejected"], 1)
        self.assertEqual(self.db.dashboard()["contacts"], 0)
        result = self.db.import_contacts_csv(csv_path)
        self.assertEqual(result["created"], 1)
        self.assertEqual(self.db.dashboard()["contacts"], 1)


if __name__ == "__main__":
    unittest.main()
