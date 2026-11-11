"""Unit tests for the pre-commit policy checks."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from pyhelper_utils.shell import run_command
from pytest import MonkeyPatch, fail, mark

from scripts.pre_commit_hooks import check_policy
from scripts.pre_commit_hooks.check_policy import (
    _added_lines_by_path,
    _diff_header_path,
    _git_header_token,
    _git_quoted_token,
    _git_unquote,
    _parse_staged_entries,
    _parse_staged_status,
    _staged_changes,
    check_file,
    check_python_source,
    check_site_path,
    check_top_level_test_path,
    main,
)
from scripts.pre_commit_hooks.policy_types import PolicyViolation
from scripts.pre_commit_hooks.tests.policy_assertions import _violation_signatures


def test_policy_violation_is_reexported_from_check_policy() -> None:
    """The shared PolicyViolation type remains available through check_policy."""
    assert check_policy.PolicyViolation is PolicyViolation, "check_policy should re-export the shared violation type"


def test_check_site_path_rejects_generated_documentation() -> None:
    """Changes below docs/site/ are rejected."""
    violation = check_site_path(file_path=Path("docs/site/index.html"))

    assert violation is not None, "generated documentation path should be rejected"
    assert "generated" in violation.message, "violation should identify generated documentation"


def test_check_site_path_allows_source_documentation() -> None:
    """Source documentation outside docs/site/ is allowed."""
    assert check_site_path(file_path=Path("docs/code-quality.md")) is None, (
        "source documentation path should be allowed"
    )


def test_check_top_level_test_path_rejects_test_module() -> None:
    """A pytest module directly under tests/ is rejected."""
    violation = check_top_level_test_path(file_path=Path("tests/test_policy.py"))

    assert violation is not None, "top-level test module should be rejected"
    assert "feature subdirectory" in violation.message, "violation should require a feature subdirectory"


def test_check_top_level_test_path_rejects_pytest_suffix() -> None:
    """A pytest module using the alternate suffix directly under tests/ is rejected."""
    violation = check_top_level_test_path(file_path=Path("tests/policy_test.py"))

    assert violation is not None, "top-level pytest-suffix module should be rejected"


def test_check_top_level_test_path_allows_feature_test() -> None:
    """A test module below a feature directory is allowed."""
    assert check_top_level_test_path(file_path=Path("tests/network/test_policy.py")) is None, (
        "feature test module should be allowed"
    )


def test_check_top_level_test_path_allows_top_level_helper() -> None:
    """A non-test helper directly under tests/ is allowed."""
    assert check_top_level_test_path(file_path=Path("tests/utils.py")) is None, (
        "top-level helper module should be allowed"
    )


def test_check_python_source_rejects_dynamic_client_construction() -> None:
    """Direct DynamicClient construction is rejected."""
    violations = check_python_source(
        file_path=Path("example.py"),
        source="client = DynamicClient(api_client)",
    )

    assert _violation_signatures(violations) == [
        (1, "reuse the DynamicClient passed through the call path instead of constructing one")
    ], "direct DynamicClient should report its exact line and message"


def test_check_python_source_rejects_qualified_dynamic_client_construction() -> None:
    """Qualified direct DynamicClient construction is rejected."""
    violations = check_python_source(
        file_path=Path("example.py"),
        source="client = kubernetes.dynamic.DynamicClient(api_client)",
    )

    assert _violation_signatures(violations) == [
        (1, "reuse the DynamicClient passed through the call path instead of constructing one")
    ], "qualified DynamicClient should report its exact line and message"


def test_check_python_source_rejects_dynamic_client_import_aliases() -> None:
    """Imported DynamicClient aliases are rejected."""
    source = dedent(
        """
        from kubernetes.dynamic import DynamicClient as DC
        import kubernetes.dynamic as kd
        direct_alias = DC(api_client)
        module_alias = kd.DynamicClient(api_client)
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (4, "reuse the DynamicClient passed through the call path instead of constructing one"),
        (5, "reuse the DynamicClient passed through the call path instead of constructing one"),
    ], "DynamicClient aliases should report exact call locations and messages"


def test_check_python_source_rejects_assignment_alias_calls() -> None:
    """Assignment aliases resolve for DynamicClient and pytest.skip calls."""
    source = dedent(
        """
        from kubernetes.dynamic import DynamicClient as DC
        dynamic_alias = DC
        dynamic_alias(api_client)

        import pytest
        pytest_alias = pytest
        skip_alias = pytest_alias.skip
        skip_alias(reason="not applicable")
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (4, "reuse the DynamicClient passed through the call path instead of constructing one"),
        (9, "pytest.skip() is forbidden"),
    ], "assignment aliases should report exact call locations and messages"


def test_check_python_source_rejects_assignment_alias_markers() -> None:
    """Assignment aliases resolve for skip decorators and pytestmark values."""
    source = dedent(
        """
        import pytest
        pytest_alias = pytest
        mark_alias = pytest_alias.mark
        decorator_alias = mark_alias.skip

        @decorator_alias
        def skipped_test():
            pass

        pytestmark = decorator_alias
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (7, "pytest.mark.skip and pytest.mark.skipif are forbidden"),
        (11, "module-level pytestmark skip markers are forbidden"),
    ], "assignment marker aliases should report exact locations and messages"


