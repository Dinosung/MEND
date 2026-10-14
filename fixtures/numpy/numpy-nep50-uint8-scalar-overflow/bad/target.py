import numpy as np


def brighten_pixel(img: np.ndarray, row: int, col: int, amount: int) -> int:
    """Brighten one uint8 pixel by `amount`, saturating at 255."""
    return int(min(img[row, col] + amount, 255))
