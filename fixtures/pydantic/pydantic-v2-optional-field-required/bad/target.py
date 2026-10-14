from typing import Optional

from pydantic import BaseModel


class UserProfileUpdate(BaseModel):
    """PATCH body: clients send only the fields they want to change."""

    display_name: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]


def parse_update(payload: dict) -> dict:
    update = UserProfileUpdate(**payload)
    return update.model_dump(exclude_none=True)
