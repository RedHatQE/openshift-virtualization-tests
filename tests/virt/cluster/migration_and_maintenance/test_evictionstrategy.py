import logging

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutSampler

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.constants import (
    EVICTIONSTRATEGY,
    LIVE_MIGRATE,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import (
    check_migration_process_after_node_drain,
    node_mgmt_console,
    restart_vm_wait_for_running_vm,
    wait_for_node_schedulable_status,
)

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.arm64, pytest.mark.rwx_default_storage]


def wait_for_vm_uid_mismatch(vmi, vmi_old_uid):
    samples = TimeoutSampler(wait_timeout=TIMEOUT_5MIN, sleep=5, func=lambda: vmi.instance.metadata.uid != vmi_old_uid)
    for sample in samples:
        if sample:
            return


def assert_vm_restarts_after_node_drain(source_node, vmi, vmi_old_uid):
    source_node_name = source_node.name
    LOGGER.info(f"The VMI was running on {source_node_name}")
    wait_for_node_schedulable_status(node=source_node, status=False)
    wait_for_vm_uid_mismatch(vmi=vmi, vmi_old_uid=vmi_old_uid)
    vmi.wait_for_status(status=vmi.Status.RUNNING, timeout=TIMEOUT_3MIN)
    assert vmi.node != source_node, f"Target node is same as source node: {source_node_name}"


@pytest.fixture()
def drained_node(vm_from_template_scope_class):
    source_node = vm_from_template_scope_class.privileged_vmi.node
    with node_mgmt_console(node=source_node, node_mgmt="drain"):
        yield source_node


@pytest.fixture()
def vmi_old_uid(vm_from_template_scope_class):
    return vm_from_template_scope_class.vmi.instance.metadata.uid


@pytest.fixture()
def hco_cr_with_evictionstrategy_none(
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"spec": {EVICTIONSTRATEGY: "None"}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def vm_restarted(vm_from_template_scope_class):
    restart_vm_wait_for_running_vm(vm=vm_from_template_scope_class, wait_for_interfaces=True)


@pytest.fixture()
def added_vm_evictionstrategy(request, vm_from_template_scope_class):
    ResourceEditor({
        vm_from_template_scope_class: {
            "spec": {"template": {"spec": {EVICTIONSTRATEGY: request.param["evictionstrategy"]}}}
        }
    }).update()
    restart_vm_wait_for_running_vm(vm=vm_from_template_scope_class, wait_for_interfaces=True)


@pytest.mark.s390x
@pytest.mark.polarion("CNV-10085")
@pytest.mark.post_upgrade
def test_evictionstrategy_not_in_templates(base_templates):
    templates_with_evictionstrategy = [
        template.name
        for template in base_templates
        if EVICTIONSTRATEGY in template.instance.objects[0].spec.template.spec.keys()
    ]
    assert not templates_with_evictionstrategy, (
        f"{EVICTIONSTRATEGY} field present in templates {templates_with_evictionstrategy}"
    )


@pytest.mark.s390x
@pytest.mark.gating
@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-10086")
def test_evictionstrategy_in_kubevirt(sno_cluster, kubevirt_config_scope_module):
    assert EVICTIONSTRATEGY in kubevirt_config_scope_module, f"{EVICTIONSTRATEGY} not present in Kubevirt"
    default_evictionstrategy_value = kubevirt_config_scope_module[EVICTIONSTRATEGY]
    expected_evictionstrategy_value = "None" if sno_cluster else LIVE_MIGRATE
    assert default_evictionstrategy_value == expected_evictionstrategy_value, (
        f"Default {EVICTIONSTRATEGY} is not correct,"
        f"Expected: {expected_evictionstrategy_value}, Current: {default_evictionstrategy_value}"
    )


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, vm_from_template_scope_class",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "vm-without-eviction-strategy",
                "template_labels": RHEL_LATEST_LABELS,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("cluster_cpu_model_scope_class")
class TestEvictionStrategy:
    @pytest.mark.polarion("CNV-10087")
    def test_hco_evictionstrategy_livemigrate_vm_no_evictionstrategy(
        self, unprivileged_client, vm_from_template_scope_class, drained_node
    ):
        check_migration_process_after_node_drain(dyn_client=unprivileged_client, vm=vm_from_template_scope_class)

    @pytest.mark.polarion("CNV-10088")
    def test_hco_evictionstrategy_none_vm_no_evictionstrategy(
        self, vm_from_template_scope_class, hco_cr_with_evictionstrategy_none, vm_restarted, vmi_old_uid, drained_node
    ):
        assert_vm_restarts_after_node_drain(
            source_node=drained_node, vmi=vm_from_template_scope_class.vmi, vmi_old_uid=vmi_old_uid
        )

    @pytest.mark.parametrize(
        "added_vm_evictionstrategy",
        [pytest.param({"evictionstrategy": "None"})],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-10073")
    def test_hco_evictionstrategy_livemigrate_vm_evictionstrategy_none(
        self, vm_from_template_scope_class, added_vm_evictionstrategy, vmi_old_uid, drained_node
    ):
        assert_vm_restarts_after_node_drain(
            source_node=drained_node, vmi=vm_from_template_scope_class.vmi, vmi_old_uid=vmi_old_uid
        )

    @pytest.mark.parametrize(
        "added_vm_evictionstrategy",
        [pytest.param({"evictionstrategy": "LiveMigrate"})],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-10357")
    def test_hco_evictionstrategy_none_vm_evictionstrategy_livemigrate(
        self,
        unprivileged_client,
        vm_from_template_scope_class,
        hco_cr_with_evictionstrategy_none,
        added_vm_evictionstrategy,
        drained_node,
    ):
        check_migration_process_after_node_drain(dyn_client=unprivileged_client, vm=vm_from_template_scope_class)
