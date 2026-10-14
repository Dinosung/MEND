from pydantic import BaseModel, Field


class Product(BaseModel):
    sku: str = Field(..., pattern=r"^[A-Z]{3}-\d{4}$")
    name: str


def parse_product(data: dict) -> Product:
    return Product(**data)
