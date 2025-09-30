import pytest

from tests.observability.metrics.utils import expected_metric_labels_and_values, get_metric_labels_non_empty_value


@pytest.mark.polarion("CNV-11744")
@pytest.mark.s390x
def test_metric_kubevirt_cdi_storageprofile_info(prometheus, storage_class_labels_for_testing):
    expected_metric_labels_and_values(
        values_from_prometheus=get_metric_labels_non_empty_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_cdi_storageprofile_info"
            f"{{storageclass='{storage_class_labels_for_testing['storageclass']}'}}",
        ),
        expected_labels_and_values=storage_class_labels_for_testing,
    )
