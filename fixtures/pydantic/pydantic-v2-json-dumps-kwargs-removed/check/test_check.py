import json
from datetime import date


def test_export_writes_readable_json(tmp_path):
    import target

    inv = target.Invoice(number="INV-1", customer="Zoë", issued=date(2024, 5, 1), total_cents=1999)
    out = tmp_path / "invoice.json"
    target.export_invoice(inv, str(out))

    text = out.read_text(encoding="utf-8")
    assert "\n  " in text  # indented
    assert "Zoë" in text  # not \u-escaped
    assert json.loads(text) == {
        "number": "INV-1", "customer": "Zoë", "issued": "2024-05-01", "total_cents": 1999,
    }
