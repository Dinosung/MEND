import matplotlib.pyplot as plt


def plot_daily_series(dates, values, title):
    """Line chart of values over datetime dates; returns the Figure."""
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot_date(dates, values, "-")
    ax.set_title(title)
    fig.autofmt_xdate()
    return fig
