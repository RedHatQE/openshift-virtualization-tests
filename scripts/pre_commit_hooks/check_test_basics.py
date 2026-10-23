"""Check mechanical Python-basics rules."""

from __future__ import annotations

from ast import (
    AST,
    Add,
    AnnAssign,
    Assert,
    Assign,
    AsyncFor,
    AsyncFunctionDef,
    AsyncWith,
    Attribute,
    AugAssign,
    Await,
    BinOp,
    Call,
    ClassDef,
    Compare,
    Constant,
    Delete,
    DictComp,
    Eq,
    For,
    FormattedValue,
    FunctionDef,
    GeneratorExp,
    If,
    ImportFrom,
    JoinedStr,
    List,
    ListComp,
    Load,
    Match,
    Module,
    Name,
    NotEq,
    Set,
    SetComp,
    Starred,
    Try,
    TryStar,
    Tuple,
    While,
    With,
    arguments,
    expr,
    iter_child_nodes,
    parse,
    stmt,
    walk,
)
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.pre_commit_hooks.ast_names import simple_name_resolver, walrus_bound_names
from scripts.pre_commit_hooks.policy_types import PolicyViolation

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Iterator

    from scripts.pre_commit_hooks.ast_names import NameResolver

    NodeOrDependencyIntersects = Callable[[AST, AST], bool]

_CHECKED_ROOTS = frozenset({"libs", "scripts", "tests", "utilities"})
_RELATIVE_IMPORT_MESSAGE = "relative imports are forbidden; use absolute imports"
_ASYNC_FUNCTION_MESSAGE = "test-basics: async functions are forbidden; use synchronous code"
_ASYNC_COMPREHENSION_MESSAGE = "test-basics: async comprehensions are forbidden; use a synchronous comprehension"
_AWAIT_MESSAGE = "test-basics: await is forbidden; use synchronous code"
_ASYNC_FOR_MESSAGE = "test-basics: async for is forbidden; use a synchronous loop"
_ASYNC_WITH_MESSAGE = "test-basics: async with is forbidden; use a synchronous context manager"
_UNKNOWN_CONSTANT = object()
_MAX_CONSTANT_DEPTH = 12
_MAX_CONSTANT_STRING_LENGTH = 4_096
_MAX_CONSTANT_INTEGER_BITS = 256
# Markers that require @pytest.mark.special_infra per AGENTS.md ("special_infra
# marker REQUIRED for special hardware/configuration"). Keep in sync with the
# AGENTS.md list and pytest.ini marker definitions.
_SPECIAL_INFRA_REQUIRED_MARKERS = frozenset({
    "gpu",
    "sriov",
    "bgp",
    "ibm_bare_metal",
    "dpdk",
    "swap",
    "cpu_manager",
    "numa",
    "hugepages",
    "jumbo_frame",
    "rwx_default_storage",
    "descheduler",
    "high_resource_vm",
})
_SPECIAL_INFRA_MESSAGE = (
    "test-basics: marker {marker} requires @pytest.mark.special_infra at module, class, or test level"
)


def _resolve_constant_expression(node: AST, depth: int = 0) -> object:
    if depth > _MAX_CONSTANT_DEPTH:
        return _UNKNOWN_CONSTANT
    if isinstance(node, Constant):
        value = node.value
        if isinstance(value, (bytes, str)) and len(value) > _MAX_CONSTANT_STRING_LENGTH:
            return _UNKNOWN_CONSTANT
        if type(value) is int and value.bit_length() > _MAX_CONSTANT_INTEGER_BITS:
            return _UNKNOWN_CONSTANT
        return value
    if isinstance(node, BinOp) and isinstance(node.op, Add):
        left = _resolve_constant_expression(node=node.left, depth=depth + 1)
        right = _resolve_constant_expression(node=node.right, depth=depth + 1)
        if isinstance(left, str) and isinstance(right, str):
            if len(left) + len(right) > _MAX_CONSTANT_STRING_LENGTH:
                return _UNKNOWN_CONSTANT
            return left + right
        if type(left) is int and type(right) is int:
            result = left + right
            return result if result.bit_length() <= _MAX_CONSTANT_INTEGER_BITS else _UNKNOWN_CONSTANT
        return _UNKNOWN_CONSTANT
    if isinstance(node, FormattedValue):
        if node.conversion != -1 or node.format_spec is not None:
            return _UNKNOWN_CONSTANT
        constant_value = _resolve_constant_expression(node=node.value, depth=depth + 1)
        return constant_value if isinstance(constant_value, str) else _UNKNOWN_CONSTANT
    if isinstance(node, JoinedStr):
        values: list[str] = []
        output_length = 0
        for value_node in node.values:
            constant_value = _resolve_constant_expression(node=value_node, depth=depth + 1)
            if not isinstance(constant_value, str):
                return _UNKNOWN_CONSTANT
            output_length += len(constant_value)
            if output_length > _MAX_CONSTANT_STRING_LENGTH:
                return _UNKNOWN_CONSTANT
            values.append(constant_value)
        return "".join(values)
    return _UNKNOWN_CONSTANT


