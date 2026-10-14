<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
We talk to a camelCase JSON API but our Python code uses snake_case. Please write
`target.py` with a pydantic model `Customer` with fields `customer_id: int` and
`display_name: str`, aliased to `customerId` and `displayName`. It must parse the API's
camelCase JSON, serialize back to camelCase when dumping by alias, and ALSO be constructible
from Python using the snake_case field names. Add `make_customer(customer_id, display_name)
-> Customer` that builds one using the field names.
