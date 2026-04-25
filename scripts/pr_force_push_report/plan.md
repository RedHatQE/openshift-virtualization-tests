# Force-Push Event Reporter Script - Implementation Plan

## Context

The user frequently needs to review force-push history for GitHub pull requests to understand what changes were made during the review process. Currently, this requires manual querying of the GitHub API and formatting the results. This script automates the process by:

- Accepting a GitHub PR URL as input
- Querying the GitHub GraphQL API for force-push events
- Generating a markdown report with clickable comparison links

This enables quick analysis of PR revision history for code review and debugging purposes.

## Approach

Create a standalone Python script `scripts/pr_tools/force_push_report.py` that:
1. Uses `gh` CLI with GraphQL API (user preference, handles auth automatically)
2. Outputs markdown format with clickable GitHub compare links (user preference)
3. Follows existing script patterns from `scripts/tests_analyzer/` and `scripts/quarantine_stats/`

## File Structure

```
scripts/pr_tools/
├── __init__.py              # Empty package marker
├── force_push_report.py     # Main executable script
├── README.md                # Usage documentation
└── plan.md                  # Design document (copy of this plan)
```

## Implementation Details

### Script Header
```python
#!/usr/bin/env python3

"""GitHub PR Force-Push Event Reporter"""

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
```

### Data Models

**ForcePushEvent dataclass:**
- `timestamp: str` - ISO 8601 timestamp
- `actor: str` - GitHub username
- `before_commit: str` - Short SHA (7 chars) for display
- `after_commit: str` - Short SHA (7 chars) for display
- `before_commit_full: str` - Full SHA for URLs
- `after_commit_full: str` - Full SHA for URLs

**ParsedPRUrl dataclass:**
- `owner: str` - Repository owner
- `repo: str` - Repository name
- `pr_number: int` - PR number
- `base_url: str` - Base repo URL for compare links

### Core Functions

1. **`parse_pr_url(pr_url: str) -> ParsedPRUrl`**
   - Regex: `r"^https://github\.com/([a-zA-Z0-9][a-zA-Z0-9._-]*)/([a-zA-Z0-9][a-zA-Z0-9._-]*)/pull/(\d+)/?$"`
   - Raises `ValueError` on invalid URL
   - Returns `ParsedPRUrl` with extracted components

2. **`build_graphql_query(owner: str, repo: str, pr_number: int, page_size: int = 100) -> str`**
   - Returns GraphQL query string for `HEAD_REF_FORCE_PUSHED_EVENT` timeline items
   - Fetches: `createdAt`, `actor.login`, `beforeCommit.oid`, `afterCommit.oid`

3. **`query_github_graphql(query: str) -> dict[str, Any]`**
   - Checks `gh` CLI availability first (`gh --version`)
   - Executes: `gh api graphql -f query={query}` via subprocess
   - Timeout: 30 seconds
   - Raises `RuntimeError` on gh CLI missing, auth failure, API errors
   - Returns parsed JSON response

4. **`parse_force_push_events(response: dict[str, Any]) -> list[ForcePushEvent]`**
   - Navigates: `data.repository.pullRequest.timelineItems.nodes`
   - Extracts short (7-char) and full SHAs
   - Skips malformed events with WARNING logs
   - Sorts chronologically (oldest first)
   - Returns list of `ForcePushEvent` objects

5. **`format_markdown_report(parsed_url: ParsedPRUrl, events: list[ForcePushEvent]) -> str`**
   - Formats timestamps as "YYYY-MM-DD HH:MM:SS UTC"
   - Generates compare URLs: `{base_url}/compare/{before_full}..{after_full}`
   - Output format:
     ```markdown
     ## Force-Push Events for PR #123

     1. [2026-02-17 12:55:53 UTC](https://github.com/owner/repo/compare/abc1234..def5678) - `abc1234` → `def5678` by username
     ```
   - Handles empty events list: "No force-push events found for this pull request."

6. **`main() -> int`**
   - Argument parser with `pr_url` positional argument
   - Optional `--page-size` (default: 100)
   - Orchestrates all functions with named arguments
   - Catches `ValueError` and `RuntimeError` specifically
   - Logs errors at ERROR level with context
   - Returns exit code 0 (success) or 1 (error)

### Error Handling

