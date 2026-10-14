<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with two scikit-learn model builders for our feature-selection
step. `fit_lasso(X, y)` fits a Lasso whose regularization strength is chosen by 5-fold
cross-validation over a path of 30 automatically generated candidate strengths, and returns
the fitted estimator. `fit_elastic_net(X, y)` does the same for an elastic net, searching
the L1 mixing ratio over 0.5 and 0.9 with 20 automatically generated strengths per ratio, and
returns the fitted estimator. Use scikit-learn's built-in cross-validated estimators.
