import pytest

from utilities.constants import KUBEVIRT_WORKQUEUE_QUEUE_DURATION_SECONDS, KUBEVIRT_WORKQUEUE_WORK_DURATION_SECONDS

CNV_WORKQUEUE_METRICS = [
    "kubevirt_workqueue_adds_total",
    "kubevirt_workqueue_depth",
    "kubevirt_workqueue_longest_running_processor_seconds",
    f"{KUBEVIRT_WORKQUEUE_QUEUE_DURATION_SECONDS}_bucket",
    f"{KUBEVIRT_WORKQUEUE_QUEUE_DURATION_SECONDS}_sum",
    f"{KUBEVIRT_WORKQUEUE_QUEUE_DURATION_SECONDS}_count",
    "kubevirt_workqueue_retries_total",
    "kubevirt_workqueue_unfinished_work_seconds",
    f"{KUBEVIRT_WORKQUEUE_WORK_DURATION_SECONDS}_bucket",
    f"{KUBEVIRT_WORKQUEUE_WORK_DURATION_SECONDS}_sum",
    f"{KUBEVIRT_WORKQUEUE_WORK_DURATION_SECONDS}_count",
]


class TestWorkQueueMetrics:
    @pytest.mark.polarion("CNV-12279")
    def test_work_queue_metrics(self, prometheus):
        metrics_without_value = [
            metric for metric in CNV_WORKQUEUE_METRICS if not prometheus.query_sampler(query=metric)
        ]
        assert not metrics_without_value, (
            f"There is workqueue metrics that not reporting any value, metrics: {metrics_without_value}"
        )
