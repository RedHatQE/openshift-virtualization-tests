# Co-authored-by: Claude <noreply@anthropic.com>
"""Collector for manual tests marked with ``@pytest.mark.manual``.

Scans the tests directory AST for tests selected by the ``manual``
marker (module ``pytestmark``, class decorator, or test decorator) and
extracts full context for each: docstrings, markers, fixtures, and
Polarion IDs.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import click
from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)

MANUAL_MARKER = "manual"

# Errors _safe_eval_bool_expr can raise for an invalid marker expression.
# RecursionError/MemoryError cover pathologically nested expressions
# (parser stack overflow); nothing else in _safe_eval_bool_expr raises them,
# so they cannot mask a real bug.
_MARKER_EXPRESSION_ERRORS = (SyntaxError, ValueError, TypeError, RecursionError, MemoryError)


def _invalid_marker_expression(marker_filter: str, exc: Exception) -> click.ClickException:
    """Build the ClickException for an invalid marker expression.

    Single construction site for the marker-expression error so the
    validation and matching paths always report identical text.

    Args:
        marker_filter: The invalid marker expression as typed.
        exc: The underlying error raised while evaluating the expression.

    Returns:
        A ClickException carrying the canonical error message.
    """
    # A typo'd expression would otherwise look like an empty selection —
    # fail fast instead of silently returning zero tests.
    return click.ClickException(f"Invalid marker expression {marker_filter!r}: {exc}")


@dataclass
class ManualTestDetail:
    """Full context for a manual test.

    Attributes:
        file_path: Path to the test file relative to the repository root
            (the parent of the nearest ``tests`` directory).
        class_name: Enclosing test class name, or None for standalone tests.
        method_name: Test method/function name.
        module_docstring: Module-level docstring (STP link, shared preconditions).
        class_docstring: Class-level docstring (class preconditions).
        test_docstring: Test function docstring (Steps, Expected).
        module_markers: Module-level pytestmark markers.
        class_markers: Markers on the class definition.
        class_fixtures: Fixtures from @pytest.mark.usefixtures on the class.
        test_markers: Markers on the test function.
        polarion_id: Polarion test case ID from @pytest.mark.polarion.
        node_id: Pytest-style node ID.
    """

    file_path: str
    class_name: str | None
    method_name: str
    module_docstring: str | None = None
    class_docstring: str | None = None
    test_docstring: str | None = None
    module_markers: list[str] = field(default_factory=list)
    class_markers: list[str] = field(default_factory=list)
    class_fixtures: list[str] = field(default_factory=list)
    test_markers: list[str] = field(default_factory=list)
    polarion_id: str | None = None
    node_id: str = ""


def _extract_docstring(node: ast.AST) -> str | None:
    """Extract docstring from an AST node.

    Checks whether the first statement in the node's body is an
    ``ast.Expr`` containing a string ``ast.Constant``.

    Args:
        node: An AST module, class, or function definition node.

    Returns:
        The docstring text, or None if no docstring is present.
    """
    body = getattr(node, "body", None)
    if not body:
        return None

    first_stmt = body[0]
    if (
        isinstance(first_stmt, ast.Expr)
        and isinstance(first_stmt.value, ast.Constant)
        and isinstance(first_stmt.value.value, str)
    ):
        return first_stmt.value.value

    return None


def _is_pytest_mark_attr(node: ast.expr) -> tuple[bool, str | None]:
    """Check if an AST node represents ``pytest.mark.MARKER``.

    Args:
        node: An AST expression node (Attribute chain).

    Returns:
        A tuple of (is_pytest_mark, marker_name).
    """
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    ):
        return True, node.attr
    return False, None


def _safe_arg_repr(arg: ast.expr) -> str:
    """Convert a decorator argument AST node to its string representation.

    Uses ``ast.literal_eval`` for simple constant nodes and falls back
    to ``ast.dump`` for complex expressions that cannot be evaluated.

    Args:
        arg: An AST expression node from a decorator's arguments.

    Returns:
        String representation of the argument.
    """
    try:
        return str(ast.literal_eval(arg))
    except ValueError, TypeError:
        return ast.dump(arg)


def _extract_markers(decorators: list[ast.expr]) -> list[str]:
    """Extract pytest marker names from decorator nodes.

    Handles both bare markers (``@pytest.mark.MARKER``) and called
    markers (``@pytest.mark.MARKER(args)``).

    Args:
        decorators: List of decorator AST expression nodes.

    Returns:
        List of marker strings, e.g. ``["smoke", "polarion(MOCK-1234)"]``.
    """
    markers: list[str] = []

    for decorator in decorators:
        if isinstance(decorator, ast.Attribute):
            is_mark, marker_name = _is_pytest_mark_attr(node=decorator)
            if is_mark and marker_name is not None:
                markers.append(marker_name)

        elif isinstance(decorator, ast.Call):
            is_mark, marker_name = _is_pytest_mark_attr(node=decorator.func)
            if is_mark and marker_name is not None:
                args_repr = ", ".join(_safe_arg_repr(arg=arg) for arg in decorator.args)
                if args_repr:
                    markers.append(f"{marker_name}({args_repr})")
                else:
                    markers.append(marker_name)

    return markers


def _extract_usefixtures(decorators: list[ast.expr]) -> list[str]:
    """Extract fixture names from ``@pytest.mark.usefixtures(...)`` decorators.

    Args:
        decorators: List of decorator AST expression nodes.

    Returns:
        List of fixture name strings.
    """
    fixtures: list[str] = []

    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue

        is_mark, marker_name = _is_pytest_mark_attr(node=decorator.func)
        if is_mark and marker_name == "usefixtures":
            for arg in decorator.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    fixtures.append(arg.value)

    return fixtures


def _extract_polarion_id(decorators: list[ast.expr]) -> str | None:
    """Extract Polarion test case ID from ``@pytest.mark.polarion("MOCK-XXXXX")``.

    Args:
        decorators: List of decorator AST expression nodes.

    Returns:
        The Polarion ID string, or None if not found.
    """
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue

        is_mark, marker_name = _is_pytest_mark_attr(node=decorator.func)
        if is_mark and marker_name == "polarion":
            if (
                len(decorator.args) == 1
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                return decorator.args[0].value

    return None


def _extract_marker_name_from_element(element: ast.expr) -> str | None:
    """Extract a marker name from a single pytestmark list element.

    Handles both ``pytest.mark.MARKER`` (Attribute) and
    ``pytest.mark.MARKER(...)`` (Call) forms.

    Args:
        element: An AST expression node from the pytestmark list.

    Returns:
        The marker name string, or None if not a pytest marker.
    """
    if isinstance(element, ast.Attribute):
        is_mark, marker_name = _is_pytest_mark_attr(node=element)
        if is_mark:
            return marker_name

    elif isinstance(element, ast.Call):
        is_mark, marker_name = _is_pytest_mark_attr(node=element.func)
        if is_mark:
            return marker_name

    return None


def _extract_module_markers(tree: ast.Module) -> list[str]:
    """Extract module-level ``pytestmark`` markers from the AST module.

    Handles both single marker assignment and list of markers::

        pytestmark = pytest.mark.usefixtures("my_fixture")
        pytestmark = [pytest.mark.smoke, pytest.mark.tier1]

    Args:
        tree: The parsed AST module.

    Returns:
        List of marker name strings.
    """
    markers: list[str] = []

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue

        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "pytestmark"):
                continue

            if isinstance(node.value, ast.List):
                for element in node.value.elts:
                    marker_name = _extract_marker_name_from_element(element=element)
                    if marker_name is not None:
                        markers.append(marker_name)
            else:
                marker_name = _extract_marker_name_from_element(element=node.value)
                if marker_name is not None:
                    markers.append(marker_name)

    return markers


def _bare_marker_name(marker: str) -> str:
    """Strip a marker's arguments, returning its bare name.

    Args:
        marker: Marker string, possibly with arguments
            (e.g. ``"parametrize(...)"``).

    Returns:
        The bare marker name, e.g. ``"parametrize"``.
    """
    paren_idx = marker.find("(")
    return marker[:paren_idx] if paren_idx != -1 else marker


def _has_manual_marker(markers: list[str]) -> bool:
    """Check whether the ``manual`` marker is present in a marker list.

    Args:
        markers: List of marker strings, possibly with arguments
            (e.g. ``"parametrize(...)"``).

    Returns:
        True if the bare ``manual`` marker is present.
    """
    # Lowercase matching is intentional leniency for hand-written markers;
    # pytest itself treats marker names as case-sensitive.
    return any(_bare_marker_name(marker=marker_str).lower() == MANUAL_MARKER for marker_str in markers)


def _safe_eval_bool_expr(expr: str) -> bool:
    """Safely evaluate a boolean expression containing only True/False/and/or/not.

    Uses AST parsing to validate the expression contains no unsafe nodes
    before evaluation. Rejects function calls, attribute access, imports, etc.

    Args:
        expr: Boolean expression string (e.g., ``"True and not False"``).

    Returns:
        Result of the boolean expression.

    Raises:
        TypeError: If the expression contains disallowed AST nodes.
    """
    tree = ast.parse(source=expr, mode="eval")
    # SECURITY BOUNDARY: this allowlist is what makes eval() safe here.
    # Do not relax it (e.g. adding ast.Compare or ast.Name) without a
    # security review — any addition widens what eval() can execute.
    safe_nodes = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Not, ast.And, ast.Or, ast.Constant)
    for node in ast.walk(tree):
        if not isinstance(node, safe_nodes):
            raise TypeError(f"Disallowed AST node in expression: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, bool):
            raise TypeError(f"Disallowed constant in expression: {node.value!r}")
    compiled = compile(source=tree, filename="<marker>", mode="eval")
    return eval(compiled)


def _matches_marker_filter(detail: ManualTestDetail, marker_filter: str) -> bool:
    """Check if a manual test matches a marker filter expression.

    Supports simple marker names and ``and``/``or``/``not`` boolean expressions.
    Markers are matched against module, class, and test-level markers.

    Args:
        detail: The manual test to check.
        marker_filter: Pytest-style marker expression (e.g., ``"gating"``,
            ``"smoke and not tier3"``).

    Returns:
        True if the test matches the expression.

    Raises:
        click.ClickException: If the marker expression cannot be evaluated.
    """
    # Strip args: "parametrize(...)" → "parametrize"
    all_markers = {
        _bare_marker_name(marker=marker_str).lower()
        for marker_str in (detail.module_markers + detail.class_markers + detail.test_markers)
    }

    expr = _build_marker_expr(marker_filter=marker_filter, all_markers=all_markers)

    try:
        return _safe_eval_bool_expr(expr=expr)
    except _MARKER_EXPRESSION_ERRORS as exc:
        raise _invalid_marker_expression(marker_filter=marker_filter, exc=exc) from exc


def _build_marker_expr(marker_filter: str, all_markers: set[str]) -> str:
    """Build a safe boolean expression from a marker filter.

    Replaces the test's known marker names with ``True`` and any
    remaining identifiers with ``False`` so only boolean constants and
    ``and``/``or``/``not`` remain — the nodes the safe evaluator accepts.

    Args:
        marker_filter: Pytest-style marker expression.
        all_markers: Bare, lowercased marker names the test carries.

    Returns:
        The transformed boolean expression string.
    """
    expr = marker_filter.lower()
    for marker_name in sorted(all_markers, key=len, reverse=True):
        if marker_name not in ("and", "or", "not"):
            expr = re.sub(pattern=rf"\b{re.escape(marker_name)}\b", repl="True", string=expr)

    # Replace remaining unknown markers with False
    return re.sub(
        pattern=r"\b(?!and\b|or\b|not\b|True\b|False\b)[a-zA-Z_][a-zA-Z0-9_]*\b",
        repl="False",
        string=expr,
    )


def _validate_marker_expression(marker_filter: str) -> None:
    """Validate a marker expression before it is applied to any test.

    Expression validity does not depend on which markers a test carries
    (both ``True`` and ``False`` substitutions evaluate), so checking the
    expression against an empty marker set catches every invalid
    expression. This makes an invalid ``-m`` fail fast even when zero
    manual tests are collected, instead of silently looking like an
    empty selection.

    Args:
        marker_filter: Pytest-style marker expression to validate.

    Raises:
        click.ClickException: If the marker expression cannot be evaluated.
    """
    expr = _build_marker_expr(marker_filter=marker_filter, all_markers=set())
    try:
        _safe_eval_bool_expr(expr=expr)
    except _MARKER_EXPRESSION_ERRORS as exc:
        raise _invalid_marker_expression(marker_filter=marker_filter, exc=exc) from exc


def _matches_keyword_filter(detail: ManualTestDetail, keyword_filter: str) -> bool:
    """Check if a manual test matches a keyword filter.

    Matches the keyword against the test's node ID (case-insensitive).

    Args:
        detail: The manual test to check.
        keyword_filter: Keyword substring to match.

    Returns:
        True if the keyword is found in the node ID.
    """
    return keyword_filter.lower() in detail.node_id.lower()


def _repo_relative_path(test_file: Path, tests_dir: Path) -> str:
    """Compute a repo-root-relative path for a test file.

    Uses the parent of the nearest ancestor directory named ``tests`` as
    the base, so node IDs are stable regardless of which ``--tests-dir``
    subdirectory was scanned (e.g. ``tests/network/test_a.py`` both when
    scanning ``tests`` and ``tests/network``). Falls back to the parent
    of ``tests_dir`` when no ``tests`` ancestor exists.

    Args:
        test_file: Absolute or relative path to the test file.
        tests_dir: The scanned tests directory.

    Returns:
        Repo-root-relative path string, e.g. ``tests/network/test_a.py``.
    """
    resolved = test_file.resolve()
    for parent in resolved.parents:
        if parent.name == "tests":
            return str(resolved.relative_to(parent.parent))
    return str(test_file.relative_to(tests_dir.parent))


def _collect_manual_class_methods(
    class_node: ast.ClassDef,
    relative_path: str,
    class_is_manual: bool,
    module_is_manual: bool,
    module_docstring: str | None,
    module_markers: list[str],
    class_docstring: str | None,
    class_markers: list[str],
    class_fixtures: list[str],
) -> list[ManualTestDetail]:
    """Collect manual test methods from a class definition.

    Args:
        class_node: AST class definition node.
        relative_path: File path relative to the repository root.
        class_is_manual: Whether the class carries the ``manual`` marker.
        module_is_manual: Whether the module carries the ``manual`` marker
            (pytest applies module pytestmark to class methods too).
        module_docstring: Module-level docstring.
        module_markers: Module-level pytestmark markers.
        class_docstring: Class-level docstring.
        class_markers: Markers on the class definition.
        class_fixtures: Fixtures from @pytest.mark.usefixtures on the class.

    Returns:
        List of ManualTestDetail for each manual test method.
    """
    details: list[ManualTestDetail] = []

    for method in class_node.body:
        if not (isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith("test_")):
            continue

        test_markers = _extract_markers(decorators=method.decorator_list)
        if not (class_is_manual or module_is_manual or _has_manual_marker(markers=test_markers)):
            continue

        node_id = f"{relative_path}::{class_node.name}::{method.name}"
        details.append(
            ManualTestDetail(
                file_path=relative_path,
                class_name=class_node.name,
                method_name=method.name,
                module_docstring=module_docstring,
                module_markers=module_markers,
                class_docstring=class_docstring,
                test_docstring=_extract_docstring(node=method),
                class_markers=class_markers,
                class_fixtures=class_fixtures,
                test_markers=test_markers,
                polarion_id=_extract_polarion_id(decorators=method.decorator_list),
                node_id=node_id,
            )
        )

    return details


def _collect_manual_standalone_function(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    relative_path: str,
    module_is_manual: bool,
    module_docstring: str | None,
    module_markers: list[str],
) -> ManualTestDetail | None:
    """Collect a standalone manual test function, if it is manual.

    Args:
        func_node: AST function definition node.
        relative_path: File path relative to the repository root.
        module_is_manual: Whether the module carries the ``manual`` marker.
        module_docstring: Module-level docstring.
        module_markers: Module-level pytestmark markers.

    Returns:
        A ManualTestDetail when the function is manual, None otherwise.
    """
    test_markers = _extract_markers(decorators=func_node.decorator_list)
    if not (module_is_manual or _has_manual_marker(markers=test_markers)):
        return None

    node_id = f"{relative_path}::{func_node.name}"
    return ManualTestDetail(
        file_path=relative_path,
        class_name=None,
        method_name=func_node.name,
        module_docstring=module_docstring,
        class_docstring=None,
        test_docstring=_extract_docstring(node=func_node),
        module_markers=module_markers,
        class_markers=[],
        class_fixtures=[],
        test_markers=test_markers,
        polarion_id=_extract_polarion_id(decorators=func_node.decorator_list),
        node_id=node_id,
    )


def collect_manual_tests(
    tests_dir: Path,
    marker_filter: str | None = None,
    keyword_filter: str | None = None,
) -> list[ManualTestDetail]:
    """Collect manual tests with full context, optionally filtered.

    Scans all ``test_*.py`` files under ``tests_dir`` for tests selected
    by the ``manual`` marker and extracts docstrings, markers, fixtures,
    and Polarion IDs for each. Node IDs are repo-root-relative and stable
    regardless of the ``tests_dir`` subdirectory scanned.

    Args:
        tests_dir: Path to the tests directory to scan.
        marker_filter: Optional pytest-style marker expression to filter by.
        keyword_filter: Optional keyword substring to match against node IDs.

    Returns:
        List of ``ManualTestDetail`` objects sorted by ``node_id``.

    Raises:
        click.ClickException: If ``marker_filter`` is not a valid marker
            expression.
    """
    if marker_filter:
        _validate_marker_expression(marker_filter=marker_filter)

    details: list[ManualTestDetail] = []

    for test_file in sorted(tests_dir.rglob("test_*.py")):
        try:
            source = test_file.read_text(encoding="utf-8")
            tree = ast.parse(source=source)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            LOGGER.warning(f"Failed to read/parse {test_file}: {exc}")
            continue

        relative_path = _repo_relative_path(test_file=test_file, tests_dir=tests_dir)
        module_docstring = _extract_docstring(node=tree)
        module_markers = _extract_module_markers(tree=tree)
        module_is_manual = _has_manual_marker(markers=module_markers)

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_markers = _extract_markers(decorators=node.decorator_list)
                details.extend(
                    _collect_manual_class_methods(
                        class_node=node,
                        relative_path=relative_path,
                        class_is_manual=_has_manual_marker(markers=class_markers),
                        module_is_manual=module_is_manual,
                        module_docstring=module_docstring,
                        module_markers=module_markers,
                        class_docstring=_extract_docstring(node=node),
                        class_markers=class_markers,
                        class_fixtures=_extract_usefixtures(decorators=node.decorator_list),
                    )
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                detail = _collect_manual_standalone_function(
                    func_node=node,
                    relative_path=relative_path,
                    module_is_manual=module_is_manual,
                    module_docstring=module_docstring,
                    module_markers=module_markers,
                )
                if detail is not None:
                    details.append(detail)

    LOGGER.info(f"Collected {len(details)} manual tests from {tests_dir}")

    if marker_filter:
        details = [detail for detail in details if _matches_marker_filter(detail=detail, marker_filter=marker_filter)]
        LOGGER.info(f"After marker filter '{marker_filter}': {len(details)} tests")

    if keyword_filter:
        details = [
            detail for detail in details if _matches_keyword_filter(detail=detail, keyword_filter=keyword_filter)
        ]
        LOGGER.info(f"After keyword filter '{keyword_filter}': {len(details)} tests")

    return sorted(details, key=lambda detail: detail.node_id)
