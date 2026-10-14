from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    email: str
    is_active: bool

    class Config:
        orm_mode = True


def serialize_user(db_user) -> dict:
    """Convert an ORM row (e.g. a SQLAlchemy User instance) into API output."""
    return UserOut.model_validate(db_user).model_dump()
