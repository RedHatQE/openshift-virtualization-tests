Generated using Claude cli

# Pytest Marker Analyzer

**Static dependency analysis for pytest marker-based test selection**

Analyzes PR changes to determine if tests with specific markers should run based on static dependency analysis. This script replaces CodeRabbit's AI-based analysis with a deterministic, offline-capable solution.

## Overview

The Pytest Marker Analyzer provides intelligent test execution decisions by:

- **Discovering tests** matching specified pytest marker expressions (e.g., `@pytest.mark.smoke`)
- **Tracing dependencies** via AST analysis (imports, fixtures, conftest.py files)
- **Matching changes** against dependency trees to identify affected tests
- **Returning decisions** in JSON or Markdown format for CI integration

This enables CI pipelines to skip expensive test suites when changes don't affect the relevant test dependencies, while ensuring critical tests run when needed.

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   INPUT     │───▶│   ANALYSIS   │───▶│   OUTPUT    │
│ Git/GitHub  │    │ AST parsing  │    │ JSON/MD     │
└─────────────┘    └──────────────┘    └─────────────┘
     │                    │                    │
     │                    │                    │
  Changed              Test                Decision
   files           dependencies          (Run/Skip)
```

## How It Works

1. **Get changed files** - Fetch changed files via git diff or GitHub API
2. **Discover tests** - Find tests matching marker expression using pytest collection
3. **Trace dependencies** - Build dependency trees via AST analysis:
   - Direct imports (`import X`, `from X import Y`)
   - Fixtures (function parameters + decorators)
   - conftest.py files in directory hierarchy
   - Transitive imports (2 levels deep)
   - Fixture dependency graph (fixtures using other fixtures)
   - Functions called by fixtures
4. **Match changed files** - Compare changed files against dependency trees
5. **Return decision** - Output JSON or Markdown with affected tests list

## Decision Logic

### RUN tests if:
- Changed file is in a marked test's dependency tree (includes direct imports, fixtures, conftest in hierarchy, and transitive imports)
- For conftest.py changes: Only run tests that use affected fixtures
  - Uses git diff to identify which specific fixtures/functions were modified
  - Computes transitive fixture dependencies
  - Only triggers if marked test uses at least one affected fixture

### SKIP tests if:
- No marked test dependencies are affected
- Changes are documentation-only
- conftest.py modified but only changed fixtures NOT used by marked tests

### Smart conftest.py Detection:
- Parses git diff to identify modified function/fixture names
- Uses AST to determine which functions are fixtures
- Computes transitive impact (fixtures that depend on modified fixtures)
- Only triggers marked tests that actually use affected fixtures
- Falls back to conservative behavior if git diff fails

**Note:** Infrastructure (utilities/, libs/) and conftest.py changes only trigger marked tests if they are actually imported/used by a marked test. Blanket rules that triggered on ANY infrastructure or conftest change have been removed to reduce false positives.

## Installation / Requirements

- Uses the repo's requirements

## Usage Examples

### Local Mode

Analyze current branch against main:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py
```

Analyze specific files:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --files path/to/file1.py path/to/file2.py
```

Compare against specific base branch:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py --base develop
```

### GitHub PR Mode

Most common for CI:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo owner/repo --pr 123
```

With explicit token:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo owner/repo --pr 123 --github-token ghp_xxx
```

With checkout (for CI without pre-checkout):
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo owner/repo --pr 123 --checkout
```

### Marker Expressions

Single marker:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py --markers smoke
```

AND logic:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --markers "smoke and tier2"
```

OR logic:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --markers "smoke or gating"
```

NOT logic:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --markers "gating and not ipv4"
```

Complex expressions:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --markers "(tier2 or tier3) and not gpu"
```

### Output Formats

JSON for CI consumption:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --output json
```

Write output to directory (for CI artifacts):
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --output json --output-dir /tmp/results
```

Enable verbose logging:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py --verbose
```

## Running in Container

When using the openshift-virtualization-tests container image:

```bash
podman run -v "$(pwd)":/mnt/host:Z \
  quay.io/openshift-cnv/openshift-virtualization-tests \
  uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo owner/repo --pr 123
```

## Output Formats

### Markdown (default)

Human-readable summary:

```markdown
## Test Execution Plan

**Run tests with marker expression `smoke`: true**

**Reason:** Changes affect 3 test(s) with marker expression: smoke

### Affected tests with marker expression `smoke`:
- `tests/virt/test_vm.py::test_create`
  - Test file: `tests/virt/test_vm.py`
  - Dependencies affected: 1
    - `utilities/virt.py`

