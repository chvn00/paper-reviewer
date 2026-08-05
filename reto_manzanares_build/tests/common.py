from __future__ import annotations

from pathlib import Path

from manzanares_agent.config import Settings


def test_settings(database_path: Path, *, api_token: str | None = None) -> Settings:
    return Settings(
        database_path=database_path,
        company_name="Grupo Manzanares S.A.S.",
        llm_provider="disabled",
        ollama_base_url="http://localhost:11434",
        ollama_model="gemma3:12b",
        monthly_sales_baseline=40_000_000,
        monthly_sales_target=80_000_000,
        api_token=api_token,
    )