def test_check_python_source_rejects_wrapped_binding_skip_decorators() -> None:
    """A skip marker hidden behind a wrapping call is still rejected on decorators."""
    source = dedent(
        """
        import pytest

        def wrap(marker):
            return marker

        value = wrap(pytest.mark.skip)

        @value
        def skipped_test():
            pass
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(9, "pytest.mark.skip and pytest.mark.skipif are forbidden")], (
        "wrapped marker bindings should still resolve on decorators"
    )


def test_check_python_source_terminates_on_binding_cycles() -> None:
    """Cyclic binding aliases must not hang or misreport the skip-marker checks."""
    source = dedent(
        """
        a = b
        b = a

        @a
        def skipped_test():
            pass
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert violations == [], "cyclic bindings must terminate without reporting skip markers"


def test_check_python_source_keeps_nested_imports_in_their_scope() -> None:
    """A nested import cannot overwrite a module alias or leak after its function."""
    source = dedent(
        """
        import pytest as pt

        def helper():
            import unrelated as pt
            pt.skip()

        pt.skip()
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(8, "pytest.skip() is forbidden")], (
        "nested imports should affect only their own scope"
    )


def test_check_python_source_resolves_function_local_aliases() -> None:
    """Function-local assignments resolve aliases without changing module bindings."""
    source = dedent(
        """
        import pytest

        def helper():
            local_skip = pytest.skip
            local_skip(reason="local")
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(6, "pytest.skip() is forbidden")], (
        "function-local aliases should report their exact call"
    )


def test_check_python_source_methods_skip_class_shadowing() -> None:
    """Method aliases resolve module names instead of class attributes."""
    source = dedent(
        """
        import pytest

        class Wrapper:
            pytest = unrelated

            def helper(self):
                pytest.skip(reason="method")
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(8, "pytest.skip() is forbidden")], (
        "class attributes should not shadow module names in methods"
    )


def test_check_python_source_resolves_class_aliases_in_method_annotations() -> None:
    """Method annotations use class aliases while method bodies do not."""
    source = dedent(
        """
        import pytest

        class Wrapper:
            skip = pytest.skip

            def helper(self, value: skip()):
                skip(reason="method")
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(7, "pytest.skip() is forbidden")], (
        "class aliases should apply to annotations but not method bodies"
    )


def test_check_python_source_does_not_leak_class_imports_into_methods() -> None:
    """Imports in a class body are not method-local aliases."""
    source = dedent(
        """
        class Wrapper:
            from pytest import skip

            def helper(self):
                skip(reason="method")
        """
    )

    assert check_python_source(file_path=Path("example.py"), source=source) == [], (
        "class imports should not create method aliases"
    )


def test_check_python_source_resolves_global_aliases_in_source_order() -> None:
    """Global alias assignments affect later references, not earlier ones."""
    source = dedent(
        """
        import pytest
        skip_alias(reason="before")

        def configure():
            global skip_alias
            skip_alias = pytest.skip

        skip_alias(reason="after")
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(9, "pytest.skip() is forbidden")], (
        "global aliases should resolve in source order"
    )


def test_check_python_source_resolves_nonlocal_aliases() -> None:
    """Nonlocal alias assignments update the enclosing function scope."""
    source = dedent(
        """
        import pytest

        def outer():
            skip_alias = unrelated

            def configure():
                nonlocal skip_alias
                skip_alias = pytest.skip

            configure()
            skip_alias(reason="after")
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(12, "pytest.skip() is forbidden")], (
        "nonlocal aliases should resolve in the enclosing function scope"
    )


def test_check_python_source_honors_nested_shadowing() -> None:
    """A local assignment shadows the module alias only inside its function."""
    source = dedent(
        """
        import pytest as pt

        def helper():
            pt = unrelated
            pt.skip()

        pt.skip()
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(8, "pytest.skip() is forbidden")], (
        "nested shadowing should preserve only the module-level violation"
    )


def test_check_python_source_resolves_chained_aliases_and_stops_cycles() -> None:
    """Chained aliases resolve while cyclic aliases terminate without a false positive."""
    source = dedent(
        """
        from kubernetes.dynamic import DynamicClient as imported_client
        first_alias = imported_client
        second_alias = first_alias
        second_alias(api_client)

        cycle_one = cycle_two
        cycle_two = cycle_one
        cycle_one(api_client)
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (5, "reuse the DynamicClient passed through the call path instead of constructing one"),
    ], "chained aliases should report the exact forbidden call"


def test_check_python_source_preserves_forbidden_binding_through_alias_cycle() -> None:
    """A later cyclic reassignment cannot erase an earlier forbidden binding."""
    source = dedent(
        """
        import pytest
        skip = pytest.skip
        cycle = skip
        skip = cycle
        skip()
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(6, "pytest.skip() is forbidden")], (
        "cyclic reassignment should preserve the exact forbidden skip binding"
    )

    staged_violations = check_python_source(file_path=Path("example.py"), source=source, added_lines={4})
    assert _violation_signatures(staged_violations) == [(6, "pytest.skip() is forbidden")], (
        "added cyclic dependency should activate the exact unchanged forbidden call"
    )


def test_check_python_source_activates_unchanged_nodes_from_added_import() -> None:
    """An added import activates unchanged aliased calls and decorators."""
    source = dedent(
        """
        import pytest as pt
        skip_alias = pt.skip
        decorator_alias = pt.mark.skip

        skip_alias(reason="legacy")

        @decorator_alias
        def skipped_test():
            pass
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source, added_lines={2})

    assert _violation_signatures(violations) == [
        (6, "pytest.skip() is forbidden"),
        (8, "pytest.mark.skip and pytest.mark.skipif are forbidden"),
    ], "added imports should activate exact unchanged calls and decorators"


def test_check_python_source_activates_unchanged_nodes_from_added_aliases() -> None:
    """Added aliases activate unchanged calls and decorators."""
    source = dedent(
        """
        import pytest as pt
        skip_alias = pt.skip
        decorator_alias = pt.mark.skip

        skip_alias(reason="legacy")

        @decorator_alias
        def skipped_test():
            pass
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source, added_lines={3, 4})

    assert _violation_signatures(violations) == [
        (6, "pytest.skip() is forbidden"),
        (8, "pytest.mark.skip and pytest.mark.skipif are forbidden"),
    ], "added aliases should activate exact unchanged calls and decorators"


def test_check_python_source_activates_multiline_call_from_added_dependency() -> None:
    """An added import activates an unchanged multiline call."""
    source = dedent(
        """
        import pytest as pt
        skip_alias = pt.skip

        skip_alias(
            reason="legacy",
        )
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source, added_lines={2})

    assert _violation_signatures(violations) == [(5, "pytest.skip() is forbidden")], (
        "added import should report the exact unchanged multiline call"
    )


def test_check_python_source_activates_multiline_decorator_from_added_dependency() -> None:
    """An added import activates an unchanged multiline decorator."""
    source = dedent(
        """
        import pytest as pt

        @pt.mark.skipif(
            condition=True,
        )
        def skipped_test():
            pass
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source, added_lines={2})

    assert _violation_signatures(violations) == [(4, "pytest.mark.skip and pytest.mark.skipif are forbidden")], (
        "added import should report the exact unchanged multiline decorator"
    )


def test_check_python_source_activates_unchanged_resource_calls_from_added_import() -> None:
    """An added Resource import activates unchanged constructor and class-get calls."""
    source = dedent(
        """
        from ocp_resources.resource import Resource

        Resource()
        Resource.get()
        """
    )

    violations = check_python_source(
        file_path=Path("example.py"),
        source=source,
        added_lines={2},
        resource_classes={("ocp_resources", "resource", "Resource")},
    )

    assert _violation_signatures(violations) == [
        (4, "resource-clients: pass an existing non-None client= to this Resource constructor"),
        (5, "resource-clients: pass an existing non-None client= to this Resource class .get()"),
    ], "a changed Resource import should activate both unchanged Resource client checks"


def test_check_python_source_ignores_unchanged_local_cache_alias_after_unrelated_addition() -> None:
    """An unrelated added line must not re-report an unchanged local cache-admin call."""
    head_source = dedent(
        """
        from utilities.cluster import cache_admin_client

        def helper():
            local_cache = cache_admin_client
            local_cache()
        """
    )
    source = dedent(
        """
        from utilities.cluster import cache_admin_client

        def helper():
            local_cache = cache_admin_client
            unrelated = True
            local_cache()
        """
    )

    violations = check_python_source(
        file_path=Path("example.py"),
        source=source,
        added_lines={5},
        head_source=head_source,
    )

    assert violations == [], "an unrelated added line must not activate an unchanged local cache-admin call"


def test_check_python_source_allows_unrelated_qualified_dynamic_client() -> None:
    """A same-named client from another library is allowed."""
    violations = check_python_source(
        file_path=Path("example.py"),
        source="client = mylib.DynamicClient(api_client)",
    )

    assert violations == [], "unrelated DynamicClient APIs should be allowed"


def test_check_python_source_detects_multiline_dynamic_client_on_added_line() -> None:
    """A multiline DynamicClient call is found when a continuation line is added."""
    source = dedent(
        text="""
        client = DynamicClient(
            api_client,
        )
        """
    )

    violations = check_python_source(
        file_path=Path("example.py"),
        source=source,
        added_lines={3},
    )

    assert _violation_signatures(violations) == [
        (2, "reuse the DynamicClient passed through the call path instead of constructing one")
    ], "multiline DynamicClient should report its exact call"


def test_check_python_source_allows_client_factory() -> None:
    """A factory function whose name contains DynamicClient is allowed."""
    violations = check_python_source(
        file_path=Path("example.py"),
        source="client = get_dynamic_client(api_client)",
    )

    assert violations == [], "approved client factory should produce no violations"


def test_check_python_source_rejects_pytest_skip_call() -> None:
    """A pytest skip call is rejected."""
    violations = check_python_source(
        file_path=Path("example.py"),
        source="pytest.skip(reason='not applicable')",
    )

    assert _violation_signatures(violations) == [(1, "pytest.skip() is forbidden")], (
        "pytest.skip should report its exact line and message"
    )


def test_check_python_source_rejects_aliased_pytest_skip_calls() -> None:
    """Aliased pytest skip calls are rejected."""
    source = dedent(
        """
        import pytest as pt
        from pytest import skip as s
        pt.skip(reason="first")
        s(reason="second")
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (4, "pytest.skip() is forbidden"),
        (5, "pytest.skip() is forbidden"),
    ], "aliased pytest.skip calls should report exact locations and messages"


def test_check_python_source_rejects_aliased_skip_decorators_and_pytestmark() -> None:
    """Aliased skip decorators and module markers are rejected."""
    source = dedent(
        """
        import pytest as pt
        from pytest import mark as m

        @pt.mark.skip
        def skipped_by_module_alias():
            pass

        @m.skipif(condition)
        def skipped_by_import_alias():
            pass

        pytestmark = [pt.mark.skip, m.skipif(condition)]
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (5, "pytest.mark.skip and pytest.mark.skipif are forbidden"),
        (9, "pytest.mark.skip and pytest.mark.skipif are forbidden"),
        (13, "module-level pytestmark skip markers are forbidden"),
    ], "aliased markers should report exact locations and messages"


def test_check_python_source_rejects_skip_decorator() -> None:
    """The pytest skip decorator is rejected."""
    source = """
    @pytest.mark.skip
    def skipped_test():
        pass
    """

    violations = check_python_source(file_path=Path("example.py"), source=dedent(source))

    assert _violation_signatures(violations) == [(2, "pytest.mark.skip and pytest.mark.skipif are forbidden")], (
        "skip decorator should report its exact line and message"
    )


def test_check_python_source_rejects_skipif_decorator() -> None:
    """The pytest skipif decorator is rejected."""
    source = """
    @pytest.mark.skipif(condition)
    def conditionally_skipped_test():
        pass
    """

    violations = check_python_source(file_path=Path("example.py"), source=dedent(source))

    assert _violation_signatures(violations) == [(2, "pytest.mark.skip and pytest.mark.skipif are forbidden")], (
        "skipif decorator should report its exact line and message"
    )


def test_check_python_source_detects_multiline_skip_decorator_on_added_line() -> None:
    """A multiline skip decorator is found when a continuation line is added."""
    source = dedent(
        text="""
        @pytest.mark.skipif(
            condition,
        )
        def conditionally_skipped_test():
            pass
        """
    )

    violations = check_python_source(
        file_path=Path("example.py"),
        source=source,
        added_lines={3},
    )

    assert _violation_signatures(violations) == [(2, "pytest.mark.skip and pytest.mark.skipif are forbidden")], (
        "multiline skip decorator should report its exact line and message"
    )


def test_check_python_source_rejects_module_pytestmark_skipif() -> None:
    """A module-level pytestmark skipif assignment is rejected."""
    source = "pytestmark = pytest.mark.skipif(condition)"

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(1, "module-level pytestmark skip markers are forbidden")], (
        "module pytestmark skip should report its exact line and message"
    )


def test_check_python_source_rejects_module_pytestmark_skip_list_and_tuple() -> None:
    """List and tuple pytestmark assignments cannot contain skip markers."""
    source = dedent(
        """
        pytestmark = [pytest.mark.smoke, pytest.mark.skip]
        other_marks = (pytest.mark.tier1, pytest.mark.skipif(condition))
        pytestmark = (pytest.mark.smoke, pytest.mark.skipif(condition))
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (2, "module-level pytestmark skip markers are forbidden"),
        (4, "module-level pytestmark skip markers are forbidden"),
    ], "pytestmark assignments should report exact lines and messages"


def test_check_python_source_rejects_module_pytestmark_aliases_and_annotations() -> None:
    """Local marker aliases and annotated pytestmark assignments are rejected."""
    source = dedent(
        """
        skip_marker = pytest.mark.skip
        pytestmark: object = skip_marker
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (3, "module-level pytestmark skip markers are forbidden"),
    ], "aliased annotated pytestmark should report its exact location and message"


def test_check_python_source_rejects_conditional_module_pytestmark() -> None:
    """A conditional module marker is rejected when either branch skips."""
    source = "pytestmark = pytest.mark.skip if condition else pytest.mark.smoke"

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(1, "module-level pytestmark skip markers are forbidden")], (
        "conditional pytestmark skip should report its exact line and message"
    )


def test_check_python_source_rejects_nested_module_pytestmark_assignment() -> None:
    """A conditional module assignment is checked, unlike function and class locals."""
    source = dedent(
        """
        if condition:
            pytestmark = pytest.mark.skip

        class Wrapper:
            pytestmark = pytest.mark.skip

        def helper():
            pytestmark = pytest.mark.skip
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(3, "module-level pytestmark skip markers are forbidden")], (
        "conditional module pytestmark should be checked without flagging nested scopes"
    )


def test_check_python_source_skips_class_scope_for_comprehension_body() -> None:
    """Comprehension bodies skip class locals while their first iterable does not."""
    source = dedent(
        """
        import pytest

        class Wrapper:
            pytest = unrelated
            [
                pytest.skip()
                for value in pytest.skip()
            ]
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(7, "pytest.skip() is forbidden")], (
        "comprehension bodies should resolve module names while first iterables use class scope"
    )


def test_check_python_source_checks_pytestmark_dependencies_on_added_lines() -> None:
    """Changing an imported marker dependency is checked with an unchanged pytestmark line."""
    source = dedent(
        """
        import pytest as pt
        pytestmark = pt.mark.skip
        """
    )

    violations = check_python_source(
        file_path=Path("example.py"),
        source=source,
        added_lines={2},
    )

    assert _violation_signatures(violations) == [(3, "module-level pytestmark skip markers are forbidden")], (
        "changed marker dependency should report the exact pytestmark violation"
    )


def test_check_python_source_checks_pytestmark_alias_in_comprehension_filter_on_added_lines() -> None:
    """A changed alias in a comprehension filter activates its pytestmark."""
    source = dedent(
        """
        import pytest
        marker_alias = pytest.mark.skip
        pytestmark = [pytest.mark.smoke for value in values if marker_alias]
        """
    )

    violations = check_python_source(
        file_path=Path("example.py"),
        source=source,
        added_lines={3},
    )

    assert _violation_signatures(violations) == [(4, "module-level pytestmark skip markers are forbidden")], (
        "changed aliases in comprehension filters should activate their pytestmark violation"
    )


def test_check_python_source_only_checks_added_pytestmark_assignment_lines() -> None:
    """An unchanged module-level pytestmark assignment is ignored."""
    source = dedent(
        """
        pytestmark = pytest.mark.skipif(condition)
        value = 1
        """
    )

    assert check_python_source(file_path=Path("example.py"), source=source, added_lines={3}) == [], (
        "unchanged pytestmark should be ignored"
    )
    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source, added_lines={2})) == [
        (2, "module-level pytestmark skip markers are forbidden")
    ], "added pytestmark should report exactly"


def test_check_python_source_allows_local_pytestmark_assignment() -> None:
    """A pytestmark assignment inside a function is not module-level."""
    source = dedent(
        """
        def helper():
            pytestmark = pytest.mark.skipif(condition)
        """
    )

    assert check_python_source(file_path=Path("example.py"), source=source) == [], "local pytestmark should be allowed"


def test_check_python_source_allows_other_pytest_markers() -> None:
    """Non-skip pytest markers are allowed."""
    source = """
    @pytest.mark.parametrize('value', [1])
    def test_value(value):
        assert value == 1, "parametrized value should remain valid"
    """

    assert check_python_source(file_path=Path("example.py"), source=dedent(source)) == [], (
        "non-skip pytest markers should be allowed"
    )


def test_check_file_runs_source_checks(tmp_path: Path) -> None:
    """The file-level check applies Python source policies."""
    file_path = tmp_path / "test_policy.py"
    file_path.write_text(data="pytest.skip(reason='not applicable')", encoding="utf-8")

    violations = check_file(file_path=file_path)

    assert _violation_signatures(violations) == [(1, "pytest.skip() is forbidden")], (
        "file-level pytest.skip should report its exact line and message"
    )


def test_main_all_files_ignores_existing_site_and_skip_violations(monkeypatch) -> None:
    """All-files runs ignore legacy site files and skip calls."""
    monkeypatch.setattr(target=check_policy, name="run_command", value=lambda **kwargs: (True, "", ""))

    assert (
        main(
            arguments=[
                "docs/site/index.html",
                "tests/fixtures/cluster/infrastructure.py",
            ]
        )
        == 0
    ), "all-files check should ignore existing violations"


def test_main_rejects_staged_site_path(monkeypatch) -> None:
    """A staged path below docs/site/ is rejected."""
    monkeypatch.setattr(
        target=check_policy,
        name="run_command",
        value=lambda **kwargs: (
            (True, "M\0docs/site/index.html\0", "") if "--name-status" in kwargs["command"] else (True, "", "")
        ),
    )

    assert main(arguments=["docs/site/index.html"]) == 1, "staged generated-docs path should be rejected"


def test_staged_changes_parses_all_python_hunks_from_one_diff(monkeypatch) -> None:
    """Staged Python line ranges come from one shared Git diff."""
    diff_calls: list[list[str]] = []
    diff = """diff --git a/first.py b/first.py
--- a/first.py
+++ b/first.py
@@ -0,0 +1 @@
+first = 1
diff --git a/second.py b/second.py
--- a/second.py
+++ b/second.py
@@ -0,0 +1 @@
+second = 2
"""

    def mocked_run_command(**kwargs):
        command = kwargs["command"]
        if command[:3] == ["git", "ls-files", "--stage"]:
            return True, "", ""
        if "--name-status" in command:
            return True, "M\0first.py\0M\0second.py\0", ""
        if command[:2] == ["git", "diff"]:
            diff_calls.append(command)
            return True, diff, ""
        if command[:2] == ["git", "show"]:
            return True, "value = 1\n", ""
        fail(f"unexpected command: {command}")

    monkeypatch.setattr(target=check_policy, name="run_command", value=mocked_run_command)

    changes = _staged_changes()

    assert changes.added_lines == {Path("first.py"): frozenset({1}), Path("second.py"): frozenset({1})}, (
        "the shared staged diff must preserve per-file added lines"
    )
    assert len(diff_calls) == 1, "all staged Python paths must be parsed from one Git diff process"


def test_main_checks_only_added_python_lines(monkeypatch, tmp_path: Path) -> None:
    """Legacy violations are ignored while newly added violations are rejected."""
    file_path = tmp_path / "example.py"
    file_path.write_text(
        data="pytest.skip(reason='legacy')\nclient = DynamicClient(api_client)\n",
        encoding="utf-8",
    )
    diff = """diff --git a/example.py b/example.py
index 0000000..1111111 100644
--- a/example.py
+++ b/example.py
@@ -1,0 +2,1 @@
+client = DynamicClient(api_client)
"""

    def run_command(**kwargs):
        command = kwargs["command"]
        if command[:3] == ["git", "ls-files", "--stage"]:
            return True, "", ""
        if "--name-status" in command:
            return True, "M\0example.py\0", ""
        if command[:2] == ["git", "diff"]:
            assert command[-1] == "--", "the shared diff mock must cover the complete staged snapshot"
            return True, diff, ""
        if command[:2] == ["git", "show"] and command[-1] == ":0:example.py":
            return True, "pytest.skip(reason='legacy')\nclient = DynamicClient(api_client)\n", ""
        if command[:2] == ["git", "show"] and command[-1] == "HEAD:example.py":
            return True, "pytest.skip(reason='legacy')\n", ""
        if command[:2] == ["git", "show"] and command[-1].endswith("exceptions.toml"):
            return True, "exceptions = []\n", ""
        fail(f"unexpected command: {command}")

    monkeypatch.setattr(target=check_policy, name="run_command", value=run_command)
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["example.py"]) == 1, "added source violation should make the check fail"


def test_main_checks_staged_source_instead_of_worktree_source(monkeypatch, tmp_path: Path) -> None:
    """Staged policy checks inspect the content that will be committed."""
    file_path = tmp_path / "example.py"
    file_path.write_text(data="value = 1\n", encoding="utf-8")
    diff = """diff --git a/example.py b/example.py
index 0000000..1111111 100644
--- a/example.py
+++ b/example.py
@@ -1,0 +1,1 @@
+pytestmark = pytest.mark.skipif(condition)
"""

    def run_command(**kwargs):
        command = kwargs["command"]
        if command[:3] == ["git", "ls-files", "--stage"]:
            return True, "", ""
        if "--name-status" in command:
            return True, "M\0example.py\0", ""
        if command[:2] == ["git", "diff"]:
            assert command[-1] == "--", "the shared diff mock must cover the complete staged snapshot"
            return True, diff, ""
        if command[:2] == ["git", "show"] and command[-1] == ":0:example.py":
            return True, "pytestmark = pytest.mark.skipif(condition)\n", ""
        if command[:2] == ["git", "show"] and command[-1] == "HEAD:example.py":
            return True, "value = 1\n", ""
        if command[:2] == ["git", "show"] and command[-1].endswith("exceptions.toml"):
            return True, "exceptions = []\n", ""
        fail(f"unexpected command: {command}")

    monkeypatch.setattr(target=check_policy, name="run_command", value=run_command)
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["example.py"]) == 1, "staged source violation should make the check fail"


def test_main_checks_staged_source_with_configured_diff_filters(monkeypatch, tmp_path: Path) -> None:
    """Configured external diff and textconv filters cannot hide violations."""
    suppressor = tmp_path / "suppress-diff"
    suppressor.write_text(data="#!/bin/sh\nexit 0\n", encoding="utf-8")
    suppressor.chmod(mode=0o755)
    (tmp_path / ".gitattributes").write_text(data="*.py diff=policy\n", encoding="utf-8")
    (tmp_path / "example.py").write_text(data="pytest.skip(reason='forbidden')\n", encoding="utf-8")
    manifest_path = tmp_path / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(data="exceptions = []\n", encoding="utf-8")

    def git(*args: str) -> None:
        run_command(command=["git", *args], cwd=tmp_path, check=True, verify_stderr=False)

    git("init", "-q")
    git("config", "diff.external", str(suppressor))
    git("config", "diff.policy.textconv", str(suppressor))
    git("add", ".gitattributes", "example.py", str(manifest_path.relative_to(tmp_path)))
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["example.py"]) == 1, "diff filters must not hide staged source violations"


def test_main_checks_staged_path_with_quoted_diff_header(monkeypatch: MonkeyPatch) -> None:
    """Shared staged-diff parsing handles paths quoted by Git's human-readable output."""
    path = ':(top)example "quoted"*.py'
    diff = """diff --git "a/:(top)example \\"quoted\\"*.py" "b/:(top)example \\"quoted\\"*.py"
index 0000000..1111111 100644
--- "a/:(top)example \\"quoted\\"*.py"
+++ "b/:(top)example \\"quoted\\"*.py"
@@ -0,0 +1 @@
+pytest.skip(reason='forbidden')
"""

    def run_command(**kwargs):
        command = kwargs["command"]
        if command[:3] == ["git", "ls-files", "--stage"]:
            return True, "", ""
        if "--name-status" in command:
            return True, f"M\0{path}\0", ""
        if command[:2] == ["git", "diff"]:
            assert {"--no-ext-diff", "--no-textconv"} <= set(command), "diff filters must be disabled"
            assert command[-1] == "--", "the shared diff should cover the complete staged snapshot"
            return True, diff, ""
        if command[:2] == ["git", "show"] and command[-1] == f":0:{path}":
            return True, "pytest.skip(reason='forbidden')\n", ""
        if command[:2] == ["git", "show"] and command[-1] == f"HEAD:{path}":
            return True, "", ""
        if command[:2] == ["git", "show"] and command[-1].endswith("exceptions.toml"):
            return True, "exceptions = []\n", ""
        fail(f"unexpected command: {command}")

    monkeypatch.setattr(target=check_policy, name="run_command", value=run_command)

    assert main(arguments=[path]) == 1, "quoted staged path violation should make the check fail"


def test_main_fails_closed_when_diff_header_cannot_be_mapped(monkeypatch: MonkeyPatch) -> None:
    """A staged file whose diff header is unmappable is checked on every line."""
    path = "example.py"
    staged_source = "value = 1\npytest.skip(reason='legacy')\n"

    def run_command(**kwargs):
        command = kwargs["command"]
        if command[:3] == ["git", "ls-files", "--stage"]:
            return True, "", ""
        if "--name-status" in command:
            return True, f"M\0{path}\0", ""
        if command[:2] == ["git", "diff"]:
            return True, 'diff --git "a/unterminated\n', ""
        if command[:2] == ["git", "show"] and command[-1] == f":0:{path}":
            return True, staged_source, ""
        if command[:2] == ["git", "show"] and command[-1] == f"HEAD:{path}":
            return True, staged_source, ""
        if command[:2] == ["git", "show"] and command[-1].endswith("exceptions.toml"):
            return True, "exceptions = []\n", ""
        fail(f"unexpected command: {command}")

    monkeypatch.setattr(target=check_policy, name="run_command", value=run_command)

    assert main(arguments=[path]) == 1, "unmappable diffs must check every staged line, not skip them"


def test_added_lines_parser_ignores_header_like_added_source() -> None:
    """Added source resembling a file header cannot redirect diff parsing."""
    diff = """diff --git a/example.py b/example.py
index 0000000..1111111 100644
--- a/example.py
+++ b/example.py
@@ -0,0 +1,2 @@
+++ b/fake.py
+pytest.skip(reason='forbidden')
"""

    assert _added_lines_by_path(diff=diff) == {Path("example.py"): frozenset({1, 2})}, (
        "header-like added source should not redirect parsing"
    )


def test_added_lines_parser_maps_rename_only_diffs() -> None:
    """An exact-rename diff maps its target with no added lines."""
    diff = """diff --git a/old.py b/renamed.py
similarity index 100%
rename from old.py
rename to renamed.py
"""

    assert _added_lines_by_path(diff=diff) == {Path("renamed.py"): frozenset()}, (
        "a resolvable rename header must map the target path instead of leaving it unmappable"
    )


def test_git_unquote_decodes_c_quoted_paths() -> None:
    """C-quoted paths decode to their raw characters, including octal bytes."""
    assert _git_unquote(quoted='"\\303\\251.py"') == "é.py", "octal byte escapes must decode to UTF-8 characters"
    assert _git_unquote(quoted='"tab\\there"') == "tab\there", "simple escapes must decode"
    assert _git_unquote(quoted='"quote\\" and backslash\\\\"') == 'quote" and backslash\\', (
        "escaped quotes and backslashes must decode"
    )
    assert _git_unquote(quoted="bare.py") == "bare.py", "unquoted paths pass through unchanged"


def test_git_unquote_preserves_invalid_utf8_bytes() -> None:
    """Invalid UTF-8 bytes survive decoding instead of collapsing to U+FFFD."""
    assert _git_unquote(quoted='"\\377"') == "\udcff", "undecodable bytes must round-trip via surrogateescape"


def test_git_quoted_token_splits_and_rejects_malformed_tokens() -> None:
    """Quoted tokens split on their closing quote and reject unterminated quotes."""
    assert _git_quoted_token(text='"a\\"b" rest') == ('"a\\"b"', " rest"), "escaped quotes must not terminate the token"
    assert _git_quoted_token(text='"unterminated') is None, "unterminated quotes must be rejected"


def test_git_header_token_splits_bare_and_quoted_tokens() -> None:
    """Header tokens split on spaces when bare and on quotes when quoted."""
    assert _git_header_token(text="b/plain.py") == ("b/plain.py", ""), "bare tokens run to the end"
    assert _git_header_token(text='"b/qu oted.py" tail') == ('"b/qu oted.py"', " tail"), (
        "quoted tokens may contain spaces"
    )


def test_diff_header_path_decodes_each_side_independently() -> None:
    """Mixed quoted and bare header paths both resolve to the target path."""
    assert _diff_header_path(diff_line='diff --git "a/ol\\303\\251.py" b/plain.py') == Path("plain.py"), (
        "a quoted old path with a bare new path must resolve"
    )
    assert _diff_header_path(diff_line='diff --git a/plain.py "b/ne\\303\\251.py"') == Path("neé.py"), (
        "a bare old path with a quoted new path must decode the target"
    )
    assert _diff_header_path(diff_line="diff --git a/x.py b/y.py") == Path("y.py"), "bare headers must resolve"
    assert _diff_header_path(diff_line='diff --git "a/unterminated b/y.py') is None, (
        "unterminated quoted headers must be rejected"
    )


def test_main_returns_success_for_compliant_files(monkeypatch) -> None:
    """The command exits zero when selected paths comply."""
    monkeypatch.setattr(target=check_policy, name="run_command", value=lambda **kwargs: (True, "", ""))

    assert main(arguments=["docs/code-quality.md"]) == 0, "compliant files should pass the policy check"


def test_aliases_resolve_in_lambdas_and_comprehensions_without_leaking() -> None:
    """Nested expression scopes catch aliases and isolate comprehension targets."""
    source = dedent(
        """
        import pytest
        from kubernetes.dynamic import DynamicClient
        skip = pytest.skip
        client = DynamicClient
        lambda shadowed: shadowed.skip()
        lambda: skip()
        lambda: client(api)
        [skip() for skip in values]
        [skip() for value in values]
        [client(api) for client in values]
        [client(api) for value in values]
        pytestmark = [pytest.mark.skip for value in values]
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (7, "pytest.skip() is forbidden"),
        (8, "reuse the DynamicClient passed through the call path instead of constructing one"),
        (10, "pytest.skip() is forbidden"),
        (12, "reuse the DynamicClient passed through the call path instead of constructing one"),
        (13, "module-level pytestmark skip markers are forbidden"),
    ], "lambda and comprehension aliases should resolve with lexical shadowing"


def test_namedexprs_resolve_outside_comprehensions() -> None:
    """Walrus bindings escape comprehensions and walrus callees resolve."""
    source = dedent(
        """
        import pytest
        [marker := pytest.mark.skip for value in values]
        pytestmark = marker
        [(skip := pytest.skip)() for value in values]
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (4, "module-level pytestmark skip markers are forbidden"),
        (5, "pytest.skip() is forbidden"),
    ], "walrus bindings in comprehensions should retain policy checks"


def test_check_python_source_relative_imports_are_filtered_to_added_lines() -> None:
    """Only added relative imports are rejected; absolute imports remain valid."""
    source = dedent(
        """
        from .local import helper
        from ..parent import value
        from absolute import allowed
        """
    )

    all_violations = check_python_source(file_path=Path("example.py"), source=source)
    assert check_python_source(file_path=Path("example.py"), source=source, added_lines={2}) == [all_violations[0]], (
        "added first relative import should be rejected"
    )
    assert check_python_source(file_path=Path("example.py"), source=source, added_lines={3}) == [all_violations[1]], (
        "added second relative import should be rejected"
    )
    assert check_python_source(file_path=Path("example.py"), source=source, added_lines={4}) == [], (
        "added absolute import should be allowed"
    )


def test_relative_dynamic_imports_activate_from_added_aliases() -> None:
    """Added aliases activate unchanged relative dynamic-import calls."""
    source = dedent(
        """
        import importlib
        module_loader = importlib.import_module
        builtin_loader = __import__
        module_loader(".local")
        builtin_loader("parent", globals(), locals(), [], 1)
        """
    )

    assert _violation_signatures(
        check_python_source(file_path=Path("example.py"), source=source, added_lines={3, 4})
    ) == [
        (5, "relative imports are forbidden; use absolute imports"),
        (6, "relative imports are forbidden; use absolute imports"),
    ], "new dynamic-import aliases should activate their unchanged relative calls"


def test_staged_entries_preserve_rename_baseline_but_not_copy_baseline() -> None:
    """Renames retain their old source while copies are new paths without a baseline."""
    entries = _parse_staged_entries(status_output="R100\0old.py\0renamed.py\0C100\0source.py\0copied.py\0")

    assert [(entry.status, entry.path, entry.head_path) for entry in entries] == [
        ("R", Path("renamed.py"), Path("old.py")),
        ("C", Path("copied.py"), None),
    ], "copy and rename status entries must drive distinct linter and STD baselines"


def test_staged_status_models_deleted_paths() -> None:
    """Name-status parsing keeps deleted paths explicit, including renames."""
    deleted_paths = _parse_staged_status("M\0keep.py\0D\0gone.py\0R100\0old.py\0new.py\0C100\0source.py\0copy.py\0")

    assert deleted_paths == {Path(path) for path in ("gone.py", "old.py")}, (
        "status parsing should retain deleted paths, including renamed sources"
    )


def test_staged_status_parsing_is_independent_of_git_entry_order() -> None:
    """Status parsing returns the same deleted-path set regardless of entry order."""
    first = _parse_staged_status(status_output="M\0first.py\0D\0second.py\0")
    second = _parse_staged_status(status_output="D\0second.py\0M\0first.py\0")

    assert first == second, "status parsing must not depend on Git's entry order"


def test_main_skips_deleted_paths(monkeypatch) -> None:
    """Deleted content is absent from the resulting commit and is not checked."""

    def run_command(**kwargs):
        command = kwargs["command"]
        if "--name-status" in command:
            return True, "D\0gone.py\0", ""
        fail(f"deleted paths should not request diff or index content: {command}")

    monkeypatch.setattr(target=check_policy, name="run_command", value=run_command)

    assert main(arguments=["gone.py"]) == 0, "deleted paths should be skipped successfully"


@mark.parametrize(
    "branch_bindings",
    [
        ("conditional_skip = pytest.skip", "conditional_skip = safe_skip"),
        ("conditional_skip = safe_skip", "conditional_skip = pytest.skip"),
    ],
)
def test_check_python_source_resolves_conditional_deferred_and_destructured_aliases(
    branch_bindings: tuple[str, str],
) -> None:
    """Forbidden aliases remain detectable through branches, deferred setup, and unpacking."""
    source = dedent(
        f"""
        import pytest
        from kubernetes.dynamic import DynamicClient
        safe_skip = unrelated

        if condition:
            {branch_bindings[0]}
        else:
            {branch_bindings[1]}
        conditional_skip(reason="conditional")

        def configure():
            global deferred_skip, deferred_client
            deferred_skip = pytest.skip
            deferred_client = DynamicClient

        configure()
        deferred_skip(reason="deferred")
        deferred_client(api_client)
        destructured_skip, destructured_client = pytest.skip, DynamicClient
        destructured_skip(reason="destructured")
        destructured_client(api_client)
        """
    )

    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source)) == [
        (10, "pytest.skip() is forbidden"),
        (18, "pytest.skip() is forbidden"),
        (19, "reuse the DynamicClient passed through the call path instead of constructing one"),
        (21, "pytest.skip() is forbidden"),
        (22, "reuse the DynamicClient passed through the call path instead of constructing one"),
    ], "alias resolution should inspect both conditional alternatives and deferred bindings"


