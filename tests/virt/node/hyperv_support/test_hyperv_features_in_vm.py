import logging

import pytest
from pytest_testconfig import py_config

from tests.os_params import (
    FEDORA_LATEST,
    FEDORA_LATEST_LABELS,
    FEDORA_LATEST_OS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_LABELS,
    WINDOWS_LATEST_OS,
)
from utilities.constants import VIRT_LAUNCHER
from utilities.virt import vm_instance_from_template

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def hyperv_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_class,
):
    hyperv_dict = request.param.get("hyperv_dict")
    if hyperv_dict:
        request.param["vm_dict"] = {"spec": {"template": {"spec": {"domain": {"features": {"hyperv": hyperv_dict}}}}}}
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_class,
    ) as vm:
        yield vm


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
                "image": WINDOWS_LATEST.get("image_path"),
                "dv_size": WINDOWS_LATEST.get("dv_size"),
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
        "hyperv_vm",
        [
            pytest.param(
                {
                    "vm_name": "win-vm-with-default-hyperv-features",
                    "template_labels": WINDOWS_LATEST_LABELS,
                },
                marks=(pytest.mark.polarion("CNV-7247")),
            ),
            pytest.param(
                {
                    "vm_name": "win-vm-with-host-passthrough",
                    "template_labels": WINDOWS_LATEST_LABELS,
                    "vm_dict": {"spec": {"template": {"spec": {"domain": {"cpu": {"model": "host-passthrough"}}}}}},
                },
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
        "hyperv_vm",
        [
            pytest.param(
                {
                    "vm_name": "win-vm-with-added-hyperv-features",
                    "template_labels": WINDOWS_LATEST_LABELS,
                    "hyperv_dict": {"vendorid": {"vendorid": "randomid"}},
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
        "hyperv_vm",
        [
            pytest.param(
                {
                    "vm_name": "win-vm-with-evmcs-feature",
                    "template_labels": WINDOWS_LATEST_LABELS,
                    "hyperv_dict": {"evmcs": {}},
                },
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
                "image": FEDORA_LATEST.get("image_path"),
                "dv_size": FEDORA_LATEST.get("dv_size"),
                "storage_class": py_config["default_storage_class"],
            },
        ),
    ],
    indirect=True,
)
class TestFedoraHyperVFlags:
    @pytest.mark.parametrize(
        "hyperv_vm",
        [
            pytest.param(
                {
                    "vm_name": "fedora-vm-with-evmcs-feature",
                    "template_labels": FEDORA_LATEST_LABELS,
                    "hyperv_dict": {"evmcs": {}},
                },
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
