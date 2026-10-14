<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Password change form with pydantic. Please write `target.py` with a model `PasswordChange`
with `password` and `password_confirm` string fields and a validator on the model that
checks both fields together and raises a validation error with the message "passwords do not
match" when they differ. Add `change_password(data: dict) -> PasswordChange`.