def test_check_file_applies_top_level_test_rule_only_to_staged_paths() -> None:
    """An unstaged selected path must not trigger the staged top-level-test rule."""
    assert check_file(file_path=Path("tests/test_policy.py"), staged=False) == [], (
        "top-level test path policy should apply only to staged changes"
    )


def test_check_file_checks_copied_python_without_added_diff_lines() -> None:
    """Copied Python paths receive full checks when Git reports no added hunks."""
    violations = check_file(
        file_path=Path("utilities/copied.py"),
        staged=True,
        added_lines=frozenset(),
        source="client = DynamicClient(api_client)\n",
    )

    assert _violation_signatures(violations) == [
        (1, "reuse the DynamicClient passed through the call path instead of constructing one")
    ], "copied Python files must not be skipped only because their diff has no hunks"


def test_check_python_source_rejects_dynamic_client_from_client_module() -> None:
    """The supported direct DynamicClient import path includes kubernetes.dynamic.client."""
    source = "from kubernetes.dynamic.client import DynamicClient\nDynamicClient(api_client)\n"

    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source)) == [
        (2, "reuse the DynamicClient passed through the call path instead of constructing one")
    ], "the client submodule import must resolve to the forbidden DynamicClient"


def test_check_python_source_rejects_skip_markers_in_marker_value_contexts() -> None:
    """Skip markers are forbidden when passed as pytest.param or parametrization marks."""
    source = dedent(
        """
        import pytest

        @pytest.mark.parametrize("value", [pytest.param(1, marks=pytest.mark.skip)])
        def test_skipped(value):
            pass

        values = [pytest.param(2, marks=pytest.mark.skipif(condition))]
        """
    )

    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source)) == [
        (4, "pytest.mark.skip and pytest.mark.skipif are forbidden"),
        (8, "pytest.mark.skip and pytest.mark.skipif are forbidden"),
    ], "skip markers in marker-value arguments must be rejected"


