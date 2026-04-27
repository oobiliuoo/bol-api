import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123")
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bol_api.db")
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "default_encryption_key_32_bytes!")
    jwt_secret: str = os.getenv("JWT_SECRET", "default_jwt_secret_change_in_production!")
    jwt_expire_hours: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    class Config:
        env_file = ".env"


settings = Settings()