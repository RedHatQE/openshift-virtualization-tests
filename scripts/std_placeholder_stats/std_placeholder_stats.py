#!/usr/bin/env -S uv run python
"""STD Placeholder Tests Statistics Generator.

Scans the tests directory for STD (Standard Test Design) placeholder tests that
are not yet implemented. These are tests with `__test__ = False` that contain
only docstrings describing expected behavior, without actual implementation code.

Output:
    - text: Human-readable summary to stdout (default)
    - json: Machine-readable JSON output

Usage:
    uv run python scripts/std_placeholder_stats/std_placeholder_stats.py
    uv run python scripts/std_placeholder_stats/std_placeholder_stats.py --tests-dir tests
    uv run python scripts/std_placeholder_stats/std_placeholder_stats.py --output-format json

Generated using Claude cli
"""

from __future__ import annotations

import ast
import json
from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from pathlib import Path
from typing import Any

from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)


def separator(symbol_: str, val: str | None = None) -> str:
    """Create a separator line for terminal output.

    Args:
        symbol_: The character to use for the separator.
        val: Optional text to center in the separator.

    Returns:
        Formatted separator string.
    """
    terminal_width = 120  # Fixed width for consistent output
    if not val:
        return symbol_ * terminal_width

    sepa = int((terminal_width - len(val) - 2) // 2)
    return f"{symbol_ * sepa} {val} {symbol_ * sepa}"


def module_has_test_false(module_tree: ast.Module) -> bool:
    """Check if a module has `__test__ = False` assignment at top level.

    Args:
        module_tree: AST module tree

    Returns:
        True if the module has __test__ = False at top level, False otherwise
    """
    for node in module_tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__test__":
                    if isinstance(node.value, ast.Constant) and node.value.value is False:
                        return True
    return False


def class_has_test_false(class_node: ast.ClassDef) -> bool:
    """Check if a class has `__test__ = False` assignment in its body.

    Args:
        class_node: AST class definition node

    Returns:
        True if the class has __test__ = False, False otherwise
    """
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "__test__":
                    if isinstance(stmt.value, ast.Constant) and stmt.value.value is False:
                        return True
    return False


def function_has_test_false(module_tree: ast.Module, function_name: str) -> bool:
    """Check if a standalone function has `function_name.__test__ = False` assignment.

    Args:
        module_tree: AST module tree
        function_name: Name of the function to check

    Returns:
        True if the function has __test__ = False assignment, False otherwise
    """
    for node in module_tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    if (
                        isinstance(target.value, ast.Name)
                        and target.value.id == function_name
                        and target.attr == "__test__"
                    ):
                        if isinstance(node.value, ast.Constant) and node.value.value is False:
                            return True
    return False


def method_has_test_false(class_node: ast.ClassDef, method_name: str) -> bool:
    """Check if a method has `method_name.__test__ = False` assignment in the class body.

    This detects patterns like:
        class TestFoo:
            def test_bar(self):
                pass
            test_bar.__test__ = False

    Args:
        class_node: AST class definition node
        method_name: Name of the method to check

    Returns:
        True if the method has __test__ = False assignment in the class body, False otherwise
    """
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Attribute):
                    if (
                        isinstance(target.value, ast.Name)
                        and target.value.id == method_name
                        and target.attr == "__test__"
                    ):
                        if isinstance(stmt.value, ast.Constant) and stmt.value.value is False:
                            return True
    return False


def get_test_methods_from_class(class_node: ast.ClassDef) -> list[str]:
    """Extract test method names from a class definition.

    Args:
        class_node: AST class definition node

    Returns:
        List of test method names.
    """
    return [
        method.name
        for method in class_node.body
        if isinstance(method, ast.FunctionDef) and method.name.startswith("test_")
    ]


def _append_class_entries(
    placeholder_files: dict[str, list[str]],
    relative_path: str,
    class_node: ast.ClassDef,
) -> None:
    """Append a class and its test methods to the placeholder files mapping.

    Adds the class entry in ``path::ClassName`` format and indented method
    entries for every ``test_*`` method found in the class body.

    Args:
        placeholder_files: Mapping of file paths to placeholder test entries
            (modified in place).
        relative_path: File path relative to the project root.
        class_node: AST class definition node to extract entries from.
    """
    placeholder_files.setdefault(relative_path, []).append(f"{relative_path}::{class_node.name}")
    test_methods = get_test_methods_from_class(class_node=class_node)
    if test_methods:
        placeholder_files[relative_path].extend(f"  - {method}" for method in test_methods)


