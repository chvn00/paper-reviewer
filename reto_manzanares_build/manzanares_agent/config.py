from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigurationError(ValueError):
    """Raised when runtime configuration is unsafe or invalid."""


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(
                f"Linea {line_number} invalida en {path.name}: falta '='."
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigurationError(
                f"Linea {line_number} invalida en {path.name}: clave vacia."
            )
        values[key] = value.strip().strip("\"'")
    return values


def _as_float(values: dict[str, str], key: str, default: float) -> float:
    try:
        return float(values.get(key, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{key} debe ser numerico.") from exc


def _as_int(values: dict[str, str], key: str, default: int) -> int:
    try:
        return int(values.get(key, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{key} debe ser entero.") from exc


def _as_bool(values: dict[str, str], key: str, default: bool) -> bool:
    raw = values.get(key, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "si", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{key} debe ser true/false.")


@dataclass(frozen=True)
class Settings:
    database_path: Path
    company_name: str
    llm_provider: str
    ollama_base_url: str
    ollama_model: str
    monthly_sales_baseline: float
    monthly_sales_target: float
    environment: str = "development"
    log_level: str = "INFO"
    json_logs: bool = False
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    api_token: str | None = None
    request_max_bytes: int = 65_536
    llm_timeout_seconds: int = 60
    llm_max_response_chars: int = 6_000

    @classmethod
    def load(cls, env_path: Path | None = None) -> "Settings":
        env_file = env_path or PROJECT_ROOT / ".env"
        values = read_env(env_file)
        values.update(os.environ)

        database_path = Path(values.get("DATABASE_PATH", "data/manzanares.db"))
        if not database_path.is_absolute():
            database_path = PROJECT_ROOT / database_path

        settings = cls(
            database_path=database_path.resolve(),
            company_name=values.get("COMPANY_NAME", "Grupo Manzanares S.A.S.").strip(),
            llm_provider=values.get("LLM_PROVIDER", "disabled").strip().lower(),
            ollama_base_url=values.get(
                "OLLAMA_BASE_URL", "http://localhost:11434"
            ).strip(),
            ollama_model=values.get("OLLAMA_MODEL", "gemma3:12b").strip(),
            monthly_sales_baseline=_as_float(
                values, "MONTHLY_SALES_BASELINE_COP", 40_000_000
            ),
            monthly_sales_target=_as_float(
                values, "MONTHLY_SALES_TARGET_COP", 80_000_000
            ),
            environment=values.get("ENVIRONMENT", "development").strip().lower(),
            log_level=values.get("LOG_LEVEL", "INFO").strip().upper(),
            json_logs=_as_bool(values, "JSON_LOGS", False),
            api_host=values.get("API_HOST", "127.0.0.1").strip(),
            api_port=_as_int(values, "API_PORT", 8080),
            api_token=values.get("API_TOKEN") or None,
            request_max_bytes=_as_int(values, "REQUEST_MAX_BYTES", 65_536),
            llm_timeout_seconds=_as_int(values, "LLM_TIMEOUT_SECONDS", 60),
            llm_max_response_chars=_as_int(
                values, "LLM_MAX_RESPONSE_CHARS", 6_000
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.company_name:
            raise ConfigurationError("COMPANY_NAME no puede estar vacio.")
        if self.llm_provider not in {"disabled", "ollama"}:
            raise ConfigurationError("LLM_PROVIDER debe ser 'disabled' u 'ollama'.")
        parsed = urlparse(self.ollama_base_url)
        if self.llm_provider == "ollama" and (
            parsed.scheme not in {"http", "https"} or not parsed.netloc
        ):
            raise ConfigurationError("OLLAMA_BASE_URL debe ser una URL HTTP valida.")
        if self.monthly_sales_baseline < 0 or self.monthly_sales_target <= 0:
            raise ConfigurationError("Las metas comerciales deben ser positivas.")
        if self.monthly_sales_target <= self.monthly_sales_baseline:
            raise ConfigurationError(
                "MONTHLY_SALES_TARGET_COP debe superar la linea base."
            )
        if not 1 <= self.api_port <= 65_535:
            raise ConfigurationError("API_PORT debe estar entre 1 y 65535.")
        if self.request_max_bytes < 1_024:
            raise ConfigurationError("REQUEST_MAX_BYTES es demasiado pequeno.")
        if not 1 <= self.llm_timeout_seconds <= 120:
            raise ConfigurationError("LLM_TIMEOUT_SECONDS debe estar entre 1 y 120.")
        if self.llm_max_response_chars < 500:
            raise ConfigurationError("LLM_MAX_RESPONSE_CHARS es demasiado pequeno.")
        if self.api_host not in {"127.0.0.1", "localhost", "::1"} and not self.api_token:
            raise ConfigurationError(
                "API_TOKEN es obligatorio cuando la API se expone fuera de localhost."
            )
