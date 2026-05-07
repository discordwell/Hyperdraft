"""Engine-specific tournament adapters for the /new-set balance loop.

Each adapter exposes a `run_<engine>_tournament(...)` async function that
emits the canonical `{set_summary, matchup, card_scores}` JSON shape
consumed by `scripts/new_set/balance_loop.py` and
`scripts/new_set/coverage.py`.
"""
