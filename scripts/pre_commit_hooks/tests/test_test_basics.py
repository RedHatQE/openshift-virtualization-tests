"""Unit tests for mechanical test-basics policy checks."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from scripts.pre_commit_hooks.check_policy import check_python_source
from scripts.pre_commit_hooks.check_test_basics import check_test_basics


def test_assertions_require_descriptive_messages() -> None:
    """Assertions without meaningful messages are rejected while described assertions pass."""
    source = dedent(
        """
        assert value
        assert empty, ""
        assert whitespace, "   "
        assert empty_formatted, f""
        assert empty_concatenated, "" + ""
        assert empty_interpolated, f"{''}"
        assert other, "other must be true"
        assert concatenated_message, "other " + "must be true"
        assert interpolated_message, f"{'other must be true'}"
        assert dynamic_message, message
        assert dynamic_formatted_message, f"{message}"
        assert unsupported_message, "other" * 2
        assert zero, 0
        assert missing, None
        assert disabled, False
        """
    )

    violations = check_test_basics(file_path=Path("tests/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (2, "test-basics: add a descriptive failure message to this assert"),
        (3, "test-basics: add a descriptive failure message to this assert"),
        (4, "test-basics: add a descriptive failure message to this assert"),
        (5, "test-basics: add a descriptive failure message to this assert"),
        (6, "test-basics: add a descriptive failure message to this assert"),
        (7, "test-basics: add a descriptive failure message to this assert"),
        (14, "test-basics: add a descriptive failure message to this assert"),
        (15, "test-basics: add a descriptive failure message to this assert"),
        (16, "test-basics: add a descriptive failure message to this assert"),
    ], "assert failure messages must contain descriptive text, not falsey placeholders"


def test_unittest_assertion_methods_are_rejected() -> None:
    """Pytest tests must use plain pytest assertions instead of self.assert methods."""
    source = dedent(
        """
        class TestExample:
            def test_value(self):
                self.assertEqual(actual, expected)
                self.assertTrue(condition)
        """
    )

    violations = check_test_basics(file_path=Path("tests/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (4, "test-basics: replace unittest self.assert* with a pytest assert"),
        (5, "test-basics: replace unittest self.assert* with a pytest assert"),
    ], "each unittest assertion method should identify its own source line"


def test_none_and_boolean_comparisons_require_identity_or_implicit_truthiness() -> None:
    """None uses identity and booleans use implicit truthiness, while other equality remains valid."""
    source = dedent(
        """
        value == None
        value != None
        value == True
        value != False
        value is None
        value is not False
        if value:
            pass
        value == 1
        """
    )

    violations = check_test_basics(file_path=Path("tests/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (2, "test-basics: compare None with 'is' or 'is not', not == or !="),
        (3, "test-basics: compare None with 'is' or 'is not', not == or !="),
        (4, "test-basics: use the value's implicit truthiness instead of comparing with True or False"),
        (5, "test-basics: use the value's implicit truthiness instead of comparing with True or False"),
    ], "only equality comparisons with None or booleans should be rejected"


def test_async_constructs_report_one_violation_per_construct() -> None:
    """Async functions, awaits, async loops, and async context managers are forbidden without duplicates."""
    source = dedent(
        """
        async def fetch():
            await operation()
            async for value in values:
                pass
            async with manager:
                pass
        """
    )

    violations = check_test_basics(file_path=Path("tests/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (2, "test-basics: async functions are forbidden; use synchronous code")
    ], "an async function should stop traversal before reporting duplicate nested async constructs"


def test_sleep_aliases_are_rejected_regardless_of_loop_context() -> None:
    """Every aliased time.sleep call is rejected, including nested expression contexts."""
    source = dedent(
        """
        import time as clock
        from time import sleep

        def helper():
            clock.sleep(1)

        for value in values:
            clock.sleep(1)
            sleep(2)

            def nested():
                clock.sleep(3)

            @decorator(clock.sleep(4))
            def decorated(value=clock.sleep(5)):
                pass

            lambda: clock.sleep(6)
            lambda value=clock.sleep(7): value

        while condition:
            clock.sleep(8)
        """
    )

    violations = check_test_basics(
        file_path=Path("tests/example.py"),
        source=source,
        added_lines={6, 9, 10, 13, 15, 16, 19, 20, 23},
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (6, "test-basics: replace time.sleep() with TimeoutSampler"),
        (9, "test-basics: replace time.sleep() with TimeoutSampler"),
        (10, "test-basics: replace time.sleep() with TimeoutSampler"),
        (13, "test-basics: replace time.sleep() with TimeoutSampler"),
        (15, "test-basics: replace time.sleep() with TimeoutSampler"),
        (16, "test-basics: replace time.sleep() with TimeoutSampler"),
        (19, "test-basics: replace time.sleep() with TimeoutSampler"),
        (20, "test-basics: replace time.sleep() with TimeoutSampler"),
        (23, "test-basics: replace time.sleep() with TimeoutSampler"),
    ], "every newly added time.sleep call should be rejected regardless of loop or expression context"


def test_added_time_sleep_is_rejected_in_root_level_python() -> None:
    """Newly added time.sleep calls are rejected even in the root conftest.py."""
    source = dedent(
        """
        import time
        time.sleep(1)
        """
    )

    violations = check_python_source(file_path=Path("conftest.py"), source=source, added_lines={3})

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (3, "test-basics: replace time.sleep() with TimeoutSampler")
    ], "root-level Python must reject newly added time.sleep calls"


def test_added_time_sleep_import_or_alias_activates_an_unchanged_call() -> None:
    """Adding either time.sleep binding activates an unchanged call through check_python_source."""
    source = dedent(
        """
        import time
        sleep = time.sleep
        sleep(1)
        """
    )

    import_violations = check_python_source(file_path=Path("conftest.py"), source=source, added_lines={2})
    alias_violations = check_python_source(file_path=Path("conftest.py"), source=source, added_lines={3})

    expected = [(4, "test-basics: replace time.sleep() with TimeoutSampler")]
    assert [(violation.line_number, violation.message) for violation in import_violations] == expected, (
        "adding the time import must activate the unchanged aliased call"
    )
    assert [(violation.line_number, violation.message) for violation in alias_violations] == expected, (
        "changing the sleep alias must activate the unchanged call"
    )


def test_comparison_policy_only_checks_none_and_booleans_adjacent_to_equality() -> None:
    """Chained identity comparisons do not make neighboring equality operands invalid."""
    source = dedent(
        """
        item == other is None
        True is flag == value
        value == None
        value != False
        """
    )

    violations = check_test_basics(file_path=Path("tests/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (4, "test-basics: compare None with 'is' or 'is not', not == or !="),
        (5, "test-basics: use the value's implicit truthiness instead of comparing with True or False"),
    ], "only operands adjacent to == or != should trigger None and boolean comparison rules"


def test_relative_imports_are_rejected_but_absolute_imports_are_allowed() -> None:
    """Relative imports are rejected while absolute imports remain valid."""
    source = dedent(
        """
        from .local import helper
        from ..parent import value
        from absolute import allowed
        """
    )

    violations = check_test_basics(file_path=Path("tests/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (2, "relative imports are forbidden; use absolute imports"),
        (3, "relative imports are forbidden; use absolute imports"),
    ], "only relative imports should be rejected"


def test_relative_imports_are_filtered_to_added_lines() -> None:
    """Only newly added relative imports are rejected."""
    source = dedent(
        """
        import importlib
        from .local import helper
        from ..parent import value
        from absolute import allowed
        importlib.import_module("." + "helpers", package=__package__)
        """
    )

    all_violations = check_test_basics(file_path=Path("tests/example.py"), source=source)
    assert check_test_basics(file_path=Path("tests/example.py"), source=source, added_lines={3}) == [
        all_violations[0]
    ], "an added first relative import should be rejected"
    assert check_test_basics(file_path=Path("tests/example.py"), source=source, added_lines={4}) == [
        all_violations[1]
    ], "an added second relative import should be rejected"
    assert check_test_basics(file_path=Path("tests/example.py"), source=source, added_lines={5}) == [], (
        "an added absolute import should be allowed"
    )
    assert check_test_basics(file_path=Path("tests/example.py"), source=source, added_lines={6}) == [
        all_violations[2]
    ], "an added constant-expression relative import should be rejected"


def test_relative_dynamic_imports_are_rejected() -> None:
    """Dynamic imports using relative names must obey the absolute-import rule."""
    source = dedent(
        """
        import importlib
        importlib.import_module(".local", package=__package__)
        importlib.import_module("." + "helpers", package=__package__)
        importlib.import_module("absolute." + "module")
        importlib.import_module(module_name, package=__package__)
        importlib.import_module("." * 2, package=__package__)
        __import__(".parent", globals(), locals(), [], 1)
        importlib.import_module("absolute.module")
        __import__("absolute.module")
        """
    )

    assert [
        (violation.line_number, violation.message)
        for violation in check_test_basics(file_path=Path("tests/example.py"), source=source)
    ] == [
        (3, "relative imports are forbidden; use absolute imports"),
        (4, "relative imports are forbidden; use absolute imports"),
        (8, "relative imports are forbidden; use absolute imports"),
    ], "relative dynamic imports must be rejected while absolute, dynamic, and unsupported names remain valid"


def test_builtins_import_aliases_with_positive_level_are_rejected_as_relative_imports() -> None:
    """Both builtins.__import__ spellings must enforce the positive relative-import level rule."""
    source = dedent(
        """
        import builtins
        builtins.__import__("pkg", level=1)
        builtins.__import__("pkg", level=1 + 0)
        builtins.__import__("pkg", level=True)
        builtins.__import__("pkg", level=import_level)
        builtins.__import__("pkg", level=1 * 1)
        from builtins import __import__ as loader
        loader("other", globals(), locals(), [], 2)
        loader("helpers", globals(), locals(), [], 1 + 0)
        """
    )

    violations = check_test_basics(file_path=Path("tests/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (3, "relative imports are forbidden; use absolute imports"),
        (4, "relative imports are forbidden; use absolute imports"),
        (9, "relative imports are forbidden; use absolute imports"),
        (10, "relative imports are forbidden; use absolute imports"),
    ], "positive constant integer levels must be rejected while bool, dynamic, and unsupported levels remain valid"


def test_relative_imports_are_checked_outside_policy_roots() -> None:
    """Relative imports remain checked for Python paths outside the four basic-policy roots."""
    source = dedent(
        """
        import importlib
        from .local import helper
        importlib.import_module("." + "helpers", package=__package__)
        assert value, f""
        """
    )

    violations = check_test_basics(file_path=Path("docs/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (3, "relative imports are forbidden; use absolute imports"),
        (4, "relative imports are forbidden; use absolute imports"),
    ], "constant relative imports should be checked while other basics remain scoped to policy roots"


def test_changes_filter_ignores_unchanged_basics_violations() -> None:
    """Added-line filtering leaves legacy violations untouched and reports new ones."""
    source = dedent(
        """
        assert legacy
        value == None
        """
    )

    assert check_test_basics(file_path=Path("tests/example.py"), source=source, added_lines={1}) == [], (
        "unchanged policy violations should not be reported for unrelated added lines"
    )
    added_violations = check_test_basics(
        file_path=Path("tests/example.py"),
        source=source,
        added_lines={3},
    )
    assert [(violation.line_number, violation.message) for violation in added_violations] == [
        (3, "test-basics: compare None with 'is' or 'is not', not == or !=")
    ], "a changed comparison should be reported when its line is added"


def test_async_comprehensions_are_rejected() -> None:
    """Async comprehensions are forbidden even when only their body line changed."""
    source = dedent(
        """
        async def fetch():
            return [value async for value in values]
        """
    )

    violations = check_test_basics(file_path=Path("tests/example.py"), source=source, added_lines={3})

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (3, "test-basics: async comprehensions are forbidden; use a synchronous comprehension")
    ], "async comprehensions must be checked independently of their async function header"


def test_local_time_class_does_not_activate_imported_time_sleep_rule() -> None:
    """A local class named time must not resolve as the imported time module."""
    source = dedent(
        """
        import time

        class time:
            pass

        time.sleep(1)
        """
    )

    assert check_test_basics(file_path=Path("tests/example.py"), source=source) == [], (
        "a local time class must not be mistaken for imported time.sleep"
    )


def test_non_policy_paths_are_ignored() -> None:
    """Source outside the checked repository roots is not subject to test-basics rules."""
    violations = check_test_basics(
        file_path=Path("docs/example.py"),
        source="assert value\n",
    )

    assert violations == [], "documentation snippets should retain their existing source policy behavior"


def test_requirement_markers_demand_special_infra() -> None:
    """Requirement markers without special_infra are rejected in test files."""
    source = dedent(
        """
        import pytest

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (4, "test-basics: marker sriov requires @pytest.mark.special_infra at module, class, or test level"),
    ], "requirement markers must be paired with special_infra"


