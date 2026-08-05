from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


LATEST_SCHEMA_VERSION = 2
VALID_CONTACT_STATUSES = {"active", "inactive", "prospect"}
VALID_PRIORITIES = {"alta", "media", "baja"}
VALID_TASK_STATUSES = {
    "pending",
    "in_progress",
    "completed",
    "cancelled",
    "superseded",
}


SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    segment TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'inactive', 'prospect')),
    monthly_value REAL NOT NULL DEFAULT 0 CHECK(monthly_value >= 0),
    days_since_purchase INTEGER NOT NULL DEFAULT 0 CHECK(days_since_purchase >= 0),
    purchase_frequency INTEGER NOT NULL DEFAULT 0 CHECK(purchase_frequency >= 0),
    interest_score INTEGER NOT NULL DEFAULT 0 CHECK(interest_score BETWEEN 0 AND 100),
    last_contact_date TEXT,
    assigned_advisor TEXT,
    consent_status TEXT NOT NULL DEFAULT 'unknown',
    data_source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    estimated_value REAL NOT NULL DEFAULT 0 CHECK(estimated_value >= 0),
    probability REAL NOT NULL DEFAULT 0 CHECK(probability BETWEEN 0 AND 1),
    next_action TEXT,
    next_action_date TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    outcome TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL,
    priority TEXT NOT NULL CHECK(priority IN ('alta', 'media', 'baja')),
    action TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT NOT NULL,
    source_run_id TEXT,
    generated_by TEXT NOT NULL DEFAULT 'agent',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS system_runs (
    run_id TEXT PRIMARY KEY,
    intent TEXT,
    status TEXT NOT NULL,
    question_hash TEXT NOT NULL,
    agents_requested INTEGER NOT NULL DEFAULT 0,
    agents_completed INTEGER NOT NULL DEFAULT 0,
    llm_used INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'INFO',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_external_id
ON contacts(external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_contacts_status_segment
ON contacts(status, segment);
CREATE INDEX IF NOT EXISTS ix_contacts_advisor
ON contacts(assigned_advisor);
CREATE INDEX IF NOT EXISTS ix_opportunities_status_action
ON opportunities(status, next_action_date);
CREATE INDEX IF NOT EXISTS ix_opportunities_contact
ON opportunities(contact_id);
CREATE INDEX IF NOT EXISTS ix_interactions_contact_created
ON interactions(contact_id, created_at);
CREATE INDEX IF NOT EXISTS ix_tasks_status_due
ON tasks(status, due_date, priority);
CREATE INDEX IF NOT EXISTS ix_tasks_contact
ON tasks(contact_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_task_contact_action
ON tasks(contact_id, action) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS ix_audit_run
ON audit_log(run_id, created_at);
"""


class DatabaseError(RuntimeError):
    """Raised for business-safe database failures."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CRMDatabase:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def session(self) -> Any:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.session() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            existing_tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            applied = {
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            }

            if "contacts" not in existing_tables:
                connection.executescript(SCHEMA_V2)
                connection.executemany(
                    "INSERT OR IGNORE INTO schema_migrations(version, description) VALUES (?, ?)",
                    [
                        (1, "Esquema CRM inicial"),
                        (2, "Controles operativos, auditoria e indices"),
                    ],
                )
            else:
                if 1 not in applied:
                    connection.execute(
                        "INSERT INTO schema_migrations(version, description) VALUES (1, ?)",
                        ("Esquema heredado detectado",),
                    )
                if 2 not in applied:
                    self._migrate_legacy_to_v2(connection)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, description) VALUES (2, ?)",
                        ("Controles operativos, auditoria e indices",),
                    )

            connection.execute(
                """
                UPDATE tasks
                SET status = 'superseded', updated_at = ?
                WHERE status = 'pending'
                  AND id NOT IN (
                      SELECT MAX(id)
                      FROM tasks
                      WHERE status = 'pending'
                      GROUP BY contact_id, action
                  )
                """,
                (utc_now(),),
            )
            connection.executescript(INDEXES)
            connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION}")

    def _migrate_legacy_to_v2(self, connection: sqlite3.Connection) -> None:
        additions: dict[str, list[tuple[str, str]]] = {
            "contacts": [
                ("external_id", "TEXT"),
                ("email", "TEXT"),
                ("consent_status", "TEXT NOT NULL DEFAULT 'unknown'"),
                ("data_source", "TEXT NOT NULL DEFAULT 'manual'"),
                ("created_at", "TEXT"),
                ("updated_at", "TEXT"),
            ],
            "opportunities": [
                ("created_at", "TEXT"),
                ("updated_at", "TEXT"),
            ],
            "tasks": [
                ("source_run_id", "TEXT"),
                ("generated_by", "TEXT NOT NULL DEFAULT 'agent'"),
                ("created_at", "TEXT"),
                ("updated_at", "TEXT"),
                ("completed_at", "TEXT"),
            ],
            "audit_log": [
                ("level", "TEXT NOT NULL DEFAULT 'INFO'"),
                ("metadata_json", "TEXT NOT NULL DEFAULT '{}'"),
            ],
        }
        for table, columns in additions.items():
            existing = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            for name, definition in columns:
                if name not in existing:
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                    )

        now = utc_now()
        connection.execute(
            "UPDATE contacts SET created_at = COALESCE(created_at, ?), "
            "updated_at = COALESCE(updated_at, ?)",
            (now, now),
        )
        connection.execute(
            "UPDATE opportunities SET created_at = COALESCE(created_at, ?), "
            "updated_at = COALESCE(updated_at, ?)",
            (now, now),
        )
        connection.execute(
            "UPDATE tasks SET created_at = COALESCE(created_at, ?), "
            "updated_at = COALESCE(updated_at, ?)",
            (now, now),
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS system_runs (
                run_id TEXT PRIMARY KEY,
                intent TEXT,
                status TEXT NOT NULL,
                question_hash TEXT NOT NULL,
                agents_requested INTEGER NOT NULL DEFAULT 0,
                agents_completed INTEGER NOT NULL DEFAULT 0,
                llm_used INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            )
            """
        )

    def schema_version(self) -> int:
        with self.session() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) version FROM schema_migrations"
            ).fetchone()
            return int(row["version"])

    def seed_demo(self, *, reset: bool = False) -> None:
        contacts = [
            ("demo-001", "Restaurante El Prado", "3001110001", "restaurante", "active", 4_200_000, 12, 4, 82, "Laura"),
            ("demo-002", "Asadero La 27", "3001110002", "restaurante", "inactive", 3_100_000, 74, 3, 88, "Camilo"),
            ("demo-003", "Hotel Santander", "3001110003", "hotel", "active", 6_800_000, 18, 5, 76, "Laura"),
            ("demo-004", "Mercado San Luis", "3001110004", "retail", "prospect", 2_500_000, 0, 0, 91, "Diana"),
            ("demo-005", "Catering Eventos SAS", "3001110005", "institucional", "prospect", 5_100_000, 0, 0, 84, "Camilo"),
            ("demo-006", "Parrilla del Norte", "3001110006", "restaurante", "inactive", 3_900_000, 105, 2, 79, "Diana"),
            ("demo-007", "Tienda La Canasta", "3001110007", "retail", "active", 1_800_000, 27, 2, 68, "Laura"),
            ("demo-008", "Comedor Industrial Oriente", "3001110008", "institucional", "prospect", 8_200_000, 0, 0, 95, "Camilo"),
        ]
        with self.session() as connection:
            current = int(
                connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
            )
            if current and not reset:
                raise DatabaseError(
                    "La base contiene contactos. Use --reset solo en un entorno demo."
                )
            if reset:
                connection.execute("DELETE FROM tasks")
                connection.execute("DELETE FROM interactions")
                connection.execute("DELETE FROM opportunities")
                connection.execute("DELETE FROM contacts")
            connection.executemany(
                """
                INSERT INTO contacts
                (external_id, name, phone, segment, status, monthly_value,
                 days_since_purchase, purchase_frequency, interest_score,
                 assigned_advisor, consent_status, data_source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', 'demo', ?, ?)
                """,
                [(*row, utc_now(), utc_now()) for row in contacts],
            )
            contact_ids = {
                row["external_id"]: row["id"]
                for row in connection.execute(
                    "SELECT id, external_id FROM contacts WHERE external_id LIKE 'demo-%'"
                )
            }
            opportunities = [
                (contact_ids["demo-004"], "qualified", 2_500_000, 0.55, "Enviar portafolio", str(date.today() + timedelta(days=1))),
                (contact_ids["demo-005"], "proposal", 5_100_000, 0.70, "Confirmar prueba de producto", str(date.today() + timedelta(days=2))),
                (contact_ids["demo-008"], "contacted", 8_200_000, 0.62, "Agendar reunion", str(date.today())),
            ]
            connection.executemany(
                """
                INSERT INTO opportunities
                (contact_id, stage, estimated_value, probability, next_action,
                 next_action_date, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(*row, utc_now(), utc_now()) for row in opportunities],
            )

    def contacts(self) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(connection.execute("SELECT * FROM contacts ORDER BY id"))

    def priority_candidates(self) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """
                    SELECT c.*,
                           COALESCE(SUM(
                               CASE WHEN o.status = 'open'
                               THEN o.estimated_value * o.probability ELSE 0 END
                           ), 0) weighted_pipeline,
                           MIN(CASE WHEN o.status = 'open' THEN o.next_action_date END)
                               next_action_date,
                           MAX(CASE WHEN o.status = 'open' THEN o.next_action END)
                               next_action
                    FROM contacts c
                    LEFT JOIN opportunities o ON o.contact_id = c.id
                    GROUP BY c.id
                    ORDER BY c.id
                    """
                )
            )

    def open_opportunities(self) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """
                    SELECT o.*, c.name, c.segment, c.interest_score
                    FROM opportunities o
                    JOIN contacts c ON c.id = o.contact_id
                    WHERE o.status = 'open'
                    ORDER BY o.estimated_value * o.probability DESC
                    """
                )
            )

    def sync_tasks(
        self,
        tasks: Iterable[tuple[int, str, str, str, str]],
        *,
        run_id: str,
    ) -> dict[str, int]:
        task_list = list(tasks)
        result = {"created": 0, "updated": 0, "unchanged": 0, "superseded": 0}
        with self.session() as connection:
            for contact_id, desired_action in {
                (item[0], item[2]) for item in task_list
            }:
                result["superseded"] += connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'superseded', updated_at = ?
                    WHERE contact_id = ? AND status = 'pending'
                      AND generated_by = 'agent' AND action <> ?
                    """,
                    (utc_now(), contact_id, desired_action),
                ).rowcount
            for contact_id, priority, action, due_date, reason in task_list:
                if priority not in VALID_PRIORITIES:
                    raise DatabaseError(f"Prioridad invalida: {priority}")
                date.fromisoformat(due_date)
                existing = connection.execute(
                    """
                    SELECT id, priority, due_date, reason
                    FROM tasks
                    WHERE contact_id = ? AND action = ? AND status = 'pending'
                    """,
                    (contact_id, action),
                ).fetchone()
                if existing:
                    changed = (
                        existing["priority"] != priority
                        or existing["due_date"] != due_date
                        or existing["reason"] != reason
                    )
                    if changed:
                        connection.execute(
                            """
                            UPDATE tasks
                            SET priority = ?, due_date = ?, reason = ?,
                                source_run_id = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                priority,
                                due_date,
                                reason,
                                run_id,
                                utc_now(),
                                existing["id"],
                            ),
                        )
                        result["updated"] += 1
                    else:
                        result["unchanged"] += 1
                else:
                    connection.execute(
                        """
                        INSERT INTO tasks
                        (contact_id, priority, action, due_date, reason,
                         source_run_id, generated_by, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'agent', ?, ?)
                        """,
                        (
                            contact_id,
                            priority,
                            action,
                            due_date,
                            reason,
                            run_id,
                            utc_now(),
                            utc_now(),
                        ),
                    )
                    result["created"] += 1
        return result

    def list_tasks(self, status: str = "pending") -> list[dict[str, Any]]:
        if status not in VALID_TASK_STATUSES and status != "all":
            raise DatabaseError(f"Estado de tarea invalido: {status}")
        where = "" if status == "all" else "WHERE t.status = ?"
        parameters: tuple[Any, ...] = () if status == "all" else (status,)
        with self.session() as connection:
            rows = connection.execute(
                f"""
                SELECT t.*, c.name contact_name, c.assigned_advisor
                FROM tasks t
                JOIN contacts c ON c.id = t.contact_id
                {where}
                ORDER BY
                    CASE t.priority WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END,
                    t.due_date,
                    t.id
                """,
                parameters,
            )
            return [dict(row) for row in rows]

    def record_interaction(
        self,
        contact_id: int,
        channel: str,
        outcome: str,
        notes: str = "",
        *,
        task_id: int | None = None,
    ) -> int:
        channel = channel.strip().lower()
        outcome = outcome.strip().lower()
        if not channel or not outcome:
            raise DatabaseError("Canal y resultado son obligatorios.")
        if len(notes) > 4_000:
            raise DatabaseError("Las notas no pueden superar 4000 caracteres.")
        with self.session() as connection:
            exists = connection.execute(
                "SELECT 1 FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
            if not exists:
                raise DatabaseError(f"Contacto inexistente: {contact_id}")
            cursor = connection.execute(
                """
                INSERT INTO interactions(contact_id, channel, outcome, notes)
                VALUES (?, ?, ?, ?)
                """,
                (contact_id, channel, outcome, notes.strip()),
            )
            connection.execute(
                "UPDATE contacts SET last_contact_date = ?, updated_at = ? WHERE id = ?",
                (str(date.today()), utc_now(), contact_id),
            )
            if task_id is not None:
                updated = connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'completed', completed_at = ?, updated_at = ?
                    WHERE id = ? AND contact_id = ? AND status IN ('pending', 'in_progress')
                    """,
                    (utc_now(), utc_now(), task_id, contact_id),
                ).rowcount
                if not updated:
                    raise DatabaseError(
                        "La tarea no existe, no pertenece al contacto o ya fue cerrada."
                    )
            return int(cursor.lastrowid)

    def start_run(
        self, run_id: str, question_hash: str, intent: str, agents_requested: int
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO system_runs
                (run_id, intent, status, question_hash, agents_requested)
                VALUES (?, ?, 'running', ?, ?)
                """,
                (run_id, intent, question_hash, agents_requested),
            )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        agents_completed: int,
        llm_used: bool,
        duration_ms: int,
        error_message: str | None = None,
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """
                UPDATE system_runs
                SET status = ?, agents_completed = ?, llm_used = ?,
                    duration_ms = ?, error_message = ?, finished_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    agents_completed,
                    int(llm_used),
                    duration_ms,
                    error_message,
                    utc_now(),
                    run_id,
                ),
            )

    def log(
        self,
        run_id: str,
        agent: str,
        event: str,
        detail: str,
        *,
        level: str = "INFO",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        safe_detail = detail.strip()[:2_000]
        safe_metadata = json.dumps(
            metadata or {}, ensure_ascii=False, separators=(",", ":")
        )[:8_000]
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO audit_log
                (run_id, agent, event, detail, level, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, agent, event, safe_detail, level.upper(), safe_metadata),
            )

    def dashboard(self) -> dict[str, float | int]:
        with self.session() as connection:
            contacts = connection.execute(
                """
                SELECT
                    COUNT(*) total,
                    COALESCE(SUM(status = 'active'), 0) active,
                    COALESCE(SUM(status = 'inactive'), 0) inactive,
                    COALESCE(SUM(status = 'prospect'), 0) prospects,
                    COALESCE(SUM(
                        CASE WHEN status = 'active' THEN monthly_value ELSE 0 END
                    ), 0) active_value,
                    COALESCE(AVG(
                        (phone IS NOT NULL AND TRIM(phone) <> '') +
                        (segment IS NOT NULL AND TRIM(segment) <> '') +
                        (assigned_advisor IS NOT NULL AND TRIM(assigned_advisor) <> '')
                    ) / 3.0 * 100, 0) completeness
                FROM contacts
                """
            ).fetchone()
            pipeline = connection.execute(
                """
                SELECT
                    COUNT(*) opportunities,
                    COALESCE(SUM(estimated_value), 0) gross_pipeline,
                    COALESCE(SUM(estimated_value * probability), 0) weighted_pipeline
                FROM opportunities
                WHERE status = 'open'
                """
            ).fetchone()
            tasks = connection.execute(
                """
                SELECT
                    COALESCE(SUM(status = 'pending'), 0) pending,
                    COALESCE(SUM(status = 'pending' AND priority = 'alta'), 0) high,
                    COALESCE(SUM(status = 'pending' AND due_date < date('now')), 0) overdue,
                    COALESCE(SUM(status = 'completed'), 0) completed,
                    COUNT(*) total
                FROM tasks
                """
            ).fetchone()
            recent_interactions = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM interactions
                    WHERE created_at >= datetime('now', '-30 days')
                    """
                ).fetchone()[0]
            )
        completion_rate = (
            float(tasks["completed"]) / float(tasks["total"]) * 100
            if tasks["total"]
            else 0.0
        )
        return {
            "contacts": int(contacts["total"]),
            "active_contacts": int(contacts["active"]),
            "inactive_contacts": int(contacts["inactive"]),
            "prospects": int(contacts["prospects"]),
            "active_monthly_value": round(float(contacts["active_value"]), 2),
            "open_opportunities": int(pipeline["opportunities"]),
            "gross_pipeline": round(float(pipeline["gross_pipeline"]), 2),
            "weighted_pipeline": round(float(pipeline["weighted_pipeline"]), 2),
            "pending_tasks": int(tasks["pending"]),
            "high_priority_tasks": int(tasks["high"]),
            "overdue_tasks": int(tasks["overdue"]),
            "task_completion_rate": round(completion_rate, 1),
            "interactions_last_30_days": recent_interactions,
            "data_completeness": round(float(contacts["completeness"]), 1),
        }

    def import_contacts_csv(
        self, source: Path, *, dry_run: bool = False
    ) -> dict[str, Any]:
        if not source.exists():
            raise DatabaseError(f"No existe el archivo: {source}")
        accepted: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"external_id", "name", "segment", "status"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise DatabaseError(
                    f"Faltan columnas obligatorias: {', '.join(sorted(missing))}"
                )
            for line_number, row in enumerate(reader, start=2):
                try:
                    status = (row.get("status") or "").strip().lower()
                    if status not in VALID_CONTACT_STATUSES:
                        raise ValueError("status debe ser active, inactive o prospect")
                    external_id = (row.get("external_id") or "").strip()
                    name = (row.get("name") or "").strip()
                    segment = (row.get("segment") or "").strip()
                    if not external_id or not name or not segment:
                        raise ValueError(
                            "external_id, name y segment son obligatorios"
                        )
                    monthly_value = max(
                        float(row.get("monthly_value") or 0), 0
                    )
                    days_since_purchase = max(
                        int(row.get("days_since_purchase") or 0), 0
                    )
                    purchase_frequency = max(
                        int(row.get("purchase_frequency") or 0), 0
                    )
                    interest_score = int(row.get("interest_score") or 0)
                    if not 0 <= interest_score <= 100:
                        raise ValueError("interest_score debe estar entre 0 y 100")
                    accepted.append(
                        {
                            "external_id": external_id,
                            "name": name,
                            "phone": (row.get("phone") or "").strip() or None,
                            "email": (row.get("email") or "").strip() or None,
                            "segment": segment,
                            "status": status,
                            "monthly_value": monthly_value,
                            "days_since_purchase": days_since_purchase,
                            "purchase_frequency": purchase_frequency,
                            "interest_score": interest_score,
                            "assigned_advisor": (
                                row.get("assigned_advisor") or ""
                            ).strip()
                            or None,
                            "consent_status": (
                                row.get("consent_status") or "unknown"
                            ).strip(),
                        }
                    )
                except (TypeError, ValueError) as exc:
                    errors.append({"line": line_number, "error": str(exc)})

        if dry_run:
            return {
                "accepted": len(accepted),
                "rejected": len(errors),
                "created": 0,
                "updated": 0,
                "errors": errors,
                "dry_run": True,
            }

        created = 0
        updated = 0
        with self.session() as connection:
            for row in accepted:
                exists = connection.execute(
                    "SELECT id FROM contacts WHERE external_id = ?",
                    (row["external_id"],),
                ).fetchone()
                values = (
                    row["name"],
                    row["phone"],
                    row["email"],
                    row["segment"],
                    row["status"],
                    row["monthly_value"],
                    row["days_since_purchase"],
                    row["purchase_frequency"],
                    row["interest_score"],
                    row["assigned_advisor"],
                    row["consent_status"],
                    utc_now(),
                    row["external_id"],
                )
                if exists:
                    connection.execute(
                        """
                        UPDATE contacts
                        SET name = ?, phone = ?, email = ?, segment = ?, status = ?,
                            monthly_value = ?, days_since_purchase = ?,
                            purchase_frequency = ?, interest_score = ?,
                            assigned_advisor = ?, consent_status = ?,
                            data_source = 'csv', updated_at = ?
                        WHERE external_id = ?
                        """,
                        values,
                    )
                    updated += 1
                else:
                    connection.execute(
                        """
                        INSERT INTO contacts
                        (name, phone, email, segment, status, monthly_value,
                         days_since_purchase, purchase_frequency, interest_score,
                         assigned_advisor, consent_status, data_source, updated_at,
                         external_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'csv', ?, ?, ?)
                        """,
                        (*values[:-2], values[-2], row["external_id"], utc_now()),
                    )
                    created += 1
        return {
            "accepted": len(accepted),
            "rejected": len(errors),
            "created": created,
            "updated": updated,
            "errors": errors,
            "dry_run": False,
        }

    def backup(self, destination: Path) -> Path:
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise DatabaseError("El backup debe usar una ruta diferente a la base.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
        return destination

    def health(self) -> dict[str, Any]:
        try:
            with self.session() as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_key_errors = list(
                    connection.execute("PRAGMA foreign_key_check")
                )
                version = self.schema_version()
            healthy = (
                integrity == "ok"
                and not foreign_key_errors
                and version == LATEST_SCHEMA_VERSION
            )
            return {
                "status": "ok" if healthy else "degraded",
                "database": str(self.path),
                "integrity": integrity,
                "foreign_key_errors": len(foreign_key_errors),
                "schema_version": version,
                "expected_schema_version": LATEST_SCHEMA_VERSION,
            }
        except sqlite3.Error as exc:
            return {
                "status": "error",
                "database": str(self.path),
                "error": str(exc),
            }
