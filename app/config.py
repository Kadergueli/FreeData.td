from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime configuration loaded from the local .env file."""

    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    analysis_rate_limit_per_hour: int = 5
    # Ceiling for all visitors together: per-IP limits do not stop many IPs from running up the AI bill.
    analysis_global_limit_per_hour: int = 30
    collection_api_key: str | None = None
    collection_rate_limit_per_hour: int = 10
    # Reading the public API needs no key, but one client must not be able to drain the free-tier
    # bandwidth: a generous cap per IP and minute, and a stricter one for the heavy file exports.
    read_rate_limit_per_minute: int = 120
    export_rate_limit_per_minute: int = 10
    nasa_firms_key: str | None = None
    # Admin area. The publishable ("anon") key is public by design: the browser needs it to
    # sign in through Supabase Auth. ADMIN_EMAILS are permanent owners (cannot be locked out).
    supabase_anon_key: str | None = None
    admin_emails: str = ""
    # Extra origins (space separated) the browser may call, on top of SUPABASE_URL. Rarely needed.
    csp_connect_extra: str = ""
    database_path: str = "data/freedatatd.db"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    @property
    def database_file(self) -> Path:
        return PROJECT_ROOT / self.database_path

    @property
    def owner_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
