"""Check explicit clients for OpenShift resource operations."""

from __future__ import annotations

from ast import (
    AST,
    AnnAssign,
    Assign,
    AsyncFunctionDef,
    Call,
    ClassDef,
    Constant,
    FunctionDef,
    Import,
    ImportFrom,
    Module,
    Name,
    dump,
    iter_child_nodes,
    parse,
    stmt,
    walk,
)
from collections import Counter
from dataclasses import dataclass
from importlib.util import find_spec
from io import StringIO
from pathlib import Path
from tokenize import COMMENT, OP, TokenInfo, generate_tokens
from typing import TYPE_CHECKING

from scripts.pre_commit_hooks.ast_names import import_bindings, resolve_syntax, simple_name_resolver
from scripts.pre_commit_hooks.policy_types import PolicyViolation

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator, Sequence
    from typing import Protocol

    from scripts.pre_commit_hooks.ast_names import NameResolver

    NodeOrDependencyAdded = Callable[[AST, AST], bool]

    class SourceReader(Protocol):
        """Read staged module source by dotted module name."""

        def __call__(self, module_name: tuple[str, ...]) -> str | None:
            """Return staged source for the module, or None when absent."""


_RESOURCE_BASES = {
    ("ocp_resources", "resource", "Resource"),
    ("ocp_resources", "resource", "NamespacedResource"),
}
_LOCAL_ROOTS = frozenset({"libs", "tests", "utilities"})
_CACHE_ADMIN_CLIENT = ("utilities", "cluster", "cache_admin_client")
_CACHE_COMMENT_MESSAGE = (
    "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
    "cache_admin_client() is required at this call site"
)


@dataclass(frozen=True, slots=True)
class _ClassRecord:
    qualified_name: tuple[str, ...]
    bases: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class _SourceComment:
    line: int
    column: int
    text: str
    comment_only: bool


def _relative_import_prefixes(module_name: tuple[str, ...], node: ImportFrom) -> tuple[tuple[str, ...], ...]:
    suffix = tuple(node.module.split(sep=".")) if node.module else ()
    package_prefix = module_name[: max(0, len(module_name) - node.level + 1)]
    module_prefix = module_name[: max(0, len(module_name) - node.level)]
    return tuple(dict.fromkeys(((*package_prefix, *suffix), (*module_prefix, *suffix))))


def _nested_statements(node: AST) -> Iterator[stmt]:
    for child in iter_child_nodes(node):
        if isinstance(child, stmt):
            yield child
            if isinstance(child, (ClassDef, FunctionDef, AsyncFunctionDef)):
                continue
        yield from _nested_statements(node=child)


def _scope_statements(statements: Sequence[stmt]) -> tuple[stmt, ...]:
    collected: list[stmt] = []
    for statement in statements:
        collected.append(statement)
        if not isinstance(statement, (ClassDef, FunctionDef, AsyncFunctionDef)):
            collected.extend(_nested_statements(node=statement))
    return tuple(collected)


def _resolved_candidates(
    node: AST,
    bindings: dict[str, tuple[str, ...]],
    binding_candidates: dict[str, tuple[tuple[str, ...], ...]],
) -> tuple[tuple[str, ...], ...]:
    resolved = resolve_syntax(node=node, bindings=bindings)
    if resolved is None:
        return ()
    for name, candidates in binding_candidates.items():
        binding = bindings.get(name)
        if binding:
            binding_length = len(binding)
            if resolved[:binding_length] == binding:
                suffix = resolved[binding_length:]
                return tuple((*candidate, *suffix) for candidate in candidates)
    return (resolved,)


