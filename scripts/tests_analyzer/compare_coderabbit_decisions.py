#!/usr/bin/env -S uv run python

# Generated using Claude cli

"""
CodeRabbit vs Pytest Marker Analyzer Comparison Tool

Compares CodeRabbit's smoke test decisions with the local pytest marker analyzer's decisions
for all open PRs in a repository.

Usage:
    uv run python scripts/tests_analyzer/compare_coderabbit_decisions.py
    uv run python scripts/tests_analyzer/compare_coderabbit_decisions.py --repo owner/repo
    uv run python scripts/tests_analyzer/compare_coderabbit_decisions.py --output json
    uv run python scripts/tests_analyzer/compare_coderabbit_decisions.py --verbose
    uv run python scripts/tests_analyzer/compare_coderabbit_decisions.py --detailed  # Include full dependency analysis
    uv run python scripts/tests_analyzer/compare_coderabbit_decisions.py --output-file report.md --detailed
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from simple_logger.logger import get_logger

# Configure logging
logger = get_logger(name=__name__, level=logging.INFO)


def get_default_repo() -> str:
    """Try to detect repo from git remote, fallback to hardcoded default."""
    git_path = shutil.which("git")
    if not git_path:
        return "RedHatQE/openshift-virtualization-tests"

    try:
        result = subprocess.run(
            [git_path, "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Parse git@github.com:owner/repo.git or https://github.com/owner/repo
            match = re.search(r"github\.com[:/]([^/]+/[^/\.]+)", url)
            if match:
                return match.group(1).rstrip(".git")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as exc:
        logger.info("Failed to detect repo from git remote", extra={"error": str(exc)})
    return "RedHatQE/openshift-virtualization-tests"


# Constants
DEFAULT_REPO = get_default_repo()
GITHUB_API_BASE = "https://api.github.com"
CODERABBIT_BOT = "coderabbitai[bot]"

# Pattern to find the Test Execution Plan section (various formats)
TEST_PLAN_PATTERN = re.compile(r"(?:#{1,3}|\*\*)\s*Test Execution Plan\s*(?:\*\*)?", re.IGNORECASE)

# Pattern to find smoke test decision (various formats)
SMOKE_TEST_PATTERN = re.compile(r"(?:\*\*)?Run smoke tests:?\s*(?:\*\*)?\s*[`*]*(True|False)[`*]*", re.IGNORECASE)


@dataclass
class CodeRabbitDecision:
    """Represents CodeRabbit's decision from a PR comment."""

    found: bool
    should_run: bool | None = None
    comment_url: str | None = None
    comment_body: str | None = None


@dataclass
class AnalyzerDecision:
    """Represents the local analyzer's decision."""

    success: bool
    should_run: bool | None = None
    reason: str | None = None
    marker_expression: str | None = None
    affected_test_count: int = 0
    total_tests: int = 0
    affected_tests: list[dict] = field(default_factory=list)  # List of {node_id, test_name, test_file, dependencies}
    changed_files: list[str] = field(default_factory=list)  # List of changed files
    error: str | None = None


@dataclass
class ComparisonResult:
    """Result of comparing CodeRabbit vs Analyzer for a single PR."""

    pr_number: int
    pr_title: str
    pr_url: str
    pr_author: str
    coderabbit: CodeRabbitDecision
    analyzer: AnalyzerDecision
    match: bool | None = None  # None if comparison not possible

    def to_dict(self) -> dict[str, Any]:
        return {
            "pr_number": self.pr_number,
            "pr_title": self.pr_title,
            "pr_url": self.pr_url,
            "pr_author": self.pr_author,
            "coderabbit_decision": self.coderabbit.should_run,
            "coderabbit_comment_url": self.coderabbit.comment_url,
            "analyzer_decision": self.analyzer.should_run,
            "analyzer_reason": self.analyzer.reason,
            "analyzer_marker_expression": self.analyzer.marker_expression,
            "analyzer_affected_test_count": self.analyzer.affected_test_count,
            "analyzer_total_tests": self.analyzer.total_tests,
            "analyzer_affected_tests": self.analyzer.affected_tests,
            "analyzer_changed_files": self.analyzer.changed_files,
            "match": self.match,
        }


