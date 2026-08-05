from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from .models import ScoreBreakdown


def _number(row: Mapping[str, Any], key: str, default: float = 0) -> float:
    value = row[key] if key in row.keys() else default
    return float(value or default)


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row[key] if key in row.keys() else ""
    return str(value or "").strip()


def commercial_score(
    row: Mapping[str, Any], *, today: date | None = None
) -> ScoreBreakdown:
    """Return a transparent 0-100 commercial priority score.

    Prospect records no longer receive an artificial urgency benefit from the
    conventional ``days_since_purchase=999`` placeholder.
    """

    today = today or date.today()
    status = _text(row, "status").lower()
    monthly_value = max(_number(row, "monthly_value"), 0)
    interest_score = min(max(_number(row, "interest_score"), 0), 100)
    purchase_frequency = max(_number(row, "purchase_frequency"), 0)
    days_since_purchase = max(_number(row, "days_since_purchase"), 0)
    weighted_pipeline = max(_number(row, "weighted_pipeline"), 0)

    value_reference = max(monthly_value, weighted_pipeline)
    value = min(value_reference / 8_000_000, 1.0) * 30
    interest = interest_score / 100 * 25
    relationship = {"prospect": 15, "inactive": 13, "active": 8}.get(status, 4)
    frequency = min(purchase_frequency / 5, 1.0) * 10

    due_date_raw = _text(row, "next_action_date")
    urgency = 0.0
    reasons: list[str] = []
    if due_date_raw:
        try:
            days_until_due = (date.fromisoformat(due_date_raw) - today).days
            if days_until_due <= 0:
                urgency = 15
                reasons.append("siguiente accion vencida o para hoy")
            elif days_until_due <= 2:
                urgency = 12
                reasons.append("siguiente accion en menos de 48 horas")
            else:
                urgency = 6
        except ValueError:
            urgency = 3
            reasons.append("fecha de siguiente accion invalida")
    elif status == "inactive":
        urgency = min(days_since_purchase / 120, 1.0) * 15
        if days_since_purchase >= 60:
            reasons.append("cliente inactivo recuperable")
    elif status == "prospect":
        urgency = 8
        reasons.append("prospecto sin siguiente accion registrada")
    else:
        urgency = min(days_since_purchase / 45, 1.0) * 8

    quality_fields = ("phone", "segment", "assigned_advisor")
    quality_count = sum(bool(_text(row, field)) for field in quality_fields)
    data_quality = quality_count / len(quality_fields) * 5
    if quality_count < len(quality_fields):
        reasons.append("registro comercial incompleto")

    if value_reference >= 4_000_000:
        reasons.append("alto potencial economico")
    if interest_score >= 80:
        reasons.append("alto interes observado")

    total = round(
        min(
            value
            + interest
            + relationship
            + urgency
            + frequency
            + data_quality,
            100,
        ),
        1,
    )
    return ScoreBreakdown(
        total=total,
        value=round(value, 1),
        interest=round(interest, 1),
        relationship=round(relationship, 1),
        urgency=round(urgency, 1),
        frequency=round(frequency, 1),
        data_quality=round(data_quality, 1),
        reasons=tuple(dict.fromkeys(reasons)),
    )
