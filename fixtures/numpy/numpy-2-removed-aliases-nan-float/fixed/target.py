import numpy as np


def clean_readings(values):
    """Sensor readings as float64; negatives are invalid -> NaN, inf -> NaN."""
    arr = np.asarray(values, dtype=np.float64)
    arr[arr < 0] = np.nan
    arr[arr == np.inf] = np.nan
    return arr
