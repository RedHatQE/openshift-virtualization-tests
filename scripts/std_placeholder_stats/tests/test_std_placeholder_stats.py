"""Unit tests for STD Placeholder Stats Generator.

Tests cover all public functions in std_placeholder_stats.py including
AST-based analysis functions and the directory scanner.

Generated using Claude cli
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

import pytest

from scripts.std_placeholder_stats.std_placeholder_stats import (
    class_has_test_false,
    function_has_test_false,
    get_test_methods_from_class,
    method_has_test_false,
    module_has_test_false,
    output_json,
    output_text,
    scan_placeholder_tests,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_FALSE_MARKER = "__test__ = False"

# ---------------------------------------------------------------------------
# Source code fragments for AST-based tests
# ---------------------------------------------------------------------------

SOURCE_MODULE_TEST_FALSE = f"""\
{TEST_FALSE_MARKER}

class TestFoo:
    def test_bar(self):
        pass
"""

SOURCE_NO_TEST_ASSIGNMENT = """\
class TestFoo:
    def test_bar(self):
        pass
"""

SOURCE_CLASS_TEST_FALSE = f"""\
class TestFoo:
    {TEST_FALSE_MARKER}

    def test_bar(self):
        pass

    def test_baz(self):
        pass
"""

SOURCE_FUNCTION_TEST_FALSE = f"""\
def test_standalone():
    pass

test_standalone.{TEST_FALSE_MARKER}
"""

SOURCE_FUNCTION_TEST_FALSE_DIFFERENT_NAME = f"""\
def test_alpha():
    pass

test_alpha.{TEST_FALSE_MARKER}

def test_beta():
    pass
"""

SOURCE_STANDALONE_FUNCTION = """\
def test_standalone():
    pass
"""

SOURCE_METHOD_TEST_FALSE = f"""\
class TestFoo:
    def test_alpha(self):
        pass

    test_alpha.{TEST_FALSE_MARKER}

    def test_beta(self):
        pass
"""

SOURCE_TWO_METHODS = """\
class TestFoo:
    def test_alpha(self):
        pass

    def test_beta(self):
        pass
"""

SOURCE_CLASS_WITH_MIXED_METHODS = f"""\
class TestFoo:
    {TEST_FALSE_MARKER}

    def __init__(self):
        pass

    def helper_method(self):
        pass

    def test_one(self):
        pass

    def test_two(self):
        pass

    def setup_method(self):
        pass
"""

SOURCE_CLASS_NO_TEST_METHODS = """\
class TestFoo:
    def __init__(self):
        pass

    def helper(self):
        pass
