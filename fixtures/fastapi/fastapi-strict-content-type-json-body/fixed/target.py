from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    quantity: int


@app.post("/items")
def create_item(item: Item):
    return {"name": item.name, "quantity": item.quantity}


def post_item(client, payload: dict):
    """Send an item to the API (used by tests and the sync script)."""
    return client.post("/items", json=payload)
