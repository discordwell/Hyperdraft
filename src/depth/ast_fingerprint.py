"""
AST fingerprint and feature extraction for card effect callables.

For each callable (effect_fn, setup_interceptors, resolve, battlecry, etc.),
parse the source module and walk the function's AST — recursively descending
into local-helper calls so the fingerprint reflects the full call graph, not
just the surface body.

The two outputs are:
    FeatureBag — raw signals used by axis_scorer.score_card
    code_fingerprint() — short hash of (helpers, state_attrs, event_types,
                         zones) that collapses literal reskins to the same key
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional


@dataclass
class FeatureBag:
    """Raw AST signals collected from a card's callable(s)."""

    # Names of all functions called transitively (top-level helpers + imports).
    helpers_called: set[str] = field(default_factory=set)
    # Attribute names accessed off `state` (e.g. zones, objects, players, stack).
    state_attrs: set[str] = field(default_factory=set)
    # EventType.X members referenced.
    event_types: set[str] = field(default_factory=set)
    # Zone-name prefixes extracted from f"<prefix>_{var}" patterns or
    # ZoneType.X enum references.
    zones_accessed: set[str] = field(default_factory=set)
    # Detected cross-controller reads/writes (!= attacker.controller etc).
    cross_controller: bool = False
    # Reads of opponent-side state (`next((p for p in state.players if p != ...))`).
    opponent_iteration: bool = False
    # Names of recognized modal/choice helpers called (resolved against profile later).
    modal_calls: set[str] = field(default_factory=set)
    # Names of recognized filter-factory calls.
    filter_factory_calls: set[str] = field(default_factory=set)
    # Names of recognized "novel" helpers (room unlock, manifest, suspect, etc).
    novel_helper_calls: set[str] = field(default_factory=set)
    # Number of distinct Call nodes encountered (rough complexity signal).
    raw_call_count: int = 0
    # Whether any `for X in ...` loop appears (signals multi-target / sweep).
    has_for_loop: bool = False
    # Whether an `if`/conditional branches the effect.
    has_branch: bool = False
    # If the only body is `return []` or trivial, mark as empty.
    is_trivially_empty: bool = False

    def code_fingerprint(self) -> str:
        """12-char hash of the structural signature. Two cards with identical
        signatures = mechanical reskins."""
        sig = (
            tuple(sorted(self.helpers_called)),
            tuple(sorted(self.state_attrs)),
            tuple(sorted(self.event_types)),
            tuple(sorted(self.zones_accessed)),
        )
        return hashlib.sha256(repr(sig).encode()).hexdigest()[:12]

    def merge(self, other: "FeatureBag") -> None:
        """Combine another bag into this one (used to fold multiple callables
        on a single card — e.g. all attacks on a Pokemon)."""
        self.helpers_called |= other.helpers_called
        self.state_attrs |= other.state_attrs
        self.event_types |= other.event_types
        self.zones_accessed |= other.zones_accessed
        self.cross_controller = self.cross_controller or other.cross_controller
        self.opponent_iteration = self.opponent_iteration or other.opponent_iteration
        self.modal_calls |= other.modal_calls
        self.filter_factory_calls |= other.filter_factory_calls
        self.novel_helper_calls |= other.novel_helper_calls
        self.raw_call_count += other.raw_call_count
        self.has_for_loop = self.has_for_loop or other.has_for_loop
        self.has_branch = self.has_branch or other.has_branch
        # is_trivially_empty: only True if BOTH are empty
        self.is_trivially_empty = self.is_trivially_empty and other.is_trivially_empty


