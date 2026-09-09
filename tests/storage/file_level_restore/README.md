# File-Level Restore Tests

Python Tier 2/3 tests for the HCO-managed [vm-file-restore-operator](https://github.com/kubevirt/vm-file-restore-operator).

## Prerequisites

- CNV cluster with the file-restore operator deployed by HCO in `openshift-cnv`
- `declarativeHotplugVolumes` enabled (default in CNV; required by the operator's restore hotplug workflow)
- VolumeSnapshot-capable StorageClass (`snapshot_storage_class_name_scope_module`)
- Windows validation image for Tier 3 tests

## Guest Helper Setup

Tests install guest helpers from the operator ConfigMap `vm-file-restore-operator-ssh`:

- `data.ssh-publickey`
- `binaryData.linux-helpers.tar` (`setup.sh`, `filerestore.sh`) staged over SSH
- `binaryData.windows-helpers.tar` (`setup.bat`, `filerestore.bat`) staged over SSH

Both platforms extract helper scripts from the ConfigMap tarballs. Linux stages scripts
with base64 over SSH; Windows uses SFTP because `setup.bat` exceeds the Windows SSH
command-line length limit when inlined as base64.

No standalone operator install or external downloads are performed by the tests.

`VirtualMachineFileRestore` names must be short enough that `{name}-restore` fits in QEMU's
36-character disk serial limit (the operator uses the hotplug volume name as the serial).

## Path semantics

`targetPath` is not supported yet. Linux and Windows helpers use different path conventions:

| OS | `sourcePath` meaning | Write test data at | Verify after restore at |
|----|----------------------|--------------------|-------------------------|
| Linux | Path on backup volume root | `{data_disk_mount}{sourcePath}` | `{sourcePath}` on guest root |
| Windows | Full original guest path | Same as `sourcePath` | Same as `sourcePath` |

Linux example: write `/mnt/data/home/cloud-user/restore-test/file.txt`, pass
`sourcePath=/home/cloud-user/restore-test/file.txt`, verify with
`cat /home/cloud-user/restore-test/file.txt`.

Windows example: write and restore `E:\restore-test\file.txt` using the same
full path for `sourcePath` and verification.

## Running

```bash
uv run pytest tests/storage/file_level_restore/ -v
```

Tier 1 scenarios are covered upstream in the operator Go e2e suite.
