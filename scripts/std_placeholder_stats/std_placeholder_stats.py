#!/usr/bin/env -S uv run python
"""STD Placeholder Tests Statistics Generator.

Scans the tests directory for STD (Standard Test Design) placeholder tests and
disabled tests. Reports two categories:

    1. **Placeholder tests** — tests with ``__test__ = False`` that contain only
       docstrings describing expected behavior (not yet implemented).
    2. **Disabled tests** — tests with ``__test__ = False`` that contain actual
       implementation code (may need attention).

Output:
    - text: Human-readable summary to stdout (default)
    - json: Machine-readable JSON output

Usage:
    uv run python std_placeholder_stats.py
    uv run python std_placeholder_stats.py --tests-dir tests
    uv run python std_placeholder_stats.py --output-format json

Co-authored-by: Claude <noreply@anthropic.com>
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)
TERMINAL_WIDTH = 120
TEST_ATTR = "__test__"


@dataclass
class PlaceholderClass:
    """A test class containing placeholder and disabled test methods.

    Attributes:
        name: Name of the test class.
        test_methods: List of placeholder test method names (docstring-only).
        disabled_methods: List of disabled test method names (implemented but __test__ = False).
    """

    name: str
    test_methods: list[str] = field(default_factory=list)
    disabled_methods: list[str] = field(default_factory=list)


@dataclass
class PlaceholderFile:
    """A test file containing placeholder and disabled tests.

    Attributes:
        file_path: Path to the test file relative to the project root.
        classes: List of test classes with placeholder or disabled methods.
        standalone_tests: List of standalone placeholder test function names.
        disabled_standalone_tests: List of standalone disabled test function names.
    """

    file_path: str
    classes: list[PlaceholderClass] = field(default_factory=list)
    standalone_tests: list[str] = field(default_factory=list)
    disabled_standalone_tests: list[str] = field(default_factory=list)

    @property
    def total_tests(self) -> int:
        """Return the total number of placeholder tests in this file."""
        class_tests = sum(len(cls.test_methods) for cls in self.classes)
        return class_tests + len(self.standalone_tests)

    @property
    def total_disabled(self) -> int:
        """Return the total number of disabled tests in this file."""
        class_disabled = sum(len(cls.disabled_methods) for cls in self.classes)
        return class_disabled + len(self.disabled_standalone_tests)


def separator(symbol: str, title: str | None = None) -> str:
    """Create a separator line for terminal output.

    Args:
        symbol: The character to use for the separator.
        title: Optional text to center in the separator.

    Returns:
        Formatted separator string.
    """
    if title is None:
        return symbol * TERMINAL_WIDTH

    padding_total = TERMINAL_WIDTH - len(title) - 2
    padding_left = padding_total // 2
    padding_right = padding_total - padding_left
    return f"{symbol * padding_left} {title} {symbol * padding_right}"


def _statements_have_test_false(
    statements: list[ast.stmt],
    target_name: str | None = None,
) -> bool:
    """Check if a list of AST statements contains a `__test__ = False` assignment.

    Handles two patterns:
        - Bare assignment: ``__test__ = False`` (when target_name is None)
        - Attribute assignment: ``target_name.__test__ = False`` (when target_name is provided)

    Args:
        statements: List of AST statement nodes to search.
        target_name: When provided, look for ``target_name.__test__ = False``
            attribute assignment. When None, look for bare ``__test__ = False``.

    Returns:
        True if the matching ``__test__ = False`` assignment is found.
    """
    for node in statements:
        # Skip non-assignment statements; only assignments can set __test__ = False
        if not isinstance(node, ast.Assign):
            continue
        # Skip assignments where the value is not the constant False
        if not (isinstance(node.value, ast.Constant) and node.value.value is False):
            continue
        for target in node.targets:
            if target_name is None:
                # Bare assignment pattern: __test__ = False (module or class level)
                if isinstance(target, ast.Name) and target.id == TEST_ATTR:
                    return True
            else:
                # Attribute assignment pattern: target_name.__test__ = False (e.g., test_func.__test__ = False)
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == target_name
                    and target.attr == TEST_ATTR
                ):
                    return True
    return False


def _is_placeholder_body(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function body contains only a docstring (no implementation).

    A placeholder test has only a docstring describing expected behavior,
    with no actual test logic (assertions, calls, etc.).

    Args:
        func_node: AST function definition node.

    Returns:
        True if the function body is docstring-only (placeholder).
    """
    # A docstring-only body has exactly one statement: an Expr containing a Constant string
    if len(func_node.body) == 1:
        stmt = func_node.body[0]
        return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
    # Also allow docstring + pass (common pattern)
    if len(func_node.body) == 2:
        first = func_node.body[0]
        second = func_node.body[1]
        is_docstring = (
            isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
        )
        is_pass = isinstance(second, ast.Pass)
        return is_docstring and is_pass
    return False


