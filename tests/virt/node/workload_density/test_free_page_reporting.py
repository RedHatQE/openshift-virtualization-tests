import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor

from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    restart_vm_wait_for_running_vm,
    running_vm,
)


def assert_vmi_free_page_reporting(vm, expected_free_page_reporting):
    actual_free_page_reporting = vm.privileged_vmi.xml_dict["domain"]["devices"]["memballoon"]["@freePageReporting"]
    assert actual_free_page_reporting == expected_free_page_reporting, (
        f"expected free_page_reporting to be {expected_free_page_reporting}, got {actual_free_page_reporting}"
    )


@pytest.fixture(scope="class")
def free_page_reporting_vm(
    namespace,
):
    name = "free-page-reporting-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_with_dedicated_cpu(
    namespace,
):
    name = "vm-with-dedicated-cpu"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cpu_placement=True,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_with_hugepages(namespace):
    name = "vm-with-hugepage"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        hugepages_page_size="1Gi",
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def disabled_free_page_reporting_in_hco_cr(
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {"virtualMachineOptions": {"disableFreePageReporting": True}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def disabled_free_page_reporting_in_vm(free_page_reporting_vm):
    ResourceEditor({
        free_page_reporting_vm: {
            "spec": {"template": {"metadata": {"annotations": {"kubevirt.io/free-page-reporting-disabled": "true"}}}}
        }
    }).update()
    restart_vm_wait_for_running_vm(vm=free_page_reporting_vm)


@pytest.mark.gating
class TestFreePageReporting:
    @pytest.mark.dependency()
    @pytest.mark.polarion("CNV-10540")
    def test_free_page_reporting_enabled_by_default(
        self, free_page_reporting_vm, hyperconverged_resource_scope_function
    ):
        assert not hyperconverged_resource_scope_function.instance.to_dict()["spec"]["virtualMachineOptions"][
            "disableFreePageReporting"
        ]
        assert_vmi_free_page_reporting(
            vm=free_page_reporting_vm,
            expected_free_page_reporting="on",
        )

    @pytest.mark.dependency(depends=["TestFreePageReporting::test_free_page_reporting_enabled_by_default"])
    @pytest.mark.polarion("CNV-10544")
    def test_disable_free_page_reporting_on_vm_level(
        self,
        free_page_reporting_vm,
        disabled_free_page_reporting_in_vm,
    ):
        assert_vmi_free_page_reporting(
            vm=free_page_reporting_vm,
            expected_free_page_reporting="off",
        )

    @pytest.mark.polarion("CNV-10543")
    def test_disable_free_page_reporting_in_hco(
        self,
        disabled_free_page_reporting_in_hco_cr,
        free_page_reporting_vm,
    ):
        restart_vm_wait_for_running_vm(vm=free_page_reporting_vm)
        assert_vmi_free_page_reporting(
            vm=free_page_reporting_vm,
            expected_free_page_reporting="off",
        )


@pytest.mark.polarion("CNV-10596")
def test_free_page_reporting_in_vm_with_dedicated_cpu(vm_with_dedicated_cpu):
    assert_vmi_free_page_reporting(
        vm=vm_with_dedicated_cpu,
        expected_free_page_reporting="off",
    )


@pytest.mark.polarion("CNV-10597")
@pytest.mark.special_infra
@pytest.mark.hugepages
def test_free_page_reporting_in_vm_with_hugepages(vm_with_hugepages):
    assert_vmi_free_page_reporting(
        vm=vm_with_hugepages,
        expected_free_page_reporting="off",
    )
