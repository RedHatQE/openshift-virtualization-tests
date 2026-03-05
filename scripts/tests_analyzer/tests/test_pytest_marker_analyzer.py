"""
Unit tests for pytest_marker_analyzer hierarchical symbol analysis.

Co-authored-by: Claude <noreply@anthropic.com>
"""

import ast
import textwrap
from pathlib import Path

from scripts.tests_analyzer.pytest_marker_analyzer import (
    AttributeAccessCollector,
    SymbolClassification,
    _build_intra_class_call_graph,
    _build_line_to_symbol_map,
    _collect_test_attribute_accesses,
    _collect_test_function_calls,
    _expand_modified_members_transitively,
    _is_fixture_decorator_standalone,
    _parse_diff_for_functions,
)


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
