# File-Level Restore Tests

Tier 2 and Tier 3 tests for the HCO-managed [vm-file-restore-operator](https://github.com/kubevirt/vm-file-restore-operator).

Design: [VIRTSTRAT-480 STP](https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/VIRTSTRAT-480_file_level_restore.md)

## Coverage

- **Tier 2** — Linux scenarios (e.g. backup-vendor workflow); implicit `tier2` marker
- **Tier 3** — Windows guest scenarios; `@pytest.mark.tier3` and `@pytest.mark.windows`

## Prerequisites

- CNV cluster with the file-restore operator deployed by HCO
- VolumeSnapshot-capable StorageClass for snapshot-based tests
- Windows validation image for Windows tests

Tests install guest helpers from the operator ConfigMap and do not deploy the operator themselves.

## Running

```bash
uv run pytest tests/storage/file_level_restore/ -v
```
