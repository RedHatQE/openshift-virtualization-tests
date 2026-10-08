# NMState Network Tests

Domain-specific guidance for `tests/network/nmstate/`.

## Cluster-Type Conditional Behaviour

NMState functionality is **bypassed on cloud clusters** (Azure/AWS) and only functional on
**bare-metal/PSI clusters**. When writing or reviewing nmstate tests, account for this:

- Tests that exercise NMState CRs (NNCP, NNCE, NNS) will not run meaningfully on cloud clusters.
- CI may filter these tests out via the `nmstate` marker on cloud environments.
- Do not assume nmstate is available without verifying the cluster type.