def get_test_methods_from_class(class_node: ast.ClassDef) -> list[str]:
    """Extract placeholder test method names from a class definition.

    Returns only test methods whose body is docstring-only (placeholders).

    Args:
        class_node: AST class definition node.

    Returns:
        List of placeholder test method names.
    """
    return [
        method.name
        for method in class_node.body
        # Collect only function definitions named test_* that are docstring-only placeholders
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and method.name.startswith("test_")
        and _is_placeholder_body(func_node=method)
    ]


def get_disabled_methods_from_class(class_node: ast.ClassDef) -> list[str]:
    """Extract implemented test method names from a class definition.

    These are test methods that have actual implementation (not docstring-only)
    and are candidates for being disabled tests.

    Args:
        class_node: AST class definition node.

    Returns:
        List of implemented test method names.
    """
    return [
        method.name
        for method in class_node.body
        # Collect test_* methods that have implementation (NOT docstring-only placeholders)
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and method.name.startswith("test_")
        and not _is_placeholder_body(func_node=method)
    ]


def _collect_placeholders(
    tree: ast.Module,
    relative_path: str,
    module_is_placeholder: bool,
) -> PlaceholderFile | None:
    """Collect placeholder tests from a module's AST.

    When module_is_placeholder is True (module has top-level __test__ = False),
    all test classes and standalone test functions are included unconditionally.
    Otherwise, each class and function is checked individually for __test__ = False.

    Args:
        tree: AST module tree.
        relative_path: File path relative to the project root.
        module_is_placeholder: Whether the module has top-level __test__ = False.

    Returns:
        A PlaceholderFile if any placeholders are found, None otherwise.
    """
    placeholder = PlaceholderFile(file_path=relative_path)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # Module-level marker or class-level __test__ = False: all test_* methods are placeholders
            if module_is_placeholder or _statements_have_test_false(statements=node.body):
                placeholder_methods = get_test_methods_from_class(class_node=node)
                disabled_methods = get_disabled_methods_from_class(class_node=node)
                if placeholder_methods or disabled_methods:
                    placeholder.classes.append(
                        PlaceholderClass(
                            name=node.name,
                            test_methods=placeholder_methods,
                            disabled_methods=disabled_methods,
                        )
                    )
            # No class-level marker: check each method for method_name.__test__ = False
            else:
                placeholder_method_names: list[str] = []
                disabled_method_names: list[str] = []
                for method in node.body:
                    # Check each test_* method for an attribute assignment in the class body
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith("test_"):
                        if _statements_have_test_false(statements=node.body, target_name=method.name):
                            if _is_placeholder_body(func_node=method):
                                placeholder_method_names.append(method.name)
                            else:
                                disabled_method_names.append(method.name)
                if placeholder_method_names or disabled_method_names:
                    placeholder.classes.append(
                        PlaceholderClass(
                            name=node.name,
                            test_methods=placeholder_method_names,
                            disabled_methods=disabled_method_names,
                        )
                    )

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            # Module-level marker or func.__test__ = False at module level
            if module_is_placeholder or _statements_have_test_false(statements=tree.body, target_name=node.name):
                if _is_placeholder_body(func_node=node):
                    placeholder.standalone_tests.append(node.name)
                else:
                    placeholder.disabled_standalone_tests.append(node.name)

    if placeholder.classes or placeholder.standalone_tests or placeholder.disabled_standalone_tests:
        return placeholder
    return None


