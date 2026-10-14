from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool


def serialize_user(db_user) -> dict:
    """Convert an ORM row (e.g. a SQLAlchemy User instance) into API output."""
    return UserOut.model_validate(db_user).model_dump()
