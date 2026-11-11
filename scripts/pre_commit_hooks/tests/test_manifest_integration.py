"""Integration tests for staged exception-manifest handling."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyhelper_utils.shell import run_command

from scripts.pre_commit_hooks.check_linter_directives import compute_source_fingerprint
from scripts.pre_commit_hooks.check_policy import main
from scripts.pre_commit_hooks.tests.git_repository import commit_all, initialize_git_repository, stage_paths

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def _policy_hook_blocks() -> list[str]:
    """Return the local policy hook definition blocks."""
    config_path = Path(__file__).parents[3] / ".pre-commit-config.yaml"
    config = config_path.read_text(encoding="utf-8")
    local_hooks = config.split("  - repo: local", maxsplit=1)[1]
    return [block for block in local_hooks.split("      - id: ")[1:] if block.startswith("check-")]


def test_policy_hooks_always_run_without_selected_files() -> None:
    """Every policy hook must run when pre-commit supplies no filenames."""
    hook_blocks = _policy_hook_blocks()

    assert hook_blocks, "the local policy hooks must be defined"
    for hook_block in hook_blocks:
        assert "always_run: true" in hook_block, "policy hooks must run for manifest-only staged deletions"


def test_policy_hooks_require_serial_execution() -> None:
    """Every policy hook must serialize status and diff parsing."""
    hook_blocks = _policy_hook_blocks()

    assert hook_blocks, "the local policy hooks must be defined"
    for hook_block in hook_blocks:
        assert "require_serial: true" in hook_block, "policy hook status and diff parsing must run serially"


def test_main_accepts_exception_manifest_only_cleanup(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Removing an obsolete exception is allowed without a Python path argument."""
    initialize_git_repository(repository_root=tmp_path)
    manifest_path = tmp_path / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        data="""[[exceptions]]
rule = "noqa"
path = "utilities/generated.py"
directive = "# noqa: E501"
source_fingerprint = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
reason = "obsolete generated source"
approval_url = "https://github.com/example/review/4"
""",
        encoding="utf-8",
    )
    commit_all(repository_root=tmp_path)

    manifest_path.write_text(data="exceptions = []\n", encoding="utf-8")
    stage_paths(repository_root=tmp_path, paths=("scripts/pre_commit_hooks/exceptions.toml",))
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["README.md"]) == 0, "removing an obsolete exception record should pass manifest policy"


def test_main_rejects_malformed_manifest_deleted_with_no_selected_paths(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Deleting the only malformed manifest must not silently bypass manifest policy."""
    initialize_git_repository(repository_root=tmp_path)
    manifest_path = tmp_path / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(data="not valid = [\n", encoding="utf-8")
    commit_all(repository_root=tmp_path)
    manifest_path.unlink()
    stage_paths(repository_root=tmp_path, paths=("scripts/pre_commit_hooks/exceptions.toml",))
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=[]) == 1, "a deleted malformed manifest should return a policy failure"


def test_main_rejects_renamed_exception_manifest_as_manifest_deletion(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Renaming the manifest away from its required path must be rejected."""
    initialize_git_repository(repository_root=tmp_path)
    manifest_path = tmp_path / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(data="exceptions = []\n", encoding="utf-8")
    commit_all(repository_root=tmp_path)
    renamed_path = manifest_path.with_name("exceptions-renamed.toml")
    run_command(
        command=["git", "mv", str(manifest_path.relative_to(tmp_path)), str(renamed_path.relative_to(tmp_path))],
        cwd=tmp_path,
        check=True,
        verify_stderr=False,
    )
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=[]) == 1, "a renamed exception manifest must be treated as deletion of the required file"


def test_main_rejects_new_exception_without_new_staged_directive(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A new manifest record must authorize a directive introduced in the same staged change."""
    initialize_git_repository(repository_root=tmp_path)
    source_path = tmp_path / "utilities/example.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(data="value = 1\n", encoding="utf-8")
    commit_all(repository_root=tmp_path)

    manifest_path = tmp_path / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.write_text(
        data="""[[exceptions]]
rule = "noqa"
path = "utilities/example.py"
directive = "# noqa: E123"
source_fingerprint = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
reason = "generated source"
approval_url = "https://github.com/example/review/7"
""",
        encoding="utf-8",
    )
    stage_paths(repository_root=tmp_path, paths=("scripts/pre_commit_hooks/exceptions.toml",))
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=[]) == 1, "orphaned new exception records must fail policy"


def test_main_accepts_new_exception_with_matching_staged_directive(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A directive and its reviewed exception record may be introduced together."""
    initialize_git_repository(repository_root=tmp_path)
    source_path = tmp_path / "utilities/example.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(data="value = 1\n", encoding="utf-8")
    commit_all(repository_root=tmp_path)

    staged_source = "value = 1  # noqa: E123\n"
    source_path.write_text(data=staged_source, encoding="utf-8")
    fingerprint = compute_source_fingerprint(source=staged_source, line_number=1, directive="# noqa: E123")
    manifest_path = tmp_path / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.write_text(
        data=f'''[[exceptions]]
rule = "noqa"
path = "utilities/example.py"
directive = "# noqa: E123"
source_fingerprint = "{fingerprint}"
reason = "generated source"
approval_url = "https://github.com/example/review/8"
''',
        encoding="utf-8",
    )
    stage_paths(
        repository_root=tmp_path,
        paths=("utilities/example.py", "scripts/pre_commit_hooks/exceptions.toml"),
    )
    monkeypatch.chdir(path=tmp_path)

    assert main(arguments=["utilities/example.py"]) == 0, "a matching same-commit exception should pass policy"