def scan_placeholder_tests(tests_dir: Path) -> dict[str, list[str]]:
    """Scan tests directory for STD placeholder tests.

    Args:
        tests_dir: Path to the tests directory to scan.

    Returns:
        Dictionary mapping file paths to lists of placeholder test entries.
    """
    placeholder_files: dict[str, list[str]] = {}

    for test_file in tests_dir.rglob("test_*.py"):
        file_content = test_file.read_text(encoding="utf-8")
        if "__test__ = False" not in file_content:
            continue

        try:
            tree = ast.parse(source=file_content)
        except SyntaxError as exc:
            LOGGER.warning(f"Failed to parse {test_file}: {exc}")
            continue

        relative_path = str(test_file.relative_to(tests_dir.parent))

        # Check if module has __test__ = False at top level
        if module_has_test_false(module_tree=tree):
            # Report ALL test classes and functions in this module
            module_has_standalone_tests = False

            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    _append_class_entries(
                        placeholder_files=placeholder_files,
                        relative_path=relative_path,
                        class_node=node,
                    )

                elif isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    # For standalone functions, add module path first if not already added
                    if not module_has_standalone_tests:
                        placeholder_files.setdefault(relative_path, []).append(relative_path)
                        module_has_standalone_tests = True
                    placeholder_files[relative_path].append(f"  - {node.name}")
        else:
            # Check individual classes and functions for __test__ = False
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    if class_has_test_false(class_node=node):
                        # Class-level __test__ = False: report class and all methods
                        _append_class_entries(
                            placeholder_files=placeholder_files,
                            relative_path=relative_path,
                            class_node=node,
                        )
                    else:
                        # Check each method for method.__test__ = False in class body
                        method_placeholders: list[str] = []
                        for method in node.body:
                            if isinstance(method, ast.FunctionDef) and method.name.startswith("test_"):
                                if method_has_test_false(class_node=node, method_name=method.name):
                                    method_placeholders.append(f"  - {method.name}")
                        if method_placeholders:
                            placeholder_files.setdefault(relative_path, []).append(f"{relative_path}::{node.name}")
                            placeholder_files[relative_path].extend(method_placeholders)

                elif isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    if function_has_test_false(module_tree=tree, function_name=node.name):
                        # For standalone functions, add module path first if not already added
                        if relative_path not in placeholder_files:
                            placeholder_files[relative_path] = [relative_path]
                        elif relative_path not in placeholder_files[relative_path]:
                            placeholder_files[relative_path].insert(0, relative_path)
                        placeholder_files[relative_path].append(f"  - {node.name}")

    return placeholder_files


def output_text(placeholder_files: dict[str, list[str]]) -> None:
    """Output results in human-readable text format.

    Args:
        placeholder_files: Dictionary mapping file paths to placeholder test entries.
    """
    if not placeholder_files:
        LOGGER.info("No STD placeholder tests found.")
        return

    total_tests = 0
    total_files = 0

    output_lines: list[str] = []
    output_lines.append(separator(symbol_="="))
    output_lines.append("STD PLACEHOLDER TESTS (not yet implemented)")
    output_lines.append(separator(symbol_="="))
    output_lines.append("")

    for entries in placeholder_files.values():
        has_tests = False
        for entry in entries:
            output_lines.append(entry)
            if entry.startswith("  - "):
                total_tests += 1
                has_tests = True
        if has_tests:
            total_files += 1

    output_lines.append("")
    output_lines.append(separator(symbol_="-"))
    output_lines.append(f"Total: {total_tests} placeholder tests in {total_files} files")
    output_lines.append(separator(symbol_="="))

    for line in output_lines:
        LOGGER.info(line)


def output_json(placeholder_files: dict[str, list[str]]) -> None:
    """Output results in JSON format.

    Args:
        placeholder_files: Dictionary mapping file paths to placeholder test entries.
    """
    total_tests = 0
    tests_by_file: dict[str, list[str]] = {}

    for file_path, entries in placeholder_files.items():
        tests: list[str] = []
        for entry in entries:
            if entry.startswith("  - "):
                tests.append(entry.strip().removeprefix("- "))
                total_tests += 1
        if tests:
            tests_by_file[file_path] = tests

    output: dict[str, Any] = {
        "total_tests": total_tests,
        "total_files": len(tests_by_file),
        "files": tests_by_file,
    }

    print(json.dumps(output, indent=2))


def parse_args() -> Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = ArgumentParser(
        description="STD Placeholder Tests Statistics Generator",
        formatter_class=RawDescriptionHelpFormatter,
        epilog="""
Scans the tests directory for STD (Standard Test Design) placeholder tests.
These are tests marked with `__test__ = False` that contain only docstrings
describing expected behavior, without actual implementation code.

Examples:
    # Scan default tests directory with text output
    uv run python scripts/std_placeholder_stats/std_placeholder_stats.py

    # Scan custom tests directory
    uv run python scripts/std_placeholder_stats/std_placeholder_stats.py --tests-dir my_tests

    # Output as JSON
    uv run python scripts/std_placeholder_stats/std_placeholder_stats.py --output-format json
        """,
    )
    parser.add_argument(
        "--tests-dir",
        type=Path,
        default=Path("tests"),
        help="The tests directory to scan (default: tests)",
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        help="Output format: text (default) or json",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point for the STD placeholder stats generator.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    args = parse_args()

    tests_dir = args.tests_dir
    if not tests_dir.is_absolute():
        tests_dir = Path.cwd() / tests_dir

    if not tests_dir.exists():
        LOGGER.error(f"Tests directory does not exist: {tests_dir}")
        return 1

    if not tests_dir.is_dir():
        LOGGER.error(f"Path is not a directory: {tests_dir}")
        return 1

    LOGGER.info(f"Scanning tests directory: {tests_dir}")

    placeholder_files = scan_placeholder_tests(tests_dir=tests_dir)

    if args.output_format == "json":
        output_json(placeholder_files=placeholder_files)
    else:
        output_text(placeholder_files=placeholder_files)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
