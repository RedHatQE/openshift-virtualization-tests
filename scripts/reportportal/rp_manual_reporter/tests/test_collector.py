# Co-authored-by: Claude <noreply@anthropic.com>
"""Tests for scripts.reportportal.rp_manual_reporter.collector module.

RFE: https://github.com/RedHatQE/openshift-virtualization-tests/pull/5207
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.reportportal.rp_manual_reporter.collector import (
    PlaceholderTestDetail,
    _extract_docstring,
    _extract_markers,
    _extract_module_markers,
    _extract_polarion_id,
    _extract_usefixtures,
    _matches_keyword_filter,
    _matches_marker_filter,
    _safe_eval_bool_expr,
    collect_placeholder_details,
    node_id_to_rp_name,
)
from scripts.reportportal.rp_manual_reporter.rp_manual_reporter import _build_launch_attributes
from scripts.reportportal.rp_manual_reporter.tests.utils import (
    MockPlaceholderClass,
    MockPlaceholderFile,
    make_detail,
)


class TestNodeIdToRpName:
    def test_node_id_to_rp_name_basic(self) -> None:
        """Verify basic node ID with class and method converts to dotted name."""
        result = node_id_to_rp_name(node_id="tests/foo/test_bar.py::TestClass::test_method")
        assert result == "tests.foo.test_bar.TestClass.test_method"

    def test_node_id_to_rp_name_with_params(self) -> None:
        """Verify parametrize suffix is preserved in conversion."""
        result = node_id_to_rp_name(node_id="tests/foo/test_bar.py::TestClass::test_method[param]")
        assert result == "tests.foo.test_bar.TestClass.test_method[param]"

    def test_node_id_to_rp_name_standalone(self) -> None:
        """Verify standalone function (no class) converts correctly."""
        result = node_id_to_rp_name(node_id="tests/foo/test_bar.py::test_func")
        assert result == "tests.foo.test_bar.test_func"


class TestExtractDocstring:
    def test_extract_docstring(self) -> None:
        """Verify docstring is extracted from a function AST node."""
        source = textwrap.dedent('''\
            def test_example():
                """This is the docstring."""
                pass
        ''')
        tree = ast.parse(source=source)
        func_node = tree.body[0]
        result = _extract_docstring(node=func_node)
        assert result == "This is the docstring."

    def test_extract_docstring_no_docstring(self) -> None:
        """Verify None returned when function has no docstring."""
        source = textwrap.dedent("""\
            def test_example():
                pass
        """)
        tree = ast.parse(source=source)
        func_node = tree.body[0]
        result = _extract_docstring(node=func_node)
        assert result is None


class TestExtractMarkers:
    def test_extract_markers(self) -> None:
        """Verify bare pytest.mark decorators are extracted."""
        source = textwrap.dedent("""\
            import pytest

            @pytest.mark.smoke
            @pytest.mark.tier1
            def test_example():
                pass
        """)
        tree = ast.parse(source=source)
        func_node = tree.body[1]
        result = _extract_markers(decorators=func_node.decorator_list)
        assert result == ["smoke", "tier1"]

    def test_extract_markers_with_args(self) -> None:
        """Verify called markers include their arguments."""
        source = textwrap.dedent("""\
            import pytest

            @pytest.mark.parametrize("x", [1, 2])
            def test_example(x):
                pass
        """)
        tree = ast.parse(source=source)
        func_node = tree.body[1]
        result = _extract_markers(decorators=func_node.decorator_list)
        assert len(result) == 1
        assert result[0].startswith("parametrize(")


class TestExtractUsefixtures:
    def test_extract_usefixtures(self) -> None:
        """Verify fixture names extracted from usefixtures decorator."""
        source = textwrap.dedent("""\
            import pytest

            @pytest.mark.usefixtures("fix1", "fix2")
            class TestExample:
                pass
        """)
        tree = ast.parse(source=source)
        class_node = tree.body[1]
        result = _extract_usefixtures(decorators=class_node.decorator_list)
        assert result == ["fix1", "fix2"]


class TestExtractPolarionId:
    def test_extract_polarion_id(self) -> None:
        """Verify Polarion ID extracted from polarion marker."""
        source = textwrap.dedent("""\
            import pytest

            @pytest.mark.polarion("MOCK-1234")
            def test_example():
                pass
        """)
        tree = ast.parse(source=source)
        func_node = tree.body[1]
        result = _extract_polarion_id(decorators=func_node.decorator_list)
        assert result == "MOCK-1234"

    def test_extract_polarion_id_no_marker(self) -> None:
        """Verify None returned when no polarion marker present."""
        source = textwrap.dedent("""\
            import pytest

            @pytest.mark.smoke
            def test_example():
                pass
        """)
        tree = ast.parse(source=source)
        func_node = tree.body[1]
        result = _extract_polarion_id(decorators=func_node.decorator_list)
        assert result is None


class TestExtractModuleMarkers:
    def test_extract_module_markers(self) -> None:
        """Verify module-level pytestmark list markers are extracted."""
        source = textwrap.dedent("""\
            import pytest

            pytestmark = [pytest.mark.foo, pytest.mark.bar]
        """)
        tree = ast.parse(source=source)
        result = _extract_module_markers(tree=tree)
        assert result == ["foo", "bar"]


class TestCollectPlaceholderDetails:
    def test_collect_placeholder_details(self, tmp_path: Path) -> None:
        """Verify full placeholder detail collection from a temp test file."""
        # Create directory structure matching expected layout
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        sub_dir = tests_dir / "network"
        sub_dir.mkdir()

        test_file = sub_dir / "test_example.py"
        test_file.write_text(
            textwrap.dedent('''\
            """Module docstring for STP link."""

            import pytest

            __test__ = False

            pytestmark = [pytest.mark.tier1]

            class TestMyFeature:
                """Class docstring."""

                @pytest.mark.polarion("MOCK-9999")
                def test_my_case(self):
                    """Test docstring with steps."""
                    pass
        ''')
        )

        mock_placeholder = MockPlaceholderFile(
            file_path="tests/network/test_example.py",
            classes=[
                MockPlaceholderClass(
                    name="TestMyFeature",
                    test_methods=["test_my_case"],
                ),
            ],
        )

        with patch(
            "scripts.reportportal.rp_manual_reporter.collector.scan_placeholder_tests",
            return_value=[mock_placeholder],
        ):
            details = collect_placeholder_details(tests_dir=tests_dir)

        assert len(details) == 1
        detail = details[0]
        assert isinstance(detail, PlaceholderTestDetail)
        assert detail.file_path == "tests/network/test_example.py"
        assert detail.class_name == "TestMyFeature"
        assert detail.method_name == "test_my_case"
        assert detail.module_docstring == "Module docstring for STP link."
        assert detail.class_docstring == "Class docstring."
        assert detail.test_docstring == "Test docstring with steps."
        assert detail.module_markers == ["tier1"]
        assert detail.polarion_id == "MOCK-9999"
        assert detail.node_id == "tests/network/test_example.py::TestMyFeature::test_my_case"
        assert detail.rp_name == "tests.network.test_example.TestMyFeature.test_my_case"


class TestMatchesMarkerFilter:
    def test_simple_marker_match(self) -> None:
        """Verify simple marker name matches."""
        detail = make_detail(test_markers=["gating"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating") is True

    def test_simple_marker_no_match(self) -> None:
        """Verify non-matching marker returns False."""
        detail = make_detail(test_markers=["tier1"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating") is False

    def test_marker_in_module_markers(self) -> None:
        """Verify marker found in module-level markers."""
        detail = make_detail(module_markers=["gating"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating") is True

    def test_marker_in_class_markers(self) -> None:
        """Verify marker found in class-level markers."""
        detail = make_detail(class_markers=["smoke"])
        assert _matches_marker_filter(detail=detail, marker_filter="smoke") is True

    def test_boolean_and_expression(self) -> None:
        """Verify 'and' boolean expression matches when both markers present."""
        detail = make_detail(test_markers=["gating", "tier1"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating and tier1") is True

    def test_boolean_and_expression_partial(self) -> None:
        """Verify 'and' expression fails when only one marker present."""
        detail = make_detail(test_markers=["gating"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating and tier1") is False

    def test_boolean_not_expression(self) -> None:
        """Verify 'not' expression excludes tests with the marker."""
        detail = make_detail(test_markers=["gating"])
        assert _matches_marker_filter(detail=detail, marker_filter="gating and not tier3") is True

    def test_marker_with_args_stripped(self) -> None:
        """Verify markers with args like 'parametrize(...)' are stripped to bare name."""
        detail = make_detail(test_markers=["parametrize('x', [1, 2])"])
        assert _matches_marker_filter(detail=detail, marker_filter="parametrize") is True


class TestMatchesKeywordFilter:
    def test_keyword_match(self) -> None:
        """Verify keyword substring matches node ID."""
        detail = make_detail(node_id="tests/network/test_bridge.py::TestBridge::test_connectivity")
        assert _matches_keyword_filter(detail=detail, keyword_filter="test_connectivity") is True

    def test_keyword_no_match(self) -> None:
        """Verify non-matching keyword returns False."""
        detail = make_detail(node_id="tests/network/test_bridge.py::TestBridge::test_connectivity")
        assert _matches_keyword_filter(detail=detail, keyword_filter="test_migration") is False

    def test_keyword_case_insensitive(self) -> None:
        """Verify keyword matching is case-insensitive."""
        detail = make_detail(node_id="tests/network/test_bridge.py::TestBridge::test_connectivity")
        assert _matches_keyword_filter(detail=detail, keyword_filter="TestBridge") is True

    def test_keyword_partial_match(self) -> None:
        """Verify partial keyword matches."""
        detail = make_detail(node_id="tests/network/test_bridge.py::TestBridge::test_connectivity")
        assert _matches_keyword_filter(detail=detail, keyword_filter="bridge") is True


class TestBuildLaunchAttributeKeys:
    """Verify that _build_launch_attributes emits the correct attribute keys.

    Tests the key naming contract (ARCH not ARCHITECTURE, OCP not OCP_VERSION)
    via _build_launch_attributes which is importable without cluster dependencies.
    """

    def test_explicit_attrs_emit_short_keys(self) -> None:
        """Verify explicit CLI args produce RP-compatible short key names."""
        result = _build_launch_attributes(
            team="NETWORK",
            bundle="v4.22.0",
            cnv_version="4.22",
            arch="amd64",
            ocp_version="4.22.0",
            cluster_name="bm15a",
            cluster_domain="bm15a.example.com",
            storage_class="ocs-storagecluster-ceph-rbd",
            channel="candidate",
        )
        keys = {attr["key"] for attr in result}

        assert "ARCH" in keys
        assert "OCP" in keys
        assert "CNV_XY_VER" in keys
        assert "SC" in keys
        assert "BUNDLE" in keys
        assert "TEAM" in keys
        assert "ARCHITECTURE" not in keys
        assert "OCP_VERSION" not in keys
        assert "CNV_VERSION" not in keys
        assert "STORAGE_CLASS" not in keys


class TestSafeEvalBoolExpr:
    def test_simple_true(self) -> None:
        """Verify simple True expression evaluates correctly."""
        assert _safe_eval_bool_expr(expr="True") is True

    def test_simple_false(self) -> None:
        """Verify simple False expression evaluates correctly."""
        assert _safe_eval_bool_expr(expr="False") is False

    def test_and_expression(self) -> None:
        """Verify and expression evaluates correctly."""
        assert _safe_eval_bool_expr(expr="True and False") is False

    def test_not_expression(self) -> None:
        """Verify not expression evaluates correctly."""
        assert _safe_eval_bool_expr(expr="not False") is True

    def test_complex_expression(self) -> None:
        """Verify complex boolean expression evaluates correctly."""
        assert _safe_eval_bool_expr(expr="True and not False or False") is True

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


class TestBuildLaunchAttributes:
    def test_cnv_version_derived_from_bundle(self) -> None:
        """Verify CNV_XY_VER is auto-derived from BUNDLE when not explicitly set."""
        result = _build_launch_attributes(bundle="v4.22.0.rhel9-102")
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["CNV_XY_VER"] == "4.22"

    def test_bundle_derived_cnv_xy_ver_overrides_explicit_cnv_version(self) -> None:
        """Bundle-derived CNV_XY_VER overrides explicit --cnv-version.

        When both --bundle and --cnv-version are provided, CNV_XY_VER is
        derived from the bundle string because the bundle is the
        authoritative version source.
        """
        result = _build_launch_attributes(
            bundle="v4.22.0",
            cnv_version="4.21",
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["CNV_XY_VER"] == "4.22"

    def test_cluster_cnv_version_kept_without_explicit_bundle(self) -> None:
        """Verify cluster-derived CNV_XY_VER is kept when bundle is not explicit."""
        result = _build_launch_attributes(
            cluster_attrs=[
                {"key": "BUNDLE", "value": "v4.22.0"},
                {"key": "CNV_XY_VER", "value": "4.21"},
            ],
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["CNV_XY_VER"] == "4.21"

    def test_cnv_version_not_derived_without_bundle(self) -> None:
        """Verify CNV_XY_VER is not set when BUNDLE is missing."""
        result = _build_launch_attributes()
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert "CNV_XY_VER" not in attrs_by_key
