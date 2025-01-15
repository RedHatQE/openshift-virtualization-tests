import pytest

from tests.observability.metrics.utils import verify_metric_labels_value
from tests.observability.utils import validate_metrics_value


class TestKubeNodesStatusAndLabels:
    @pytest.mark.polarion("CNV-11741")
    def test_metric_kube_node_labels(self, prometheus, nodes_allocatable_info, node_labels_exists):
        verify_metric_labels_value(
            prometheus=prometheus,
            metric_name=f"kube_node_labels{{node='{nodes_allocatable_info['node_name']}'}}",
            label=node_labels_exists,
        )

    @pytest.mark.polarion("CNV-11742")
    def test_metric_kube_node_status_allocatable(
        self, prometheus, nodes_allocatable_info, nodes_allocatable_data_to_check_exists
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kube_node_status_allocatable{{node='{nodes_allocatable_info['node_name']}',resource='pods'}}",
            expected_value=nodes_allocatable_data_to_check_exists,
        )
