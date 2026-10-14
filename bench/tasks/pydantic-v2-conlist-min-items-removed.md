<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Bulk team invites with pydantic. Please write `target.py` with a model `BulkInvite` with
`team_id: int` and `emails`, a list of strings that must contain at least 1 and at most 50
entries, using pydantic's constrained list type. Add `parse_invite(data: dict) ->
BulkInvite`; out-of-range lists must raise a validation error.