def test_special_infra_marker_satisfies_the_requirement() -> None:
    """A module-level special_infra marker satisfies the requirement-marker policy."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "special_infra at module level satisfies the marker requirement"


def test_requirement_marker_outside_tests_root_is_not_flagged() -> None:
    """Requirement markers in non-test paths are not subject to the special_infra rule."""
    source = dedent(
        """
        import pytest

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("utilities/example.py"), source=source)

    assert violations == [], "the special_infra rule applies only to the tests directory"


def test_pre_existing_requirement_marker_is_not_flagged_without_added_lines() -> None:
    """Only newly added requirement markers are subject to the special_infra rule."""
    source = dedent(
        """
        import pytest

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(
        file_path=Path("tests/network/test_example.py"),
        source=source,
        added_lines=frozenset({5}),
    )

    assert violations == [], "legacy requirement markers must not block unrelated edits"


def test_special_infra_on_unrelated_test_does_not_satisfy_requirement() -> None:
    """A special_infra marker on a different test does not cover a requirement marker."""
    source = dedent(
        """
        import pytest

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"

        @pytest.mark.special_infra
        def test_unrelated_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (4, "test-basics: marker sriov requires @pytest.mark.special_infra at module, class, or test level"),
    ], "special_infra must cover the requirement marker's own test, class, or module scope"


