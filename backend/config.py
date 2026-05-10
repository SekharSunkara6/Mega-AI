from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str = ""
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    secret_key: str = "dev-secret"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()