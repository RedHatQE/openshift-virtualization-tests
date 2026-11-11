# NMState Network Tests

Domain-specific guidance for `tests/network/`.

## NMState-Dependent Tests

NMState-dependent tests are identified by the `nmstate_dependent_placeholder` fixture and marked dynamically. Before running them, the network session check verifies that the `openshift-nmstate` namespace exists and its pods are running; do not assume the operator is available without checking the target cluster.

- The `nmstate` marker is added automatically for tests that depend on NMState fixtures.
- Verify the target cluster's NMState installation and supported network configuration before running these tests.
