from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # VK (опциональные)
    VK_SERVICE_TOKEN: str | None = None
    VK_GROUP_ID: int | None = None

    # Database
    DATABASE_URL: str = "sqlite:///./notifications.db"

    # Security
    ENCRYPTION_KEY: str = "change-me-to-random-32-chars!!"

    # App
    DEBUG: bool = True


settings = Settings()