# ---------------------------------------------------------------------------
# Module-level AST cache (one parse per source file).
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _parse_module(path: str) -> tuple[Optional[ast.Module], dict[str, ast.FunctionDef]]:
    """Parse a Python file and index its FunctionDefs by name AND by qualname.

    Indexes both top-level functions (keyed by simple name) and nested
    functions (keyed by qualname, e.g. ``make_equipment_setup.<locals>._setup``).
    This lets the scorer locate closures returned by factory helpers — the
    AST walker can then descend into the nested ``def _setup(obj, state):``
    body and surface the real mechanics. Without this, every card built
    through ``make_equipment_setup`` / ``make_aura_setup`` / similar
    factories fingerprinted as ``helpers=[]`` because the walker only
    found the wrapper (whose body just calls the helper) and couldn't
    follow the closure into its captured logic. Surfaced by SPMC/MHA/TMH
    spice-pass agents 2026-05-18.
    """
    try:
        source = Path(path).read_text()
    except (OSError, UnicodeDecodeError):
        return None, {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None, {}
    funcs: dict[str, ast.FunctionDef] = {}
    # Top-level functions: keyed by simple name (backwards-compatible).
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node  # type: ignore[assignment]

    # Nested functions: keyed by approximate qualname so closures returned
    # by factory helpers are findable. Walks every FunctionDef in the tree
    # and synthesizes ``<parent>.<locals>.<name>`` keys matching Python's
    # runtime ``__qualname__`` format.
    def _index_nested(node: ast.AST, parent_qualname: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = (
                    f"{parent_qualname}.<locals>.{child.name}"
                    if parent_qualname
                    else child.name
                )
                if parent_qualname:
                    # Don't overwrite the top-level entry above; nested
                    # entries get the dotted qualname key.
                    funcs.setdefault(qualname, child)  # type: ignore[assignment]
                _index_nested(child, qualname)
            else:
                _index_nested(child, parent_qualname)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _index_nested(node, node.name)

    return tree, funcs


def _func_source_for_callable(fn: Callable) -> tuple[Optional[str], Optional[ast.FunctionDef], dict[str, ast.FunctionDef]]:
    """Locate the source file and AST FunctionDef for a runtime callable.

    Tries ``fn.__qualname__`` first to find nested closures (e.g.
    ``make_equipment_setup.<locals>._setup``), then falls back to
    ``fn.__name__`` for the top-level case. Without the qualname lookup,
    a closure returned by a factory helper resolves to a top-level entry
    named ``_setup`` that doesn't exist, and the walker would early-return
    an empty FeatureBag.
    """
    try:
        path = inspect.getsourcefile(fn) or inspect.getfile(fn)
    except (TypeError, OSError):
        return None, None, {}
    if not path:
        return None, None, {}
    _, funcs = _parse_module(path)
    # Prefer qualname for nested closures; fall back to simple name.
    qualname = getattr(fn, "__qualname__", None)
    fdef = None
    if qualname and qualname in funcs:
        fdef = funcs[qualname]
    if fdef is None:
        fdef = funcs.get(fn.__name__)
    return path, fdef, funcs


# ---------------------------------------------------------------------------
# Helpers for identifying specific AST patterns.
# ---------------------------------------------------------------------------


def _name_of_call(node: ast.expr) -> Optional[str]:
    """Return the simple function name being called, or None if it's a method
    chain we don't care about."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        # Method call like state.zones.get — return the attr name so we can
        # detect specific patterns (e.g. "get" on zones).
        return node.attr
    return None


_ZONE_F_STRING_RE = re.compile(r"^([a-zA-Z_]+)_$")


def _zone_prefix_from_fstring(arg: ast.expr) -> Optional[str]:
    """Extract the zone prefix from f"<prefix>_{var}" or "<prefix>" literal."""
    # f"bench_{var}" → JoinedStr with FormattedValue
    if isinstance(arg, ast.JoinedStr):
        # First Constant value should be "<prefix>_"
        if arg.values and isinstance(arg.values[0], ast.Constant):
            val = arg.values[0].value
            if isinstance(val, str):
                m = _ZONE_F_STRING_RE.match(val)
                if m:
                    return m.group(1)
                # Some zones may be written as e.g. "battlefield" (no suffix)
                if "_" not in val:
                    return val.rstrip("_") or None
    # Plain string literal: "battlefield"
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value.split("_")[0] if "_" in arg.value else arg.value
    return None


def _refers_to_controller(node: ast.expr) -> bool:
    """Detect `attacker.controller`, `obj.controller`, `<x>.controller`."""
    return isinstance(node, ast.Attribute) and node.attr == "controller"


def _is_zonetype_attr(node: ast.expr) -> bool:
    """Detect ZoneType.BATTLEFIELD-style references."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "ZoneType"
    )


# ---------------------------------------------------------------------------
# Walker.
# ---------------------------------------------------------------------------


# Builtins / library names we should not descend into.
_NEVER_DESCEND = frozenset({
    "len", "min", "max", "sum", "any", "all", "list", "set", "dict", "tuple",
    "range", "enumerate", "zip", "sorted", "reversed", "abs", "int", "float",
    "str", "bool", "next", "iter", "type", "isinstance", "hasattr", "getattr",
    "setattr", "print", "id", "repr", "open", "Path", "deepcopy", "copy",
    # AST builtins from Pokemon helpers
    "Event", "EventType", "ZoneType",
    # Random / RNG
    "random", "choice", "shuffle", "randint", "sample",
})


def _iter_name_args(node: ast.Call):
    """Yield every `ast.Name` reference appearing anywhere inside a Call
    node's positional args, keyword values, or nested dict/list/tuple/set
    values. Used by the function-arg descent (slice 7B) to find module-level
    function references passed as data (e.g. `{1: chapter_i, 2: chapter_ii}`
    for ``make_saga_setup`` or ``[{'effect_fn': fn}]`` for
    ``make_equipment_setup``).

    We only walk through *container* literals (Dict / List / Tuple / Set)
    and *keyword* values; nested Calls / Lambdas / Comprehensions stop the
    descent because their contents aren't being passed as plain function
    handles. This matches the pattern of every caller in the catalog and
    keeps the walker O(args) instead of O(AST)."""
    def _walk(expr):
        if isinstance(expr, ast.Name):
            yield expr
            return
        if isinstance(expr, ast.Dict):
            # Both keys (Name-as-key is rare but exists) and values.
            for k in expr.keys:
                if k is not None:
                    yield from _walk(k)
            for v in expr.values:
                yield from _walk(v)
            return
        if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
            for elt in expr.elts:
                yield from _walk(elt)
            return
        # Anything else (Call, Lambda, Subscript, ...) is opaque — don't
        # descend. The function reference, if any, isn't being passed as a
        # plain handle.

    for arg in node.args:
        yield from _walk(arg)
    for kw in node.keywords:
        yield from _walk(kw.value)


class _FeatureCollector(ast.NodeVisitor):
    """Walk a function's body and accumulate features. Recurses into
    same-module helper calls to flatten the call graph."""

    def __init__(
        self,
        module_funcs: dict[str, ast.FunctionDef],
        bag: FeatureBag,
        visited: set[str],
        modal_helpers: frozenset[str],
        filter_factories: frozenset[str],
        novel_helpers: frozenset[str],
        function_accepting_helpers: frozenset[str] = frozenset(),
        bundle_features: Optional[dict] = None,
    ):
        self.module_funcs = module_funcs
        self.bag = bag
        self.visited = visited
        self.modal_helpers = modal_helpers
        self.filter_factories = filter_factories
        self.novel_helpers = novel_helpers
        # Slice 7B: function-accepting helpers (saga chapters, granted abilities)
        # where effect_fns are passed as values inside dicts/lists/kwargs.
        self.function_accepting_helpers = function_accepting_helpers
        # Slice 7A: bundle helpers from other modules (ability_bundles.py).
        # AST walker can't descend across imports, so inject pre-declared
        # feature contributions on name match.
        self.bundle_features = bundle_features or {}

    def visit_Call(self, node: ast.Call) -> None:
        self.bag.raw_call_count += 1
        name = _name_of_call(node.func)
        if name:
            # Skip builtins and a few engine constructors for clarity.
            if name not in _NEVER_DESCEND:
                self.bag.helpers_called.add(name)
            # Recognize known helper categories.
            if name in self.modal_helpers:
                self.bag.modal_calls.add(name)
            if name in self.filter_factories:
                self.bag.filter_factory_calls.add(name)
            if name in self.novel_helpers:
                self.bag.novel_helper_calls.add(name)
            # Inject bundle features for known cross-module helpers (the
            # walker can't descend into ability_bundles.py so we declare the
            # bundle's effect contribution upfront — see EngineProfile docs).
            if name in self.bundle_features:
                bf = self.bundle_features[name]
                self.bag.event_types |= bf.get("event_types", frozenset())
                self.bag.state_attrs |= bf.get("state_attrs", frozenset())
                self.bag.zones_accessed |= bf.get("zones_accessed", frozenset())
                if bf.get("cross_controller"):
                    self.bag.cross_controller = True
                self.bag.modal_calls |= bf.get("modal_calls", frozenset())
                self.bag.filter_factory_calls |= bf.get("filter_factory_calls", frozenset())
                self.bag.novel_helper_calls |= bf.get("novel_helper_calls", frozenset())
            # Detect zone access: state.zones.get(...) — name is "get", func.value.attr is "zones".
            if (
                name == "get"
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "zones"
                and node.args
            ):
                zone = _zone_prefix_from_fstring(node.args[0])
                if zone:
                    self.bag.zones_accessed.add(zone)
            # Recurse into local helpers (same-module top-level defs).
            if name in self.module_funcs and name not in self.visited and name not in _NEVER_DESCEND:
                self.visited.add(name)
                inner_func = self.module_funcs[name]
                inner = _FeatureCollector(
                    self.module_funcs, self.bag, self.visited,
                    self.modal_helpers, self.filter_factories, self.novel_helpers,
                    function_accepting_helpers=self.function_accepting_helpers,
                    bundle_features=self.bundle_features,
                )
                inner.generic_visit(inner_func)
            # Slice 7B: function-arg descent. When the call site is a known
            # function-accepting helper, scan args for Name nodes that
            # resolve to module-level function defs and walk into them.
            # This surfaces saga chapter handlers, granted-ability effect_fns,
            # and similar callbacks the scorer would otherwise miss.
            if name in self.function_accepting_helpers:
                for name_node in _iter_name_args(node):
                    fn_name = name_node.id
                    if fn_name in self.module_funcs and fn_name not in self.visited:
                        self.visited.add(fn_name)
                        inner_func = self.module_funcs[fn_name]
                        inner = _FeatureCollector(
                            self.module_funcs, self.bag, self.visited,
                            self.modal_helpers, self.filter_factories,
                            self.novel_helpers,
                            function_accepting_helpers=self.function_accepting_helpers,
                        )
                        inner.generic_visit(inner_func)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # state.X
        if isinstance(node.value, ast.Name) and node.value.id == "state":
            self.bag.state_attrs.add(node.attr)
        # <var>.state.X  — direct read or write of a GameObject's state, e.g.
        # `target.state.damage_counters` or `attacker.state.is_paralyzed`.
        # Critical for Pokemon cards which mutate state via attached objects.
        if isinstance(node.value, ast.Attribute) and node.value.attr == "state":
            self.bag.state_attrs.add(node.attr)
        # EventType.X
        if isinstance(node.value, ast.Name) and node.value.id == "EventType":
            self.bag.event_types.add(node.attr)
        # ZoneType.X — extract zone name in lowercase for matching against profiles
        if _is_zonetype_attr(node):
            self.bag.zones_accessed.add(node.attr.lower())
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        # Detect `<x> != attacker.controller` or `<x> != obj.controller`
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.NotEq, ast.Eq)):
                if _refers_to_controller(comparator) or _refers_to_controller(node.left):
                    if isinstance(op, ast.NotEq):
                        self.bag.cross_controller = True
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        # Detect `next((p for p in state.players if p != attacker.controller), None)`
        for gen in node.generators:
            if (
                isinstance(gen.iter, ast.Attribute)
                and isinstance(gen.iter.value, ast.Name)
                and gen.iter.value.id == "state"
                and gen.iter.attr == "players"
            ):
                self.bag.opponent_iteration = True
                self.bag.cross_controller = True
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.bag.has_for_loop = True
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.bag.has_branch = True
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.bag.has_branch = True
        self.generic_visit(node)