def _intersects(node: AST, added_lines: Collection[int] | None) -> bool:
    if added_lines is None:
        return True
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", start)
    return start is not None and end is not None and any(start <= line <= end for line in added_lines)


def _is_relative_dynamic_import(node: Call, resolver: NameResolver) -> bool:
    resolved_names = resolver(node=node.func)
    if ("importlib", "import_module") in resolved_names:
        module_name = (
            node.args[0]
            if node.args
            else next(
                (keyword.value for keyword in node.keywords if keyword.arg == "name"),
                None,
            )
        )
        resolved_module_name = (
            _resolve_constant_expression(node=module_name) if module_name is not None else _UNKNOWN_CONSTANT
        )
        return isinstance(resolved_module_name, str) and resolved_module_name.startswith(".")
    if not any(name in resolved_names for name in (("__import__",), ("builtins", "__import__"))):
        return False
    level = (
        node.args[4]
        if len(node.args) > 4
        else next(
            (keyword.value for keyword in node.keywords if keyword.arg == "level"),
            None,
        )
    )
    resolved_level = _resolve_constant_expression(node=level) if level is not None else _UNKNOWN_CONSTANT
    return type(resolved_level) is int and resolved_level > 0


def _comparison_message(node: Compare) -> str | None:
    operands = [node.left, *node.comparators]
    for operator, left, right in zip(node.ops, operands, operands[1:]):
        if not isinstance(operator, (Eq, NotEq)):
            continue
        compared = (left, right)
        if any(isinstance(operand, Constant) and operand.value is None for operand in compared):
            return "test-basics: compare None with 'is' or 'is not', not == or !="
        if any(isinstance(operand, Constant) and isinstance(operand.value, bool) for operand in compared):
            return "test-basics: use the value's implicit truthiness instead of comparing with True or False"
    return None


def _argument_annotations(node: arguments) -> Iterable[AST]:
    function_arguments = [*node.posonlyargs, *node.args, *node.kwonlyargs]
    if node.vararg is not None:
        function_arguments.append(node.vararg)
    if node.kwarg is not None:
        function_arguments.append(node.kwarg)
    return (argument.annotation for argument in function_arguments if argument.annotation is not None)


def _function_header(node: FunctionDef | AsyncFunctionDef) -> Iterable[AST]:
    yield from node.decorator_list
    yield from node.args.defaults
    yield from (default for default in node.args.kw_defaults if default is not None)
    yield from _argument_annotations(node=node.args)
    if node.returns is not None:
        yield node.returns


