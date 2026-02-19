import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_VMI_MEMORY_DOMAIN_BYTE,
    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
    KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL,
)
from tests.observability.metrics.utils import (
    assert_vm_metric_virt_handler_pod,
    get_vm_metrics,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            "kubevirt_vmi_network_receive_packets_dropped_total",
            marks=pytest.mark.polarion("CNV-6657"),
            id="parity_with_rhv_metrics_kubevirt_vmi_network_receive_packets_dropped_total",
        ),
        pytest.param(
            "kubevirt_vmi_network_transmit_packets_dropped_total",
            marks=pytest.mark.polarion("CNV-6658"),
            id="parity_with_rhv_metrics_kubevirt_vmi_network_transmit_packets_dropped_total",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_DOMAIN_BYTE,
            marks=pytest.mark.polarion("CNV-8194"),
            id="parity_with_rhv_metrics_kubevirt_vmi_memory_domain_bytes",
        ),
        pytest.param(
            "kubevirt_vmi_memory_unused_bytes",
            marks=pytest.mark.polarion("CNV-6660"),
            id="parity_with_rhv_metrics_kubevirt_vmi_memory_unused_bytes",
        ),
        pytest.param(
            "kubevirt_vmi_memory_usable_bytes",
            marks=pytest.mark.polarion("CNV-6661"),
            id="parity_with_rhv_metrics_kubevirt_vmi_memory_usable_bytes",
        ),
        pytest.param(
            "kubevirt_vmi_memory_actual_balloon_bytes",
            marks=pytest.mark.polarion("CNV-6662"),
            id="parity_with_rhv_metrics_kubevirt_vmi_memory_actual_balloon_bytes",
        ),
        pytest.param(
            "kubevirt_vmi_memory_pgmajfault_total",
            marks=pytest.mark.polarion("CNV-6663"),
            id="parity_with_rhv_metrics_kubevirt_vmi_memory_pgmajfault_total",
        ),
        pytest.param(
            "kubevirt_vmi_memory_pgminfault_total",
            marks=pytest.mark.polarion("CNV-6664"),
            id="parity_with_rhv_metrics_kubevirt_vmi_memory_pgminfault_total",
        ),
        pytest.param(
            "kubevirt_vmi_storage_flush_requests_total",
            marks=pytest.mark.polarion("CNV-6665"),
            id="parity_with_rhv_metrics_kubevirt_vmi_storage_flush_requests_total",
        ),
        pytest.param(
            "kubevirt_vmi_storage_flush_times_seconds_total",
            marks=pytest.mark.polarion("CNV-6666"),
            id="parity_with_rhv_metrics_kubevirt_vmi_storage_flush_times_seconds_total",
        ),
        pytest.param(
            "kubevirt_vmi_network_receive_bytes_total",
            marks=pytest.mark.polarion("CNV-6174"),
            id="passive_key_metrics_kubevirt_vmi_network_receive_bytes_total",
        ),
        pytest.param(
            "kubevirt_vmi_network_transmit_bytes_total",
            marks=pytest.mark.polarion("CNV-6175"),
            id="passive_key_metrics_kubevirt_vmi_network_transmit_bytes_total",
        ),
        pytest.param(
            "kubevirt_vmi_storage_iops_write_total",
            marks=pytest.mark.polarion("CNV-6176"),
            id="passive_key_metrics_kubevirt_vmi_storage_iops_write_total",
        ),
        pytest.param(
            "kubevirt_vmi_storage_iops_read_total",
            marks=pytest.mark.polarion("CNV-6177"),
            id="passive_key_metrics_kubevirt_vmi_storage_iops_read_total",
        ),
        pytest.param(
            "kubevirt_vmi_storage_write_traffic_bytes_total",
            marks=pytest.mark.polarion("CNV-6178"),
            id="passive_key_metrics_kubevirt_vmi_storage_write_traffic_bytes_total",
        ),
        pytest.param(
            "kubevirt_vmi_storage_read_traffic_bytes_total",
            marks=pytest.mark.polarion("CNV-6179"),
            id="passive_key_metrics_kubevirt_vmi_storage_read_traffic_bytes_total",
        ),
        pytest.param(
            KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL,
            marks=pytest.mark.polarion("CNV-6180"),
            id="passive_key_metrics_kubevirt_vmi_vcpu_wait_seconds_total",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
            marks=pytest.mark.polarion("CNV-6181"),
            id="passive_key_metrics_kubevirt_vmi_memory_swap_in_traffic_bytes",
        ),
        pytest.param(
            KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
            marks=pytest.mark.polarion("CNV-6182"),
            id="passive_key_metrics_kubevirt_vmi_memory_swap_out_traffic_bytes",
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


@pytest.mark.polarion("CNV-10438")
def test_cnv_installation_with_hco_cr_metrics(
    prometheus,
):
    validate_metrics_value(
        prometheus=prometheus,
        metric_name=KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS,
        expected_value="1",
    )
