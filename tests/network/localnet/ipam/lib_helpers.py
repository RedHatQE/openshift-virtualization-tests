from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError
from timeout_sampler import TimeoutSampler

from libs.net.netattachdef import IPAMClaim
from libs.vm.vm import BaseVirtualMachine


def wait_for_ipam_claim_bound(vm: BaseVirtualMachine, iface_name: str, client: DynamicClient) -> None:
    """Wait until the IPAMClaim for a VM's interface has IP allocations.

    Args:
        vm: The virtual machine whose IPAMClaim to wait for.
        iface_name: Logical network interface name as declared in the VM spec.
        client: Kubernetes dynamic client for resource access.
    """
    claim = IPAMClaim(
        name=f"{vm.name}.{iface_name}",
        namespace=vm.namespace,
        client=client,
    )
    for sample in TimeoutSampler(
        wait_timeout=60,
        sleep=5,
        func=lambda: claim.instance.status.ips,
        exceptions_dict={NotFoundError: [], AttributeError: []},
    ):
        if sample:
            break
