import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError

from tests.virt.constants import MachineTypesNames
from tests.virt.utils import validate_machine_type
from utilities.hco import update_hco_annotations
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
    wait_for_updated_kv_value,
)

pytestmark = pytest.mark.post_upgrade
LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def vm(request, cluster_cpu_model_scope_function, unprivileged_client, namespace):
    name = f"vm-{request.param['vm_name']}-machine-type"

    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        machine_type=request.param.get("machine_type"),
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def updated_kubevirt_config_machine_type(
    request,
    hyperconverged_resource_scope_function,
    kubevirt_config,
    admin_client,
    hco_namespace,
    nodes_cpu_architecture,
):
    machine_type = request.param["machine_type"]
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_function,
        path="architectureConfiguration",
        value={nodes_cpu_architecture: {"machineType": machine_type}},
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=["architectureConfiguration", nodes_cpu_architecture, "machineType"],
            value=machine_type,
        )
        yield


@pytest.fixture()
def restarted_vm(vm, machine_type_from_kubevirt_config):
    validate_machine_type(vm=vm, expected_machine_type=machine_type_from_kubevirt_config)
    restart_vm_wait_for_running_vm(vm=vm, check_ssh_connectivity=False)


@pytest.fixture()
def migrated_vm(vm, machine_type_from_kubevirt_config):
    validate_machine_type(vm=vm, expected_machine_type=machine_type_from_kubevirt_config)
    migrate_vm_and_verify(vm=vm)


@pytest.mark.arm64
@pytest.mark.x86_64
@pytest.mark.s390x
@pytest.mark.parametrize(
    "vm",
    [
        pytest.param(
            {"vm_name": "default"},
            marks=pytest.mark.polarion("CNV-3312"),
        )
    ],
    indirect=True,
)
def test_default_machine_type(machine_type_from_kubevirt_config, vm):
    # Workaround for s390x (https://github.com/kubevirt/kubevirt/issues/14953), as machine type missing in config and
    # hardcoded to s390_ccw_virtio in kubevirt code.
    if machine_type_from_kubevirt_config == MachineTypesNames.s390_ccw_virtio:
        expected_libvirt_machine_type = MachineTypesNames.s390_ccw_virtio_rhel9_6
    else:
        expected_libvirt_machine_type = machine_type_from_kubevirt_config
    validate_machine_type(
        vm=vm,
        expected_machine_type=machine_type_from_kubevirt_config,
        expected_libvirt_machine_type=expected_libvirt_machine_type,
    )


@pytest.mark.parametrize(
    "vm, expected, expected_libvirt",
    [
        pytest.param(
            {"vm_name": "pc-q35", "machine_type": MachineTypesNames.pc_q35_rhel7_6},
            MachineTypesNames.pc_q35_rhel7_6,
            MachineTypesNames.pc_q35_rhel7_6,
            marks=[pytest.mark.polarion("CNV-3311"), pytest.mark.x86_64()],
        ),
        pytest.param(
            {"vm_name": "s390-ccw-virtio", "machine_type": MachineTypesNames.s390_ccw_virtio},
            MachineTypesNames.s390_ccw_virtio,
            MachineTypesNames.s390_ccw_virtio_rhel9_6,
            marks=[pytest.mark.s390x()],
        ),
    ],
    indirect=["vm"],
)
def test_vm_machine_type(vm, expected, expected_libvirt):
    validate_machine_type(vm=vm, expected_machine_type=expected, expected_libvirt_machine_type=expected_libvirt)


@pytest.mark.parametrize(
    "vm",
    [
        pytest.param(
            {"vm_name": "machine-type-mig"},
            marks=pytest.mark.polarion("CNV-3323"),
        )
    ],
    indirect=True,
)
@pytest.mark.arm64
@pytest.mark.rwx_default_storage
@pytest.mark.gating
@pytest.mark.x86_64
@pytest.mark.s390x
def test_migrate_vm(machine_type_from_kubevirt_config, vm):
    """Migrate VM and check machine type is same"""
    migrate_vm_and_verify(vm=vm)
    # s390x: machine type missing in config (GH#14953). Same as above.
    if machine_type_from_kubevirt_config == MachineTypesNames.s390_ccw_virtio:
        expected_libvirt_machine_type = MachineTypesNames.s390_ccw_virtio_rhel9_6
    else:
        expected_libvirt_machine_type = machine_type_from_kubevirt_config
    validate_machine_type(
        vm=vm,
        expected_machine_type=machine_type_from_kubevirt_config,
        expected_libvirt_machine_type=expected_libvirt_machine_type,
    )


