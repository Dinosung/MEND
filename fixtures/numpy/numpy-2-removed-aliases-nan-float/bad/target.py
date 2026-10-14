import numpy as np


def clean_readings(values):
    """Sensor readings as float64; negatives are invalid -> NaN, inf -> NaN."""
    arr = np.asarray(values, dtype=np.float_)
    arr[arr < 0] = np.NaN
    arr[arr == np.Inf] = np.NaN
    return arr
