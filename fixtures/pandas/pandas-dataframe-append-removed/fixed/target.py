import pandas as pd


def orders_to_frame(orders):
    """Collect order dicts ({"sku": ..., "qty": ...}) into a DataFrame."""
    rows = [{"sku": o["sku"], "qty": o["qty"]} for o in orders]
    return pd.DataFrame(rows, columns=["sku", "qty"])
