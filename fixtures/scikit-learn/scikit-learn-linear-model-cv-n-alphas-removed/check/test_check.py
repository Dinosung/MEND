import numpy as np


def make_data():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(120, 5))
    y = X @ np.array([3.0, 0.0, -2.0, 0.0, 0.0]) + 0.1 * rng.normal(size=120)
    return X, y


def test_fit_lasso():
    import target

    model = target.fit_lasso(*make_data())
    assert len(model.alphas_) == 30
    assert abs(model.coef_[0] - 3.0) < 0.2 and abs(model.coef_[2] + 2.0) < 0.2


def test_fit_elastic_net():
    import target

    model = target.fit_elastic_net(*make_data())
    assert np.shape(model.alphas_) == (2, 20)
    assert model.l1_ratio_ in (0.5, 0.9)
    assert abs(model.coef_[0] - 3.0) < 0.3
