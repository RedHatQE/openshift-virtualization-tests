#!/usr/bin/env python3
"""Retry CodeRabbit reviews that hit rate limits.

Scans open, non-draft, non-WIP, non-stale, non-conflicting PRs (updated in the
last 2 days) for CodeRabbit rate-limit comments and re-triggers review once the
wait period has elapsed.

Intended to be invoked from GitHub Actions with env vars::

    REPO=owner/repo GH_TOKEN=... uv run python3 scripts/coderabbit_retry/coderabbit_retry.py

Local usage (requires ``uv`` and ``myk-pi-tools`` on PATH; ``gh`` optional for token)::

    REPO=owner/repo GH_TOKEN=$(gh auth token) \\
        uv run python3 scripts/coderabbit_retry/coderabbit_retry.py

Safety limits:
    - Processes eligible PRs concurrently (``MAX_WORKERS`` threads)
    - Skips PRs where ``@coderabbitai review`` or ``resume`` was already posted
    - Per-PR API/parse failures are logged and skipped (fail-safe)

Dependencies:
    - ``PyGithub``: GitHub API interactions (resolved via ``uv run``)
    - ``myk-pi-tools``: rate-limit detection CLI (installed separately)

Co-authored-by: Claude <noreply@anthropic.com>
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from itertools import islice
from json import JSONDecodeError
from json import loads as json_loads
from math import isfinite
from os import environ
from re import IGNORECASE
from re import compile as re_compile
from subprocess import TimeoutExpired
from subprocess import run as subprocess_run
from time import time as time_time
from typing import TYPE_CHECKING

from github import Auth, Github, GithubException
from simple_logger.logger import get_logger

if TYPE_CHECKING:
    from typing import Any

    from github.Issue import Issue
    from github.Repository import Repository

LOGGER = get_logger(name=__name__)

MAX_PRS = 200
SINCE_DAYS = 2
SUBPROCESS_TIMEOUT_SECONDS = 30
MAX_WORKERS = 5

REVIEW_REQUEST_PATTERN = re_compile(
    pattern=r"@coderabbitai\s+(review|resume)",
    flags=IGNORECASE,
)
WIP_PATTERN = re_compile(
    pattern=r"\bwip\b|\[wip\]",
    flags=IGNORECASE,
)


def is_wip_title(title: str) -> bool:
    """Return True if the PR title indicates a work-in-progress change."""
    return bool(WIP_PATTERN.search(string=title))


def list_eligible_prs(github_client: Github, repo_name: str) -> list[Issue]:
    """List open PRs eligible for rate-limit retry via GitHub search API.

    Args:
        github_client: Authenticated GitHub client.
        repo_name: Repository in ``owner/repo`` format.

    Returns:
        List of matching Issue objects (PRs), capped at ``MAX_PRS``.
    """
    since_date = (datetime.now(tz=UTC) - timedelta(days=SINCE_DAYS)).strftime(format="%Y-%m-%d")
    query = (
        f"repo:{repo_name} is:pr is:open draft:false "
        f"-label:Stale -label:wip -label:has-conflicts "
        f"updated:>={since_date}"
    )
    LOGGER.info(f"Searching PRs: {query}")
    return list(islice(github_client.search_issues(query=query, sort="updated", order="desc"), MAX_PRS))


def _validate_rate_limit_payload(payload: dict[str, Any], pr_number: int) -> dict[str, Any] | None:
    """Validate rate-limit payload field types.

    Args:
        payload: Parsed JSON dict from ``myk-pi-tools``.
        pr_number: PR number for log context.

    Returns:
        The payload if valid, ``None`` otherwise.
    """
    rate_limited = payload.get("rate_limited")
    wait_seconds = payload.get("wait_seconds")
    updated_at = payload.get("updated_at")

    if rate_limited is not None and not isinstance(rate_limited, bool):
        LOGGER.warning(f"PR #{pr_number}: unexpected rate_limited type: {type(rate_limited).__name__}")
        return None
    if wait_seconds is not None and (
        isinstance(wait_seconds, bool)
        or not isinstance(wait_seconds, (int, float))
        or not isfinite(wait_seconds)
        or wait_seconds < 0
    ):
        LOGGER.warning(f"PR #{pr_number}: invalid wait_seconds: {wait_seconds!r}")
        return None
    if updated_at is not None and not isinstance(updated_at, str):
        LOGGER.warning(f"PR #{pr_number}: unexpected updated_at type: {type(updated_at).__name__}")
        return None
    return payload


def check_rate_limit(repo_name: str, pr_number: int) -> dict[str, Any] | None:
    """Check whether a PR has a CodeRabbit rate-limit comment via myk-pi-tools CLI.

    Args:
        repo_name: Repository in ``owner/repo`` format.
        pr_number: Pull request number.

    Returns:
        Validated JSON dict with type-checked keys ``rate_limited``
        (bool), ``wait_seconds`` (non-negative finite int/float), and
        ``updated_at`` (str); keys may be absent or ``None``. Returns
        ``None`` on failure or invalid field types.
    """
    try:
        result = subprocess_run(
            args=["myk-pi-tools", "coderabbit", "check", repo_name, str(pr_number)],
            capture_output=True,
            text=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, TimeoutExpired) as error:
        LOGGER.warning(f"PR #{pr_number}: rate-limit check failed: {error}")
        return None

    if result.returncode != 0:
        LOGGER.warning(f"PR #{pr_number}: rate-limit check exited {result.returncode}: {result.stderr.strip()}")
        return None

    try:
        payload = json_loads(s=result.stdout)
    except JSONDecodeError as error:
        LOGGER.warning(f"PR #{pr_number}: failed to parse rate-limit JSON: {error}")
        return None

    if not isinstance(payload, dict):
        LOGGER.warning(f"PR #{pr_number}: rate-limit payload is not a dict")
        return None

    return _validate_rate_limit_payload(payload=payload, pr_number=pr_number)


def has_review_request_after(repo: Repository, pr_number: int, after_epoch: float) -> bool | None:
    """Check whether a review/resume request was posted after a timestamp.

    Args:
        repo: GitHub Repository object.
        pr_number: Pull request number.
        after_epoch: Epoch seconds threshold.

    Returns:
        ``True`` if found, ``False`` if not, ``None`` on API failure.
    """
    since_dt = datetime.fromtimestamp(after_epoch, tz=UTC)
    try:
        for comment in repo.get_issue(number=pr_number).get_comments(since=since_dt):
            if comment.user and comment.user.login == "coderabbitai[bot]":
                continue
            if REVIEW_REQUEST_PATTERN.search(string=comment.body or ""):
                if comment.created_at.replace(tzinfo=UTC).timestamp() > after_epoch:
                    return True
    except GithubException as error:
        LOGGER.warning(f"PR #{pr_number}: failed to fetch comments: {error}")
        return None
    return False


def trigger_review(repo: Repository, pr_number: int) -> bool:
    """Post ``@coderabbitai review`` on a PR.

    Args:
        repo: GitHub Repository object.
        pr_number: Pull request number.

    Returns:
        ``True`` if posted, ``False`` on failure.
    """
    try:
        repo.get_issue(number=pr_number).create_comment(body="@coderabbitai review")
        return True
    except GithubException as error:
        LOGGER.warning(f"PR #{pr_number}: failed to trigger review: {error}")
        return False


def process_pr(repo_name: str, repo: Repository, pr_number: int) -> bool:
    """Evaluate a PR and trigger a review retry if the rate-limit wait has elapsed.

    Args:
        repo_name: Repository in ``owner/repo`` format.
        repo: GitHub Repository object.
        pr_number: Pull request number.

    Returns:
        ``True`` if a review was triggered, ``False`` otherwise.
    """
    LOGGER.info(f"=== PR #{pr_number} ===")
    check_result = check_rate_limit(repo_name=repo_name, pr_number=pr_number)
    if check_result is None or not check_result.get("rate_limited"):
        if check_result is not None:
            LOGGER.info(f"PR #{pr_number}: not rate limited")
        return False

    wait_seconds = check_result.get("wait_seconds")
    updated_at = check_result.get("updated_at")
    if wait_seconds is None or not updated_at:
        LOGGER.warning(f"PR #{pr_number}: rate-limited but missing wait_seconds or updated_at")
        return False

    try:
        updated_at_epoch = datetime.fromisoformat(updated_at).timestamp()
    except ValueError:
        LOGGER.warning(f"PR #{pr_number}: unparseable updated_at: {updated_at!r}")
        return False

    elapsed = time_time() - updated_at_epoch
    if elapsed < wait_seconds:
        LOGGER.info(f"PR #{pr_number}: wait not elapsed ({int(wait_seconds - elapsed)}s remaining)")
        return False

    review_check = has_review_request_after(repo=repo, pr_number=pr_number, after_epoch=updated_at_epoch)
    if review_check is None:
        LOGGER.warning(f"PR #{pr_number}: review check failed — skipping")
        return False
    if review_check:
        LOGGER.info(f"PR #{pr_number}: review already requested — skipping")
        return False

    LOGGER.info(f"PR #{pr_number}: triggering review...")
    if not trigger_review(repo=repo, pr_number=pr_number):
        return False

    LOGGER.info(f"PR #{pr_number}: review triggered")
    return True


def main() -> int:
    """Scan eligible PRs and retry rate-limited CodeRabbit reviews.

    Returns:
        ``0`` on success, ``1`` on missing env vars, repo access failure,
        or PR list failure.
    """
    repo_name = environ.get("REPO")
    if not repo_name:
        LOGGER.error("REPO environment variable is required (owner/repo)")
        return 1

    token = environ.get("GH_TOKEN")
    if not token:
        LOGGER.error("GH_TOKEN environment variable is required")
        return 1

    github_client = Github(auth=Auth.Token(token=token))
    try:
        repo = github_client.get_repo(full_name_or_id=repo_name)
    except GithubException as error:
        LOGGER.error(f"Failed to access repo {repo_name}: {error}")
        return 1

    try:
        pull_requests = list_eligible_prs(github_client=github_client, repo_name=repo_name)
    except GithubException as error:
        LOGGER.error(f"Failed to search PRs: {error}")
        return 1

    LOGGER.info(f"Found {len(pull_requests)} eligible PR(s)")
    skipped = 0
    to_process: list[Issue] = []
    for pr_issue in pull_requests:
        if is_wip_title(title=pr_issue.title):
            LOGGER.info(f"PR #{pr_issue.number}: skipping WIP")
            skipped += 1
            continue
        to_process.append(pr_issue)

    checked = len(to_process)
    retried = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_pr = {
            executor.submit(
                process_pr,
                repo_name=repo_name,
                repo=repo,
                pr_number=pr_issue.number,
            ): pr_issue.number
            for pr_issue in to_process
        }
        for future in as_completed(fs=future_to_pr):
            pr_number = future_to_pr[future]
            try:
                if future.result():
                    retried += 1
            except GithubException as error:
                LOGGER.warning(f"PR #{pr_number}: processing failed: {error}")

    LOGGER.info(f"Summary: checked={checked} skipped={skipped} retried={retried}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
