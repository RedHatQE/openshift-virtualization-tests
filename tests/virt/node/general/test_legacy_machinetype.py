import logging

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.virt.node.general.constants import MachineTypesNames
from tests.virt.utils import validate_machine_type
from utilities.constants import Images
from utilities.hco import is_hco_tainted, update_hco_annotations
from utilities.storage import create_dv, create_or_update_data_source, get_test_artifact_server_url
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    get_rhel_os_dict,
    running_vm,
    wait_for_updated_kv_value,
)

pytestmark = pytest.mark.post_upgrade
LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def updated_hco_emulated_machine_i440fx(
    hyperconverged_resource_scope_function,
    admin_client,
    hco_namespace,
):
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
def rhel_8_10_dv(admin_client, golden_images_namespace):
    with create_dv(
        dv_name="rhel-8-10-dv",
        namespace=golden_images_namespace.name,
        storage_class=py_config["default_storage_class"],
        url=f"{get_test_artifact_server_url()}{Images.Rhel.DIR}/{Images.Rhel.RHEL8_10_IMG}",
        size=Images.Rhel.DEFAULT_DV_SIZE,
        client=admin_client,
    ) as dv:
        yield dv


@pytest.fixture()
def rhel_8_10_ds(admin_client, rhel_8_10_dv):
    yield from create_or_update_data_source(admin_client=admin_client, dv=rhel_8_10_dv)


@pytest.fixture()
def rhel_8_10_vm(unprivileged_client, namespace, rhel_8_10_ds):
    rhel_8_10 = get_rhel_os_dict(rhel_version="rhel-8-10")
    with VirtualMachineForTestsFromTemplate(
        name="rhel-8-10",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**rhel_8_10["template_labels"]),
        data_source=rhel_8_10_ds,
        machine_type=MachineTypesNames.pc_i440fx_rhel7_6,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.parametrize(
    "expected_machine_type",
    [
        pytest.param(
            MachineTypesNames.pc_i440fx_rhel7_6,
            marks=pytest.mark.polarion("CNV-7311"),
        )
    ],
)
@pytest.mark.x86_64  # no legacy machinetype for s390x which is different from emulated machine types
def test_legacy_machine_type(
    updated_hco_emulated_machine_i440fx,
    rhel_8_10_vm,
    expected_machine_type,
):
    validate_machine_type(
        vm=rhel_8_10_vm,
        expected_machine_type=expected_machine_type,
    )
