from typing import Final

from kubernetes.dynamic import DynamicClient

from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Metadata
from libs.vm.vm import BaseVirtualMachine, add_volume_disk, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs.cloudinit import NetworkData, primary_iface_cloud_init
from utilities.constants import SSH_PORT_22

SERVICE_IP_FAMILY_POLICY_SINGLE_STACK = "SingleStack"
SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK = "PreferDualStack"
SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK = "RequireDualStack"

SERVICE_VM_ANTI_AFFINITY_LABEL: Final[tuple[str, str]] = ("service-test", "true")


def assert_svc_ip_params(
    svc,
    expected_num_families_in_service,
    expected_ip_family_policy,
):
    assert (
        len(svc.instance.spec.ipFamilies) == expected_num_families_in_service
        and svc.instance.spec.ipFamilyPolicy == expected_ip_family_policy
    ), f"{expected_ip_family_policy} service wrongly created."


def basic_expose_command(
    resource_name,
    svc_name,
    resource="vm",
    port="27017",
    target_port=SSH_PORT_22,
    service_type="NodePort",
    protocol="TCP",
):
    return (
        f"expose {resource} {resource_name} --port={port} --target-port="
        f"{target_port} --type={service_type} --name={svc_name} --protocol={protocol}"
    )


def service_vm(namespace: str, name: str, client: DynamicClient) -> BaseVirtualMachine:
    """Fedora VM pre-configured for service connectivity tests.

    Sets anti-affinity labels and injects dual-stack cloud-init when the cluster supports IPv6.

    Args:
        namespace: Namespace for the VM.
        name: Name of the VM.
        client: Kubernetes client.

    Returns:
        BaseVirtualMachine ready to be deployed.
    """
    spec = base_vmspec()
    spec.template.metadata = spec.template.metadata or Metadata()
    spec.template.metadata.labels = dict([SERVICE_VM_ANTI_AFFINITY_LABEL])
    spec.template.spec.affinity = new_pod_anti_affinity(label=SERVICE_VM_ANTI_AFFINITY_LABEL)
    if primary := primary_iface_cloud_init():
        netdata = NetworkData(ethernets={"eth0": primary})
        disk, volume = cloudinitdisk_storage(
            data=CloudInitNoCloud(
                networkData=cloudinit.asyaml(no_cloud=netdata),
                userData=cloudinit.format_cloud_config(userdata=cloudinit.UserData(users=[])),
            )
        )
        spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)
    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)
