"""
models.py — Pydantic models para el módulo de certificados.
"""
from pydantic import BaseModel
from typing import Optional, List


class LoginRequest(BaseModel):
    username: str
    password: str


class CertificateCreate(BaseModel):
    student_name: str
    student_id: str           # Número de documento
    student_email: str
    student_phone: Optional[str] = ""
    certificate_types: List[str]  # Ej: ["certificado de notas", "certificado de matrícula"]
    notes: Optional[str] = ""


class CertificateUpdate(BaseModel):
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    student_phone: Optional[str] = None
    certificate_types: Optional[List[str]] = None
    notes: Optional[str] = None


class StageCompleteRequest(BaseModel):
    notes: Optional[str] = ""
    completed_at: Optional[str] = None  # ISO "YYYY-MM-DD" — por defecto hoy


class EmailLogCreate(BaseModel):
    stage_number: Optional[int] = None
    direction: str             # "inbound" | "outbound"
    subject: str
    body: str
    from_addr: str
    to_addr: str
    logged_at: Optional[str] = None  # ISO, por defecto ahora