def test_main_rejects_deleted_generated_documentation(monkeypatch: MonkeyPatch) -> None:
    """Deleting generated site content remains a policy violation."""

    def run_command(**kwargs):
        command = kwargs["command"]
        if "--name-status" in command:
            return True, "D\0docs/site/index.html\0", ""
        fail(f"deleted site paths should not request content: {command}")

    monkeypatch.setattr(target=check_policy, name="run_command", value=run_command)

    assert main(arguments=["docs/site/index.html"]) == 1, "deleted generated documentation must be rejected"


@mark.parametrize(
    "source, line_number",
    [
        (
            "import pytest\n\ndef run():\n    alias()\nalias = pytest.skip\n",
            4,
        ),
        (
            "import pytest\n\ndef run():\n    global alias\n    alias()\ndef configure():\n    global alias\n    alias = pytest.skip\n",
            5,
        ),
        (
            "import pytest\n\ndef run():\n    alias()\n    alias = pytest.skip\n",
            4,
        ),
    ],
)
def test_check_python_source_resolves_module_bindings_declared_after_function_bodies(
    source: str, line_number: int
) -> None:
    """Deferred function bodies must resolve forbidden module and global bindings declared later."""
    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(line_number, "pytest.skip() is forbidden")], (
        "forbidden aliases declared after a function body must remain visible to deferred calls"
    )


