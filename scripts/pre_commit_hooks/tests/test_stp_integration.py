"""Integration tests for the stp-links check family."""

from __future__ import annotations

from json import dumps
from typing import TYPE_CHECKING

from scripts.pre_commit_hooks import check_policy
from scripts.pre_commit_hooks.check_policy import main
from scripts.pre_commit_hooks.tests.git_repository import commit_all, initialize_git_repository, stage_paths

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch

_MERGED_PATH = "stps/sig-network/EVPN.md"
_UNMERGED_URL = (
    "https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/missing.md"
)
_TEST_SOURCE = f'''"""STP: {_UNMERGED_URL}"""


def test_feature():
    """Feature scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
    assert value, "value must be true"
'''


def _fake_design_docs_tree(monkeypatch: MonkeyPatch, merged_paths: tuple[str, ...]) -> None:
    """Intercept the design-docs tree request while delegating git commands."""
    original_git_output = check_policy._git_output

    def git_output(command: list[str]) -> str:
        if command[0] == "gh":
            return dumps(obj={"truncated": False, "tree": [{"path": path} for path in merged_paths]})
        return original_git_output(command=command)

    monkeypatch.setattr(target=check_policy, name="_git_output", value=git_output)


def _stage_stp_test_file(repository_root: Path) -> None:
    """Commit a baseline, then stage a new test file with an unmerged STP reference."""
    commit_all(repository_root=repository_root)
    test_path = repository_root / "tests/network/test_example.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(data=_TEST_SOURCE, encoding="utf-8")
    stage_paths(repository_root=repository_root, paths=("tests/network/test_example.py",))


def test_main_rejects_stp_link_not_merged(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A staged STP reference to an unmerged document fails policy."""
    initialize_git_repository(repository_root=tmp_path)
    _stage_stp_test_file(repository_root=tmp_path)
    _fake_design_docs_tree(monkeypatch=monkeypatch, merged_paths=(_MERGED_PATH,))
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["tests/network/test_example.py"]) == 1, "an unmerged STP reference must fail policy"


def test_main_accepts_merged_stp_link(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A staged STP reference to a merged document passes policy."""
    initialize_git_repository(repository_root=tmp_path)
    _stage_stp_test_file(repository_root=tmp_path)
    _fake_design_docs_tree(monkeypatch=monkeypatch, merged_paths=("stps/sig-storage/missing.md",))
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["tests/network/test_example.py"]) == 0, "a merged STP reference must pass policy"


def test_main_stp_links_family_selected_alone(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Only the selected check family verifies STP links."""
    initialize_git_repository(repository_root=tmp_path)
    _stage_stp_test_file(repository_root=tmp_path)
    _fake_design_docs_tree(monkeypatch=monkeypatch, merged_paths=(_MERGED_PATH,))
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["--check", "stp-links", "tests/network/test_example.py"]) == 1, (
        "the stp-links family must reject the unmerged reference on its own"
    )
    assert main(arguments=["--check", "test-std", "tests/network/test_example.py"]) == 0, (
        "the test-std family must not verify STP links"
    )


def test_main_stp_links_fails_closed_when_tree_cannot_be_fetched(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A failed design-docs tree request rejects the file instead of passing it."""
    initialize_git_repository(repository_root=tmp_path)
    _stage_stp_test_file(repository_root=tmp_path)
    original_git_output = check_policy._git_output

    def failing_git_output(command: list[str]) -> str:
        if command[0] == "gh":
            raise RuntimeError("gh command failed: gh: not authenticated")
        return original_git_output(command=command)

    monkeypatch.setattr(target=check_policy, name="_git_output", value=failing_git_output)
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["--check", "stp-links", "tests/network/test_example.py"]) == 1, (
        "an unverifiable STP reference must fail closed"
    )


def test_main_stp_links_skips_fetch_without_references(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """No design-docs request is made when no staged file carries STP references."""
    initialize_git_repository(repository_root=tmp_path)
    source_path = tmp_path / "tests/network/test_plain.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    commit_all(repository_root=tmp_path)
    source_path.write_text(
        data='"""Plain source."""\n\n\ndef test_feature():\n    assert value, "value must be true"\n',
        encoding="utf-8",
    )
    stage_paths(repository_root=tmp_path, paths=("tests/network/test_plain.py",))
    original_git_output = check_policy._git_output

    def unexpected_git_output(command: list[str]) -> str:
        if command[0] == "gh":
            raise AssertionError("no design-docs fetch should run without STP references")
        return original_git_output(command=command)

    monkeypatch.setattr(target=check_policy, name="_git_output", value=unexpected_git_output)
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["--check", "stp-links", "tests/network/test_plain.py"]) == 0, (
        "no fetch is made and the check passes without STP references"
    )


def test_main_stp_links_ignores_non_test_paths(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """STP references outside tests/ are tooling fixtures and are not verified."""
    initialize_git_repository(repository_root=tmp_path)
    commit_all(repository_root=tmp_path)
    tooling_path = tmp_path / "scripts/pre_commit_hooks/tests/test_fixture.py"
    tooling_path.parent.mkdir(parents=True, exist_ok=True)
    tooling_path.write_text(data=f'_UNMERGED_URL = "{_UNMERGED_URL}"\n', encoding="utf-8")
    stage_paths(repository_root=tmp_path, paths=("scripts/pre_commit_hooks/tests/test_fixture.py",))

    def unexpected_git_output(command: list[str]) -> str:
        if command[0] == "gh":
            raise AssertionError("tooling fixture URLs must not trigger a design-docs fetch")
        return original_git_output(command=command)

    original_git_output = check_policy._git_output
    monkeypatch.setattr(target=check_policy, name="_git_output", value=unexpected_git_output)
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["--check", "stp-links", "scripts/pre_commit_hooks/tests/test_fixture.py"]) == 0, (
        "STP references outside tests/ must not be verified"
    )


def test_main_stp_links_fails_closed_on_malformed_tree_response(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A non-JSON design-docs response fails closed with the documented message."""
    initialize_git_repository(repository_root=tmp_path)
    _stage_stp_test_file(repository_root=tmp_path)
    original_git_output = check_policy._git_output

    def malformed_git_output(command: list[str]) -> str:
        if command[0] == "gh":
            return "<html>gateway error</html>"
        return original_git_output(command=command)

    monkeypatch.setattr(target=check_policy, name="_git_output", value=malformed_git_output)
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["--check", "stp-links", "tests/network/test_example.py"]) == 1, (
        "a malformed design-docs response must fail closed, not crash"
    )


def test_main_stp_links_fails_closed_on_missing_tree_key(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A design-docs response without a tree listing fails closed."""
    initialize_git_repository(repository_root=tmp_path)
    _stage_stp_test_file(repository_root=tmp_path)
    original_git_output = check_policy._git_output

    def keyless_git_output(command: list[str]) -> str:
        if command[0] == "gh":
            return '{"message": "Not Found"}'
        return original_git_output(command=command)

    monkeypatch.setattr(target=check_policy, name="_git_output", value=keyless_git_output)
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["--check", "stp-links", "tests/network/test_example.py"]) == 1, (
        "a response without a tree listing must fail closed, not crash"
    )
