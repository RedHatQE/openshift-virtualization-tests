import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.storage_profile import StorageProfile
from pytest_testconfig import py_config

from tests.storage.upgrade.utils import (
    create_snapshot_for_upgrade,
    create_vm_for_snapshot_upgrade_tests,
)
from tests.storage.utils import update_scratch_space_sc
from utilities.constants import HOTPLUG_DISK_SERIAL, HOTPLUG_DISK_VIRTIO_BUS
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import create_dv, virtctl_volume
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
    wait_for_ssh_connectivity,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def skip_if_less_than_two_storage_classes(cluster_storage_classes):
    if len(cluster_storage_classes) < 2:
        pytest.skip("Need two Storage Classes at least.")


@pytest.fixture(scope="session")
def storage_class_for_updating_cdiconfig_scratch(
    skip_if_less_than_two_storage_classes, cdi_config, cluster_storage_classes
):
    """
    Choose one StorageClass which is not the current one for scratch space.
    """
    current_sc_for_scratch = cdi_config.scratch_space_storage_class_from_status
    LOGGER.info(f"The current StorageClass for scratch space on CDIConfig is: {current_sc_for_scratch}")
    for sc in cluster_storage_classes:
        if sc.instance.metadata.get("name") != current_sc_for_scratch:
            LOGGER.info(f"Candidate StorageClass: {sc.instance.metadata.name}")
            return sc


@pytest.fixture(scope="session")
def override_cdiconfig_scratch_spec(
    hyperconverged_resource_scope_session,
    cdi_config,
    storage_class_for_updating_cdiconfig_scratch,
):
    """
    Change spec.scratchSpaceStorageClass to the selected StorageClass on CDIConfig.
    """
    if storage_class_for_updating_cdiconfig_scratch:
        new_sc = storage_class_for_updating_cdiconfig_scratch.name

    with update_scratch_space_sc(
        cdi_config=cdi_config, new_sc=new_sc, hco=hyperconverged_resource_scope_session
    ) as edited_cdi_config:
        yield edited_cdi_config


@pytest.fixture(scope="session")
def skip_if_not_override_cdiconfig_scratch_space(override_cdiconfig_scratch_spec):
    if not override_cdiconfig_scratch_spec:
        pytest.skip("Skip test because the scratch space was not changed.")


@pytest.fixture(scope="session")
def cirros_vm_for_upgrade_a(
    upgrade_namespace_scope_session,
    admin_client,
    storage_class_for_snapshot,
    cluster_common_node_cpu,
):
    with create_vm_for_snapshot_upgrade_tests(
        vm_name="snapshot-upgrade-a",
        namespace=upgrade_namespace_scope_session.name,
        client=admin_client,
        storage_class_for_snapshot=storage_class_for_snapshot,
        cpu_model=cluster_common_node_cpu,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def snapshots_for_upgrade_a(
    admin_client,
    cirros_vm_for_upgrade_a,
):
    with create_snapshot_for_upgrade(vm=cirros_vm_for_upgrade_a, client=admin_client) as snapshot:
        yield snapshot


@pytest.fixture(scope="session")
def cirros_vm_for_upgrade_b(
    upgrade_namespace_scope_session,
    admin_client,
    storage_class_for_snapshot,
    cluster_common_node_cpu,
):
    with create_vm_for_snapshot_upgrade_tests(
        vm_name="snapshot-upgrade-b",
        namespace=upgrade_namespace_scope_session.name,
        client=admin_client,
        storage_class_for_snapshot=storage_class_for_snapshot,
        cpu_model=cluster_common_node_cpu,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def snapshots_for_upgrade_b(
    admin_client,
    cirros_vm_for_upgrade_b,
):
    with create_snapshot_for_upgrade(vm=cirros_vm_for_upgrade_b, client=admin_client) as snapshot:
        yield snapshot


@pytest.fixture(scope="session")
def blank_disk_dv_with_default_sc(upgrade_namespace_scope_session):
    with create_dv(
        source="blank",
        dv_name="blank-dv",
        namespace=upgrade_namespace_scope_session.name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        consume_wffc=False,
        client=upgrade_namespace_scope_session.client,
    ) as dv:
        yield dv


@pytest.fixture(scope="session")
def enabled_feature_gate_for_declarative_hotplug_volumes_upg(
    hyperconverged_resource_scope_session,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_session: {"spec": {"featureGates": {"declarativeHotplugVolumes": True}}},
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="session")
def fedora_vm_for_hotplug_upg(upgrade_namespace_scope_session, cluster_common_node_cpu):
    name = "fedora-hotplug-upg"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_namespace_scope_session.name,
        body=fedora_vm_body(name=name),
        cpu_model=cluster_common_node_cpu,
        client=upgrade_namespace_scope_session.client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="session")
def hotplug_volume_upg(fedora_vm_for_hotplug_upg):
    with virtctl_volume(
        action="add",
        namespace=fedora_vm_for_hotplug_upg.namespace,
        vm_name=fedora_vm_for_hotplug_upg.name,
        volume_name="blank-dv",
        persist=True,
        serial=HOTPLUG_DISK_SERIAL,
        bus=HOTPLUG_DISK_VIRTIO_BUS,
    ) as res:
        status, out, err = res
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        yield


@pytest.fixture()
def fedora_vm_for_hotplug_upg_ssh_connectivity(fedora_vm_for_hotplug_upg):
    wait_for_ssh_connectivity(vm=fedora_vm_for_hotplug_upg)


@pytest.fixture(scope="session")
def skip_if_config_default_storage_class_access_mode_rwo(admin_client):
    storage_class = py_config["default_storage_class"]
    access_modes = StorageProfile(name=storage_class, client=admin_client).first_claim_property_set_access_modes()
    assert access_modes, f"Could not get the access mode from the {storage_class} storage profile"
    access_mode = access_modes[0]
    LOGGER.info(f"Storage class '{storage_class}' has access mode: '{access_mode}'")
    if access_mode == DataVolume.AccessMode.RWO:
        pytest.skip(reason="Skip when access_mode is RWO")
