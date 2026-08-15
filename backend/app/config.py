from pydantic_settings import BaseSettings
from typing import List, Tuple


class Settings(BaseSettings):
    # System DB
    database_url: str

    # Security
    fernet_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # LLM (free-only — no paid models; availability changes, test scripts/test_models.py)
    # Primary: gpt-oss-120b via Groq's OpenAI-compatible endpoint
    #   (free tier: 30 RPM / 1000 RPD / 8K TPM, ~500 tok/s) — high daily quota.
    # Fallback: gemini-3.6-flash via the official google.genai SDK (Interactions API)
    #   (free tier caps at ~20 requests/day per project+model — too low for primary use;
    #   see actions.md note). Model names are generation-specific:
    #   gemini-2.5-flash is retired for new keys — use the current generation.
    # Model slugs drive provider routing automatically (see endpoint_for).
    gemini_api_key: str
    groq_api_key: str
    primary_llm_model: str = "openai/gpt-oss-120b"
    fallback_llm_models: str = "gemini-3.6-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Query router (pre-pipeline intent classifier, project.md 4.0): when the
    # heuristic is ambiguous, spend one small LLM call to classify the turn
    # rather than running the full SQL pipeline on chit-chat. Disable to stay
    # strictly heuristic (ambiguous input then defaults to the full pipeline).
    query_router_escalation: bool = True

    # E2B
    e2b_api_key: str

    # CORS
    allowed_origins: str = "http://localhost:5173"

    @property
    def fallback_models_list(self) -> List[str]:
        return [m.strip() for m in self.fallback_llm_models.split(",") if m.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def endpoint_for(self, model_slug: str) -> Tuple[str, str]:
        """Resolve (base_url, api_key) for a model slug across supported providers.

        `gemini-*` slugs route to Google's OpenAI-compatible endpoint; everything
        else (e.g. `openai/*` on Groq) routes to Groq.
        """
        if model_slug.startswith("gemini-"):
            return self.gemini_base_url, self.gemini_api_key
        return self.groq_base_url, self.groq_api_key

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()


def _mask_key(key: str) -> str:
    if not key:
        return "<empty>"
    if len(key) <= 8:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


# Startup visibility into the loaded LLM config (URLs in full, keys masked).
print(
    "[config] GEMINI_BASE_URL="
    f"{settings.gemini_base_url!r} GEMINI_API_KEY={_mask_key(settings.gemini_api_key)} "
    f"GROQ_BASE_URL={settings.groq_base_url!r} GROQ_API_KEY={_mask_key(settings.groq_api_key)} "
    f"PRIMARY={settings.primary_llm_model} FALLBACK={settings.fallback_llm_models}",
    flush=True,
)
