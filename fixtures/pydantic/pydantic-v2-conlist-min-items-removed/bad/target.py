from pydantic import BaseModel, conlist


class BulkInvite(BaseModel):
    team_id: int
    emails: conlist(str, min_items=1, max_items=50)


def parse_invite(data: dict) -> BulkInvite:
    return BulkInvite(**data)