def test_special_infra_on_enclosing_class_satisfies_requirement() -> None:
    """A class-level special_infra marker covers requirement markers on its tests."""
    source = dedent(
        """
        import pytest

        @pytest.mark.special_infra
        class TestSriov:
            @pytest.mark.sriov
            def test_sriov_feature(self):
                assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "class-level special_infra must cover the class's tests"


def test_special_infra_on_same_test_satisfies_requirement() -> None:
    """A test-level special_infra marker covers that test's requirement marker."""
    source = dedent(
        """
        import pytest

        @pytest.mark.special_infra
        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "test-level special_infra must cover that test's requirement markers"


def test_overwritten_pytestmark_does_not_satisfy_requirement() -> None:
    """An overwritten module-level special_infra marker no longer covers requirement markers."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra
        pytestmark = pytest.mark.smoke

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "only the effective (last) pytestmark assignment may satisfy the requirement"


def test_requirement_marker_alias_decorator_is_checked() -> None:
    """A requirement marker reached through an assigned alias is still checked."""
    source = dedent(
        """
        import pytest

        sriov_alias = pytest.mark.sriov

        @sriov_alias
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a requirement marker applied through an alias must still require special_infra"


def test_special_infra_alias_in_pytestmark_satisfies_requirement() -> None:
    """A module-level special_infra alias assigned to pytestmark covers requirement markers."""
    source = dedent(
        """
        import pytest

        special = pytest.mark.special_infra
        pytestmark = special

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "a special_infra alias in pytestmark must satisfy the marker requirement"


def test_special_infra_alias_decorator_satisfies_requirement() -> None:
    """A special_infra alias used as a decorator covers the decorated test."""
    source = dedent(
        """
        import pytest

        special = pytest.mark.special_infra

        @special
        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "a special_infra alias decorator must satisfy the marker requirement"


def test_conditional_pytestmark_reassignment_fails_closed() -> None:
    """A conditional pytestmark reassignment removes module-level marker coverage."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra
        if condition:
            pytestmark = pytest.mark.smoke

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "conditional pytestmark reassignment must fail closed for module-level coverage"


def test_conditional_pytestmark_value_does_not_satisfy_requirement() -> None:
    """A conditional module-level marker value provides no coverage."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra if condition else pytest.mark.smoke

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a conditional pytestmark value must not satisfy the marker requirement"


def test_conditional_decorator_does_not_satisfy_requirement() -> None:
    """A conditional decorator expression provides no coverage."""
    source = dedent(
        """
        import pytest

        special = pytest.mark.special_infra

        @(special if condition else pytest.mark.smoke)
        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a conditional decorator must not satisfy the marker requirement"


def test_alias_definition_is_not_flagged_when_application_is_covered() -> None:
    """An alias definition is not itself a requirement-marker application."""
    source = dedent(
        """
        import pytest

        sriov = pytest.mark.sriov
        special = pytest.mark.special_infra

        @special
        @sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "a covered alias application must not be flagged at its definition"


def test_augmented_pytestmark_satisfies_requirement() -> None:
    """An augmented module-level special_infra assignment covers requirement markers."""
    source = dedent(
        """
        import pytest

        pytestmark = []
        pytestmark += [pytest.mark.special_infra]

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "an augmented special_infra pytestmark must satisfy the marker requirement"


def test_walrus_pytestmark_mutation_fails_closed() -> None:
    """A walrus-operator pytestmark mutation drops module-level coverage."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra
        (pytestmark := pytest.mark.smoke)

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a walrus pytestmark mutation must fail closed for module-level coverage"


def test_deleted_pytestmark_fails_closed() -> None:
    """Deleting pytestmark drops module-level marker coverage."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra
        del pytestmark

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a deleted pytestmark must fail closed for module-level coverage"


def test_function_local_pytestmark_is_not_an_application() -> None:
    """A function-local pytestmark variable is not module marker metadata."""
    source = dedent(
        """
        import pytest

        def helper():
            pytestmark = pytest.mark.sriov
            return pytestmark

        @pytest.mark.smoke
        def test_unrelated():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "a function-local pytestmark variable must not be treated as an application"


def test_marker_nested_in_decorator_arguments_does_not_satisfy_requirement() -> None:
    """A marker passed as decorator data is not a direct application."""
    source = dedent(
        """
        import pytest

        @pytest.mark.parametrize("marker", [pytest.mark.special_infra])
        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a marker nested in decorator arguments must not satisfy the marker requirement"


def test_function_local_pytestmark_does_not_drop_module_coverage() -> None:
    """A function-local pytestmark variable does not invalidate module coverage."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra

        def helper():
            pytestmark = pytest.mark.smoke
            return pytestmark

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "a function-local pytestmark variable must not drop module-level coverage"


def test_match_case_pytestmark_application_is_checked() -> None:
    """A pytestmark assignment inside a match case is a marker application."""
    source = dedent(
        """
        import pytest

        match value:
            case 1:
                pytestmark = pytest.mark.sriov
            case _:
                pytestmark = pytest.mark.smoke

        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a pytestmark application inside a match case must require special_infra"


def test_try_star_pytestmark_application_is_checked() -> None:
    """A pytestmark assignment inside an except-star handler is a marker application."""
    source = dedent(
        """
        import pytest

        try:
            pass
        except* ValueError:
            pytestmark = pytest.mark.sriov

        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a pytestmark application inside an except-star handler must require special_infra"


def test_lambda_local_walrus_pytestmark_keeps_module_coverage() -> None:
    """A walrus inside a lambda is local and does not drop module coverage."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra
        callback = lambda: (pytestmark := pytest.mark.smoke)

        @pytest.mark.sriov
        def test_sriov_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "a lambda-local walrus must not drop module-level pytestmark coverage"


def test_requirement_marker_nested_in_decorator_arguments_is_not_applied() -> None:
    """A marker inside parametrize arguments is data, not an application."""
    source = dedent(
        """
        import pytest

        @pytest.mark.parametrize(argnames="mode", argvalues=[pytest.mark.sriov])
        def test_feature(mode):
            assert mode, "mode must be truthy"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations == [], "a marker nested in decorator arguments must not count as applied"


def test_destructured_pytestmark_assignment_is_an_application() -> None:
    """A tuple destructuring that binds pytestmark applies its markers."""
    source = dedent(
        """
        import pytest

        pytestmark, label = [pytest.mark.sriov, "network"]

        def test_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a destructuring assignment binding pytestmark must apply its markers"


def test_nested_destructured_pytestmark_mutation_fails_closed() -> None:
    """A control-flow destructuring binding pytestmark drops module coverage."""
    source = dedent(
        """
        import pytest

        pytestmark = pytest.mark.special_infra
        if value:
            pytestmark, label = [pytest.mark.smoke, "x"]

        @pytest.mark.sriov
        def test_feature():
            assert value, "value must be true"
        """
    )

    violations = check_test_basics(file_path=Path("tests/network/test_example.py"), source=source)

    assert violations, "a nested destructuring binding pytestmark must drop module coverage"