def _class_records(module_name: tuple[str, ...], source: str) -> tuple[_ClassRecord, ...]:
    tree = parse(source=source)
    statements = _scope_statements(statements=tree.body)
    bindings = import_bindings(tree=tree)
    binding_candidates: dict[str, tuple[tuple[str, ...], ...]] = {
        name: (binding,) for name, binding in bindings.items()
    }
    local_classes = {node.name for node in statements if isinstance(node, ClassDef)}
    records: list[_ClassRecord] = []
    for node in statements:
        if isinstance(node, Import):
            for imported in node.names:
                imported_name = tuple(imported.name.split(sep="."))
                bound_name = imported.asname or imported_name[0]
                binding = imported_name if imported.asname else imported_name[:1]
                bindings[bound_name] = binding
                binding_candidates[bound_name] = (binding,)
            continue
        if isinstance(node, ImportFrom):
            imported_prefixes = (
                (tuple(node.module.split(sep=".")),)
                if node.level == 0 and node.module
                else _relative_import_prefixes(module_name=module_name, node=node)
            )
            for imported in node.names:
                if imported.name != "*":
                    imported_bases = tuple((*prefix, imported.name) for prefix in imported_prefixes)
                    bound_name = imported.asname or imported.name
                    records.append(
                        _ClassRecord(
                            qualified_name=(*module_name, bound_name),
                            bases=imported_bases,
                        )
                    )
                    if imported_bases:
                        bindings[bound_name] = imported_bases[0]
                        binding_candidates[bound_name] = imported_bases
            continue
        if isinstance(node, (Assign, AnnAssign)):
            value = node.value
            resolved = (
                _resolved_candidates(node=value, bindings=bindings, binding_candidates=binding_candidates)
                if value is not None
                else ()
            )
            targets = node.targets if isinstance(node, Assign) else [node.target]
            for target in targets:
                if isinstance(target, Name) and resolved:
                    bindings[target.id] = resolved[0]
                    binding_candidates[target.id] = resolved
                    records.append(
                        _ClassRecord(
                            qualified_name=(*module_name, target.id),
                            bases=resolved,
                        )
                    )
            continue
        if not isinstance(node, ClassDef):
            continue
        bases: list[tuple[str, ...]] = []
        for base in node.bases:
            resolved = _resolved_candidates(node=base, bindings=bindings, binding_candidates=binding_candidates)
            for candidate in resolved:
                if len(candidate) == 1 and candidate[0] in local_classes:
                    candidate = (*module_name, *candidate)
                bases.append(candidate)
        records.append(_ClassRecord(qualified_name=(*module_name, node.name), bases=tuple(bases)))
        bindings[node.name] = (*module_name, node.name)
        binding_candidates[node.name] = (bindings[node.name],)
    return tuple(records)


def _module_name(path: Path, root: Path, prefix: tuple[str, ...] = ()) -> tuple[str, ...]:
    parts = path.relative_to(root).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return (*prefix, *parts)


def _records_under(root: Path, prefix: tuple[str, ...] = ()) -> list[_ClassRecord]:
    records: list[_ClassRecord] = []
    if not root.is_dir():
        return records
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "class " not in source:
            continue
        records.extend(
            _class_records(
                module_name=_module_name(path=path, root=root, prefix=prefix),
                source=source,
            )
        )
    return records


def _dependency_root() -> Path:
    spec = find_spec("ocp_resources")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("resource-clients: installed ocp_resources source could not be located")
    return Path(next(iter(spec.submodule_search_locations)))


def imported_module_names(
    tree: Module,
    module_name: tuple[str, ...] = (),
) -> frozenset[tuple[str, ...]]:
    """Return absolute modules imported by source represented by ``tree``.

    Args:
        tree: Parsed Python module.
        module_name: Absolute module name of ``tree``, used to resolve
            relative imports to their absolute candidate module names.

    Returns:
        Imported module names; relative imports are resolved to their
        absolute candidate module names rather than excluded.
    """
    modules: set[tuple[str, ...]] = set()
    for node in _scope_statements(statements=tree.body):
        if isinstance(node, Import):
            modules.update(tuple(imported.name.split(sep=".")) for imported in node.names)
        elif isinstance(node, ImportFrom):
            imported_prefixes = (
                (tuple(node.module.split(sep=".")),)
                if node.level == 0 and node.module
                else _relative_import_prefixes(module_name=module_name, node=node)
            )
            for imported_prefix in imported_prefixes:
                modules.add(imported_prefix)
                modules.update((*imported_prefix, imported.name) for imported in node.names if imported.name != "*")
    return frozenset(modules)


