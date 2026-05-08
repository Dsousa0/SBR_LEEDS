from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    app_env: str = "development"
    secret_key: str = "dev-insecure-change-me-in-production"

    pedido_mobile_base_url: str = "https://pedidomobile.com/webservice/v3"
    pedido_mobile_user: str | None = None
    pedido_mobile_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
