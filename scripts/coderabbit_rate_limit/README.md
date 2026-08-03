# CodeRabbit Rate Limit Handler

CLI tool for detecting and recovering from CodeRabbit rate limiting and reviews-paused states on pull requests.

## Prerequisites

- `gh` CLI authenticated with a token that has `pull-requests:write` scope

## Commands

### check

Detect rate limiting or reviews-paused state on a PR. Outputs JSON to stdout.

```bash
uv run coderabbit-rate-limit check <owner/repo> <pr_number>
```

**JSON output shapes:**

| State | Output |
|-------|--------|
| Clear | `{"rate_limited": false, "reviews_paused": false}` |
| Rate limited | `{"rate_limited": true, "reviews_paused": false, "wait_seconds": N, "comment_id": N}` |
| Reviews paused | `{"rate_limited": false, "reviews_paused": true, "comment_id": N}` |

Exit code `0` on success (JSON written), `1` on error.

### trigger

Wait then re-trigger a CodeRabbit review. Polls until review starts (max 10 minutes).

```bash
uv run coderabbit-rate-limit trigger <owner/repo> <pr_number> --wait <seconds>
```

Add ~30 seconds buffer to the `wait_seconds` from `check` output.

### resume

Resume paused CodeRabbit reviews by posting `@coderabbitai resume`.

```bash
uv run coderabbit-rate-limit resume <owner/repo> <pr_number>
```

## Typical Recovery Workflow

```bash
# 1. Check if rate limited
result=$(uv run coderabbit-rate-limit check RedHatQE/openshift-virtualization-tests 5869)

# 2a. If rate limited — wait and trigger
wait=$(echo "$result" | jq '.wait_seconds')
uv run coderabbit-rate-limit trigger RedHatQE/openshift-virtualization-tests 5869 --wait $((wait + 30))

# 2b. If reviews paused — resume
uv run coderabbit-rate-limit resume RedHatQE/openshift-virtualization-tests 5869
```
