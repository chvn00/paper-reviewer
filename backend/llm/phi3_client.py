"""
phi3_client.py — CHVN Paper Reviewer (Local Ollama mode)
----------------------------------------------------------
LLM backend: Ollama local API (http://localhost:11434)
Sin API key. Sin rate limits. Sin datos a la nube.

Modelos recomendados (configurable desde UI):
  32GB+ RAM  → qwen3:32b     (máxima calidad, 20-24GB VRAM)
  16-24GB RAM → qwen3:14b    (muy bueno, 8-10GB VRAM)
  8-16GB RAM → llama3.2      (rápido, 4-6GB VRAM)

El modelo actual se controla desde /config (UI) y se aplica a todos los modos.
Environment override: OLLAMA_MODEL (aplica a todos los modos)
"""

import os
import json
import re
import logging
import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

OLLAMA_MODELS = [
    "qwen3:32b",
    "qwen3:14b",
    "qwen3:8b",
    "gemma3:12b",
    "llama3.2:latest",
]

MODE_MODELS: dict = {
    # Nota: todos los modos usan el mismo modelo configurado en runtime (DEFAULT_CONFIG["model"])
    # Las diferencias están en max_chars y max_tokens_override por modo, no en el modelo LLM
}

DEFAULT_CONFIG = {
    "model":       os.environ.get("OLLAMA_MODEL", "llama3.2"),
    "temperature": 0.2,
    "top_p":       0.9,
    "max_tokens":  4096,
}

_runtime_config = DEFAULT_CONFIG.copy()


def update_config(new_config: dict):
    global _runtime_config
    _runtime_config.update(new_config)
    logger.info(f"[LLM] Config updated: {_runtime_config}")


def get_config() -> dict:
    return _runtime_config.copy()


async def call_llm(prompt: str, system_prompt: str = "", config_override: dict = None) -> str:
    """Envía prompt a Ollama y retorna el texto de respuesta."""
    cfg = _runtime_config.copy()
    if config_override:
        cfg.update(config_override)

    model = cfg.get("model", DEFAULT_CONFIG["model"])

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": cfg.get("temperature", 0.2),
            "top_p":       cfg.get("top_p", 0.9),
            "num_predict": cfg.get("max_tokens", 4096),
        },
    }
    # Todos los agentes esperan JSON: format=json fuerza salida válida en Ollama
    # (desactivable con config_override={"json_mode": False})
    if cfg.get("json_mode", True):
        payload["format"] = "json"

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"].strip()

    except httpx.ConnectError:
        raise RuntimeError(
            "No se puede conectar a Ollama en localhost:11434. "
            "Ejecuta: ollama serve"
        )
    except Exception as e:
        logger.error(f"[Ollama] API call failed: {e}")
        raise


def _extract_json_object(text: str):
    """
    Extrae el primer objeto JSON completo del texto rastreando profundidad de llaves.
    Maneja correctamente texto antes y después del JSON (ej: 'Here is the JSON: {...} Hope this helps!').
    """
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_json_response(text: str, agent_name: str) -> dict:
    """
    Parser JSON robusto. Maneja markdown, texto extra antes/después del JSON,
    y bloques <think> de modelos con razonamiento interno (qwen3, deepseek).
    """
    # Elimina bloques <think> (qwen3, deepseek-r1, etc.)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Estrategia 1: parse directo
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Estrategia 2: extraer de ```json ... ``` o ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Estrategia 3: extracción por balanceo de llaves (maneja texto antes/después)
    candidate = _extract_json_object(text)
    if candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    logger.warning(f"[{agent_name}] JSON parse failed. Raw output: {text[:300]!r}")
    return {
        "agent_name": agent_name,
        "scope": "Parse error",
        "strengths": [],
        "weaknesses": ["Could not parse model response — raw output stored"],
        "major_comments": [],
        "minor_comments": [],
        "specific_recommendations": ["Re-run this agent or check model output"],
        "raw_output": text[:500],
        "score": 0,
        "confidence": 0,
        "parse_error": True,
    }


async def check_ollama_health() -> dict:
    """Verifica que Ollama esté corriendo y lista los modelos disponibles."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            available = [m["name"] for m in data.get("models", [])]
            return {
                "ollama_running": True,
                "available_models": available,
                "mode_models": MODE_MODELS,
                "configured_model": _runtime_config.get("model", "qwen3:32b"),
            }
    except Exception as e:
        return {
            "ollama_running": False,
            "error": str(e),
            "mode_models": MODE_MODELS,
            "configured_model": _runtime_config.get("model", "qwen3:32b"),
        }
