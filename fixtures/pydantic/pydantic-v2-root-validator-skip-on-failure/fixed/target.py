from pydantic import BaseModel, model_validator


class PasswordChange(BaseModel):
    password: str
    password_confirm: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("passwords do not match")
        return self


def change_password(data: dict) -> PasswordChange:
    return PasswordChange(**data)
