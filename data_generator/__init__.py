"""Synthetic health-tech data generator.

Produces reproducible, correlated synthetic data for wearables, body-composition
scans, nutrition logs, a device dimension, and an A/B experiment. All data is
fake (numpy + Faker); no real users are involved.
"""

__all__ = ["generate"]
