import numpy as np


def area_under_curve(x, y):
    """Trapezoidal integral of y(x), e.g. for an ROC curve or a dose curve."""
    return float(np.trapezoid(y, x))


def common_ids(a, b):
    """Boolean mask of which ids in `a` also appear in `b`."""
    return np.isin(a, b)