"""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_first_class_node(source: str) -> ast.ClassDef:
    """Parse source and return the first ClassDef node.

    Args:
        source: Python source code containing a class definition.

    Returns:
        The first ast.ClassDef found in the parsed source.
    """
    tree = ast.parse(source=source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return node
    raise ValueError("No class definition found in source")


def _create_test_file(directory: Path, filename: str, content: str) -> Path:
    """Create a test file in the given directory.

    Args:
        directory: Parent directory for the file.
        filename: Name of the test file.
        content: Python source content for the file.

    Returns:
        Path to the created file.
    """
    file_path = directory / filename
    file_path.write_text(data=content, encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tests_dir(tmp_path: Path) -> Path:
    """Provide a temporary 'tests' directory for scan_placeholder_tests."""
    directory = tmp_path / "tests"
    directory.mkdir()
    return directory


# ===========================================================================
# Tests for module_has_test_false()
# ===========================================================================


class TestModuleHasTestFalse:
    """Tests for the module_has_test_false() function."""

    def test_returns_true_when_module_has_test_false(self) -> None:
        """module_has_test_false() detects __test__ = False at module level."""
        tree = ast.parse(source=SOURCE_MODULE_TEST_FALSE)
        assert module_has_test_false(module_tree=tree) is True

    def test_returns_false_when_no_test_assignment(self) -> None:
        """module_has_test_false() returns False with no __test__ assignment."""
        tree = ast.parse(source=SOURCE_NO_TEST_ASSIGNMENT)
        assert module_has_test_false(module_tree=tree) is False

    def test_ignores_class_level_test_false(self) -> None:
        """module_has_test_false() ignores __test__ = False inside classes."""
        tree = ast.parse(source=SOURCE_CLASS_TEST_FALSE)
        assert module_has_test_false(module_tree=tree) is False


# ===========================================================================
# Tests for class_has_test_false()
# ===========================================================================


class TestClassHasTestFalse:
    """Tests for the class_has_test_false() function."""

    def test_returns_true_when_class_has_test_false(self) -> None:
        """class_has_test_false() detects __test__ = False in class body."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_TEST_FALSE)
        assert class_has_test_false(class_node=class_node) is True

    def test_returns_false_when_no_test_assignment(self) -> None:
        """class_has_test_false() returns False with no __test__ assignment."""
        class_node = _get_first_class_node(source=SOURCE_NO_TEST_ASSIGNMENT)
        assert class_has_test_false(class_node=class_node) is False

    def test_detects_test_false_in_class_with_mixed_methods(self) -> None:
        """class_has_test_false() detects __test__ = False even with non-test methods present."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_WITH_MIXED_METHODS)
        assert class_has_test_false(class_node=class_node) is True


# ===========================================================================
# Tests for function_has_test_false()
# ===========================================================================


class TestFunctionHasTestFalse:
    """Tests for the function_has_test_false() function."""

    def test_returns_true_when_function_has_test_false(self) -> None:
        """function_has_test_false() detects func.__test__ = False at module level."""
        tree = ast.parse(source=SOURCE_FUNCTION_TEST_FALSE)
        assert function_has_test_false(module_tree=tree, function_name="test_standalone") is True

    def test_returns_false_for_non_matching_function_name(self) -> None:
        """function_has_test_false() returns False for a different function name."""
        tree = ast.parse(source=SOURCE_FUNCTION_TEST_FALSE)
        assert function_has_test_false(module_tree=tree, function_name="test_other") is False

    def test_returns_false_when_no_test_assignment_exists(self) -> None:
        """function_has_test_false() returns False with no __test__ assignment."""
        tree = ast.parse(source=SOURCE_STANDALONE_FUNCTION)
        assert function_has_test_false(module_tree=tree, function_name="test_standalone") is False

    def test_matches_correct_function_among_multiple(self) -> None:
        """function_has_test_false() only matches the specific function name."""
        tree = ast.parse(source=SOURCE_FUNCTION_TEST_FALSE_DIFFERENT_NAME)
        assert function_has_test_false(module_tree=tree, function_name="test_alpha") is True
        assert function_has_test_false(module_tree=tree, function_name="test_beta") is False


# ===========================================================================
# Tests for method_has_test_false()
# ===========================================================================


class TestMethodHasTestFalse:
    """Tests for the method_has_test_false() function."""

    def test_returns_true_when_method_has_test_false(self) -> None:
        """method_has_test_false() detects method.__test__ = False in class body."""
        class_node = _get_first_class_node(source=SOURCE_METHOD_TEST_FALSE)
        assert method_has_test_false(class_node=class_node, method_name="test_alpha") is True

    def test_returns_false_for_non_matching_method_name(self) -> None:
        """method_has_test_false() returns False for a different method name."""
        class_node = _get_first_class_node(source=SOURCE_METHOD_TEST_FALSE)
        assert method_has_test_false(class_node=class_node, method_name="test_beta") is False

    def test_returns_false_when_no_test_assignment_exists(self) -> None:
        """method_has_test_false() returns False with no __test__ assignment."""
        class_node = _get_first_class_node(source=SOURCE_TWO_METHODS)
        assert method_has_test_false(class_node=class_node, method_name="test_alpha") is False


# ===========================================================================
# Tests for get_test_methods_from_class()
# ===========================================================================


class TestGetTestMethodsFromClass:
    """Tests for the get_test_methods_from_class() function."""

    def test_returns_raw_test_method_names(self) -> None:
        """get_test_methods_from_class() returns raw test method names."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_TEST_FALSE)
        result = get_test_methods_from_class(class_node=class_node)
        assert result == ["test_bar", "test_baz"]

    def test_excludes_non_test_methods(self) -> None:
        """get_test_methods_from_class() excludes helper methods, __init__, etc."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_WITH_MIXED_METHODS)
        result = get_test_methods_from_class(class_node=class_node)
        assert result == ["test_one", "test_two"]

    def test_returns_empty_list_for_no_test_methods(self) -> None:
        """get_test_methods_from_class() returns empty list when no test_ methods."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_NO_TEST_METHODS)
        result = get_test_methods_from_class(class_node=class_node)
        assert result == []


# ===========================================================================
# Tests for scan_placeholder_tests()
# ===========================================================================