@mark.parametrize(
    "source, line_number",
    [
        (
            dedent(
                """
                import pytest
                alias = pytest.skip
                if condition:
                    alias = safe
                alias()
                """
            ),
            6,
        ),
        (
            dedent(
                """
                import pytest
                if condition:
                    alias = safe
                else:
                    alias = pytest.skip
                alias()
                """
            ),
            7,
        ),
        (
            dedent(
                """
                import pytest
                if condition:
                    alias = pytest.skip
                else:
                    alias = safe
                alias()
                """
            ),
            7,
        ),
    ],
)
def test_check_python_source_rejects_forbidden_alias_when_any_branch_reaches_call(
    source: str, line_number: int
) -> None:
    """A safe branch must not hide a pytest.skip alias reachable through another branch."""
    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(line_number, "pytest.skip() is forbidden")], (
        "every feasible forbidden branch must activate the alias call"
    )


def test_check_python_source_allows_unconditional_alias_reset_after_branches() -> None:
    """A later unconditional safe reset makes a formerly forbidden branch unreachable at the call."""
    source = dedent(
        """
        import pytest
        alias = pytest.skip
        if condition:
            alias = safe
        alias = safe
        alias()
        """
    )

    assert check_python_source(file_path=Path("example.py"), source=source) == [], (
        "an unconditional safe alias reset must replace earlier branch bindings"
    )


