from typing import List

from pydantic import BaseModel


class Tag(BaseModel):
    name: str


class TagList(BaseModel):
    """Request body that is a bare JSON array of tags."""

    __root__: List[Tag]


def parse_tags(raw_json: str) -> list[str]:
    tags = TagList.model_validate_json(raw_json)
    return [t.name for t in tags.__root__]
