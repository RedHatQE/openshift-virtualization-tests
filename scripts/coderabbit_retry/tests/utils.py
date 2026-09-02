from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock


def make_completed_process(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    """Create a mock subprocess CompletedProcess.

    Args:
        returncode: Process exit code.
        stdout: Standard output.
        stderr: Standard error.

    Returns:
        MagicMock configured as a CompletedProcess.
    """
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def make_comment(login: str = "human", body: str | None = "", created_at: str = "2026-08-05T10:00:00Z") -> MagicMock:
    """Create a mock GitHub IssueComment.

    Args:
        login: Comment author login.
        body: Comment body text.
        created_at: ISO 8601 timestamp.

    Returns:
        MagicMock configured as an IssueComment.
    """
    comment = MagicMock()
    comment.user = MagicMock()
    comment.user.login = login
    comment.body = body
    comment.created_at = datetime.fromisoformat(created_at).replace(tzinfo=None)
    return comment


def make_issue(comments: list[MagicMock] | None = None) -> MagicMock:
    """Create a mock GitHub Issue.

    Args:
        comments: List of mock comments to return from get_comments.

    Returns:
        MagicMock configured as an Issue.
    """
    issue = MagicMock()
    issue.get_comments.return_value = comments or []
    return issue


def make_repo(issue: MagicMock | None = None) -> MagicMock:
    """Create a mock GitHub Repository.

    Args:
        issue: Mock issue to return from get_issue.

    Returns:
        MagicMock configured as a Repository.
    """
    repo = MagicMock()
    repo.get_issue.return_value = issue or make_issue()
    return repo


def make_pr_issue(number: int = 1, title: str = "test PR") -> MagicMock:
    """Create a mock Issue as returned by search_issues.

    Args:
        number: PR number.
        title: PR title.

    Returns:
        MagicMock configured as a search result Issue.
    """
    pr_issue = MagicMock()
    pr_issue.number = number
    pr_issue.title = title
    return pr_issue
