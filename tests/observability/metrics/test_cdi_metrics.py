import pytest

from tests.observability.utils import validate_metrics_value


@pytest.mark.polarion("CNV-10557")
def test_kubevirt_cdi_clone_pods_high_restart(
    skip_test_if_no_filesystem_sc,
    skip_test_if_no_block_sc,
    prometheus,
    zero_clone_dv_restart_count,
    restarted_cdi_dv_clone,
):
    validate_metrics_value(
        prometheus=prometheus,
        expected_value="1",
        metric_name="kubevirt_cdi_clone_pods_high_restart",
    )


@pytest.mark.polarion("CNV-10717")
def test_kubevirt_cdi_upload_pods_high_restart(
    prometheus,
    zero_upload_dv_restart_count,
    restarted_cdi_dv_upload,
):
    validate_metrics_value(
        prometheus=prometheus,
        expected_value="1",
        metric_name="kubevirt_cdi_upload_pods_high_restart",
    )
