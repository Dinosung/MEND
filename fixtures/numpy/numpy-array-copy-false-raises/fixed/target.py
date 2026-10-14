import numpy as np


def to_float_array(data):
    """Convert input (list, tuple or ndarray) to a float64 array without
    copying when it is already one."""
    return np.asarray(data, dtype=np.float64)
