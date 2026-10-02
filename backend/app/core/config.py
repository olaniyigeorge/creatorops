from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "development"
    PROJECT_NAME: str = "CreatorOps"
    PORT: int = 8000
    CLIENT_DOMAIN: str = "http://localhost:3000"

    # Local dev: your own Postgres (backend/scripts/setup_local_db.sh), role bellz.
    # Production: Supabase session-mode pooler or direct connection, with sslmode=require.
    DATABASE_URL: str = "postgresql+psycopg://bellz@localhost:5432/creatorops"
    DB_POOL_SIZE: int = 3
    DB_MAX_OVERFLOW: int = 2
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Auth ---
    SECRET_KEY: str = "dev-insecure-change-me-dev-insecure-key"
    # Local testing without Google: POST /auth/dev-login. Refused outright in production.
    DEV_LOGIN_ENABLED: bool = False
    SESSION_COOKIE_NAME: str = "creatorops_session"
    SESSION_TTL_HOURS: int = 24 * 7
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/api/auth/google/callback"
    INVITATION_TTL_DAYS: int = 7

    # --- LLM (model agnostic: any provider supported by langchain init_chat_model) ---
    LLM_PROVIDER: str = "google_genai"
    LLM_MODEL: str = "gemini-2.5-flash-lite"
    LLM_TEMPERATURE: float = 0.7

    # --- Video generation (optional feature, pluggable provider) ---
    VIDEO_GEN_ENABLED: bool = False
    VIDEO_PROVIDER: str = "gemini_veo"
    VIDEO_MODEL: str = "veo-3.1-generate-preview"

    # Estimated price per generated second; budget enforcement uses it. Set it to your
    # provider's current price: while 0/unset, video generation is blocked (cost unknown).
    VIDEO_COST_PER_SECOND_USD: float = 0.0
    VIDEO_DEFAULT_SECONDS: int = 8

    # --- Image generation (thumbnails; optional, pluggable like video) ---
    IMAGE_GEN_ENABLED: bool = False
    IMAGE_PROVIDER: str = "gemini_imagen"
    IMAGE_MODEL: str = "imagen-4.0-generate-001"

    # --- Content calendar ---
    DEFAULT_PUBLISH_HOUR_UTC: int = 15

    # --- Editor workflow ---
    BRIEF_LEAD_DAYS: int = 3  # default deadline: this many days before the scheduled publish
    BRIEF_FOLLOWUP_INTERVAL_HOURS: int = 24  # minimum gap between follow-ups on one brief
    BRIEF_MAX_FOLLOWUPS: int = 3  # editor follow-ups before the owner is told instead

    # --- Provider credentials ---
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # --- Integrations ---
    YOUTUBE_API_KEY: str = ""
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "CreatorOps <noreply@example.com>"
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""

    # --- Asset storage (Cloudinary) ---
    CLOUDINARY_URL: str = ""  # cloudinary://<key>:<secret>@<cloud_name>

    # --- Task execution ---
    TASKS_EAGER: bool = False  # run tasks inline (local dev without Redis)
    RUN_STALE_MINUTES: int = 15  # a 'running' run older than this is reclaimable

    LANGSMITH_TRACING: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _require_real_secret_in_production(self):
        if self.ENV.lower() == "production" and self.SECRET_KEY == "dev-insecure-change-me-dev-insecure-key":
            raise ValueError("SECRET_KEY must be set in production")
        if self.ENV.lower() == "production" and self.DEV_LOGIN_ENABLED:
            raise ValueError("DEV_LOGIN_ENABLED must be false in production")
        return self


settings = Settings()