class _BasicsVisitor:
    def __init__(
        self,
        file_path: Path,
        added_lines: Collection[int] | None,
    ) -> None:
        self.file_path = file_path
        self.added_lines = added_lines
        self.violations: list[PolicyViolation] = []

    def _add(self, node: AST, message: str) -> None:
        self.violations.append(
            PolicyViolation(file_path=self.file_path, line_number=getattr(node, "lineno", None), message=message)
        )

    def _visit_function(self, node: FunctionDef | AsyncFunctionDef) -> None:
        for header_node in _function_header(node=node):
            self._visit(node=header_node)
        function_is_added_async = isinstance(node, AsyncFunctionDef) and (
            self.added_lines is None or node.lineno in self.added_lines
        )
        if function_is_added_async:
            self._add(node=node, message=_ASYNC_FUNCTION_MESSAGE)
            return
        for statement in node.body:
            self._visit(node=statement)

    def _visit(self, node: AST) -> None:
        if isinstance(node, (FunctionDef, AsyncFunctionDef)):
            self._visit_function(node=node)
            return
        if isinstance(node, Assert) and _intersects(node=node, added_lines=self.added_lines):
            message = _resolve_constant_expression(node=node.msg) if node.msg is not None else _UNKNOWN_CONSTANT
            if node.msg is None or (
                message is not _UNKNOWN_CONSTANT and (not isinstance(message, str) or not message.strip())
            ):
                self._add(node=node, message="test-basics: add a descriptive failure message to this assert")
        elif (
            isinstance(node, (DictComp, GeneratorExp, ListComp, SetComp))
            and any(generator.is_async for generator in node.generators)
            and _intersects(node=node, added_lines=self.added_lines)
        ):
            self._add(
                node=node,
                message=_ASYNC_COMPREHENSION_MESSAGE,
            )
        elif isinstance(node, Await) and _intersects(node=node, added_lines=self.added_lines):
            self._add(node=node, message=_AWAIT_MESSAGE)
        elif isinstance(node, AsyncFor) and (self.added_lines is None or node.lineno in self.added_lines):
            self._add(node=node, message=_ASYNC_FOR_MESSAGE)
        elif isinstance(node, AsyncWith) and (self.added_lines is None or node.lineno in self.added_lines):
            self._add(node=node, message=_ASYNC_WITH_MESSAGE)
        elif isinstance(node, Call) and _intersects(node=node, added_lines=self.added_lines):
            if (
                isinstance(node.func, Attribute)
                and isinstance(node.func.value, Name)
                and node.func.value.id == "self"
                and node.func.attr.startswith("assert")
            ):
                self._add(node=node, message="test-basics: replace unittest self.assert* with a pytest assert")
        elif (
            isinstance(node, Compare)
            and _intersects(node=node, added_lines=self.added_lines)
            and (message := _comparison_message(node=node))
        ):
            self._add(node=node, message=message)

        for child in iter_child_nodes(node):
            self._visit(node=child)

    def visit(self, tree: Module) -> None:
        """Visit a parsed source module and collect policy violations."""
        self._visit(node=tree)


def _expression_marker_chains(expression: AST, resolver: NameResolver) -> set[tuple[str, ...]]:
    """Resolve marker chains an expression applies directly and unconditionally.

    Only the decorated call target, marker-list elements, and plain marker
    references count. Conditional expressions (ternaries, boolean operators)
    and markers nested inside call arguments are not direct applications, so
    they provide no coverage (fail closed).
    """
    if isinstance(expression, Call):
        return _expression_marker_chains(expression=expression.func, resolver=resolver)
    if isinstance(expression, (List, Set, Tuple)):
        chains: set[tuple[str, ...]] = set()
        for element in expression.elts:
            chains.update(_expression_marker_chains(expression=element, resolver=resolver))
        return chains
    if isinstance(expression, Attribute) or (isinstance(expression, Name) and isinstance(expression.ctx, Load)):
        element_chains = resolver(node=expression)
        if len(element_chains) > 1:
            # A branch-dependent binding may resolve to a different marker at
            # runtime; the element provides no coverage (fail closed).
            return set()
        return set(element_chains)
    return set()


def _direct_application_nodes(expression: AST) -> Iterator[Name | Attribute]:
    """Yield nodes that directly apply markers for ``expression``.

    Mirrors :func:`_expression_marker_chains`: the decorated call target,
    marker-list elements, and plain marker references. Markers nested inside
    call arguments are data, not applications, and are not yielded.
    """
    if isinstance(expression, Call):
        yield from _direct_application_nodes(expression=expression.func)
    elif isinstance(expression, (List, Set, Tuple)):
        for element in expression.elts:
            yield from _direct_application_nodes(expression=element)
    elif isinstance(expression, Attribute) or (isinstance(expression, Name) and isinstance(expression.ctx, Load)):
        yield expression


