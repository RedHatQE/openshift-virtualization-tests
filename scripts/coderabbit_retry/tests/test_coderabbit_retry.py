"""Unit tests for coderabbit_retry module.

Co-authored-by: Claude <noreply@anthropic.com>
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from scripts.coderabbit_retry.coderabbit_retry import (
    _validate_rate_limit_payload,
    check_rate_limit,
    has_review_request_after,
    is_wip_title,
    list_eligible_prs,
    main,
    process_pr,
    trigger_review,
)
from scripts.coderabbit_retry.tests.utils import (
    make_comment,
    make_completed_process,
    make_issue,
    make_pr_issue,
    make_repo,
)

SUBPROCESS_PATH = "scripts.coderabbit_retry.coderabbit_retry.subprocess_run"
REPO = "owner/repo"
PR_NUMBER = 42


class TestListEligiblePrs:
    """Tests for list_eligible_prs using PyGithub search."""

    def test_returns_matching_prs(self) -> None:
        github_client = MagicMock()
        github_client.search_issues.return_value = [make_pr_issue(number=1), make_pr_issue(number=2)]
        result = list_eligible_prs(github_client=github_client, repo_name=REPO)
        assert len(result) == 2
        call_kwargs = github_client.search_issues.call_args
        assert call_kwargs.kwargs["sort"] == "updated"
        assert call_kwargs.kwargs["order"] == "desc"

    def test_caps_at_max_prs(self) -> None:
        github_client = MagicMock()
        github_client.search_issues.return_value = [make_pr_issue(number=idx) for idx in range(300)]
        result = list_eligible_prs(github_client=github_client, repo_name=REPO)
        assert len(result) == 200

    def test_returns_empty_list_when_no_matches(self) -> None:
        github_client = MagicMock()
        github_client.search_issues.return_value = []
        result = list_eligible_prs(github_client=github_client, repo_name=REPO)
        assert result == []


class TestValidateRateLimitPayload:
    """Tests for _validate_rate_limit_payload type checking."""

    def test_valid_payload_passes(self) -> None:
        payload = {"rate_limited": True, "wait_seconds": 120, "updated_at": "2026-08-05T10:00:00+00:00"}
        assert _validate_rate_limit_payload(payload=payload, pr_number=PR_NUMBER) == payload

    def test_accepts_none_values(self) -> None:
        payload = {"rate_limited": None, "wait_seconds": None, "updated_at": None}
        assert _validate_rate_limit_payload(payload=payload, pr_number=PR_NUMBER) == payload

    def test_rejects_non_bool_rate_limited(self) -> None:
        payload = {"rate_limited": "yes"}
        assert _validate_rate_limit_payload(payload=payload, pr_number=PR_NUMBER) is None

    @pytest.mark.parametrize(
        "invalid_wait_seconds",
        [
            pytest.param("120", id="string"),
            pytest.param(True, id="bool_true"),
            pytest.param(False, id="bool_false"),
            pytest.param(-60, id="negative"),
        ],
    )
    def test_rejects_invalid_wait_seconds(self, invalid_wait_seconds: object) -> None:
        payload = {"wait_seconds": invalid_wait_seconds}
        assert _validate_rate_limit_payload(payload=payload, pr_number=PR_NUMBER) is None

    def test_rejects_non_str_updated_at(self) -> None:
        payload = {"updated_at": 12345}
        assert _validate_rate_limit_payload(payload=payload, pr_number=PR_NUMBER) is None


class TestCheckRateLimit:
    """Tests for check_rate_limit (myk-pi-tools subprocess)."""

    @patch(SUBPROCESS_PATH)
    def test_returns_valid_payload(self, mock_run: MagicMock) -> None:
        payload = {"rate_limited": True, "wait_seconds": 120, "updated_at": "2026-08-05T10:00:00+00:00"}
        mock_run.return_value = make_completed_process(stdout=json.dumps(payload))
        assert check_rate_limit(repo_name=REPO, pr_number=PR_NUMBER) == payload

    @patch(SUBPROCESS_PATH)
    def test_returns_none_on_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = TimeoutExpired(cmd="myk-pi-tools", timeout=30)
        assert check_rate_limit(repo_name=REPO, pr_number=PR_NUMBER) is None

    @patch(SUBPROCESS_PATH)
    def test_returns_none_on_nonzero_exit(self, mock_run: MagicMock) -> None:
        mock_run.return_value = make_completed_process(returncode=1, stderr="error")
        assert check_rate_limit(repo_name=REPO, pr_number=PR_NUMBER) is None

    @patch(SUBPROCESS_PATH)
    def test_returns_none_on_invalid_json(self, mock_run: MagicMock) -> None:
        mock_run.return_value = make_completed_process(stdout="not json")
        assert check_rate_limit(repo_name=REPO, pr_number=PR_NUMBER) is None

    @patch(SUBPROCESS_PATH)
    def test_returns_none_when_payload_not_dict(self, mock_run: MagicMock) -> None:
        mock_run.return_value = make_completed_process(stdout="[1, 2]")
        assert check_rate_limit(repo_name=REPO, pr_number=PR_NUMBER) is None

    @pytest.mark.parametrize(
        "json_value",
        [
            pytest.param("Infinity", id="positive_infinity"),
            pytest.param("-Infinity", id="negative_infinity"),
            pytest.param("NaN", id="nan"),
        ],
    )
    @patch(SUBPROCESS_PATH)
    def test_rejects_non_finite_wait_seconds(self, mock_run: MagicMock, json_value: str) -> None:
        raw_json = f'{{"rate_limited": true, "wait_seconds": {json_value}, "updated_at": "2026-08-05T10:00:00+00:00"}}'
        mock_run.return_value = make_completed_process(stdout=raw_json)
        assert check_rate_limit(repo_name=REPO, pr_number=PR_NUMBER) is None


class TestHasReviewRequestAfter:
    """Tests for has_review_request_after using PyGithub."""

    def test_returns_true_when_matching_comment_found(self) -> None:
        comment = make_comment(login="human", body="@coderabbitai review", created_at="2026-08-05T12:00:00Z")
        repo = make_repo(issue=make_issue(comments=[comment]))
        result = has_review_request_after(repo=repo, pr_number=PR_NUMBER, after_epoch=1000.0)
        assert result is True

    def test_returns_false_when_no_matching_comment(self) -> None:
        comment = make_comment(login="human", body="looks good", created_at="2026-08-05T12:00:00Z")
        repo = make_repo(issue=make_issue(comments=[comment]))
        result = has_review_request_after(repo=repo, pr_number=PR_NUMBER, after_epoch=1000.0)
        assert result is False

    def test_ignores_coderabbit_bot_comments(self) -> None:
        comment = make_comment(
            login="coderabbitai[bot]", body="@coderabbitai review", created_at="2026-08-05T12:00:00Z"
        )
        repo = make_repo(issue=make_issue(comments=[comment]))
        result = has_review_request_after(repo=repo, pr_number=PR_NUMBER, after_epoch=1000.0)
        assert result is False

    def test_returns_none_on_github_exception(self) -> None:
        repo = MagicMock()
        repo.get_issue.side_effect = GithubException(status=500, data={"message": "error"})
        result = has_review_request_after(repo=repo, pr_number=PR_NUMBER, after_epoch=1000.0)
        assert result is None

    def test_returns_false_when_comment_before_epoch(self) -> None:
        comment = make_comment(login="human", body="@coderabbitai review", created_at="2020-01-01T00:00:00Z")
        repo = make_repo(issue=make_issue(comments=[comment]))
        future_epoch = datetime(year=2030, month=1, day=1, tzinfo=UTC).timestamp()
        result = has_review_request_after(repo=repo, pr_number=PR_NUMBER, after_epoch=future_epoch)
        assert result is False

    def test_handles_null_body(self) -> None:
        comment = make_comment(login="human", body=None, created_at="2026-08-05T12:00:00Z")
        repo = make_repo(issue=make_issue(comments=[comment]))
        result = has_review_request_after(repo=repo, pr_number=PR_NUMBER, after_epoch=1000.0)
        assert result is False


class TestTriggerReview:
    """Tests for trigger_review using PyGithub."""

    def test_returns_true_on_success(self) -> None:
        repo = make_repo(issue=make_issue())
        assert trigger_review(repo=repo, pr_number=PR_NUMBER) is True

    def test_returns_false_on_github_exception(self) -> None:
        repo = MagicMock()
        repo.get_issue.side_effect = GithubException(status=403, data={"message": "forbidden"})
        assert trigger_review(repo=repo, pr_number=PR_NUMBER) is False


class TestIsWipTitle:
    """Tests for WIP title detection."""

    @pytest.mark.parametrize(
        "title",
        [
            pytest.param("WIP: my feature", id="wip_prefix_upper"),
            pytest.param("wip: my feature", id="wip_prefix_lower"),
            pytest.param("[WIP] my feature", id="bracket_wip_upper"),
            pytest.param("[wip] my feature", id="bracket_wip_lower"),
            pytest.param("my wip feature", id="wip_word"),
        ],
    )
    def test_wip_patterns_match(self, title: str) -> None:
        assert is_wip_title(title=title) is True

    @pytest.mark.parametrize(
        "title",
        [
            pytest.param("fix: normal title", id="normal_title"),
            pytest.param("swiping feature", id="swiping_substring"),
            pytest.param("docs: update guide", id="docs_title"),
            pytest.param("wipe old data", id="wipe_substring"),
        ],
    )
    def test_non_wip_titles_do_not_match(self, title: str) -> None:
        assert is_wip_title(title=title) is False


class TestProcessPr:
    """Tests for process_pr orchestration."""

    @patch("scripts.coderabbit_retry.coderabbit_retry.trigger_review", return_value=True)
    @patch("scripts.coderabbit_retry.coderabbit_retry.has_review_request_after", return_value=False)
    @patch("scripts.coderabbit_retry.coderabbit_retry.time_time")
    @patch("scripts.coderabbit_retry.coderabbit_retry.check_rate_limit")
    def test_triggers_when_wait_elapsed(
        self, mock_check: MagicMock, mock_time: MagicMock, _mock_review: MagicMock, _mock_trigger: MagicMock
    ) -> None:
        mock_check.return_value = {
            "rate_limited": True,
            "wait_seconds": 60,
            "updated_at": "2026-08-05T10:00:00+00:00",
        }
        mock_time.return_value = datetime.fromisoformat("2026-08-05T10:05:00+00:00").timestamp()
        repo = make_repo()
        assert process_pr(repo_name=REPO, repo=repo, pr_number=PR_NUMBER) is True

    @patch("scripts.coderabbit_retry.coderabbit_retry.check_rate_limit")
    def test_skips_when_not_rate_limited(self, mock_check: MagicMock) -> None:
        mock_check.return_value = {"rate_limited": False}
        assert process_pr(repo_name=REPO, repo=make_repo(), pr_number=PR_NUMBER) is False

    @patch("scripts.coderabbit_retry.coderabbit_retry.time_time")
    @patch("scripts.coderabbit_retry.coderabbit_retry.check_rate_limit")
    def test_skips_when_wait_not_elapsed(self, mock_check: MagicMock, mock_time: MagicMock) -> None:
        mock_check.return_value = {
            "rate_limited": True,
            "wait_seconds": 600,
            "updated_at": "2026-08-05T10:00:00+00:00",
        }
        mock_time.return_value = datetime.fromisoformat("2026-08-05T10:01:00+00:00").timestamp()
        assert process_pr(repo_name=REPO, repo=make_repo(), pr_number=PR_NUMBER) is False

    @patch("scripts.coderabbit_retry.coderabbit_retry.check_rate_limit")
    def test_skips_when_missing_wait_seconds(self, mock_check: MagicMock) -> None:
        mock_check.return_value = {"rate_limited": True}
        assert process_pr(repo_name=REPO, repo=make_repo(), pr_number=PR_NUMBER) is False

    @patch("scripts.coderabbit_retry.coderabbit_retry.check_rate_limit")
    def test_skips_when_missing_updated_at(self, mock_check: MagicMock) -> None:
        mock_check.return_value = {"rate_limited": True, "wait_seconds": 60}
        assert process_pr(repo_name=REPO, repo=make_repo(), pr_number=PR_NUMBER) is False

    @patch("scripts.coderabbit_retry.coderabbit_retry.check_rate_limit")
    def test_skips_when_updated_at_unparseable(self, mock_check: MagicMock) -> None:
        mock_check.return_value = {"rate_limited": True, "wait_seconds": 60, "updated_at": "not-a-date"}
        assert process_pr(repo_name=REPO, repo=make_repo(), pr_number=PR_NUMBER) is False


class TestMain:
    """Tests for main entry point."""

    @patch.dict("os.environ", {}, clear=True)
    def test_exits_1_when_repo_missing(self) -> None:
        assert main() == 1

    @patch.dict("os.environ", {"REPO": "owner/repo"}, clear=True)
    def test_exits_1_when_gh_token_missing(self) -> None:
        assert main() == 1

    @patch("scripts.coderabbit_retry.coderabbit_retry.process_pr", return_value=False)
    @patch("scripts.coderabbit_retry.coderabbit_retry.list_eligible_prs")
    @patch("scripts.coderabbit_retry.coderabbit_retry.Github")
    @patch.dict("os.environ", {"REPO": "owner/repo", "GH_TOKEN": "fake-token"}, clear=True)
    def test_exits_0_with_valid_env(
        self, _mock_github_cls: MagicMock, mock_list: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_list.return_value = [make_pr_issue(number=1)]
        assert main() == 0

    @patch("scripts.coderabbit_retry.coderabbit_retry.process_pr", return_value=False)
    @patch("scripts.coderabbit_retry.coderabbit_retry.list_eligible_prs")
    @patch("scripts.coderabbit_retry.coderabbit_retry.Github")
    @patch.dict("os.environ", {"REPO": "owner/repo", "GH_TOKEN": "fake-token"}, clear=True)
    def test_skips_wip_prs(self, _mock_github_cls: MagicMock, mock_list: MagicMock, mock_process: MagicMock) -> None:
        mock_list.return_value = [make_pr_issue(number=1, title="[WIP] my feature")]
        assert main() == 0
        mock_process.assert_not_called()

    @patch("scripts.coderabbit_retry.coderabbit_retry.process_pr", side_effect=[True, False, True])
    @patch("scripts.coderabbit_retry.coderabbit_retry.list_eligible_prs")
    @patch("scripts.coderabbit_retry.coderabbit_retry.Github")
    @patch.dict("os.environ", {"REPO": "owner/repo", "GH_TOKEN": "fake-token"}, clear=True)
    def test_aggregates_results_from_multiple_prs(
        self,
        _mock_github_cls: MagicMock,
        mock_list: MagicMock,
        mock_process: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_list.return_value = [
            make_pr_issue(number=1),
            make_pr_issue(number=2),
            make_pr_issue(number=3),
        ]
        with caplog.at_level(level="INFO"):
            assert main() == 0
        assert "Summary: checked=3 skipped=0 retried=2" in caplog.text
        assert mock_process.call_count == 3

    @patch("scripts.coderabbit_retry.coderabbit_retry.process_pr")
    @patch("scripts.coderabbit_retry.coderabbit_retry.list_eligible_prs")
    @patch("scripts.coderabbit_retry.coderabbit_retry.Github")
    @patch.dict("os.environ", {"REPO": "owner/repo", "GH_TOKEN": "fake-token"}, clear=True)
    def test_isolates_github_exception_per_pr(
        self,
        _mock_github_cls: MagicMock,
        mock_list: MagicMock,
        mock_process: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def process_side_effect(*, pr_number: int, **_unused_parameters: object) -> bool:
            if pr_number == 1:
                raise GithubException(status=500, data={"message": "server error"})
            return True

        mock_process.side_effect = process_side_effect
        mock_list.return_value = [
            make_pr_issue(number=1),
            make_pr_issue(number=2),
        ]
        with caplog.at_level(level="INFO"):
            assert main() == 0
        assert "PR #1: processing failed" in caplog.text
        assert "retried=1" in caplog.text

    @patch("scripts.coderabbit_retry.coderabbit_retry.process_pr", return_value=False)
    @patch("scripts.coderabbit_retry.coderabbit_retry.list_eligible_prs")
    @patch("scripts.coderabbit_retry.coderabbit_retry.Github")
    @patch.dict("os.environ", {"REPO": "owner/repo", "GH_TOKEN": "fake-token"}, clear=True)
    def test_counts_wip_and_non_wip_correctly(
        self,
        _mock_github_cls: MagicMock,
        mock_list: MagicMock,
        mock_process: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_list.return_value = [
            make_pr_issue(number=1, title="[WIP] feature one"),
            make_pr_issue(number=2, title="normal PR two"),
            make_pr_issue(number=3, title="WIP: feature three"),
            make_pr_issue(number=4, title="normal PR four"),
            make_pr_issue(number=5, title="normal PR five"),
        ]
        with caplog.at_level(level="INFO"):
            assert main() == 0
        assert "Summary: checked=3 skipped=2" in caplog.text
        assert mock_process.call_count == 3
