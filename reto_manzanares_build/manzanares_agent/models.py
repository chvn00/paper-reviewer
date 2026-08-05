from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AgentContribution:
    agent: str
    objective: str
    findings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | str] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationMetrics:
    model: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None
    total_duration_seconds: float | None = None

    def display(self) -> str:
        prompt = (
            str(self.prompt_tokens) if self.prompt_tokens is not None else "n/d"
        )
        output = (
            str(self.output_tokens) if self.output_tokens is not None else "n/d"
        )
        speed = (
            f"{self.tokens_per_second:.2f}"
            if self.tokens_per_second is not None
            else "n/d"
        )
        duration = (
            f" | Tiempo: {self.total_duration_seconds:.2f} s"
            if self.total_duration_seconds is not None
            else ""
        )
        return (
            f"Modelo: {self.model} | Entrada: {prompt} tokens | "
            f"Salida: {output} tokens | Velocidad: {speed} tok/s{duration}"
        )


@dataclass
class OrchestrationResult:
    question: str
    intent: str
    agents: list[str]
    contributions: list[AgentContribution]
    executive_summary: str
    run_id: str = ""
    generated_at: str = field(default_factory=utc_now)
    llm_used: bool = False
    generation_metrics: GenerationMetrics | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            "MANZANARES GROWTH AGENT",
            "=" * 72,
            f"Ejecucion: {self.run_id or 'n/a'}",
            f"Solicitud: {self.question}",
            f"Tipo: {self.intent}",
            f"Agentes activos: {', '.join(self.agents)}",
            "",
            "FLUJO Y APORTES",
            "-" * 72,
        ]
        for item in self.contributions:
            lines.append(f"\n[{item.agent}] {item.objective}")
            lines.extend(f"  Hallazgo: {value}" for value in item.findings)
            lines.extend(f"  Accion: {value}" for value in item.actions)
        lines.extend(["", "LECTURA EJECUTIVA", "-" * 72, self.executive_summary])
        if self.generation_metrics:
            lines.extend(
                [
                    "",
                    "METRICAS DE GENERACION",
                    "-" * 72,
                    self.generation_metrics.display(),
                ]
            )
        if self.warnings:
            lines.extend(["", "ADVERTENCIAS", "-" * 72])
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines)


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    value: float
    interest: float
    relationship: float
    urgency: float
    frequency: float
    data_quality: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
