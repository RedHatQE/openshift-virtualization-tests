import bitmath
import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_API_REQUEST_DEPRECATED_TOTAL_WITH_VERSION_VERB_AND_RESOURCE,
    KUBEVIRT_VM_INFO,
    KUBEVIRT_VMI_INFO,
)
from tests.observability.metrics.utils import (
    assert_vm_metric_virt_handler_pod,
    compare_kubevirt_vmi_info_metric_with_vm_info,
    get_vm_metrics,
    validate_metric_value_within_range,
    wait_vmi_dommemstat_match_with_metric_value,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS,
    VIRT_API,
    VIRT_HANDLER,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


class TestMetricsLinux:
    @pytest.mark.polarion("CNV-11906")
    def test_cnv_vmi_monitoring_metrics_linux_vm(
        self, prometheus, single_metric_vm, cnv_vmi_monitoring_metrics_matrix__function__
    ):
        """
        Tests validating ability to perform various prometheus api queries on various metrics against a given vm.
        This test also validates ability to pull metric information from a given vm's virt-handler pod and validates
        appropriate information exists for that metrics.
        """
        get_vm_metrics(
            prometheus=prometheus, query=cnv_vmi_monitoring_metrics_matrix__function__, vm_name=single_metric_vm.name
        )
        assert_vm_metric_virt_handler_pod(query=cnv_vmi_monitoring_metrics_matrix__function__, vm=single_metric_vm)


class TestMetricsWindows:
    @pytest.mark.polarion("CNV-11880")
    def test_cnv_vmi_monitoring_metrics_windows_vm(
        self, prometheus, windows_vm_for_test, xfail_if_metric_has_bug, cnv_vmi_monitoring_metrics_matrix__function__
    ):
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


class TestVMIMetricsLinuxVms:
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
    ):
        """This test will check the used memory of VMI with given metrics output in bytes."""
        wait_vmi_dommemstat_match_with_metric_value(prometheus=prometheus, vm=single_metric_vm)

    @pytest.mark.polarion("CNV-11400")
    def test_kubevirt_vmi_info(self, prometheus, single_metric_vm, vmi_guest_os_kernel_release_info_linux):
        compare_kubevirt_vmi_info_metric_with_vm_info(
            prometheus=prometheus,
            query=KUBEVIRT_VMI_INFO.format(vm_name=single_metric_vm.name),
            expected_value="1",
            values_to_compare=vmi_guest_os_kernel_release_info_linux,
        )

    @pytest.mark.polarion("CNV-11862")
    def test_metric_kubevirt_vm_info(self, prometheus, single_metric_vm, linux_vm_info_to_compare):
        compare_kubevirt_vmi_info_metric_with_vm_info(
            prometheus=prometheus,
            query=KUBEVIRT_VM_INFO.format(vm_name=single_metric_vm.name),
            expected_value="1",
            values_to_compare=linux_vm_info_to_compare,
        )


class TestVMIMetricsWindowsVms:
    @pytest.mark.polarion("CNV-11859")
    def test_vmi_domain_total_memory_bytes_windows(
        self,
        windows_vm_for_test,
        vmi_domain_total_memory_in_bytes_from_windows_vm,
        windows_vmi_domain_total_memory_bytes_metric_value_from_prometheus,
    ):
        """This test will check the domain total memory of VMI with given metrics output in bytes."""
        assert (
            vmi_domain_total_memory_in_bytes_from_windows_vm
            == windows_vmi_domain_total_memory_bytes_metric_value_from_prometheus
        ), (
            f"VM {windows_vm_for_test.name}'s domain memory total {vmi_domain_total_memory_in_bytes_from_windows_vm} "
            "is not matching with metrics value "
            f"{windows_vmi_domain_total_memory_bytes_metric_value_from_prometheus} bytes."
        )

    @pytest.mark.polarion("CNV-11860")
    @pytest.mark.jira("CNV-59552")
    def test_vmi_used_memory_bytes_windows(
        self,
        prometheus,
        windows_vm_for_test,
    ):
        wait_vmi_dommemstat_match_with_metric_value(prometheus=prometheus, vm=windows_vm_for_test)

    @pytest.mark.polarion("CNV-11861")
    def test_kubevirt_vmi_info_windows(self, prometheus, windows_vm_for_test, vmi_guest_os_kernel_release_info_windows):
        compare_kubevirt_vmi_info_metric_with_vm_info(
            prometheus=prometheus,
            query=KUBEVIRT_VMI_INFO.format(vm_name=windows_vm_for_test.name),
            expected_value="1",
            values_to_compare=vmi_guest_os_kernel_release_info_windows,
        )

    @pytest.mark.polarion("CNV-11863")
    def test_metric_kubevirt_vm_info_windows(self, prometheus, windows_vm_for_test, windows_vm_info_to_compare):
        compare_kubevirt_vmi_info_metric_with_vm_info(
            prometheus=prometheus,
            query=KUBEVIRT_VM_INFO.format(vm_name=windows_vm_for_test.name),
            expected_value="1",
            values_to_compare=windows_vm_info_to_compare,
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
