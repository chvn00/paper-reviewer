"""
db.py — Configuración SQLite para el sistema de certificados.
"""
import sqlite3
import uuid
import hashlib
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent.parent
DB_PATH = BASE_DIR / "cert_tracker.db"
CERT_FILES_DIR = BASE_DIR / "cert_files"
CERT_FILES_DIR.mkdir(exist_ok=True)

# Etapas del proceso de certificación
STAGE_NAMES = {
    1: "Solicitud recibida",
    2: "Polígrafo enviado al estudiante",
    3: "Comprobante de pago recibido",
    4: "Certificado elaborado y enviado a Sec. División",
    5: "Firmado en Sec. División (Nelson + sello)",
    6: "Firmado en Sec. General (firma + sello)",
    7: "Recibido de Sec. División",
    8: "Certificado enviado al estudiante",
}

# SLA por etapa: día hábil máximo desde el pago (stage 3)
STAGE_SLA = {
    4: 1,
    5: 2,
    6: 3,
    7: 4,
    8: 5,
}


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return h, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    h, _ = hash_password(password, salt)
    return h == stored_hash


def init_db():
    """Crea las tablas y usuarios por defecto si no existen."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            username    TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt        TEXT NOT NULL,
            full_name   TEXT DEFAULT '',
            role        TEXT NOT NULL DEFAULT 'secretary',
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS certificates (
            id                  TEXT PRIMARY KEY,
            tracking_code       TEXT UNIQUE NOT NULL,
            student_name        TEXT NOT NULL,
            student_id          TEXT NOT NULL,
            student_email       TEXT NOT NULL,
            student_phone       TEXT DEFAULT '',
            certificate_types   TEXT NOT NULL DEFAULT '[]',
            notes               TEXT DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'active',
            current_stage       INTEGER NOT NULL DEFAULT 1,
            created_at          TEXT NOT NULL,
            created_by          TEXT NOT NULL,
            poligrafo_sent_at   TEXT,
            poligrafo_deadline  TEXT,
            payment_received_at TEXT,
            delivery_deadline   TEXT,
            completed_at        TEXT,
            updated_at          TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stages (
            id              TEXT PRIMARY KEY,
            certificate_id  TEXT NOT NULL,
            stage_number    INTEGER NOT NULL,
            stage_name      TEXT NOT NULL,
            completed       INTEGER NOT NULL DEFAULT 0,
            completed_at    TEXT,
            completed_by    TEXT,
            notes           TEXT DEFAULT '',
            FOREIGN KEY (certificate_id) REFERENCES certificates(id) ON DELETE CASCADE,
            UNIQUE(certificate_id, stage_number)
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id              TEXT PRIMARY KEY,
            certificate_id  TEXT NOT NULL,
            stage_number    INTEGER,
            filename        TEXT NOT NULL,
            original_name   TEXT NOT NULL,
            content_type    TEXT NOT NULL DEFAULT 'application/octet-stream',
            description     TEXT DEFAULT '',
            is_certificate  INTEGER NOT NULL DEFAULT 0,
            uploaded_at     TEXT NOT NULL,
            uploaded_by     TEXT NOT NULL,
            FOREIGN KEY (certificate_id) REFERENCES certificates(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS email_logs (
            id              TEXT PRIMARY KEY,
            certificate_id  TEXT NOT NULL,
            stage_number    INTEGER,
            direction       TEXT NOT NULL,
            subject         TEXT DEFAULT '',
            body            TEXT DEFAULT '',
            from_addr       TEXT DEFAULT '',
            to_addr         TEXT DEFAULT '',
            logged_at       TEXT NOT NULL,
            logged_by       TEXT NOT NULL,
            FOREIGN KEY (certificate_id) REFERENCES certificates(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS config (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL
        );
        """)

        conn.execute(
            "INSERT OR IGNORE INTO config (key, value) VALUES ('cert_counter', '0')"
        )
        _create_default_users(conn)
        conn.commit()


def _create_default_users(conn):
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing == 0:
        now = datetime.now().isoformat()
        h1, s1 = hash_password("admin2026")
        conn.execute(
            "INSERT INTO users (id, username, password_hash, salt, full_name, role, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "admin", h1, s1, "Administrador", "admin", now),
        )
        h2, s2 = hash_password("secretaria2026")
        conn.execute(
            "INSERT INTO users (id, username, password_hash, salt, full_name, role, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "secretaria", h2, s2, "Secretaria", "secretary", now),
        )
        print("=" * 50)
        print("[CertTracker] Usuarios por defecto creados:")
        print("  admin       / admin2026")
        print("  secretaria  / secretaria2026")
        print("=" * 50)


def next_tracking_code() -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = 'cert_counter'"
        ).fetchone()
        counter = int(row["value"]) + 1
        conn.execute(
            "UPDATE config SET value = ? WHERE key = 'cert_counter'",
            (str(counter),),
        )
        conn.commit()
    return f"CERT-2026-{counter:04d}"


def create_stages_for_cert(conn, cert_id: str):
    """Inserta las 8 etapas vacías para un nuevo certificado."""
    for num, name in STAGE_NAMES.items():
        conn.execute(
            "INSERT INTO stages (id, certificate_id, stage_number, stage_name) "
            "VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), cert_id, num, name),
        )
