# GitHub PR Force-Push Event Reporter

Generates a markdown report of force-push events for a GitHub pull request, with clickable comparison links.

## Prerequisites

- **GitHub CLI (`gh`)** - [Installation guide](https://cli.github.com/)
- **Authentication** - Run `gh auth login` before first use

## Installation

No additional installation needed. The script uses the project's existing dependencies.

## Usage

```bash
# Basic usage
uv run python scripts/pr_tools/force_push_report.py https://github.com/owner/repo/pull/123

# Limit number of events fetched
uv run python scripts/pr_tools/force_push_report.py --page-size 50 https://github.com/owner/repo/pull/123
```

## Example Output

```markdown
## Force-Push Events for PR #35

1. [2026-02-17 12:55:53 UTC](https://github.com/owner/repo/compare/abc1234...def5678) - `abc1234` → `def5678` by username1
2. [2026-02-18 09:30:12 UTC](https://github.com/owner/repo/compare/def5678...ghi9012) - `def5678` → `ghi9012` by username2
3. [2026-02-19 14:15:45 UTC](https://github.com/owner/repo/compare/ghi9012...jkl3456) - `ghi9012` → `jkl3456` by username1
```

Each line contains:
- **Timestamp** - When the force-push occurred (clickable link to GitHub compare view)
- **Commit SHAs** - Before and after commits (shortened to 7 characters)
- **Actor** - GitHub username who performed the force-push

## Common Errors

### `gh CLI not found`

**Solution:** Install GitHub CLI from https://cli.github.com/

```bash
# Fedora/RHEL
sudo dnf install gh

# macOS
brew install gh

# Ubuntu/Debian
sudo apt install gh
```

### `GitHub API error: HTTP 401`

**Solution:** Authenticate with GitHub CLI:

```bash
gh auth login
```

### `Invalid GitHub PR URL format`

**Solution:** Ensure URL follows this exact format:

```
https://github.com/owner/repo/pull/NUMBER
```

## CI Integration Example

```bash
# Generate report and save to file
uv run python scripts/pr_tools/force_push_report.py \
  https://github.com/RedHatQE/cnv-tests/pull/3783 > force_push_report.md

# Use in CI to detect force-pushes during code freeze
FORCE_PUSHES=$(uv run python scripts/pr_tools/force_push_report.py "$PR_URL" | grep -c "→" || true)
if [ "$FORCE_PUSHES" -gt 0 ]; then
  echo "Warning: PR has $FORCE_PUSHES force-push(es)"
fi
```

## Technical Details

- **API**: GitHub GraphQL API via `gh` CLI
- **Event Type**: `HEAD_REF_FORCE_PUSHED_EVENT`
- **Timeout**: 30 seconds for API requests
- **Default Page Size**: 100 events
- **Output Format**: GitHub-flavored Markdown

## Related Scripts

- `scripts/tests_analyzer/` - Test analysis tools
- `scripts/quarantine_stats/` - Quarantine statistics dashboard
