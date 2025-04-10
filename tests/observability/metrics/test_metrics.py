import bitmath
import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_API_REQUEST_DEPRECATED_TOTAL_WITH_VERSION_VERB_AND_RESOURCE,
    KUBEVIRT_VMI_INFO,
)
from tests.observability.metrics.utils import (
    assert_vm_metric_virt_handler_pod,
    assert_vmi_dommemstat_with_metric_value,
    compare_kubevirt_vmi_info_metric_with_vm_info,
    get_vm_metrics,
    validate_metric_value_within_range,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS,
    KUBEVIRT_VMI_MEMORY_ACTUAL_BALLOON_BYTES,
    KUBEVIRT_VMI_MEMORY_DOMAIN_BYTE,
    KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_PGMINFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_UNUSED_BYTES,
    KUBEVIRT_VMI_MEMORY_USABLE_BYTES,
    KUBEVIRT_VMI_NETWORK_RECEIVE_BYTES_TOTAL,
    KUBEVIRT_VMI_NETWORK_RECEIVE_PACKETS_DROPPED_TOTAL,
    KUBEVIRT_VMI_NETWORK_TRANSMIT_BYTES_TOTAL,
    KUBEVIRT_VMI_NETWORK_TRANSMIT_PACKETS_DROPPED_TOTAL,
    KUBEVIRT_VMI_STORAGE_FLUSH_REQUESTS_TOTAL,
    KUBEVIRT_VMI_STORAGE_FLUSH_TIMES_SECONDS_TOTAL,
    KUBEVIRT_VMI_STORAGE_IOPS_READ_TOTAL,
    KUBEVIRT_VMI_STORAGE_IOPS_WRITE_TOTAL,
    KUBEVIRT_VMI_STORAGE_READ_TRAFFIC_BYTES_TOTAL,
    KUBEVIRT_VMI_STORAGE_WRITE_TRAFFIC_BYTES_TOTAL,
    KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL,
    VIRT_API,
    VIRT_HANDLER,
)
from utilities.infra import is_jira_open

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]
METRICS_WITH_WINDOWS_VM_BUGS = [
    KUBEVIRT_VMI_MEMORY_UNUSED_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_USABLE_BYTES,
]


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            KUBEVIRT_VMI_NETWORK_RECEIVE_PACKETS_DROPPED_TOTAL,
            marks=pytest.mark.polarion("CNV-6657"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_NETWORK_RECEIVE_PACKETS_DROPPED_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_NETWORK_TRANSMIT_PACKETS_DROPPED_TOTAL,
            marks=pytest.mark.polarion("CNV-6658"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_NETWORK_TRANSMIT_PACKETS_DROPPED_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_DOMAIN_BYTE,
            marks=pytest.mark.polarion("CNV-8194"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_NETWORK_TRANSMIT_PACKETS_DROPPED_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_UNUSED_BYTES,
            marks=pytest.mark.polarion("CNV-6660"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_MEMORY_UNUSED_BYTES}",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_USABLE_BYTES,
            marks=pytest.mark.polarion("CNV-6661"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_MEMORY_UNUSED_BYTES}",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_ACTUAL_BALLOON_BYTES,
            marks=pytest.mark.polarion("CNV-6662"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_MEMORY_ACTUAL_BALLOON_BYTES}",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL,
            marks=pytest.mark.polarion("CNV-6663"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_PGMINFAULT_TOTAL,
            marks=pytest.mark.polarion("CNV-6664"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_MEMORY_PGMINFAULT_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_STORAGE_FLUSH_REQUESTS_TOTAL,
            marks=pytest.mark.polarion("CNV-6665"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_STORAGE_FLUSH_REQUESTS_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_STORAGE_FLUSH_TIMES_SECONDS_TOTAL,
            marks=pytest.mark.polarion("CNV-6666"),
            id=f"parity_with_rhv_metrics_{KUBEVIRT_VMI_STORAGE_FLUSH_TIMES_SECONDS_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_NETWORK_RECEIVE_BYTES_TOTAL,
            marks=pytest.mark.polarion("CNV-6174"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_NETWORK_RECEIVE_BYTES_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_NETWORK_TRANSMIT_BYTES_TOTAL,
            marks=pytest.mark.polarion("CNV-6175"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_NETWORK_TRANSMIT_BYTES_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_STORAGE_IOPS_WRITE_TOTAL,
            marks=pytest.mark.polarion("CNV-6176"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_STORAGE_IOPS_WRITE_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_STORAGE_IOPS_READ_TOTAL,
            marks=pytest.mark.polarion("CNV-6177"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_STORAGE_IOPS_READ_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_STORAGE_WRITE_TRAFFIC_BYTES_TOTAL,
            marks=pytest.mark.polarion("CNV-6178"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_STORAGE_WRITE_TRAFFIC_BYTES_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_STORAGE_READ_TRAFFIC_BYTES_TOTAL,
            marks=pytest.mark.polarion("CNV-6179"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_STORAGE_READ_TRAFFIC_BYTES_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL,
            marks=pytest.mark.polarion("CNV-6180"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL}",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
            marks=pytest.mark.polarion("CNV-6181"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES}",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
            marks=pytest.mark.polarion("CNV-6182"),
            id=f"passive_key_metrics_{KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES}",
        ),
    ],
)
def test_metrics(prometheus, single_metric_vm, query):
    """
    Tests validating ability to perform various prometheus api queries on various metrics against a given vm.
    This test also validates ability to pull metric information from a given vm's virt-handler pod and validates
    appropriate information exists for that metrics.
    """
    get_vm_metrics(prometheus=prometheus, query=query, vm_name=single_metric_vm.name)
    assert_vm_metric_virt_handler_pod(query=query, vm=single_metric_vm)


class TestMetricsWindows:
    @pytest.mark.polarion("CNV-11880")
    def test_metrics_windows_vm(self, prometheus, windows_vm_for_test, cnv_vmi_monitoring_metrics_matrix__function__):
        """
        Tests validating ability to perform various prometheus api queries on various metrics against a given vm.
        This test also validates ability to pull metric information from a given vm's virt-handler pod and validates
        appropriate information exists for that metrics.
        """
        if is_jira_open(jira_id="CNV-59679"):
            if cnv_vmi_monitoring_metrics_matrix__function__ in METRICS_WITH_WINDOWS_VM_BUGS:
                pytest.xfail(
                    f"Bug (CNV-59679), Metric: {cnv_vmi_monitoring_metrics_matrix__function__} not showing "
                    f"any value for windows vm"
                )

        get_vm_metrics(
            prometheus=prometheus, query=cnv_vmi_monitoring_metrics_matrix__function__, vm_name=windows_vm_for_test.name
        )
        assert_vm_metric_virt_handler_pod(query=cnv_vmi_monitoring_metrics_matrix__function__, vm=windows_vm_for_test)


@pytest.mark.polarion("CNV-10438")
def test_cnv_installation_with_hco_cr_metrics(
    prometheus,
):
    query_result = prometheus.query(query=KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS)["data"]["result"]
    assert str(query_result[0]["value"][1]) == "1", (
        f"Metrics query: {KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS},  result: {query_result}"
    )


class TestVMIMetrics:
    @pytest.mark.polarion("CNV-8262")
    def test_vmi_domain_total_memory_bytes(
        self,
        single_metric_vm,
        vmi_domain_total_memory_in_bytes_from_vm,
        vmi_domain_total_memory_bytes_metric_value_from_prometheus,
    ):
        """This test will check the domain total memory of VMI with given metrics output in bytes."""
        assert vmi_domain_total_memory_in_bytes_from_vm == vmi_domain_total_memory_bytes_metric_value_from_prometheus, (
            f"VM {single_metric_vm.name}'s domain memory total {vmi_domain_total_memory_in_bytes_from_vm} "
            f"is not matching with metrics value {vmi_domain_total_memory_bytes_metric_value_from_prometheus} bytes."
        )

    @pytest.mark.polarion("CNV-8931")
    def test_vmi_used_memory_bytes(
        self,
        prometheus,
        single_metric_vm,
        updated_dommemstat,
    ):
        """This test will check the used memory of VMI with given metrics output in bytes."""
        assert_vmi_dommemstat_with_metric_value(prometheus=prometheus, vm=single_metric_vm)

    @pytest.mark.polarion("CNV-11400")
    def test_kubevirt_vmi_info(self, prometheus, single_metric_vm, single_metric_vmi_guest_os_kernel_release_info):
        compare_kubevirt_vmi_info_metric_with_vm_info(
            prometheus=prometheus,
            query=KUBEVIRT_VMI_INFO.format(vm_name=single_metric_vm.name),
            expected_value="1",
            values_to_compare=single_metric_vmi_guest_os_kernel_release_info,
        )


class TestMemoryDeltaFromRequestedBytes:
    @pytest.mark.polarion("CNV-11632")
    def test_metric_kubevirt_memory_delta_from_requested_bytes_working_set(
        self, prometheus, highest_memory_usage_virt_api_pod, virt_api_requested_memory
    ):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=f"kubevirt_memory_delta_from_requested_bytes{{container='{VIRT_API}', "
            f"reason='memory_working_set_delta_from_request'}}",
            expected_value=float(
                bitmath.MiB(highest_memory_usage_virt_api_pod["memory_usage"] - virt_api_requested_memory).Byte
            ),
        )

    @pytest.mark.polarion("CNV-11633")
    def test_metric_kubevirt_memory_delta_from_requested_bytes_rss(
        self, prometheus, virt_api_rss_memory, virt_api_requested_memory
    ):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=f"kubevirt_memory_delta_from_requested_bytes{{container='{VIRT_API}', "
            f"reason='memory_rss_delta_from_request'}}",
            expected_value=float(bitmath.MiB(virt_api_rss_memory - virt_api_requested_memory).Byte),
        )

    @pytest.mark.polarion("CNV-11690")
    def test_metric_cnv_abnormal_working_set(
        self, prometheus, highest_memory_usage_virt_api_pod, virt_api_requested_memory
    ):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=f"cnv_abnormal{{container='{VIRT_API}', reason='memory_working_set_delta_from_request'}}",
            expected_value=float(
                bitmath.MiB(highest_memory_usage_virt_api_pod["memory_usage"] - virt_api_requested_memory).Byte
            ),
        )

    @pytest.mark.polarion("CNV-11691")
    def test_metric_cnv_abnormal_rss(self, prometheus, virt_api_rss_memory, virt_api_requested_memory):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=f"cnv_abnormal{{container='{VIRT_API}', reason='memory_rss_delta_from_request'}}",
            expected_value=float(bitmath.MiB(virt_api_rss_memory - virt_api_requested_memory).Byte),
        )


class TestKubeDaemonsetStatusNumberReady:
    @pytest.mark.polarion("CNV-11727")
    def test_kube_daemonset_status_number_ready(self, prometheus, virt_handler_pods_count):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kube_daemonset_status_number_ready{{daemonset='{VIRT_HANDLER}'}}",
            expected_value=virt_handler_pods_count,
        )


class TestKubevirtApiRequestDeprecatedTotal:
    @pytest.mark.polarion("CNV-11739")
    def test_metric_kubevirt_api_request_deprecated_total(self, prometheus, generated_api_deprecated_requests):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_API_REQUEST_DEPRECATED_TOTAL_WITH_VERSION_VERB_AND_RESOURCE,
            expected_value=str(generated_api_deprecated_requests),
        )


class TestAllocatableNodes:
    @pytest.mark.polarion("CNV-11818")
    def test_metirc_kubevirt_allocatable_nodes(self, prometheus, allocatable_nodes):
        validate_metrics_value(
            prometheus=prometheus, metric_name="kubevirt_allocatable_nodes", expected_value=f"{len(allocatable_nodes)}"
        )
