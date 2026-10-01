from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "development"
    PROJECT_NAME: str = "CreatorOps"
    PORT: int = 8000
    CLIENT_DOMAIN: str = "http://localhost:3000"

    # Supabase: use the session-mode pooler or direct connection, with sslmode=require.
    DATABASE_URL: str = "postgresql+psycopg://creatorops:creatorops@localhost:5432/creatorops"
    DB_POOL_SIZE: int = 3
    DB_MAX_OVERFLOW: int = 2
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Auth ---
    SECRET_KEY: str = "dev-insecure-change-me-dev-insecure-key"
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

    LANGSMITH_TRACING: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _require_real_secret_in_production(self):
        if self.ENV.lower() == "production" and self.SECRET_KEY == "dev-insecure-change-me-dev-insecure-key":
            raise ValueError("SECRET_KEY must be set in production")
        return self


settings = Settings()
