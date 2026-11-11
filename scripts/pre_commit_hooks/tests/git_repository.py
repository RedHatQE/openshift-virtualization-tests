"""Shared helpers for pre-commit policy tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyhelper_utils.shell import run_command

if TYPE_CHECKING:
    from collections.abc import Collection


def initialize_git_repository(repository_root: Path) -> None:
    """Initialize a temporary repository with the identity required for commits."""
    run_command(command=["git", "init", "-q"], cwd=repository_root, check=True, verify_stderr=False)
    run_command(
        command=["git", "config", "commit.gpgsign", "false"],
        cwd=repository_root,
        check=True,
        verify_stderr=False,
    )
    run_command(
        command=["git", "config", "user.email", "test@example.com"],
        cwd=repository_root,
        check=True,
        verify_stderr=False,
    )
    run_command(
        command=["git", "config", "user.name", "Policy Test"],
        cwd=repository_root,
        check=True,
        verify_stderr=False,
    )
    manifest_path = repository_root / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if not manifest_path.exists():
        manifest_path.write_text(data="exceptions = []\n", encoding="utf-8")


def stage_paths(repository_root: Path, paths: Collection[str]) -> None:
    """Stage selected paths in a temporary repository."""
    run_command(command=["git", "add", *paths], cwd=repository_root, check=True, verify_stderr=False)


def commit_all(repository_root: Path, message: str = "baseline") -> None:
    """Stage the repository contents and create one temporary baseline commit."""
    stage_paths(repository_root=repository_root, paths=(".",))
    run_command(command=["git", "commit", "-qm", message], cwd=repository_root, check=True, verify_stderr=False)
