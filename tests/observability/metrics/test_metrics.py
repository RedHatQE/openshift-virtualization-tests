import pytest

from tests.observability.metrics.utils import (
    assert_vm_metric_labels,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


class TestMetricsLinux:
    @pytest.mark.polarion("CNV-11906")
    @pytest.mark.s390x
    def test_cnv_vmi_monitoring_metrics_linux_vm(
        self, prometheus, admin_client, single_metric_vm, cnv_vmi_monitoring_metrics_matrix__function__
    ):
        """Validate VM metrics contain the expected node and namespace labels."""
        assert_vm_metric_labels(
            prometheus=prometheus,
            query=cnv_vmi_monitoring_metrics_matrix__function__,
            vm=single_metric_vm,
            admin_client=admin_client,
        )


@pytest.mark.tier3
class TestMetricsWindows:
    @pytest.mark.polarion("CNV-11880")
    def test_cnv_vmi_monitoring_metrics_windows_vm(
        self, prometheus, admin_client, windows_vm_for_test, cnv_vmi_monitoring_metrics_matrix__function__
    ):
        assert_vm_metric_labels(
            prometheus=prometheus,
            query=cnv_vmi_monitoring_metrics_matrix__function__,
            vm=windows_vm_for_test,
            admin_client=admin_client,
        )


@pytest.mark.polarion("CNV-10438")
def test_cnv_installation_with_hco_cr_metrics(prometheus):
    validate_metrics_value(
        prometheus=prometheus,
        metric_name=KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS,
        expected_value="1",
    )
