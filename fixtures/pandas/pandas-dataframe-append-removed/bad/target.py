import pandas as pd


def orders_to_frame(orders):
    """Collect order dicts ({"sku": ..., "qty": ...}) into a DataFrame."""
    df = pd.DataFrame(columns=["sku", "qty"])
    for order in orders:
        df = df.append(order, ignore_index=True)
    return df
