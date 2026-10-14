import math

import numpy as np


def test_invalid_readings_become_nan():
    import target

    out = target.clean_readings([1.5, -2.0, float("inf"), 4])
    assert out.dtype == np.float64
    assert out[0] == 1.5 and out[3] == 4.0
    assert math.isnan(out[1]) and math.isnan(out[2])