def _has_dynamic_pytestmark_mutation(source_tree: Module, top_level: set[int]) -> bool:
    """Return whether module-scope ``pytestmark`` is dynamically mutated.

    Assignments nested in module-level control flow, walrus mutations, and
    deletion make the effective marker set ambiguous, so module ``pytestmark``
    coverage must fail closed. Function- and class-local ``pytestmark`` names
    are ordinary variables and do not affect module coverage.
    """

    def statement_mutates(statement: stmt) -> bool:
        if isinstance(statement, (AnnAssign, Assign, AugAssign)):
            targets = statement.targets if isinstance(statement, Assign) else [statement.target]
            if any("pytestmark" in _assignment_target_names(target=target) for target in targets):
                return id(statement) not in top_level
        if isinstance(statement, Delete):
            if any("pytestmark" in _assignment_target_names(target=target) for target in statement.targets):
                return True
        # Walrus targets local to nested functions, lambdas, or classes are
        # ordinary local variables; only module-scope mutations count.
        return "pytestmark" in walrus_bound_names(node=statement)

    def visit_statement(statement: stmt) -> bool:
        if isinstance(statement, (AsyncFunctionDef, ClassDef, FunctionDef)):
            return False
        if statement_mutates(statement=statement):
            return True
        if isinstance(statement, (If, While)):
            return any(visit_statement(statement=nested) for nested in [*statement.body, *statement.orelse])
        if isinstance(statement, (AsyncFor, For)):
            return any(visit_statement(statement=nested) for nested in statement.body)
        if isinstance(statement, (Try, TryStar)):
            nested_statements: list[stmt] = [*statement.body, *statement.orelse, *statement.finalbody]
            for handler in statement.handlers:
                nested_statements.extend(handler.body)
            return any(visit_statement(statement=nested) for nested in nested_statements)
        if isinstance(statement, With):
            return any(visit_statement(statement=nested) for nested in statement.body)
        if isinstance(statement, Match):
            return any(visit_statement(statement=nested) for case in statement.cases for nested in case.body)
        return False

    return any(visit_statement(statement=statement) for statement in source_tree.body)


def _scope_marker_chains(
    node: AST,
    parents: dict[AST, AST],
    source_tree: Module,
    resolver: NameResolver,
) -> set[tuple[str, ...]]:
    """Resolve the marker chains covering the scope of the given node.

    Coverage follows the AGENTS.md rule: a marker is satisfied at module,
    class, or test level. The returned chains come from the module-level
    ``pytestmark`` assignment and from the decorators of the node's enclosing
    test, class, and module scopes.

    Args:
        node: Node whose enclosing scopes are inspected.
        parents: Parent map built from the module AST.
        source_tree: Parsed Python module.
        resolver: Alias-aware AST name resolver.

    Returns:
        Resolved marker chains that apply to the node's scope.
    """
    chains: set[tuple[str, ...]] = set()
    effective_mark: AST | None = None
    augmented_marks: list[AST] = []
    top_level_mark_statements: set[int] = set()
    for statement in source_tree.body:
        if isinstance(statement, (AnnAssign, Assign, AugAssign)):
            targets = statement.targets if isinstance(statement, Assign) else [statement.target]
        else:
            continue
        if not any(isinstance(target, Name) and target.id == "pytestmark" for target in targets):
            continue
        top_level_mark_statements.add(id(statement))
        if statement.value is None:
            continue
        if isinstance(statement, AugAssign):
            # An augmented assignment extends the current marker list.
            augmented_marks.append(statement.value)
        else:
            # A later plain assignment overwrites earlier ones, including any
            # augmented extensions; only the effective value applies.
            effective_mark = statement.value
            augmented_marks = []
    if _has_dynamic_pytestmark_mutation(source_tree=source_tree, top_level=top_level_mark_statements):
        # A conditional or dynamic reassignment makes the effective module
        # marker ambiguous; fail closed and drop module pytestmark coverage.
        effective_mark = None
        augmented_marks = []
    if effective_mark is not None:
        chains.update(_expression_marker_chains(expression=effective_mark, resolver=resolver))
    for augmented_mark in augmented_marks:
        chains.update(_expression_marker_chains(expression=augmented_mark, resolver=resolver))
    scope: AST = node
    while scope is not source_tree:
        scope = parents[scope]
        if isinstance(scope, (AsyncFunctionDef, ClassDef, FunctionDef)):
            for decorator in scope.decorator_list:
                chains.update(_expression_marker_chains(expression=decorator, resolver=resolver))
    return chains


