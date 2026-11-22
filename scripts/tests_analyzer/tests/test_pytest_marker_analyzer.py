"""
Unit tests for pytest_marker_analyzer hierarchical symbol analysis.

Co-authored-by: Claude <noreply@anthropic.com>
"""

from __future__ import annotations

import argparse
import ast
import base64
import json
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from scripts.tests_analyzer.pytest_marker_analyzer import (
    _OLD_REVISION_CACHE,
    AnalyzerGitError,
    AttributeAccessCollector,
    Fixture,
    ImportVisitor,
    MarkedTest,
    MarkerTestAnalyzer,
    SymbolClassification,
    _build_intra_class_call_graph,
    _build_line_to_symbol_map,
    _check_conftest_pathway,
    _collect_test_attribute_accesses,
    _collect_test_function_calls,
    _expand_modified_members_transitively,
    _extract_deleted_symbols_from_diff,
    _extract_modified_items_from_conftest,
    _extract_modified_symbols,
    _fetch_old_file_source,
    _get_modified_function_names,
    _is_fixture_decorator_standalone,
    _iter_diff_statements,
    _parse_diff_for_functions,
    main,
    run_github_mode,
    run_local_mode,
)

if TYPE_CHECKING:
    from pytest import CaptureFixture

# A (changed file, marked test, classification cache) conftest pathway.
Pathway = tuple[Path, MarkedTest, dict[Path, SymbolClassification | None]]


class TestBuildLineToSymbolMap:
    def test_top_level_function(self):
        source = textwrap.dedent("""\
            def hello():
                pass
        """)
        symbol_map = _build_line_to_symbol_map(source=source)
        names = [entry[2] for entry in symbol_map.top_level]
        assert "hello" in names

    def test_async_function(self):
        source = textwrap.dedent("""\
            async def async_hello():
                pass
        """)
        symbol_map = _build_line_to_symbol_map(source=source)
        names = [entry[2] for entry in symbol_map.top_level]
        assert "async_hello" in names

    def test_class_with_methods(self):
        source = textwrap.dedent("""\
            class MyClass:
                def method_a(self):
                    pass
                def method_b(self):
                    pass
        """)
        symbol_map = _build_line_to_symbol_map(source=source)
        top_level_names = [entry[2] for entry in symbol_map.top_level]
        assert "MyClass" in top_level_names
        assert "MyClass" in symbol_map.class_members
        member_info = symbol_map.class_members["MyClass"]
        assert "method_a" in member_info.members
        assert "method_b" in member_info.members

    def test_class_member_line_ranges(self):
        source = textwrap.dedent("""\
            class MyClass:
                def method_a(self):
                    x = 1
                    return x
                def method_b(self):
                    pass
        """)
        symbol_map = _build_line_to_symbol_map(source=source)
        member_info = symbol_map.class_members["MyClass"]
        start_a, end_a = member_info.members["method_a"]
        start_b, end_b = member_info.members["method_b"]
        assert start_a < end_a, "method_a should span multiple lines"
        assert start_b <= end_b, "method_b should have valid range"
        assert start_a < start_b, "method_a should come before method_b"

    def test_class_intra_call_graph(self):
        source = textwrap.dedent("""\
            class MyClass:
                def caller(self):
                    self.helper()
                def helper(self):
                    pass
        """)
        symbol_map = _build_line_to_symbol_map(source=source)
        member_info = symbol_map.class_members["MyClass"]
        assert "helper" in member_info.internal_calls["caller"]

    def test_module_level_assignment(self):
        source = "FOO = 42\n"
        symbol_map = _build_line_to_symbol_map(source=source)
        names = [entry[2] for entry in symbol_map.top_level]
        assert "FOO" in names

    def test_annotated_assignment(self):
        source = "FOO: int = 42\n"
        symbol_map = _build_line_to_symbol_map(source=source)
        names = [entry[2] for entry in symbol_map.top_level]
        assert "FOO" in names

    def test_empty_source(self):
        symbol_map = _build_line_to_symbol_map(source="")
        assert symbol_map.top_level == []
        assert symbol_map.class_members == {}

    def test_mixed_definitions(self):
        source = textwrap.dedent("""\
            FOO = 1

            def my_func():
                pass

            class MyClass:
                def method(self):
                    pass
        """)
        symbol_map = _build_line_to_symbol_map(source=source)
        names = [entry[2] for entry in symbol_map.top_level]
        assert "FOO" in names
        assert "my_func" in names
        assert "MyClass" in names
        assert "MyClass" in symbol_map.class_members

    def test_sorted_by_start_line(self):
        source = textwrap.dedent("""\
            def second_func():
                pass

            FOO = 1

            class MyClass:
                pass
        """)
        symbol_map = _build_line_to_symbol_map(source=source)
        start_lines = [entry[0] for entry in symbol_map.top_level]
        assert start_lines == sorted(start_lines), "top_level should be sorted by start line"


class TestBuildIntraClassCallGraph:
    def test_simple_self_call(self):
        source = textwrap.dedent("""\
            class MyClass:
                def method_a(self):
                    self.helper()
                def helper(self):
                    pass
        """)
        tree = ast.parse(source)
        class_node = tree.body[0]
        graph = _build_intra_class_call_graph(class_node=class_node)
        assert "helper" in graph["method_a"]

    def test_no_self_calls(self):
        source = textwrap.dedent("""\
            class MyClass:
                def method_a(self):
                    print("hello")
        """)
        tree = ast.parse(source)
        class_node = tree.body[0]
        graph = _build_intra_class_call_graph(class_node=class_node)
        assert graph["method_a"] == set()

    def test_multiple_callees(self):
        source = textwrap.dedent("""\
            class MyClass:
                def method_a(self):
                    self.helper_one()
                    self.helper_two()
                def helper_one(self):
                    pass
                def helper_two(self):
                    pass
        """)
        tree = ast.parse(source)
        class_node = tree.body[0]
        graph = _build_intra_class_call_graph(class_node=class_node)
        assert graph["method_a"] == {"helper_one", "helper_two"}

    def test_nested_self_call(self):
        source = textwrap.dedent("""\
            class MyClass:
                def method_a(self):
                    if True:
                        for i in range(10):
                            self.helper()
                def helper(self):
                    pass
        """)
        tree = ast.parse(source)
        class_node = tree.body[0]
        graph = _build_intra_class_call_graph(class_node=class_node)
        assert "helper" in graph["method_a"]

    def test_non_self_call_ignored(self):
        source = textwrap.dedent("""\
            class MyClass:
                def method_a(self):
                    other.method()
                    obj.do_thing()
        """)
        tree = ast.parse(source)
        class_node = tree.body[0]
        graph = _build_intra_class_call_graph(class_node=class_node)
        assert graph["method_a"] == set()


class TestExpandModifiedMembersTransitively:
    def test_no_expansion_needed(self):
        directly_modified = {"lonely_method"}
        internal_calls = {
            "other_method": {"unrelated"},
        }
        result = _expand_modified_members_transitively(
            directly_modified=directly_modified,
            internal_calls=internal_calls,
        )
        assert result == {"lonely_method"}

    def test_single_transitive_caller(self):
        directly_modified = {"helper"}
        internal_calls = {
            "caller": {"helper"},
            "helper": set(),
        }
        result = _expand_modified_members_transitively(
            directly_modified=directly_modified,
            internal_calls=internal_calls,
        )
        assert result == {"caller", "helper"}

    def test_chain_expansion(self):
        directly_modified = {"leaf"}
        internal_calls = {
            "top": {"middle"},
            "middle": {"leaf"},
            "leaf": set(),
        }
        result = _expand_modified_members_transitively(
            directly_modified=directly_modified,
            internal_calls=internal_calls,
        )
        assert result == {"top", "middle", "leaf"}

    def test_diamond_expansion(self):
        directly_modified = {"target"}
        internal_calls = {
            "caller_a": {"target"},
            "caller_b": {"target"},
            "target": set(),
        }
        result = _expand_modified_members_transitively(
            directly_modified=directly_modified,
            internal_calls=internal_calls,
        )
        assert result == {"caller_a", "caller_b", "target"}

    def test_empty_modified(self):
        internal_calls = {
            "method_a": {"method_b"},
            "method_b": set(),
        }
        result = _expand_modified_members_transitively(
            directly_modified=set(),
            internal_calls=internal_calls,
        )
        assert result == set()

    def test_cycle_handling(self):
        directly_modified = {"method_a"}
        internal_calls = {
            "method_a": {"method_b"},
            "method_b": {"method_a"},
        }
        result = _expand_modified_members_transitively(
            directly_modified=directly_modified,
            internal_calls=internal_calls,
        )
        assert result == {"method_a", "method_b"}


class TestAttributeAccessCollector:
    def test_simple_attribute(self):
        source = "obj.attr"
        tree = ast.parse(source)
        collector = AttributeAccessCollector()
        collector.visit(node=tree)
        assert "attr" in collector.accessed_attrs

    def test_multiple_attributes(self):
        source = textwrap.dedent("""\
            obj.x
            obj.y
        """)
        tree = ast.parse(source)
        collector = AttributeAccessCollector()
        collector.visit(node=tree)
        assert collector.accessed_attrs == {"x", "y"}

    def test_getattr_sets_dynamic(self):
        source = 'getattr(obj, "x")'
        tree = ast.parse(source)
        collector = AttributeAccessCollector()
        collector.visit(node=tree)
        assert collector.has_dynamic_access is True

    def test_setattr_sets_dynamic(self):
        source = 'setattr(obj, "x", value)'
        tree = ast.parse(source)
        collector = AttributeAccessCollector()
        collector.visit(node=tree)
        assert collector.has_dynamic_access is True

    def test_delattr_sets_dynamic(self):
        source = 'delattr(obj, "x")'
        tree = ast.parse(source)
        collector = AttributeAccessCollector()
        collector.visit(node=tree)
        assert collector.has_dynamic_access is True

    def test_no_dynamic_access(self):
        source = "obj.normal_attr"
        tree = ast.parse(source)
        collector = AttributeAccessCollector()
        collector.visit(node=tree)
        assert collector.has_dynamic_access is False

    def test_method_call_attribute(self):
        source = "obj.method()"
        tree = ast.parse(source)
        collector = AttributeAccessCollector()
        collector.visit(node=tree)
        assert "method" in collector.accessed_attrs

    def test_chained_attribute(self):
        source = "obj.a.b.c"
        tree = ast.parse(source)
        collector = AttributeAccessCollector()
        collector.visit(node=tree)
        assert {"a", "b", "c"} == collector.accessed_attrs


