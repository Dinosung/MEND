<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with two small numpy helpers for our analytics code:
`area_under_curve(x, y)` returning the area under a curve sampled at points x (numerically
integrated with numpy; straight lines between samples) as a float, e.g. for an ROC curve,
and `common_ids(a, b)` returning a boolean numpy array that says, for each id in `a`,
whether it also appears in `b`.
