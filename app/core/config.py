from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import (
    Field,
    PostgresDsn,
    SecretStr
)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int


    # JWT
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str = Field("HS256", validation_alias='jwt_algo')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 90


    ENVIRONMENT: str = "DEV" # OR PROD

    # LOGGING
    LOG_LEVEL: str = "INFO"
    
    @property
    def database_url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

settings = Settings()