def _targeted_local_records(
    module_names: Collection[tuple[str, ...]],
    source_reader: SourceReader,
) -> list[_ClassRecord]:
    records: list[_ClassRecord] = []
    pending = [name for name in module_names if name and name[0] in _LOCAL_ROOTS]
    visited: set[tuple[str, ...]] = set()
    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        visited.add(module_name)
        source = source_reader(module_name=module_name)
        if source is None:
            continue
        source_tree = parse(source=source)
        module_records = _class_records(module_name=module_name, source=source)
        records.extend(module_records)
        pending.extend(
            imported_name
            for imported_name in imported_module_names(tree=source_tree, module_name=module_name)
            if imported_name and imported_name[0] in _LOCAL_ROOTS and imported_name not in visited
        )
        for record in module_records:
            pending.extend(
                base[:-1]
                for base in record.bases
                if len(base) > 1 and base[0] in _LOCAL_ROOTS and base[:-1] not in visited
            )
    return records


def _resource_closure(records: Collection[_ClassRecord]) -> frozenset[tuple[str, ...]]:
    resources: set[tuple[str, ...]] = set(_RESOURCE_BASES)
    changed = True
    while changed:
        changed = False
        for record in records:
            if record.qualified_name not in resources and any(base in resources for base in record.bases):
                resources.add(record.qualified_name)
                changed = True
    return frozenset(resources)


def discover_resource_classes(
    repository_root: Path = Path("."),
    *,
    source_reader: SourceReader | None = None,
    module_names: Collection[tuple[str, ...]] | None = None,
) -> frozenset[tuple[str, ...]]:
    """Discover dependency and local ``Resource`` subclasses from source only.

    Project modules are parsed, never imported. By default local roots are
    scanned for direct API compatibility. Integrated checks can provide an
    index-backed reader and imported module names to inspect only relevant
    local inheritance chains.

    Args:
        repository_root: Root used by the compatibility full-source scan.
        source_reader: Optional staged-snapshot module source reader.
        module_names: Local modules to inspect with ``source_reader``.

    Returns:
        Fully qualified names of statically discovered Resource subclasses.
    """
    dependency_root = _dependency_root()
    records = _records_under(root=dependency_root, prefix=("ocp_resources",))
    if source_reader is not None and module_names is not None:
        records.extend(_targeted_local_records(module_names=module_names, source_reader=source_reader))
    else:
        resolved_root = repository_root.resolve()
        for local_root_name in _LOCAL_ROOTS:
            records.extend(_records_under(root=resolved_root / local_root_name, prefix=(local_root_name,)))
    return _resource_closure(records=records)


def _local_resource_classes(
    tree: Module,
    resolve_name: NameResolver,
    known_resources: Collection[tuple[str, ...]],
) -> frozenset[tuple[str, ...]]:
    resources = set(known_resources)
    local: set[tuple[str, ...]] = set()
    changed = True
    while changed:
        changed = False
        for node in _scope_statements(statements=tree.body):
            if not isinstance(node, ClassDef):
                continue
            local_name = ("<local>", node.name)
            if local_name in local:
                continue
            if any(set(resolve_name(node=base)) & (resources | local) for base in node.bases):
                local.add(local_name)
                changed = True
    return frozenset(local)


def _has_explicit_client(node: Call) -> bool:
    return any(
        keyword.arg == "client" and not (isinstance(keyword.value, Constant) and keyword.value.value is None)
        for keyword in node.keywords
    )


def _intersects(node: AST, added_lines: Collection[int] | None) -> bool:
    if added_lines is None:
        return True
    start_line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", start_line)
    return (
        start_line is not None and end_line is not None and any(start_line <= line <= end_line for line in added_lines)
    )


