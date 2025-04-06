import pytest

from utilities.constants import Images
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.fixture(scope="class")
def rhel_vm_with_preference(namespace, admin_client, vm_preference_for_test):
    with vm_preference_for_test as vm_preference:
        with VirtualMachineForTests(
            client=admin_client,
            name="rhel-vm-with-preference",
            namespace=namespace.name,
            image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
            memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
            vm_preference=vm_preference,
            disk_type="scsi",
        ) as vm:
            yield running_vm(vm=vm)


@pytest.mark.parametrize(
    "common_vm_preference_param_dict",
    [
        pytest.param(
            {
                "name": "basic-vm-preference",
                "devices": {"preferredDiskBus": "virtio"},
            },
        ),
    ],
    indirect=True,
)
class TestVmCPrefOverride:
    @pytest.mark.polarion("CNV-9817")
    def test_vm_diskbus(self, rhel_vm_with_preference):
        vmi_spec = rhel_vm_with_preference.vmi.instance.spec
        assert vmi_spec["domain"]["devices"]["disks"][0]["disk"]["bus"] == rhel_vm_with_preference.disk_type