class TestCollectTestAttributeAccesses:
    def test_simple_test_function(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_foo(vm):
                vm.start()
                vm.stop()
        """)
        )
        result = _collect_test_attribute_accesses(
            test_file=test_file,
            test_name="test_foo",
        )
        assert result is not None
        assert "start" in result
        assert "stop" in result

    def test_class_based_test(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            class TestVM:
                def test_boot(self, vm):
                    vm.start()

            class TestOther:
                def test_boot(self, svc):
                    svc.restart()
        """)
        )
        result = _collect_test_attribute_accesses(
            test_file=test_file,
            test_name="TestVM::test_boot",
        )
        assert result is not None
        assert "start" in result
        assert "restart" not in result

    def test_parametrized_name_stripped(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_foo(vm):
                vm.migrate()
        """)
        )
        result = _collect_test_attribute_accesses(
            test_file=test_file,
            test_name="test_foo[param1]",
        )
        assert result is not None
        assert "migrate" in result

    def test_class_parametrized_stripped(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            class TestVM:
                def test_boot(self, vm):
                    vm.start()
        """)
        )
        result = _collect_test_attribute_accesses(
            test_file=test_file,
            test_name="TestVM::test_boot[linux-fedora]",
        )
        assert result is not None
        assert "start" in result

    def test_dynamic_access_returns_none(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_dynamic(vm):
                getattr(vm, "start")()
        """)
        )
        result = _collect_test_attribute_accesses(
            test_file=test_file,
            test_name="test_dynamic",
        )
        assert result is None

    def test_constructor_adds_init(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_create(ns):
                vm = VirtualMachine()
                vm.start()
        """)
        )
        result = _collect_test_attribute_accesses(
            test_file=test_file,
            test_name="test_create",
        )
        assert result is not None
        assert "__init__" in result

    def test_nonexistent_test_returns_none(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_existing(vm):
                vm.start()
        """)
        )
        result = _collect_test_attribute_accesses(
            test_file=test_file,
            test_name="test_nonexistent",
        )
        assert result is None

    def test_invalid_syntax_returns_none(self, tmp_path: Path):
        test_file = tmp_path / "test_bad.py"
        test_file.write_text("def broken(:\n")
        result = _collect_test_attribute_accesses(
            test_file=test_file,
            test_name="broken",
        )
        assert result is None


class TestCollectTestFunctionCalls:
    def test_simple_function_call(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_calls():
                foo()
        """)
        )
        result = _collect_test_function_calls(
            test_file=test_file,
            test_name="test_calls",
        )
        assert result is not None
        assert "foo" in result

    def test_method_call(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_method(obj):
                obj.bar()
        """)
        )
        result = _collect_test_function_calls(
            test_file=test_file,
            test_name="test_method",
        )
        assert result is not None
        assert "bar" in result

    def test_class_based_test(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            class TestSuite:
                def test_inner(self):
                    helper()

            def test_inner():
                other_func()
        """)
        )
        result = _collect_test_function_calls(
            test_file=test_file,
            test_name="TestSuite::test_inner",
        )
        assert result is not None
        assert "helper" in result
        assert "other_func" not in result

    def test_parametrized_name_stripped(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_param():
                do_work()
        """)
        )
        result = _collect_test_function_calls(
            test_file=test_file,
            test_name="test_param[case-1]",
        )
        assert result is not None
        assert "do_work" in result

    def test_nonexistent_returns_none(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_real():
                pass
        """)
        )
        result = _collect_test_function_calls(
            test_file=test_file,
            test_name="test_ghost",
        )
        assert result is None

    def test_multiple_calls(self, tmp_path: Path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_multi():
                alpha()
                beta()
                obj.gamma()
        """)
        )
        result = _collect_test_function_calls(
            test_file=test_file,
            test_name="test_multi",
        )
        assert result is not None
        assert {"alpha", "beta", "gamma"}.issubset(result)


class TestIsFixtureDecoratorStandalone:
    def test_bare_fixture(self):
        source = textwrap.dedent("""\
            @fixture
            def my_fixture():
                pass
        """)
        tree = ast.parse(source)
        func_node = tree.body[0]
        decorator = func_node.decorator_list[0]
        assert _is_fixture_decorator_standalone(decorator=decorator) is True

    def test_pytest_fixture(self):
        source = textwrap.dedent("""\
            @pytest.fixture
            def my_fixture():
                pass
        """)
        tree = ast.parse(source)
        func_node = tree.body[0]
        decorator = func_node.decorator_list[0]
        assert _is_fixture_decorator_standalone(decorator=decorator) is True

    def test_pytest_fixture_with_params(self):
        source = textwrap.dedent("""\
            @pytest.fixture(scope="session")
            def my_fixture():
                pass
        """)
        tree = ast.parse(source)
        func_node = tree.body[0]
        decorator = func_node.decorator_list[0]
        assert _is_fixture_decorator_standalone(decorator=decorator) is True

    def test_non_fixture_decorator(self):
        source = textwrap.dedent("""\
            @pytest.mark.smoke
            def my_test():
                pass
        """)
        tree = ast.parse(source)
        func_node = tree.body[0]
        decorator = func_node.decorator_list[0]
        assert _is_fixture_decorator_standalone(decorator=decorator) is False

    def test_random_decorator(self):
        source = textwrap.dedent("""\
            @my_decorator
            def my_func():
                pass
        """)
        tree = ast.parse(source)
        func_node = tree.body[0]
        decorator = func_node.decorator_list[0]
        assert _is_fixture_decorator_standalone(decorator=decorator) is False


class TestParseDiffForFunctions:
    def test_single_function_modified(self):
        diff_content = textwrap.dedent("""\
            @@ -10,6 +10,7 @@ def my_function(arg):
                 existing_code()
            +    new_code()
                 more_code()
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert result == {"my_function"}

    def test_multiple_functions_modified(self):
        diff_content = textwrap.dedent("""\
            @@ -10,6 +10,7 @@ def func_one():
                 existing()
            +    added()
            @@ -30,6 +31,7 @@ def func_two():
                 existing()
            +    also_added()
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert result == {"func_one", "func_two"}

    def test_no_functions_modified(self):
        diff_content = textwrap.dedent("""\
            @@ -1,3 +1,4 @@
             import os
            +import sys
             import re
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert result == set()

    def test_async_function_modified(self):
        diff_content = textwrap.dedent("""\
            @@ -10,6 +10,7 @@ async def async_handler(request):
                 data = await fetch()
            +    log(data)
                 return data
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert result == {"async_handler"}

    def test_comment_only_changes_ignored(self):
        diff_content = textwrap.dedent("""\
            @@ -10,6 +10,7 @@ def my_function():
                 code()
            +    # this is just a comment
                 more_code()
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert result == set()

    def test_whitespace_only_changes_ignored(self):
        diff_content = textwrap.dedent("""\
            @@ -10,6 +10,7 @@ def my_function():
                 code()
            +
                 more_code()
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert result == set()

    def test_new_function_added_after_existing(self) -> None:
        diff_content = textwrap.dedent("""\
            @@ -93,3 +96,25 @@ def uploaded_dv_scope_class(request):
            +
            +@pytest.fixture(scope="module")
            +def uploaded_dv_in_udn_namespace(request):
            +    yield from create_dv(request)
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert result == {"uploaded_dv_in_udn_namespace"}, "New function added after existing should be detected"

    def test_new_function_added_does_not_mark_existing_as_modified(self) -> None:
        diff_content = textwrap.dedent("""\
            @@ -50,3 +50,10 @@ def existing_func():
            +
            +def brand_new_func():
            +    do_something()
            +    do_more()
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert "existing_func" not in result, (
            "Existing function in @@ header should not be marked as modified when only new code was added"
        )
        assert result == {"brand_new_func"}, "Only the newly added function should be in the result"

    def test_removed_function_detected(self) -> None:
        diff_content = textwrap.dedent("""\
            @@ -50,10 +50,3 @@ def existing_func():
            -
            -def removed_func():
            -    do_something()
            -    do_more()
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert "existing_func" not in result, (
            "Existing function in @@ header should not be marked when a different function was removed"
        )
        assert result == {"removed_func"}, "Removed function should be detected in the diff"

    def test_new_async_function_added_after_existing(self) -> None:
        diff_content = textwrap.dedent("""\
            @@ -93,3 +96,10 @@ def existing_func():
            +
            +async def new_async_handler(request):
            +    data = await fetch()
            +    return data
        """)
        result = _parse_diff_for_functions(diff_content=diff_content)
        assert result == {"new_async_handler"}, "New async function added after existing should be detected"
        assert "existing_func" not in result, (
            "Existing function in @@ header should not be marked when only new async code was added"
        )


class TestSymbolClassificationModifiedMembers:
    def test_default_empty_dict(self):
        classification = SymbolClassification(
            modified_symbols=set(),
            new_symbols=set(),
        )
        assert classification.modified_members == {}

    def test_with_modified_members(self):
        members = {"MyClass": {"method_a", "method_b"}}
        classification = SymbolClassification(
            modified_symbols={"MyClass"},
            new_symbols=set(),
            modified_members=members,
        )
        assert classification.modified_members == members
        assert "method_a" in classification.modified_members["MyClass"]


class TestGetModifiedFunctionNames:
    """Tests for _get_modified_function_names return type semantics."""

    def test_returns_none_when_github_api_returns_no_diff(self, tmp_path: Path) -> None:
        """When GitHub API returns empty/None diff_content, function returns None."""
        file_path = tmp_path / "conftest.py"
        file_path.write_text("def my_func(): pass\n")
        github_pr_info = {"repo": "org/repo", "pr_number": 1, "token": "fake"}

        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.get_pr_file_diff",
            return_value="",
        ):
            result = _get_modified_function_names(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=github_pr_info,
            )

        assert result is None

    def test_returns_set_when_github_api_returns_valid_diff(self, tmp_path: Path) -> None:
        """When GitHub API returns valid diff with no function changes, returns empty set."""
        file_path = tmp_path / "conftest.py"
        file_path.write_text("import os\n")
        github_pr_info = {"repo": "org/repo", "pr_number": 1, "token": "fake"}
        diff_content = "--- a/conftest.py\n+++ b/conftest.py\n@@ -1 +1 @@\n-import sys\n+import os\n"

        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.get_pr_file_diff",
            return_value=diff_content,
        ):
            result = _get_modified_function_names(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=github_pr_info,
            )

        assert result is not None
        assert result == set()

    def test_returns_none_when_git_diff_fails(self, tmp_path: Path) -> None:
        """When local git diff subprocess fails, returns None."""
        file_path = tmp_path / "conftest.py"
        file_path.write_text("def my_func(): pass\n")

        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            side_effect=OSError("git not found"),
        ):
            result = _get_modified_function_names(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is None

    def test_returns_none_when_git_diff_nonzero_returncode(self, tmp_path: Path) -> None:
        """When local git diff returns non-zero exit code, returns None."""
        file_path = tmp_path / "conftest.py"
        file_path.write_text("def my_func(): pass\n")

        mock_result = type("Result", (), {"returncode": 128, "stdout": "", "stderr": "fatal: bad revision"})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _get_modified_function_names(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is None

    def test_returns_empty_set_for_module_level_only_diff(self, tmp_path: Path) -> None:
        """When git diff succeeds but only module-level lines changed, returns empty set."""
        file_path = tmp_path / "conftest.py"
        file_path.write_text("import os\n")
        diff_content = "--- a/conftest.py\n+++ b/conftest.py\n@@ -1 +1 @@\n-import sys\n+import os\n"

        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _get_modified_function_names(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None
        assert result == set()

    def test_returns_function_names_from_cache(self, tmp_path: Path) -> None:
        """When diff is in pr_diffs_cache, returns parsed function names."""
        file_path = tmp_path / "conftest.py"
        file_path.write_text("def my_fixture(): pass\n")
        diff_content = (
            "--- a/conftest.py\n"
            "+++ b/conftest.py\n"
            "@@ -1,3 +1,3 @@ def my_fixture\n"
            " def my_fixture():\n"
            "-    pass\n"
            "+    return 42\n"
        )

        result = _get_modified_function_names(
            file_path=file_path,
            base_branch="main",
            repo_root=tmp_path,
            github_pr_info=None,
            pr_diffs_cache={"conftest.py": diff_content},
        )

        assert result == {"my_fixture"}

    def test_checkout_mode_falls_through_to_local_git_when_github_api_empty(self, tmp_path: Path) -> None:
        """In checkout mode, when GitHub API returns empty diff, fall through to local git diff."""
        file_path = tmp_path / "conftest.py"
        file_path.write_text("def my_func(): pass\n")
        github_pr_info = {"repo": "org/repo", "pr_number": 1, "token": "fake"}
        diff_content = (
            "--- a/conftest.py\n"
            "+++ b/conftest.py\n"
            "@@ -1,3 +1,3 @@ def my_func\n"
            " def my_func():\n"
            "-    pass\n"
            "+    return 42\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()

        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer.get_pr_file_diff",
                return_value="",
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
        ):
            result = _get_modified_function_names(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=github_pr_info,
                is_checkout=True,
            )

        assert result is not None, "Checkout mode should fall through to local git diff"
        assert result == {"my_func"}

    def test_remote_mode_returns_none_when_github_api_empty(self, tmp_path: Path) -> None:
        """In remote mode (default), when GitHub API returns empty diff, returns None without local fallback."""
        file_path = tmp_path / "conftest.py"
        file_path.write_text("def my_func(): pass\n")
        github_pr_info = {"repo": "org/repo", "pr_number": 1, "token": "fake"}

        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.get_pr_file_diff",
            return_value="",
        ):
            result = _get_modified_function_names(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=github_pr_info,
                is_checkout=False,
            )

        assert result is None


class TestExtractModifiedItemsFromConftestDiffFailure:
    """Tests that _extract_modified_items_from_conftest handles diff failure vs empty diff correctly."""

    def test_module_level_changes_do_not_flag_all_fixtures(self, tmp_path: Path) -> None:
        """When only module-level imports change, no fixtures should be flagged.

        This is the core bug: module-level changes produce an empty set (not None)
        from _get_modified_function_names, meaning no functions were modified.
        The conftest should NOT return all fixtures as modified.
        """
        conftest = tmp_path / "conftest.py"
        conftest.write_text(
            textwrap.dedent("""\
            import pytest
            import os

            @pytest.fixture()
            def my_fixture():
                return 42

            @pytest.fixture()
            def another_fixture():
                return "hello"
        """)
        )

        no_pytest_plugins = SymbolClassification(
            modified_symbols={"os"},
            new_symbols=set(),
        )
        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._get_modified_function_names",
                return_value=set(),
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._extract_modified_symbols",
                return_value=no_pytest_plugins,
            ),
        ):
            modified_fixtures, modified_functions = _extract_modified_items_from_conftest(
                changed_file=conftest,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert modified_fixtures == set()
        assert modified_functions == set()

    def test_diff_failure_returns_all_fixtures_conservatively(self, tmp_path: Path) -> None:
        """When diff retrieval fails (returns None), all fixtures returned conservatively."""
        conftest = tmp_path / "conftest.py"
        conftest.write_text(
            textwrap.dedent("""\
            import pytest

            @pytest.fixture()
            def my_fixture():
                return 42

            @pytest.fixture()
            def another_fixture():
                return "hello"
        """)
        )

        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer._get_modified_function_names",
            return_value=None,
        ):
            modified_fixtures, modified_functions = _extract_modified_items_from_conftest(
                changed_file=conftest,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert modified_fixtures == {"my_fixture", "another_fixture"}
        assert modified_functions == set()

    def test_passes_is_checkout_to_get_modified_function_names(self, tmp_path: Path) -> None:
        """Verify is_checkout parameter is threaded through to _get_modified_function_names."""
        conftest = tmp_path / "conftest.py"
        conftest.write_text(
            textwrap.dedent("""\
            import pytest

            @pytest.fixture()
            def my_fixture():
                return 42
        """)
        )

        no_pytest_plugins = SymbolClassification(
            modified_symbols=set(),
            new_symbols=set(),
        )
        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._get_modified_function_names",
                return_value=set(),
            ) as mock_get_modified,
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._extract_modified_symbols",
                return_value=no_pytest_plugins,
            ),
        ):
            _extract_modified_items_from_conftest(
                changed_file=conftest,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
                is_checkout=True,
            )

        mock_get_modified.assert_called_once()
        call_kwargs = mock_get_modified.call_args[1]
        assert call_kwargs["is_checkout"] is True, "is_checkout must be passed through"


class TestSymbolClassificationHasUnattributedChanges:
    """Tests for the has_unattributed_changes field on SymbolClassification."""

    def test_defaults_to_false(self) -> None:
        classification = SymbolClassification(modified_symbols={"foo"}, new_symbols=set())
        assert classification.has_unattributed_changes is False

    def test_can_be_set_to_true(self) -> None:
        classification = SymbolClassification(
            modified_symbols={"foo"},
            new_symbols=set(),
            has_unattributed_changes=True,
        )
        assert classification.has_unattributed_changes is True


