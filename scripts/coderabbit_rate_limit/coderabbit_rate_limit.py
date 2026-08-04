"""CodeRabbit rate limit handler — thin wrapper around myk-pi-tools.

CLI tool to detect and handle CodeRabbit rate limiting on pull requests.
Delegates to myk_pi_tools.coderabbit for all logic.

Usage:
    uv run coderabbit-rate-limit check RedHatQE/openshift-virtualization-tests 5869
    uv run coderabbit-rate-limit trigger RedHatQE/openshift-virtualization-tests 5869 --wait 330
    uv run coderabbit-rate-limit resume RedHatQE/openshift-virtualization-tests 5869
"""

from __future__ import annotations

import sys
from json import JSONDecodeError, loads

import click
from myk_pi_tools.coderabbit.rate_limit import run_check, run_trigger
from myk_pi_tools.coderabbit.utils import run_gh, validate_owner_repo
from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)


def _run_resume(owner_repo: str, pr_number: int) -> int:
    """Resume paused CodeRabbit reviews on a PR.

    Args:
        owner_repo: Repository in 'owner/repo' format.
        pr_number: Pull request number.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    if not validate_owner_repo(owner_repo=owner_repo):
        return 1

    owner, repo = owner_repo.split("/")
    LOGGER.info("Posting @coderabbitai resume...")
    exit_code, stdout, stderr = run_gh(
        args=[
            "api",
            f"repos/{owner}/{repo}/issues/{pr_number}/comments",
            "-f",
            "body=@coderabbitai resume",
        ],
        timeout=30,
    )
    if exit_code != 0:
        LOGGER.error(f"Failed to post resume trigger: {stderr}")
        return 1

    try:
        comment_id = loads(stdout).get("id")
    except JSONDecodeError:
        comment_id = None
    except AttributeError:
        comment_id = None

    LOGGER.info(f"Resume trigger posted (comment ID: {comment_id}).")
    return 0


@click.group()
def main() -> None:
    """CodeRabbit rate limit handler."""


@main.command("check")
@click.argument("owner_repo")
@click.argument("pr_number", type=int)
def check_command(owner_repo: str, pr_number: int) -> None:
    """Check if CodeRabbit is rate limited or reviews are paused on a PR.

    Outputs JSON to stdout with rate limit status and wait time.
    """
    sys.exit(run_check(owner_repo=owner_repo, pr_number=pr_number))


@main.command("trigger")
@click.argument("owner_repo")
@click.argument("pr_number", type=int)
@click.option(
    "--wait",
    "wait_seconds",
    type=click.IntRange(min=0),
    default=0,
    help="Seconds to wait before posting review trigger.",
)
def trigger_command(owner_repo: str, pr_number: int, wait_seconds: int) -> None:
    """Wait and trigger a CodeRabbit review on a PR.

    Waits the specified duration, posts @coderabbitai review,
    then polls until the review starts (max 10 minutes).
    """
    sys.exit(run_trigger(owner_repo=owner_repo, pr_number=pr_number, wait_seconds=wait_seconds))


@main.command("resume")
@click.argument("owner_repo")
@click.argument("pr_number", type=int)
def resume_command(owner_repo: str, pr_number: int) -> None:
    """Resume paused CodeRabbit reviews on a PR.

    Posts @coderabbitai resume to unblock paused reviews.
    """
    sys.exit(_run_resume(owner_repo=owner_repo, pr_number=pr_number))
