import logging

LOGGER = logging.getLogger(__name__)


def verify_pods_priority_class_value(pods, expected_value):
    failed_pods_list = [pod.name for pod in pods if pod.instance.spec["priorityClassName"] != expected_value]
    assert not failed_pods_list, (
        f"priorityClassName not set correctly in pods: {failed_pods_list}, should be {expected_value}"
    )


def check_vm_xml_smbios(vm, cm_values):
    """
    Verify SMBIOS on VM XML [sysinfo type=smbios][system] match kubevirt-config
    config map.
    """

    LOGGER.info("Verify VM XML - SMBIOS values.")
    smbios_vm = vm.privileged_vmi.xml_dict["domain"]["sysinfo"]["system"]["entry"]
    smbios_vm_dict = {entry["@name"]: entry["#text"] for entry in smbios_vm}
    assert smbios_vm, "VM XML missing SMBIOS values."
    results = {
        "manufacturer": smbios_vm_dict["manufacturer"] == cm_values["manufacturer"],
        "product": smbios_vm_dict["product"] == cm_values["product"],
        "family": smbios_vm_dict["family"] == cm_values["family"],
        "version": smbios_vm_dict["version"] == cm_values["version"],
    }
    LOGGER.info(f"Results: {results}")
    assert all(results.values())


def check_smbios_defaults(smbios_defaults, cm_values):
    LOGGER.info("Compare SMBIOS config map values to expected default values.")
    assert cm_values == smbios_defaults, f"Configmap values {cm_values} do not match default values {smbios_defaults}"