def _is_trivially_empty(fdef: ast.FunctionDef) -> bool:
    """True if body is just `return []` or `return None` (possibly with docstring)."""
    body = list(fdef.body)
    # Skip docstring
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return True
    if len(body) == 1 and isinstance(body[0], ast.Return):
        ret = body[0].value
        if ret is None:
            return True
        if isinstance(ret, ast.Constant) and ret.value is None:
            return True
        if isinstance(ret, ast.List) and not ret.elts:
            return True
    return False


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


def _extract_callables(
    val,
    out: list,
    visited: set[int],
    _depth: int = 0,
) -> None:
    """Recursively unpack a closure value, appending any reachable function
    callables to ``out``. Stops at depth 3 to bound work and tracks identity
    to avoid cycles.

    Used by the closure walker (slice 7B) so that captured *spec lists* like
    ``granted_activated_abilities=[{'effect_fn': fn}, ...]`` surface the
    per-card ``effect_fn`` to the AST walker. Without this, every Equipment
    with granted abilities collapsed to a single fingerprint because the
    closure walker only sees the captured container, not the function
    references inside.
    """
    if val is None or _depth > 3:
        return
    if callable(val) and hasattr(val, '__name__'):
        # Skip type/class callables (e.g. dict, str, int captured as defaults)
        # — they would just lead the walker into builtins. Functions and
        # bound methods have callable __code__ which classes don't.
        if isinstance(val, type):
            return
        vid = id(val)
        if vid not in visited:
            out.append(val)
        return
    if isinstance(val, dict):
        for v in val.values():
            _extract_callables(v, out, visited, _depth + 1)
        return
    if isinstance(val, (list, tuple, set, frozenset)):
        for v in val:
            _extract_callables(v, out, visited, _depth + 1)
        return
    # Primitives (int/str/bool/None) → nothing to extract.


