import logging

import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_VMI_CPU_SYSTEM_USAGE_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_CPU_USAGE_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_CPU_USER_USAGE_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_VCPU_DELAY_SECONDS_TOTAL_QUERY_STR,
)
from tests.observability.metrics.utils import (
    wait_for_non_empty_metrics_value,
)

LOGGER = logging.getLogger(__name__)


class TestCpuUsageMetrics:
    @pytest.mark.parametrize(
        "query",
        [
            pytest.param(
                KUBEVIRT_VMI_VCPU_DELAY_SECONDS_TOTAL_QUERY_STR,
                marks=(pytest.mark.polarion("CNV-11368")),
            ),
            pytest.param(
                KUBEVIRT_VMI_CPU_USER_USAGE_SECONDS_TOTAL_QUERY_STR,
                marks=(pytest.mark.polarion("CNV-9742")),
            ),
            pytest.param(
                KUBEVIRT_VMI_CPU_SYSTEM_USAGE_SECONDS_TOTAL_QUERY_STR,
                marks=(pytest.mark.polarion("CNV-9740")),
            ),
            pytest.param(
                KUBEVIRT_VMI_CPU_USAGE_SECONDS_TOTAL_QUERY_STR,
                marks=(pytest.mark.polarion("CNV-9743")),
            ),
        ],
    )
    def test_vmi_non_empty_cpu_metrics(self, prometheus, query, running_metric_vm, windows_vm_for_test):
        wait_for_non_empty_metrics_value(
            prometheus=prometheus, metric_name=query.format(vm_name=running_metric_vm.name)
        )
        wait_for_non_empty_metrics_value(
            prometheus=prometheus, metric_name=query.format(vm_name=windows_vm_for_test.name)
        )
