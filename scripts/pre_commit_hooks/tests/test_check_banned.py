"""Unit tests for the stateless whole-file banned-policy checks."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scripts.pre_commit_hooks.check_banned import (
    banned_construct_violations,
    banned_path_violations,
    main,
)
from scripts.pre_commit_hooks.check_linter_directives import EXCEPTIONS_PATH


def test_top_level_test_module_is_banned() -> None:
    """Test modules placed directly under tests/ are rejected."""
    violations = banned_path_violations(file_path=Path("tests/test_example.py"))

    assert len(violations) == 1, "the top-level test module is rejected"
    assert "feature subdirectory" in violations[0].message, "the rejection names the required placement"


def test_top_level_test_module_suffix_variant_is_banned() -> None:
    """The *_test.py naming variant is rejected like the test_ prefix."""
    violations = banned_path_violations(file_path=Path("tests/example_test.py"))

    assert len(violations) == 1, "the suffix naming variant is rejected"


def test_feature_subdirectory_test_module_is_allowed() -> None:
    """Test modules inside a feature subdirectory pass."""
    assert banned_path_violations(file_path=Path("tests/network/test_example.py")) == [], (
        "feature subdirectory test modules pass"
    )


def test_non_test_top_level_module_is_allowed() -> None:
    """Non-test modules directly under tests/ pass."""
    assert banned_path_violations(file_path=Path("tests/conftest.py")) == [], "non-test top-level modules pass"


def test_python_symlink_is_banned(tmp_path: Path) -> None:
    """Symlinked Python files are rejected."""
    real_file = tmp_path / "real_module.py"
    real_file.write_text(encoding="utf-8", data="VALUE = 1\n")
    symlinked = tmp_path / "utilities" / "linked_module.py"
    symlinked.parent.mkdir()
    symlinked.symlink_to(real_file)

    violations = banned_path_violations(file_path=symlinked)

    assert len(violations) == 1, "the symlinked Python file is rejected"
    assert "Python symlinks are not allowed" in violations[0].message, "the rejection names the symlink rule"


def test_symlinked_exception_manifest_is_banned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A symlinked exception manifest is rejected."""
    monkeypatch.chdir(tmp_path)
    real_manifest = tmp_path / "real_manifest.toml"
    real_manifest.write_text(encoding="utf-8", data="exceptions = []\n")
    manifest_directory = tmp_path / "scripts" / "pre_commit_hooks"
    manifest_directory.mkdir(parents=True)
    (tmp_path / EXCEPTIONS_PATH).symlink_to(real_manifest)

    violations = banned_path_violations(file_path=EXCEPTIONS_PATH)

    assert len(violations) == 1, "the symlinked manifest is rejected"
    assert "exception manifest must be a real file" in violations[0].message, "the rejection names the manifest rule"


def test_real_python_file_is_not_reported_as_symlink(tmp_path: Path) -> None:
    """A regular Python file raises no path violations."""
    real_file = tmp_path / "utilities" / "module.py"
    real_file.parent.mkdir()
    real_file.write_text(encoding="utf-8", data="VALUE = 1\n")

    assert banned_path_violations(file_path=real_file) == [], "regular Python files raise no path violations"


def test_relative_import_is_banned() -> None:
    """Relative imports are rejected in the whole-file flow."""
    source = dedent(
        """
        from . import sibling
        """
    )

    violations = banned_construct_violations(file_path=Path("tests/network/test_example.py"), source=source)

    assert [violation.message for violation in violations] == [
        "relative imports are forbidden; use absolute imports"
    ], "relative imports are rejected"


def test_absolute_import_is_allowed() -> None:
    """Absolute imports pass."""
    source = dedent(
        """
        from utilities import network
        """
    )

    assert banned_construct_violations(file_path=Path("tests/network/test_example.py"), source=source) == [], (
        "absolute imports pass"
    )


def test_relative_dynamic_import_is_banned() -> None:
    """Relative dynamic imports are rejected in the whole-file flow."""
    source = dedent(
        """
        from importlib import import_module

        sibling = import_module(".sibling")
        """
    )

    violations = banned_construct_violations(file_path=Path("tests/network/test_example.py"), source=source)

    assert len(violations) == 1, "the relative dynamic import is rejected"
    assert violations[0].message == "relative imports are forbidden; use absolute imports", (
        "the rejection names the relative import rule"
    )


def test_async_function_is_banned() -> None:
    """Async function definitions are rejected in the whole-file flow."""
    source = dedent(
        """
        async def fetch_value():
            return 1
        """
    )

    violations = banned_construct_violations(file_path=Path("tests/network/test_example.py"), source=source)

    assert [violation.message for violation in violations] == [
        "test-basics: async functions are forbidden; use synchronous code"
    ], "async function definitions are rejected"


