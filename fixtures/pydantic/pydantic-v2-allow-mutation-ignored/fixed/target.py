from pydantic import BaseModel, ConfigDict


class ApiCredentials(BaseModel):
    """Loaded once at startup; must not be changed afterwards."""

    model_config = ConfigDict(frozen=True)

    client_id: str
    region: str


def load_credentials() -> ApiCredentials:
    return ApiCredentials(client_id="svc-123", region="us-east-1")
