from datetime import date

from pydantic import BaseModel


class Invoice(BaseModel):
    number: str
    customer: str
    issued: date
    total_cents: int


def export_invoice(invoice: Invoice, path: str) -> None:
    """Write a human-readable JSON export of the invoice."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(invoice.json(indent=2, ensure_ascii=False))