def _source_layout(source: str) -> tuple[tuple[_SourceComment, ...], tuple[TokenInfo, ...]]:
    tokens = tuple(generate_tokens(readline=StringIO(source).readline))
    comments = tuple(
        _SourceComment(
            line=token.start[0],
            column=token.start[1],
            text=token.string.lstrip("#").strip(),
            comment_only=not token.line[: token.start[1]].strip(),
        )
        for token in tokens
        if token.type == COMMENT
    )
    return comments, tokens


def _containing_statement(call: Call, parents: dict[AST, AST]) -> AST:
    current: AST = call
    while current in parents:
        current = parents[current]
        if isinstance(current, stmt):
            return current
    return call


def _statement_header(statement: AST, tokens: tuple[TokenInfo, ...]) -> tuple[int, int, int | None]:
    decorators = getattr(statement, "decorator_list", ())
    start = min((decorator.lineno for decorator in decorators), default=getattr(statement, "lineno", 0))
    body = getattr(statement, "body", None)
    if not isinstance(body, list):
        return start, getattr(statement, "end_lineno", start) or start, None

    statement_position = (getattr(statement, "lineno", start), getattr(statement, "col_offset", 0))
    depth = 0
    for token in tokens:
        if token.start < statement_position:
            continue
        if token.type == OP:
            if token.string in "([{":
                depth += 1
            elif token.string in ")]}":
                depth -= 1
            elif token.string == ":" and depth == 0:
                body_on_header_line = any(getattr(child, "lineno", -1) == token.start[0] for child in body)
                return start, token.start[0], token.end[1] if body_on_header_line else None
    return start, getattr(statement, "lineno", start), None


def _has_explanatory_comment(
    call: Call,
    source_comments: tuple[_SourceComment, ...],
    tokens: tuple[TokenInfo, ...],
    parents: dict[AST, AST],
) -> bool:
    statement = _containing_statement(call=call, parents=parents)
    start, end, end_column = _statement_header(statement=statement, tokens=tokens)
    return any(
        comment.text
        and (
            (comment.comment_only and comment.line == start - 1)
            or (
                start <= comment.line <= end
                and (comment.line < end or end_column is None or comment.column <= end_column)
            )
        )
        for comment in source_comments
    )


def _resource_call_message(
    node: Call,
    resolved_names: Collection[tuple[str, ...]],
    resources: Collection[tuple[str, ...]],
) -> str | None:
    if any(resolved_name in resources for resolved_name in resolved_names) and not _has_explicit_client(node=node):
        return "resource-clients: pass an existing non-None client= to this Resource constructor"
    if any(
        resolved_name[-1:] == ("get",) and resolved_name[:-1] in resources for resolved_name in resolved_names
    ) and not _has_explicit_client(node=node):
        return "resource-clients: pass an existing non-None client= to this Resource class .get()"
    return None


def _parents(tree: Module) -> dict[AST, AST]:
    return {child: parent for parent in walk(tree) for child in iter_child_nodes(parent)}


_CacheIdentity = tuple[tuple[str, ...], str, int]


def _cache_identity_base(call: Call, parents: dict[AST, AST]) -> tuple[tuple[str, ...], str]:
    owners: list[str] = []
    current: AST = call
    while current in parents:
        current = parents[current]
        if isinstance(current, (ClassDef, FunctionDef, AsyncFunctionDef)):
            owners.append(current.name)
    return tuple(reversed(owners)), dump(node=call, annotate_fields=True, include_attributes=False)


def _cache_identities(
    tree: Module,
    resolver: NameResolver,
    parents: dict[AST, AST],
) -> dict[Call, _CacheIdentity]:
    occurrences: Counter[tuple[tuple[str, ...], str]] = Counter()
    identities: dict[Call, _CacheIdentity] = {}
    for node in walk(tree):
        if not isinstance(node, Call) or _CACHE_ADMIN_CLIENT not in resolver(node=node.func):
            continue
        base = _cache_identity_base(call=node, parents=parents)
        occurrences[base] += 1
        identities[node] = (*base, occurrences[base])
    return identities


