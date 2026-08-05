from __future__ import annotations

import hashlib
import time
import uuid

from .agents import AGENTS
from .config import Settings
from .database import CRMDatabase
from .llm import synthesize_with_ollama
from .models import AgentContribution, GenerationMetrics, OrchestrationResult


class OrchestrationError(RuntimeError):
    """Raised when no reliable orchestration result can be produced."""


class ManzanaresOrchestrator:
    def __init__(self, database: CRMDatabase, settings: Settings):
        self.database = database
        self.settings = settings

    def classify(self, question: str) -> tuple[str, list[str]]:
        text = question.casefold()
        routes = [
            (
                "diagnostico",
                ("diagnost", "indicador", "tablero", "kpi", "brecha"),
                ["diagnostico", "segmentador"],
            ),
            (
                "priorizacion",
                ("prospect", "prior", "quien llamar", "quién llamar"),
                ["segmentador", "priorizador", "seguimiento"],
            ),
            (
                "reactivacion",
                ("reactiv", "inactivo", "recompra"),
                [
                    "segmentador",
                    "priorizador",
                    "reactivacion",
                    "seguimiento",
                    "growth",
                ],
            ),
            (
                "growth",
                ("campaña", "growth", "crecimiento", "duplicar", "experimento"),
                [
                    "diagnostico",
                    "segmentador",
                    "priorizador",
                    "reactivacion",
                    "growth",
                ],
            ),
        ]
        matched = [
            (intent, agents)
            for intent, terms, agents in routes
            if any(term in text for term in terms)
        ]
        if matched:
            requested = {agent for _, agents in matched for agent in agents}
            selected = [key for key in AGENTS if key in requested]
            return "+".join(intent for intent, _ in matched), selected
        return "briefing", list(AGENTS)

    def run(self, question: str) -> OrchestrationResult:
        clean_question = " ".join(question.split())
        if not clean_question:
            raise OrchestrationError("La solicitud no puede estar vacia.")
        if len(clean_question) > 1_000:
            raise OrchestrationError("La solicitud no puede superar 1000 caracteres.")

        started = time.monotonic()
        run_id = str(uuid.uuid4())
        intent, selected = self.classify(clean_question)
        question_hash = hashlib.sha256(clean_question.encode("utf-8")).hexdigest()
        self.database.start_run(run_id, question_hash, intent, len(selected))
        self.database.log(
            run_id,
            "Coordinador",
            "clasificacion",
            f"Flujo seleccionado: {intent}",
            metadata={"agents": selected},
        )

        contributions: list[AgentContribution] = []
        warnings: list[str] = []
        try:
            for key in selected:
                agent = AGENTS[key]
                agent_started = time.monotonic()
                try:
                    contribution = agent.run(
                        self.database,
                        question=clean_question,
                        settings=self.settings,
                        run_id=run_id,
                    )
                    contributions.append(contribution)
                    self.database.log(
                        run_id,
                        contribution.agent,
                        "aporte",
                        "Agente completado.",
                        metadata={
                            "findings": len(contribution.findings),
                            "actions": len(contribution.actions),
                            "metrics": contribution.metrics,
                            "duration_ms": int(
                                (time.monotonic() - agent_started) * 1000
                            ),
                        },
                    )
                except Exception as exc:
                    warning = f"El agente {agent.name} no pudo completar su analisis."
                    warnings.append(warning)
                    self.database.log(
                        run_id,
                        agent.name,
                        "error",
                        str(exc),
                        level="ERROR",
                    )

            if not contributions:
                raise OrchestrationError(
                    "Ningun agente pudo producir evidencia confiable."
                )

            deterministic = self._deterministic_summary(intent)
            llm_prompt = self._build_prompt(
                clean_question, intent, contributions
            )
            synthesis = synthesize_with_ollama(llm_prompt, self.settings)
            if synthesis.warning:
                warnings.append(synthesis.warning)
            summary = synthesis.text or deterministic
            self.database.log(
                run_id,
                "Redactor",
                "respuesta_final",
                "Briefing consolidado.",
                metadata={
                    "llm_used": synthesis.used,
                    "summary_chars": len(summary),
                    "prompt_tokens": synthesis.prompt_tokens,
                    "output_tokens": synthesis.output_tokens,
                    "tokens_per_second": synthesis.tokens_per_second,
                },
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            status = "completed_with_warnings" if warnings else "completed"
            self.database.finish_run(
                run_id,
                status=status,
                agents_completed=len(contributions),
                llm_used=synthesis.used,
                duration_ms=duration_ms,
            )
            return OrchestrationResult(
                question=clean_question,
                intent=intent,
                agents=[item.agent for item in contributions],
                contributions=contributions,
                executive_summary=summary,
                run_id=run_id,
                llm_used=synthesis.used,
                generation_metrics=(
                    GenerationMetrics(
                        model=self.settings.ollama_model,
                        prompt_tokens=synthesis.prompt_tokens,
                        output_tokens=synthesis.output_tokens,
                        tokens_per_second=synthesis.tokens_per_second,
                        total_duration_seconds=synthesis.total_duration_seconds,
                    )
                    if synthesis.used
                    else None
                ),
                warnings=warnings,
            )
        except Exception as exc:
            self.database.finish_run(
                run_id,
                status="failed",
                agents_completed=len(contributions),
                llm_used=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                error_message=str(exc)[:1_000],
            )
            raise

    def _deterministic_summary(self, intent: str) -> str:
        dashboard = self.database.dashboard()
        covered_value = float(dashboard["active_monthly_value"]) + float(
            dashboard["weighted_pipeline"]
        )
        gap = max(self.settings.monthly_sales_target - covered_value, 0)
        return (
            f"El flujo {intent} recomienda operar una cola diaria priorizada, "
            "cerrar la trazabilidad de cada contacto y validar los resultados con "
            "experimentos controlados. Las ventas activas identificadas mas el "
            f"pipeline ponderado suman ${covered_value:,.0f} COP; la brecha "
            f"indicativa frente a la meta es ${gap:,.0f} COP. Hay "
            f"{dashboard['overdue_tasks']} tareas vencidas y la completitud de datos "
            f"es {float(dashboard['data_completeness']):.1f}%. La prioridad operativa "
            "es ejecutar las tareas de mayor score, registrar resultados y revisar "
            "semanalmente conversion e ingreso incremental."
        )

    def _build_prompt(
        self,
        question: str,
        intent: str,
        contributions: list[AgentContribution],
    ) -> str:
        evidence = "\n".join(
            f"{item.agent}: {'; '.join(item.findings)} "
            f"Acciones: {'; '.join(item.actions)}"
            for item in contributions
        )
        return f"""Eres el redactor ejecutivo de un sistema comercial auditable.
Empresa: {self.settings.company_name}
Solicitud: {question}
Tipo de flujo: {intent}
Meta mensual: {self.settings.monthly_sales_target:,.0f} COP

Evidencia autorizada:
{evidence}

Genera un briefing breve, sobrio y accionable. Usa exclusivamente la evidencia
anterior. Diferencia hechos, estimaciones y recomendaciones. Incluye prioridades
para hoy, indicador de exito y siguiente experimento. No inventes cifras, clientes,
integraciones, capacidades ni resultados."""
