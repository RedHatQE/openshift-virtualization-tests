# Quickstart & Setup

Get your Python environment configured using `uv`, validate your code quality tools, and execute your first OpenShift Virtualization test suite. This guide gets you up and running against a live cluster in minutes.

## Prerequisites

* A running OpenShift cluster with OpenShift Virtualization installed.
* Cluster admin access with the `KUBECONFIG` environment variable exported.
* Python 3.14 or newer.
* The [`uv` package manager](https://github.com/astral-sh/uv) installed on your workstation.
* Git.

## Quick Example

If you already have `uv` and a valid `KUBECONFIG`, you can run your first tests immediately:

```bash
git clone <repository-url> openshift-virtualization-tests
cd openshift-virtualization-tests

# Ensure pre-commit and linter checks pass
uv run pre-commit run --all-files

# Run basic virtualization tests
uv run pytest --tc-file=tests/global_config.py -m tier2 tests/virt/
```

## Step-by-step Setup

### 1. Install Tooling

The project strictly enforces `uv` for dependency management and test execution. Do not use `pip` or virtualenv directly.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Prepare the Repository

Clone the repository and verify your environment by running the pre-commit checks. This automatically provisions the required dependencies in an isolated environment.

```bash
git clone <repository-url> openshift-virtualization-tests
cd openshift-virtualization-tests

# Install dependencies and run linters
uv run pre-commit run --all-files
```

> **Note:** The `uv run` command automatically handles virtual environments and dependency resolution behind the scenes. See [Code Quality & Pre-commits](code-quality.html) for more details.

### 3. Configure Cluster Access

Tests interact with your OpenShift cluster using standard Kubernetes authentication.

```bash
export KUBECONFIG=/path/to/your/kubeconfig
```

### 4. Execute Tests

Always supply the global test configuration file when invoking pytest. This file dynamically loads parameters and defaults based on your cluster's architecture.

```bash
uv run pytest --tc-file=tests/global_config.py tests/network/
```

> **Tip:** You do not need to run the entire suite. Target specific domains like `tests/network/` or `tests/storage/`. For more domain details, see [Networking Tests](network-tests.html) and [Storage Tests](storage-tests.html).

## Advanced Usage

### CI Verification with Tox

Before submitting a pull request, you must ensure all Continuous Integration (CI) checks pass locally. The project uses Tox to orchestrate these checks.

```bash
# Run the full CI validation suite
uv run tox

# Run only the utility unit tests
uv run tox -e utilities-unittests
```

See [Pull Request Discipline](pr-discipline.html) for all required pre-merge checks.

### Multi-Architecture Environments

If testing against ARM64 or S390X clusters, configure the architecture environment variable before running tests so the framework pulls the correct container images.

```bash
export OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH=arm64
uv run pytest --tc-file=tests/global_config.py -m arm64 tests/virt/
```

See [Multi-Architecture Support](multi-architecture-testing.html) for topology constraints and advanced routing configurations.

### Filtering Test Execution

You can narrow down executions using tier markers and specific domains.

```bash
# Run complex/time-consuming storage tests
uv run pytest --tc-file=tests/global_config.py -m tier3 tests/storage/
```

See [Running and Filtering Tests](running-tests.html) for a complete list of available markers and execution methods.

## Troubleshooting

* **Missing test configuration:** If pytest fails with configuration errors or missing global variables, ensure you are passing `--tc-file=tests/global_config.py`. See [Configuration & Global Contexts](configuration-constants.html) for details.
* **Authentication failures:** Tests failing with `Unauthorized` or `Forbidden` usually mean an expired or unset `KUBECONFIG`. Validate your session by running `oc whoami` outside the test suite.
* **Linter suppression errors:** The project strictly prohibits `# noqa` or `# type: ignore`. If `uv run pre-commit run --all-files` fails, you must fix the code itself rather than ignoring the rule.

## Related Pages

- [Running and Filtering Tests](running-tests.html)
- [Implementing New Tests](implementing-tests.html)
- [Code Quality & Pre-commits](code-quality.html)
