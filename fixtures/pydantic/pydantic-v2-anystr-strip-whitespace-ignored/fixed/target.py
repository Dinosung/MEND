from pydantic import BaseModel, ConfigDict


class SignupForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, str_to_lower=True)

    username: str
    email: str


def parse_signup(form_data: dict) -> SignupForm:
    return SignupForm(**form_data)
