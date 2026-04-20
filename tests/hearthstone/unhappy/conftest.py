import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "hs_unhappy: Hearthstone unhappy-path edge-case tests"
    )
    config.addinivalue_line(
        "markers", "slow: tests that take nontrivial time (may be skipped in fast TDD loop)"
    )
