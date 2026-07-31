from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    # Owning/superuser role. Used only by Alembic (DDL rights) and admin
    # scripts — never by the running API. See alembic/versions/0004 for why:
    # this role bypasses RLS unconditionally, so a request handler connecting
    # with it would silently see and write every branch's data regardless of
    # scope.
    database_url: str = (
        "postgresql+psycopg2://cocoims:cocoims_dev_local_only@localhost:5433/cocoims"
    )

    # Unprivileged role (NOSUPERUSER, NOBYPASSRLS) the API connects as for
    # every request. RLS policies only bind against this role — see
    # alembic/versions/0004_operational_rls_and_rpt.py.
    app_database_url: str = (
        "postgresql+psycopg2://cocoims_app:cocoims_app_dev_local_only@localhost:5433/cocoims"
    )

    jwt_secret_key: str = "dev-only-change-me"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 14


settings = Settings()
