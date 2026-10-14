from matplotlib import cm
from matplotlib.colors import to_hex


def color_ramp(name, n):
    """n evenly spaced hex colors sampled from the named colormap, first to last."""
    cmap = cm.get_cmap(name, n)
    return [to_hex(cmap(i)) for i in range(n)]