@mark.parametrize(
    "source, line_number",
    [
        (
            "import pytest\n\ntry:\n    alias = pytest.skip\nexcept Exception:\n    alias = safe\nalias()\n",
            7,
        ),
        (
            "import pytest\n\nmatch value:\n    case 1:\n        alias = pytest.skip\n    case _:\n        alias = safe\nalias()\n",
            8,
        ),
    ],
)
def test_check_python_source_rejects_forbidden_aliases_from_try_and_match_branches(
    source: str, line_number: int
) -> None:
    """Try and match alternatives must preserve a forbidden alias when it remains feasible."""
    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(line_number, "pytest.skip() is forbidden")], (
        "try and match branch alternatives must not hide a feasible forbidden alias"
    )


def test_check_python_source_allows_locally_defined_dynamic_client_class_but_rejects_import() -> None:
    """A local DynamicClient class is valid while the real Kubernetes class remains forbidden."""
    source = dedent(
        """
        class DynamicClient:
            pass

        DynamicClient(api_client)
        from kubernetes.dynamic import DynamicClient as ImportedDynamicClient
        ImportedDynamicClient(api_client)
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [
        (7, "reuse the DynamicClient passed through the call path instead of constructing one")
    ], "only imported Kubernetes DynamicClient construction should be rejected"


def test_check_python_source_activates_unchanged_pytest_param_from_added_marker_alias() -> None:
    """Adding a forbidden marker alias must activate an unchanged pytest.param call."""
    source = dedent(
        """
        import pytest
        marker_alias = pytest.mark.skip
        values = pytest.param(1, marks=marker_alias)
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source, added_lines={3})

    assert _violation_signatures(violations) == [(4, "pytest.mark.skip and pytest.mark.skipif are forbidden")], (
        "an added marker alias must activate the unchanged pytest.param marker use"
    )


