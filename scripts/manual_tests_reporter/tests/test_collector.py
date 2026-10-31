# Co-authored-by: Claude <noreply@anthropic.com>
"""Tests for scripts.manual_tests_reporter.collector module.

See scripts/manual_tests_reporter/README.md for the tool this module belongs to.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest
from click import ClickException

from scripts.manual_tests_reporter.collector import (
    ManualTestDetail,
    _extract_docstring,
    _extract_markers,
    _extract_module_markers,
    _extract_polarion_id,
    _extract_usefixtures,
    _has_manual_marker,
    _matches_keyword_filter,
    _matches_marker_filter,
    _safe_arg_repr,
    _safe_eval_bool_expr,
    collect_manual_tests,
)
from scripts.manual_tests_reporter.tests.utils import make_detail


class TestExtractDocstring:
    def test_extract_docstring(self) -> None:
        """Verify docstring is extracted from a function AST node."""
        source = textwrap.dedent(
            text='''\
            def test_example():
                """This is the docstring."""
                pass
        '''
        )
        tree = ast.parse(source=source)
        func_node = tree.body[0]
        result = _extract_docstring(node=func_node)
        assert result == "This is the docstring.", f"Expected 'This is the docstring.', got {result!r}"

    def test_extract_docstring_no_docstring(self) -> None:
        """Verify None returned when function has no docstring."""
        source = textwrap.dedent(
            text="""\
            def test_example():
                pass
        """
        )
        tree = ast.parse(source=source)
        func_node = tree.body[0]
        result = _extract_docstring(node=func_node)
        assert result is None, "Expected: None returned when function has no docstring"


class TestExtractMarkers:
    def test_extract_markers(self) -> None:
        """Verify bare pytest.mark decorators are extracted."""
        source = textwrap.dedent(
            text="""\
            import pytest

            @pytest.mark.smoke
            @pytest.mark.tier1
            def test_example():
                pass
        """
        )
        tree = ast.parse(source=source)
        func_node = tree.body[1]
        assert isinstance(func_node, ast.FunctionDef), "Expected: bare pytest.mark decorators are extracted"
        result = _extract_markers(decorators=func_node.decorator_list)
        assert result == ["smoke", "tier1"], f"Expected ['smoke', 'tier1'], got {result!r}"

    def test_extract_markers_with_args(self) -> None:
        """Verify called markers include their arguments."""
        source = textwrap.dedent(
            text="""\
            import pytest

            @pytest.mark.parametrize("x", [1, 2])
            def test_example(x):
                pass
        """
        )
        tree = ast.parse(source=source)
        func_node = tree.body[1]
        assert isinstance(func_node, ast.FunctionDef), "Expected: called markers include their arguments"
        result = _extract_markers(decorators=func_node.decorator_list)
        assert len(result) == 1, f"Expected 1, got {len(result)!r}"
        assert result[0].startswith("parametrize("), "Expected: called markers include their arguments"


class TestExtractUsefixtures:
    def test_extract_usefixtures(self) -> None:
        """Verify fixture names extracted from usefixtures decorator."""
        source = textwrap.dedent(
            text="""\
            import pytest

            @pytest.mark.usefixtures("fix1", "fix2")
            class TestExample:
                pass
        """
        )
        tree = ast.parse(source=source)
        class_node = tree.body[1]
        assert isinstance(class_node, ast.ClassDef), "Expected: fixture names extracted from usefixtures decorator"
        result = _extract_usefixtures(decorators=class_node.decorator_list)
        assert result == ["fix1", "fix2"], f"Expected ['fix1', 'fix2'], got {result!r}"


class TestExtractPolarionId:
    def test_extract_polarion_id(self) -> None:
        """Verify Polarion ID extracted from polarion marker."""
        source = textwrap.dedent(
            text="""\
            import pytest

            @pytest.mark.polarion("MOCK-1234")
            def test_example():
                pass
        """
        )
        tree = ast.parse(source=source)
        func_node = tree.body[1]
        assert isinstance(func_node, ast.FunctionDef), "Expected: Polarion ID extracted from polarion marker"
        result = _extract_polarion_id(decorators=func_node.decorator_list)
        assert result == "MOCK-1234", f"Expected 'MOCK-1234', got {result!r}"

    def test_extract_polarion_id_no_marker(self) -> None:
        """Verify None returned when no polarion marker present."""
        source = textwrap.dedent(
            text="""\
            import pytest

            @pytest.mark.smoke
            def test_example():
                pass
        """
        )
        tree = ast.parse(source=source)
        func_node = tree.body[1]
        assert isinstance(func_node, ast.FunctionDef), "Expected: None returned when no polarion marker present"
        result = _extract_polarion_id(decorators=func_node.decorator_list)
        assert result is None, "Expected: None returned when no polarion marker present"


class TestExtractModuleMarkers:
    def test_extract_module_markers(self) -> None:
        """Verify module-level pytestmark list markers are extracted."""
        source = textwrap.dedent(
            text="""\
            import pytest

            pytestmark = [pytest.mark.foo, pytest.mark.bar]
        """
        )
        tree = ast.parse(source=source)
        result = _extract_module_markers(tree=tree)
        assert result == ["foo", "bar"], f"Expected ['foo', 'bar'], got {result!r}"


class TestHasManualMarker:
    def test_bare_manual_marker(self) -> None:
        """Verify bare manual marker is detected."""
        assert _has_manual_marker(markers=["smoke", "manual"]), "Expected: bare manual marker is detected"

    def test_marker_with_args_stripped(self) -> None:
        """Verify markers with args are stripped before matching."""
        assert not _has_manual_marker(markers=["parametrize('x', [1, 2])"]), (
            "Expected: markers with args are stripped before matching"
        )

    def test_no_manual_marker(self) -> None:
        """Verify absence of manual marker returns False."""
        assert not _has_manual_marker(markers=["smoke", "tier1"]), "Expected: absence of manual marker returns False"


class TestCollectManualTests:
    def test_collect_test_level_manual_marker(self, tmp_path: Path) -> None:
        """Verify tests with a direct manual decorator are collected."""
        tests_dir = tmp_path / "tests"
        (tests_dir / "network").mkdir(parents=True)
        (tests_dir / "network" / "test_example.py").write_text(
            data=textwrap.dedent(
                text='''\
            """Module docstring for STP link."""

            import pytest

            pytestmark = [pytest.mark.tier1]

            class TestMyFeature:
                """Class docstring."""

                @pytest.mark.manual
                @pytest.mark.polarion("MOCK-9999")
                def test_my_case(self):
                    """Test docstring with steps."""
                    pass

                def test_automated_case(self):
                    assert True
        '''
            )
        )

        details = collect_manual_tests(tests_dir=tests_dir)

        assert len(details) == 1, f"Expected 1, got {len(details)!r}"
        detail = details[0]
        assert isinstance(detail, ManualTestDetail), "Expected: tests with a direct manual decorator are collected"
        assert detail.file_path == "tests/network/test_example.py", (
            f"Expected 'tests/network/test_example.py', got {detail.file_path!r}"
        )
        assert detail.class_name == "TestMyFeature", f"Expected 'TestMyFeature', got {detail.class_name!r}"
        assert detail.method_name == "test_my_case", f"Expected 'test_my_case', got {detail.method_name!r}"
        assert detail.module_docstring == "Module docstring for STP link.", (
            f"Expected 'Module docstring for STP link.', got {detail.module_docstring!r}"
        )
        assert detail.class_docstring == "Class docstring.", (
            f"Expected 'Class docstring.', got {detail.class_docstring!r}"
        )
        assert detail.test_docstring == "Test docstring with steps.", (
            f"Expected 'Test docstring with steps.', got {detail.test_docstring!r}"
        )
        assert detail.module_markers == ["tier1"], f"Expected ['tier1'], got {detail.module_markers!r}"
        assert detail.test_markers == ["manual", "polarion(MOCK-9999)"], (
            f"Expected ['manual', 'polarion(MOCK-9999)'], got {detail.test_markers!r}"
        )
        assert detail.polarion_id == "MOCK-9999", f"Expected 'MOCK-9999', got {detail.polarion_id!r}"
        assert detail.node_id == "tests/network/test_example.py::TestMyFeature::test_my_case", (
            f"Expected 'tests/network/test_example.py::TestMyFeature::test_my_case', got {detail.node_id!r}"
        )

    def test_collect_class_level_manual_marker(self, tmp_path: Path) -> None:
        """Verify all test methods in a manual-marked class are collected."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_class_manual.py").write_text(
            data=textwrap.dedent(
                text="""\
            import pytest

            @pytest.mark.manual
            class TestAllManual:
                def test_one(self):
                    pass

                def test_two(self):
                    pass
        """
            )
        )

        details = collect_manual_tests(tests_dir=tests_dir)
        assert {detail.method_name for detail in details} == {"test_one", "test_two"}, (
            "Expected {'test_two', 'test_one'}"
        )

    def test_collect_module_level_manual_marker(self, tmp_path: Path) -> None:
        """Verify standalone tests are collected when module pytestmark is manual."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_module_manual.py").write_text(
            data=textwrap.dedent(
                text="""\
            import pytest

            pytestmark = pytest.mark.manual

            def test_standalone(self=None):
                pass
        """
            )
        )

        details = collect_manual_tests(tests_dir=tests_dir)
        assert len(details) == 1, f"Expected 1, got {len(details)!r}"
        assert details[0].class_name is None, (
            "Expected: standalone tests are collected when module pytestmark is manual"
        )
        assert details[0].node_id == "tests/test_module_manual.py::test_standalone", (
            f"Expected 'tests/test_module_manual.py::test_standalone', got {details[0].node_id!r}"
        )

    def test_collect_module_pytestmark_applies_to_class_methods(self, tmp_path: Path) -> None:
        """Verify class methods are collected when module pytestmark is manual.

        pytest applies module pytestmark to all tests, including class
        methods; the collector must do the same.
        """
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_module_class_manual.py").write_text(
            data=textwrap.dedent(
                text="""\
            import pytest

            pytestmark = pytest.mark.manual

            class TestModuleManual:
                def test_one(self):
                    pass

                def test_two(self):
                    pass
        """
            )
        )

        details = collect_manual_tests(tests_dir=tests_dir)
        assert {detail.node_id for detail in details} == {
            "tests/test_module_class_manual.py::TestModuleManual::test_one",
            "tests/test_module_class_manual.py::TestModuleManual::test_two",
        }, f"Expected both class methods collected, got {[detail.node_id for detail in details]!r}"

    def test_collect_standalone_manual_function(self, tmp_path: Path) -> None:
        """Verify standalone function with manual decorator is collected."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_standalone.py").write_text(
            data=textwrap.dedent(
                text="""\
            import pytest

            @pytest.mark.manual
            def test_manual_standalone():
                pass
        """
            )
        )

        details = collect_manual_tests(tests_dir=tests_dir)
        assert len(details) == 1, f"Expected 1, got {len(details)!r}"
        assert details[0].node_id == "tests/test_standalone.py::test_manual_standalone", (
            f"Expected 'tests/test_standalone.py::test_manual_standalone', got {details[0].node_id!r}"
        )

    def test_non_manual_tests_excluded(self, tmp_path: Path) -> None:
        """Verify tests without any manual marker are not collected."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_automated.py").write_text(
            data=textwrap.dedent(
                text="""\
            import pytest

            class TestAutomated:
                def test_one(self):
                    assert True
        """
            )
        )

        details = collect_manual_tests(tests_dir=tests_dir)
        assert details == [], f"Expected [], got {details!r}"

    def test_marker_filter(self, tmp_path: Path) -> None:
        """Verify marker filter narrows collected manual tests."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_filtered.py").write_text(
            data=textwrap.dedent(
                text="""\
            import pytest

            class TestFiltered:
                @pytest.mark.manual
                @pytest.mark.gating
                def test_gating_manual(self):
                    pass

                @pytest.mark.manual
                def test_plain_manual(self):
                    pass
        """
            )
        )

        details = collect_manual_tests(tests_dir=tests_dir, marker_filter="gating")
        assert [detail.method_name for detail in details] == ["test_gating_manual"], (
            f"Expected ['test_gating_manual'], got {[detail.method_name for detail in details]!r}"
        )

    def test_keyword_filter(self, tmp_path: Path) -> None:
        """Verify keyword filter narrows collected manual tests."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_keyword.py").write_text(
            data=textwrap.dedent(
                text="""\
            import pytest

            class TestKeyword:
                @pytest.mark.manual
                def test_connectivity(self):
                    pass

                @pytest.mark.manual
                def test_migration(self):
                    pass
        """
            )
        )

        details = collect_manual_tests(tests_dir=tests_dir, keyword_filter="migration")
        assert [detail.method_name for detail in details] == ["test_migration"], (
            f"Expected ['test_migration'], got {[detail.method_name for detail in details]!r}"
        )

    def test_node_ids_stable_when_scanning_subdirectory(self, tmp_path: Path) -> None:
        """Verify node IDs are repo-root-relative regardless of scanned subdirectory."""
        tests_dir = tmp_path / "tests"
        (tests_dir / "network").mkdir(parents=True)
        (tests_dir / "network" / "test_stable.py").write_text(
            data=textwrap.dedent(
                text="""\
            import pytest

            @pytest.mark.manual
            def test_stable_one():
                pass
        """
            )
        )

        from_root = collect_manual_tests(tests_dir=tests_dir)
        from_subdir = collect_manual_tests(tests_dir=tests_dir / "network")

        assert [detail.node_id for detail in from_root] == ["tests/network/test_stable.py::test_stable_one"], (
            f"Expected ['tests/network/test_stable.py::test_stable_one'], got {[detail.node_id for detail in from_root]!r}"
        )
        assert [detail.node_id for detail in from_subdir] == ["tests/network/test_stable.py::test_stable_one"], (
            f"Expected ['tests/network/test_stable.py::test_stable_one'], got {[detail.node_id for detail in from_subdir]!r}"
        )

    def test_unparseable_file_skipped(self, tmp_path: Path) -> None:
        """Verify files with syntax errors are skipped with a warning."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_broken.py").write_text(data="def test_broken(:\n    pass\n")

        details = collect_manual_tests(tests_dir=tests_dir)
        assert details == [], f"Expected [], got {details!r}"

    def test_invalid_marker_expression_with_zero_manual_tests(self, tmp_path: Path) -> None:
        """Verify an invalid marker expression fails even when no manual tests exist.

        Without upfront validation, an invalid ``-m`` expression over a
        directory with no manual tests would silently look like an empty
        selection instead of failing fast.
        """
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_automated.py").write_text(
            data=("import pytest\n\n\nclass TestAutomated:\n    def test_one(self):\n        assert True\n"),
            encoding="utf-8",
        )

        with pytest.raises(ClickException, match="Invalid marker expression"):
            collect_manual_tests(tests_dir=tests_dir, marker_filter="smoke and (")


