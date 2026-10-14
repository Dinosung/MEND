from pydantic import BaseModel, Field


class Customer(BaseModel):
    """Payload model for a camelCase JSON API, also built from Python code."""

    customer_id: int = Field(alias="customerId")
    display_name: str = Field(alias="displayName")

    class Config:
        allow_population_by_field_name = True


def make_customer(customer_id: int, display_name: str) -> Customer:
    return Customer(customer_id=customer_id, display_name=display_name)
