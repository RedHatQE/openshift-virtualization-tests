import pytest

CNV_WORKQUEUE_METRICS = [
    "kubevirt_workqueue_adds_total",
    "kubevirt_workqueue_depth",
    "kubevirt_workqueue_longest_running_processor_seconds",
    "kubevirt_workqueue_queue_duration_seconds_bucket",
    "kubevirt_workqueue_queue_duration_seconds_sum",
    "kubevirt_workqueue_queue_duration_seconds_count",
    "kubevirt_workqueue_retries_total",
    "kubevirt_workqueue_unfinished_work_seconds",
    "kubevirt_workqueue_work_duration_seconds_bucket",
    "kubevirt_workqueue_work_duration_seconds_sum",
    "kubevirt_workqueue_work_duration_seconds_count",
]


class TestWorkQueueMetrics:
    @pytest.mark.polarion("CNV-12279")
    @pytest.mark.conformance
    def test_work_queue_metrics(self, prometheus):
        metrics_without_value = [
            metric for metric in CNV_WORKQUEUE_METRICS if not prometheus.query_sampler(query=metric)
        ]
        assert not metrics_without_value, (
            f"There is workqueue metrics that not reporting any value, metrics: {metrics_without_value}"
        )
