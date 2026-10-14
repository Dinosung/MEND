def test_area_under_curve():
    import target

    auc = target.area_under_curve([0.0, 0.5, 1.0], [0.0, 0.8, 1.0])
    assert abs(auc - 0.65) < 1e-12


def test_common_ids():
    import target

    assert target.common_ids([3, 7, 9], [9, 3]).tolist() == [True, False, True]
