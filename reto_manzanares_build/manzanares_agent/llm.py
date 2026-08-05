from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class SynthesisResult:
    text: str | None
    used: bool
    warning: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None
    total_duration_seconds: float | None = None


def synthesize_with_ollama(prompt: str, settings: Settings) -> SynthesisResult:
    if settings.llm_provider != "ollama":
        return SynthesisResult(text=None, used=False)

    payload = json.dumps(
        {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 900},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "manzanares-growth-agent/2.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.llm_timeout_seconds
        ) as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                return SynthesisResult(
                    text=None,
                    used=False,
                    warning="Ollama respondio con un tipo de contenido inesperado.",
                )
            raw = response.read(1_000_000)
        result = json.loads(raw.decode("utf-8"))
        text = result.get("response")
        if not isinstance(text, str) or not text.strip():
            return SynthesisResult(
                text=None,
                used=False,
                warning="Ollama no produjo una respuesta util.",
            )
        prompt_tokens = _optional_int(result.get("prompt_eval_count"))
        output_tokens = _optional_int(result.get("eval_count"))
        eval_duration = _optional_int(result.get("eval_duration"))
        total_duration = _optional_int(result.get("total_duration"))
        tokens_per_second = (
            output_tokens / (eval_duration / 1_000_000_000)
            if output_tokens is not None and eval_duration and eval_duration > 0
            else None
        )
        return SynthesisResult(
            text=text.strip()[: settings.llm_max_response_chars],
            used=True,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            tokens_per_second=(
                round(tokens_per_second, 2)
                if tokens_per_second is not None
                else None
            ),
            total_duration_seconds=(
                round(total_duration / 1_000_000_000, 2)
                if total_duration is not None
                else None
            ),
        )
    except urllib.error.HTTPError as exc:
        return SynthesisResult(
            text=None,
            used=False,
            warning=f"Ollama no disponible (HTTP {exc.code}); se uso el resumen auditable.",
        )
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return SynthesisResult(
            text=None,
            used=False,
            warning="Ollama no disponible; se uso el resumen auditable.",
        )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None