def test_dynamic_client_construction_is_banned() -> None:
    """Direct DynamicClient construction is rejected in the whole-file flow."""
    source = dedent(
        """
        from kubernetes.dynamic import DynamicClient

        client = DynamicClient()
        """
    )

    violations = banned_construct_violations(file_path=Path("utilities/virt.py"), source=source)

    assert [violation.message for violation in violations] == [
        "reuse the DynamicClient passed through the call path instead of constructing one"
    ], "direct DynamicClient construction is rejected"


def test_dynamic_client_alias_construction_is_banned() -> None:
    """Aliased DynamicClient construction is still rejected."""
    source = dedent(
        """
        from kubernetes.dynamic import DynamicClient as Client

        client = Client()
        """
    )

    violations = banned_construct_violations(file_path=Path("utilities/virt.py"), source=source)

    assert len(violations) == 1, "aliased DynamicClient construction is rejected"


def test_ratcheted_rules_are_not_reported_in_whole_file_flow() -> None:
    """Staged-only rules stay out of the whole-file flow.

    time.sleep replacement and descriptive assert messages are ratcheted
    against added lines, so pre-existing occurrences must not be flagged
    when the whole file is checked.
    """
    source = dedent(
        """
        import time

        def probe_value():
            time.sleep(1)
            assert probe_value()
        """
    )

    assert banned_construct_violations(file_path=Path("tests/network/test_example.py"), source=source) == [], (
        "ratcheted rules stay out of the whole-file flow"
    )


def test_main_returns_zero_for_compliant_file(tmp_path: Path) -> None:
    """A compliant Python file exits zero."""
    compliant = tmp_path / "test_example.py"
    compliant.write_text(encoding="utf-8", data="from utilities import network\n")

    assert main(arguments=["--check", "banned-constructs", str(compliant)]) == 0, "a compliant Python file exits zero"


def test_main_returns_one_for_banned_construct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A violating Python file exits one and reports the violation."""
    monkeypatch.chdir(tmp_path)
    violating = tmp_path / "tests" / "test_example.py"
    violating.parent.mkdir()
    violating.write_text(encoding="utf-8", data="async def fetch_value():\n    return 1\n")

    assert main(arguments=["--check", "banned-constructs", "tests/test_example.py"]) == 1, (
        "a violating Python file exits one"
    )


def test_main_reports_unreadable_file(tmp_path: Path) -> None:
    """An unreadable Python path fails closed."""
    unreadable = tmp_path / "directory.py"
    unreadable.mkdir()

    assert main(arguments=["--check", "banned-constructs", str(unreadable)]) == 1, (
        "an unreadable Python path fails closed"
    )


def test_main_reports_unparsable_file(tmp_path: Path) -> None:
    """A Python file with a syntax error fails closed."""
    unparsable = tmp_path / "test_example.py"
    unparsable.write_text(encoding="utf-8", data="def broken(:\n")

    assert main(arguments=["--check", "banned-constructs", str(unparsable)]) == 1, (
        "an unparsable Python file fails closed"
    )


def test_main_reports_unparsable_file_line_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The syntax-error violation carries the offending line number."""
    unparsable = tmp_path / "test_example.py"
    unparsable.write_text(encoding="utf-8", data="VALUE = 1\ndef broken(:\n")

    main(arguments=["--check", "banned-constructs", str(unparsable)])

    captured = capsys.readouterr()
    assert ":2: could not be parsed" in captured.err, "the syntax-error violation carries the offending line number"


def test_main_check_selection_limits_families(tmp_path: Path) -> None:
    """Selecting banned-paths does not run the constructs family."""
    violating = tmp_path / "test_example.py"
    violating.write_text(encoding="utf-8", data="from . import sibling\n")

    assert main(arguments=["--check", "banned-paths", str(violating)]) == 0, "the paths family does not check imports"
    assert main(arguments=["--check", "banned-constructs", str(violating)]) == 1, "the constructs family checks imports"


def test_main_without_selection_runs_every_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --check every family runs."""
    monkeypatch.chdir(tmp_path)
    top_level_test = tmp_path / "tests" / "test_example.py"
    top_level_test.parent.mkdir()
    top_level_test.write_text(encoding="utf-8", data="from . import sibling\n")

    assert main(arguments=["tests/test_example.py"]) == 1, "every family runs without a selection"
    captured = capsys.readouterr()
    assert "feature subdirectory" in captured.err, "the paths family runs without a selection"
    assert "relative imports are forbidden" in captured.err, "the constructs family runs without a selection"


def test_main_rejects_unknown_check_family() -> None:
    """An unknown check family is a usage error."""
    with pytest.raises(SystemExit, match="unknown check family"):
        main(arguments=["--check", "banned-nothing", "tests/test_example.py"])


def test_main_rejects_check_without_family_name() -> None:
    """A trailing --check without a family name is a usage error."""
    with pytest.raises(SystemExit, match="requires a check family name"):
        main(arguments=["--check"])
