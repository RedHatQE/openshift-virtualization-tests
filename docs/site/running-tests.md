# Running and Filtering Tests

Execute test suites against your cluster, leverage pytest markers to filter by test domain or complexity, and run the test harness inside an isolated container.

## Prerequisites

- A fully configured Python environment using `uv`. See [Quickstart & Setup](quickstart.html) for details.
- A valid OpenShift cluster connection (via the `KUBECONFIG` environment variable or `~/.kube/config`).
- For containerized execution: `podman` or `docker` installed on your machine.

## Quick Example

To run a specific test file using the project's dependency manager:

```bash
uv run pytest tests/network/connectivity/test_pod_network.py
```

To run all basic network tests while excluding complex configurations:

```bash
uv run pytest tests/network -m "tier2 and not tier3"
```

## Step-by-Step Guide

Follow these steps to filter and run tests effectively:

1. **Use the `uv` wrapper:** Always prefix your commands with `uv run`. This ensures the test suite executes within the correctly resolved virtual environment.
   > **Warning:** Never execute `pytest`, `tox`, or `python` directly. Always use the `uv run` prefix.

2. **Select the target path:** Pass the directory or specific test file you want to validate. Pointing pytest directly to the domain folder saves collection time.
   ```bash
   uv run pytest tests/storage/
   ```

3. **Filter using markers:** Use the `-m` flag to specify which markers to include or exclude. You can combine markers using `and`, `or`, and `not`.
   ```bash
   # Run only virtualization tests marked for gating
   uv run pytest tests/virt -m "gating"
   ```

4. **Run full local validations:** Before pushing code, validate everything using `tox`. This runs linting, formatting, and utilities unit tests.
   ```bash
   uv run tox
   ```

## Advanced Usage

### Marker Categories

The test framework categorizes markers into two types. Understanding this distinction is critical for targeting the right tests.

| Marker Category | Examples | Application Method | Purpose |
|-----------------|----------|--------------------|---------|
| **Implicit** | `tier2`, `network`, `storage`, `virt`, `chaos` | Automatically applied by the framework based on the test's directory location or default rules. | Defines standard customer use cases and categorizes tests into feature domains without cluttering the code. |
| **Explicit** | `tier3`, `gating`, `special_infra`, `gpu`, `dpdk` | Manually added to the test code using `@pytest.mark.<marker>`. | Identifies tests with specific hardware requirements, advanced configurations, or those that strictly block release promotion. |

### Handling Special Infrastructure

When writing or running tests that require specific cluster capabilities (like GPU, SR-IOV, or hugepages), they must be explicitly targeted. These tests use the `special_infra` marker alongside their specific requirement marker.

To run tests that require DPDK:

```bash
uv run pytest -m "special_infra and dpdk"
```

See [Implementing New Tests](implementing-tests.html) for more information on applying infrastructure markers correctly in your code.

### Running Tests in a Container

For environments with strict network boundaries (like disconnected clusters) or CI/CD pipelines, you can build and execute the entire test suite from within a container image.

1. **Build the container image:**
   ```bash
   make build-container
   ```

2. **Execute the tests via Podman:** Mount your local kubeconfig into the container so it can authenticate and communicate with the cluster.
   ```bash
   podman run --rm \
     -v ~/.kube/config:/root/.kube/config:z \
     quay.io/openshift-cnv/openshift-virtualization-tests-github:latest \
     pytest tests/virt -m "tier2"
   ```

## Troubleshooting

- **No tests were collected:** Ensure you are passing the correct directory path and that your marker syntax is valid. Tests lacking explicit exclusion markers are implicitly tagged as `tier2`. If you filter for an explicit marker without considering the implicit ones, you might get zero collected items.
- **Dependency errors or ModuleNotFoundError:** You bypassed `uv`. Ensure you are running `uv run pytest` rather than invoking `pytest` directly.
- **Authentication failures in container:** When using `podman run`, double-check the `:z` flag on your volume mount. It handles SELinux context labeling so the container is permitted to read your `kubeconfig` file.

## Related Pages

- [Quickstart & Setup](quickstart.html)
- [Virtualization Tests](virt-tests.html)
- [Pytest Fixture Strategy](fixture-strategy.html)
