"""
router.py — FastAPI router para el sistema de seguimiento de certificados.
Endpoints bajo el prefijo /cert/
"""
import uuid
import json
import secrets
from pathlib import Path
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request, Form
from fastapi.responses import FileResponse

from .db import (
    get_conn, verify_password, next_tracking_code,
    create_stages_for_cert, STAGE_NAMES, STAGE_SLA, CERT_FILES_DIR
)
from .models import (
    LoginRequest, CertificateCreate, CertificateUpdate,
    StageCompleteRequest, EmailLogCreate
)
from .calendar_co import (
    add_business_days, business_days_elapsed,
    business_days_remaining, is_business_day
)

router = APIRouter(prefix="/cert", tags=["certificates"])

# ── Sesiones en memoria ───────────────────────────────────────────────────────
# { token: { "user_id": str, "username": str, "role": str, "full_name": str } }
_sessions: dict = {}

MAX_ATTACHMENT_MB = 20


# ── Helpers de autenticación ─────────────────────────────────────────────────

def _get_session(request: Request) -> dict:
    token = request.headers.get("X-Session-Token", "")
    if not token or token not in _sessions:
        raise HTTPException(status_code=401, detail="No autorizado. Inicie sesión.")
    return _sessions[token]


def _require_admin(request: Request) -> dict:
    session = _get_session(request)
    if session["role"] != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol de administrador.")
    return session


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post("/auth/login")
def login(req: LoginRequest):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (req.username,)
        ).fetchone()
    if not row or not verify_password(req.password, row["password_hash"], row["salt"]):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "user_id":   row["id"],
        "username":  row["username"],
        "full_name": row["full_name"],
        "role":      row["role"],
    }
    return {
        "token":      token,
        "username":   row["username"],
        "full_name":  row["full_name"],
        "role":       row["role"],
    }


@router.post("/auth/logout")
def logout(request: Request):
    token = request.headers.get("X-Session-Token", "")
    _sessions.pop(token, None)
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request):
    return _get_session(request)


# ── SLA por tipo de certificado ───────────────────────────────────────────────
_CERT_TYPE_SLA: dict[str, int] = {
    "certificado de contenido programático":  20,
    "certificado de contenido programatico":  20,
}
_DEFAULT_SLA = 10

def _get_cert_sla(certificate_types: list) -> int:
    """Días hábiles de entrega según los tipos solicitados (máximo si hay varios)."""
    return max(
        (_CERT_TYPE_SLA.get(ct.lower().strip(), _DEFAULT_SLA) for ct in certificate_types),
        default=_DEFAULT_SLA,
    )


# ── Helpers de negocio ────────────────────────────────────────────────────────