@mark.parametrize("callee_expression", ["pytest.param if condition else safe", "safe if condition else pytest.param"])
def test_check_python_source_rejects_pytest_param_when_conditional_callee_is_feasible(
    callee_expression: str,
) -> None:
    """A conditional callee must be rejected whenever pytest.param is one feasible alternative."""
    source = dedent(
        f"""
        import pytest
        callee = {callee_expression}
        callee(1, marks=pytest.mark.skip)
        """
    )

    violations = check_python_source(file_path=Path("example.py"), source=source)

    assert _violation_signatures(violations) == [(4, "pytest.mark.skip and pytest.mark.skipif are forbidden")], (
        "pytest.param marker policy must follow every feasible conditional callee"
    )


def test_check_python_source_rejects_imported_skip_after_empty_for_loop_shadowing() -> None:
    """An empty loop cannot replace the imported pytest.skip binding."""
    source = 'from pytest import skip\nfor skip in ():\n pass\nskip("x")'

    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source)) == [
        (4, "pytest.skip() is forbidden")
    ], "an empty loop must preserve the directly imported pytest.skip binding"


@mark.parametrize(
    "added_lines, expected_signatures",
    [
        (None, [(6, "pytest.skip() is forbidden")]),
        ({6}, [(6, "pytest.skip() is forbidden")]),
        ({1}, [(6, "pytest.skip() is forbidden")]),
        ({2}, []),
    ],
    ids=["full", "call-only", "import-only", "unrelated-line"],
)
def test_check_python_source_preserves_incoming_binding_when_while_body_does_not_run(
    added_lines: set[int] | None,
    expected_signatures: list[tuple[int, str]],
) -> None:
    """A while loop body cannot unconditionally replace its incoming binding."""
    source = "import pytest\nunrelated = object()\nalias = pytest.skip\nwhile condition:\n alias = safe\nalias()"

    violations = check_python_source(file_path=Path("example.py"), source=source, added_lines=added_lines)

    assert _violation_signatures(violations) == expected_signatures, (
        "a zero-iteration while path must retain the incoming pytest.skip alias"
    )


