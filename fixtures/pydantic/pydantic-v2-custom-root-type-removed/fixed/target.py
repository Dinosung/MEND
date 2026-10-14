from typing import List

from pydantic import BaseModel, RootModel


class Tag(BaseModel):
    name: str


class TagList(RootModel[List[Tag]]):
    """Request body that is a bare JSON array of tags."""


def parse_tags(raw_json: str) -> list[str]:
    tags = TagList.model_validate_json(raw_json)
    return [t.name for t in tags.root]
