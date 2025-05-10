from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # variabel environment
    MONGODB_URI: str
    DATABASE_NAME: str = "app_db"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"


settings = Settings()
