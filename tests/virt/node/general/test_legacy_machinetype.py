import logging

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.template import Template

from tests.virt.constants import MachineTypesNames
from tests.virt.utils import validate_machine_type
from utilities.constants import (
    DATA_SOURCE_STR,
    DV_SIZE_STR,
    FLAVOR_STR,
    IMAGE_PATH_STR,
    OS_STR,
    TEMPLATE_LABELS_STR,
    WORKLOAD_STR,
    Images,
)
from utilities.hco import is_hco_tainted, update_hco_annotations
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    running_vm,
    wait_for_updated_kv_value,
)

pytestmark = pytest.mark.post_upgrade

LOGGER = logging.getLogger(__name__)
RHEL_8_10 = {
    IMAGE_PATH_STR: f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_10_IMG}",
    DV_SIZE_STR: "20Gi",
    TEMPLATE_LABELS_STR: {
        OS_STR: "rhel8.10",
        WORKLOAD_STR: "server",
        FLAVOR_STR: "tiny",
    },
    DATA_SOURCE_STR: "rhel8",
}


@pytest.fixture()
def updated_hco_emulated_machine_i440fx(hyperconverged_resource_scope_function, admin_client, hco_namespace):
    annotations_path = "architectureConfiguration"
    amd64_machine_type_list = ["q35*", "pc-q35*", "pc-i440fx-rhel7.6.0"]
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_function,
        path=annotations_path,
        value={"amd64": {"emulatedMachines": amd64_machine_type_list}},
        resource_list=[KubeVirt],
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=[annotations_path, "amd64", "emulatedMachines"],
            value=amd64_machine_type_list,
        )
        yield
    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)


@pytest.fixture()
def rhel_8_10_vm(unprivileged_client, namespace, golden_image_data_volume_template_for_test_scope_function):
    with VirtualMachineForTestsFromTemplate(
        name="rhel-8-10-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**RHEL_8_10["template_labels"]),
        data_volume_template=golden_image_data_volume_template_for_test_scope_function,
        machine_type=MachineTypesNames.pc_i440fx_rhel7_6,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_function, expected_machine_type",
    [
        pytest.param(
            {"os_dict": RHEL_8_10},
            MachineTypesNames.pc_i440fx_rhel7_6,
            marks=pytest.mark.polarion("CNV-7311"),
        )
    ],
    indirect=["golden_image_data_source_for_test_scope_function"],
)
def test_legacy_machine_type(updated_hco_emulated_machine_i440fx, rhel_8_10_vm, expected_machine_type):
    validate_machine_type(vm=rhel_8_10_vm, expected_machine_type=expected_machine_type)