**Total tests with marker expression `smoke`:** 20
**Changed files:** 1
```

### JSON

Machine-readable for CI:

```json
{
  "should_run_tests": true,
  "reason": "Changes affect 3 test(s) with marker expression: smoke",
  "marker_expression": "smoke",
  "affected_tests": [
    {
      "node_id": "tests/virt/test_vm.py::test_create",
      "test_name": "test_create",
      "test_file": "tests/virt/test_vm.py",
      "dependencies": ["utilities/virt.py"]
    }
  ],
  "total_tests": 20,
  "changed_files": ["utilities/virt.py"]
}
```

## CI Integration

### Using Shell Script Wrapper

The included `example_ci_integration.sh` provides a complete CI integration example:

```bash
./scripts/test_analyzer/example_ci_integration.sh --markers smoke
```

This script:
- Runs the analyzer with JSON output
- Parses the decision
- Sets environment variable: `TESTS_REQUIRED=true/false`
- Displays affected tests
- Exits with appropriate status code

### Manual CI Integration

Example Jenkins/GitHub Actions workflow:

```bash
# Run analyzer
RESULT=$(uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo $REPO --pr $PR_NUMBER --output json)

# Parse decision
SHOULD_RUN=$(echo "$RESULT" | jq -r '.should_run_tests')

if [ "$SHOULD_RUN" = "true" ]; then
  echo "Running smoke tests..."
  pytest -m smoke
else
  echo "Skipping smoke tests (no dependencies affected)"
fi
```

### External Reporting

Report decision to Jenkins input step:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo owner/repo --pr 123 \
  --report-url "https://jenkins.example.com/job/smoke/buildWithParameters" \
  --report-format form \
  --report-token "$JENKINS_TOKEN"
```

Report to webhook with JSON:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo owner/repo --pr 123 \
  --report-url "https://webhook.example.com/smoke-decision" \
  --report-format json \
  --report-header "X-Custom-Header: value"
```

Supported formats:
- **json**: POST request with JSON body (default)
- **form**: POST request with form-encoded data
- **query**: GET request with query parameters

## Tools Included

### 1. pytest_marker_analyzer.py

Main analyzer tool for determining if tests should run.

**Features:**
- Pytest marker expression support (AND, OR, NOT logic)
- Local git mode and GitHub PR mode
- Smart conftest.py fixture-level analysis
- Transitive dependency tracking
- JSON and Markdown output formats

### 2. example_ci_integration.sh

Shell wrapper for CI integration.

**Usage:**
```bash
./scripts/test_analyzer/example_ci_integration.sh --markers smoke
./scripts/test_analyzer/example_ci_integration.sh \
  --markers "smoke and sanity"
./scripts/test_analyzer/example_ci_integration.sh --help
```

**Features:**
- Validates JSON output
- Sets TESTS_REQUIRED environment variable
- Displays affected tests
- Color-coded output
- Graceful fallback without jq

## Security Features

- **Strict repo name validation** - Prevents command injection
- **Token never embedded in URLs** - Prevents exposure in logs
- **Symlink validation** - Prevents path traversal
- **Response size limits** - Prevents memory exhaustion
- **Timeouts on all subprocess calls** - Prevents hangs

## GitHub API Integration

When analyzing remote PRs (`--repo/--pr` without `--checkout`):

- Uses GitHub API to fetch PR file diffs instead of local git
- Enables accurate fixture-level analysis without local checkout
- Requires `GITHUB_TOKEN` for authentication and higher rate limits

Example:
```bash
export GITHUB_TOKEN=ghp_xxx
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo owner/repo --pr 123
```

## Advanced Options

### Work Directory Control

Use custom temporary directory:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --repo owner/repo --pr 123 --checkout \
  --work-dir /mnt/workspace/temp
```

Useful in Jenkins to use workspace directory instead of system temp.

### Output Directory

Write results to specific directory:
```bash
uv run python scripts/test_analyzer/pytest_marker_analyzer.py \
  --output json --output-dir /tmp/results
```

Creates `marker_analysis.json` or `marker_analysis.md` in specified directory.

## Environment Variables

- `GITHUB_TOKEN` - GitHub API token for authentication
- `TESTS_REQUIRED` - Set by CI integration script (true/false)

## Exit Codes

- **0** - Success
- **1** - Error (analyzer failure, no tests found, invalid arguments)

## Contributing

When modifying the analyzer:

1. Test with various marker expressions
2. Verify fixture-level conftest.py analysis
3. Test both local and GitHub PR modes
4. Update tests if adding new features
5. Run comparison tool to validate against CodeRabbit

## License

See repository license.

## Related Documentation

- [pytest markers documentation](https://docs.pytest.org/en/stable/how-to/mark.html)
- [AST module documentation](https://docs.python.org/3/library/ast.html)
- [GitHub REST API](https://docs.github.com/en/rest)
- [uv documentation](https://github.com/astral-sh/uv)
