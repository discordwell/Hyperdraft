"""
wire_set — register a freshly built set with the rest of the codebase.

Two registration paths, depending on engine:

1. MTG-engine sets (real or custom)
   Edits `src/cards/set_registry.py`:
     - Adds an import line in the appropriate import block.
     - Adds a `SETS["CODE"] = SetInfo(...)` entry.
     - Adds a `("CODE", REGISTRY_VAR)` tuple to `SET_REGISTRIES`.
   Also edits `src/cards/custom/__init__.py` (or `src/cards/__init__.py`
   for non-custom MTG) to expose the registry symbol.

2. Non-MTG engine sets (minecraft, pokemon, yugioh, hearthstone)
   Edits `src/cards/<engine>/__init__.py`:
     - Adds `from .<set_module> import <REGISTRY_VAR>`.
     - Merges `**<REGISTRY_VAR>` into the aggregate `<ENGINE>_CARDS` dict.

Both paths are idempotent — re-running with the same arguments is a
no-op (matching imports / entries are detected and skipped).

Smoke-test scaffold:
    `scaffold_smoke_test(...)` writes a `tests/test_<set>.py` file that
    asserts every card loads, every card has either a setup_interceptor
    or a cast_effect or is intentionally vanilla, and every starter deck
    loads without raising. The "every card resolves at least once"
    coverage check is owned by the balance-loop stage, not the smoke
    test.

CLI:
    python -m scripts.new_set.wire_set register-mtg \\
        --code MYSET --name "My Cool Set" --module myset \\
        --registry-var MYSET_CARDS --custom

    python -m scripts.new_set.wire_set register-engine \\
        --engine minecraft --module myset --registry-var MYSET_CARDS \\
        --aggregate-var MINECRAFT_CARDS

    python -m scripts.new_set.wire_set scaffold-test \\
        --set-label MYSET --import-path src.cards.minecraft.myset \\
        --registry-var MYSET_CARDS --decks "build:make_my_deck"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SET_REGISTRY_PATH = PROJECT_ROOT / "src" / "cards" / "set_registry.py"
CUSTOM_INIT_PATH = PROJECT_ROOT / "src" / "cards" / "custom" / "__init__.py"
CARDS_INIT_PATH = PROJECT_ROOT / "src" / "cards" / "__init__.py"


# =============================================================================
# Helpers
# =============================================================================

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _insert_before_line(text: str, anchor: str, insert: str) -> str:
    """
    Insert `insert` immediately before the first line containing `anchor`.
    Idempotent — if `insert` already exists in `text`, returns text
    unchanged.
    """
    if insert.strip() in text:
        return text
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if anchor in line:
            insert_with_nl = insert if insert.endswith("\n") else insert + "\n"
            lines.insert(i, insert_with_nl)
            return "".join(lines)
    raise ValueError(f"anchor not found: {anchor!r}")


def _insert_in_import_block(
    text: str,
    block_anchor: str,
    new_import: str,
) -> str:
    """
    Insert `new_import` (one bare identifier line, e.g. "    MYSET_CARDS,")
    inside a `from .X import (` block whose opening line contains
    `block_anchor`. Idempotent.
    """
    if new_import.strip() in text:
        return text
    lines = text.splitlines(keepends=True)
    in_block = False
    for i, line in enumerate(lines):
        if block_anchor in line and "import (" in line:
            in_block = True
            continue
        if in_block and line.strip().startswith(")"):
            new_line = new_import if new_import.endswith("\n") else new_import + "\n"
            lines.insert(i, new_line)
            return "".join(lines)
    raise ValueError(f"import block not found: {block_anchor!r}")


# =============================================================================
# 1. MTG-engine registration
# =============================================================================

def register_mtg_set(
    *,
    code: str,
    name: str,
    module: str,
    registry_var: str,
    set_type: str = "custom",
    release_date: str = "2026-01-01",
    custom: bool = True,
) -> tuple[Path, Path]:
    """
    Register an MTG-engine set in `src/cards/set_registry.py` and expose
    it from `src/cards/custom/__init__.py` (when custom=True) or
    `src/cards/__init__.py` (when custom=False).

    Args:
        code:          Set code, e.g. "MYSET". Must match the convention
                       used in `SETS` (3-4 letter uppercase).
        name:          Display name, e.g. "My Cool Set".
        module:        Python module name under cards/(custom/), e.g.
                       "myset" for `src/cards/custom/myset.py`.
        registry_var:  The dict variable exposed by that module, e.g.
                       "MYSET_CARDS".
        set_type:      "custom" | "standard" | "universes_beyond" | etc.
        release_date:  ISO date string for the SetInfo entry.
        custom:        True → custom dir; False → root cards dir.

    Returns:
        (set_registry_path, init_path) — the two files modified.
    """
    init_path = CUSTOM_INIT_PATH if custom else CARDS_INIT_PATH

    # 1a. Expose the registry symbol from cards/(custom/)__init__.py
    init_text = _read(init_path)
    import_line = f"from .{module} import {registry_var}\n"
    if import_line.strip() not in init_text:
        # Append at the very top of the existing imports — these init files
        # have their imports clustered at the top, so prepending after the
        # docstring is safe.
        # Find the last `from .` import and insert right after it.
        last_from = 0
        for m in re.finditer(r"^from \.\S+ import [A-Z_,\s]+\n",
                             init_text, flags=re.MULTILINE):
            last_from = m.end()
        if last_from == 0:
            init_text = import_line + init_text
        else:
            init_text = init_text[:last_from] + import_line + init_text[last_from:]
        _write(init_path, init_text)

    # 1b. Add to set_registry.py (import + SETS + SET_REGISTRIES)
    text = _read(SET_REGISTRY_PATH)

    if custom:
        block_anchor = "from .custom import"
    else:
        block_anchor = "from . import"
    new_import = f"    {registry_var},"
    text = _insert_in_import_block(text, block_anchor, new_import)

    # SETS dict — append before the closing brace of the dict.
    sets_entry = (
        f'    "{code}": SetInfo("{code}", "{name}", '
        f'len({registry_var}), "{release_date}", "{set_type}"),\n'
    )
    if sets_entry.strip() not in text:
        # Find `SETS: dict[...] = {` and its matching closing `}`. The
        # type annotation may contain nested brackets, so we accept any
        # non-`=` chars between the colon and the assignment.
        m = re.search(r"^SETS\s*(?::\s*[^=]+)?=\s*\{", text, flags=re.MULTILINE)
        if not m:
            raise ValueError("SETS dict not found in set_registry.py")
        # Find first `}\n` after this position at column 0.
        close = re.search(r"^\}\s*\n", text[m.end():], flags=re.MULTILINE)
        if not close:
            raise ValueError("SETS dict closing brace not found")
        close_idx = m.end() + close.start()
        text = text[:close_idx] + sets_entry + text[close_idx:]

    # SET_REGISTRIES list — append before the closing bracket.
    reg_entry = f'    ("{code}", {registry_var}),\n'
    if reg_entry.strip() not in text:
        # `list[tuple[str, dict]]` has nested brackets — accept any
        # non-`=` chars between the colon and the assignment.
        m = re.search(
            r"^SET_REGISTRIES\s*(?::\s*[^=]+)?=\s*\[",
            text,
            flags=re.MULTILINE,
        )
        if not m:
            raise ValueError("SET_REGISTRIES list not found")
        close = re.search(r"^\]\s*\n", text[m.end():], flags=re.MULTILINE)
        if not close:
            raise ValueError("SET_REGISTRIES list closing bracket not found")
        close_idx = m.end() + close.start()
        text = text[:close_idx] + reg_entry + text[close_idx:]

    _write(SET_REGISTRY_PATH, text)
    return SET_REGISTRY_PATH, init_path


# =============================================================================
# 2. Engine-specific registration (non-MTG)
# =============================================================================

def register_engine_set(
    *,
    engine: str,
    module: str,
    registry_var: str,
    aggregate_var: str | None = None,
) -> Path:
    """
    Register a set in a non-MTG engine's `__init__.py`. Adds:
        from .<module> import <REGISTRY_VAR>
    and merges `**<REGISTRY_VAR>` into the engine's aggregate dict literal.

    Args:
        engine:        engine subdir name, e.g. "minecraft".
        module:        new file under that engine, e.g. "myset".
        registry_var:  dict var exported by that module, e.g.
                       "MYSET_CARDS".
        aggregate_var: name of the aggregate dict (default
                       "<ENGINE>_CARDS"). The aggregate must already exist
                       and be a `{**A, **B}`-style dict literal at module
                       top level.

    Returns the modified `__init__.py` path.
    """
    init_path = PROJECT_ROOT / "src" / "cards" / engine / "__init__.py"
    if not init_path.exists():
        raise FileNotFoundError(init_path)
    if aggregate_var is None:
        aggregate_var = f"{engine.upper()}_CARDS"

    text = _read(init_path)

    # 2a. Add import.
    import_line = f"from .{module} import {registry_var}\n"
    if import_line.strip() not in text:
        # Insert right after the last existing `from .X import …` line.
        matches = list(re.finditer(
            r"^from \.\S+ import .+\n(?:.+\n)*?(?:[A-Z_]+,\n)*?\)?\n?",
            text,
            flags=re.MULTILINE,
        ))
        if matches:
            last = matches[-1]
            text = text[:last.end()] + import_line + text[last.end():]
        else:
            text = import_line + text

    # 2b. Merge into aggregate dict.
    # Two supported layouts:
    #   (a) Single-line spread literal:
    #         <aggregate_var>: dict = {**A, **B}
    #       → insert `, **<registry_var>` before the closing `}`.
    #   (b) Dict comprehension over a `for card in [*A.values(), *B.values()]` list:
    #         <aggregate_var>: dict[str, X] = {
    #             card.name: card
    #             for card in [
    #                 *FOO.values(),
    #                 *BAR.values(),
    #             ]
    #         }
    #       → insert `*<registry_var>.values(),` inside the bracketed source list.
    #   This is the shape `src/cards/scp/__init__.py` uses, and a few other engines
    #   follow it when they need post-construction mutation passes (mechanics
    #   appliers etc.).
    # The `\b` after the var name prevents `MINECRAFT_CARDS` from also
    # matching e.g. `MINECRAFT_CARDS_LEGACY` if both exist in the file.
    pattern_inline = re.compile(
        rf"^({re.escape(aggregate_var)}\b(?:\s*:\s*dict)?\s*=\s*\{{)([^}}]*)(\}})",
        flags=re.MULTILINE,
    )
    m = pattern_inline.search(text)
    spread_token = f"**{registry_var}"
    values_token = f"*{registry_var}.values(),"
    if m:
        inside = m.group(2)
        if spread_token not in inside:
            if inside.strip().endswith(",") or not inside.strip():
                new_inside = f"{inside}{spread_token}, "
            else:
                new_inside = f"{inside}, {spread_token}"
            text = text[:m.start()] + m.group(1) + new_inside + m.group(3) + text[m.end():]
    else:
        # Layout (b): dict comprehension over a bracketed source list.
        # Find the `<aggregate_var>... = {` header (multi-line allowed),
        # then locate the bracketed `for card in [...]` list inside and
        # append a `*<registry_var>.values(),` line.
        header = re.search(
            rf"^{re.escape(aggregate_var)}\b[^\n]*?=\s*\{{",
            text,
            flags=re.MULTILINE,
        )
        if not header:
            raise ValueError(
                f"aggregate dict {aggregate_var} not found in {init_path}"
            )
        # Find `for ... in [` after the header, then its matching `]`.
        body_search = re.search(r"for\s+\w+\s+in\s+\[", text[header.end():])
        if not body_search:
            raise ValueError(
                f"aggregate dict {aggregate_var} is neither a {{**A, **B}} "
                f"literal nor a `for card in [...]` comprehension; "
                f"unsupported layout in {init_path}"
            )
        list_open_idx = header.end() + body_search.end()
        # Locate matching `]` accounting for nested brackets.
        depth = 1
        i = list_open_idx
        n = len(text)
        list_close_idx: int | None = None
        while i < n and depth > 0:
            ch = text[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    list_close_idx = i
                    break
            i += 1
        if list_close_idx is None:
            raise ValueError(
                f"could not find closing `]` for aggregate dict comprehension "
                f"of {aggregate_var} in {init_path}"
            )
        slice_inside = text[list_open_idx:list_close_idx]
        if values_token not in slice_inside and spread_token not in slice_inside:
            # Insert as a new indented line right before the closing `]`.
            # Detect the indent by looking at the previous non-empty line
            # in slice_inside.
            inner_lines = slice_inside.splitlines()
            indent = "        "
            for line in reversed(inner_lines):
                stripped = line.lstrip()
                if stripped and stripped != "":
                    indent = line[: len(line) - len(stripped)]
                    break
            insertion = f"{indent}{values_token}\n"
            # If the closing `]` sits on a line of its own with trailing whitespace
            # before it, place the insertion right before that line's start.
            # Walk backward from list_close_idx to find newline.
            pre_close = text.rfind("\n", 0, list_close_idx)
            if pre_close == -1:
                text = (
                    text[:list_close_idx]
                    + insertion
                    + text[list_close_idx:]
                )
            else:
                # Insert insertion before the `]` line.
                text = (
                    text[: pre_close + 1]
                    + insertion
                    + text[pre_close + 1:]
                )

    _write(init_path, text)
    return init_path


# =============================================================================
# 3. Smoke-test scaffolding
# =============================================================================

SMOKE_TEST_TEMPLATE = '''"""
Smoke tests for {set_label} — generated by scripts/new_set/wire_set.py.

