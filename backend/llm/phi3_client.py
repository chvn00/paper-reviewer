"""
phi3_client.py — CHVN Paper Reviewer v4
-----------------------------------------
LLM client: Groq API (llama-3.3-70b-versatile by default).
Falls back to env var GROQ_MODEL if set.
Papers are processed via API — Groq does NOT store or train on API data.
"""

import os
import json
import re
import logging

logger = logging.getLogger(__name__)

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
    "llama-3.1-8b-instant",
]

DEFAULT_CONFIG = {
    "model":       os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
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
    """Send prompt to Groq API and return response text."""
    from groq import AsyncGroq

    cfg = _runtime_config.copy()
    if config_override:
        cfg.update(config_override)

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    client = AsyncGroq(api_key=api_key)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            temperature=cfg["temperature"],
            top_p=cfg["top_p"],
            max_tokens=cfg["max_tokens"],
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"[Groq] API call failed: {e}")
        raise


def parse_json_response(text: str, agent_name: str) -> dict:
    """
    Robust JSON parser. Handles markdown code blocks and stray text.
    Groq models are generally clean — but we keep fallbacks for safety.
    """
    # Strip any <think> blocks just in case
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: First { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning(f"[{agent_name}] JSON parse failed. Using fallback.")
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
    """Health check — now reports Groq API status instead of Ollama."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    model   = _runtime_config.get("model", "llama-3.3-70b-versatile")
    if not api_key:
        return {
            "groq_api": False,
            "model_available": False,
            "configured_model": model,
            "error": "GROQ_API_KEY not set",
        }
    return {
        "groq_api": True,
        "model_available": True,
        "available_models": GROQ_MODELS,
        "configured_model": model,
    }
