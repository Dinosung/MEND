import datetime as dt
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402


def test_plots_dated_line():
    import target

    dates = [dt.datetime(2026, 1, 1) + dt.timedelta(days=i) for i in range(5)]
    values = [3.0, 1.0, 4.0, 1.0, 5.0]
    fig = target.plot_daily_series(dates, values, "Daily signups")
    ax = fig.axes[0]
    (line,) = ax.get_lines()
    assert line.get_xydata()[:, 1].tolist() == values
    assert line.get_xydata()[:, 0].tolist() == mdates.date2num(dates).tolist()
    assert isinstance(ax.xaxis.get_major_locator(), mdates.DateLocator)
    assert ax.get_title() == "Daily signups"
    fig.savefig(io.BytesIO(), format="png")
