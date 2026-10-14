from pydantic import BaseModel, ConfigDict, Field


class Customer(BaseModel):
    """Payload model for a camelCase JSON API, also built from Python code."""

    model_config = ConfigDict(populate_by_name=True)

    customer_id: int = Field(alias="customerId")
    display_name: str = Field(alias="displayName")


def make_customer(customer_id: int, display_name: str) -> Customer:
    return Customer(customer_id=customer_id, display_name=display_name)
