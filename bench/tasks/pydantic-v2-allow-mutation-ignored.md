<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our service loads API credentials once at startup and nothing should be able to change them
afterwards. Please write `target.py` with a pydantic model `ApiCredentials` (`client_id:
str`, `region: str`) whose instances are immutable, so attempting to assign to a field
raises a validation error. Add `load_credentials()` that returns
`ApiCredentials(client_id="svc-123", region="us-east-1")`.