class TestMatchesMarkerFilter:
    def test_simple_marker_match(self) -> None:
        """Verify simple marker name matches."""
        detail = make_detail(test_markers=["gating"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating"), "Expected: simple marker name matches"

    def test_simple_marker_no_match(self) -> None:
        """Verify non-matching marker returns False."""
        detail = make_detail(test_markers=["tier1"])
        assert not _matches_marker_filter(detail=detail, marker_filter="gating"), (
            "Expected: non-matching marker returns False"
        )

    def test_marker_in_module_markers(self) -> None:
        """Verify marker found in module-level markers."""
        detail = make_detail(module_markers=["gating"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating"), (
            "Expected: marker found in module-level markers"
        )

    def test_marker_in_class_markers(self) -> None:
        """Verify marker found in class-level markers."""
        detail = make_detail(class_markers=["smoke"])
        assert _matches_marker_filter(detail=detail, marker_filter="smoke"), (
            "Expected: marker found in class-level markers"
        )

    def test_boolean_and_expression(self) -> None:
        """Verify 'and' boolean expression matches when both markers present."""
        detail = make_detail(test_markers=["gating", "tier1"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating and tier1"), (
            "Expected: 'and' boolean expression matches when both markers present"
        )

    def test_boolean_and_expression_partial(self) -> None:
        """Verify 'and' expression fails when only one marker present."""
        detail = make_detail(test_markers=["gating"])
        assert not _matches_marker_filter(detail=detail, marker_filter="gating and tier1"), (
            "Expected: 'and' expression fails when only one marker present"
        )

    def test_boolean_not_expression(self) -> None:
        """Verify 'not' expression excludes tests with the marker."""
        detail = make_detail(test_markers=["gating"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating and not tier3"), (
            "Expected: 'not' expression excludes tests with the marker"
        )

    def test_marker_with_args_stripped(self) -> None:
        """Verify markers with args like 'parametrize(...)' are stripped to bare name."""
        detail = make_detail(test_markers=["parametrize('x', [1, 2])"])
        assert _matches_marker_filter(detail=detail, marker_filter="parametrize"), (
            "Expected: markers with args like 'parametrize(...)' are stripped to bare name"
        )

    def test_unparseable_expression_raises(self) -> None:
        """Verify an unparseable marker expression fails fast instead of matching nothing."""
        detail = make_detail(test_markers=["gating"])
        with pytest.raises(ClickException, match="Invalid marker expression"):
            _matches_marker_filter(detail=detail, marker_filter="gating and")

    def test_pathologically_nested_expression_fails_cleanly(self) -> None:
        """Verify a pathologically nested expression fails cleanly, not with a parser crash.

        [NEGATIVE] A parser stack overflow (MemoryError/RecursionError) from a
        hostile ``-m`` expression must surface as the same clean
        ClickException as any other invalid expression.
        """
        detail = make_detail(test_markers=["manual"])
        with pytest.raises(ClickException, match="Invalid marker expression"):
            _matches_marker_filter(detail=detail, marker_filter="not " * 20000 + "manual")


class TestSafeArgRepr:
    def test_complex_node_falls_back_to_ast_dump(self) -> None:
        """Verify nodes literal_eval cannot evaluate fall back to ast.dump."""
        source = textwrap.dedent(
            text="""\
            def test_example(x=flag if True else None):
                pass
        """
        )
        tree = ast.parse(source=source)
        func_node = tree.body[0]
        assert isinstance(func_node, ast.FunctionDef), (
            "Expected: nodes literal_eval cannot evaluate fall back to ast.dump"
        )
        default = func_node.args.defaults[0]
        result = _safe_arg_repr(arg=default)
        assert "IfExp" in result, f"Expected ast.dump fallback output, got {result!r}"


class TestMatchesKeywordFilter:
    def test_keyword_match(self) -> None:
        """Verify keyword substring matches node ID."""
        detail = make_detail(node_id="tests/network/test_bridge.py::TestBridge::test_connectivity")
        assert _matches_keyword_filter(detail=detail, keyword_filter="test_connectivity"), (
            "Expected: keyword substring matches node ID"
        )

    def test_keyword_no_match(self) -> None:
        """Verify non-matching keyword returns False."""
        detail = make_detail(node_id="tests/network/test_bridge.py::TestBridge::test_connectivity")
        assert not _matches_keyword_filter(detail=detail, keyword_filter="test_migration"), (
            "Expected: non-matching keyword returns False"
        )

    def test_keyword_case_insensitive(self) -> None:
        """Verify keyword matching is case-insensitive."""
        detail = make_detail(node_id="tests/network/test_bridge.py::TestBridge::test_connectivity")
        assert _matches_keyword_filter(detail=detail, keyword_filter="TestBridge"), (
            "Expected: keyword matching is case-insensitive"
        )

    def test_keyword_partial_match(self) -> None:
        """Verify partial keyword matches."""
        detail = make_detail(node_id="tests/network/test_bridge.py::TestBridge::test_connectivity")
        assert _matches_keyword_filter(detail=detail, keyword_filter="bridge"), "Expected: partial keyword matches"


class TestSafeEvalBoolExpr:
    def test_simple_true(self) -> None:
        """Verify simple True expression evaluates correctly."""
        assert _safe_eval_bool_expr(expr="True"), "Expected: simple True expression evaluates correctly"

    def test_simple_false(self) -> None:
        """Verify simple False expression evaluates correctly."""
        assert not _safe_eval_bool_expr(expr="False"), "Expected: simple False expression evaluates correctly"

    def test_and_expression(self) -> None:
        """Verify and expression evaluates correctly."""
        assert not _safe_eval_bool_expr(expr="True and False"), "Expected: and expression evaluates correctly"

    def test_not_expression(self) -> None:
        """Verify not expression evaluates correctly."""
        assert _safe_eval_bool_expr(expr="not False"), "Expected: not expression evaluates correctly"

    def test_complex_expression(self) -> None:
        """Verify complex boolean expression evaluates correctly."""
        assert _safe_eval_bool_expr(expr="True and not False or False"), (
            "Expected: complex boolean expression evaluates correctly"
        )

    def test_rejects_function_call(self) -> None:
        """Verify function calls are rejected."""
        with pytest.raises(TypeError, match="Disallowed AST node"):
            _safe_eval_bool_expr(expr="__import__('os')")

    def test_rejects_attribute_access(self) -> None:
        """Verify attribute access is rejected."""
        with pytest.raises(TypeError, match="Disallowed AST node"):
            _safe_eval_bool_expr(expr="True.__class__")

    def test_rejects_string_constant(self) -> None:
        """Verify non-boolean constants are rejected."""
        with pytest.raises(TypeError, match="Disallowed constant"):
            _safe_eval_bool_expr(expr="'injection'")

    def test_rejects_numeric_constant(self) -> None:
        """Verify numeric constants are rejected."""
        with pytest.raises(TypeError, match="Disallowed constant"):
            _safe_eval_bool_expr(expr="42")