class TestScanPlaceholderTests:
    """Tests for the scan_placeholder_tests() function."""

    def test_module_level_test_false_reports_all_classes_and_functions(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports all classes and functions when module has __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_example.py",
            content=(
                f"{TEST_FALSE_MARKER}\n\n"
                "class TestFoo:\n"
                "    def test_bar(self):\n"
                "        pass\n\n"
                "class TestBaz:\n"
                "    def test_qux(self):\n"
                "        pass\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert "tests/test_example.py" in result, (
            f"Expected key 'tests/test_example.py' in result, got keys: {list(result.keys())}"
        )
        entries = result["tests/test_example.py"]
        assert "tests/test_example.py::TestFoo" in entries, (
            f"Expected 'tests/test_example.py::TestFoo' in entries, got: {entries}"
        )
        assert "  - test_bar" in entries, f"Expected '  - test_bar' in entries, got: {entries}"
        assert "tests/test_example.py::TestBaz" in entries, (
            f"Expected 'tests/test_example.py::TestBaz' in entries, got: {entries}"
        )
        assert "  - test_qux" in entries, f"Expected '  - test_qux' in entries, got: {entries}"

    def test_module_level_test_false_reports_standalone_functions(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports standalone test functions under module-level __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_funcs.py",
            content=(f"{TEST_FALSE_MARKER}\n\ndef test_alpha():\n    pass\n\ndef test_beta():\n    pass\n"),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert "tests/test_funcs.py" in result, (
            f"Expected key 'tests/test_funcs.py' in result, got keys: {list(result.keys())}"
        )
        entries = result["tests/test_funcs.py"]
        assert "tests/test_funcs.py" in entries, f"Expected 'tests/test_funcs.py' in entries, got: {entries}"
        assert "  - test_alpha" in entries, f"Expected '  - test_alpha' in entries, got: {entries}"
        assert "  - test_beta" in entries, f"Expected '  - test_beta' in entries, got: {entries}"

    def test_class_level_test_false_reports_class_and_methods(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports class and its methods when class has __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_cls.py",
            content=(
                "class TestFoo:\n"
                f"    {TEST_FALSE_MARKER}\n\n"
                "    def test_bar(self):\n"
                "        pass\n\n"
                "    def test_baz(self):\n"
                "        pass\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert "tests/test_cls.py" in result, (
            f"Expected key 'tests/test_cls.py' in result, got keys: {list(result.keys())}"
        )
        entries = result["tests/test_cls.py"]
        assert "tests/test_cls.py::TestFoo" in entries, (
            f"Expected 'tests/test_cls.py::TestFoo' in entries, got: {entries}"
        )
        assert "  - test_bar" in entries, f"Expected '  - test_bar' in entries, got: {entries}"
        assert "  - test_baz" in entries, f"Expected '  - test_baz' in entries, got: {entries}"

    def test_method_level_test_false_reports_only_that_method(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports only the specific method with __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_meth.py",
            content=(
                "class TestFoo:\n"
                "    def test_alpha(self):\n"
                "        pass\n\n"
                f"    test_alpha.{TEST_FALSE_MARKER}\n\n"
                "    def test_beta(self):\n"
                "        pass\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert "tests/test_meth.py" in result, (
            f"Expected key 'tests/test_meth.py' in result, got keys: {list(result.keys())}"
        )
        entries = result["tests/test_meth.py"]
        assert "tests/test_meth.py::TestFoo" in entries, (
            f"Expected 'tests/test_meth.py::TestFoo' in entries, got: {entries}"
        )
        assert "  - test_alpha" in entries, f"Expected '  - test_alpha' in entries, got: {entries}"
        assert "  - test_beta" not in entries, f"Unexpected '  - test_beta' found in entries: {entries}"

    def test_function_level_test_false_reports_only_that_function(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports only the function with func.__test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_func.py",
            content=(f"def test_alpha():\n    pass\n\ntest_alpha.{TEST_FALSE_MARKER}\n\ndef test_beta():\n    pass\n"),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert "tests/test_func.py" in result, (
            f"Expected key 'tests/test_func.py' in result, got keys: {list(result.keys())}"
        )
        entries = result["tests/test_func.py"]
        assert "  - test_alpha" in entries, f"Expected '  - test_alpha' in entries, got: {entries}"
        assert "  - test_beta" not in entries, f"Unexpected '  - test_beta' found in entries: {entries}"

    def test_skips_files_without_test_false(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() skips files that do not contain __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_normal.py",
            content=("class TestFoo:\n    def test_bar(self):\n        assert True\n"),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result == {}

    def test_handles_syntax_errors_gracefully(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() logs warning and continues on syntax errors."""
        _create_test_file(
            directory=tests_dir,
            filename="test_broken.py",
            content=f"{TEST_FALSE_MARKER}\n\ndef this is not valid python:\n",
        )
        _create_test_file(
            directory=tests_dir,
            filename="test_valid.py",
            content=(f"{TEST_FALSE_MARKER}\n\nclass TestGood:\n    def test_pass(self):\n        pass\n"),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        # Broken file should be skipped, valid file should be included
        assert "tests/test_broken.py" not in result, (
            f"Unexpected key 'tests/test_broken.py' in result: {list(result.keys())}"
        )
        assert "tests/test_valid.py" in result, (
            f"Expected key 'tests/test_valid.py' in result, got keys: {list(result.keys())}"
        )

    def test_returns_empty_dict_when_no_test_files(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() returns empty dict when no test files exist."""
        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result == {}

    def test_scans_subdirectories_recursively(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() finds test files in nested subdirectories."""
        sub_dir = tests_dir / "network" / "ipv6"
        sub_dir.mkdir(parents=True)
        _create_test_file(
            directory=sub_dir,
            filename="test_deep.py",
            content=(f"{TEST_FALSE_MARKER}\n\nclass TestDeep:\n    def test_nested(self):\n        pass\n"),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected at least one entry from nested test file"
        found_keys = list(result.keys())
        assert any("test_deep.py" in key for key in found_keys)

    def test_ignores_non_test_files(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() only processes files matching test_*.py pattern."""
        _create_test_file(
            directory=tests_dir,
            filename="conftest.py",
            content=f"{TEST_FALSE_MARKER}\n\ndef fixture():\n    pass\n",
        )
        _create_test_file(
            directory=tests_dir,
            filename="helper.py",
            content=f"{TEST_FALSE_MARKER}\n\ndef helper():\n    pass\n",
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result == {}


# ===========================================================================
# Tests for output_text() and output_json()
# ===========================================================================


class TestOutputFunctions:
    """Tests for output_text() and output_json() functions."""

    SAMPLE_PLACEHOLDER_FILES: dict[str, list[str]] = {
        "tests/test_foo.py": [
            "tests/test_foo.py::TestFoo",
            "  - test_bar",
            "  - test_baz",
        ],
        "tests/test_standalone.py": [
            "tests/test_standalone.py",
            "  - test_alpha",
        ],
    }

    def test_output_json_structure(self, capsys: pytest.CaptureFixture[str]) -> None:
        """output_json() produces valid JSON with correct totals and file entries."""
        output_json(placeholder_files=self.SAMPLE_PLACEHOLDER_FILES)
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert result["total_tests"] == 3, f"Expected 3 total tests, got {result['total_tests']}"
        assert result["total_files"] == 2, f"Expected 2 total files, got {result['total_files']}"
        assert "tests/test_foo.py" in result["files"], (
            f"Missing tests/test_foo.py in files, got keys: {list(result['files'].keys())}"
        )
        assert result["files"]["tests/test_foo.py"] == ["test_bar", "test_baz"], (
            f"Expected ['test_bar', 'test_baz'], got {result['files']['tests/test_foo.py']}"
        )
        assert result["files"]["tests/test_standalone.py"] == ["test_alpha"], (
            f"Expected ['test_alpha'], got {result['files']['tests/test_standalone.py']}"
        )

    def test_output_json_empty_input(self, capsys: pytest.CaptureFixture[str]) -> None:
        """output_json() produces correct JSON for empty input."""
        output_json(placeholder_files={})
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert result["total_tests"] == 0, f"Expected 0 total tests, got {result['total_tests']}"
        assert result["total_files"] == 0, f"Expected 0 total files, got {result['total_files']}"
        assert result["files"] == {}, f"Expected empty files dict, got: {result['files']}"

    def test_output_text_counts_only_files_with_tests(self) -> None:
        """output_text() counts only files that have test entries in the total."""
        placeholder_files: dict[str, list[str]] = {
            "tests/test_foo.py": [
                "tests/test_foo.py::TestFoo",
                "  - test_bar",
            ],
            "tests/test_empty.py": [
                "tests/test_empty.py::TestEmpty",
            ],
        }
        handler = logging.Handler()
        messages: list[str] = []
        handler.emit = lambda record: messages.append(record.getMessage())
        logger = logging.getLogger(name="scripts.std_placeholder_stats.std_placeholder_stats")
        logger.addHandler(hdlr=handler)
        try:
            output_text(placeholder_files=placeholder_files)
        finally:
            logger.removeHandler(hdlr=handler)

        summary_line = [line for line in messages if "Total:" in line]
        assert summary_line, f"Expected 'Total:' summary line in log output, got: {messages}"
        assert "1 placeholder tests in 1 files" in summary_line[0], (
            f"Expected '1 placeholder tests in 1 files', got: {summary_line[0]}"
        )