def _compute_alert(cert: dict, stages: list) -> dict:
    """
    Calcula el estado de alerta de un certificado.
    Retorna { level: 'ok'|'warning'|'critical'|'overdue', message: str, days_remaining: int|None }
    """
    status = cert["status"]

    if status == "completed":
        return {"level": "ok", "message": "Completado", "days_remaining": None}
    if status in ("cancelled_no_payment", "cancelled"):
        return {"level": "info", "message": "Cancelado", "days_remaining": None}

    today = date.today()

    # ── Revisar vencimiento del polígrafo (stage 2 completada, stage 3 no) ──
    poligrafo_sent = cert.get("poligrafo_sent_at")
    payment_received = cert.get("payment_received_at")

    if poligrafo_sent and not payment_received:
        sent_date = date.fromisoformat(poligrafo_sent[:10])
        elapsed = business_days_elapsed(sent_date, today)
        if elapsed >= 5:
            return {
                "level": "critical",
                "message": f"⚠️ Polígrafo vencido ({elapsed} días hábiles sin pago)",
                "days_remaining": 0,
            }
        if elapsed == 4:
            return {
                "level": "warning",
                "message": "Polígrafo vence mañana — último día para recibir pago",
                "days_remaining": 1,
            }
        remaining = 5 - elapsed
        return {
            "level": "ok",
            "message": f"Esperando pago ({elapsed}/5 días hábiles)",
            "days_remaining": remaining,
        }

    # ── Si hay pago, revisar SLA de las etapas 4–8 ─────────────────────────
    if payment_received:
        payment_date = date.fromisoformat(payment_received[:10])
        deadline_date = date.fromisoformat(cert["delivery_deadline"][:10])
        elapsed = business_days_elapsed(payment_date, today)
        days_left = business_days_remaining(deadline_date, today)
        current_stage = cert["current_stage"]

        if current_stage > 8:
            return {"level": "ok", "message": "Completado", "days_remaining": None}

        # Buscar si la etapa actual tiene SLA propio
        stage_sla = STAGE_SLA.get(current_stage)

        if days_left <= 0 and current_stage <= 8:
            return {
                "level": "overdue",
                "message": f"🔴 VENCIDO — {abs(days_left)} días hábiles de retraso",
                "days_remaining": days_left,
            }
        if days_left == 1:
            return {
                "level": "critical",
                "message": f"🟠 Vence HOY — Etapa {current_stage}: {STAGE_NAMES.get(current_stage, '')}",
                "days_remaining": 1,
            }
        if days_left == 2:
            return {
                "level": "warning",
                "message": f"🟡 Vence mañana — {days_left} días hábiles restantes",
                "days_remaining": days_left,
            }

        # Revisar si la etapa actual está atrasada respecto a su SLA propio
        if stage_sla and elapsed > stage_sla:
            return {
                "level": "warning",
                "message": f"Etapa {current_stage} con retraso ({elapsed} días desde pago, SLA: {stage_sla})",
                "days_remaining": days_left,
            }

        return {
            "level": "ok",
            "message": f"{days_left} días hábiles restantes",
            "days_remaining": days_left,
        }

    # Sin polígrafo enviado todavía
    return {"level": "ok", "message": "Solicitud recibida", "days_remaining": None}


def _cert_to_dict(row) -> dict:
    d = dict(row)
    if isinstance(d.get("certificate_types"), str):
        try:
            d["certificate_types"] = json.loads(d["certificate_types"])
        except Exception:
            d["certificate_types"] = []
    return d


def _row_to_dict(row) -> dict:
    return dict(row)


# ── Certificados ──────────────────────────────────────────────────────────────

@router.get("/certificates")
def list_certificates(request: Request, status: Optional[str] = None):
    _get_session(request)
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM certificates WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM certificates ORDER BY created_at DESC"
            ).fetchall()

    certs = []
    for row in rows:
        cert = _cert_to_dict(row)
        # Obtener etapas para cálculo de alerta
        with get_conn() as conn2:
            stages = [
                _row_to_dict(s)
                for s in conn2.execute(
                    "SELECT * FROM stages WHERE certificate_id = ? ORDER BY stage_number",
                    (cert["id"],),
                ).fetchall()
            ]
        cert["alert"] = _compute_alert(cert, stages)
        certs.append(cert)

    return {"certificates": certs, "total": len(certs)}


