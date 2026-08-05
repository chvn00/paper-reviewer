from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .config import Settings
from .database import CRMDatabase
from .models import AgentContribution
from .scoring import commercial_score


def money(value: float) -> str:
    return f"${value:,.0f} COP"


class DiagnosticAgent:
    name = "Diagnostico"

    def run(
        self,
        db: CRMDatabase,
        *,
        settings: Settings,
        **_: object,
    ) -> AgentContribution:
        data = db.dashboard()
        coverage = (
            float(data["interactions_last_30_days"]) / max(int(data["contacts"]), 1)
        )
        base_plus_pipeline = float(data["active_monthly_value"]) + float(
            data["weighted_pipeline"]
        )
        gap = max(settings.monthly_sales_target - base_plus_pipeline, 0)
        return AgentContribution(
            agent=self.name,
            objective="Cuantificar la linea base, la capacidad operativa y la brecha.",
            findings=[
                f"La base contiene {data['contacts']} contactos y {data['open_opportunities']} oportunidades abiertas.",
                f"Ventas activas identificadas mas pipeline ponderado: {money(base_plus_pipeline)}.",
                f"Brecha indicativa frente a la meta: {money(gap)}.",
                f"Completitud de campos operativos: {float(data['data_completeness']):.1f}%.",
            ],
            actions=[
                "Validar la linea base con ventas facturadas y estacionalidad antes de contractualizar la meta.",
                "Medir semanalmente cobertura, contacto efectivo, conversion, recompra e ingreso atribuible.",
            ],
            metrics={
                "commercial_gap_cop": round(gap, 2),
                "contact_coverage_30d": round(coverage, 2),
                "data_completeness_pct": float(data["data_completeness"]),
            },
        )


class SegmentationAgent:
    name = "Segmentador"

    def run(self, db: CRMDatabase, **_: object) -> AgentContribution:
        contacts = db.contacts()
        high_value = [
            row for row in contacts if float(row["monthly_value"]) >= 4_000_000
        ]
        dormant = [
            row
            for row in contacts
            if row["status"] == "inactive"
            and int(row["days_since_purchase"]) >= 60
        ]
        missing_owner = [
            row for row in contacts if not str(row["assigned_advisor"] or "").strip()
        ]
        return AgentContribution(
            agent=self.name,
            objective="Organizar la base por valor, recurrencia, estado y accionabilidad.",
            findings=[
                f"{len(high_value)} contactos superan 4 millones COP de potencial mensual.",
                f"{len(dormant)} clientes cumplen el criterio inicial de reactivacion.",
                f"{len(missing_owner)} contactos no tienen asesor asignado.",
            ],
            actions=[
                "Separar tratamiento para prospectos, activos, inactivos y recompra.",
                "No activar campañas sobre registros sin responsable y datos de contacto suficientes.",
            ],
            metrics={
                "high_value_contacts": len(high_value),
                "reactivation_candidates": len(dormant),
                "contacts_without_owner": len(missing_owner),
            },
        )


class PrioritizationAgent:
    name = "Priorizador"

    def ranked(self, db: CRMDatabase) -> list[tuple[Any, Any]]:
        ranked = [
            (commercial_score(row), row) for row in db.priority_candidates()
        ]
        return sorted(ranked, key=lambda item: item[0].total, reverse=True)

    def run(self, db: CRMDatabase, **_: object) -> AgentContribution:
        top = self.ranked(db)[:5]
        findings = []
        for score, row in top:
            reasons = ", ".join(score.reasons[:3]) or "prioridad por score compuesto"
            findings.append(
                f"{row['name']}: {score.total}/100; potencial "
                f"{money(float(row['monthly_value']))}; razones: {reasons}."
            )
        return AgentContribution(
            agent=self.name,
            objective="Ordenar la gestion diaria con un score explicable y reproducible.",
            findings=findings or ["No hay contactos disponibles para priorizar."],
            actions=[
                "Atender primero los contactos con score alto y siguiente accion vencida.",
                "Recalibrar pesos con conversion observada; no usar el score como decision automatica de exclusion.",
            ],
            metrics={
                "ranked_contacts": len(self.ranked(db)),
                "top_score": top[0][0].total if top else 0,
            },
        )