@pytest.mark.parametrize(
    "vm, updated_kubevirt_config_machine_type",
    [
        pytest.param(
            {"vm_name": "default-kubevirt-config"},
            {"machine_type": MachineTypesNames.pc_q35_rhel8_1},
            marks=[
                pytest.mark.polarion("CNV-4347"),
                pytest.mark.x86_64(),  # s390x: machine type missing in config (GH#14953)
            ],
        )
    ],
    indirect=True,
)
@pytest.mark.gating
def test_machine_type_after_vm_restart(
    machine_type_from_kubevirt_config,
    vm,
    updated_kubevirt_config_machine_type,
    restarted_vm,
):
    """Test machine type change in kubevirt_config; existing VM does not get new
    value after restart"""
    validate_machine_type(vm=vm, expected_machine_type=machine_type_from_kubevirt_config)


@pytest.mark.parametrize(
    "vm, updated_kubevirt_config_machine_type",
    [
        pytest.param(
            {"vm_name": "default-kubevirt-config"},
            {"machine_type": MachineTypesNames.pc_q35_rhel8_1},
            marks=[
                pytest.mark.polarion("CNV-11268"),
                pytest.mark.x86_64(),  # s390x: machine type missing in config (GH#14953)
            ],
        )
    ],
    indirect=True,
)
@pytest.mark.rwx_default_storage
@pytest.mark.gating
def test_machine_type_after_vm_migrate(
    machine_type_from_kubevirt_config, vm, updated_kubevirt_config_machine_type, migrated_vm
):
    """Test machine type change in kubevirt_config; existing VM does not get new
    value after migration"""

    validate_machine_type(vm=vm, expected_machine_type=machine_type_from_kubevirt_config)


@pytest.mark.parametrize(
    "vm, updated_kubevirt_config_machine_type",
    [
        pytest.param(
            {"vm_name": "updated-kubevirt-config"},
            {"machine_type": MachineTypesNames.pc_q35_rhel8_1},
            marks=[
                pytest.mark.polarion("CNV-3681"),
                pytest.mark.x86_64(),  # s390x: machine type missing in config (GH#14953)
            ],
        )
    ],
    indirect=True,
)
@pytest.mark.gating
def test_machine_type_kubevirt_config_update(updated_kubevirt_config_machine_type, vm):
    """Test machine type change in kubevirt_config; new VM gets new value"""
    validate_machine_type(vm=vm, expected_machine_type=MachineTypesNames.pc_q35_rhel8_1)


@pytest.mark.x86_64
@pytest.mark.s390x
@pytest.mark.polarion("CNV-3688")
def test_unsupported_machine_type(namespace, unprivileged_client):
    vm_name = "vm-invalid-machine-type"

    with pytest.raises(UnprocessibleEntityError):
        with VirtualMachineForTests(
            name=vm_name,
            namespace=namespace.name,
            body=fedora_vm_body(name=vm_name),
            client=unprivileged_client,
            machine_type=MachineTypesNames.pc_i440fx_rhel7_6,
        ):
            pytest.fail("VM created with invalid machine type.")


@pytest.mark.arm64
@pytest.mark.gating
@pytest.mark.polarion("CNV-5658")
@pytest.mark.x86_64  # s390x: machine type missing in config (GH#14953)
def test_major_release_machine_type(machine_type_from_kubevirt_config):
    # CNV should always use a major release for machine type, for example: pc-q35-rhel8.3.0
    assert machine_type_from_kubevirt_config.endswith(".0"), (
        f"Machine type should be a major release {machine_type_from_kubevirt_config}"
    )


@pytest.mark.gating
@pytest.mark.polarion("CNV-8561")
@pytest.mark.x86_64  # s390x: machine type missing in config (GH#14953)
def test_machine_type_as_rhel_9_6(machine_type_from_kubevirt_config):
    """Verify that machine type in KubeVirt CR match the value pc-q35-rhel9.6.0"""
    assert machine_type_from_kubevirt_config == MachineTypesNames.pc_q35_rhel9_6, (
        f"Machine type value is {machine_type_from_kubevirt_config}"
        f"does not match with {MachineTypesNames.pc_q35_rhel9_6}"
    )
