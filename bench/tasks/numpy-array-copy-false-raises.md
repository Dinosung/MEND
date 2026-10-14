<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Performance matters in our numeric pipeline, so I want to avoid needless copies. Please
write `target.py` with `to_float_array(data)` that converts a list, tuple or ndarray to a
float64 numpy array, and guarantees that if the input is already a float64 ndarray it is
returned as-is (the very same object, no copy).
