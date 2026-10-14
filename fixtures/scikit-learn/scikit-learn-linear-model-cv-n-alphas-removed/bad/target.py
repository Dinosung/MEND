from sklearn.linear_model import ElasticNetCV, LassoCV


def fit_lasso(X, y):
    """Lasso tuned by 5-fold CV over 30 automatically generated alphas."""
    return LassoCV(n_alphas=30, cv=5).fit(X, y)


def fit_elastic_net(X, y):
    """Elastic net tuned by 5-fold CV over l1_ratio in (0.5, 0.9) and 20 alphas each."""
    return ElasticNetCV(l1_ratio=[0.5, 0.9], n_alphas=20, cv=5).fit(X, y)
