import pytest


@pytest.mark.s390x
def test_same_random_minute_after_delete_hco_pod(
    admin_client,
    hco_namespace,
    data_import_schedule_minute_and_hour_values,
    deleted_hco_operator_pod,
):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-8296 # <skip-jira-utils-check>
    Polarion: CNV-7603

    The test verifies that the random minutes field is not changed after deletion of the HCO operator pod
    """
    assert data_import_schedule_minute_and_hour_values == deleted_hco_operator_pod
