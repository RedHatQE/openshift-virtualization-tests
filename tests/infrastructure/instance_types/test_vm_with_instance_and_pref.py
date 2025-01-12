import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.controller_revision import ControllerRevision
from ocp_resources.resource import ResourceEditor

from tests.infrastructure.instance_types.constants import UPDATED_MEMORY_2Gi, UPDATED_MEMORY_3Gi
from utilities.constants import Images
from utilities.virt import VirtualMachineForTests, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.gating]

CLOCK_TIMEZONE = "America/New_York"
CLOCK_UTC_OFFSET = 600
CLOCK_TIMER = {
    "hpet": {"present": False},
    "hyperv": {"present": True},
    "kvm": {"present": True},
    "pit": {"present": True, "tickPolicy": "delay"},
    "rtc": {"present": True, "tickPolicy": "catchup", "track": "guest"},
}


@pytest.fixture()
def rhel_vm_spec(rhel_vm_with_instance_type_and_preference):
    return rhel_vm_with_instance_type_and_preference.instance.spec


@pytest.fixture()
def instance_controller_revision(rhel_vm_with_instance_type_and_preference, rhel_vm_spec):
    return ControllerRevision(
        name=rhel_vm_spec.instancetype.revisionName,
        namespace=rhel_vm_with_instance_type_and_preference.namespace,
    )


@pytest.fixture()
def pref_controller_revision(rhel_vm_with_instance_type_and_preference, rhel_vm_spec):
    return ControllerRevision(
        name=rhel_vm_spec.preference.revisionName,
        namespace=rhel_vm_with_instance_type_and_preference.namespace,
    )


@pytest.fixture()
def updated_memory(request):
    return request.param["updated_memory"]


@pytest.fixture()
def updated_instance_type(instance_type_for_test_scope_class, updated_memory):
    with ResourceEditor(
        patches={
            instance_type_for_test_scope_class: {
                "spec": {
                    "memory": {"guest": updated_memory},
                }
            }
        }
    ):
        yield instance_type_for_test_scope_class


@pytest.fixture()
def old_revision_name(
    rhel_vm_with_instance_type_and_preference,
):
    yield rhel_vm_with_instance_type_and_preference.instance.spec.instancetype.revisionName


@pytest.fixture()
def deleted_revision_name_restart_vm(rhel_vm_with_instance_type_and_preference):
    ResourceEditor(
        patches={rhel_vm_with_instance_type_and_preference: {"spec": {"instancetype": {"revisionName": ""}}}}
    ).update()
    rhel_vm_with_instance_type_and_preference.restart(wait=True)


@pytest.fixture()
def recreated_vm(rhel_vm_with_instance_type_and_preference):
    rhel_vm_with_instance_type_and_preference.clean_up()
    rhel_vm_with_instance_type_and_preference.deploy(wait=True)
    running_vm(
        vm=rhel_vm_with_instance_type_and_preference,
        wait_for_interfaces=False,
        check_ssh_connectivity=False,
    )
    yield rhel_vm_with_instance_type_and_preference


def validate_revision_name_update(vm_for_test, old_revision_name, updated_memory):
    guest_memory = vm_for_test.vmi.instance.spec.domain.memory.guest
    assert vm_for_test.instance.spec.instancetype.revisionName != old_revision_name, (
        "The revisionName is still {old_revision_name}, not updated after editing"
    )
    assert guest_memory == updated_memory, (
        "The Guest Memory in VMI is {guest_memory}, not updated to {updated_memory} after editing"
    )


@pytest.mark.parametrize(
    "common_instance_type_param_dict, common_vm_preference_param_dict",
    [
        pytest.param(
            {
                "name": "basic",
                "memory_requests": "1.5Gi",
            },
            {
                "name": "basic-vm-preference",
                "clock_timezone": CLOCK_TIMEZONE,
                "clock_utc_seconds_offset": CLOCK_UTC_OFFSET,
                "clock_preferred_timer": CLOCK_TIMER,
                "cpu_topology": "spread",
                "cpu_spread_options": {"across": "SocketCoresThreads", "ratio": 2},
            },
        ),
    ],
    indirect=True,
)
class TestNegativeVmWithInstanceTypeAndPref:
    @pytest.mark.polarion("CNV-11525")
    def test_vm_start_fails_with_insufficient_cpu_for_spread_option(
        self, unprivileged_client, namespace, instance_type_for_test_scope_class, vm_preference_for_test
    ):
        with pytest.raises(
            UnprocessibleEntityError,
            match=r".*vCPUs provided by the instance type are not divisible by the "
            r"Spec.PreferSpreadSocketToCoreRatio or Spec.CPU.PreferSpreadOptions.Ratio*",
        ):
            with instance_type_for_test_scope_class as vm_instance_type, vm_preference_for_test as vm_preference:
                with VirtualMachineForTests(
                    client=unprivileged_client,
                    name="rhel-vm-with-instance-type",
                    namespace=namespace.name,
                    image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
                    vm_instance_type=vm_instance_type,
                    vm_preference=vm_preference,
                ):
                    pytest.fail("Expected Failure due to UnprocessibleEntityError")


