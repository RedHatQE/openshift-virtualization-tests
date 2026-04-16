#!/usr/bin/env python3
# Generated using Claude cli

"""GitHub PR Force-Push Event Reporter."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)


@dataclass
class ForcePushEvent:
    """Represents a force-push event in a GitHub PR."""

    timestamp: str
    actor: str
    before_commit: str
    after_commit: str
    before_commit_full: str
    after_commit_full: str


@dataclass
class ParsedPRUrl:
    """Parsed GitHub PR URL components."""

    owner: str
    repo: str
    pr_number: int
    base_url: str


def parse_pr_url(pr_url: str) -> ParsedPRUrl:
    """Parse GitHub PR URL into components.

    Args:
        pr_url: GitHub PR URL in format https://github.com/owner/repo/pull/NUMBER

    Returns:
        ParsedPRUrl with extracted owner, repo, pr_number, and base_url

    Raises:
        ValueError: If URL format is invalid
    """
    pattern = r"^https://github\.com/([a-zA-Z0-9][a-zA-Z0-9._-]*)/([a-zA-Z0-9][a-zA-Z0-9._-]*)/pull/(\d+)/?$"
    match = re.match(pattern=pattern, string=pr_url)

    if not match:
        raise ValueError("Invalid GitHub PR URL format. Expected: https://github.com/owner/repo/pull/NUMBER")

    owner = match.group(1)
    repo = match.group(2)
    pr_number = int(match.group(3))
    base_url = f"https://github.com/{owner}/{repo}"

    return ParsedPRUrl(owner=owner, repo=repo, pr_number=pr_number, base_url=base_url)


def build_graphql_query(owner: str, repo: str, pr_number: int, page_size: int = 100) -> str:
    """Build GraphQL query for PR force-push events.

    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: Pull request number
        page_size: Maximum events to fetch per page

    Returns:
        GraphQL query string
    """
    query = f"""
    {{
      repository(owner: "{owner}", name: "{repo}") {{
        pullRequest(number: {pr_number}) {{
          timelineItems(itemTypes: [HEAD_REF_FORCE_PUSHED_EVENT], first: {page_size}) {{
            nodes {{
              ... on HeadRefForcePushedEvent {{
                createdAt
                actor {{
                  login
                }}
                beforeCommit {{
                  oid
                }}
                afterCommit {{
                  oid
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    return query


def query_github_graphql(query: str) -> dict[str, Any]:
    """Execute GraphQL query using gh CLI.

    Args:
        query: GraphQL query string

    Returns:
        Parsed JSON response from GitHub API

    Raises:
        RuntimeError: If gh CLI is missing, auth fails, or API returns error
    """
    # Check gh CLI availability
    try:
        subprocess.run(
            args=["gh", "--version"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gh CLI not found. Install via: https://cli.github.com/") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"gh CLI check failed: {exc.stderr.decode()}") from exc

    # Execute GraphQL query
    try:
        result = subprocess.run(
            args=["gh", "api", "graphql", "-f", f"query={query}"],
            check=True,
            capture_output=True,
            timeout=30,
            text=True,
        )
        LOGGER.info("GitHub API query successful")
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub API request timed out after 30 seconds") from exc
    except subprocess.CalledProcessError as exc:
        error_msg = exc.stderr if exc.stderr else "Unknown error"
        raise RuntimeError(f"GitHub API error: {error_msg}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse GitHub API response: {exc}") from exc


def parse_force_push_events(response: dict[str, Any]) -> list[ForcePushEvent]:
    """Parse force-push events from GraphQL response.

    Args:
        response: Parsed JSON response from GitHub GraphQL API

    Returns:
        List of ForcePushEvent objects sorted chronologically (oldest first)
    """
    events: list[ForcePushEvent] = []

    try:
        nodes = response["data"]["repository"]["pullRequest"]["timelineItems"]["nodes"]
    except (KeyError, TypeError) as exc:
        LOGGER.warning(f"Unexpected response structure: {exc}")
        return events

    for node in nodes:
        try:
            timestamp = node["createdAt"]
            actor = node["actor"]["login"]
            before_full = node["beforeCommit"]["oid"]
            after_full = node["afterCommit"]["oid"]

            event = ForcePushEvent(
                timestamp=timestamp,
                actor=actor,
                before_commit=before_full[:7],
                after_commit=after_full[:7],
                before_commit_full=before_full,
                after_commit_full=after_full,
            )
            events.append(event)
        except (KeyError, TypeError) as exc:
            LOGGER.warning(f"Skipping malformed event: {exc}")
            continue

    # Sort chronologically (oldest first)
    events.sort(key=lambda event: event.timestamp)

    return events


def format_markdown_report(parsed_url: ParsedPRUrl, events: list[ForcePushEvent]) -> str:
    """Format force-push events as markdown report.

    Args:
        parsed_url: Parsed PR URL components
        events: List of force-push events

    Returns:
        Markdown formatted report string
    """
    report_lines = [f"## Force-Push Events for PR #{parsed_url.pr_number}", ""]

    if not events:
        report_lines.append("No force-push events found for this pull request.")
        return "\n".join(report_lines)

    for idx, event in enumerate(iterable=events, start=1):
        # Parse ISO 8601 timestamp and format as "YYYY-MM-DD HH:MM:SS UTC"
        timestamp_dt = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        formatted_time = timestamp_dt.strftime(format="%Y-%m-%d %H:%M:%S UTC")

        # Generate compare URL
        compare_url = f"{parsed_url.base_url}/compare/{event.before_commit_full}..{event.after_commit_full}"

        # Format line
        line = (
            f"{idx}. [{formatted_time}]({compare_url}) - "
            f"`{event.before_commit}` → `{event.after_commit}` by {event.actor}"
        )
        report_lines.append(line)

    return "\n".join(report_lines)


def main() -> int:
    """Main entry point for force-push event reporter.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="Generate force-push event report for GitHub PR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pr_url",
        help="GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Maximum number of events to fetch (default: 100)",
    )

    args = parser.parse_args()

    try:
        # Parse PR URL
        parsed_url = parse_pr_url(pr_url=args.pr_url)

        # Build and execute GraphQL query
        query = build_graphql_query(
            owner=parsed_url.owner,
            repo=parsed_url.repo,
            pr_number=parsed_url.pr_number,
            page_size=args.page_size,
        )
        response = query_github_graphql(query=query)

        # Parse events
        events = parse_force_push_events(response=response)

        # Format and print report
        report = format_markdown_report(parsed_url=parsed_url, events=events)
        print(report)

        return 0

    except ValueError as exc:
        LOGGER.error(f"Invalid input: {exc}")
        return 1
    except RuntimeError as exc:
        LOGGER.error(f"Operation failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