def scan_placeholder_tests(tests_dir: Path) -> list[PlaceholderFile]:
    """Scan tests directory for STD placeholder tests.

    Args:
        tests_dir: Path to the tests directory to scan.

    Returns:
        List of PlaceholderFile objects describing found placeholder tests.
    """
    placeholder_files: list[PlaceholderFile] = []

    for test_file in tests_dir.rglob("test_*.py"):
        try:
            file_content = test_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            LOGGER.warning(f"Failed to read {test_file}: {exc}")
            continue
        if TEST_ATTR not in file_content:
            continue

        try:
            tree = ast.parse(source=file_content)
        except SyntaxError as exc:
            LOGGER.warning(f"Failed to parse {test_file}: {exc}")
            continue

        relative_path = str(test_file.relative_to(tests_dir.parent))

        # Dispatch: unified placeholder collection with module-level marker detection
        result = _collect_placeholders(
            tree=tree,
            relative_path=relative_path,
            module_is_placeholder=_statements_have_test_false(statements=tree.body),
        )

        if result:
            placeholder_files.append(result)

    return placeholder_files


def count_placeholder_tests(placeholder_files: list[PlaceholderFile]) -> tuple[int, int]:
    """Count total placeholder tests and files.

    Args:
        placeholder_files: List of PlaceholderFile objects to count.

    Returns:
        A tuple of (total_tests, total_files).
    """
    total_tests = sum(pf.total_tests for pf in placeholder_files)
    total_files = sum(1 for pf in placeholder_files if pf.total_tests > 0)
    return total_tests, total_files


def count_disabled_tests(placeholder_files: list[PlaceholderFile]) -> tuple[int, int]:
    """Count total disabled tests and files containing them.

    Args:
        placeholder_files: List of PlaceholderFile objects to count.

    Returns:
        A tuple of (total_disabled_tests, total_files_with_disabled).
    """
    total_disabled = sum(pf.total_disabled for pf in placeholder_files)
    files_with_disabled = sum(1 for pf in placeholder_files if pf.total_disabled > 0)
    return total_disabled, files_with_disabled


def _format_placeholder_lines(placeholder_file: PlaceholderFile) -> list[str]:
    """Format placeholder tests from a PlaceholderFile into display lines.

    Args:
        placeholder_file: The placeholder file to format.

    Returns:
        List of formatted strings for display.
    """
    lines: list[str] = []

    for cls in placeholder_file.classes:
        if cls.test_methods:
            lines.append(f"{placeholder_file.file_path}::{cls.name}")
            lines.extend(f"  - {method}" for method in cls.test_methods)

    if placeholder_file.standalone_tests:
        lines.append(f"{placeholder_file.file_path}::<standalone>")
        lines.extend(f"  - {test}" for test in placeholder_file.standalone_tests)

    return lines


def _format_disabled_lines(placeholder_file: PlaceholderFile) -> list[str]:
    """Format disabled tests from a PlaceholderFile into display lines.

    Args:
        placeholder_file: The placeholder file to format.

    Returns:
        List of formatted strings for display.
    """
    lines: list[str] = []

    for cls in placeholder_file.classes:
        if cls.disabled_methods:
            lines.append(f"{placeholder_file.file_path}::{cls.name}")
            lines.extend(f"  - {method}" for method in cls.disabled_methods)

    if placeholder_file.disabled_standalone_tests:
        lines.append(f"{placeholder_file.file_path}::<standalone>")
        lines.extend(f"  - {test}" for test in placeholder_file.disabled_standalone_tests)

    return lines


