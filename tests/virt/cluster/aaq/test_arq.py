import logging

import pytest
from ocp_resources.pod import Pod

from tests.virt.cluster.aaq.constants import (
    CPU_MAX_SOCKETS,
    MEMORY_MAX_GUEST,
    POD_LIMITS_CPU,
    POD_LIMITS_MEMORY,
    POD_REQUESTS_CPU,
    POD_REQUESTS_MEMORY,
    QUOTA_FOR_ONE_VMI,
    QUOTA_FOR_TWO_VMI,
)
from tests.virt.cluster.aaq.utils import restart_vm_wait_for_gated_state
from tests.virt.constants import (
    LIMITS_CPU_STR,
    LIMITS_MEMORY_STR,
    PODS_STR,
    REQUESTS_CPU_STR,
    REQUESTS_CPU_VMI_STR,
    REQUESTS_INSTANCES_VMI_STR,
    REQUESTS_MEMORY_STR,
    REQUESTS_MEMORY_VMI_STR,
)
from tests.virt.utils import check_arq_status_values, wait_when_pod_in_gated_state
from utilities.virt import migrate_vm_and_verify, wait_for_running_vm

LOGGER = logging.getLogger(__name__)

TESTS_POD_CLASS_NAME = "TestARQCanManagePods"
TESTS_VM_CLASS_NAME = "TestARQCanManageVMs"


pytestmark = [
    pytest.mark.usefixtures(
        "enabled_aaq_in_hco_scope_package",
        "updated_namespace_with_aaq_label",
    ),
    pytest.mark.gating,
]