@router.post("/certificates")
def create_certificate(req: CertificateCreate, request: Request):
    session = _get_session(request)
    cert_id = str(uuid.uuid4())
    tracking_code = next_tracking_code()
    now = datetime.now().isoformat()

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO certificates
               (id, tracking_code, student_name, student_id, student_email,
                student_phone, certificate_types, notes, status, current_stage,
                created_at, created_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?, ?)""",
            (
                cert_id, tracking_code,
                req.student_name, req.student_id, req.student_email,
                req.student_phone or "",
                json.dumps(req.certificate_types, ensure_ascii=False),
                req.notes or "",
                now, session["username"], now,
            ),
        )
        create_stages_for_cert(conn, cert_id)
        conn.commit()

    return {"id": cert_id, "tracking_code": tracking_code}


@router.get("/certificates/{cert_id}")
def get_certificate(cert_id: str, request: Request):
    _get_session(request)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM certificates WHERE id = ?", (cert_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Certificado no encontrado.")

        cert = _cert_to_dict(row)

        stages = [
            _row_to_dict(s)
            for s in conn.execute(
                "SELECT * FROM stages WHERE certificate_id = ? ORDER BY stage_number",
                (cert_id,),
            ).fetchall()
        ]
        attachments = [
            _row_to_dict(a)
            for a in conn.execute(
                "SELECT id, certificate_id, stage_number, original_name, "
                "content_type, description, is_certificate, uploaded_at, uploaded_by "
                "FROM attachments WHERE certificate_id = ? ORDER BY uploaded_at DESC",
                (cert_id,),
            ).fetchall()
        ]
        emails = [
            _row_to_dict(e)
            for e in conn.execute(
                "SELECT * FROM email_logs WHERE certificate_id = ? ORDER BY logged_at DESC",
                (cert_id,),
            ).fetchall()
        ]

    cert["stages"] = stages
    cert["attachments"] = attachments
    cert["emails"] = emails
    cert["alert"] = _compute_alert(cert, stages)
    return cert


@router.put("/certificates/{cert_id}")
def update_certificate(cert_id: str, req: CertificateUpdate, request: Request):
    session = _get_session(request)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM certificates WHERE id = ?", (cert_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Certificado no encontrado.")

        updates = {}
        if req.student_name is not None:
            updates["student_name"] = req.student_name
        if req.student_email is not None:
            updates["student_email"] = req.student_email
        if req.student_phone is not None:
            updates["student_phone"] = req.student_phone
        if req.certificate_types is not None:
            updates["certificate_types"] = json.dumps(req.certificate_types, ensure_ascii=False)
        if req.notes is not None:
            updates["notes"] = req.notes

        if updates:
            updates["updated_at"] = datetime.now().isoformat()
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE certificates SET {set_clause} WHERE id = ?",
                list(updates.values()) + [cert_id],
            )
            conn.commit()

    return {"ok": True}


@router.delete("/certificates/{cert_id}")
def cancel_certificate(cert_id: str, request: Request, reason: str = "cancelled"):
    _get_session(request)
    valid = ("cancelled", "cancelled_no_payment")
    if reason not in valid:
        reason = "cancelled"
    with get_conn() as conn:
        conn.execute(
            "UPDATE certificates SET status = ?, updated_at = ? WHERE id = ?",
            (reason, datetime.now().isoformat(), cert_id),
        )
        conn.commit()
    return {"ok": True}


# ── Etapas ────────────────────────────────────────────────────────────────────

@router.post("/certificates/{cert_id}/stages/{stage_number}/complete")
def complete_stage(cert_id: str, stage_number: int, req: StageCompleteRequest, request: Request):
    session = _get_session(request)
    if stage_number < 1 or stage_number > 8:
        raise HTTPException(400, "Número de etapa inválido (1–8).")

    now_iso = datetime.now().isoformat()
    completed_at = req.completed_at or date.today().isoformat()

    with get_conn() as conn:
        cert = conn.execute(
            "SELECT * FROM certificates WHERE id = ?", (cert_id,)
        ).fetchone()
        if not cert:
            raise HTTPException(404, "Certificado no encontrado.")
        if cert["status"] not in ("active",):
            raise HTTPException(400, "Solo se pueden actualizar certificados activos.")

        # Marcar la etapa como completada
        conn.execute(
            "UPDATE stages SET completed = 1, completed_at = ?, completed_by = ?, notes = ? "
            "WHERE certificate_id = ? AND stage_number = ?",
            (completed_at, session["username"], req.notes or "", cert_id, stage_number),
        )

        # Actualizar metadatos especiales según la etapa
        cert_updates: dict = {
            "current_stage": stage_number + 1,
            "updated_at": now_iso,
        }

        if stage_number == 2:
            # Polígrafo enviado → calcular deadline de pago (5 días hábiles)
            sent_date = date.fromisoformat(completed_at)
            deadline = add_business_days(sent_date, 5)
            cert_updates["poligrafo_sent_at"] = completed_at
            cert_updates["poligrafo_deadline"] = deadline.isoformat()

        elif stage_number == 3:
            # Pago recibido → arrancar reloj según tipo de certificado
            payment_date = date.fromisoformat(completed_at)
            cert_types = json.loads(cert["certificate_types"] or "[]")
            sla_days = _get_cert_sla(cert_types)
            delivery_deadline = add_business_days(payment_date, sla_days)
            cert_updates["payment_received_at"] = completed_at
            cert_updates["delivery_deadline"] = delivery_deadline.isoformat()

        elif stage_number == 8:
            # Certificado entregado → marcar como completado
            cert_updates["status"] = "completed"
            cert_updates["completed_at"] = completed_at
            cert_updates["current_stage"] = 8

        set_clause = ", ".join(f"{k} = ?" for k in cert_updates)
        conn.execute(
            f"UPDATE certificates SET {set_clause} WHERE id = ?",
            list(cert_updates.values()) + [cert_id],
        )
        conn.commit()

    return {"ok": True, "stage": stage_number, "completed_at": completed_at}


@router.post("/certificates/{cert_id}/stages/{stage_number}/undo")
def undo_stage(cert_id: str, stage_number: int, request: Request):
    """Deshace la marca de completado de una etapa."""
    _get_session(request)
    with get_conn() as conn:
        cert = conn.execute(
            "SELECT * FROM certificates WHERE id = ?", (cert_id,)
        ).fetchone()
        if not cert:
            raise HTTPException(404, "Certificado no encontrado.")

        conn.execute(
            "UPDATE stages SET completed = 0, completed_at = NULL, completed_by = NULL "
            "WHERE certificate_id = ? AND stage_number = ?",
            (cert_id, stage_number),
        )

        # Revertir metadatos especiales
        updates: dict = {
            "current_stage": stage_number,
            "updated_at": datetime.now().isoformat(),
        }
        if stage_number == 2:
            updates["poligrafo_sent_at"] = None
            updates["poligrafo_deadline"] = None
        elif stage_number == 3:
            updates["payment_received_at"] = None
            updates["delivery_deadline"] = None
        elif stage_number == 8:
            updates["status"] = "active"
            updates["completed_at"] = None

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE certificates SET {set_clause} WHERE id = ?",
            list(updates.values()) + [cert_id],
        )
        conn.commit()

    return {"ok": True}


# ── Archivos adjuntos ─────────────────────────────────────────────────────────

@router.post("/certificates/{cert_id}/attachments")
async def upload_attachment(
    cert_id: str,
    request: Request,
    file: UploadFile = File(...),
    stage_number: Optional[int] = Form(None),
    description: str = Form(""),
    is_certificate: bool = Form(False),
):
    session = _get_session(request)

    with get_conn() as conn:
        if not conn.execute(
            "SELECT id FROM certificates WHERE id = ?", (cert_id,)
        ).fetchone():
            raise HTTPException(404, "Certificado no encontrado.")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_ATTACHMENT_MB:
        raise HTTPException(413, f"Archivo demasiado grande ({size_mb:.1f} MB). Máx: {MAX_ATTACHMENT_MB} MB.")

    attachment_id = str(uuid.uuid4())
    suffix = Path(file.filename).suffix
    stored_name = f"{attachment_id}{suffix}"

    # Guardar en carpeta del certificado
    cert_dir = CERT_FILES_DIR / cert_id
    cert_dir.mkdir(exist_ok=True)
    (cert_dir / stored_name).write_bytes(content)

    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO attachments "
            "(id, certificate_id, stage_number, filename, original_name, "
            "content_type, description, is_certificate, uploaded_at, uploaded_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attachment_id, cert_id, stage_number, stored_name,
                file.filename, file.content_type or "application/octet-stream",
                description, 1 if is_certificate else 0,
                now, session["username"],
            ),
        )
        conn.commit()

    return {
        "id": attachment_id,
        "original_name": file.filename,
        "uploaded_at": now,
    }


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: str, request: Request):
    _get_session(request)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Archivo no encontrado.")

    file_path = CERT_FILES_DIR / row["certificate_id"] / row["filename"]
    if not file_path.exists():
        raise HTTPException(404, "Archivo no encontrado en el servidor.")

    return FileResponse(
        path=str(file_path),
        media_type=row["content_type"],
        filename=row["original_name"],
    )


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, request: Request):
    _get_session(request)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Archivo no encontrado.")
        file_path = CERT_FILES_DIR / row["certificate_id"] / row["filename"]
        file_path.unlink(missing_ok=True)
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        conn.commit()
    return {"ok": True}


# ── Registro de correos ───────────────────────────────────────────────────────

@router.post("/certificates/{cert_id}/emails")
def log_email(cert_id: str, req: EmailLogCreate, request: Request):
    session = _get_session(request)
    with get_conn() as conn:
        if not conn.execute(
            "SELECT id FROM certificates WHERE id = ?", (cert_id,)
        ).fetchone():
            raise HTTPException(404, "Certificado no encontrado.")

    log_id = str(uuid.uuid4())
    logged_at = req.logged_at or datetime.now().isoformat()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO email_logs "
            "(id, certificate_id, stage_number, direction, subject, body, "
            "from_addr, to_addr, logged_at, logged_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                log_id, cert_id, req.stage_number, req.direction,
                req.subject, req.body, req.from_addr, req.to_addr,
                logged_at, session["username"],
            ),
        )
        conn.commit()

    return {"id": log_id, "logged_at": logged_at}


@router.delete("/emails/{email_id}")
def delete_email_log(email_id: str, request: Request):
    _get_session(request)
    with get_conn() as conn:
        conn.execute("DELETE FROM email_logs WHERE id = ?", (email_id,))
        conn.commit()
    return {"ok": True}


# ── Dashboard / Alertas ───────────────────────────────────────────────────────

@router.get("/alerts")
def get_alerts(request: Request):
    """Retorna todos los certificados activos con alertas warning/critical/overdue."""
    _get_session(request)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM certificates WHERE status = 'active' ORDER BY created_at"
        ).fetchall()

    alerts = []
    for row in rows:
        cert = _cert_to_dict(row)
        with get_conn() as conn2:
            stages = [
                _row_to_dict(s)
                for s in conn2.execute(
                    "SELECT * FROM stages WHERE certificate_id = ? ORDER BY stage_number",
                    (cert["id"],),
                ).fetchall()
            ]
        alert = _compute_alert(cert, stages)
        if alert["level"] in ("warning", "critical", "overdue"):
            alerts.append({
                "cert_id":        cert["id"],
                "tracking_code":  cert["tracking_code"],
                "student_name":   cert["student_name"],
                "current_stage":  cert["current_stage"],
                "stage_name":     STAGE_NAMES.get(cert["current_stage"], ""),
                "alert":          alert,
            })

    # Ordenar: overdue primero, luego critical, luego warning
    priority = {"overdue": 0, "critical": 1, "warning": 2}
    alerts.sort(key=lambda x: priority.get(x["alert"]["level"], 9))
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/stats")
def get_stats(request: Request):
    """Estadísticas para el panel principal."""
    _get_session(request)
    today = date.today()
    month_start = today.replace(day=1).isoformat()

    with get_conn() as conn:
        total_active = conn.execute(
            "SELECT COUNT(*) FROM certificates WHERE status = 'active'"
        ).fetchone()[0]
        completed_month = conn.execute(
            "SELECT COUNT(*) FROM certificates WHERE status = 'completed' AND completed_at >= ?",
            (month_start,),
        ).fetchone()[0]
        cancelled = conn.execute(
            "SELECT COUNT(*) FROM certificates WHERE status IN ('cancelled', 'cancelled_no_payment')"
        ).fetchone()[0]
        total_all = conn.execute(
            "SELECT COUNT(*) FROM certificates"
        ).fetchone()[0]

    # Contar vencidos (requiere lógica de negocio)
    with get_conn() as conn2:
        active_rows = conn2.execute(
            "SELECT * FROM certificates WHERE status = 'active'"
        ).fetchall()

    overdue_count = 0
    for row in active_rows:
        cert = _cert_to_dict(row)
        alert = _compute_alert(cert, [])
        if alert["level"] in ("overdue", "critical"):
            overdue_count += 1

    return {
        "total_active":     total_active,
        "overdue":          overdue_count,
        "completed_month":  completed_month,
        "cancelled":        cancelled,
        "total_all":        total_all,
    }
