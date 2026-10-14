from pydantic import BaseModel, conlist


class BulkInvite(BaseModel):
    team_id: int
    emails: conlist(str, min_length=1, max_length=50)


def parse_invite(data: dict) -> BulkInvite:
    return BulkInvite(**data)