def _undocumented_cache_calls(
    source: str,
    tree: Module | None = None,
    resolve_name: NameResolver | None = None,
) -> Counter[_CacheIdentity]:
    source_tree = tree or parse(source=source)
    resolver = resolve_name or simple_name_resolver(tree=source_tree)
    parents = _parents(tree=source_tree)
    identities = _cache_identities(tree=source_tree, resolver=resolver, parents=parents)
    source_comments, tokens = _source_layout(source=source)
    return Counter(
        identity
        for node, identity in identities.items()
        if not _has_explanatory_comment(
            call=node,
            source_comments=source_comments,
            tokens=tokens,
            parents=parents,
        )
    )


def check_resource_clients(
    file_path: Path,
    source: str,
    added_lines: Collection[int] | None = None,
    resolve_name: NameResolver | None = None,
    repository_root: Path = Path("."),
    *,
    head_source: str | None = None,
    head_tree: Module | None = None,
    head_resolve_name: NameResolver | None = None,
    tree: Module | None = None,
    known_resources: Collection[tuple[str, ...]] | None = None,
    node_or_dependency_added: NodeOrDependencyAdded | None = None,
) -> list[PolicyViolation]:
    """Check changed Resource calls and cache-client explanations.

    Args:
        file_path: Repository-relative path used in violations.
        source: Current source, normally read from the Git index.
        added_lines: Added source lines, or ``None`` to inspect all calls.
        resolve_name: Optional scope-aware resolver for current source.
        repository_root: Root for compatibility Resource discovery.
        head_source: Source from ``HEAD`` used to detect comment-only removals.
        head_tree: Optional pre-parsed ``HEAD`` source.
        head_resolve_name: Optional scope-aware resolver for ``HEAD`` source.
        tree: Optional pre-parsed current source.
        known_resources: Optional Resource classes discovered for this snapshot.
        node_or_dependency_added: Optional callback that detects additions to a call or its resolved dependency.

    Returns:
        Resource-client and cache-comment violations ordered by location.
    """
    source_tree = tree or parse(source=source, filename=str(file_path))
    resolver = resolve_name or simple_name_resolver(tree=source_tree)
    resources = set(
        discover_resource_classes(repository_root=repository_root) if known_resources is None else known_resources
    )
    resources.update(_local_resource_classes(tree=source_tree, resolve_name=resolver, known_resources=resources))
    parents = _parents(tree=source_tree)
    source_comments, tokens = _source_layout(source=source)
    cache_identities = _cache_identities(tree=source_tree, resolver=resolver, parents=parents)
    legacy_undocumented = (
        _undocumented_cache_calls(source=head_source, tree=head_tree, resolve_name=head_resolve_name)
        if head_source is not None
        else Counter()
    )
    violations: list[PolicyViolation] = []
    for node in walk(source_tree):
        if not isinstance(node, Call):
            continue
        resolved_names = resolver(node=node.func)
        resource_call_added = (
            node_or_dependency_added(node, node.func)
            if node_or_dependency_added is not None
            else _intersects(node=node, added_lines=added_lines)
        )
        if resource_call_added:
            message = _resource_call_message(node=node, resolved_names=resolved_names, resources=resources)
            if message:
                violations.append(PolicyViolation(file_path=file_path, line_number=node.lineno, message=message))
        if _CACHE_ADMIN_CLIENT not in resolved_names or _has_explanatory_comment(
            call=node,
            source_comments=source_comments,
            tokens=tokens,
            parents=parents,
        ):
            continue
        identity = cache_identities[node]
        if not _intersects(node=node, added_lines=added_lines) and legacy_undocumented[identity]:
            legacy_undocumented[identity] -= 1
            continue
        violations.append(PolicyViolation(file_path=file_path, line_number=node.lineno, message=_CACHE_COMMENT_MESSAGE))
    return sorted(violations, key=lambda violation: (violation.line_number or 0, violation.message))
