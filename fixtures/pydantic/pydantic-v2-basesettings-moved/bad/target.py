from pydantic import BaseSettings


class AppSettings(BaseSettings):
    database_url: str = "sqlite:///local.db"
    debug: bool = False


def load_settings() -> AppSettings:
    return AppSettings()
