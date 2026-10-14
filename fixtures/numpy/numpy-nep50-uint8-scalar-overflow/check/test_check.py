import warnings

import numpy as np


def test_brighten_saturates_instead_of_wrapping():
    import target

    img = np.array([[250, 10]], dtype=np.uint8)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        assert target.brighten_pixel(img, 0, 0, 10) == 255
        assert target.brighten_pixel(img, 0, 1, 10) == 20
