import numpy as np


def test_stacks_rows():
    import target

    out = target.stack_readings([np.array([1.0, 2.0, 3.0]), [4.0, 5.0, 6.0]])
    assert out.shape == (2, 3)
    assert out.tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]


def test_mixes_rows_and_blocks():
    import target

    out = target.stack_readings([np.zeros(2), np.ones((2, 2))])
    assert out.tolist() == [[0.0, 0.0], [1.0, 1.0], [1.0, 1.0]]