def _assignment_target_names(target: expr) -> frozenset[str]:
    """Return names bound by an assignment target, including destructuring.

    Args:
        target: Assignment target expression.

    Returns:
        Names the target binds; attribute and subscript targets bind nothing.
    """
    if isinstance(target, Name):
        return frozenset({target.id})
    if isinstance(target, Starred):
        return _assignment_target_names(target=target.value)
    if isinstance(target, (List, Tuple)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_assignment_target_names(target=element))
        return frozenset(names)
    return frozenset()


def _marker_application_expressions(source_tree: Module) -> list[AST]:
    """Collect expressions where pytest applies markers.

    Markers are applied by decorators on tests and classes and by
    module-scope ``pytestmark`` assignments (including augmented ones).
    Function-local ``pytestmark`` names are ordinary variables, and alias
    definitions such as ``sriov = pytest.mark.sriov`` are plain bindings —
    neither is an application.
    """
    expressions: list[AST] = []
    for node in walk(source_tree):
        if isinstance(node, (AsyncFunctionDef, ClassDef, FunctionDef)):
            expressions.extend(node.decorator_list)

    def visit_statement(statement: stmt) -> None:
        if isinstance(statement, (AsyncFunctionDef, ClassDef, FunctionDef)):
            # Function and class bodies are separate scopes; a local
            # ``pytestmark`` is an ordinary variable, not module metadata.
            return
        if isinstance(statement, (AnnAssign, Assign, AugAssign)):
            targets = statement.targets if isinstance(statement, Assign) else [statement.target]
            if statement.value is not None and any(
                "pytestmark" in _assignment_target_names(target=target) for target in targets
            ):
                expressions.append(statement.value)
            return
        if isinstance(statement, (If, While)):
            for nested in [*statement.body, *statement.orelse]:
                visit_statement(statement=nested)
        elif isinstance(statement, (AsyncFor, For)):
            for nested in statement.body:
                visit_statement(statement=nested)
        elif isinstance(statement, (Try, TryStar)):
            nested_statements: list[stmt] = [*statement.body, *statement.orelse, *statement.finalbody]
            for handler in statement.handlers:
                nested_statements.extend(handler.body)
            for nested in nested_statements:
                visit_statement(statement=nested)
        elif isinstance(statement, Match):
            for case in statement.cases:
                for nested in case.body:
                    visit_statement(statement=nested)
        elif isinstance(statement, With):
            for nested in statement.body:
                visit_statement(statement=nested)

    for statement in source_tree.body:
        visit_statement(statement=statement)
    return expressions


def _special_infra_violations(
    file_path: Path,
    source_tree: Module,
    resolver: NameResolver,
    added_lines: Collection[int] | None,
    dependency_intersects: NodeOrDependencyIntersects | None = None,
) -> list[PolicyViolation]:
    """Flag requirement markers added without the special_infra marker.

    Tests declaring hardware, configuration, or resource requirement markers
    (for example gpu, sriov, hugepages) must also carry
    ``@pytest.mark.special_infra`` at module, class, or test level — the
    marker must cover the requirement marker's own scope, not an unrelated
    test in the same file. Only newly added marker applications are flagged
    so legacy files can still be edited.

    Args:
        file_path: Repository-relative source path.
        source_tree: Parsed Python module.
        resolver: Alias-aware AST name resolver.
        added_lines: Added index lines, or ``None`` to inspect all markers.

    Returns:
        Violations for added requirement markers lacking special_infra.
    """
    parents = {child: parent for parent in walk(source_tree) for child in iter_child_nodes(parent)}
    intersects = dependency_intersects or (lambda node, dependency: _intersects(node=node, added_lines=added_lines))
    violations: list[PolicyViolation] = []
    for expression in _marker_application_expressions(source_tree=source_tree):
        for node in _direct_application_nodes(expression=expression):
            for chain in resolver(node=node):
                if (
                    len(chain) == 3
                    and chain[:2] == ("pytest", "mark")
                    and chain[2] in _SPECIAL_INFRA_REQUIRED_MARKERS
                    and intersects(node, node)
                ):
                    covering_chains = _scope_marker_chains(
                        node=node,
                        parents=parents,
                        source_tree=source_tree,
                        resolver=resolver,
                    )
                    if not any(covering == ("pytest", "mark", "special_infra") for covering in covering_chains):
                        violations.append(
                            PolicyViolation(
                                file_path=file_path,
                                line_number=node.lineno,
                                message=_SPECIAL_INFRA_MESSAGE.format(marker=chain[2]),
                            )
                        )
    return violations


