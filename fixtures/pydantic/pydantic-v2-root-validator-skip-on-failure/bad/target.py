from pydantic import BaseModel, root_validator


class PasswordChange(BaseModel):
    password: str
    password_confirm: str

    @root_validator
    def passwords_match(cls, values):
        if values.get("password") != values.get("password_confirm"):
            raise ValueError("passwords do not match")
        return values


def change_password(data: dict) -> PasswordChange:
    return PasswordChange(**data)
