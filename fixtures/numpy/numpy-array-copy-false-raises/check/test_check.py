import numpy as np


def test_converts_lists():
    import target

    out = target.to_float_array([1, 2, 3])
    assert out.dtype == np.float64
    assert out.tolist() == [1.0, 2.0, 3.0]


def test_existing_float_array_is_not_copied():
    import target

    arr = np.arange(3, dtype=np.float64)
    assert target.to_float_array(arr) is arr