class TestExtractModifiedSymbolsUnattributed:
    """Tests that _extract_modified_symbols handles unattributed lines correctly.

    Safe unmapped lines (imports, comments, blanks, docstrings) set
    has_unattributed_changes=True.  Unsafe unmapped lines (executable
    module-level code like function calls or assignments not captured
    in the symbol map) force a conservative None return.
    """

    def test_import_only_change_returns_classification_not_none(self, tmp_path: Path) -> None:
        """An import swap is attributed to the imported names, not left unattributed.

        ``utilities.ssp.get_windows_timezone`` is no longer bound by the new
        file, so it is reported as a removal; ``TCP_TIMEOUT_30SEC`` is bound, so
        swapping in its import has no impact.
        """
        source = textwrap.dedent("""\
            from utilities.constants import TCP_TIMEOUT_30SEC

            def my_func():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes only the import line (line 1)
        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1 +1 @@\n"
            "-from utilities.ssp import get_windows_timezone\n"
            "+from utilities.constants import TCP_TIMEOUT_30SEC\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "Should return SymbolClassification, not None"
        assert result.modified_symbols == {"get_windows_timezone"}, (
            "a removed project import name must be attributed as modified"
        )
        assert result.has_unattributed_changes is False, "import-line edits must not force file-level fallback"

    def test_mixed_import_and_constant_change(self, tmp_path: Path) -> None:
        """When both an import and a constant change, returns both info."""
        source = textwrap.dedent("""\
            import os

            TIMEOUT = 60

            def my_func():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes both line 1 (import) and line 3 (constant)
        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-import sys\n"
            "+import os\n"
            " \n"
            "-TIMEOUT = 30\n"
            "+TIMEOUT = 60\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value="import sys\n\nTIMEOUT = 30\n\ndef my_func():\n    pass\n",
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "Should return SymbolClassification, not None"
        assert "TIMEOUT" in result.modified_symbols
        assert result.has_unattributed_changes is False, (
            "import edits alongside a constant change are still attributable"
        )

    def test_all_changes_within_symbols_no_unattributed(self, tmp_path: Path) -> None:
        """When all changed lines fall within symbols, has_unattributed_changes is False."""
        source = textwrap.dedent("""\
            TIMEOUT = 60

            def my_func():
                return 42
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes only line 4 (inside my_func)
        diff_content = (
            "--- a/module.py\n+++ b/module.py\n@@ -3,2 +3,2 @@\n def my_func():\n-    return 0\n+    return 42\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value="TIMEOUT = 60\n\ndef my_func():\n    return 0\n",
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None
        assert "my_func" in result.modified_symbols
        assert result.has_unattributed_changes is False

    def test_diff_failure_still_returns_none(self, tmp_path: Path) -> None:
        """When diff retrieval fails, still returns None (not SymbolClassification)."""
        file_path = tmp_path / "module.py"
        file_path.write_text("def foo(): pass\n")

        mock_result = type("Result", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is None

    def test_pure_deletion_returns_classification_with_removed_imports(self, tmp_path: Path) -> None:
        """A pure deletion of imports returns the unbound names, not an empty set."""
        file_path = tmp_path / "module.py"
        file_path.write_text("def foo(): pass\n")

        # Diff with only deletions (no + lines except the +++ header)
        diff_content = "--- a/module.py\n+++ b/module.py\n@@ -1,3 +1 @@\n-import os\n-import sys\n def foo(): pass\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        # Pure deletion now returns SymbolClassification (not None) to enable symbol narrowing
        assert result is not None
        assert result.modified_symbols == {"os", "sys"}, "dropped imports unbind their names, so both are removals"

    def test_executable_module_level_code_returns_none(self, tmp_path: Path) -> None:
        """When unmapped line is executable code (e.g. function call), returns None (conservative)."""
        source = textwrap.dedent("""\
            import os

            setup_logging()

            def my_func():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes line 3 (setup_logging() call — executable, unmapped)
        diff_content = "--- a/module.py\n+++ b/module.py\n@@ -3 +3 @@\n-configure_logging()\n+setup_logging()\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is None, "Executable module-level code should trigger conservative fallback"

    def test_comment_between_functions_is_safe(self, tmp_path: Path) -> None:
        """When unmapped line is a comment, returns SymbolClassification with has_unattributed_changes."""
        source = textwrap.dedent("""\
            def func_a():
                pass

            # This is a comment between functions

            def func_b():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes only line 4 (comment)
        diff_content = (
            "--- a/module.py\n+++ b/module.py\n@@ -4 +4 @@\n-# Old comment\n+# This is a comment between functions\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "Comment-only change should not trigger conservative fallback"
        assert result.has_unattributed_changes is True

    def test_indented_docstring_line_starting_with_from_is_not_an_import(self, tmp_path: Path) -> None:
        """An indented prose line starting with ``from`` binds no import name."""
        source = textwrap.dedent('''\
            def helper():
                """Docstring.

                Values are taken
                from the caller.
                """
                return True
        ''')
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -3,4 +3,4 @@\n"
            " \n"
            "     Values are taken\n"
            "-        from the environment.\n"
            "+        from the caller.\n"
            '     """\n'
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value=source.replace("from the caller.", "from the environment."),
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert "helper" in result.modified_symbols, "a docstring edit belongs to the enclosing symbol"
        assert result.has_unattributed_changes is False, (
            "an indented prose line starting with 'from' must not be read as an import edit"
        )

    def test_blank_line_between_functions_is_safe(self, tmp_path: Path) -> None:
        """When unmapped line is blank, returns SymbolClassification with has_unattributed_changes."""
        source = textwrap.dedent("""\
            def func_a():
                pass


            def func_b():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that adds a blank line (line 3 is blank, line 4 is blank)
        diff_content = "--- a/module.py\n+++ b/module.py\n@@ -2,2 +2,3 @@\n     pass\n+\n \n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "Blank-line change should not trigger conservative fallback"
        assert result.has_unattributed_changes is True

    def test_module_docstring_is_safe(self, tmp_path: Path) -> None:
        """When unmapped line is a string literal (docstring), returns SymbolClassification."""
        source = textwrap.dedent('''\
            """Module docstring."""

            def my_func():
                pass
        ''')
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes line 1 (module docstring)
        diff_content = (
            '--- a/module.py\n+++ b/module.py\n@@ -1 +1 @@\n-"""Old docstring."""\n+"""Module docstring."""\n'
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "Docstring change should not trigger conservative fallback"
        assert result.has_unattributed_changes is True

    def test_mixed_safe_and_unsafe_unmapped_returns_none(self, tmp_path: Path) -> None:
        """When unmapped lines include both safe (import) and unsafe (call), returns None."""
        source = textwrap.dedent("""\
            import os

            register_plugin()

            def my_func():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes both line 1 (import) and line 3 (executable call)
        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-import sys\n"
            "+import os\n"
            " \n"
            "-init_plugin()\n"
            "+register_plugin()\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is None, "Executable module-level code should trigger conservative fallback"

    def test_new_decorated_function_classified_as_new_symbol(self, tmp_path: Path) -> None:
        """A newly added decorated function should be classified as a new symbol.

        When a diff adds a decorated function (decorator + def + body), all
        changed lines fall within the function's symbol range because
        ``_symbol_start_line`` includes decorators.  The function should be
        classified as a *new* symbol (not modified), and no conservative
        fallback should occur.
        """
        source = textwrap.dedent("""\
            import pytest

            @pytest.mark.some_marker("ID-1234")
            def test_new_feature():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that adds the decorated function (lines 3-5).  _symbol_start_line
        # includes the decorator, so the symbol range covers all changed lines.
        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1,2 +1,5 @@\n"
            " import pytest\n"
            " \n"
            '+@pytest.mark.some_marker("ID-1234")\n'
            "+def test_new_feature():\n"
            "+    pass\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "Decorated new function should not trigger conservative fallback"
        assert "test_new_feature" in result.new_symbols, "Newly added decorated function should be in new_symbols"
        assert "test_new_feature" not in result.modified_symbols, (
            "Newly added function should not appear in modified_symbols"
        )

    def test_line_number_beyond_source_returns_none(self, tmp_path: Path) -> None:
        """When changed line number exceeds source length, returns None (conservative)."""
        source = "def my_func():\n    pass\n"
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff claims change at line 10, but source only has 2 lines
        diff_content = "--- a/module.py\n+++ b/module.py\n@@ -10 +10 @@\n-old_line\n+new_line\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is None, "Line beyond source should trigger conservative fallback"

    def test_fetch_failure_falls_through_to_local_file_in_checkout_mode(self, tmp_path: Path) -> None:
        """When _fetch_file_at_ref fails in checkout mode, should fall through to local file.

        In --checkout mode the local file IS the PR HEAD, so the local
        file is authoritative and symbol-level analysis should proceed.
        """
        source = textwrap.dedent("""\
            def my_func():
                return 42
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes line 2 (inside my_func)
        diff_content = (
            "--- a/module.py\n+++ b/module.py\n@@ -1,2 +1,2 @@\n def my_func():\n-    return 0\n+    return 42\n"
        )
        pr_diffs_cache = {"module.py": diff_content}

        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer._fetch_file_at_ref",
            return_value=None,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info={"repo": "owner/repo"},
                pr_diffs_cache=pr_diffs_cache,
                pr_head_ref="abc123",
                is_checkout=True,
            )

        assert result is not None, "Checkout mode should fall through to local file, not return None"
        assert "my_func" in result.modified_symbols

    def test_fetch_failure_returns_none_in_remote_mode(self, tmp_path: Path) -> None:
        """When _fetch_file_at_ref fails in remote mode, should return None.

        In remote mode (no --checkout), the local file may be on a
        different branch/commit than the PR HEAD.  Using it would build
        the symbol map from the wrong file version and potentially
        narrow away real impacts.
        """
        source = textwrap.dedent("""\
            def my_func():
                return 42
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that changes line 2 (inside my_func)
        diff_content = (
            "--- a/module.py\n+++ b/module.py\n@@ -1,2 +1,2 @@\n def my_func():\n-    return 0\n+    return 42\n"
        )
        pr_diffs_cache = {"module.py": diff_content}

        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer._fetch_file_at_ref",
            return_value=None,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info={"repo": "owner/repo"},
                pr_diffs_cache=pr_diffs_cache,
                pr_head_ref="abc123",
                is_checkout=False,
            )

        assert result is None, "Remote mode fetch failure should return None (conservative fallback)"


class TestLocalModeRequiresBaseBranch:
    """Local mode must not silently diff against an assumed base branch.

    Diffing a release-branch checkout against main reports the whole branch
    divergence as affected dependencies, so local mode requires --base.
    """

    def test_local_mode_without_base_exits_with_parser_error(self, capsys: CaptureFixture[str]) -> None:
        """Local mode without --base exits with a parser error naming --base."""
        with (
            patch(target="sys.argv", new=["pytest_marker_analyzer.py", "--markers", "smoke"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 2, "argparse errors must exit with code 2"
        assert "--base is required in local mode" in capsys.readouterr().err, (
            "local mode without --base must fail with a message naming --base"
        )

    def test_get_changed_files_without_base_or_files_raises(self, tmp_path: Path) -> None:
        """get_changed_files raises when neither files nor base_branch is provided."""
        analyzer = MarkerTestAnalyzer(marker_expression="smoke", repo_root=tmp_path)

        with pytest.raises(ValueError, match="base_branch is required when files is not provided"):
            analyzer.get_changed_files()

    def test_get_changed_files_unresolvable_base_raises(self, tmp_path: Path) -> None:
        """An unresolvable base ref raises instead of reporting an empty change set."""
        analyzer = MarkerTestAnalyzer(marker_expression="smoke", repo_root=tmp_path)
        unresolved = type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=unresolved,
            ),
            pytest.raises(AnalyzerGitError) as exc_info,
        ):
            analyzer.get_changed_files(base_branch="origin/cnv-5.0")

        assert "origin/cnv-5.0" in str(exc_info.value), "error must name the unresolvable base branch"

    def test_get_changed_files_failing_diff_raises_with_context(self, tmp_path: Path) -> None:
        """A failing git diff (e.g. no merge base) raises with base, cwd and stderr."""
        analyzer = MarkerTestAnalyzer(marker_expression="smoke", repo_root=tmp_path)
        verified = type("Result", (), {"returncode": 0, "stdout": "abc123\n", "stderr": ""})()
        diff_failed = type("Result", (), {"returncode": 128, "stdout": "", "stderr": "fatal: no merge base"})()

        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                side_effect=[verified, diff_failed],
            ),
            pytest.raises(AnalyzerGitError) as exc_info,
        ):
            analyzer.get_changed_files(base_branch="origin/cnv-5.0")

        message = str(exc_info.value)
        assert "origin/cnv-5.0" in message, "error must name the base branch"
        assert str(tmp_path) in message, "error must name the working directory"
        assert "fatal: no merge base" in message, "error must include the git stderr"

    def test_run_local_mode_returns_error_on_analyzer_git_error(self) -> None:
        """run_local_mode exits non-zero when the change set cannot be determined."""
        with patch("scripts.tests_analyzer.pytest_marker_analyzer.MarkerTestAnalyzer") as mock_analyzer_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.marked_tests = ["test_something"]
            mock_analyzer.get_changed_files.side_effect = AnalyzerGitError(
                "base branch 'origin/nope' could not be resolved; pass a valid --base"
            )
            mock_analyzer_cls.return_value = mock_analyzer

            result, exit_code = run_local_mode(args=argparse.Namespace(markers="smoke", base="origin/nope", files=None))

        assert result is None, "run_local_mode must not return a result when the change set is undeterminable"
        assert exit_code == 1, "an undeterminable change set must exit non-zero"


class TestSymbolAttributionRemovals:
    """Moved/removed symbols must be attributed instead of wiping the change set.

    PR 6631 moved helpers from ``utilities/ssp.py`` to ``utilities/windows.py``
    and re-imported them.  The deleted ``def`` lines and the changed import
    lines must attribute those names.  A removal-derived name always stays in
    ``modified_symbols``, even when the new file re-binds it from another
    module: the re-export can still change behaviour for importers.
    """

    def test_import_swap_with_name_still_bound_stays_modified(self, tmp_path: Path) -> None:
        """``from utilities.ssp import x`` -> ``from utilities.guest_agent import x``."""
        source = textwrap.dedent("""\
            from utilities.guest_agent import guest_agent_version_parser

            def some_helper():
                return 1
        """)
        file_path = tmp_path / "infra.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/utilities/infra.py\n"
            "+++ b/utilities/infra.py\n"
            "@@ -1 +1 @@\n"
            "-from utilities.ssp import guest_agent_version_parser\n"
            "+from utilities.guest_agent import guest_agent_version_parser\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert "guest_agent_version_parser" in result.modified_symbols, (
            "a re-bound removal-derived name stays modified: the new source can change behaviour"
        )
        assert result.has_unattributed_changes is False, "import-line edits must not force file-level fallback"

    def test_import_removal_of_unbound_name_is_attributed(self, tmp_path: Path) -> None:
        """A name removed by an import edit and not re-bound is a modified symbol."""
        source = textwrap.dedent("""\
            from utilities.guest_agent import something_else

            def some_helper():
                return 1
        """)
        file_path = tmp_path / "infra.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/utilities/infra.py\n"
            "+++ b/utilities/infra.py\n"
            "@@ -1 +1 @@\n"
            "-from utilities.ssp import guest_agent_version_parser\n"
            "+from utilities.guest_agent import something_else\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert "guest_agent_version_parser" in result.modified_symbols, (
            "a removed project import name must be attributed as modified"
        )
        assert result.has_unattributed_changes is False, "import-line edits must not force file-level fallback"

    def test_mixed_deletion_and_addition_keeps_deleted_defs(self, tmp_path: Path) -> None:
        """Deleted defs stay in modified_symbols even when the new file re-imports one."""
        source = textwrap.dedent("""\
            from utilities.windows import get_windows_os_info

            def helper():
                return 42
        """)
        file_path = tmp_path / "ssp.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/utilities/ssp.py\n"
            "+++ b/utilities/ssp.py\n"
            "@@ -1,6 +1,4 @@\n"
            "+from utilities.windows import get_windows_os_info\n"
            " \n"
            "-def get_windows_os_info():\n"
            '-    return "ga"\n'
            "-def get_windows_timezone():\n"
            '-    return "tz"\n'
            "+def helper():\n"
            "+    return 42\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert "get_windows_timezone" in result.modified_symbols, "deleted defs must stay attributed"
        assert "get_windows_os_info" in result.modified_symbols, (
            "a deleted def stays modified even though the new file re-imports the name"
        )
        assert result.has_unattributed_changes is False, "import and deletion edits are fully attributable"

    def test_body_modified_symbol_is_never_dropped(self, tmp_path: Path) -> None:
        """A changed function body keeps the symbol even though its def binds the name."""
        source = textwrap.dedent("""\
            def wait_for_windows_vm():
                return True
        """)
        file_path = tmp_path / "virt.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/utilities/virt.py\n"
            "+++ b/utilities/virt.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def wait_for_windows_vm():\n"
            "-    return False\n"
            "+    return True\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value="def wait_for_windows_vm():\n    return False\n",
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert "wait_for_windows_vm" in result.modified_symbols, "a body-modified symbol must stay attributed"
        assert result.has_unattributed_changes is False, "import-line edits must not force file-level fallback"

    def test_removed_third_party_imports_are_symbol_removals(self, tmp_path: Path) -> None:
        """A diff-dropped stdlib/third-party import still unbinds its names.

        PR 6631 moved helpers out of ``utilities/ssp.py``; the now-unused
        ``import json``, ``import shlex`` and ``run_ssh_commands`` import were
        dropped by the diff.  The names leave the module namespace, so callers
        using ``ssp.run_ssh_commands()`` break and must not be skipped.
        """
        source = textwrap.dedent("""\
            from utilities.constants import TCP_TIMEOUT_30SEC
            from ocp_resources.virtual_machine import VirtualMachine

            def some_helper():
                return 1
        """)
        file_path = tmp_path / "ssp.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/utilities/ssp.py\n"
            "+++ b/utilities/ssp.py\n"
            "@@ -1,3 +1,2 @@\n"
            "-import json\n"
            "-import shlex\n"
            "-from pyhelper_utils.shell import run_ssh_commands\n"
            "+from utilities.constants import TCP_TIMEOUT_30SEC\n"
            "+from ocp_resources.virtual_machine import VirtualMachine\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.modified_symbols == {"json", "shlex", "run_ssh_commands"}, (
            f"every name a removed import bound is a removal symbol: {result.modified_symbols}"
        )
        assert result.has_unattributed_changes is False, "third-party import removals are fully attributable"

    def test_relative_import_removal_of_unbound_name_is_attributed(self, tmp_path: Path) -> None:
        """A relative import of project code is a project import."""
        source = textwrap.dedent("""\
            from .windows import something_else

            def some_helper():
                return 1
        """)
        file_path = tmp_path / "infra.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/utilities/infra.py\n"
            "+++ b/utilities/infra.py\n"
            "@@ -1 +1 @@\n"
            "-from .ssp import guest_agent_version_parser\n"
            "+from .windows import something_else\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert "guest_agent_version_parser" in result.modified_symbols, (
            "a removed project import name must be attributed as modified"
        )
        assert "something_else" not in result.modified_symbols, (
            "an added import binds a name here; it removes no API from this module"
        )
        assert result.has_unattributed_changes is False, "import-line edits must not force file-level fallback"

    def test_removed_multiline_project_import_is_attributed(self, tmp_path: Path) -> None:
        """A parenthesized multi-line project import attributes its removed names."""
        source = textwrap.dedent("""\
            from utilities.guest_agent import something_else

            def some_helper():
                return 1
        """)
        file_path = tmp_path / "infra.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/utilities/infra.py\n"
            "+++ b/utilities/infra.py\n"
            "@@ -1,3 +1 @@\n"
            "-from utilities.ssp import (\n"
            "-    guest_agent_version_parser,\n"
            "-)\n"
            "+from utilities.guest_agent import something_else\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert "guest_agent_version_parser" in result.modified_symbols, (
            "a name removed by a multi-line import must be attributed, not silently ignored"
        )
        assert result.has_unattributed_changes is False, "a balanced multi-line import is fully attributable"

    def test_incomplete_multiline_import_is_unattributed(self, tmp_path: Path) -> None:
        """An unbalanced import hunk cannot be narrowed and must stay conservative."""
        file_path = tmp_path / "infra.py"
        file_path.write_text("def some_helper():\n    return 1\n")

        diff_content = (
            "--- a/utilities/infra.py\n"
            "+++ b/utilities/infra.py\n"
            "@@ -1,2 +1,0 @@\n"
            "-from utilities.ssp import (\n"
            "-    guest_agent_version_parser,\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.has_unattributed_changes is True, (
            "an import whose continuation lines are missing must not be silently ignored"
        )

    def test_deleted_body_statement_is_unattributed(self, tmp_path: Path) -> None:
        """Deleting one statement inside a live function must not look clean."""
        file_path = tmp_path / "virt.py"
        file_path.write_text("def wait_for_windows_vm():\n    return True\n")

        diff_content = (
            "--- a/utilities/virt.py\n"
            "+++ b/utilities/virt.py\n"
            "@@ -1,3 +1,2 @@\n"
            " def wait_for_windows_vm():\n"
            '-    return "debug"\n'
            "     return True\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.modified_symbols == set(), "a deleted body line maps to no new-file line"
        assert result.has_unattributed_changes is True, (
            "a deletion the diff cannot attribute must force the conservative fallback"
        )

    def test_replacement_adjacent_to_another_symbol_is_unattributed(self, tmp_path: Path) -> None:
        """A deletion followed by an unrelated new function is not a replacement.

        CodeRabbit's example: ``helper()`` loses its ``return False`` while an
        unrelated ``newly_added()`` is added right after it.  Mapping the deleted
        line to its old symbol (``helper``) shows that no modified symbol owns
        it, so the change must stay conservative: a conftest fixture calling
        ``helper()`` now gets ``None`` instead of ``False``.
        """
        source = "def helper():\n    setup()\ndef newly_added():\n    return True\n"
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1,3 +1,4 @@\n"
            " def helper():\n"
            "     setup()\n"
            "-    return False\n"
            "+def newly_added():\n"
            "+    return True\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value="def helper():\n    setup()\n    return False\n",
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.has_unattributed_changes is True, (
            "the deleted return belongs to helper(), which has no changed line on the new side"
        )
        assert result.new_symbols == {"newly_added"}, "the unrelated addition is still a new symbol"

        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()
        test_file = tmp_path / "tests" / "test_module.py"
        test_file.touch()
        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_module",
            node_id="tests/test_module.py::test_module",
            dependencies={conftest_path},
            fixtures=set(),
            symbol_imports={},
        )
        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=file_path,
            marked_test=marked_test,
            conftest_symbol_imports={},
            conftest_opaque_deps={conftest_path: {file_path}},
            modified_symbols_cache={file_path: result},
            fixtures_dict={},
            repo_root=tmp_path,
        )

        assert is_affected is True, (
            "a conftest fixture calling helper() must be flagged when helper() changes behaviour"
        )
        assert matching_deps, "a flagged pathway must report the dependency that caused it"

    def test_module_level_deletion_with_unrelated_addition_is_unattributed(self, tmp_path: Path) -> None:
        """A deleted module-level statement belongs to no modified symbol."""
        source = "def helper():\n    return True\ndef newly_added():\n    return 1\n"
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1,3 +1,4 @@\n"
            "-TIMEOUT = 30\n"
            " def helper():\n"
            "     return True\n"
            "+def newly_added():\n"
            "+    return 1\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value="TIMEOUT = 30\ndef helper():\n    return True\n",
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.has_unattributed_changes is True, "a deleted module-level statement maps to no modified symbol"

    def test_deleted_function_with_new_function_addition_still_narrows(self, tmp_path: Path) -> None:
        """Deleting a definition must not stop a separate added function being new."""
        source = "def helper():\n    return True\ndef newly_added():\n    return 1\n"
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1,4 +1,4 @@\n"
            "-def removed():\n"
            "-    return False\n"
            " def helper():\n"
            "     return True\n"
            "+def newly_added():\n"
            "+    return 1\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value="def removed():\n    return False\ndef helper():\n    return True\n",
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.modified_symbols == {"removed"}, "the deleted definition stays attributed"
        assert result.new_symbols == {"newly_added"}, "a fully added function must stay eligible for narrowing"
        assert result.has_unattributed_changes is False, (
            "a deleted definition and a new function are both fully attributable"
        )

    def test_in_place_body_edit_without_old_source_is_unattributed(self, tmp_path: Path) -> None:
        """Without the old source a body edit cannot be proven to be in-place."""
        file_path = tmp_path / "virt.py"
        file_path.write_text("def wait_for_windows_vm():\n    return True\n")

        diff_content = (
            "--- a/utilities/virt.py\n"
            "+++ b/utilities/virt.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def wait_for_windows_vm():\n"
            "-    return False\n"
            "+    return True\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value=None,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "an unavailable old file must not make the diff unresolvable"
        assert result.has_unattributed_changes is True, (
            "an unattributable deletion must stay conservative instead of looking clean"
        )


class TestBlankLineAndMemberAttribution:
    """Removed blank lines and class members are attributed to their own code."""

    def test_removed_blank_line_inside_docstring_is_unattributed(self, tmp_path: Path) -> None:
        """A blank line inside a docstring changes the string value."""
        file_path = tmp_path / "module.py"
        file_path.write_text(
            'def helper():\n    """\n    Do the thing.\n\n    More detail.\n    """\n    return True\n'
        )

        diff_content = "--- a/module.py\n+++ b/module.py\n@@ -4,1 +3,0 @@\n-\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value='def helper():\n    """\n    Do the thing.\n\n    More detail.\n    """\n    return True\n',
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.has_unattributed_changes is True, (
            "removing a blank line from a docstring changes its value and must not look clean"
        )

    def test_removed_blank_line_between_definitions_is_ignored(self, tmp_path: Path) -> None:
        """A blank separator between definitions carries no behaviour."""
        source = "def first():\n    return 1\n\n\ndef second():\n    return 2\n"
        file_path = tmp_path / "module.py"
        file_path.write_text("def first():\n    return 1\n\ndef second():\n    return 2\n")

        diff_content = "--- a/module.py\n+++ b/module.py\n@@ -4,1 +3,0 @@\n-\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value=source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.has_unattributed_changes is False, (
            "a blank line between definitions belongs to no symbol and changes nothing"
        )

    def test_removed_blank_line_in_modified_function_is_attributed(self, tmp_path: Path) -> None:
        """A docstring blank line is attributed when the same function also changed."""
        old_source = 'def helper():\n    """\n    Do the thing.\n\n    More detail.\n    """\n    return True\n'
        file_path = tmp_path / "module.py"
        file_path.write_text('def helper():\n    """\n    Do the thing.\n    More detail.\n    """\n    return False\n')

        diff_content = "--- a/module.py\n+++ b/module.py\n@@ -4,1 +3,0 @@\n-\n@@ -7,1 +6,1 @@\n-    return True\n+    return False\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value=old_source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.modified_symbols == {"helper"}, "the changed function stays reported"
        assert result.has_unattributed_changes is False, (
            "the blank line belongs to helper, which is modified on the new side"
        )

    def test_deletion_in_unmodified_method_of_modified_class_is_unattributed(self, tmp_path: Path) -> None:
        """A class-level match is not enough: the deleted line's method must have changed."""
        old_source = (
            "class Service:\n"
            "    def first(self):\n"
            "        setup()\n"
            "        return 1\n"
            "\n"
            "    def second(self):\n"
            "        return 2\n"
        )
        file_path = tmp_path / "module.py"
        file_path.write_text(
            "class Service:\n    def first(self):\n        setup()\n\n    def second(self):\n        return 3\n"
        )

        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -4,1 +4,0 @@\n"
            "-        return 1\n"
            "@@ -7,1 +6,1 @@\n"
            "-        return 2\n"
            "+        return 3\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value=old_source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.modified_symbols == {"Service"}, "the class is reported as modified"
        assert result.modified_members == {}, (
            "an unattributed deletion may hide a class-scope change, so member detail is dropped"
        )
        assert result.has_unattributed_changes is True, (
            "the deleted line belongs to first(), which has no changed line on the new side"
        )

    def test_deletion_in_modified_method_is_attributed(self, tmp_path: Path) -> None:
        """An in-place edit of one method stays attributed at member level."""
        old_source = (
            "class Service:\n    def first(self):\n        return 1\n\n    def second(self):\n        return 2\n"
        )
        file_path = tmp_path / "module.py"
        file_path.write_text(
            "class Service:\n    def first(self):\n        return 3\n\n    def second(self):\n        return 2\n"
        )

        diff_content = "--- a/module.py\n+++ b/module.py\n@@ -3,1 +3,1 @@\n-        return 1\n+        return 3\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value=old_source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.modified_members == {"Service": {"first"}}, "the edited method is tracked"
        assert result.has_unattributed_changes is False, (
            "the deleted line belongs to the same method that changed on the new side"
        )

    def test_deletion_falls_back_to_class_when_members_are_unmapped(self, tmp_path: Path) -> None:
        """A class-level change without member mapping keeps class-level attribution."""
        old_source = (
            "class Service:\n"
            "    def first(self):\n"
            "        setup()\n"
            "        return 1\n"
            "\n"
            "    def second(self):\n"
            "        return 2\n"
        )
        file_path = tmp_path / "module.py"
        file_path.write_text(
            "class Service:\n"
            "    timeout = 5\n"
            "\n"
            "    def first(self):\n"
            "        setup()\n"
            "\n"
            "    def second(self):\n"
            "        return 2\n"
        )

        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1,1 +1,2 @@\n"
            " class Service:\n"
            "+    timeout = 5\n"
            "@@ -4,1 +5,0 @@\n"
            "-        return 1\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value=old_source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.modified_members == {}, "an unmapped class line leaves member detail unknown"
        assert result.has_unattributed_changes is False, (
            "without member detail the deletion is attributed at class level"
        )

    def test_class_scope_deletion_drops_member_narrowing(self, tmp_path: Path) -> None:
        """A removed class decorator changes every member, so narrowing must not survive."""
        old_source = (
            "@dataclass\n"
            "class Service:\n"
            "    def first(self):\n"
            "        return 1\n"
            "\n"
            "    def second(self):\n"
            "        return 2\n"
        )
        file_path = tmp_path / "module.py"
        file_path.write_text(
            "class Service:\n    def first(self):\n        return 1\n\n    def second(self):\n        return 3\n"
        )

        diff_content = (
            "--- a/module.py\n"
            "+++ b/module.py\n"
            "@@ -1,1 +0,0 @@\n"
            "-@dataclass\n"
            "@@ -7,1 +6,1 @@\n"
            "-        return 2\n"
            "+        return 3\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_old_file_source",
                return_value=old_source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "a resolvable diff must produce a classification, not None"
        assert result.modified_symbols == {"Service"}, "the class is reported as modified"
        assert result.modified_members == {}, (
            "a removed class decorator affects every member, so narrowing to second() would skip first()"
        )
        assert result.has_unattributed_changes is False, (
            "a class-scope deletion is attributed to the class itself, which is reported as modified"
        )


class TestFetchOldFileSourceRevision:
    """The old file must come from the revision the diff was computed against."""

    @pytest.fixture(autouse=True)
    def _clear_revision_cache(self) -> None:
        """The resolved revision is cached per run, so isolate every test."""
        _OLD_REVISION_CACHE.clear()
        yield
        _OLD_REVISION_CACHE.clear()

    @staticmethod
    def _json_response(payload: dict) -> MagicMock:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode()
        return response

    def test_local_mode_reads_the_merge_base(self, tmp_path: Path) -> None:
        """``git diff main...HEAD`` is relative to the merge base, not to main's tip."""
        file_path = tmp_path / "module.py"
        file_path.write_text("def helper():\n    return True\n")
        merge_base_result = MagicMock(returncode=0, stdout="mergebasesha\n", stderr="")
        show_result = MagicMock(returncode=0, stdout="def helper():\n    return False\n", stderr="")

        with patch(
            target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            side_effect=[merge_base_result, show_result],
        ) as run_mock:
            content = _fetch_old_file_source(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert content == "def helper():\n    return False\n", "the base content must be returned"
        commands = [call.args[0] for call in run_mock.call_args_list]
        assert commands == [
            ["git", "merge-base", "main", "HEAD"],
            ["git", "show", "mergebasesha:module.py"],
        ], f"the file must be read from the merge base, not from main: {commands}"

    def test_local_mode_unresolvable_merge_base_is_conservative(self, tmp_path: Path) -> None:
        """Without a merge base the old content is unknown, so nothing is attributed."""
        file_path = tmp_path / "module.py"
        file_path.write_text("def helper():\n    return True\n")
        merge_base_result = MagicMock(returncode=1, stdout="", stderr="fatal: no merge base")

        with patch(
            target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            side_effect=[merge_base_result],
        ) as run_mock:
            content = _fetch_old_file_source(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert content is None, "an unresolvable merge base must not fall back to the base tip"
        assert len(run_mock.call_args_list) == 1, "no file read may happen without a merge base"

    def test_remote_mode_reads_the_merge_base(self, tmp_path: Path) -> None:
        """The pull-request patch is relative to the merge base, so the Contents API must use it."""
        file_path = tmp_path / "module.py"
        file_path.write_text("def helper():\n    return True\n")
        compare_response = self._json_response({"merge_base_commit": {"sha": "mergebasesha"}})
        contents_response = self._json_response({
            "encoding": "base64",
            "content": base64.b64encode(b"def helper():\n    return False\n").decode(),
        })

        with (
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer._fetch_pr_head_sha",
                return_value="headsha",
            ),
            patch(
                target="scripts.tests_analyzer.pytest_marker_analyzer.urllib.request.urlopen",
                side_effect=[compare_response, contents_response],
            ) as urlopen_mock,
        ):
            content = _fetch_old_file_source(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info={"repo": "owner/repo", "pr_number": 7, "token": "token"},
            )

        assert content == "def helper():\n    return False\n", "the base content must be returned"
        urls = [call.args[0].full_url for call in urlopen_mock.call_args_list]
        assert any("/compare/main...headsha" in url for url in urls), f"the merge base must be resolved: {urls}"
        assert urls[-1].endswith("?ref=mergebasesha"), f"the file must be read at the merge base: {urls[-1]}"

    def test_merge_base_is_resolved_once_per_run(self, tmp_path: Path) -> None:
        """The merge base is a property of the run, so it is resolved once."""
        file_path = tmp_path / "module.py"
        file_path.write_text("def helper():\n    return True\n")
        merge_base_result = MagicMock(returncode=0, stdout="mergebasesha\n", stderr="")
        show_result = MagicMock(returncode=0, stdout="def helper():\n    return False\n", stderr="")

        with patch(
            target="scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            side_effect=[merge_base_result, show_result, show_result],
        ) as run_mock:
            for _ in range(2):
                _fetch_old_file_source(
                    file_path=file_path,
                    base_branch="main",
                    repo_root=tmp_path,
                    github_pr_info=None,
                )

        merge_base_calls = [call for call in run_mock.call_args_list if call.args[0][1] == "merge-base"]
        assert len(merge_base_calls) == 1, f"the merge base must be resolved once per run: {merge_base_calls}"


class TestCheckConftestPathwayEmptyCleanClassification:
    """An empty-and-clean classification must resolve the conftest pathway as safe."""

    @pytest.fixture(scope="function")
    def pathway_builder(self, tmp_path: Path) -> Callable[[SymbolClassification], Pathway]:
        """Build a conftest pathway that opaquely imports a changed module.

        Args:
            tmp_path: Pytest temporary directory used as the repository root.

        Returns:
            A builder taking the changed file's classification and returning the
            changed file, a marked test depending on the conftest, and the
            classification cache keyed by the changed file.
        """

        def build(classification: SymbolClassification) -> Pathway:
            conftest_path = tmp_path / "tests" / "conftest.py"
            conftest_path.parent.mkdir(parents=True)
            conftest_path.touch()

            changed_file = tmp_path / "utilities" / "ssp.py"
            changed_file.parent.mkdir(parents=True)
            changed_file.touch()

            test_file = tmp_path / "tests" / "test_ssp.py"
            test_file.touch()

            marked_test = MarkedTest(
                file_path=test_file,
                test_name="test_ssp",
                node_id="tests/test_ssp.py::test_ssp",
                dependencies={conftest_path},
                fixtures=set(),
                symbol_imports={},
            )
            return changed_file, marked_test, {changed_file: classification}

        return build

    def test_empty_clean_classification_is_not_affected(
        self,
        pathway_builder: Callable[[SymbolClassification], Pathway],
        tmp_path: Path,
    ) -> None:
        """Nothing observable changed — every opaque importer must not be flagged."""
        changed_file, marked_test, modified_symbols_cache = pathway_builder(
            SymbolClassification(modified_symbols=set(), new_symbols=set(), has_unattributed_changes=False)
        )

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports={},
            conftest_opaque_deps={tmp_path / "tests" / "conftest.py": {changed_file}},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict={},
            repo_root=tmp_path,
        )

        assert is_affected is False, f"empty-and-clean classification must not flag tests, got {matching_deps}"
        assert matching_deps == [], "an empty-and-clean classification must produce no dependency entries"

    def test_unattributed_changes_still_flag(
        self,
        pathway_builder: Callable[[SymbolClassification], Pathway],
        tmp_path: Path,
    ) -> None:
        """Module-level changes we could not attribute stay conservative."""
        changed_file, marked_test, modified_symbols_cache = pathway_builder(
            SymbolClassification(modified_symbols=set(), new_symbols=set(), has_unattributed_changes=True)
        )

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports={},
            conftest_opaque_deps={tmp_path / "tests" / "conftest.py": {changed_file}},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict={},
            repo_root=tmp_path,
        )

        assert is_affected is True, "unattributed changes must still flag the test through the conftest pathway"
        assert matching_deps, "a flagged pathway must report the dependency that caused it"

    def test_deletion_only_body_edit_flags_instead_of_resolving(
        self,
        pathway_builder: Callable[[SymbolClassification], Pathway],
        tmp_path: Path,
    ) -> None:
        """A diff that only deletes a body statement must not resolve as safe."""
        changed_path = tmp_path / "module.py"
        changed_path.write_text("def helper():\n    return True\n")
        diff_content = (
            '--- a/module.py\n+++ b/module.py\n@@ -1,3 +1,2 @@\n def helper():\n-    return "debug"\n     return True\n'
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            classification = _extract_modified_symbols(
                file_path=changed_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert classification is not None, "a resolvable diff must produce a classification, not None"
        assert classification.has_unattributed_changes is True, (
            "a deletion-only body edit must not look like an empty-and-clean diff"
        )

        changed_file, marked_test, modified_symbols_cache = pathway_builder(classification)
        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports={},
            conftest_opaque_deps={tmp_path / "tests" / "conftest.py": {changed_file}},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict={},
            repo_root=tmp_path,
        )

        assert is_affected is True, "a deletion-only body edit must flag the test instead of resolving the pathway"
        assert matching_deps, "a flagged pathway must report the dependency that caused it"


class TestRunGithubModeCheckoutGithubPrInfo:
    """Verify that checkout mode passes github_pr_info to MarkerTestAnalyzer.

    When --checkout is used, the analyzer must still receive github_pr_info
    so the GitHub API diffs cache is available as fallback when local git
    diff fails (e.g., base branch fetch failure or shallow clone).
    """

    @patch("scripts.tests_analyzer.pytest_marker_analyzer.cleanup_temp_dir")
    @patch("scripts.tests_analyzer.pytest_marker_analyzer.os.chdir")
    @patch("scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run")
    @patch("scripts.tests_analyzer.pytest_marker_analyzer.checkout_pr")
    @patch("scripts.tests_analyzer.pytest_marker_analyzer.get_pr_changed_files", return_value=["some_file.py"])
    @patch(
        "scripts.tests_analyzer.pytest_marker_analyzer.get_pr_info",
        return_value={"base_ref": "main", "head_ref": "feature-branch"},
    )
    @patch("scripts.tests_analyzer.pytest_marker_analyzer.MarkerTestAnalyzer")
    def test_checkout_mode_passes_github_pr_info(
        self,
        mock_analyzer_cls,
        mock_get_pr_info,
        mock_get_changed_files,
        mock_checkout_pr,
        mock_subprocess_run,
        mock_chdir,
        mock_cleanup,
        tmp_path,
    ):
        """Checkout mode must pass github_pr_info dict, not None."""
        mock_analyzer = MagicMock()
        mock_analyzer.marked_tests = ["test_something"]
        mock_analyzer.analyze_impact.return_value = MagicMock()
        mock_analyzer_cls.return_value = mock_analyzer

        args = argparse.Namespace(
            repo="org/repo",
            pr=42,
            github_token="fake-token",
            checkout=True,
            workdir=tmp_path,
            work_dir=None,
            markers="smoke",
        )

        run_github_mode(args=args)

        constructor_kwargs = mock_analyzer_cls.call_args
        actual_github_pr_info = constructor_kwargs.kwargs["github_pr_info"]

        assert actual_github_pr_info is not None, (
            "github_pr_info must not be None in checkout mode; it is needed as fallback when local git diff fails"
        )
        assert actual_github_pr_info["repo"] == "org/repo"
        assert actual_github_pr_info["pr_number"] == 42
        assert actual_github_pr_info["token"] == "fake-token"


class TestCheckConftestPathwayNoFixtureMatch:
    """Conftest imports a modified symbol but no fixture used by the test calls it."""

    def test_no_fixture_calls_overlapping_symbol_does_not_flag(self, tmp_path: Path) -> None:
        """When no fixture calls the overlapping symbol the test should NOT be flagged.

        Previously this was a false positive: the analyzer conservatively flagged
        the test even though no fixture connected the modified symbol to the test.
        """
        repo_root = tmp_path
        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        changed_file = tmp_path / "utilities" / "network.py"
        changed_file.parent.mkdir(parents=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_vm_deletion.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_vm_deletion",
            node_id="tests/test_vm_deletion.py::test_vm_deletion",
            dependencies={conftest_path},
            fixtures={"some_unrelated_fixture"},
            symbol_imports={},
        )

        # Conftest imports lookup_iface_status from the changed file
        conftest_symbol_imports: dict[Path, dict[Path, set[str]]] = {
            conftest_path: {changed_file: {"lookup_iface_status"}},
        }

        # lookup_iface_status was modified
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols={"lookup_iface_status"},
                new_symbols=set(),
            ),
        }

        # The fixture used by the test does NOT call lookup_iface_status
        fixtures_dict: dict[str, Fixture] = {
            "some_unrelated_fixture": Fixture(
                name="some_unrelated_fixture",
                file_path=conftest_path,
                function_calls={"other_function"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports=conftest_symbol_imports,
            conftest_opaque_deps={},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert not is_affected, (
            f"Test should NOT be flagged when no fixture calls the modified symbol, "
            f"but got matching_deps={matching_deps}"
        )
        assert matching_deps == [], f"no dependency should be reported, but got {matching_deps}"

    def test_hierarchy_scans_past_no_fixture_match_conftest(self, tmp_path: Path) -> None:
        """When the first conftest has no fixture match, later conftests must still be checked.

        A test can inherit multiple conftest.py files. If the first conftest
        imports the modified symbol but no fixture calls it (safe), the loop
        must continue to check subsequent conftest files that may have a real
        fixture dependency.
        """
        repo_root = tmp_path
        # First conftest: imports modified symbol, but no fixture match
        conftest_parent = tmp_path / "tests" / "conftest.py"
        conftest_parent.parent.mkdir(parents=True)
        conftest_parent.touch()

        # Second conftest: imports modified symbol AND has a matching fixture
        conftest_child = tmp_path / "tests" / "network" / "conftest.py"
        conftest_child.parent.mkdir(parents=True)
        conftest_child.touch()

        changed_file = tmp_path / "utilities" / "network.py"
        changed_file.parent.mkdir(parents=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "network" / "test_connectivity.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_connectivity",
            node_id="tests/network/test_connectivity.py::test_connectivity",
            dependencies={conftest_parent, conftest_child},
            fixtures={"unrelated_fixture", "network_fixture"},
            symbol_imports={},
        )

        # Both conftests import lookup_iface_status from the changed file
        conftest_symbol_imports: dict[Path, dict[Path, set[str]]] = {
            conftest_parent: {changed_file: {"lookup_iface_status"}},
            conftest_child: {changed_file: {"lookup_iface_status"}},
        }

        # lookup_iface_status was modified
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols={"lookup_iface_status"},
                new_symbols=set(),
            ),
        }

        # First conftest: fixture does NOT call lookup_iface_status
        # Second conftest: fixture DOES call lookup_iface_status
        fixtures_dict: dict[str, Fixture] = {
            "unrelated_fixture": Fixture(
                name="unrelated_fixture",
                file_path=conftest_parent,
                function_calls={"other_function"},
            ),
            "network_fixture": Fixture(
                name="network_fixture",
                file_path=conftest_child,
                function_calls={"lookup_iface_status"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports=conftest_symbol_imports,
            conftest_opaque_deps={},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert is_affected, (
            "Test SHOULD be flagged when a later conftest in the hierarchy has a fixture that calls the modified symbol"
        )
        assert matching_deps, "Should have at least one matching dependency"
        assert any("network_fixture" in dep for dep in matching_deps), (
            f"Should reference network_fixture, got {matching_deps}"
        )

    def test_diff_unavailable_no_fixture_match_does_not_flag(self, tmp_path: Path) -> None:
        """When the diff for the changed file is unavailable but no fixture used
        by the test calls the imported symbols, the test should NOT be flagged.
        Fixture narrowing should apply even without diff info.
        """
        repo_root = tmp_path
        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        changed_file = tmp_path / "utilities" / "storage.py"
        changed_file.parent.mkdir(parents=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_csv.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_csv_properties",
            node_id="tests/test_csv.py::test_csv_properties",
            dependencies={conftest_path},
            fixtures={"csv_scope_session"},
            symbol_imports={},
        )

        # Conftest imports wait_for_default_sc from the changed file
        conftest_symbol_imports: dict[Path, dict[Path, set[str]]] = {
            conftest_path: {changed_file: {"wait_for_default_sc_in_cdiconfig"}},
        }

        # Diff unavailable — classification is None
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: None,
        }

        # The fixture used by the test does NOT call wait_for_default_sc_in_cdiconfig
        fixtures_dict: dict[str, Fixture] = {
            "csv_scope_session": Fixture(
                name="csv_scope_session",
                file_path=conftest_path,
                function_calls={"get_csv", "other_function"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports=conftest_symbol_imports,
            conftest_opaque_deps={},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert not is_affected, (
            f"Test should NOT be flagged when diff is unavailable and no fixture "
            f"calls the imported symbols, but got matching_deps={matching_deps}"
        )
        assert matching_deps == []


class TestRenamedFileHandling:
    """Tests that renamed files with no content changes do not flag tests as affected.

    When GitHub reports file_status="renamed" with no diff patch, the file was
    only moved (e.g., tests/network/libs/ip.py -> libs/net/ip.py). All symbols
    exist in the new location but none were modified, so zero tests should be
    impacted.
    """

    def test_extract_modified_symbols_renamed_file_returns_empty(self, tmp_path: Path) -> None:
        """Renamed file with no content changes should return empty classification (no impact)."""
        source = textwrap.dedent("""\
            def helper_func():
                return 42

            class MyClass:
                def method(self):
                    pass
        """)
        file_path = tmp_path / "ip.py"
        file_path.write_text(source)

        result = _extract_modified_symbols(
            file_path=file_path,
            base_branch="main",
            repo_root=tmp_path,
            github_pr_info=None,
            file_status="renamed",
        )

        assert result is not None, "Renamed file should return SymbolClassification, not None"
        assert result.modified_symbols == set(), "Renamed file should have no modified symbols"
        assert result.new_symbols == set(), "Renamed file with no content changes should have no new symbols"

    def test_extract_modified_items_from_conftest_renamed_returns_empty(self, tmp_path: Path) -> None:
        """Renamed conftest.py should not flag any fixtures or functions as modified."""
        conftest = tmp_path / "conftest.py"
        conftest.write_text(
            textwrap.dedent("""\
            import pytest

            @pytest.fixture()
            def my_fixture():
                return 42

            @pytest.fixture()
            def another_fixture():
                return "hello"

            def helper():
                pass
        """)
        )

        modified_fixtures, modified_functions = _extract_modified_items_from_conftest(
            changed_file=conftest,
            base_branch="main",
            repo_root=tmp_path,
            github_pr_info=None,
            file_status="renamed",
        )

        assert modified_fixtures == set(), "Renamed conftest should not flag any fixtures"
        assert modified_functions == set(), "Renamed conftest should not flag any functions"


class TestImportVisitorTypeChecking:
    """Tests for TYPE_CHECKING-guarded import exclusion."""

    def test_regular_imports_collected(self):
        source = textwrap.dedent("""\
            from libs.vm.vm import BaseVirtualMachine
            from libs.net.ip import get_ip
        """)
        tree = ast.parse(source)
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        assert "libs.vm.vm" in visitor.imports
        assert "libs.net.ip" in visitor.imports

    def test_type_checking_imports_skipped(self):
        source = textwrap.dedent("""\
            from typing import TYPE_CHECKING

            from libs.net.ip import get_ip

            if TYPE_CHECKING:
                from libs.vm.vm import BaseVirtualMachine
        """)
        tree = ast.parse(source)
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        assert "libs.net.ip" in visitor.imports
        assert "libs.vm.vm" not in visitor.imports
        assert "libs.vm.vm.BaseVirtualMachine" not in visitor.imports

    def test_typing_dot_type_checking_skipped(self):
        source = textwrap.dedent("""\
            import typing

            from libs.net.ip import get_ip

            if typing.TYPE_CHECKING:
                from libs.vm.vm import BaseVirtualMachine
        """)
        tree = ast.parse(source)
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        assert "libs.net.ip" in visitor.imports
        assert "libs.vm.vm" not in visitor.imports

    def test_type_checking_does_not_affect_symbol_imports(self):
        source = textwrap.dedent("""\
            from typing import TYPE_CHECKING
            from libs.net.ip import get_ip

            if TYPE_CHECKING:
                from libs.vm.vm import BaseVirtualMachine
        """)
        tree = ast.parse(source)
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        assert "libs.net.ip" in visitor.symbol_imports
        assert "libs.vm.vm" not in visitor.symbol_imports

    def test_bare_import_inside_type_checking_skipped(self):
        source = textwrap.dedent("""\
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                import libs.vm.vm
        """)
        tree = ast.parse(source)
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        assert "libs.vm.vm" not in visitor.imports
        assert "libs.vm.vm" not in visitor.opaque_imports

    def test_else_branch_of_type_checking_collected(self):
        source = textwrap.dedent("""\
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                from typing_extensions import Protocol
            else:
                from collections.abc import Protocol
        """)
        tree = ast.parse(source)
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        assert "typing_extensions" not in visitor.imports
        assert "collections.abc" in visitor.imports

    def test_elif_after_type_checking_collected(self):
        source = textwrap.dedent("""\
            from typing import TYPE_CHECKING
            import sys

            if TYPE_CHECKING:
                from libs.vm.vm import BaseVirtualMachine
            elif sys.version_info >= (3, 11):
                from libs.fallback import FallbackVM
        """)
        tree = ast.parse(source)
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        assert "libs.vm.vm" not in visitor.imports
        assert "libs.fallback" in visitor.imports

    def test_non_typing_type_checking_not_skipped(self):
        source = textwrap.dedent("""\
            import settings

            from libs.net.ip import get_ip

            if settings.TYPE_CHECKING:
                from libs.vm.vm import BaseVirtualMachine
        """)
        tree = ast.parse(source)
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        assert "libs.net.ip" in visitor.imports
        assert "libs.vm.vm" in visitor.imports


class TestCheckConftestPathwayOpaqueNarrowing:
    """Opaque conftest imports should use symbol-level narrowing when available."""

    def test_opaque_import_narrowed_by_modified_symbols(self, tmp_path: Path) -> None:
        """When conftest opaquely imports a changed file but no fixture calls modified symbols, test is safe."""
        repo_root = tmp_path
        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        changed_file = tmp_path / "utilities" / "hco.py"
        changed_file.parent.mkdir(parents=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_smoke.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_smoke",
            node_id="tests/test_smoke.py::test_smoke",
            dependencies={conftest_path},
            fixtures={"vm_fixture"},
            symbol_imports={},
        )

        # Conftest opaquely imports the changed file
        conftest_opaque_deps: dict[Path, set[Path]] = {
            conftest_path: {changed_file},
        }

        # Symbol analysis shows only verify_boot_sources was modified
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols={"verify_boot_sources_reimported"},
                new_symbols=set(),
            ),
        }

        # The test's fixture does NOT call verify_boot_sources_reimported
        fixtures_dict: dict[str, Fixture] = {
            "vm_fixture": Fixture(
                name="vm_fixture",
                file_path=conftest_path,
                function_calls={"create_vm", "wait_for_vm"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports={},
            conftest_opaque_deps=conftest_opaque_deps,
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert not is_affected, (
            f"Test should NOT be flagged when opaque import is narrowed and no fixture calls modified symbols, "
            f"but got matching_deps={matching_deps}"
        )

    def test_opaque_import_flags_when_fixture_calls_modified_symbol(self, tmp_path: Path) -> None:
        """When conftest opaquely imports a changed file AND a fixture calls the modified symbol, flag test."""
        repo_root = tmp_path
        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        changed_file = tmp_path / "utilities" / "hco.py"
        changed_file.parent.mkdir(parents=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_hco_update.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_hco_update",
            node_id="tests/test_hco_update.py::test_hco_update",
            dependencies={conftest_path},
            fixtures={"hco_fixture"},
            symbol_imports={},
        )

        conftest_opaque_deps: dict[Path, set[Path]] = {
            conftest_path: {changed_file},
        }

        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols={"verify_boot_sources_reimported"},
                new_symbols=set(),
            ),
        }

        # This fixture DOES call the modified symbol
        fixtures_dict: dict[str, Fixture] = {
            "hco_fixture": Fixture(
                name="hco_fixture",
                file_path=conftest_path,
                function_calls={"verify_boot_sources_reimported", "get_hco_cr"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports={},
            conftest_opaque_deps=conftest_opaque_deps,
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert is_affected, "Test SHOULD be flagged when fixture calls the modified symbol"
        assert any("via fixture hco_fixture" in dep for dep in matching_deps)

    def test_opaque_import_only_new_symbols_skips(self, tmp_path: Path) -> None:
        """When opaquely imported file has only new symbols (no modifications), test is safe."""
        repo_root = tmp_path
        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        changed_file = tmp_path / "utilities" / "hco.py"
        changed_file.parent.mkdir(parents=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_smoke.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_smoke",
            node_id="tests/test_smoke.py::test_smoke",
            dependencies={conftest_path},
            fixtures={"vm_fixture"},
            symbol_imports={},
        )

        conftest_opaque_deps: dict[Path, set[Path]] = {
            conftest_path: {changed_file},
        }

        # Only new symbols — nothing was modified
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols=set(),
                new_symbols={"new_helper_function"},
            ),
        }

        fixtures_dict: dict[str, Fixture] = {
            "vm_fixture": Fixture(
                name="vm_fixture",
                file_path=conftest_path,
                function_calls={"create_vm"},
            ),
        }

        is_affected, _ = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports={},
            conftest_opaque_deps=conftest_opaque_deps,
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert not is_affected, "Test should NOT be flagged when only new symbols were added"

    def test_opaque_import_no_classification_falls_back(self, tmp_path: Path) -> None:
        """When classification is None (diff failed), fall back to conservative file-level flagging."""
        repo_root = tmp_path
        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        changed_file = tmp_path / "utilities" / "hco.py"
        changed_file.parent.mkdir(parents=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_smoke.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_smoke",
            node_id="tests/test_smoke.py::test_smoke",
            dependencies={conftest_path},
            fixtures={"vm_fixture"},
            symbol_imports={},
        )

        conftest_opaque_deps: dict[Path, set[Path]] = {
            conftest_path: {changed_file},
        }

        # Classification is None — diff parsing failed
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: None,
        }

        fixtures_dict: dict[str, Fixture] = {
            "vm_fixture": Fixture(
                name="vm_fixture",
                file_path=conftest_path,
                function_calls={"create_vm"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports={},
            conftest_opaque_deps=conftest_opaque_deps,
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert is_affected, "Test SHOULD be flagged when classification is None (conservative fallback)"
        assert any("opaque import" in dep for dep in matching_deps)


class TestCheckConftestPathwayTransitive:
    """Transitive conftest narrowing: conftest -> intermediate -> changed_file."""

    def test_transitive_no_fixture_match_does_not_flag(self, tmp_path: Path) -> None:
        """When conftest imports an intermediate module that imports the changed file,
        but no fixture used by the test calls the intermediate's symbols, the test
        should NOT be flagged.
        """
        repo_root = tmp_path

        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        intermediate_path = tmp_path / "libs" / "net" / "vmspec.py"
        intermediate_path.parent.mkdir(parents=True, exist_ok=True)
        # Intermediate module imports BaseVirtualMachine from the changed file
        intermediate_path.write_text(
            "from libs.vm.vm import BaseVirtualMachine\n",
            encoding="utf-8",
        )

        changed_file = tmp_path / "libs" / "vm" / "vm.py"
        changed_file.parent.mkdir(parents=True, exist_ok=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_smoke.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_smoke_basic",
            node_id="tests/test_smoke.py::test_smoke_basic",
            dependencies={conftest_path, intermediate_path, changed_file},
            fixtures={"some_unrelated_fixture"},
            symbol_imports={},
        )

        # Conftest imports lookup_iface_status from the intermediate (NOT directly from changed_file)
        conftest_symbol_imports: dict[Path, dict[Path, set[str]]] = {
            conftest_path: {intermediate_path: {"lookup_iface_status"}},
        }

        # BaseVirtualMachine was modified in the changed file
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols={"BaseVirtualMachine"},
                new_symbols=set(),
            ),
        }

        # The fixture used by the test does NOT call lookup_iface_status
        fixtures_dict: dict[str, Fixture] = {
            "some_unrelated_fixture": Fixture(
                name="some_unrelated_fixture",
                file_path=conftest_path,
                function_calls={"other_function"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports=conftest_symbol_imports,
            conftest_opaque_deps={},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert not is_affected, (
            f"Test should NOT be flagged via transitive path when no fixture calls "
            f"the intermediate module's symbols, but got matching_deps={matching_deps}"
        )
        assert matching_deps == []

    def test_transitive_with_fixture_match_flags_test(self, tmp_path: Path) -> None:
        """When a fixture used by the test calls the intermediate module's symbols,
        and the intermediate imports modified symbols from the changed file,
        the test SHOULD be flagged.
        """
        repo_root = tmp_path

        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        intermediate_path = tmp_path / "libs" / "net" / "vmspec.py"
        intermediate_path.parent.mkdir(parents=True, exist_ok=True)
        intermediate_path.write_text(
            "from libs.vm.vm import BaseVirtualMachine\n",
            encoding="utf-8",
        )

        changed_file = tmp_path / "libs" / "vm" / "vm.py"
        changed_file.parent.mkdir(parents=True, exist_ok=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_upgrade.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_upgrade_network",
            node_id="tests/test_upgrade.py::test_upgrade_network",
            dependencies={conftest_path, intermediate_path, changed_file},
            fixtures={"running_vm_upgrade_a"},
            symbol_imports={},
        )

        conftest_symbol_imports: dict[Path, dict[Path, set[str]]] = {
            conftest_path: {intermediate_path: {"lookup_iface_status"}},
        }

        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols={"BaseVirtualMachine"},
                new_symbols=set(),
            ),
        }

        # This fixture DOES call lookup_iface_status AND the test uses it
        fixtures_dict: dict[str, Fixture] = {
            "running_vm_upgrade_a": Fixture(
                name="running_vm_upgrade_a",
                file_path=conftest_path,
                function_calls={"lookup_iface_status", "other_call"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports=conftest_symbol_imports,
            conftest_opaque_deps={},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert is_affected, "Test SHOULD be flagged when fixture uses transitive dependency"
        assert len(matching_deps) == 1
        assert "lookup_iface_status" in matching_deps[0]

    def test_transitive_no_overlapping_symbols_does_not_flag(self, tmp_path: Path) -> None:
        """When the intermediate imports from the changed file but none of the
        modified symbols overlap, the test should NOT be flagged.
        """
        repo_root = tmp_path

        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        intermediate_path = tmp_path / "libs" / "net" / "vmspec.py"
        intermediate_path.parent.mkdir(parents=True, exist_ok=True)
        # Intermediate imports BaseVirtualMachine but only container_image was modified
        intermediate_path.write_text(
            "from libs.vm.vm import BaseVirtualMachine\n",
            encoding="utf-8",
        )

        changed_file = tmp_path / "libs" / "vm" / "vm.py"
        changed_file.parent.mkdir(parents=True, exist_ok=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_smoke.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_smoke_basic",
            node_id="tests/test_smoke.py::test_smoke_basic",
            dependencies={conftest_path, intermediate_path, changed_file},
            fixtures={"running_vm_upgrade_a"},
            symbol_imports={},
        )

        conftest_symbol_imports: dict[Path, dict[Path, set[str]]] = {
            conftest_path: {intermediate_path: {"lookup_iface_status"}},
        }

        # Only container_image was modified, NOT BaseVirtualMachine
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols={"container_image"},
                new_symbols=set(),
            ),
        }

        fixtures_dict: dict[str, Fixture] = {
            "running_vm_upgrade_a": Fixture(
                name="running_vm_upgrade_a",
                file_path=conftest_path,
                function_calls={"lookup_iface_status"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports=conftest_symbol_imports,
            conftest_opaque_deps={},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert not is_affected, (
            f"Test should NOT be flagged when modified symbols don't overlap with "
            f"intermediate imports, but got matching_deps={matching_deps}"
        )

    def test_transitive_diff_unavailable_no_fixture_match_does_not_flag(self, tmp_path: Path) -> None:
        """When the diff for the changed file is unavailable but no fixture used
        by the test calls the intermediate module's symbols, the test should NOT
        be flagged. Fixture narrowing should still apply even without diff info.
        """
        repo_root = tmp_path

        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        intermediate_path = tmp_path / "libs" / "net" / "vmspec.py"
        intermediate_path.parent.mkdir(parents=True, exist_ok=True)
        intermediate_path.write_text(
            "from libs.vm.vm import BaseVirtualMachine\n",
            encoding="utf-8",
        )

        changed_file = tmp_path / "libs" / "vm" / "vm.py"
        changed_file.parent.mkdir(parents=True, exist_ok=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_smoke.py"
        test_file.touch()

        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_smoke_basic",
            node_id="tests/test_smoke.py::test_smoke_basic",
            dependencies={conftest_path, intermediate_path, changed_file},
            fixtures={"some_unrelated_fixture"},
            symbol_imports={},
        )

        conftest_symbol_imports: dict[Path, dict[Path, set[str]]] = {
            conftest_path: {intermediate_path: {"lookup_iface_status"}},
        }

        # Diff unavailable — classification is None
        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: None,
        }

        fixtures_dict: dict[str, Fixture] = {
            "some_unrelated_fixture": Fixture(
                name="some_unrelated_fixture",
                file_path=conftest_path,
                function_calls={"other_function"},
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports=conftest_symbol_imports,
            conftest_opaque_deps={},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert not is_affected, (
            f"Test should NOT be flagged even with diff unavailable when no fixture "
            f"calls the intermediate module's symbols, but got matching_deps={matching_deps}"
        )
        assert matching_deps == []

    def test_transitive_fixture_chain_flags_test(self, tmp_path: Path) -> None:
        """When fixture_a depends on fixture_b and fixture_b calls the
        intermediate module's symbols, the test should be flagged even though
        the test only directly uses fixture_a.
        """
        repo_root = tmp_path

        conftest_path = tmp_path / "tests" / "conftest.py"
        conftest_path.parent.mkdir(parents=True)
        conftest_path.touch()

        intermediate_path = tmp_path / "libs" / "net" / "vmspec.py"
        intermediate_path.parent.mkdir(parents=True, exist_ok=True)
        intermediate_path.write_text(
            "from libs.vm.vm import BaseVirtualMachine\n",
            encoding="utf-8",
        )

        changed_file = tmp_path / "libs" / "vm" / "vm.py"
        changed_file.parent.mkdir(parents=True, exist_ok=True)
        changed_file.touch()

        test_file = tmp_path / "tests" / "test_upgrade.py"
        test_file.touch()

        # Test only directly uses fixture_a, but fixture_a depends on fixture_b
        marked_test = MarkedTest(
            file_path=test_file,
            test_name="test_upgrade_vm",
            node_id="tests/test_upgrade.py::test_upgrade_vm",
            dependencies={conftest_path, intermediate_path, changed_file},
            fixtures={"fixture_a"},
            symbol_imports={},
        )

        conftest_symbol_imports: dict[Path, dict[Path, set[str]]] = {
            conftest_path: {intermediate_path: {"lookup_iface_status"}},
        }

        modified_symbols_cache: dict[Path, SymbolClassification | None] = {
            changed_file: SymbolClassification(
                modified_symbols={"BaseVirtualMachine"},
                new_symbols=set(),
            ),
        }

        # fixture_a depends on fixture_b, fixture_b calls lookup_iface_status
        fixtures_dict: dict[str, Fixture] = {
            "fixture_a": Fixture(
                name="fixture_a",
                file_path=conftest_path,
                function_calls={"some_setup"},
                fixture_deps={"fixture_b"},
            ),
            "fixture_b": Fixture(
                name="fixture_b",
                file_path=conftest_path,
                function_calls={"lookup_iface_status"},
                fixture_deps=set(),
            ),
        }

        is_affected, matching_deps = _check_conftest_pathway(
            changed_file=changed_file,
            marked_test=marked_test,
            conftest_symbol_imports=conftest_symbol_imports,
            conftest_opaque_deps={},
            modified_symbols_cache=modified_symbols_cache,
            fixtures_dict=fixtures_dict,
            repo_root=repo_root,
        )

        assert is_affected, (
            "Test SHOULD be flagged when fixture_b (transitively used via fixture_a) "
            "calls the intermediate module's symbols"
        )
        assert len(matching_deps) == 1
        assert "lookup_iface_status" in matching_deps[0]


class TestExtractDeletedSymbolsFromDiff:
    """Tests for _extract_deleted_symbols_from_diff extracting function/class names."""

    def test_deleted_function(self) -> None:
        """Detects deleted function definitions."""
        diff = (
            "@@ -10,5 +10,0 @@\n"
            "-def skip_no_reencrypt_route(upload_proxy_route):\n"
            "-    if upload_proxy_route.termination != 'reencrypt':\n"
            "-        pytest.skip('Skip testing.')\n"
        )
        result = _extract_deleted_symbols_from_diff(diff_content=diff)
        assert result == {"skip_no_reencrypt_route"}

    def test_deleted_async_function(self) -> None:
        """Detects deleted async function definitions."""
        diff = "@@ -1,3 +1,0 @@\n-async def fetch_data(url):\n-    return await get(url)\n"
        result = _extract_deleted_symbols_from_diff(diff_content=diff)
        assert result == {"fetch_data"}

    def test_deleted_class_and_members(self) -> None:
        """Deleted class and its member methods are both extracted as symbols."""
        diff = "@@ -1,4 +1,0 @@\n-class OldHelper:\n-    def method(self):\n-        pass\n"
        result = _extract_deleted_symbols_from_diff(diff_content=diff)
        assert result == {"OldHelper", "method"}

    def test_no_deletions_returns_empty(self) -> None:
        """No deletion lines produces empty set."""
        diff = "@@ -1,2 +1,3 @@\n context\n+new_line\n context\n"
        result = _extract_deleted_symbols_from_diff(diff_content=diff)
        assert result == set()

    def test_file_header_not_matched(self) -> None:
        """--- file header is not treated as a deletion."""
        diff = "--- a/old_file.py\n+++ b/new_file.py\n@@ -1,1 +1,1 @@\n-old_content\n+new_content\n"
        result = _extract_deleted_symbols_from_diff(diff_content=diff)
        assert result == set()

    def test_mixed_deletions_and_additions(self) -> None:
        """Only deleted symbol definitions are captured, not added ones."""
        diff = "@@ -1,4 +1,4 @@\n-def old_func():\n-    pass\n+def new_func():\n+    pass\n"
        result = _extract_deleted_symbols_from_diff(diff_content=diff)
        assert result == {"old_func"}

    def test_deleted_class_member_collides_with_toplevel(self) -> None:
        """Deleted class members are returned as bare names, which may collide with unrelated top-level symbols."""
        diff = (
            "@@ -1,6 +1,0 @@\n"
            "-class OldHelper:\n"
            "-    def setup(self):\n"
            "-        pass\n"
            "-    def teardown(self):\n"
            "-        pass\n"
        )
        result = _extract_deleted_symbols_from_diff(diff_content=diff)
        # Both the class and its members are extracted as independent symbols.
        # "setup" and "teardown" could collide with unrelated top-level fixtures,
        # causing broader test selection — acceptable over-reporting for safety.
        assert result == {"OldHelper", "setup", "teardown"}

    def test_paren_in_string_keeps_following_deleted_def(self) -> None:
        """A paren inside a string literal must not swallow the next deleted def."""
        diff = '@@ -1,4 +1,0 @@\n-def first(label="("):\n-    return label\n-def removed_helper():\n-    return None\n'
        result = _extract_deleted_symbols_from_diff(diff_content=diff)
        assert result == {"first", "removed_helper"}, (
            f"every deleted def is detected on its own line; removed_helper must not be lost: {result}"
        )


class TestIterDiffStatements:
    """Tests for the statement grouping used for import attribution."""

    def test_balanced_multiline_import_is_one_statement(self) -> None:
        """A parenthesized multi-line import stays grouped as a single statement."""
        diff = "@@ -1,3 +1,0 @@\n-from utilities.ssp import (\n-    guest_agent_version_parser,\n-)\n"
        statements = [statement for sign, statement, _ in _iter_diff_statements(diff_content=diff) if sign]
        assert statements == ["from utilities.ssp import (\n    guest_agent_version_parser,\n)"], (
            f"a balanced multiline import must be attributed as one statement: {statements}"
        )


class TestPureDeletionSymbolNarrowing:
    """Tests that pure-deletion diffs enable symbol-level narrowing."""

    def test_pure_deletion_returns_classification_not_none(self, tmp_path: Path) -> None:
        """When a diff only deletes a function, returns SymbolClassification with the deleted symbol."""
        source = textwrap.dedent("""\
            import pytest

            def remaining_func():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that only deletes a function (no additions)
        diff_content = "@@ -3,4 +3,0 @@\n-def deleted_func():\n-    if True:\n-        pytest.skip()\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "Should return SymbolClassification, not None (was the old bug)"
        assert result.modified_symbols == {"deleted_func"}
        assert result.new_symbols == set()

    def test_pure_deletion_no_symbols_returns_empty_classification(self, tmp_path: Path) -> None:
        """A diff that deletes only non-symbol lines attributes no symbol."""
        source = textwrap.dedent("""\
            import os

            def my_func():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that deletes only a comment/blank line (no function/class defs)
        diff_content = "@@ -1,2 +1,1 @@\n-# old comment\n"
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, "Should return SymbolClassification, not None"
        assert result.modified_symbols == set(), "a deleted comment attributes no symbol"
        assert result.has_unattributed_changes is True, (
            "a deletion the diff cannot attribute must force the conservative fallback"
        )


class TestTypeCheckingLineSafety:
    """Tests that if TYPE_CHECKING: lines are treated as safe unmapped lines."""

    def test_type_checking_guard_is_safe(self, tmp_path: Path) -> None:
        """if TYPE_CHECKING: line should NOT cause conservative fallback."""
        source = textwrap.dedent("""\
            from __future__ import annotations

            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                from some_module import SomeType

            CONSTANT = 42

            def my_func():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        # Diff that adds TYPE_CHECKING guard (lines 3-6 are additions)
        diff_content = (
            "@@ -1,2 +1,7 @@\n"
            " from __future__ import annotations\n"
            " \n"
            "+from typing import TYPE_CHECKING\n"
            "+\n"
            "+if TYPE_CHECKING:\n"
            "+    from some_module import SomeType\n"
            "+\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, (
            "Should return SymbolClassification, not None \u2014 if TYPE_CHECKING: should be treated as safe"
        )
        assert result.has_unattributed_changes is True

    def test_typing_type_checking_guard_is_safe(self, tmp_path: Path) -> None:
        """if typing.TYPE_CHECKING: line should NOT cause conservative fallback."""
        source = textwrap.dedent("""\
            import typing

            if typing.TYPE_CHECKING:
                from some_module import SomeType

            def my_func():
                pass
        """)
        file_path = tmp_path / "module.py"
        file_path.write_text(source)

        diff_content = (
            "@@ -1,1 +1,5 @@\n+import typing\n+\n+if typing.TYPE_CHECKING:\n+    from some_module import SomeType\n+\n"
        )
        mock_result = type("Result", (), {"returncode": 0, "stdout": diff_content, "stderr": ""})()
        with patch(
            "scripts.tests_analyzer.pytest_marker_analyzer.subprocess.run",
            return_value=mock_result,
        ):
            result = _extract_modified_symbols(
                file_path=file_path,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )

        assert result is not None, (
            "Should return SymbolClassification, not None \u2014 if typing.TYPE_CHECKING: should be treated as safe"
        )
        assert result.has_unattributed_changes is True


class TestDecoratorLineRange:
    """Tests that decorator lines are included in symbol line ranges."""

    def test_function_with_decorators_includes_decorator_lines(self) -> None:
        """Decorator lines are included in the function's line range."""
        source = "@pytest.mark.smoke\n@pytest.mark.s390x\ndef test_something():\n    pass\n"
        symbol_map = _build_line_to_symbol_map(source=source)
        # Decorator at line 1 should be included in the range
        assert symbol_map.top_level[0] == (1, 4, "test_something"), (
            "Function range should start at first decorator line"
        )

    def test_class_with_decorators_includes_decorator_lines(self) -> None:
        """Decorator lines are included in the class's line range."""
        source = "@pytest.mark.some_marker('FAKE-1234')\nclass TestFoo:\n    def test_bar(self):\n        pass\n"
        symbol_map = _build_line_to_symbol_map(source=source)
        assert symbol_map.top_level[0] == (1, 4, "TestFoo"), "Class range should start at first decorator line"

    def test_function_without_decorators_unchanged(self) -> None:
        """Functions without decorators start at def keyword."""
        source = "def plain_function():\n    return 1\n"
        symbol_map = _build_line_to_symbol_map(source=source)
        assert symbol_map.top_level[0] == (1, 2, "plain_function"), (
            "Function without decorators should start at def line"
        )

    def test_class_member_with_decorator_includes_decorator_lines(self) -> None:
        """Class member decorator lines are included in member line range."""
        source = "class Foo:\n    @pytest.fixture\n    def my_fixture(self):\n        return 1\n"
        symbol_map = _build_line_to_symbol_map(source=source)
        members = symbol_map.class_members["Foo"].members
        assert members["my_fixture"] == (2, 4), "Member range should start at decorator line"

    def test_decorator_change_maps_to_function(self, tmp_path: Path) -> None:
        """Decorator-only diff change maps to the decorated function."""
        source = (
            "import pytest\n"
            "\n"
            "@pytest.mark.smoke\n"
            "@pytest.mark.s390x\n"
            "def test_something():\n"
            "    pass\n"
            "\n"
            "def test_other():\n"
            "    pass\n"
        )
        diff = (
            "--- a/tests/example/test_file.py\n"
            "+++ b/tests/example/test_file.py\n"
            "@@ -3,6 +3,7 @@\n"
            " @pytest.mark.smoke\n"
            "+@pytest.mark.s390x\n"
            " def test_something():\n"
            "     pass\n"
        )
        source_file = tmp_path / "tests" / "example" / "test_file.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text(source)

        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._get_diff_content",
                return_value=diff,
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._fetch_file_at_ref",
                return_value=source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=source_file,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )
        assert result is not None, "Should return SymbolClassification, not None"
        assert "test_something" in result.modified_symbols, "Decorator change should map to test_something"
        assert "test_other" not in result.modified_symbols, "Unmodified function should not be in modified symbols"


class TestImportContinuationSafety:
    """Tests that multi-line import continuation lines are treated as safe."""

    def test_import_continuation_line_is_safe(self, tmp_path: Path) -> None:
        """Import continuation lines do not trigger conservative fallback."""
        source = (
            "from utilities.constants.timeouts import (\n"
            "    TIMEOUT_1MIN,\n"
            "    TIMEOUT_2MIN,\n"
            ")\n"
            "\n"
            "def existing_func():\n"
            "    pass\n"
        )
        diff = (
            "--- a/utilities/example.py\n"
            "+++ b/utilities/example.py\n"
            "@@ -1,3 +1,4 @@\n"
            " from utilities.constants.timeouts import (\n"
            "     TIMEOUT_1MIN,\n"
            "+    TIMEOUT_2MIN,\n"
            " )\n"
        )
        source_file = tmp_path / "utilities" / "example.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text(source)

        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._get_diff_content",
                return_value=diff,
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._fetch_file_at_ref",
                return_value=source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=source_file,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )
        assert result is not None, "Import continuation should not trigger file-level fallback"
        assert result.has_unattributed_changes is True
        assert result.modified_symbols == set()

    def test_import_continuation_with_alias(self, tmp_path: Path) -> None:
        """Import continuation with 'as' alias is treated as safe."""
        source = "from collections.abc import (\n    Generator,\n    Collection as Col,\n)\n\ndef func():\n    pass\n"
        diff = (
            "--- a/utilities/example.py\n"
            "+++ b/utilities/example.py\n"
            "@@ -1,3 +1,4 @@\n"
            " from collections.abc import (\n"
            "     Generator,\n"
            "+    Collection as Col,\n"
            " )\n"
        )
        source_file = tmp_path / "utilities" / "example.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text(source)

        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._get_diff_content",
                return_value=diff,
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._fetch_file_at_ref",
                return_value=source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=source_file,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )
        assert result is not None, "Import continuation with alias should not trigger fallback"

    def test_closing_paren_is_safe(self, tmp_path: Path) -> None:
        """Closing parenthesis of multi-line import is treated as safe."""
        source = "from os.path import (\n    join,\n)\n\ndef func():\n    pass\n"
        diff = "--- a/utils.py\n+++ b/utils.py\n@@ -1,2 +1,3 @@\n from os.path import (\n+    join,\n )\n"
        source_file = tmp_path / "utils.py"
        source_file.write_text(source)

        with (
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._get_diff_content",
                return_value=diff,
            ),
            patch(
                "scripts.tests_analyzer.pytest_marker_analyzer._fetch_file_at_ref",
                return_value=source,
            ),
        ):
            result = _extract_modified_symbols(
                file_path=source_file,
                base_branch="main",
                repo_root=tmp_path,
                github_pr_info=None,
            )
        assert result is not None, "Closing paren should not trigger file-level fallback"


class TestParseDiffForFunctionsContextReset:
    """Tests that _parse_diff_for_functions resets context on new function definitions."""

    def test_appended_function_not_attributed_to_context(self) -> None:
        """New function appended after context function is attributed correctly."""
        diff = (
            "@@ -50,6 +50,15 @@ def existing_fixture():\n"
            "     return dv\n"
            " \n"
            " \n"
            "+def new_fixture():\n"
            '+    """Brand new fixture."""\n'
            "+    return something\n"
        )
        result = _parse_diff_for_functions(diff_content=diff)
        assert "new_fixture" in result, "Appended function should be in modified set"
        assert "existing_fixture" not in result, (
            "Context function should NOT be in modified set when only new code is appended after it"
        )

    def test_modified_context_function_still_detected(self) -> None:
        """When both the context function and an appended function are modified."""
        diff = (
            "@@ -50,6 +50,15 @@ def existing_fixture():\n"
            "-    return old_dv\n"
            "+    return new_dv\n"
            " \n"
            " \n"
            "+def new_fixture():\n"
            "+    return something\n"
        )
        result = _parse_diff_for_functions(diff_content=diff)
        assert "existing_fixture" in result, "Modified context function should be detected"
        assert "new_fixture" in result, "Appended function should also be detected"

    def test_deleted_function_attributed_correctly(self) -> None:
        """Deleted function definition is attributed to the deleted function, not context."""
        diff = (
            "@@ -50,10 +50,3 @@ def existing_fixture():\n"
            "     return dv\n"
            " \n"
            " \n"
            "-def old_fixture():\n"
            '-    """Old fixture to remove."""\n'
            "-    return old_thing\n"
        )
        result = _parse_diff_for_functions(diff_content=diff)
        assert "old_fixture" in result, "Deleted function should be in modified set"
        assert "existing_fixture" not in result, (
            "Context function should NOT be in modified set when only a subsequent function is deleted"
        )

    def test_async_function_appended(self) -> None:
        """Async function appended after context is attributed correctly."""
        diff = (
            "@@ -10,3 +10,8 @@ def sync_func():\n     pass\n \n+async def new_async_func():\n+    await something()\n"
        )
        result = _parse_diff_for_functions(diff_content=diff)
        assert "new_async_func" in result, "Appended async function should be in modified set"
        assert "sync_func" not in result, (
            "Context function should NOT be in modified set when only async function is appended after it"
        )

    def test_decorator_before_appended_function(self) -> None:
        """Decorator before appended function is not attributed to context function."""
        diff = (
            "@@ -50,6 +50,16 @@ def existing_fixture():\n"
            "     return dv\n"
            " \n"
            '+@pytest.fixture(scope="session")\n'
            "+def new_fixture():\n"
            "+    return something\n"
        )
        result = _parse_diff_for_functions(diff_content=diff)
        assert "new_fixture" in result, "Appended function with decorator should be in modified set"
        assert "existing_fixture" not in result, (
            "Context function should NOT be in modified set when decorator belongs to appended function"
        )

    def test_parse_diff_decorator_bound_to_context_def(self) -> None:
        """Decorator-only diff followed by context def line binds to that function."""
        diff = "@@ -10,6 +10,7 @@ def other_func\n+@pytest.mark.tier3\n def existing_fixture():\n     pass\n"
        result = _parse_diff_for_functions(diff_content=diff)
        assert result == {"existing_fixture"}, f"Decorator change should bind only to context def line, got {result}"


class TestPytestPluginsDetection:
    """Tests that pytest_plugins changes are detected by symbol-level analysis."""

    def test_pytest_plugins_in_symbol_map(self) -> None:
        """pytest_plugins assignment is tracked as a top-level symbol."""
        source = textwrap.dedent("""\
            import logging
            import pytest

            pytest_plugins = [
                "tests.fixtures.network.l2_bridge",
                "tests.fixtures.network.cluster",
            ]

            LOGGER = logging.getLogger(__name__)
        """)
        symbol_map = _build_line_to_symbol_map(source=source)
        symbol_names = {name for _, _, name in symbol_map.top_level}
        assert "pytest_plugins" in symbol_names, "pytest_plugins assignment should be tracked as a top-level symbol"
