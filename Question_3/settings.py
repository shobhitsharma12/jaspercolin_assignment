from pydantic import BaseSettings, AnyUrl

class Settings(BaseSettings):
    DATABASE_URL: AnyUrl = "postgresql+asyncpg://user:pass@localhost:5432/analytics"
    APP_NAME: str = "Sales Analytics API"
    TOP_N: int = 5

    class Config:
        env_file = ".env"

settings = Settings()
