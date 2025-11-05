import pytest

from tests.infrastructure.numa.utils import assert_qos_guaranteed
from tests.utils import (
    assert_numa_cpu_allocation,
    assert_virt_launcher_pod_cpu_manager_node_selector,
    get_numa_node_cpu_dict,
    get_vm_cpu_list,
)
from utilities.virt import validate_libvirt_persistent_domain


@pytest.mark.special_infra
@pytest.mark.hugepages
class TestBasicCx1Numa:
    @pytest.mark.polarion("CNV-12364")
    def test_numa_pod_resource_limits_match_requests(self, created_vm_cx1_instancetype):
        container = created_vm_cx1_instancetype.vmi.virt_launcher_pod.instance.spec.containers[0]
        limits = container.resources.limits or {}
        requests = container.resources.requests or {}

        mismatches = []
        for key in ("cpu", "memory", "hugepages-1Gi"):  # ignoring devices and ephemeral-storage
            if limits[key] != requests[key]:
                mismatches.append(f"{key}: limit={limits[key]}, request={requests[key]}")
        assert not mismatches, f"Mismatches found: {mismatches}"

    @pytest.mark.polarion("CNV-12365")
    def test_numa_pod_qos_class_guaranteed(self, created_vm_cx1_instancetype):
        assert_qos_guaranteed(vm=created_vm_cx1_instancetype)

    @pytest.mark.polarion("CNV-12366")
    def test_numa_virt_launcher_pod_cpu_manager_node_selector(self, created_vm_cx1_instancetype):
        assert_virt_launcher_pod_cpu_manager_node_selector(
            virt_launcher_pod=created_vm_cx1_instancetype.vmi.virt_launcher_pod.instance
        )

    @pytest.mark.polarion("CNV-12367")
    def test_numa_cpu_allocation(self, created_vm_cx1_instancetype):
        assert_numa_cpu_allocation(
            vm_cpus=get_vm_cpu_list(vm=created_vm_cx1_instancetype),
            numa_nodes=get_numa_node_cpu_dict(vm=created_vm_cx1_instancetype),
        )

    @pytest.mark.polarion("CNV-12368")
    def test_live_migrate_numa_vm(
        self, skip_access_mode_rwo_scope_class, created_vm_cx1_instancetype, migrated_numa_cx1_vm
    ):
        validate_libvirt_persistent_domain(vm=created_vm_cx1_instancetype)
        assert_qos_guaranteed(vm=created_vm_cx1_instancetype)
        assert_numa_cpu_allocation(
            vm_cpus=get_vm_cpu_list(vm=created_vm_cx1_instancetype),
            numa_nodes=get_numa_node_cpu_dict(vm=created_vm_cx1_instancetype),
        )
