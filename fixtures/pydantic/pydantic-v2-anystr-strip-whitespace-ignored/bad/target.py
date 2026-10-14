from pydantic import BaseModel


class SignupForm(BaseModel):
    username: str
    email: str

    class Config:
        anystr_strip_whitespace = True
        anystr_lower = True


def parse_signup(form_data: dict) -> SignupForm:
    return SignupForm(**form_data)
