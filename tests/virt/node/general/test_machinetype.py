import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.kubevirt import KubeVirt
from pytest_testconfig import config as py_config

from tests.virt.node.general.constants import MachineTypesNames
from utilities.hco import is_hco_tainted, update_hco_annotations
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    get_rhel_os_dict,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
    wait_for_updated_kv_value,
)

pytestmark = pytest.mark.post_upgrade
LOGGER = logging.getLogger(__name__)

RHEL_8_10 = get_rhel_os_dict(rhel_version="rhel-8-10")
RHEL_8_10_TEMPLATE_LABELS = RHEL_8_10["template_labels"]


def validate_machine_type(expected_machine_type, vm):
    vm_machine_type = vm.instance.spec.template.spec.domain.machine.type
    vmi_machine_type = vm.vmi.instance.spec.domain.machine.type

    assert vm_machine_type == vmi_machine_type == expected_machine_type, (
        f"Created VM's machine type does not match the request. "
        f"Expected: {expected_machine_type} VM: {vm_machine_type}, VMI: {vmi_machine_type}"
    )
    vmi_xml_machine_type = vm.privileged_vmi.xml_dict["domain"]["os"]["type"]["@machine"]
    assert vmi_xml_machine_type == expected_machine_type, (
        f"libvirt machine type {vmi_xml_machine_type} does not match expected type {expected_machine_type}"
    )


@pytest.fixture()
def updated_hco_emulated_machine_i440fx(
    hyperconverged_resource_scope_function,
    admin_client,
    hco_namespace,
):
    annotations_path = "architectureConfiguration"
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_function,
        path=annotations_path,
        value={"amd64": {"emulatedMachines": ["q35*", "pc-q35*", "pc-i440fx-rhel7.6.0"]}},
        resource_list=[KubeVirt],
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=[annotations_path, "amd64", "emulatedMachines"],
            value=["q35*", "pc-q35*", "pc-i440fx-rhel7.6.0"],
        )
        yield
    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)


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
):
    machine_type = request.param["machine_type"]
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_function,
        path="machineType",
        value=machine_type,
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=["machineType"],
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
    validate_machine_type(vm=vm, expected_machine_type=machine_type_from_kubevirt_config)


@pytest.mark.parametrize(
    "vm, expected",
    [
        pytest.param(
            {"vm_name": "pc-q35", "machine_type": MachineTypesNames.pc_q35_rhel7_6},
            MachineTypesNames.pc_q35_rhel7_6,
            marks=pytest.mark.polarion("CNV-3311"),
        )
    ],
    indirect=["vm"],
)
def test_pc_q35_vm_machine_type(vm, expected):
    validate_machine_type(vm=vm, expected_machine_type=expected)


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
@pytest.mark.gating
def test_migrate_vm(
    skip_if_no_common_cpu,
    skip_access_mode_rwo_scope_function,
    machine_type_from_kubevirt_config,
    vm,
):
    migrate_vm_and_verify(vm=vm)

    validate_machine_type(vm=vm, expected_machine_type=machine_type_from_kubevirt_config)


@pytest.mark.parametrize(
    "vm, updated_kubevirt_config_machine_type",
    [
        pytest.param(
            {"vm_name": "default-kubevirt-config"},
            {"machine_type": MachineTypesNames.pc_q35_rhel8_1},
            marks=pytest.mark.polarion("CNV-4347"),
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
            marks=pytest.mark.polarion("CNV-11268"),
        )
    ],
    indirect=True,
)
@pytest.mark.gating
def test_machine_type_after_vm_migrate(
    skip_if_no_common_cpu,
    skip_access_mode_rwo_scope_function,
    machine_type_from_kubevirt_config,
    vm,
    updated_kubevirt_config_machine_type,
    migrated_vm,
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
            marks=pytest.mark.polarion("CNV-3681"),
        )
    ],
    indirect=True,
)
@pytest.mark.gating
def test_machine_type_kubevirt_config_update(updated_kubevirt_config_machine_type, vm):
    """Test machine type change in kubevirt_config; new VM gets new value"""

    validate_machine_type(vm=vm, expected_machine_type=MachineTypesNames.pc_q35_rhel8_1)


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


@pytest.mark.gating
@pytest.mark.polarion("CNV-5658")
def test_major_release_machine_type(machine_type_from_kubevirt_config):
    # CNV should always use a major release for machine type, for example: pc-q35-rhel8.3.0
    assert machine_type_from_kubevirt_config.endswith(".0"), (
        f"Machine type should be a major release {machine_type_from_kubevirt_config}"
    )


@pytest.mark.gating
@pytest.mark.polarion("CNV-8561")
def test_machine_type_as_rhel_9_4(machine_type_from_kubevirt_config):
    """Verify that machine type in KubeVirt CR match the value pc-q35-rhel9.4.0"""
    assert machine_type_from_kubevirt_config == MachineTypesNames.pc_q35_rhel9_4, (
        f"Machine type value is {machine_type_from_kubevirt_config}"
        f"does not match with {MachineTypesNames.pc_q35_rhel9_4}"
    )


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vm_from_template_scope_function, expected_machine_type",
    [
        pytest.param(
            {
                "dv_name": RHEL_8_10_TEMPLATE_LABELS["os"],
                "image": RHEL_8_10["image_path"],
                "dv_size": RHEL_8_10["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "legacy-vm",
                "template_labels": RHEL_8_10_TEMPLATE_LABELS,
                "machine_type": MachineTypesNames.pc_i440fx_rhel7_6,
            },
            MachineTypesNames.pc_i440fx_rhel7_6,
            marks=pytest.mark.polarion("CNV-7311"),
        )
    ],
    indirect=[
        "golden_image_data_volume_scope_function",
        "vm_from_template_scope_function",
    ],
)
def test_legacy_machine_type(
    updated_hco_emulated_machine_i440fx,
    golden_image_data_volume_scope_function,
    vm_from_template_scope_function,
    expected_machine_type,
):
    validate_machine_type(
        vm=vm_from_template_scope_function,
        expected_machine_type=expected_machine_type,
    )