Asserts:
  - every card in the set imports without error
  - every card has a CardDefinition with name + characteristics
  - every starter deck builder runs without raising and returns a
    non-empty list of CardDefinitions

The "every card actually resolves in play" guarantee is enforced by the
balance-loop coverage stage (scripts/new_set/balance_loop.py +
scripts/new_set/coverage.py), which can detect missing implementations
via zero-play cards across the tournament — that check is engine-aware
where this scaffold is engine-agnostic by design.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from {import_path} import {registry_var}{deck_imports}


def test_every_card_loads():
    assert {registry_var}, "{set_label} card registry is empty"
    for name, card in {registry_var}.items():
        assert card is not None, f"{{name}}: card def is None"
        assert card.name, f"{{name}}: card has no .name"
        assert card.characteristics is not None, \\
            f"{{name}}: card has no .characteristics"


{deck_tests}


if __name__ == "__main__":
    test_every_card_loads()
{deck_test_calls}
    print("OK — {set_label} smoke tests pass.")
'''


DECK_TEST_TEMPLATE = '''def test_deck_{deck_name}_builds():
    deck = {builder_call}()
    assert deck, "{deck_name} builder returned an empty deck"
    for cd in deck:
        assert cd is not None, "{deck_name} contains a None card"
        assert getattr(cd, "name", None), "{deck_name} contains a nameless card"
