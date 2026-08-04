"""Tests for the local resume flow in coderabbit_rate_limit."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.coderabbit_rate_limit.coderabbit_rate_limit import _run_resume


class TestRunResume:
    """Tests for _run_resume function."""

    def test_invalid_owner_repo_no_slash(self) -> None:
        """Test that owner/repo without slash returns exit code 1."""
        assert _run_resume(owner_repo="invalid", pr_number=1) == 1

    def test_invalid_owner_repo_empty(self) -> None:
        """Test that empty owner/repo returns exit code 1."""
        assert _run_resume(owner_repo="", pr_number=1) == 1

    def test_invalid_owner_repo_too_many_slashes(self) -> None:
        """Test that owner/repo with too many slashes returns exit code 1."""
        assert _run_resume(owner_repo="a/b/c", pr_number=1) == 1

    def test_gh_api_failure(self) -> None:
        """Test that GitHub API failure returns exit code 1."""
        mock_run_gh = MagicMock(return_value=(1, "", "API error"))
        with patch(
            "scripts.coderabbit_rate_limit.coderabbit_rate_limit.run_gh",
            mock_run_gh,
        ):
            assert _run_resume(owner_repo="owner/repo", pr_number=123) == 1

    def test_successful_resume(self) -> None:
        """Test that successful resume returns exit code 0."""
        mock_run_gh = MagicMock(return_value=(0, '{"id": 42}', ""))
        with patch(
            "scripts.coderabbit_rate_limit.coderabbit_rate_limit.run_gh",
            mock_run_gh,
        ):
            result = _run_resume(owner_repo="owner/repo", pr_number=123)
            assert result == 0
            mock_run_gh.assert_called_once_with(
                args=[
                    "api",
                    "repos/owner/repo/issues/123/comments",
                    "-f",
                    "body=@coderabbitai resume",
                ],
                timeout=30,
            )

    def test_malformed_json_response(self) -> None:
        """Test that malformed JSON response still returns exit code 0."""
        mock_run_gh = MagicMock(return_value=(0, "not json", ""))
        with patch(
            "scripts.coderabbit_rate_limit.coderabbit_rate_limit.run_gh",
            mock_run_gh,
        ):
            result = _run_resume(owner_repo="owner/repo", pr_number=123)
            assert result == 0

    def test_empty_stdout(self) -> None:
        """Test that empty stdout still returns exit code 0."""
        mock_run_gh = MagicMock(return_value=(0, "", ""))
        with patch(
            "scripts.coderabbit_rate_limit.coderabbit_rate_limit.run_gh",
            mock_run_gh,
        ):
            result = _run_resume(owner_repo="owner/repo", pr_number=123)
            assert result == 0
