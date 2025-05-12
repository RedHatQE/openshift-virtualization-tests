import logging

import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pytest_testconfig import py_config

from tests.os_params import (
    FEDORA_LATEST,
    FEDORA_LATEST_OS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_OS,
)
from utilities.constants import OS_FLAVOR_FEDORA, OS_FLAVOR_WINDOWS, VIRT_LAUNCHER
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def hyperv_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_class,
    hyperv_instance_type,
    hyperv_preference,
):
    with VirtualMachineForTests(
        name=request.param.get("vm_name"),
        namespace=namespace.name,
        client=unprivileged_client,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_image_data_source_scope_class
        ),
        disk_type=None,
        vm_instance_type=hyperv_instance_type,
        vm_preference=hyperv_preference,
        os_flavor=request.param.get("os_flavor"),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def hyperv_instance_type(request):
    with VirtualMachineClusterInstancetype(
        name="hyperv-instance-type",
        memory={"guest": "8Gi"},
        cpu={"guest": 2, "model": request.param.get("model")},
    ) as hyperv_instance_type:
        yield hyperv_instance_type


@pytest.fixture()
def hyperv_preference(request):
    hyperv_preference_dict = VirtualMachineClusterPreference(
        name=request.param.get("preference_name")
    ).instance.to_dict()
    hyperv_preference_dict["metadata"] = {"name": "hyperv-cluster-preference"}
    if hyperv_dict := request.param.get("hyperv_dict"):
        hyperv_preference_dict["spec"]["features"].update(hyperv_dict)
    with VirtualMachineClusterPreference(kind_dict=hyperv_preference_dict) as hyperv_preference:
        yield hyperv_preference


def get_hyperv_enabled_labels(instance_labels):
    return [
        label
        for label, value in instance_labels.items()
        if label.startswith("hyperv.node.kubevirt.io/") and value == "true"
    ]


def verify_evmcs_related_attributes(vmi_xml_dict):
    LOGGER.info("Verify vmx policy 'required' and 'vapic' hyperv feature are added when using evcms feature")
    cpu_feature = vmi_xml_dict["domain"]["cpu"]["feature"]
    vmx_feature = [feature for feature in cpu_feature for policy, name in feature.items() if name == "vmx"]
    assert vmx_feature and vmx_feature[0]["@policy"] == "require", (
        f"Wrong vmx policy. Actual: {vmx_feature}, expected: 'require'"
    )

    vapic_hyperv_feature = vmi_xml_dict["domain"]["features"]["hyperv"]["vapic"]
    assert vapic_hyperv_feature["@state"] == "on", f"vapic feature in libvirt: {vapic_hyperv_feature}"


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class,",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_LATEST_OS,
                "image": WINDOWS_LATEST["image_path"],
                "dv_size": WINDOWS_LATEST["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
class TestWindowsHyperVFlags:
    @pytest.mark.parametrize(
        "hyperv_vm, hyperv_instance_type, hyperv_preference",
        [
            pytest.param(
                {"vm_name": "win-vm-with-default-hyperv-features", "os_flavor": OS_FLAVOR_WINDOWS},
                {},
                {"preference_name": "windows.2k19"},
                marks=(pytest.mark.polarion("CNV-7247")),
            ),
            pytest.param(
                {"vm_name": "win-vm-with-host-passthrough", "os_flavor": OS_FLAVOR_WINDOWS},
                {"model": "host-passthrough"},
                {"preference_name": "windows.2k19"},
                marks=(pytest.mark.polarion("CNV-7248")),
            ),
        ],
        indirect=True,
    )
    def test_vm_hyperv_labels_on_launcher_pod(
        self,
        hyperv_vm,
    ):
        LOGGER.info(
            f"Verify hyperv node selector labels are added to {VIRT_LAUNCHER} pod "
            "and they match the hosting node labels"
        )
        virt_launcher_hyperv_labels = get_hyperv_enabled_labels(
            instance_labels=hyperv_vm.vmi.virt_launcher_pod.instance.spec.nodeSelector
        )
        node_hyperv_labels = get_hyperv_enabled_labels(
            instance_labels=hyperv_vm.privileged_vmi.virt_launcher_pod.node.instance.metadata.labels
        )
        assert virt_launcher_hyperv_labels, (
            f"hyperv labels are missing from {VIRT_LAUNCHER} pod node selector, "
            f"node's labels: {virt_launcher_hyperv_labels}"
        )
        assert all(label in node_hyperv_labels for label in virt_launcher_hyperv_labels), (
            f"node selector hyperV labels don't match the {VIRT_LAUNCHER} node hyperV labels"
            f"{VIRT_LAUNCHER} labels: {virt_launcher_hyperv_labels}"
            f"{VIRT_LAUNCHER} node labels: {node_hyperv_labels}"
        )

    @pytest.mark.parametrize(
        "hyperv_vm, hyperv_instance_type, hyperv_preference",
        [
            pytest.param(
                {"vm_name": "win-vm-with-added-hyperv-features", "os_flavor": OS_FLAVOR_WINDOWS},
                {},
                {
                    "preference_name": "windows.2k19",
                    "hyperv_dict": {"preferredHyperv": {"vendorid": {"vendorid": "randomid"}}},
                },
                marks=(pytest.mark.polarion("CNV-6087")),
            ),
        ],
        indirect=True,
    )
    def test_vm_added_hyperv_features(
        self,
        hyperv_vm,
    ):
        LOGGER.info("Verify added hyperv feature is added to libvirt")
        vendor_id = hyperv_vm.privileged_vmi.xml_dict["domain"]["features"]["hyperv"]["vendor_id"]
        assert vendor_id["@state"] == "on" and vendor_id["@value"] == "randomid", f"Vendor id in libvirt: {vendor_id}"

    @pytest.mark.parametrize(
        "hyperv_vm, hyperv_instance_type, hyperv_preference",
        [
            pytest.param(
                {"vm_name": "win-vm-with-evmcs-feature", "os_flavor": OS_FLAVOR_WINDOWS},
                {},
                {"preference_name": "windows.2k19"},
                marks=pytest.mark.polarion("CNV-6202"),
            ),
        ],
        indirect=True,
    )
    def test_windows_vm_with_evmcs_feature(self, hyperv_vm):
        verify_evmcs_related_attributes(vmi_xml_dict=hyperv_vm.privileged_vmi.xml_dict)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class,",
    [
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST["image_path"],
                "dv_size": FEDORA_LATEST["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
        ),
    ],
    indirect=True,
)
class TestFedoraHyperVFlags:
    @pytest.mark.parametrize(
        "hyperv_vm, hyperv_instance_type, hyperv_preference",
        [
            pytest.param(
                {"vm_name": "fedora-vm-with-evmcs-feature", "os_flavor": OS_FLAVOR_FEDORA},
                {},
                {"preference_name": "fedora", "hyperv_dict": {"preferredHyperv": {"evmcs": {}}}},
                marks=pytest.mark.polarion("CNV-6090"),
            ),
        ],
        indirect=True,
    )
    def test_fedora_vm_with_evmcs_feature(self, hyperv_vm):
        LOGGER.info("Verify added hyperv feature evmcs is added to libvirt")
        hyperv_vm_xml = hyperv_vm.privileged_vmi.xml_dict
        evmcs_feature = hyperv_vm_xml["domain"]["features"]["hyperv"]["evmcs"]
        assert evmcs_feature["@state"] == "on", f"evmcs in libvirt: {evmcs_feature}"

        verify_evmcs_related_attributes(vmi_xml_dict=hyperv_vm_xml)
