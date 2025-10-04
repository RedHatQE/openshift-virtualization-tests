import logging
import re
import shlex

import pytest
import requests
import xmltodict
from bs4 import BeautifulSoup
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import Resource
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.constants import TIMEOUT_3MIN, TIMEOUT_30SEC
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_artifactory_header, get_node_selector_dict, get_node_selector_name
from utilities.virt import (
    running_vm,
    vm_instance_from_template,
)

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.usefixtures("enabled_downward_metrics_hco_featuregate"),
]


LOGGER = logging.getLogger(__name__)

RPMS_REPO_URL = f"{py_config['servers']['https_server']}cnv-tests/rpms/"


def download_and_install_vm_dump_metrics(vm, rpm_file_name):
    LOGGER.info(f"Download and install vm-dump-metrics tool to VM: {vm.name}")
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            shlex.split(
                f"curl {RPMS_REPO_URL + rpm_file_name} -k -O "
                f"-H 'Authorization: {get_artifactory_header()['Authorization']}' "
            ),
            shlex.split(f"sudo yum install -y ./{rpm_file_name}"),
        ],
    )


@pytest.fixture(scope="module")
def enabled_downward_metrics_hco_featuregate(hyperconverged_resource_scope_module):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_module: {"spec": {"featureGates": {"downwardMetrics": True}}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="module")
def rpm_file_name(nodes_cpu_architecture):
    soup_page = BeautifulSoup(
        markup=requests.get(RPMS_REPO_URL, headers=get_artifactory_header(), verify=False, timeout=TIMEOUT_30SEC).text,
        features="html.parser",
    )
    rpm_file_names = [link.get("href") for link in soup_page.find_all("a", href=re.compile(r"\.rpm$"))]
    assert rpm_file_names, f"No RPM files found at the URL - {RPMS_REPO_URL}"

    return next(
        file_name for file_name in rpm_file_names if ("s390x" in file_name) == (nodes_cpu_architecture == "s390x")
    )


@pytest.fixture()
def vhostmd_vm1(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_function,
    worker_node1,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_function,
        node_selector=get_node_selector_dict(node_selector=worker_node1.name),
    ) as vhostmd_vm1:
        vhostmd_vm1.start()
        yield vhostmd_vm1


@pytest.fixture()
def vhostmd_vm2(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_function,
    worker_node1,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_function,
        node_selector=get_node_selector_dict(node_selector=worker_node1.name),
    ) as vhostmd_vm2:
        vhostmd_vm2.start()
        yield vhostmd_vm2


@pytest.fixture()
def running_vhostmd_vm1(vhostmd_vm1, rpm_file_name):
    running_vm(vm=vhostmd_vm1, ssh_timeout=TIMEOUT_3MIN)
    download_and_install_vm_dump_metrics(vm=vhostmd_vm1, rpm_file_name=rpm_file_name)


@pytest.fixture()
def running_vhostmd_vm2(vhostmd_vm2, rpm_file_name):
    running_vm(vm=vhostmd_vm2, ssh_timeout=TIMEOUT_3MIN)
    download_and_install_vm_dump_metrics(vm=vhostmd_vm2, rpm_file_name=rpm_file_name)


def run_vm_dump_metrics(vm):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=["sudo", "vm-dump-metrics"],
    )[0]


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vhostmd_vm1, vhostmd_vm2,",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "vhostmd1",
                "vhostmd": True,
                "template_labels": RHEL_LATEST_LABELS,
                "start_vm": False,
            },
            {
                "vm_name": "vhostmd2",
                "vhostmd": True,
                "template_labels": RHEL_LATEST_LABELS,
                "start_vm": False,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-6547")
@pytest.mark.s390x
def test_vhostmd_disk(
    vhostmd_vm1,
    vhostmd_vm2,
    running_vhostmd_vm1,
    running_vhostmd_vm2,
):
    assert vhostmd_vm1.node_selector == vhostmd_vm2.node_selector, (
        f"Both the VM's should be running on the same node. "
        f"The  VM {vhostmd_vm1.name} runs on {vhostmd_vm1.node_selector} and "
        f"{vhostmd_vm2.name} runs on {vhostmd_vm2.node_selector}"
    )
    expected_vendor_metric_name = "VirtualizationVendor"
    expected_vendor_metric_value = Resource.ApiGroup.KUBEVIRT_IO
    expected_host_metric_name = "HostName"
    for vm in [vhostmd_vm1, vhostmd_vm2]:
        expected_host_metric_value = get_node_selector_name(node_selector=vm.node_selector)
        all_metric_names = []
        for metric in xmltodict.parse(xml_input=run_vm_dump_metrics(vm=vm))["metrics"]["metric"]:
            # Gather all the metric names available from vm-dump-metrics.
            for value in metric.values():
                if metric["name"]:
                    all_metric_names.append(value)
            metric_name = metric["name"]
            metric_value = metric["value"]
            if metric_name == expected_vendor_metric_name:
                assert metric_value == expected_vendor_metric_value, (
                    f"Expected: vhostmd should have {expected_vendor_metric_name} as {expected_vendor_metric_value}."
                    f"Actual: vhostmd has {metric_name} as {metric_value}."
                )
            if metric_name == expected_host_metric_name:
                assert metric_value == expected_host_metric_value, (
                    f"Expected: The VMI: {vm.name} with metric name: {expected_host_metric_name} "
                    f"should match {expected_host_metric_value}"
                    f"Actual: The VMI: {vm.name} with metric name: {metric_name} has the value {metric_value}"
                )
        assert expected_vendor_metric_name in all_metric_names, (
            f"vm-dump-metrics output {all_metric_names} does not contain {expected_vendor_metric_name}"
        )
        assert expected_host_metric_name in all_metric_names, (
            f"vm-dump-metrics output {all_metric_names} does not contain {expected_host_metric_name}"
        )
