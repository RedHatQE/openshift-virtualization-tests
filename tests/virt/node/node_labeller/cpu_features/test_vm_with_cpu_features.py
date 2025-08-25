"""
VM with CPU features
"""

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError

from utilities.constants import AMD
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.usefixtures("fail_if_amd_cpu_nodes")]


@pytest.fixture()
def fail_if_amd_cpu_nodes(nodes_cpu_vendor):
    if nodes_cpu_vendor == AMD:
        pytest.skip("PCID CPU feature is not supported on AMD CPU")


@pytest.fixture(
    params=[
        pytest.param(
            [{"features": [{"name": "pcid"}]}, "no-policy"],
            marks=(pytest.mark.polarion("CNV-1830")),
        ),
        pytest.param(
            [{"features": [{"name": "pcid", "policy": "force"}]}, "policy-force"],
            marks=(pytest.mark.polarion("CNV-1836")),
        ),
    ],
    ids=["Feature: name: pcid", "Feature: name: pcid , policy:force"],
)
def cpu_features_vm_positive(request, unprivileged_client, namespace):
    name = f"vm-cpu-features-positive-{request.param[1]}"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_flags=request.param[0],
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


def test_vm_with_cpu_feature_positive(cpu_features_vm_positive):
    """
    Test VM with cpu flag, test the VM started and is accessible via SSH
    """
    cpu_features_vm_positive.ssh_exec.executor().is_connective()
    assert (
        cpu_features_vm_positive.cpu_flags["features"][0]["name"]
        == (cpu_features_vm_positive.instance["spec"]["template"]["spec"]["domain"]["cpu"]["features"][0]["name"])
    )


@pytest.mark.parametrize(
    "features",
    [
        pytest.param(
            [{"name": "pcid", "policy": "nomatch"}],
            id="1 invalid policy",
            marks=pytest.mark.polarion("CNV-1832"),
        ),
        pytest.param(
            [
                {"name": "pcid", "policy": "require"},
                {"name": "pclmuldq", "policy": "nomatch"},
            ],
            id="1 valid, 1 invalid policy",
            marks=[pytest.mark.polarion("CNV-3056"), pytest.mark.x86_64()],
        ),
    ],
)
def test_invalid_cpu_feature_policy_negative(unprivileged_client, namespace, features):
    """VM should not be created successfully"""
    vm_name = "invalid-cpu-feature-policy-vm"
    with pytest.raises(UnprocessibleEntityError):
        with VirtualMachineForTests(
            name=vm_name,
            namespace=namespace.name,
            cpu_flags={"features": features},
            body=fedora_vm_body(name=vm_name),
            client=unprivileged_client,
        ):
            pytest.fail("VM was created with an invalid cpu feature policy.")
