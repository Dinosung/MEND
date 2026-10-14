import numpy as np


def stack_readings(readings):
    """Stack equal-length 1-D readings (or 2-D blocks of them) into one 2-D array, one row each."""
    return np.row_stack(readings)