| Error Type | Exception | Exit Code | User Message |
|------------|-----------|-----------|--------------|
| Invalid URL format | `ValueError` | 1 | "Invalid GitHub PR URL format. Expected: https://github.com/owner/repo/pull/NUMBER" |
| gh CLI missing | `RuntimeError` | 1 | "gh CLI not found. Install via: https://cli.github.com/" |
| API failure | `RuntimeError` | 1 | "GitHub API error: {details from stderr}" |
| Network timeout | `RuntimeError` | 1 | "GitHub API request timed out after 30 seconds" |
| No force-pushes | (not error) | 0 | "No force-push events found for this pull request." |

All exceptions re-raised with `from exc` to preserve stack traces.

### Existing Patterns to Follow

**From `scripts/tests_analyzer/compare_coderabbit_decisions.py`:**
- Shebang: `#!/usr/bin/env python3`
- Comment: `# Generated using Claude cli`
- Logging: `logger = get_logger(name=__name__)` (note: lowercase `logger` used in this file)
- Dataclass usage for data modeling
- ArgumentParser with `RawDescriptionHelpFormatter`

**From `scripts/quarantine_stats/generate_dashboard.py`:**
- Logging: `LOGGER = get_logger(name=__name__)` (note: uppercase `LOGGER` used in this file)
- Subprocess with explicit timeouts
- Named arguments for function calls

**Project standards (CLAUDE.md):**
- Type hints mandatory on all public functions
- Google-format docstrings for public functions
- Named arguments for 2+ parameter function calls
- No single-letter variables
- Import pattern: `from module import func`
- INFO logging for API responses
- ERROR logging for exceptions with context

**Note:** Use uppercase `LOGGER` to match the project standard in CLAUDE.md.

## Implementation Steps

1. Create directory structure:
   ```bash
   mkdir -p scripts/pr_tools
   touch scripts/pr_tools/__init__.py
   ```

2. Create `force_push_report.py`:
   - Add shebang, docstring, imports
   - Implement data models (dataclasses)
   - Implement functions in order: parse_pr_url → build_graphql_query → query_github_graphql → parse_force_push_events → format_markdown_report → main
   - Add `if __name__ == "__main__": sys.exit(main())`

3. Create `README.md` with:
   - Prerequisites (gh CLI installation)
   - Usage examples
   - Output format example
   - Common errors and solutions
   - CI integration example

4. Create `plan.md`:
   - Copy this design document to `scripts/pr_tools/plan.md` for future reference

5. Test manually:
   - Valid PR with force-pushes: `https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/35`
   - Valid PR without force-pushes (test empty case)
   - Invalid URL (test error handling)
   - Non-existent PR (test API error handling)

6. Run verification:
   ```bash
   pre-commit run --all-files
   ```

## Critical Files

**To create:**
- `scripts/pr_tools/force_push_report.py` - Main script (all logic)
- `scripts/pr_tools/README.md` - Documentation
- `scripts/pr_tools/__init__.py` - Empty package marker
- `scripts/pr_tools/plan.md` - Design document (copy of this plan)

**Reference patterns:**
- `scripts/tests_analyzer/compare_coderabbit_decisions.py` - URL validation, dataclasses, argparse
- `scripts/quarantine_stats/generate_dashboard.py` - Subprocess patterns, logging

## Verification

### Manual Testing
```bash
# Test with PR that has force-pushes
python scripts/pr_tools/force_push_report.py \
  https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/35

# Test with PR without force-pushes (if available)
python scripts/pr_tools/force_push_report.py \
  https://github.com/RedHatQE/cnv-tests/pull/XXXX

# Test invalid URL
python scripts/pr_tools/force_push_report.py "not-a-url"

# Test --page-size flag
python scripts/pr_tools/force_push_report.py --page-size 5 \
  https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/35
```

### Expected Behavior
- ✅ Markdown output with numbered list
- ✅ Clickable timestamp links to GitHub compare view
- ✅ Commit SHAs shortened to 7 characters in display
- ✅ Full SHAs in compare URLs (two-dot notation: `..`)
- ✅ Events sorted chronologically (oldest first)
- ✅ Empty events show friendly message
- ✅ Invalid URL returns exit code 1 with clear error
- ✅ Missing gh CLI returns helpful installation message
- ✅ All errors go to stderr
- ✅ Passes `pre-commit run --all-files`

### Linting
```bash
pre-commit run --all-files
```

All checks must pass before completion.