@pytest.mark.arm64
@pytest.mark.s390x
@pytest.mark.usefixtures(
    "application_aware_resource_quota",
    "first_pod_for_aaq_test",
    "second_pod_for_aaq_test_in_gated_state",
)
class TestARQCanManagePods:
    @pytest.mark.dependency(name=f"{TESTS_POD_CLASS_NAME}::pod_gated")
    @pytest.mark.polarion("CNV-11234")
    def test_arq_pod_gated_when_quota_reached(
        self,
        application_aware_resource_quota,
        first_pod_for_aaq_test,
    ):
        check_arq_status_values(
            current_values=application_aware_resource_quota.instance.status.used,
            expected_values={
                **first_pod_for_aaq_test.instance.to_dict()["spec"]["containers"][0]["resources"],
                PODS_STR: "1",
            },
        )

    @pytest.mark.parametrize(
        "updated_arq_quota",
        [
            pytest.param(
                {
                    "hard": {
                        LIMITS_CPU_STR: POD_LIMITS_CPU * 2,
                        LIMITS_MEMORY_STR: f"{float(POD_LIMITS_MEMORY[:-2]) * 2}Gi",
                        REQUESTS_CPU_STR: POD_REQUESTS_CPU * 2,
                        REQUESTS_MEMORY_STR: f"{float(POD_REQUESTS_MEMORY[:-2]) * 2}Gi",
                        PODS_STR: "2",
                    },
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.dependency(depends=[f"{TESTS_POD_CLASS_NAME}::pod_gated"])
    @pytest.mark.polarion("CNV-11281")
    def test_arq_gated_pod_started_when_quota_increased(
        self,
        second_pod_for_aaq_test_in_gated_state,
        updated_arq_quota,
    ):
        second_pod_for_aaq_test_in_gated_state.wait_for_status(status=Pod.Status.RUNNING)


@pytest.mark.arm64
@pytest.mark.usefixtures(
    "application_aware_resource_quota",
    "vm_for_aaq_test",
    "vm_for_aaq_test_in_gated_state",
)
class TestARQCanManageVMs:
    @pytest.mark.dependency(name=f"{TESTS_VM_CLASS_NAME}::vm_gated")
    @pytest.mark.polarion("CNV-11235")
    def test_arq_vm_gated_when_quota_reached(
        self,
        application_aware_resource_quota,
    ):
        check_arq_status_values(
            current_values=application_aware_resource_quota.instance.status.used,
            expected_values=QUOTA_FOR_ONE_VMI,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_VM_CLASS_NAME}::vm_gated"])
    @pytest.mark.polarion("CNV-11282")
    def test_arq_vm_migration_allowed_when_quota_reached(self, vm_for_aaq_test):
        migrate_vm_and_verify(vm=vm_for_aaq_test)

    @pytest.mark.parametrize(
        "updated_arq_quota",
        [
            pytest.param(
                {
                    "hard": QUOTA_FOR_TWO_VMI,
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.dependency(depends=[f"{TESTS_VM_CLASS_NAME}::vm_gated"])
    @pytest.mark.polarion("CNV-11269")
    def test_arq_gated_vm_started_when_quota_increased(
        self,
        vm_for_aaq_test_in_gated_state,
        updated_arq_quota,
    ):
        wait_for_running_vm(vm=vm_for_aaq_test_in_gated_state)

    @pytest.mark.parametrize(
        "updated_arq_quota",
        [
            pytest.param(
                {
                    "hard": {
                        REQUESTS_INSTANCES_VMI_STR: "0",
                    },
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-11236")
    def test_arq_vm_active_and_migratable_when_lower_quota_applied(
        self, vm_for_aaq_test, updated_arq_quota, migrated_arq_vm
    ):
        restart_vm_wait_for_gated_state(vm=vm_for_aaq_test)


@pytest.mark.usefixtures(
    "application_aware_resource_quota",
    "hotplug_vm_for_aaq_test",
)
class TestARQSupportCPUHotplug:
    @pytest.mark.parametrize(
        "hotplugged_resource",
        [
            pytest.param({"sockets": 2}),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-11237")
    def test_arq_cpu_hotplug(
        self,
        application_aware_resource_quota,
        hotplug_vm_for_aaq_test,
        hotplugged_resource,
    ):
        vmi_spec_domain = hotplug_vm_for_aaq_test.vmi.instance.spec.domain
        check_arq_status_values(
            current_values=application_aware_resource_quota.instance.status.used,
            expected_values={
                **QUOTA_FOR_ONE_VMI,
                REQUESTS_CPU_VMI_STR: vmi_spec_domain.cpu.sockets,
                REQUESTS_MEMORY_VMI_STR: vmi_spec_domain.memory.guest,
            },
        )

    @pytest.mark.parametrize(
        "hotplugged_resource_exceeding_quota",
        [
            pytest.param({"sockets": CPU_MAX_SOCKETS}),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-11238")
    def test_arq_blocks_cpu_hotplug_when_quota_exceeded(
        self,
        hotplugged_resource_exceeding_quota,
        hotplugged_target_pod,
    ):
        wait_when_pod_in_gated_state(pod=hotplugged_target_pod)


@pytest.mark.arm64
class TestARQSupportMemoryHotplug:
    @pytest.mark.parametrize(
        "hotplugged_resource",
        [
            pytest.param({"memory_guest": "2Gi"}),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-11240")
    def test_arq_memory_hotplug(
        self,
        application_aware_resource_quota,
        hotplug_vm_for_aaq_test,
        hotplugged_resource,
    ):
        vmi_spec_domain = hotplug_vm_for_aaq_test.vmi.instance.spec.domain
        check_arq_status_values(
            current_values=application_aware_resource_quota.instance.status.used,
            expected_values={
                **QUOTA_FOR_ONE_VMI,
                REQUESTS_CPU_VMI_STR: vmi_spec_domain.cpu.sockets,
                REQUESTS_MEMORY_VMI_STR: vmi_spec_domain.memory.guest,
            },
        )

    @pytest.mark.parametrize(
        "hotplugged_resource_exceeding_quota",
        [pytest.param({"memory_guest": MEMORY_MAX_GUEST})],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-11239")
    def test_arq_blocks_memory_hotplug_when_quota_exceeded(
        self,
        hotplugged_resource_exceeding_quota,
        hotplugged_target_pod,
    ):
        wait_when_pod_in_gated_state(pod=hotplugged_target_pod)
