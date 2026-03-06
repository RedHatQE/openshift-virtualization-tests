"""Unit tests for STD Placeholder Stats Generator.

Tests cover all public functions in std_placeholder_stats.py including
AST-based analysis functions and the directory scanner.

Generated-by: Claude
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import ClassVar

import pytest

from scripts.std_placeholder_stats.std_placeholder_stats import (
    PlaceholderClass,
    PlaceholderFile,
    _format_disabled_lines,
    _format_placeholder_lines,
    _statements_have_test_false,
    count_disabled_tests,
    count_placeholder_tests,
    get_disabled_methods_from_class,
    get_test_methods_from_class,
    output_json,
    output_text,
    scan_placeholder_tests,
    separator,
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
        \"\"\"Placeholder test.\"\"\"
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
        \"\"\"Placeholder test.\"\"\"

    def test_baz(self):
        \"\"\"Placeholder test.\"\"\"
"""

SOURCE_FUNCTION_TEST_FALSE = f"""\
def test_standalone():
    \"\"\"Placeholder test.\"\"\"

test_standalone.{TEST_FALSE_MARKER}
"""

SOURCE_FUNCTION_TEST_FALSE_DIFFERENT_NAME = f"""\
def test_alpha():
    \"\"\"Placeholder test.\"\"\"

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
        \"\"\"Placeholder test.\"\"\"

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
        \"\"\"Placeholder test.\"\"\"

    def test_two(self):
        \"\"\"Placeholder test.\"\"\"

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


def _find_placeholder_file(result: list[PlaceholderFile], file_path: str) -> PlaceholderFile:
    """Find a PlaceholderFile by file_path in scan results.

    Args:
        result: List of PlaceholderFile objects from scan_placeholder_tests.
        file_path: The file path to search for.

    Returns:
        The matching PlaceholderFile.

    Raises:
        AssertionError: If no matching PlaceholderFile is found.
    """
    placeholder = next(
        (pf for pf in result if pf.file_path == file_path),
        None,
    )
    assert placeholder is not None, (
        f"Expected PlaceholderFile for '{file_path}', got file_paths: {[pf.file_path for pf in result]}"
    )
    return placeholder


def _find_placeholder_class(placeholder: PlaceholderFile, class_name: str) -> PlaceholderClass:
    """Find a PlaceholderClass by name in a PlaceholderFile.

    Args:
        placeholder: The PlaceholderFile to search in.
        class_name: The class name to search for.

    Returns:
        The matching PlaceholderClass.

    Raises:
        AssertionError: If no matching PlaceholderClass is found.
    """
    found = next(
        (cls for cls in placeholder.classes if cls.name == class_name),
        None,
    )
    assert found is not None, f"Expected class '{class_name}', got: {[cls.name for cls in placeholder.classes]}"
    return found


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
# Tests for _statements_have_test_false() — module-level patterns
# ===========================================================================


class TestStatementsHaveTestFalseModule:
    """Tests for _statements_have_test_false() with module-level statements."""

    def test_returns_true_when_module_has_test_false(self) -> None:
        """_statements_have_test_false() detects __test__ = False at module level."""
        tree = ast.parse(source=SOURCE_MODULE_TEST_FALSE)
        assert _statements_have_test_false(statements=tree.body) is True

    def test_returns_false_when_no_test_assignment(self) -> None:
        """_statements_have_test_false() returns False with no __test__ assignment."""
        tree = ast.parse(source=SOURCE_NO_TEST_ASSIGNMENT)
        assert _statements_have_test_false(statements=tree.body) is False

    def test_ignores_class_level_test_false(self) -> None:
        """_statements_have_test_false() ignores __test__ = False inside classes."""
        tree = ast.parse(source=SOURCE_CLASS_TEST_FALSE)
        assert _statements_have_test_false(statements=tree.body) is False


# ===========================================================================
# Tests for _statements_have_test_false() — class-level patterns
# ===========================================================================


class TestStatementsHaveTestFalseClass:
    """Tests for _statements_have_test_false() with class body statements."""

    def test_returns_true_when_class_has_test_false(self) -> None:
        """_statements_have_test_false() detects __test__ = False in class body."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_TEST_FALSE)
        assert _statements_have_test_false(statements=class_node.body) is True

    def test_returns_false_when_no_test_assignment(self) -> None:
        """_statements_have_test_false() returns False with no __test__ assignment."""
        class_node = _get_first_class_node(source=SOURCE_NO_TEST_ASSIGNMENT)
        assert _statements_have_test_false(statements=class_node.body) is False

    def test_detects_test_false_in_class_with_mixed_methods(self) -> None:
        """_statements_have_test_false() detects __test__ = False even with non-test methods present."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_WITH_MIXED_METHODS)
        assert _statements_have_test_false(statements=class_node.body) is True


# ===========================================================================
# Tests for _statements_have_test_false() — function-level patterns
# ===========================================================================


class TestStatementsHaveTestFalseFunction:
    """Tests for _statements_have_test_false() with function-level attribute assignments."""

    def test_returns_true_when_function_has_test_false(self) -> None:
        """_statements_have_test_false() detects func.__test__ = False at module level."""
        tree = ast.parse(source=SOURCE_FUNCTION_TEST_FALSE)
        assert _statements_have_test_false(statements=tree.body, target_name="test_standalone") is True

    def test_returns_false_for_non_matching_function_name(self) -> None:
        """_statements_have_test_false() returns False for a different function name."""
        tree = ast.parse(source=SOURCE_FUNCTION_TEST_FALSE)
        assert _statements_have_test_false(statements=tree.body, target_name="test_other") is False

    def test_returns_false_when_no_test_assignment_exists(self) -> None:
        """_statements_have_test_false() returns False with no __test__ assignment."""
        tree = ast.parse(source=SOURCE_STANDALONE_FUNCTION)
        assert _statements_have_test_false(statements=tree.body, target_name="test_standalone") is False

    def test_matches_correct_function_among_multiple(self) -> None:
        """_statements_have_test_false() only matches the specific function name."""
        tree = ast.parse(source=SOURCE_FUNCTION_TEST_FALSE_DIFFERENT_NAME)
        assert _statements_have_test_false(statements=tree.body, target_name="test_alpha") is True
        assert _statements_have_test_false(statements=tree.body, target_name="test_beta") is False


# ===========================================================================
# Tests for _statements_have_test_false() — method-level patterns
# ===========================================================================


class TestStatementsHaveTestFalseMethod:
    """Tests for _statements_have_test_false() with method-level attribute assignments."""

    def test_returns_true_when_method_has_test_false(self) -> None:
        """_statements_have_test_false() detects method.__test__ = False in class body."""
        class_node = _get_first_class_node(source=SOURCE_METHOD_TEST_FALSE)
        assert _statements_have_test_false(statements=class_node.body, target_name="test_alpha") is True

    def test_returns_false_for_non_matching_method_name(self) -> None:
        """_statements_have_test_false() returns False for a different method name."""
        class_node = _get_first_class_node(source=SOURCE_METHOD_TEST_FALSE)
        assert _statements_have_test_false(statements=class_node.body, target_name="test_beta") is False

    def test_returns_false_when_no_test_assignment_exists(self) -> None:
        """_statements_have_test_false() returns False with no __test__ assignment."""
        class_node = _get_first_class_node(source=SOURCE_TWO_METHODS)
        assert _statements_have_test_false(statements=class_node.body, target_name="test_alpha") is False


# ===========================================================================
# Tests for get_test_methods_from_class()
# ===========================================================================


class TestGetTestMethodsFromClass:
    """Tests for the get_test_methods_from_class() function."""

    def test_returns_raw_test_method_names(self) -> None:
        """get_test_methods_from_class() returns raw test method names."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_TEST_FALSE)
        result = get_test_methods_from_class(class_node=class_node)
        assert result == ["test_bar", "test_baz"], f"Expected ['test_bar', 'test_baz'], got: {result}"

    def test_excludes_non_test_methods(self) -> None:
        """get_test_methods_from_class() excludes helper methods, __init__, etc."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_WITH_MIXED_METHODS)
        result = get_test_methods_from_class(class_node=class_node)
        assert result == ["test_one", "test_two"], f"Expected ['test_one', 'test_two'], got: {result}"

    def test_returns_empty_list_for_no_test_methods(self) -> None:
        """get_test_methods_from_class() returns empty list when no test_ methods."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_NO_TEST_METHODS)
        result = get_test_methods_from_class(class_node=class_node)
        assert result == [], f"Expected empty list, got: {result}"


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
                '        """Placeholder test."""\n\n'
                "class TestBaz:\n"
                "    def test_qux(self):\n"
                '        """Placeholder test."""\n'
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_example.py")
        class_names = [cls.name for cls in placeholder.classes]
        assert "TestFoo" in class_names, f"Expected 'TestFoo' in class names, got: {class_names}"
        assert "TestBaz" in class_names, f"Expected 'TestBaz' in class names, got: {class_names}"
        foo_class = _find_placeholder_class(placeholder=placeholder, class_name="TestFoo")
        assert "test_bar" in foo_class.test_methods, (
            f"Expected 'test_bar' in TestFoo methods, got: {foo_class.test_methods}"
        )
        baz_class = _find_placeholder_class(placeholder=placeholder, class_name="TestBaz")
        assert "test_qux" in baz_class.test_methods, (
            f"Expected 'test_qux' in TestBaz methods, got: {baz_class.test_methods}"
        )

    def test_module_level_test_false_reports_standalone_functions(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports standalone test functions under module-level __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_funcs.py",
            content=f'{TEST_FALSE_MARKER}\n\ndef test_alpha():\n    """Placeholder test."""\n\ndef test_beta():\n    """Placeholder test."""\n',
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_funcs.py")
        assert "test_alpha" in placeholder.standalone_tests, (
            f"Expected 'test_alpha' in standalone_tests, got: {placeholder.standalone_tests}"
        )
        assert "test_beta" in placeholder.standalone_tests, (
            f"Expected 'test_beta' in standalone_tests, got: {placeholder.standalone_tests}"
        )

    def test_class_level_test_false_reports_class_and_methods(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports class and its methods when class has __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_cls.py",
            content=(
                "class TestFoo:\n"
                f"    {TEST_FALSE_MARKER}\n\n"
                "    def test_bar(self):\n"
                '        """Placeholder test."""\n\n'
                "    def test_baz(self):\n"
                '        """Placeholder test."""\n'
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_cls.py")
        assert placeholder.classes, "Expected at least one PlaceholderClass"
        foo_class = _find_placeholder_class(placeholder=placeholder, class_name="TestFoo")
        assert "test_bar" in foo_class.test_methods, (
            f"Expected 'test_bar' in TestFoo methods, got: {foo_class.test_methods}"
        )
        assert "test_baz" in foo_class.test_methods, (
            f"Expected 'test_baz' in TestFoo methods, got: {foo_class.test_methods}"
        )

    def test_method_level_test_false_reports_only_that_method(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports only the specific method with __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_meth.py",
            content=(
                "class TestFoo:\n"
                "    def test_alpha(self):\n"
                '        """Placeholder test."""\n\n'
                f"    test_alpha.{TEST_FALSE_MARKER}\n\n"
                "    def test_beta(self):\n"
                "        pass\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_meth.py")
        foo_class = _find_placeholder_class(placeholder=placeholder, class_name="TestFoo")
        assert "test_alpha" in foo_class.test_methods, (
            f"Expected 'test_alpha' in TestFoo methods, got: {foo_class.test_methods}"
        )
        assert "test_beta" not in foo_class.test_methods, (
            f"Unexpected 'test_beta' found in TestFoo methods: {foo_class.test_methods}"
        )

    def test_function_level_test_false_reports_only_that_function(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() reports only the function with func.__test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_func.py",
            content=f'def test_alpha():\n    """Placeholder test."""\n\ntest_alpha.{TEST_FALSE_MARKER}\n\ndef test_beta():\n    pass\n',
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_func.py")
        assert "test_alpha" in placeholder.standalone_tests, (
            f"Expected 'test_alpha' in standalone_tests, got: {placeholder.standalone_tests}"
        )
        assert "test_beta" not in placeholder.standalone_tests, (
            f"Unexpected 'test_beta' found in standalone_tests: {placeholder.standalone_tests}"
        )

    def test_skips_files_without_test_false(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() skips files that do not contain __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_normal.py",
            content="class TestFoo:\n    def test_bar(self):\n        assert True\n",
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result == []

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
            content=f'{TEST_FALSE_MARKER}\n\nclass TestGood:\n    def test_pass(self):\n        """Placeholder test."""\n',
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        file_paths = [pf.file_path for pf in result]
        assert "tests/test_broken.py" not in file_paths, f"Unexpected 'tests/test_broken.py' in result: {file_paths}"
        assert "tests/test_valid.py" in file_paths, f"Expected 'tests/test_valid.py' in result, got: {file_paths}"

    def test_returns_empty_list_when_no_test_files(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() returns empty list when no test files exist."""
        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result == []

    def test_scans_subdirectories_recursively(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() finds test files in nested subdirectories."""
        sub_dir = tests_dir / "network" / "ipv6"
        sub_dir.mkdir(parents=True)
        _create_test_file(
            directory=sub_dir,
            filename="test_deep.py",
            content=f'{TEST_FALSE_MARKER}\n\nclass TestDeep:\n    def test_nested(self):\n        """Placeholder test."""\n',
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected at least one entry from nested test file"
        file_paths = [pf.file_path for pf in result]
        assert any("test_deep.py" in path for path in file_paths), (
            f"Expected a file_path containing 'test_deep.py' in results, got: {file_paths}"
        )

    def test_handles_unreadable_files_gracefully(
        self,
        tests_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """scan_placeholder_tests() logs warning and continues on read errors."""
        unreadable = _create_test_file(
            directory=tests_dir,
            filename="test_unreadable.py",
            content=f'{TEST_FALSE_MARKER}\n\nclass TestFoo:\n    def test_bar(self):\n        """Placeholder."""\n',
        )
        _create_test_file(
            directory=tests_dir,
            filename="test_readable.py",
            content=f'{TEST_FALSE_MARKER}\n\nclass TestGood:\n    def test_pass(self):\n        """Placeholder."""\n',
        )

        original_read_text = Path.read_text

        def fake_read_text(path_self: Path, *args: object, **kwargs: object) -> str:
            if path_self == unreadable:
                raise OSError("simulated read failure")
            return original_read_text(path_self, *args, **kwargs)

        monkeypatch.setattr(target=Path, name="read_text", value=fake_read_text)

        result = scan_placeholder_tests(tests_dir=tests_dir)

        file_paths = [pf.file_path for pf in result]
        assert "tests/test_unreadable.py" not in file_paths, (
            f"Unexpected 'tests/test_unreadable.py' in result: {file_paths}"
        )
        assert "tests/test_readable.py" in file_paths, f"Expected 'tests/test_readable.py' in result, got: {file_paths}"

    def test_async_placeholder_and_disabled_detected(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() detects async test methods as placeholders and disabled."""
        _create_test_file(
            directory=tests_dir,
            filename="test_async.py",
            content=(
                "class TestAsync:\n"
                f"    {TEST_FALSE_MARKER}\n\n"
                "    async def test_async_placeholder(self):\n"
                '        """This async test is a placeholder."""\n\n'
                "    async def test_async_disabled(self):\n"
                '        """This async test has implementation."""\n'
                "        await some_function()\n"
                "        assert True\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_async.py")
        async_class = _find_placeholder_class(placeholder=placeholder, class_name="TestAsync")
        assert "test_async_placeholder" in async_class.test_methods, (
            f"Expected 'test_async_placeholder' in test_methods, got: {async_class.test_methods}"
        )
        assert "test_async_disabled" in async_class.disabled_methods, (
            f"Expected 'test_async_disabled' in disabled_methods, got: {async_class.disabled_methods}"
        )

    def test_async_standalone_placeholder_detected(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() detects standalone async placeholder test functions."""
        _create_test_file(
            directory=tests_dir,
            filename="test_async_standalone.py",
            content=(f'{TEST_FALSE_MARKER}\n\nasync def test_async_standalone():\n    """Async placeholder test."""\n'),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_async_standalone.py")
        assert "test_async_standalone" in placeholder.standalone_tests, (
            f"Expected 'test_async_standalone' in standalone_tests, got: {placeholder.standalone_tests}"
        )

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

        assert result == []


# ===========================================================================
# Tests for output_text() and output_json()
# ===========================================================================


class TestOutputFunctions:
    """Tests for output_text() and output_json() functions."""

    SAMPLE_PLACEHOLDER_FILES: ClassVar[list[PlaceholderFile]] = [
        PlaceholderFile(
            file_path="tests/test_foo.py",
            classes=[
                PlaceholderClass(
                    name="TestFoo",
                    test_methods=["test_bar", "test_baz"],
                    disabled_methods=["test_implemented"],
                )
            ],
        ),
        PlaceholderFile(
            file_path="tests/test_standalone.py",
            standalone_tests=["test_alpha"],
        ),
    ]

    def test_output_json_structure(self, capsys: pytest.CaptureFixture[str]) -> None:
        """output_json() produces valid JSON with correct totals and file entries."""
        output_json(placeholder_files=self.SAMPLE_PLACEHOLDER_FILES)
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        placeholder = result["placeholder"]
        assert placeholder["total_tests"] == 3, f"Expected 3 total tests, got {placeholder['total_tests']}"
        assert placeholder["total_files"] == 2, f"Expected 2 total files, got {placeholder['total_files']}"
        assert "tests/test_foo.py" in placeholder["files"], (
            f"Missing tests/test_foo.py in files, got keys: {list(placeholder['files'].keys())}"
        )
        assert placeholder["files"]["tests/test_foo.py"] == ["TestFoo::test_bar", "TestFoo::test_baz"], (
            f"Expected ['TestFoo::test_bar', 'TestFoo::test_baz'], got {placeholder['files']['tests/test_foo.py']}"
        )
        assert placeholder["files"]["tests/test_standalone.py"] == ["test_alpha"], (
            f"Expected ['test_alpha'], got {placeholder['files']['tests/test_standalone.py']}"
        )

        disabled = result["disabled"]
        assert disabled["total_tests"] == 1, f"Expected 1 disabled test, got {disabled['total_tests']}"
        assert disabled["total_files"] == 1, f"Expected 1 file with disabled tests, got {disabled['total_files']}"
        assert disabled["files"]["tests/test_foo.py"] == ["TestFoo::test_implemented"], (
            f"Expected ['TestFoo::test_implemented'], got {disabled['files']['tests/test_foo.py']}"
        )

    def test_output_json_empty_input(self, capsys: pytest.CaptureFixture[str]) -> None:
        """output_json() produces correct JSON for empty input."""
        output_json(placeholder_files=[])
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        placeholder = result["placeholder"]
        assert placeholder["total_tests"] == 0, f"Expected 0 total tests, got {placeholder['total_tests']}"
        assert placeholder["total_files"] == 0, f"Expected 0 total files, got {placeholder['total_files']}"
        assert placeholder["files"] == {}, f"Expected empty files dict, got: {placeholder['files']}"

        disabled = result["disabled"]
        assert disabled["total_tests"] == 0, f"Expected 0 disabled tests, got {disabled['total_tests']}"
        assert disabled["total_files"] == 0, f"Expected 0 disabled files, got {disabled['total_files']}"
        assert disabled["files"] == {}, f"Expected empty disabled files dict, got: {disabled['files']}"

    def test_output_text_counts_only_files_with_tests(self, caplog: pytest.LogCaptureFixture) -> None:
        """output_text() counts only files that have test entries in the total."""
        placeholder_files: list[PlaceholderFile] = [
            PlaceholderFile(
                file_path="tests/test_foo.py",
                classes=[PlaceholderClass(name="TestFoo", test_methods=["test_bar"])],
            ),
        ]
        logger = logging.getLogger(name="scripts.std_placeholder_stats.std_placeholder_stats")
        original_propagate = logger.propagate
        logger.propagate = True
        try:
            with caplog.at_level(level=logging.INFO, logger="scripts.std_placeholder_stats.std_placeholder_stats"):
                output_text(placeholder_files=placeholder_files)
        finally:
            logger.propagate = original_propagate

        summary_line = [line for line in caplog.messages if "Total:" in line]
        assert summary_line, f"Expected 'Total:' summary line in log output, got: {caplog.messages}"
        assert "1 placeholder test in 1 file" in summary_line[0], (
            f"Expected '1 placeholder test in 1 file', got: {summary_line[0]}"
        )

    def test_output_text_empty_input(self, caplog: pytest.LogCaptureFixture) -> None:
        """output_text() logs 'no placeholder tests found' for empty input."""
        logger = logging.getLogger(name="scripts.std_placeholder_stats.std_placeholder_stats")
        original_propagate = logger.propagate
        logger.propagate = True
        try:
            with caplog.at_level(level=logging.INFO, logger="scripts.std_placeholder_stats.std_placeholder_stats"):
                output_text(placeholder_files=[])
        finally:
            logger.propagate = original_propagate

        assert any("No STD placeholder or disabled tests found" in msg for msg in caplog.messages), (
            f"Expected 'No STD placeholder or disabled tests found' in log output, got: {caplog.messages}"
        )


# ===========================================================================
# Tests for separator()
# ===========================================================================


class TestSeparator:
    """Tests for the separator() function."""

    def test_plain_separator(self) -> None:
        """separator() creates a line of repeated symbols."""
        result = separator(symbol="=")
        assert result == "=" * 120, f"Expected 120 '=' chars, got length {len(result)}"

    def test_separator_with_title(self) -> None:
        """separator() centers title text in the separator line."""
        result = separator(symbol="=", title="HELLO")
        assert "HELLO" in result, f"Expected 'HELLO' in separator, got: {result}"
        assert result.startswith("="), f"Expected separator to start with '=', got: {result}"
        assert result.endswith("="), f"Expected separator to end with '=', got: {result}"

    def test_separator_with_different_symbol(self) -> None:
        """separator() works with different symbol characters."""
        result = separator(symbol="-")
        assert result == "-" * 120, f"Expected 120 '-' chars, got length {len(result)}"


# ===========================================================================
# Tests for count_placeholder_tests()
# ===========================================================================


class TestCountPlaceholderTests:
    """Tests for the count_placeholder_tests() function."""

    def test_counts_tests_and_files(self) -> None:
        """count_placeholder_tests() returns correct totals."""
        placeholder_files = [
            PlaceholderFile(
                file_path="tests/test_a.py",
                classes=[PlaceholderClass(name="TestA", test_methods=["test_one", "test_two"])],
            ),
            PlaceholderFile(
                file_path="tests/test_b.py",
                standalone_tests=["test_three"],
            ),
        ]
        total_tests, total_files = count_placeholder_tests(placeholder_files=placeholder_files)
        assert total_tests == 3, f"Expected 3 total tests, got {total_tests}"
        assert total_files == 2, f"Expected 2 total files, got {total_files}"

    def test_empty_input(self) -> None:
        """count_placeholder_tests() returns zeros for empty input."""
        total_tests, total_files = count_placeholder_tests(placeholder_files=[])
        assert total_tests == 0, f"Expected 0 total tests, got {total_tests}"
        assert total_files == 0, f"Expected 0 total files, got {total_files}"


# ===========================================================================
# Tests for _format_placeholder_lines()
# ===========================================================================


class TestFormatPlaceholderLines:
    """Tests for the _format_placeholder_lines() function."""

    def test_formats_class_entries(self) -> None:
        """_format_placeholder_lines() formats class entries with file path prefix."""
        placeholder = PlaceholderFile(
            file_path="tests/test_foo.py",
            classes=[PlaceholderClass(name="TestFoo", test_methods=["test_bar", "test_baz"])],
        )
        lines = _format_placeholder_lines(placeholder_file=placeholder)
        assert lines[0] == "tests/test_foo.py::TestFoo", f"Expected class header, got: {lines[0]}"
        assert "  - test_bar" in lines, f"Expected '  - test_bar' in lines, got: {lines}"
        assert "  - test_baz" in lines, f"Expected '  - test_baz' in lines, got: {lines}"

    def test_formats_standalone_entries(self) -> None:
        """_format_placeholder_lines() formats standalone tests with <standalone> label."""
        placeholder = PlaceholderFile(
            file_path="tests/test_foo.py",
            standalone_tests=["test_alpha"],
        )
        lines = _format_placeholder_lines(placeholder_file=placeholder)
        assert lines[0] == "tests/test_foo.py::<standalone>", f"Expected standalone header, got: {lines[0]}"
        assert "  - test_alpha" in lines, f"Expected '  - test_alpha' in lines, got: {lines}"


# ===========================================================================
# Tests for get_disabled_methods_from_class()
# ===========================================================================


class TestGetDisabledMethodsFromClass:
    """Tests for the get_disabled_methods_from_class() function."""

    def test_returns_implemented_test_methods(self) -> None:
        """get_disabled_methods_from_class() returns test methods with implementation."""
        source = (
            "class TestFoo:\n"
            "    def test_placeholder(self):\n"
            '        """Placeholder test."""\n\n'
            "    def test_implemented(self):\n"
            '        """Has code."""\n'
            "        assert True\n"
        )
        class_node = _get_first_class_node(source=source)
        result = get_disabled_methods_from_class(class_node=class_node)
        assert result == ["test_implemented"], f"Expected ['test_implemented'], got: {result}"

    def test_excludes_placeholder_methods(self) -> None:
        """get_disabled_methods_from_class() excludes docstring-only methods."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_TEST_FALSE)
        result = get_disabled_methods_from_class(class_node=class_node)
        assert result == [], f"Expected empty list, got: {result}"

    def test_excludes_non_test_methods(self) -> None:
        """get_disabled_methods_from_class() excludes helper methods."""
        class_node = _get_first_class_node(source=SOURCE_CLASS_NO_TEST_METHODS)
        result = get_disabled_methods_from_class(class_node=class_node)
        assert result == [], f"Expected empty list, got: {result}"


# ===========================================================================
# Tests for disabled test detection in scan_placeholder_tests()
# ===========================================================================


class TestDisabledTestDetection:
    """Tests for disabled test detection in scan_placeholder_tests()."""

    def test_module_level_test_false_separates_placeholder_and_disabled(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() separates placeholder (docstring-only) from disabled (implemented) tests."""
        _create_test_file(
            directory=tests_dir,
            filename="test_mixed.py",
            content=(
                f"{TEST_FALSE_MARKER}\n\n"
                "class TestMixed:\n"
                "    def test_placeholder(self):\n"
                '        """This test is not yet implemented."""\n\n'
                "    def test_implemented(self):\n"
                '        """This test has code."""\n'
                "        assert True\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_mixed.py")
        mixed_class = _find_placeholder_class(placeholder=placeholder, class_name="TestMixed")
        assert "test_placeholder" in mixed_class.test_methods, (
            f"Expected 'test_placeholder' in placeholder methods, got: {mixed_class.test_methods}"
        )
        assert "test_implemented" in mixed_class.disabled_methods, (
            f"Expected 'test_implemented' in disabled methods, got: {mixed_class.disabled_methods}"
        )
        assert "test_implemented" not in mixed_class.test_methods, (
            f"Unexpected 'test_implemented' in placeholder methods: {mixed_class.test_methods}"
        )

    def test_standalone_disabled_function_detected(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() detects standalone disabled functions with implementation."""
        _create_test_file(
            directory=tests_dir,
            filename="test_disabled_func.py",
            content=(
                "def test_with_code():\n"
                '    """Has implementation."""\n'
                "    assert 1 + 1 == 2\n\n"
                f"test_with_code.{TEST_FALSE_MARKER}\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_disabled_func.py")
        assert "test_with_code" in placeholder.disabled_standalone_tests, (
            f"Expected 'test_with_code' in disabled_standalone_tests, got: {placeholder.disabled_standalone_tests}"
        )
        assert "test_with_code" not in placeholder.standalone_tests, (
            f"Unexpected 'test_with_code' in placeholder standalone_tests: {placeholder.standalone_tests}"
        )

    def test_class_level_test_false_separates_placeholder_and_disabled(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() separates categories at class level __test__ = False."""
        _create_test_file(
            directory=tests_dir,
            filename="test_cls_mixed.py",
            content=(
                "class TestFoo:\n"
                f"    {TEST_FALSE_MARKER}\n\n"
                "    def test_placeholder(self):\n"
                '        """Placeholder test."""\n\n'
                "    def test_implemented(self):\n"
                '        """Has code."""\n'
                "        assert True\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_cls_mixed.py")
        foo_class = _find_placeholder_class(placeholder=placeholder, class_name="TestFoo")
        assert "test_placeholder" in foo_class.test_methods, (
            f"Expected 'test_placeholder' in test_methods, got: {foo_class.test_methods}"
        )
        assert "test_implemented" in foo_class.disabled_methods, (
            f"Expected 'test_implemented' in disabled_methods, got: {foo_class.disabled_methods}"
        )

    def test_method_level_disabled_detected(self, tests_dir: Path) -> None:
        """scan_placeholder_tests() detects method-level disabled tests with implementation."""
        _create_test_file(
            directory=tests_dir,
            filename="test_meth_disabled.py",
            content=(
                "class TestFoo:\n"
                "    def test_implemented(self):\n"
                '        """Has code."""\n'
                "        assert True\n\n"
                f"    test_implemented.{TEST_FALSE_MARKER}\n\n"
                "    def test_normal(self):\n"
                "        assert True\n"
            ),
        )

        result = scan_placeholder_tests(tests_dir=tests_dir)

        assert result, "Expected non-empty result list"
        placeholder = _find_placeholder_file(result=result, file_path="tests/test_meth_disabled.py")
        foo_class = _find_placeholder_class(placeholder=placeholder, class_name="TestFoo")
        assert "test_implemented" in foo_class.disabled_methods, (
            f"Expected 'test_implemented' in disabled_methods, got: {foo_class.disabled_methods}"
        )
        assert "test_implemented" not in foo_class.test_methods, (
            f"Unexpected 'test_implemented' in test_methods: {foo_class.test_methods}"
        )


# ===========================================================================
# Tests for count_disabled_tests()
# ===========================================================================


class TestCountDisabledTests:
    """Tests for the count_disabled_tests() function."""

    def test_counts_disabled_tests_and_files(self) -> None:
        """count_disabled_tests() returns correct totals."""
        placeholder_files = [
            PlaceholderFile(
                file_path="tests/test_a.py",
                classes=[PlaceholderClass(name="TestA", disabled_methods=["test_disabled"])],
            ),
            PlaceholderFile(
                file_path="tests/test_b.py",
                standalone_tests=["test_placeholder"],
            ),
        ]
        total_disabled, disabled_files = count_disabled_tests(placeholder_files=placeholder_files)
        assert total_disabled == 1, f"Expected 1 disabled test, got {total_disabled}"
        assert disabled_files == 1, f"Expected 1 file with disabled tests, got {disabled_files}"

    def test_empty_input(self) -> None:
        """count_disabled_tests() returns zeros for empty input."""
        total_disabled, disabled_files = count_disabled_tests(placeholder_files=[])
        assert total_disabled == 0, f"Expected 0 disabled tests, got {total_disabled}"
        assert disabled_files == 0, f"Expected 0 files, got {disabled_files}"


# ===========================================================================
# Tests for _format_disabled_lines()
# ===========================================================================


class TestFormatDisabledLines:
    """Tests for the _format_disabled_lines() function."""

    def test_formats_disabled_entries(self) -> None:
        """_format_disabled_lines() formats disabled test entries."""
        placeholder = PlaceholderFile(
            file_path="tests/test_foo.py",
            classes=[PlaceholderClass(name="TestFoo", disabled_methods=["test_implemented"])],
        )
        lines = _format_disabled_lines(placeholder_file=placeholder)
        assert lines[0] == "tests/test_foo.py::TestFoo", f"Expected class header, got: {lines[0]}"
        assert "  - test_implemented" in lines, f"Expected '  - test_implemented' in lines, got: {lines}"

    def test_formats_standalone_disabled_entries(self) -> None:
        """_format_disabled_lines() formats standalone disabled tests."""
        placeholder = PlaceholderFile(
            file_path="tests/test_foo.py",
            disabled_standalone_tests=["test_disabled_func"],
        )
        lines = _format_disabled_lines(placeholder_file=placeholder)
        assert lines[0] == "tests/test_foo.py::<standalone>", f"Expected standalone header, got: {lines[0]}"
        assert "  - test_disabled_func" in lines, f"Expected '  - test_disabled_func' in lines, got: {lines}"

    def test_returns_empty_for_no_disabled(self) -> None:
        """_format_disabled_lines() returns empty list when no disabled tests."""
        placeholder = PlaceholderFile(
            file_path="tests/test_foo.py",
            classes=[PlaceholderClass(name="TestFoo", test_methods=["test_bar"])],
        )
        lines = _format_disabled_lines(placeholder_file=placeholder)
        assert lines == [], f"Expected empty list, got: {lines}"
