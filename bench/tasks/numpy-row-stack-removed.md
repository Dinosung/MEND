<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with a small numpy helper for our sensor pipeline:
`stack_readings(readings)` takes a list whose items are either equal-length 1-D readings
(numpy arrays or plain lists) or 2-D blocks of such readings, and stacks them row-wise into a
single 2-D numpy array with one reading per row, in order.
