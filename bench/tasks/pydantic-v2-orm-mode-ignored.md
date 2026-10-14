<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our API returns users loaded by the ORM. Please write `target.py` with a pydantic output
model `UserOut` (`id: int`, `email: str`, `is_active: bool`) and `serialize_user(db_user) ->
dict` that converts an ORM object (data lives on attributes, e.g. a SQLAlchemy `User`
instance; it is not a dict) into a plain dict via the pydantic model.