def _validate_github_url(url: str) -> None:
    """Validate that URL uses HTTPS scheme and targets GitHub API."""
    if not url.startswith("https://"):
        raise ValueError(f"URL must use HTTPS scheme: {url}")
    if not url.startswith(GITHUB_API_BASE):
        raise ValueError(f"URL must target GitHub API: {url}")


def github_request(url: str, token: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    """Make a GitHub API request with error handling."""
    _validate_github_url(url=url)

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "coderabbit-comparison-tool",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            logger.error(
                "GitHub API rate limit exceeded",
                extra={"url": url, "status_code": exc.code, "error": str(exc)},
            )
        raise


def get_open_prs(repo: str, token: str | None = None) -> list[dict]:
    """Get all open PRs targeting main branch."""
    prs: list[dict[str, Any]] = []
    page = 1
    per_page = 100

    while True:
        url = f"{GITHUB_API_BASE}/repos/{repo}/pulls?state=open&base=main&per_page={per_page}&page={page}"
        logger.info(msg="Fetching PRs page", extra={"page": page, "repo": repo})

        try:
            data = github_request(url=url, token=token)
            if not isinstance(data, list):
                break
            prs.extend(data)

            if len(data) < per_page:
                break
            page += 1
        except urllib.error.HTTPError as exc:
            logger.error(
                msg="Failed to fetch PRs",
                extra={"repo": repo, "page": page, "error": str(exc)},
            )
            break
        except urllib.error.URLError as exc:
            logger.warning(msg="Network error fetching PRs", extra={"repo": repo, "error": str(exc)})
            break

    logger.info(msg="Found open PRs targeting main branch", extra={"count": len(prs), "repo": repo})
    return prs


def get_pr_comments(repo: str, pr_number: int, token: str | None = None) -> list[dict]:
    """Get all comments on a PR (issue comments, review comments, and reviews)."""
    comments: list[dict[str, Any]] = []
    page = 1
    per_page = 100

    # Get issue comments (regular PR comments)
    while True:
        url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments?per_page={per_page}&page={page}"
        try:
            data = github_request(url=url, token=token)
            if not data or not isinstance(data, list):
                break
            comments.extend(data)
            if len(data) < per_page:
                break
            page += 1
        except urllib.error.HTTPError as exc:
            logger.error(
                msg="Failed to fetch issue comments",
                extra={"pr_number": pr_number, "page": page, "error": str(exc)},
            )
            break
        except urllib.error.URLError as exc:
            logger.warning(
                "Network error fetching issue comments",
                extra={"pr_number": pr_number, "error": str(exc)},
            )
            break

    # Get review comments (inline code comments)
    page = 1
    while True:
        url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/comments?per_page={per_page}&page={page}"
        try:
            data = github_request(url=url, token=token)
            if not data or not isinstance(data, list):
                break
            comments.extend(data)
            if len(data) < per_page:
                break
            page += 1
        except urllib.error.HTTPError as exc:
            logger.error(
                msg="Failed to fetch review comments",
                extra={"pr_number": pr_number, "page": page, "error": str(exc)},
            )
            break
        except urllib.error.URLError as exc:
            logger.warning(
                "Network error fetching review comments",
                extra={"pr_number": pr_number, "error": str(exc)},
            )
            break

    # Get reviews (PR review summaries which may contain the decision)
    page = 1
    while True:
        url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/reviews?per_page={per_page}&page={page}"
        try:
            data = github_request(url=url, token=token)
            # Reviews have a body field that may contain the Test Execution Plan
            if not data or not isinstance(data, list):
                break
            for review in data:
                if review.get("body"):
                    comments.append({
                        "user": review.get("user"),
                        "body": review.get("body"),
                        "html_url": review.get("html_url"),
                    })
            if len(data) < per_page:
                break
            page += 1
        except urllib.error.HTTPError as exc:
            logger.error(
                msg="Failed to fetch reviews",
                extra={"pr_number": pr_number, "page": page, "error": str(exc)},
            )
            break
        except urllib.error.URLError as exc:
            logger.warning(
                "Network error fetching reviews",
                extra={"pr_number": pr_number, "error": str(exc)},
            )
            break

    logger.info(msg="Fetched comments for PR", extra={"pr_number": pr_number, "count": len(comments)})
    return comments


def find_coderabbit_decision(comments: list[dict]) -> CodeRabbitDecision:
    """
    Find CodeRabbit's smoke test decision in PR comments.

    Searches through all comment types (issue comments, review comments, reviews)
    for the Test Execution Plan section and smoke test decision.
    """
    for comment in comments:
        user = comment.get("user", {})
        login = user.get("login", "") if user else ""
        body = comment.get("body", "") or ""

        # Check if comment is from CodeRabbit
        if login != CODERABBIT_BOT:
            continue

        # Check if comment contains Test Execution Plan (various formats)
        # Matches: "## Test Execution Plan", "**Test Execution Plan**", "### Test Execution Plan"
        if not TEST_PLAN_PATTERN.search(body):
            continue

        logger.info(msg="Found Test Execution Plan in comment", extra={"login": login})

        # Extract the decision
        # Matches various formats:
        # - **Run smoke tests: True**
        # - **Run smoke tests: False**
        # - Run smoke tests: `True`
        # - Run smoke tests: `False`
        # - **Run smoke tests:** True
        match = SMOKE_TEST_PATTERN.search(string=body)
        if match:
            decision_str = match.group(1).lower()
            should_run = decision_str == "true"

            logger.info(msg="Extracted decision", extra={"should_run": should_run})

            return CodeRabbitDecision(
                found=True,
                should_run=should_run,
                comment_url=comment.get("html_url"),
                comment_body=body[:500] + "..." if len(body) > 500 else body,
            )
        # Found Test Execution Plan but no smoke test decision pattern
        logger.info(msg="Test Execution Plan found but no smoke test decision matched", extra={"login": login})

    return CodeRabbitDecision(found=False)


def run_analyzer(repo: str, pr_number: int, token: str | None = None) -> AnalyzerDecision:
    """Run the local pytest marker analyzer against a PR."""
    script_dir = Path(__file__).parent
    analyzer_path = script_dir / "pytest_marker_analyzer.py"

    if not analyzer_path.exists():
        return AnalyzerDecision(
            success=False,
            error=f"Analyzer not found at {analyzer_path}",
        )

    # Validate repo format to prevent command injection
    if not re.match(r"^[\w.-]+/[\w.-]+$", repo):
        return AnalyzerDecision(
            success=False,
            error=f"Invalid repository format: {repo}",
        )

    cmd = [
        sys.executable,
        str(analyzer_path),
        "--repo",
        repo,
        "--pr",
        str(pr_number),
        "--output",
        "json",
    ]

    env = os.environ.copy()
    if token:
        env["GITHUB_TOKEN"] = token

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            check=False,
        )

        if result.returncode != 0:
            logger.info(
                msg="Analyzer returned non-zero exit code",
                extra={"returncode": result.returncode, "stderr": result.stderr[:200]},
            )
            return AnalyzerDecision(
                success=False,
                error=f"Analyzer failed (rc={result.returncode}): {result.stderr[:200]}",
            )

        # Parse JSON output
        try:
            data = json.loads(result.stdout)
            affected_tests = data.get("affected_tests", [])
            return AnalyzerDecision(
                success=True,
                should_run=data.get("should_run_tests"),
                reason=data.get("reason"),
                marker_expression=data.get("marker_expression"),
                affected_test_count=len(affected_tests),
                total_tests=data.get("total_tests", 0),
                affected_tests=affected_tests,
                changed_files=data.get("changed_files", []),
            )
        except json.JSONDecodeError as exc:
            return AnalyzerDecision(
                success=False,
                error=f"Failed to parse analyzer output: {exc}",
            )

    except subprocess.TimeoutExpired:
        return AnalyzerDecision(
            success=False,
            error="Analyzer timed out after 120 seconds",
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return AnalyzerDecision(
            success=False,
            error=str(exc),
        )


def compare_pr(
    repo: str,
    pr: dict,
    token: str | None = None,
) -> ComparisonResult:
    """Compare CodeRabbit vs Analyzer decision for a single PR."""
    pr_number = pr["number"]
    pr_title = pr["title"]
    pr_url = pr["html_url"]
    pr_user = pr.get("user")
    pr_author = pr_user.get("login", "unknown") if pr_user else "[deleted]"

    logger.info(msg="Processing PR", extra={"pr_number": pr_number, "pr_title": pr_title[:50]})

    # Get CodeRabbit's decision
    comments = get_pr_comments(repo=repo, pr_number=pr_number, token=token)
    coderabbit = find_coderabbit_decision(comments=comments)

    if not coderabbit.found:
        logger.info(msg="No CodeRabbit decision found", extra={"pr_number": pr_number})
    else:
        logger.info(
            msg="CodeRabbit decision",
            extra={"pr_number": pr_number, "should_run": coderabbit.should_run},
        )

    # Run local analyzer
    analyzer = run_analyzer(repo=repo, pr_number=pr_number, token=token)

    if not analyzer.success:
        logger.warning(msg="Analyzer failed", extra={"pr_number": pr_number, "error": analyzer.error})
    else:
        logger.info(
            msg="Analyzer decision",
            extra={"pr_number": pr_number, "should_run": analyzer.should_run},
        )

    # Determine if they match
    match = None
    if coderabbit.found and analyzer.success:
        match = coderabbit.should_run == analyzer.should_run
        if match:
            logger.info(
                msg="MATCH: Both decisions agree",
                extra={"pr_number": pr_number, "decision": coderabbit.should_run},
            )
        else:
            logger.info(
                msg="MISMATCH: Decisions disagree",
                extra={
                    "pr_number": pr_number,
                    "coderabbit": coderabbit.should_run,
                    "analyzer": analyzer.should_run,
                },
            )

    return ComparisonResult(
        pr_number=pr_number,
        pr_title=pr_title,
        pr_url=pr_url,
        pr_author=pr_author,
        coderabbit=coderabbit,
        analyzer=analyzer,
        match=match,
    )


def generate_detailed_mismatch_analysis(result: ComparisonResult) -> list[str]:
    """Generate detailed analysis for a mismatch case."""
    lines = []

    lines.append(f"### PR #{result.pr_number} - [{result.pr_title}]({result.pr_url})")
    lines.append("")
    lines.append(f"**Author:** {result.pr_author}")
    lines.append(f"**CodeRabbit decision:** {'Run' if result.coderabbit.should_run else 'Skip'}")
    lines.append(f"**Analyzer decision:** {'Run' if result.analyzer.should_run else 'Skip'}")
    if result.analyzer.marker_expression:
        lines.append(f"**Marker expression:** `{result.analyzer.marker_expression}`")
    lines.append("")

    # Show changed files
    if result.analyzer.changed_files:
        lines.append(f"**Changed files ({len(result.analyzer.changed_files)}):**")
        for file in result.analyzer.changed_files[:10]:  # Limit to first 10
            lines.append(f"- `{file}`")
        if len(result.analyzer.changed_files) > 10:
            lines.append(f"- _(and {len(result.analyzer.changed_files) - 10} more)_")
        lines.append("")

    # Show affected tests
    if result.analyzer.affected_tests:
        lines.append(f"**Affected smoke tests ({result.analyzer.affected_test_count}/{result.analyzer.total_tests}):**")
        for test in result.analyzer.affected_tests[:10]:  # Limit to first 10
            node_id = test.get("node_id", "unknown")
            deps = test.get("dependencies", [])
            lines.append(f"- `{node_id}`")
            if deps:
                lines.append(f"  - Dependencies: {', '.join(f'`{dep}`' for dep in deps[:3])}")
                if len(deps) > 3:
                    lines.append(f"  - _(and {len(deps) - 3} more dependencies)_")
        if result.analyzer.affected_test_count > 10:
            lines.append(f"- _(and {result.analyzer.affected_test_count - 10} more tests)_")
        lines.append("")

    # Show analyzer reasoning
    lines.append(f"**Analyzer reasoning:** {result.analyzer.reason}")
    lines.append("")

    return lines


def generate_markdown_report(results: list[ComparisonResult], repo: str, *, detailed: bool = False) -> str:
    """Generate a Markdown report of the comparison results."""
    lines = [
        "# CodeRabbit vs Pytest Marker Analyzer Comparison Report",
        "",
        f"**Repository:** [{repo}](https://github.com/{repo})",
        f"**Generated:** {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total PRs analyzed:** {len(results)}",
        "",
    ]

    # Summary statistics
    with_coderabbit = [result for result in results if result.coderabbit.found]
    with_analyzer = [result for result in results if result.analyzer.success]
    comparable = [result for result in results if result.match is not None]
    matches = [result for result in comparable if result.match]
    mismatches = [result for result in comparable if not result.match]

    lines.extend([
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total PRs | {len(results)} |",
        f"| PRs with CodeRabbit decision | {len(with_coderabbit)} |",
        f"| PRs with successful analyzer run | {len(with_analyzer)} |",
        f"| Comparable (both available) | {len(comparable)} |",
        f"| **Matches** | {len(matches)} |",
        f"| **Mismatches** | {len(mismatches)} |",
        "",
    ])

    if comparable:
        accuracy = (len(matches) / len(comparable)) * 100
        lines.append(f"**Agreement Rate:** {accuracy:.1f}%")
        lines.append("")

    # Mismatches section (most important)
    if mismatches:
        lines.extend([
            "## Mismatches (Disagreements)",
            "",
            "| PR | CodeRabbit | Analyzer | Affected Tests | Changed Files | Analyzer Reason |",
            "|----|------------|----------|----------------|---------------|-----------------|",
        ])
        for mismatch in mismatches:
            coderabbit_decision = "Run" if mismatch.coderabbit.should_run else "Skip"
            analyzer_decision = "Run" if mismatch.analyzer.should_run else "Skip"
            affected = (
                f"{mismatch.analyzer.affected_test_count}/{mismatch.analyzer.total_tests}"
                if mismatch.analyzer.total_tests
                else "N/A"
            )
            changed = str(len(mismatch.analyzer.changed_files)) if mismatch.analyzer.changed_files else "0"
            reason = (mismatch.analyzer.reason or "N/A")[:50]
            lines.append(
                f"| [#{mismatch.pr_number}]({mismatch.pr_url}) | {coderabbit_decision} | "
                f"{analyzer_decision} | {affected} | {changed} | {reason} |"
            )
        lines.append("")

        # Detailed breakdown if requested
        if detailed:
            lines.extend([
                "### Detailed Mismatch Analysis",
                "",
            ])
            for mismatch in mismatches:
                lines.extend(generate_detailed_mismatch_analysis(result=mismatch))
                lines.append("---")
                lines.append("")

    # Matches section
    if matches:
        lines.extend([
            "## Matches (Agreements)",
            "",
            "| PR | Decision | Affected Tests | Changed Files | Analyzer Reason |",
            "|----|----------|----------------|---------------|-----------------|",
        ])
        for match_result in matches:
            decision = "Run" if match_result.coderabbit.should_run else "Skip"
            affected = (
                f"{match_result.analyzer.affected_test_count}/{match_result.analyzer.total_tests}"
                if match_result.analyzer.total_tests
                else "N/A"
            )
            changed = str(len(match_result.analyzer.changed_files)) if match_result.analyzer.changed_files else "0"
            reason = (match_result.analyzer.reason or "N/A")[:50]
            lines.append(
                f"| [#{match_result.pr_number}]({match_result.pr_url}) | {decision} | "
                f"{affected} | {changed} | {reason} |"
            )
        lines.append("")

    # PRs without CodeRabbit decision
    no_coderabbit = [result for result in results if not result.coderabbit.found]
    if no_coderabbit:
        lines.extend([
            "## PRs Without CodeRabbit Decision",
            "",
            "| PR | Analyzer Decision | Reason |",
            "|----|-------------------|--------|",
        ])
        for pr_result in no_coderabbit:
            if pr_result.analyzer.success:
                decision = "Run" if pr_result.analyzer.should_run else "Skip"
                reason = (pr_result.analyzer.reason or "N/A")[:50]
            else:
                decision = "Error"
                reason = (pr_result.analyzer.error or "Unknown")[:50]
            lines.append(f"| [#{pr_result.pr_number}]({pr_result.pr_url}) | {decision} | {reason} |")
        lines.append("")

    # Analyzer errors
    errors = [result for result in results if not result.analyzer.success]
    if errors:
        lines.extend([
            "## Analyzer Errors",
            "",
            "| PR | Error |",
            "|----|-------|",
        ])
        for error_result in errors:
            error_message = (error_result.analyzer.error or "Unknown")[:100]
            lines.append(f"| [#{error_result.pr_number}]({error_result.pr_url}) | {error_message} |")
        lines.append("")

    # Detailed results
    lines.extend([
        "## All Results",
        "",
        "| PR | Author | CodeRabbit | Analyzer | Match |",
        "|----|--------|------------|----------|-------|",
    ])
    for result in results:
        coderabbit_status = "Run" if result.coderabbit.should_run else ("Skip" if result.coderabbit.found else "N/A")
        analyzer_status = "Run" if result.analyzer.should_run else ("Skip" if result.analyzer.success else "Error")
        match_str = "✓" if result.match else ("✗" if result.match is False else "-")
        lines.append(
            f"| [#{result.pr_number}]({result.pr_url}) | {result.pr_author} | "
            f"{coderabbit_status} | {analyzer_status} | {match_str} |"
        )

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compare CodeRabbit's smoke test decisions with local pytest marker analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--output",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of PRs to analyze",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--detailed",
        "-d",
        action="store_true",
        help="Include detailed dependency chain analysis for mismatches",
    )

    args = parser.parse_args()

    # Note: verbose flag kept for backward compatibility but INFO is always used
    if args.verbose:
        logger.info(msg="Verbose mode enabled", extra={"verbose": True})

    # Get GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning(
            msg="GITHUB_TOKEN not set, API rate limits will apply",
            extra={"hint": "Set GITHUB_TOKEN environment variable for better performance"},
        )

    # Fetch open PRs
    logger.info(msg="Fetching open PRs", extra={"repo": args.repo})
    prs = get_open_prs(repo=args.repo, token=token)

    if not prs:
        logger.info(msg="No open PRs found", extra={"repo": args.repo})
        return 0

    # Apply limit if specified
    if args.limit:
        prs = prs[: args.limit]
        logger.info(msg="Limited PR count", extra={"count": len(prs)})

    # Compare each PR
    results = []
    for pr in prs:
        result = compare_pr(repo=args.repo, pr=pr, token=token)
        results.append(result)

    # Generate output
    if args.output == "json":
        output = json.dumps([result.to_dict() for result in results], indent=2)
    else:
        output = generate_markdown_report(results=results, repo=args.repo, detailed=args.detailed)

    # Write output
    if args.output_file:
        args.output_file.write_text(data=output, encoding="utf-8")
        logger.info(msg="Report written", extra={"output_file": str(args.output_file)})
    else:
        print(output)

    # Summary
    comparable = [result for result in results if result.match is not None]
    matches = [result for result in comparable if result.match]

    if comparable:
        accuracy = (len(matches) / len(comparable)) * 100
        logger.info(
            msg="Agreement rate calculated",
            extra={"accuracy": f"{accuracy:.1f}%", "matches": len(matches), "comparable": len(comparable)},
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
