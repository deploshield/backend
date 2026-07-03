from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/deployshield"
    TEMP_DIR: str = "./temp/repositories"

    class Config:
        env_file = ".env"


settings = Settings()

TEMP_PATH = Path(settings.TEMP_DIR)
TEMP_PATH.mkdir(parents=True, exist_ok=True)
