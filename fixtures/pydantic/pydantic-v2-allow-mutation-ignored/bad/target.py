from pydantic import BaseModel


class ApiCredentials(BaseModel):
    """Loaded once at startup; must not be changed afterwards."""

    client_id: str
    region: str

    class Config:
        allow_mutation = False


def load_credentials() -> ApiCredentials:
    return ApiCredentials(client_id="svc-123", region="us-east-1")
