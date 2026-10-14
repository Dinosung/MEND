import matplotlib

matplotlib.use("Agg")


def test_viridis_ramp():
    import target

    assert target.color_ramp("viridis", 3) == ["#440154", "#21918c", "#fde725"]


def test_ramp_length_and_ends():
    import target

    ramp = target.color_ramp("viridis", 5)
    assert len(ramp) == 5
    assert ramp[0] == "#440154" and ramp[-1] == "#fde725"
