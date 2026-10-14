<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with a matplotlib helper for our reporting jobs:
`plot_daily_series(dates, values, title)` takes a list of `datetime.datetime` objects and a
list of numbers, draws them as a single line chart with a proper date axis (date ticks and
labels on x, labels rotated so they don't overlap) and the given title, and returns the
matplotlib Figure. It runs headless on a server, so nothing should be shown on screen.
