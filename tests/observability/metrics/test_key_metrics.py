import logging

import pytest

from tests.observability.metrics import utils
from utilities.constants import (
    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
    KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]
STRESS_NG = "stress-ng --cpu 8 --io 2 --vm 2 --vm-bytes 128M --timeout 60s &>1 &"
STORAGE_WRITE = "for i in {1..10}; do head -c 10M </dev/urandom > randfile$i; done"
STORAGE_READ = "for i in {1..20}; do cat /etc/hosts; done"
NODE_STRESS_SETUP = "sudo sysctl -w kernel.sched_schedstats=1"
NODE_STRESS_CLEANUP = "sudo sysctl -w kernel.sched_schedstats=0"
STRESS_NG_MEMORY = "stress-ng --vm 2 --vm-bytes 90% --vm-method all -t 15m  &>1 &"


LOGGER = logging.getLogger(__name__)


@pytest.mark.usefixtures("vm_list", "prometheus")
class TestKeyMetrics:
    @pytest.mark.parametrize(
        "vm_metrics_setup, node_setup, query",
        [
            pytest.param(
                {"vm_commands": [utils.PING]},
                {"node_command": None},
                "kubevirt_vmi_network_receive_bytes_total",
                marks=pytest.mark.polarion("CNV-6295"),
                id="kubevirt_vmi_network_receive_bytes_total_active",
            ),
            pytest.param(
                {"vm_commands": [utils.PING]},
                {"node_command": None},
                "kubevirt_vmi_network_transmit_bytes_total",
                marks=pytest.mark.polarion("CNV-6296"),
                id="kubevirt_vmi_network_transmit_bytes_total_active",
            ),
            pytest.param(
                {"vm_commands": [STORAGE_WRITE]},
                {"node_command": None},
                "kubevirt_vmi_storage_iops_write_total",
                marks=pytest.mark.polarion("CNV-6297"),
                id="kubevirt_vmi_storage_iops_write_total_active",
            ),
            pytest.param(
                {"vm_commands": [STORAGE_READ]},
                {"node_command": None},
                "kubevirt_vmi_storage_iops_read_total",
                marks=pytest.mark.polarion("CNV-6298"),
                id="kubevirt_vmi_storage_iops_read_total_active",
            ),
            pytest.param(
                {"vm_commands": [STORAGE_WRITE]},
                {"node_command": None},
                "kubevirt_vmi_storage_write_traffic_bytes_total",
                marks=pytest.mark.polarion("CNV-6299"),
                id="kubevirt_vmi_storage_write_traffic_bytes_total_active",
            ),
            pytest.param(
                {"vm_commands": [STORAGE_READ]},
                {"node_command": None},
                "kubevirt_vmi_storage_read_traffic_bytes_total",
                marks=pytest.mark.polarion("CNV-6300"),
                id="kubevirt_vmi_storage_read_traffic_bytes_total_active",
            ),
            pytest.param(
                {"vm_commands": [STRESS_NG]},
                {
                    "node_command": {
                        "setup": NODE_STRESS_SETUP,
                        "cleanup": NODE_STRESS_CLEANUP,
                    }
                },
                KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL,
                marks=pytest.mark.polarion("CNV-6301"),
                id="kubevirt_vmi_vcpu_wait_seconds_total_active",
            ),
            pytest.param(
                {"vm_commands": [STRESS_NG]},
                {"node_command": None},
                KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
                marks=pytest.mark.polarion("CNV-6302"),
                id="kubevirt_vmi_memory_swap_in_traffic_bytes_active",
            ),
            pytest.param(
                {"vm_command": [STRESS_NG]},
                {"node_command": None},
                KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
                marks=pytest.mark.polarion("CNV-6303"),
                id="kubevirt_vmi_memory_swap_out_traffic_bytes_active",
            ),
        ],
        indirect=["vm_metrics_setup", "node_setup"],
    )
    @pytest.mark.s390x
    def test_key_metric_active(self, node_setup, vm_metrics_setup, query, prometheus):
        """
        Tests that validates various metrics are present and our ability to make prometheus cli queries for them. These
        tests, generates appropriate traffics/loads on the vm being used, to ensure associated queries return expected
        results
        """
        vm = vm_metrics_setup[0]
        LOGGER.info(f'Prometheus query: "{query}" to be run against vm: {vm.name}')
        utils.assert_prometheus_metric_values(prometheus=prometheus, query=query, vm=vm)

    @pytest.mark.parametrize(
        "vm_metrics_setup, node_setup, metric_names, query_time",
        [
            pytest.param(
                {"vm_commands": [utils.PING], "num_vms": utils.TOPK_VMS},
                {"node_command": None, "num_vms": utils.TOPK_VMS},
                [
                    "kubevirt_vmi_network_receive_bytes_total",
                    "kubevirt_vmi_network_transmit_bytes_total",
                ],
                "5m",
                marks=pytest.mark.polarion("CNV-6193"),
                id="test_top3_network_transmit_receive_bytes_total",
            ),
            pytest.param(
                {"vm_commands": [utils.PING], "num_vms": utils.TOPK_VMS},
                {"node_command": None, "num_vms": utils.TOPK_VMS},
                [
                    "kubevirt_vmi_storage_read_traffic_bytes_total",
                    "kubevirt_vmi_storage_write_traffic_bytes_total",
                ],
                "5m",
                marks=pytest.mark.polarion("CNV-6194"),
                id="test_top3_storage_read_write_traffic_bytes_total",
            ),
            pytest.param(
                {
                    "vm_commands": [
                        STORAGE_WRITE,
                        STORAGE_READ,
                    ],
                    "num_vms": utils.TOPK_VMS,
                },
                {"node_command": None, "num_vms": utils.TOPK_VMS},
                [
                    "kubevirt_vmi_storage_iops_read_total",
                    "kubevirt_vmi_storage_iops_write_total",
                ],
                "5m",
                marks=pytest.mark.polarion("CNV-6195"),
                id="test_top3_storage_iops_read_write_total",
            ),
            pytest.param(
                {
                    "vm_commands": [
                        STRESS_NG_MEMORY,
                        "swapon -s",
                    ],
                    "num_vms": utils.TOPK_VMS,
                },
                {"node_command": None, "num_vms": utils.TOPK_VMS},
                [
                    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
                    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
                ],
                "5m",
                marks=pytest.mark.polarion("CNV-6196"),
                id="test_top3_memory_swap_in_out_traffic_bytes_total",
            ),
            pytest.param(
                {"vm_commands": [STRESS_NG], "num_vms": utils.TOPK_VMS},
                {
                    "node_command": {
                        "setup": NODE_STRESS_SETUP,
                        "cleanup": NODE_STRESS_CLEANUP,
                    },
                    "num_vms": utils.TOPK_VMS,
                },
                [KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL],
                "5m",
                marks=pytest.mark.polarion("CNV-6197"),
                id="test_top3_vcpu_wait_seconds",
            ),
        ],
        indirect=["vm_metrics_setup", "node_setup"],
    )
    def test_top_metric_query(
        self,
        node_setup,
        vm_metrics_setup,
        metric_names,
        query_time,
        prometheus,
    ):
        """
        Tests validating that topk metrics queries works as expected
        """
        vm_names = [vm.name for vm in vm_metrics_setup]

        query = utils.get_topk_query(
            metric_names=metric_names,
            time_period=query_time,
        )
        LOGGER.info(f'Prometheus topk query: "{query}" to be run against vms: {vm_names} ')
        utils.assert_topk_vms(
            prometheus=prometheus,
            query=query,
            vm_list=vm_names,
        )