class FollowUpAgent:
    name = "Seguimiento"

    def run(
        self,
        db: CRMDatabase,
        *,
        run_id: str,
        **_: object,
    ) -> AgentContribution:
        ranked = PrioritizationAgent().ranked(db)[:8]
        tasks: list[tuple[int, str, str, str, str]] = []
        for score, row in ranked:
            if row["next_action"]:
                action = str(row["next_action"])
            elif row["status"] == "prospect":
                action = "Contacto consultivo y validacion de necesidad"
            elif row["status"] == "inactive":
                action = "Oferta de reactivacion y recuperacion de recompra"
            else:
                action = "Seguimiento de recompra y venta cruzada"
            priority = (
                "alta" if score.total >= 75 else "media" if score.total >= 55 else "baja"
            )
            due_offset = 0 if priority == "alta" else 1 if priority == "media" else 2
            due_date = str(date.today() + timedelta(days=due_offset))
            reason = (
                f"Score {score.total}/100. "
                + (", ".join(score.reasons[:3]) or "prioridad comercial compuesta")
            )
            tasks.append((int(row["id"]), priority, action, due_date, reason))
        sync = db.sync_tasks(tasks, run_id=run_id)
        return AgentContribution(
            agent=self.name,
            objective="Convertir el analisis en una cola diaria persistente y trazable.",
            findings=[
                f"Cola sincronizada: {sync['created']} tareas nuevas, "
                f"{sync['updated']} actualizadas, {sync['unchanged']} sin cambios "
                f"y {sync['superseded']} reemplazadas conservando historial."
            ],
            actions=[
                "Registrar resultado y siguiente accion al terminar cada contacto.",
                "Revisar tareas vencidas al inicio y al cierre de cada jornada.",
            ],
            metrics=sync,
        )


class ReactivationAgent:
    name = "Reactivacion"

    def run(self, db: CRMDatabase, **_: object) -> AgentContribution:
        candidates = [
            row
            for row in db.contacts()
            if row["status"] == "inactive"
            and int(row["days_since_purchase"]) >= 60
        ]
        value = sum(float(row["monthly_value"]) for row in candidates)
        return AgentContribution(
            agent=self.name,
            objective="Recuperar clientes inactivos mediante experimentos controlados.",
            findings=[
                f"{len(candidates)} clientes cumplen el criterio inicial de reactivacion.",
                f"Potencial mensual historico asociado: {money(value)}.",
            ],
            actions=[
                "Asignar aleatoriamente tratamiento y control antes de iniciar la campaña.",
                "Medir ingreso incremental, no solo respuestas o pedidos brutos.",
            ],
            metrics={
                "reactivation_candidates": len(candidates),
                "historical_value_cop": round(value, 2),
            },
        )


class GrowthAgent:
    name = "Growth"

    def run(self, db: CRMDatabase, **_: object) -> AgentContribution:
        data = db.dashboard()
        experiment = (
            "reactivacion de inactivos"
            if int(data["inactive_contacts"]) > 0
            else "recompra programada"
        )
        return AgentContribution(
            agent=self.name,
            objective="Diseñar experimentos comerciales medibles y repetibles.",
            findings=[
                f"El siguiente experimento recomendado es {experiment}.",
                f"Hay {data['overdue_tasks']} tareas vencidas y "
                f"{data['interactions_last_30_days']} interacciones registradas en 30 dias.",
            ],
            actions=[
                "Definir hipotesis, grupo de control, metrica primaria y regla de parada antes de ejecutar.",
                "Mantener un tablero semanal con embudo, costo de gestion e ingreso incremental.",
            ],
            metrics={
                "overdue_tasks": int(data["overdue_tasks"]),
                "interactions_last_30_days": int(
                    data["interactions_last_30_days"]
                ),
            },
        )


AGENTS = {
    "diagnostico": DiagnosticAgent(),
    "segmentador": SegmentationAgent(),
    "priorizador": PrioritizationAgent(),
    "seguimiento": FollowUpAgent(),
    "reactivacion": ReactivationAgent(),
    "growth": GrowthAgent(),
}
