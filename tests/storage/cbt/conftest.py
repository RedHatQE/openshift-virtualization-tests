"""CBT backup fixtures (backup success only)."""

import secrets
from contextlib import ExitStack
from logging import getLogger

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.secret import Secret
from pytest_testconfig import config as py_config

from tests.storage.cbt.constants import (
    CBT_BACKUP_TYPE_FULL,
    CBT_CONCURRENT_VM_COUNT,
    CBT_ENABLED_LABEL,
)
from tests.storage.cbt.utils import (
    cbt_backup_pvc,
    cbt_backup_tracker,
    cbt_backup_wait_timeout,
    cbt_enabled_vm,
    cbt_push_backup,
    cbt_source_ref,
    concurrent_backup_type,
    delete_cbt_pull_backup_and_wait_for_export,
    delete_cbt_pull_backups_and_wait_for_exports,
    deploy_cbt_pull_backup,
    incremental_test_data,
    incremental_test_data_file,
    live_migrate_cbt_vm,
    wait_for_pull_backup_export_deleted,
    wait_for_pull_backup_export_ready,
    wait_for_push_backup_complete,
    write_cbt_guest_file,
    write_incremental_data_for_concurrent_vms,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, hco_feature_gates_patch
from utilities.storage import write_file_via_ssh

LOGGER = getLogger(name=__name__)


@pytest.fixture(scope="module")
def cbt_hco_configured(admin_client, hco_namespace, hyperconverged_resource_scope_module):
    """Enable incremental backup and CBT VM label selectors in HyperConverged CR."""
    spec_patch = hco_feature_gates_patch(hco_resource=hyperconverged_resource_scope_module, enable=["incrementalBackup"])
    spec_patch["spec"]["virtualization"] = {"changedBlockTrackingLabelSelectors": {"virtualMachineLabelSelector": {"matchLabels": CBT_ENABLED_LABEL}}}
    with ResourceEditorValidateHCOReconcile(patches={hyperconverged_resource_scope_module: spec_patch}, list_resource_reconcile=[KubeVirt], wait_for_reconcile_post_update=True, admin_client=admin_client, hco_namespace=hco_namespace.name):
        yield


@pytest.fixture()
def vm_with_cbt_label(request, unprivileged_client, namespace, cbt_hco_configured, rhel9_data_source_scope_session, unique_suffix):
    """VM with CBT enabled, started, and test data written."""
    storage_class = request.getfixturevalue(argname=request.param.get("storage_class_fixture", "storage_class_name_scope_module"))
    with cbt_enabled_vm(name=f"{request.param['name']}-{unique_suffix}", namespace=namespace.name, client=unprivileged_client, data_source=rhel9_data_source_scope_session, storage_class=storage_class, unique_suffix=unique_suffix, data_disk_count=request.param.get("data_disk_count", 0)) as vm:
        yield vm


@pytest.fixture()
def backup_tracker_for_vm(unprivileged_client, namespace, vm_with_cbt_label):
    """VirtualMachineBackupTracker for the VM."""
    with cbt_backup_tracker(namespace=namespace.name, client=unprivileged_client, vm=vm_with_cbt_label) as tracker:
        yield tracker


@pytest.fixture()
def backup_tracker_source(backup_tracker_for_vm):
    """VirtualMachineBackup.spec.source reference for the VM backup tracker."""
    return cbt_source_ref(resource=backup_tracker_for_vm)


@pytest.fixture()
def push_backup_pvc(unprivileged_client, namespace, vm_with_cbt_label, unique_suffix):
    """RWO PVC for storing push-mode backup output."""
    with cbt_backup_pvc(name=f"cbt-backup-{unique_suffix}", namespace=namespace.name, client=unprivileged_client, vm=vm_with_cbt_label, storage_class=py_config["default_storage_class"]) as pvc:
        yield pvc


@pytest.fixture()
def pull_backup_staging_pvc(unprivileged_client, namespace, vm_with_cbt_label, unique_suffix):
    """RWO staging PVC for pull-mode backup export."""
    with cbt_backup_pvc(name=f"cbt-staging-{unique_suffix}", namespace=namespace.name, client=unprivileged_client, vm=vm_with_cbt_label, storage_class=py_config["default_storage_class"]) as pvc:
        yield pvc


@pytest.fixture()
def pull_mode_token_secret(unprivileged_client, namespace, unique_suffix):
    """User-provided export token secret for pull-mode backup authentication."""
    with Secret(name=f"cbt-pull-token-{unique_suffix}", namespace=namespace.name, client=unprivileged_client, string_data={"token": secrets.token_urlsafe(nbytes=16)}) as secret:
        yield secret


# Preserve the target branch's existing fixtures and append the concurrent fixtures below.
