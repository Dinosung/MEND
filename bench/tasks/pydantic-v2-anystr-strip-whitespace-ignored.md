<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Signup form handling with pydantic. Please write `target.py` with a model `SignupForm`
(`username: str`, `email: str`) that automatically strips surrounding whitespace and
lowercases every string field, configured at the model level rather than per field, and
`parse_signup(form_data: dict) -> SignupForm`.
