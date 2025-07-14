"""
Test RDP - Expose Windows VirtualMachine (latest version) as a service and use for authenticating RDP connection.
"""

import logging

import pytest
from ocp_resources.service import Service
from pytest_testconfig import config as py_config

from utilities.constants import (
    OS_FLAVOR_WINDOWS,
    QUARANTINED,
    TIMEOUT_5MIN,
    TIMEOUT_35MIN,
)
from utilities.virt import get_windows_os_dict, vm_instance_from_template

LOGGER = logging.getLogger(__name__)
# TODO : Use once Win19 RDP issue resolved - WIN_LATEST_VERSION = py_config["latest_windows_os_dict"]["os_version"]
WIN_VERSION_16_CONFIG = get_windows_os_dict(windows_version="win-2016")
WIN_OS_VERSION_16 = WIN_VERSION_16_CONFIG.get("os_version")


@pytest.fixture(scope="module")
def rdp_vm(
    request,
    namespace,
    golden_image_data_source_scope_function,
    unprivileged_client,
):
    with vm_instance_from_template(
        request=request,
        namespace=namespace,
        data_source=golden_image_data_source_scope_function,
        unprivileged_client=unprivileged_client,
    ) as rdp_vm:
        rdp_vm.custom_service_enable(service_name="rdp-svc-test", port=3389, service_type=Service.Type.NODE_PORT)
        LOGGER.info(
            f"{Service.Type.NODE_PORT} service created to expose VirtualMachine "
            f"{rdp_vm.name} via RDP port {rdp_vm.custom_service.service_port}..."
        )
        yield rdp_vm


@pytest.fixture(scope="module")
def rdp_pod(workers_utility_pods, rdp_vm):
    """
    Return a pod on a different node than the one that runs the VM (rdp_vm).

    Returns:
        Pod: A Pod object to execute from.
    """
    for pod in workers_utility_pods:
        if pod.node.name != rdp_vm.vmi.node.name:
            return pod
    assert False, f"No Pod found on a different node than the one that runs the VirtualMachine {rdp_vm.name}."


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, rdp_vm",
    [
        pytest.param(
            {
                "dv_name": WIN_VERSION_16_CONFIG.get("template_labels", {}).get("os"),
                "image": WIN_VERSION_16_CONFIG.get("image_path"),
                "storage_class": py_config["default_storage_class"],
                "dv_size": WIN_VERSION_16_CONFIG.get("dv_size"),
            },
            {
                "vm_name": f"win{WIN_OS_VERSION_16}-vm-test",
                "os_version": WIN_OS_VERSION_16,
                "template_labels": WIN_VERSION_16_CONFIG.get("template_labels"),
                "network_model": "virtio",
                "wait_for_interfaces_timeout": TIMEOUT_35MIN,
            },
            marks=(pytest.mark.polarion("CNV-235")),
            id="test_rdp_for_exposed_win_vm_svc",
        ),
    ],
    indirect=True,
)
@pytest.mark.xfail(
    reason=f"{QUARANTINED}: RDP test case must be fixed and implement a reliable client; tracked in CNV-43997",
    run=False,
)
def test_rdp_for_exposed_win_vm_as_node_port_svc(
    rdp_vm,
    rdp_pod,
):
    """
    Creates a Windows VM from the latest Windows version and starts the VM.
    Exposes the VM as a NodePort service and authenticates connection to the service via RDP.

    For authenticating the RDP connection, we will use two packages:
        1. xvfb - Virtual X display server.
        2. xfreerdp - X11 RDP client.
    """
    # TODO : Supposed to run on latest Windows version (Win19) once RDP issue is fixed - currently testing on Win16.
    rdp_auth_cmd = (
        f"WLOG_PREFIX='[%hr:%mi:%se:%ml] [%mn] - ' xvfb-run --server-args='-screen 0 1024x768x24' "
        f"xfreerdp /cert-ignore /auth-only "
        f"/v:{rdp_vm.custom_service.instance.spec.clusterIP}:{rdp_vm.custom_service.port} "
        f"/u:{py_config['os_login_param'][OS_FLAVOR_WINDOWS]['username']} "
        f"/p:{py_config['os_login_param'][OS_FLAVOR_WINDOWS]['password']}"
    )
    LOGGER.info(f"Checking RDP connection to exposed {Service.Type.NODE_PORT} service, Authentication only...")
    auth_result = rdp_pod.execute(command=["bash", "-c", rdp_auth_cmd], timeout=TIMEOUT_5MIN)
    # The exit status is 0 when authentication succeeds, 1 otherwise.
    assert "exit status 0" in auth_result
