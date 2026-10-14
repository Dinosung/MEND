"""MEND-Bench: does verified failure memory reduce repeat failures by coding agents?

Headline metric: repeat-failure rate = fraction of scored tasks whose solution exhibits
the fixture's known failure (scored by running the fixture's own check/ against the
agent's target.py), compared between a baseline arm and a with-MEND arm.
"""
