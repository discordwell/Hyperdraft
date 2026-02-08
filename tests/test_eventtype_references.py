import re
from pathlib import Path

from src.engine.types import EventType


def test_no_missing_eventtype_references_in_card_scripts():
    """
    Card scripts frequently reference EventType members in filter/resolve code.

    A missing EventType name will crash at runtime the first time that code path
    executes, which is painful to debug in long stress runs. Keep this cheap
    static check to prevent regressions.
    """
    members = set(EventType.__members__.keys())
    pat = re.compile(r"EventType\\.([A-Z0-9_]+)")

    repo_root = Path(__file__).resolve().parents[1]
    cards_root = repo_root / "src" / "cards"

    missing: dict[str, set[str]] = {}
    for path in cards_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in pat.finditer(text):
            name = m.group(1)
            if name not in members:
                missing.setdefault(name, set()).add(str(path.relative_to(repo_root)))

    assert not missing, f"Missing EventType members referenced in src/cards: {missing}"