@pytest.mark.parametrize(
    "common_instance_type_param_dict, common_vm_preference_param_dict",
    [
        pytest.param(
            {
                "name": "basic",
                "preferred_cpu_topology_value": 2,
                "memory_requests": "1.5Gi",
            },
            {
                "name": "basic-vm-preference",
                "clock_timezone": CLOCK_TIMEZONE,
                "clock_utc_seconds_offset": CLOCK_UTC_OFFSET,
                "clock_preferred_timer": CLOCK_TIMER,
                "cpu_topology": "spread",
                "cpu_spread_options": {"across": "SocketCoresThreads", "ratio": 2},
            },
        ),
    ],
    indirect=True,
)
class TestVmWithInstanceTypeAndPref:
    @pytest.mark.dependency(name="start_vm_with_instance_type_and_preference")
    @pytest.mark.polarion("CNV-9087")
    def test_start_vm_with_instance_type_and_preference(self, rhel_vm_with_instance_type_and_preference):
        running_vm(vm=rhel_vm_with_instance_type_and_preference)

    @pytest.mark.dependency(depends=["start_vm_with_instance_type_and_preference"])
    @pytest.mark.polarion("CNV-9545")
    def test_instance_pref_controller_revision(
        self,
        rhel_vm_with_instance_type_and_preference,
        instance_controller_revision,
        pref_controller_revision,
    ):
        vm_name = rhel_vm_with_instance_type_and_preference.name
        assert instance_controller_revision.exists, "instance type controller revision was not created"
        assert pref_controller_revision.exists, "preference controller revision was not created"
        assert instance_controller_revision.instance["metadata"]["ownerReferences"][0]["name"] == vm_name
        assert pref_controller_revision.instance["metadata"]["ownerReferences"][0]["name"] == vm_name

    @pytest.mark.dependency(depends=["start_vm_with_instance_type_and_preference"])
    @pytest.mark.polarion("CNV-9821")
    def test_validate_clock_values(self, rhel_vm_with_instance_type_and_preference):
        clock_dict = rhel_vm_with_instance_type_and_preference.vmi.instance.to_dict()["spec"]["domain"]["clock"]
        vmi_clock_values = [
            clock_dict["timezone"],
            clock_dict["utc"]["offsetSeconds"],
            clock_dict["timer"],
        ]
        vmi_expected_values = [CLOCK_TIMEZONE, CLOCK_UTC_OFFSET, CLOCK_TIMER]
        assert vmi_clock_values == vmi_expected_values, (
            "Not all clock fields match, VMI values: {vmi_clock_values}, expected: {vmi_expected_values}"
        )

    @pytest.mark.dependency(depends=["start_vm_with_instance_type_and_preference"])
    @pytest.mark.parametrize(
        "updated_memory",
        [
            pytest.param(
                {"updated_memory": UPDATED_MEMORY_2Gi},
                marks=pytest.mark.polarion("CNV-9898"),
            )
        ],
        indirect=True,
    )
    def test_edit_instancetype_with_delete_revision_name(
        self,
        updated_memory,
        rhel_vm_with_instance_type_and_preference,
        old_revision_name,
        updated_instance_type,
        deleted_revision_name_restart_vm,
    ):
        validate_revision_name_update(
            vm_for_test=rhel_vm_with_instance_type_and_preference,
            old_revision_name=old_revision_name,
            updated_memory=updated_memory,
        )

    @pytest.mark.dependency(depends=["start_vm_with_instance_type_and_preference"])
    @pytest.mark.parametrize(
        "updated_memory",
        [
            pytest.param(
                {"updated_memory": UPDATED_MEMORY_3Gi},
                marks=pytest.mark.polarion("CNV-9911"),
            )
        ],
        indirect=True,
    )
    def test_edit_with_delete_create_vm(
        self,
        updated_memory,
        old_revision_name,
        updated_instance_type,
        recreated_vm,
    ):
        validate_revision_name_update(
            vm_for_test=recreated_vm,
            old_revision_name=old_revision_name,
            updated_memory=updated_memory,
        )
