"""Application settings, loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Models for which Groq documents strict `json_schema` structured outputs.
STRICT_SCHEMA_MODELS = frozenset({"openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"})
# Models for which Groq documents best-effort `json_schema` (strict=false).
BEST_EFFORT_SCHEMA_MODELS = frozenset({"openai/gpt-oss-safeguard-20b"})

StructuredMode = Literal["auto", "json_schema", "json_object"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Runtime ---------------------------------------------------------
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    # Local mongod, Docker, or an Atlas SRV string (mongodb+srv://user:pass@cluster/...).
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "etocelest"
    # Comma-separated list of allowed browser origins for CORS.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Groq ------------------------------------------------------------
    groq_api_key: SecretStr = Field(default=SecretStr(""))
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model_agent: str = "openai/gpt-oss-120b"
    groq_model_judge: str = "openai/gpt-oss-120b"
    # auto = pick json_schema for models Groq documents as supporting it, else json_object.
    groq_structured_mode: StructuredMode = "auto"
    # Optional. Only sent when set (Groq returns 400 for values a model does not support).
    groq_reasoning_effort: str | None = None
    llm_timeout_seconds: float = 90.0
    llm_max_retries: int = Field(default=5, ge=0, le=10)
    llm_max_backoff_seconds: float = Field(default=90.0, gt=0)
    llm_max_concurrency: int = Field(default=4, ge=1, le=32)
    llm_agent_max_tokens: int = Field(default=4096, ge=256)
    llm_judge_max_tokens: int = Field(default=4096, ge=256)
    # How many times a single call is re-asked when the model returns invalid output.
    llm_validation_attempts: int = Field(default=3, ge=1, le=6)

    # --- Debate ----------------------------------------------------------
    min_rounds: int = Field(default=2, ge=1, le=10)
    max_rounds: int = Field(default=4, ge=1, le=10)
    max_shift_days: int = Field(default=60, ge=1, le=365)
    max_concurrent_debates: int = Field(default=2, ge=1, le=32)
    mission_timeout_seconds: float = Field(default=1800.0, gt=0)
    # Extra LangGraph steps allowed beyond the worst-case path (2 per round + ground/fallback/finalize).
    # The step budget is derived from the mission's max_rounds, so this only needs raising if you add nodes.
    graph_step_headroom: int = Field(default=4, ge=0, le=100)

    # --- Abuse protection ------------------------------------------------
    rate_limit_missions_per_hour: int = Field(default=20, ge=1)
    max_active_missions_per_owner: int = Field(default=2, ge=1)

    # --- Grounding (NOAA SWPC solar-cycle forecast) ----------------------
    grounding_enabled: bool = True
    noaa_solar_cycle_url: str = "https://services.swpc.noaa.gov/json/solar-cycle/predicted-solar-cycle.json"
    grounding_timeout_seconds: float = 10.0
    grounding_cache_ttl_seconds: float = 6 * 3600

    @model_validator(mode="after")
    def _check_rounds(self) -> Settings:
        if self.min_rounds > self.max_rounds:
            raise ValueError("MIN_ROUNDS must be <= MAX_ROUNDS")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def require_llm_key(self) -> str:
        key = self.groq_api_key.get_secret_value().strip()
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Create a key at https://console.groq.com/keys and "
                "export it (or put it in .env) before starting the server."
            )
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