def output_text(placeholder_files: list[PlaceholderFile]) -> None:
    """Output results in human-readable text format.

    Args:
        placeholder_files: List of PlaceholderFile objects to display.
    """
    total_tests, total_files = count_placeholder_tests(placeholder_files=placeholder_files)
    total_disabled, disabled_files = count_disabled_tests(placeholder_files=placeholder_files)

    if total_tests == 0 and total_disabled == 0:
        LOGGER.info("No STD placeholder or disabled tests found.")
        return

    output_lines: list[str] = []

    if total_tests > 0:
        output_lines.append(separator(symbol="="))
        output_lines.append("STD PLACEHOLDER TESTS (not yet implemented)")
        output_lines.append(separator(symbol="="))
        output_lines.append("")

        for placeholder_file in placeholder_files:
            lines = _format_placeholder_lines(placeholder_file=placeholder_file)
            if lines:
                output_lines.extend(lines)

        output_lines.append("")
        output_lines.append(separator(symbol="-"))
        test_word = "test" if total_tests == 1 else "tests"
        file_word = "file" if total_files == 1 else "files"
        output_lines.append(f"Total: {total_tests} placeholder {test_word} in {total_files} {file_word}")
        output_lines.append(separator(symbol="="))

    if total_disabled > 0:
        output_lines.append("")
        output_lines.append(separator(symbol="="))
        output_lines.append("DISABLED TESTS (implemented but marked __test__ = False)")
        output_lines.append(separator(symbol="="))
        output_lines.append("")

        for placeholder_file in placeholder_files:
            lines = _format_disabled_lines(placeholder_file=placeholder_file)
            if lines:
                output_lines.extend(lines)

        output_lines.append("")
        output_lines.append(separator(symbol="-"))
        test_word = "test" if total_disabled == 1 else "tests"
        file_word = "file" if disabled_files == 1 else "files"
        output_lines.append(f"Total: {total_disabled} disabled {test_word} in {disabled_files} {file_word}")
        output_lines.append(separator(symbol="="))

    for line in output_lines:
        LOGGER.info(line)


def output_json(placeholder_files: list[PlaceholderFile]) -> None:
    """Output results in JSON format.

    Args:
        placeholder_files: List of PlaceholderFile objects to output as JSON.
    """
    total_tests, total_files = count_placeholder_tests(placeholder_files=placeholder_files)
    total_disabled, disabled_files = count_disabled_tests(placeholder_files=placeholder_files)

    placeholder_by_file: dict[str, list[str]] = {}
    disabled_by_file: dict[str, list[str]] = {}

    for placeholder_file in placeholder_files:
        # Placeholder tests
        tests: list[str] = []
        for cls in placeholder_file.classes:
            tests.extend(f"{cls.name}::{method}" for method in cls.test_methods)
        tests.extend(placeholder_file.standalone_tests)
        if tests:
            placeholder_by_file[placeholder_file.file_path] = tests

        # Disabled tests
        disabled: list[str] = []
        for cls in placeholder_file.classes:
            disabled.extend(f"{cls.name}::{method}" for method in cls.disabled_methods)
        disabled.extend(placeholder_file.disabled_standalone_tests)
        if disabled:
            disabled_by_file[placeholder_file.file_path] = disabled

    output: dict[str, Any] = {
        "placeholder": {
            "total_tests": total_tests,
            "total_files": total_files,
            "files": placeholder_by_file,
        },
        "disabled": {
            "total_tests": total_disabled,
            "total_files": disabled_files,
            "files": disabled_by_file,
        },
    }

    # Use print() instead of LOGGER to produce clean JSON on stdout without log formatting
    print(json.dumps(obj=output, indent=2))


@click.command(
    help="STD Placeholder Tests Statistics Generator",
    epilog="""
Scans the tests directory for STD (Standard Test Design) placeholder tests.
These are tests marked with `__test__ = False` that contain only docstrings
describing expected behavior, without actual implementation code.

\b
Examples:
    uv run python std_placeholder_stats.py
    uv run python std_placeholder_stats.py --tests-dir my_tests
    uv run python std_placeholder_stats.py --output-format json
    """,
)
@click.option(
    "--tests-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True, path_type=Path),
    default=Path("tests"),
    help="The tests directory to scan (default: tests)",
)
@click.option(
    "--output-format",
    type=click.Choice(choices=["text", "json"]),
    default="text",
    help="Output format: text (default) or json",
)
def main(tests_dir: Path, output_format: str) -> None:
    """Main entry point for the STD placeholder stats generator."""
    LOGGER.info(f"Scanning tests directory: {tests_dir}")

    placeholder_files = scan_placeholder_tests(tests_dir=tests_dir)

    if output_format == "json":
        output_json(placeholder_files=placeholder_files)
    else:
        output_text(placeholder_files=placeholder_files)


if __name__ == "__main__":
    main()