def extract_features_from_callable(
    fn: Callable,
    modal_helpers: frozenset[str] = frozenset(),
    filter_factories: frozenset[str] = frozenset(),
    novel_helpers: frozenset[str] = frozenset(),
    cross_controller_helpers: frozenset[str] = frozenset(),
    function_accepting_helpers: frozenset[str] = frozenset(),
    bundle_features: Optional[dict] = None,
    _closure_depth: int = 0,
    _closure_visited: Optional[set[int]] = None,
) -> FeatureBag:
    """Parse `fn`'s source module, walk its AST, return a FeatureBag.

    `modal_helpers`, `filter_factories`, `novel_helpers` come from the
    engine profile and tag specific call sites for axis scoring.

    `cross_controller_helpers` is the set of helper names whose call
    implies cross-controller interaction (the `!=` comparator lives in
    a different module the walker doesn't descend into). Any call site
    matching this set flips `bag.cross_controller=True` post-walk.

    `bundle_features` is the cross-module helper feature-injection map
    (e.g. for `ability_bundles.etb_gain_life(...)` → inject LIFE_CHANGE
    and `life` state-attr). The walker can't descend into a different
    module's source but it CAN see the call name, so we declare each
    bundle helper's contribution upfront in the engine profile and
    inject it on a name match. Surfaced by DBZ slice-4 agent 2026-05-19:
    cards built via v1 bundle helpers scored zero on all axes.

    Closure-walking (gotcha #19 from spice-pass.md): when `fn` is a
    closure produced by a wrapper-factory like `_pass5_compose_setup`,
    its AST body only mentions the captured names (`old_setup(...)`,
    `added_setup(...)`) — it has no visibility into the wrapped functions.
    To surface the real mechanical diversity, this function also walks
    callables captured in `fn`'s closure cells via `inspect.getclosurevars`
    and merges their FeatureBags into the wrapper's. Depth is capped at
    4 to bound recursion, and same-object identities are tracked across
    the chain to break cycles. This is the fix for PKH's 233-card
    "wired-but-wrapped" measurement gap (every Pokemon goes through
    `_pass5_compose_setup`, so without this walk every card fingerprints
    as `helpers=[]`)."""
    bag = FeatureBag()
    path, fdef, funcs = _func_source_for_callable(fn)
    if fdef is not None:
        bag.is_trivially_empty = _is_trivially_empty(fdef)
        visited: set[str] = {fn.__name__}
        collector = _FeatureCollector(
            funcs, bag, visited, modal_helpers, filter_factories, novel_helpers,
            function_accepting_helpers=function_accepting_helpers,
            bundle_features=bundle_features,
        )
        collector.generic_visit(fdef)
    # else: fn is a closure with no top-level fdef (e.g. wrapper produced by
    # a factory like `_pass5_compose_setup`). The closure walk below picks
    # up the captured wrapped functions, so we don't early-return.

    # Walk closure cells if fn is a wrapper-style closure. Bounded depth
    # so a chain of wrappers can't recurse forever, and identity-tracked
    # so cycles can't either.
    MAX_CLOSURE_DEPTH = 4
    if _closure_visited is None:
        _closure_visited = set()
    _closure_visited.add(id(fn))
    if _closure_depth < MAX_CLOSURE_DEPTH:
        try:
            closurevars = inspect.getclosurevars(fn)
            nonlocal_callables = []
            # Slice 7B: in addition to direct-callable nonlocals, unpack
            # container nonlocals (list/tuple/dict/set) one level so closures
            # that captured a *spec* like `granted_activated_abilities=[{
            # 'effect_fn': fn}]` surface the per-card effect_fn. The walker
            # previously only saw the shared listener machinery and every
            # Equipment with granted abilities collapsed to fingerprint
            # ababd2c75e63 regardless of its actual per-card effect.
            for val in closurevars.nonlocals.values():
                _extract_callables(val, nonlocal_callables, _closure_visited)
        except (TypeError, ValueError):
            nonlocal_callables = []
        # Track the number of closure-walked callables — if any are
        # non-trivial we override the initial is_trivially_empty default.
        walked_any = False
        for inner_fn in nonlocal_callables:
            inner_bag = extract_features_from_callable(
                inner_fn,
                modal_helpers=modal_helpers,
                filter_factories=filter_factories,
                novel_helpers=novel_helpers,
                cross_controller_helpers=cross_controller_helpers,
                function_accepting_helpers=function_accepting_helpers,
                bundle_features=bundle_features,
                _closure_depth=_closure_depth + 1,
                _closure_visited=_closure_visited,
            )
            bag.merge(inner_bag)
            walked_any = True
        # If fdef was None (closure wrapper) AND we walked at least one
        # non-empty captured callable, the merged bag is no longer
        # "trivially empty" — flip to False to reflect the captured logic.
        if fdef is None and walked_any:
            bag.is_trivially_empty = bag.is_trivially_empty  # merge already
            # handled the conjunction; nothing to override here. The default
            # FeatureBag value is False so the bag arrives with the merged
            # value already set correctly. (Kept this block for the comment.)

    if cross_controller_helpers and bag.helpers_called & cross_controller_helpers:
        bag.cross_controller = True
    return bag
