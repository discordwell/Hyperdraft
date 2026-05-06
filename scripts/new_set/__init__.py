"""
new_set — orchestrator helpers for the /new-set and /new-game pipelines.

Modules:
    coverage      Per-card play-counter + force-include deck builder helpers.
    balance_loop  Tournament JSON analyzer: per-card win-contribution,
                  per-archetype winrate, outlier detection, convergence check.
    wire_set      Edits set_registry.py / engine __init__.py + scaffolds the
                  smoke test for a freshly built set.
    art_harness   Generalized prompt-pack writer — same modes (manual / api /
                  local) as scripts/phyrexian_overworld/generate_card_art.py
                  but parameterized over a per-set style config so the
                  pipeline can drive it for any engine + any aesthetic.
"""
