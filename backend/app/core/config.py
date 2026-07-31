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

    # SPEC §7.4 separation of duties: a count variance beyond this magnitude
    # cannot be approved by the user who submitted it. A flat constant for
    # now — a real per-item/location threshold belongs in core.param_set,
    # which is forecast/ladder-phase work (deferred, see the approved plan);
    # nothing here invents that structure early.
    count_variance_approval_threshold: int = 20


settings = Settings()
