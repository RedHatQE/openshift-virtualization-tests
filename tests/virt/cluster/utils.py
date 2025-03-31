import logging

LOGGER = logging.getLogger(__name__)


def verify_pods_priority_class_value(pods, expected_value):
    failed_pods_list = [pod.name for pod in pods if pod.instance.spec["priorityClassName"] != expected_value]
    assert not failed_pods_list, (
        f"priorityClassName not set correctly in pods: {failed_pods_list}, should be {expected_value}"
    )


def check_smbios_defaults(smbios_defaults, cm_values):
    LOGGER.info("Compare SMBIOS config map values to expected default values.")
    assert cm_values == smbios_defaults, f"Configmap values {cm_values} do not match default values {smbios_defaults}"
