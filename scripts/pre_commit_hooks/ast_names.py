"""Small syntax-only helpers for resolving imported Python names."""

from __future__ import annotations

from ast import (
    AST,
    AnnAssign,
    Assign,
    AsyncFunctionDef,
    Attribute,
    ClassDef,
    FunctionDef,
    Import,
    ImportFrom,
    Lambda,
    Module,
    Name,
    NamedExpr,
    iter_child_nodes,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection
    from typing import Protocol

    class NameResolver(Protocol):
        """Resolve dotted-name candidates for an AST expression."""

        def __call__(self, node: AST) -> Collection[tuple[str, ...]]:
            """Return dotted-name candidates for the expression."""


def dotted_name(node: AST) -> tuple[str, ...] | None:
    """Return the components of a dotted name or attribute expression.

    Args:
        node: Expression to inspect.

    Returns:
        Dotted name components, or ``None`` for another expression type.
    """
    if isinstance(node, Name):
        return (node.id,)
    if isinstance(node, Attribute) and (parent := dotted_name(node=node.value)) is not None:
        return (*parent, node.attr)
    return None


def resolve_syntax(node: AST, bindings: dict[str, tuple[str, ...]]) -> tuple[str, ...] | None:
    """Resolve a dotted expression through simple module-level bindings.

    Args:
        node: Name or attribute expression to resolve.
        bindings: Local names mapped to imported or aliased names.

    Returns:
        Resolved name components, or ``None`` for another expression type.
    """
    name = dotted_name(node=node)
    if name is None:
        return None
    root, *suffix = name
    return (*bindings.get(root, (root,)), *suffix)


def walrus_bound_names(node: AST) -> frozenset[str]:
    """Return names bound by walrus operators in the node's own scope.

    Assignment expressions bind in their containing scope, so walrus targets
    nested inside functions, lambdas, or class bodies are local to those
    scopes and are excluded.

    Args:
        node: Statement or expression to scan.

    Returns:
        Names bound at the node's own scope level by ``:=`` operators.
    """
    names: set[str] = set()
    if isinstance(node, NamedExpr) and isinstance(node.target, Name):
        names.add(node.target.id)
    for child in iter_child_nodes(node):
        if isinstance(child, (AsyncFunctionDef, ClassDef, FunctionDef, Lambda)):
            continue
        names.update(walrus_bound_names(node=child))
    return frozenset(names)


def import_bindings(tree: Module) -> dict[str, tuple[str, ...]]:
    """Return absolute top-level import bindings from a module AST.

    Args:
        tree: Parsed Python module.

    Returns:
        Local import names mapped to absolute dotted names.
    """
    bindings: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if isinstance(node, Import):
            for imported in node.names:
                local_name = imported.asname or imported.name.split(sep=".", maxsplit=1)[0]
                bindings[local_name] = tuple(imported.name.split(sep=".")) if imported.asname else (local_name,)
        elif isinstance(node, ImportFrom) and node.level == 0 and node.module:
            for imported in node.names:
                if imported.name != "*":
                    bindings[imported.asname or imported.name] = (*node.module.split(sep="."), imported.name)
    return bindings


def simple_name_resolver(tree: Module) -> NameResolver:
    """Build a resolver for imports, assignment aliases, and local classes.

    Args:
        tree: Parsed Python module.

    Returns:
        A syntax-only dotted-name resolver.
    """
    bindings = import_bindings(tree=tree)
    for node in tree.body:
        if isinstance(node, (Assign, AnnAssign)):
            value = node.value
            resolved = resolve_syntax(node=value, bindings=bindings) if value is not None else None
            targets = node.targets if isinstance(node, Assign) else [node.target]
            for target in targets:
                if isinstance(target, Name):
                    if resolved is None:
                        bindings.pop(target.id, None)
                    else:
                        bindings[target.id] = resolved
        elif isinstance(node, ClassDef):
            bindings[node.name] = (node.name,)
        elif isinstance(node, (FunctionDef, AsyncFunctionDef)):
            bindings.pop(node.name, None)

    def resolve(node: AST) -> frozenset[tuple[str, ...]]:
        resolved = resolve_syntax(node=node, bindings=bindings)
        return frozenset({resolved}) if resolved is not None else frozenset()

    return resolve