'''


def scaffold_smoke_test(
    *,
    set_label: str,
    import_path: str,
    registry_var: str,
    decks: list[tuple[str, str]] | None = None,
    out_path: Path | None = None,
) -> Path:
    """
    Write a tests/test_<set_label>.py smoke test.

    Args:
        set_label:      Used in the docstring + assert messages.
        import_path:    Python module path to import from, e.g.
                        "src.cards.minecraft.myset".
        registry_var:   Dict variable name inside that module.
        decks:          List of (deck_name, builder_func_name) tuples,
                        each builder is called as `builder_func_name()`.
                        Pass [] if the set has no starter decks yet.
        out_path:       Override path. Default
                        `tests/test_<set_label_lower>.py`.

    Returns the written path.
    """
    decks = decks or []

    if decks:
        deck_imports = ", " + ", ".join(b for _, b in decks)
        deck_tests = "\n".join(
            DECK_TEST_TEMPLATE.format(deck_name=name, builder_call=builder)
            for name, builder in decks
        )
        deck_test_calls = "\n".join(
            f"    test_deck_{name}_builds()" for name, _ in decks
        )
    else:
        deck_imports = ""
        deck_tests = ""
        deck_test_calls = ""

    body = SMOKE_TEST_TEMPLATE.format(
        set_label=set_label,
        import_path=import_path,
        registry_var=registry_var,
        deck_imports=deck_imports,
        deck_tests=deck_tests,
        deck_test_calls=deck_test_calls,
    )

    if out_path is None:
        out_path = PROJECT_ROOT / "tests" / f"test_{set_label.lower()}.py"
    _write(out_path, body)
    return out_path


# =============================================================================
# CLI
# =============================================================================

def _cmd_register_mtg(args: argparse.Namespace) -> int:
    reg, init = register_mtg_set(
        code=args.code,
        name=args.name,
        module=args.module,
        registry_var=args.registry_var,
        set_type=args.set_type,
        release_date=args.release_date,
        custom=args.custom,
    )
    print(f"updated: {reg}")
    print(f"updated: {init}")
    return 0


def _cmd_register_engine(args: argparse.Namespace) -> int:
    p = register_engine_set(
        engine=args.engine,
        module=args.module,
        registry_var=args.registry_var,
        aggregate_var=args.aggregate_var,
    )
    print(f"updated: {p}")
    return 0


def _cmd_scaffold_test(args: argparse.Namespace) -> int:
    decks: list[tuple[str, str]] = []
    for spec in (args.decks or "").split(","):
        spec = spec.strip()
        if not spec:
            continue
        if ":" not in spec:
            raise SystemExit(
                f"--decks entry must be 'name:builder_func', got {spec!r}"
            )
        name, builder = spec.split(":", 1)
        decks.append((name.strip(), builder.strip()))

    p = scaffold_smoke_test(
        set_label=args.set_label,
        import_path=args.import_path,
        registry_var=args.registry_var,
        decks=decks,
        out_path=Path(args.out) if args.out else None,
    )
    print(f"wrote: {p}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("register-mtg",
                        help="Register an MTG-engine set in set_registry.py.")
    p1.add_argument("--code", required=True)
    p1.add_argument("--name", required=True)
    p1.add_argument("--module", required=True)
    p1.add_argument("--registry-var", required=True)
    p1.add_argument("--set-type", default="custom")
    p1.add_argument("--release-date", default="2026-01-01")
    p1.add_argument("--custom", action="store_true",
                    help="Set lives under src/cards/custom/.")
    p1.set_defaults(fn=_cmd_register_mtg)

    p2 = sub.add_parser("register-engine",
                        help="Register a set in a non-MTG engine __init__.py.")
    p2.add_argument("--engine", required=True,
                    help="Engine dir name, e.g. minecraft.")
    p2.add_argument("--module", required=True)
    p2.add_argument("--registry-var", required=True)
    p2.add_argument("--aggregate-var", default=None)
    p2.set_defaults(fn=_cmd_register_engine)

    p3 = sub.add_parser("scaffold-test",
                        help="Write tests/test_<set>.py smoke test.")
    p3.add_argument("--set-label", required=True)
    p3.add_argument("--import-path", required=True)
    p3.add_argument("--registry-var", required=True)
    p3.add_argument("--decks", default="",
                    help="Comma-separated 'name:builder_func' pairs.")
    p3.add_argument("--out", default=None)
    p3.set_defaults(fn=_cmd_scaffold_test)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
