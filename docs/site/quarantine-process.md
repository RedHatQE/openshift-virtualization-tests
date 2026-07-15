# Test Quarantine Process

Temporarily disable failing tests to keep continuous integration (CI) lanes green while teams investigate root causes. Categorize failures correctly to ensure product bugs are tracked separately from automated test code issues.

## Prerequisites

- A failing test identified in the CI pipeline.
- An open Jira ticket (Bug for product defects, Task for automation issues).
- Local testing environment configured (See [Quickstart & Setup](quickstart.html)).

## Quick Examples

### Quarantining an Automation Issue

Disable a test when the failure is caused by a test framework or automation script bug:

```python
import pytest
from utilities.constants.pytest import QUARANTINED

@pytest.mark.xfail(
    reason=f"{QUARANTINED}: VM goes into running state unexpectedly, CNV-12345",
    run=False,
)
def test_vm_lifecycle():
    ...
```

### Skipping for a Product Bug

Disable a test conditionally when an actual product defect causes the failure:

```python
import pytest

@pytest.mark.jira("CNV-54321", run=False)
def test_new_feature():
    ...
```

## Quarantine Methods Compared

| Failure Type | Description | Required Action | Pytest Marker | Re-enable Condition |
| --- | --- | --- | --- | --- |
| **Product Bug** | Feature is broken in the product. | Open a Jira Bug. | `@pytest.mark.jira("...", run=False)` | Automatic when the Jira bug transitions to resolved. |
| **Automation Issue** | Test code is flawed or flaky. | Open a Jira Task. | `@pytest.mark.xfail(reason=..., run=False)` | Manual PR to remove the marker after a proven fix. |
| **Environment** | Infrastructure/cluster issue. | Open a DevOps ticket. | **Do NOT Quarantine** | N/A (fix the environment). |

## Step-by-Step: Managing a Failing Test

1. **Analyze the Failure**
   Determine if the failure originates from the OpenShift cluster (Product Bug), the test framework (Automation Issue), or external dependencies (System Issue).
2. **Verify Manually**
   Attempt the test steps manually on a test cluster. If the manual steps succeed but the automation fails, you have an automation issue.
3. **Open a Jira Ticket**
   Include specific failure logs, error messages, and steps to reproduce. Avoid generic titles like "Test failed".
4. **Apply the Correct Marker**
   Add either the `@pytest.mark.xfail` or `@pytest.mark.jira` marker directly above the test function definition.
5. **Submit a Pull Request**
   Prefix the PR title with `Quarantine: ` and include a brief explanation alongside a link to the Jira ticket in the description.

## Advanced Usage

### Running Quarantined Tests Locally

The test suite automatically assigns the `quarantined` marker to tests using the `xfail` format. You can isolate these tests to verify potential fixes:

```bash
# Run only quarantined tests
uv run pytest -m quarantined

# Run tests that are NOT quarantined
uv run pytest -m "not quarantined"

# Combine with other domain markers
uv run pytest -m "quarantined and storage"
```

> **Tip:** See [Running and Filtering Tests](running-tests.html) for more selection commands.

### The De-Quarantine Process

Before removing an `xfail` quarantine marker, you must prove the test is stable.

1. Fix the underlying automation issue.
2. Enhance assertion messages if the original failure lacked context.
3. Run the test consecutively 25 times against an identical cluster setup.

```bash
# Verify stability locally
uv run pytest --repeat-scope=session --count=25 path/to/test_file.py
```

4. Submit a PR removing the `xfail` marker and update the Jira ticket with your local verification results.

## Troubleshooting

- **Test runs despite Jira marker:** Ensure the Jira bug is open. The `pytest_jira` plugin automatically executes the test if the ticket is closed.
- **Marker not detected:** Ensure you include `run=False` in your `xfail` or `jira` markers to prevent test execution.
- **Merge Blocked:** Check if you accidentally used `@pytest.mark.skip` or `pytest.skip()`. The project strictly forbids native skip methods in favor of the workflow above.

## Related Pages

- [Test Design Workflow (STP/STD)](test-design-workflow.html)
- [Running and Filtering Tests](running-tests.html)
- [Operations & Chaos](operations-chaos.html)
