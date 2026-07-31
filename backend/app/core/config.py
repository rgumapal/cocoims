from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg2://cocoims:cocoims_dev_local_only@localhost:5433/cocoims"
    )


settings = Settings()