def check_test_basics(
    file_path: Path,
    source: str,
    added_lines: Collection[int] | None = None,
    resolve_name: NameResolver | None = None,
    *,
    tree: Module | None = None,
    node_or_dependency_intersects: NodeOrDependencyIntersects | None = None,
) -> list[PolicyViolation]:
    """Check relative imports, mechanical Python basics, and test marker policy.

    Covers relative imports in all files, the scoped mechanical rules, and —
    for files under ``tests/`` — the requirement-marker policy: a newly added
    hardware/configuration/resource marker must be paired with
    ``@pytest.mark.special_infra`` covering its module, class, or test scope.
    Requirement-marker violations are filtered by added lines and by the
    bindings their application sites depend on, so changing an alias that
    supplies a marker re-checks its unchanged applications.

    Args:
        file_path: Repository-relative source path.
        source: Python source to inspect.
        added_lines: Added index lines, or ``None`` to inspect all source.
        resolve_name: Optional alias-aware AST name resolver.
        tree: Optional pre-parsed source module.
        node_or_dependency_intersects: Optional changed-line predicate for an AST
            node and the bindings on which it depends.

    Returns:
        Violations ordered by source location.
    """
    source_tree = tree or parse(source=source, filename=str(file_path))
    violations = [
        PolicyViolation(
            file_path=file_path,
            line_number=node.lineno,
            message=_RELATIVE_IMPORT_MESSAGE,
        )
        for node in walk(source_tree)
        if isinstance(node, ImportFrom) and node.level > 0 and _intersects(node=node, added_lines=added_lines)
    ]
    resolver = resolve_name or simple_name_resolver(tree=source_tree)
    if file_path.parts[:1] == ("tests",):
        violations.extend(
            _special_infra_violations(
                file_path=file_path,
                source_tree=source_tree,
                resolver=resolver,
                added_lines=added_lines,
                dependency_intersects=node_or_dependency_intersects,
            )
        )
    intersects = node_or_dependency_intersects or (
        lambda node, _dependency: _intersects(node=node, added_lines=added_lines)
    )
    violations.extend(
        PolicyViolation(file_path=file_path, line_number=node.lineno, message=_RELATIVE_IMPORT_MESSAGE)
        for node in walk(source_tree)
        if isinstance(node, Call)
        and _is_relative_dynamic_import(node=node, resolver=resolver)
        and intersects(node, node.func)
    )
    parents = {child: parent for parent in walk(source_tree) for child in iter_child_nodes(parent)}
    scope_types = (AsyncFunctionDef, ClassDef, FunctionDef, Module)

    def containing_scope(node: AST) -> AST:
        current = parents[node]
        while not isinstance(current, scope_types):
            current = parents[current]
        return current

    local_classes = [node for node in walk(source_tree) if isinstance(node, ClassDef)]
    violations.extend(
        PolicyViolation(
            file_path=file_path,
            line_number=node.lineno,
            message="test-basics: replace time.sleep() with TimeoutSampler",
        )
        for node in walk(source_tree)
        if isinstance(node, Call)
        and ("time", "sleep") in resolver(node=node.func)
        and not (
            isinstance(node.func, Attribute)
            and isinstance(node.func.value, Name)
            and any(
                local_class.name == node.func.value.id
                and containing_scope(local_class) is containing_scope(node)
                and local_class.end_lineno is not None
                and local_class.end_lineno < node.lineno
                for local_class in local_classes
            )
        )
        and intersects(node, node.func)
    )
    if not file_path.parts or file_path.parts[0] not in _CHECKED_ROOTS:
        return sorted(violations, key=lambda violation: violation.line_number or 0)
    visitor = _BasicsVisitor(file_path=file_path, added_lines=added_lines)
    visitor.visit(tree=source_tree)
    violations.extend(visitor.violations)
    return sorted(violations, key=lambda violation: violation.line_number or 0)
