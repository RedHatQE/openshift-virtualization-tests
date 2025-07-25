"""
Check VM with Service Account
"""

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.service_account import ServiceAccount
from pyhelper_utils.shell import run_ssh_commands

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.fixture(scope="module")
def service_account(namespace):
    with ServiceAccount(name="sa-test", namespace=namespace.name) as sa:
        yield sa


@pytest.fixture()
def service_account_vm(namespace, service_account, unprivileged_client):
    name = "service-account-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        service_accounts=[service_account.name],
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-1000")
def test_vm_with_specified_service_account(is_s390x_cluster, service_account_vm):
    """
    Verifies VM with specified ServiceAccount
    """

    pod_sa = service_account_vm.privileged_vmi.virt_launcher_pod.execute(
        command=["cat", "/var/run/secrets/kubernetes.io/serviceaccount/namespace"],
        container="compute",
    )
    vm_namespace = service_account_vm.namespace
    assert pod_sa == vm_namespace, "ServiceAccount should be attached to the POD"

    # Verifies that ServiceAccount is attached to VMI
    # Change mount device based on cluster cpu architecture
    mount_device = "/dev/vdb" if is_s390x_cluster else "/dev/sda"
    output = run_ssh_commands(
        host=service_account_vm.ssh_exec,
        commands=[
            ["sudo", "mount", mount_device, "/mnt"],
            ["sudo", "cat", "/mnt/namespace"],
        ],
    )
    assert output[1] == vm_namespace, f"Wrong ServiceAccount attachment, VM: {vm_namespace}, OS: {output[1]}"


@pytest.mark.polarion("CNV-1001")
def test_vm_with_2_service_accounts(namespace):
    """
    Negative: Verifies that VM with 2 ServiceAccounts can't be created
    """
    name = "vm-with-2-sa"
    with pytest.raises(ApiException, match=r".* must have max one serviceAccount .*"):
        with VirtualMachineForTests(
            name=name,
            namespace=namespace.name,
            service_accounts=["sa-1", "sa-2"],
            body=fedora_vm_body(name=name),
        ):
            return