@mark.parametrize("loop_header", ["for item in items:", "while condition:"], ids=["for", "while"])
@mark.parametrize(
    "added_lines, expected_signatures",
    [
        (None, [(9, "pytest.skip() is forbidden")]),
        ({9}, [(9, "pytest.skip() is forbidden")]),
        ({1}, [(9, "pytest.skip() is forbidden")]),
        ({2}, []),
    ],
    ids=["full", "call-only", "import-only", "unrelated-line"],
)
def test_check_python_source_break_bypasses_loop_else(
    loop_header: str,
    added_lines: set[int] | None,
    expected_signatures: list[tuple[int, str]],
) -> None:
    """A break path retains its binding because it does not execute the loop else."""
    source = (
        "import pytest\n"
        "unrelated = object()\n"
        "alias = safe\n"
        f"{loop_header}\n"
        " alias = pytest.skip\n"
        " break\n"
        "else:\n"
        " alias = safe\n"
        "alias()"
    )

    violations = check_python_source(file_path=Path("example.py"), source=source, added_lines=added_lines)

    assert _violation_signatures(violations) == expected_signatures, (
        "for and while break paths must bypass their loop else binding"
    )


@mark.parametrize("abrupt_statement", ["raise ValueError", "return"], ids=["raise", "return"])
@mark.parametrize(
    "added_lines",
    [None, {9}, {1}, {2}],
    ids=["full", "call-only", "import-only", "unrelated-line"],
)
def test_check_python_source_excludes_abrupt_branch_bindings_from_following_join(
    abrupt_statement: str,
    added_lines: set[int] | None,
) -> None:
    """Bindings from raise and return branches cannot reach a following call."""
    source = (
        "import pytest\n"
        "unrelated = object()\n"
        "alias = safe\n"
        "def helper(condition):\n"
        " global alias\n"
        " if condition:\n"
        "  alias = pytest.skip\n"
        f"  {abrupt_statement}\n"
        " alias()"
    )

    violations = check_python_source(file_path=Path("example.py"), source=source, added_lines=added_lines)

    assert violations == [], "raise and return branch bindings must not flow into the following join"


def test_check_python_source_rejects_outer_pytest_skip_after_uncalled_global_assignment() -> None:
    """An uncalled function's global assignment cannot replace the outer pytest binding."""
    source = 'import pytest\ndef helper():\n global pytest\n pytest = safe\npytest.skip("x")'

    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source)) == [
        (5, "pytest.skip() is forbidden")
    ], "an uncalled function must not apply its global assignment to outer control flow"


def test_check_python_source_preserves_pytest_skip_alias_when_try_raises_before_else() -> None:
    """A raised exception bypasses an else reassignment and preserves the skip alias."""
    source = 'import pytest\ntry:\n alias = pytest.skip\n raise ValueError\nexcept ValueError:\n pass\nelse:\n alias = safe\nalias("x")'

    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source)) == [
        (9, "pytest.skip() is forbidden")
    ], "the raised try path must preserve its pytest.skip alias after the handler"


def test_check_python_source_allows_exception_alias_shadowing_pytest_skip_alias() -> None:
    """An exception handler alias shadows an earlier pytest.skip alias inside the handler."""
    source = 'import pytest\nalias = pytest.skip\ntry:\n raise ValueError\nexcept ValueError as alias:\n alias("x")'

    assert check_python_source(file_path=Path("example.py"), source=source) == [], (
        "exception aliases must shadow earlier aliases within their handler"
    )


def test_check_python_source_rejects_wildcard_imported_pytest_skip() -> None:
    """A wildcard pytest import must still identify skip as the forbidden pytest function."""
    source = 'from pytest import *\nskip("x")'

    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source)) == [
        (2, "pytest.skip() is forbidden")
    ], "wildcard-imported pytest.skip calls must be rejected"


def test_check_python_source_preserves_shadowing_after_wildcard_pytest_import() -> None:
    """A local skip binding shadows a wildcard import only in its nested scope."""
    source = dedent(
        """
        from pytest import *

        skip("outer")

        def helper():
            skip = safe
            skip("local")
        """
    )

    assert _violation_signatures(check_python_source(file_path=Path("example.py"), source=source)) == [
        (4, "pytest.skip() is forbidden")
    ], "wildcard imports must retain lexical shadowing behavior"


def test_git_unquote_preserves_raw_surrogate_characters() -> None:
    """A raw surrogate character in a quoted token round-trips without crashing."""
    assert _git_unquote(quoted='"\udcff.py"') == "\udcff.py", (
        "raw surrogate characters must survive decoding instead of raising UnicodeEncodeError"
    )


def test_added_lines_parser_counts_only_physical_newlines() -> None:
    """Unicode line separators inside diff content must not shift line numbers."""
    diff = (
        "diff --git a/tests/network/test_example.py b/tests/network/test_example.py\n"
        "--- a/tests/network/test_example.py\n"
        "+++ b/tests/network/test_example.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+text = 'before\u2028after'\n"
        "+pytest.skip(reason='hidden')\n"
        "+value = 1\n"
    )

    added_lines = _added_lines_by_path(diff=diff)

    assert added_lines[Path("tests/network/test_example.py")] == frozenset({1, 2, 3}), (
        "only physical newline characters may delimit diff lines; a Unicode line separator "
        "inside added content must not drift subsequent line numbers"
    )


def test_changed_alias_binding_activates_requirement_marker_check() -> None:
    """Changing an alias binding activates the requirement check at its unchanged application."""
    source = dedent(
        """
        import pytest

        marker = pytest.mark.sriov

        @marker
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_python_source(
        file_path=Path("tests/network/test_example.py"),
        source=source,
        added_lines={4},
    )

    assert violations, "a changed alias binding must activate the requirement-marker check at its application"


def test_branch_ambiguous_alias_does_not_satisfy_requirement() -> None:
    """An alias whose binding is branch-dependent provides no marker coverage."""
    source = dedent(
        """
        import pytest

        special = pytest.mark.special_infra if condition else pytest.mark.smoke

        @special
        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_python_source(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a branch-ambiguous alias must not satisfy the marker requirement"
