import pytest

pytestmark = pytest.mark.sno


@pytest.mark.polarion("CNV-8378")
def test_cnv_daemonset_sno_one_scheduled(cnv_daemonset_by_name):
    daemonset_name = cnv_daemonset_by_name.name
    daemonset_instance = cnv_daemonset_by_name.instance
    current_scheduled = daemonset_instance.status.currentNumberScheduled
    desired_scheduled = daemonset_instance.status.desiredNumberScheduled
    num_available = daemonset_instance.status.numberAvailable
    num_ready = daemonset_instance.status.numberReady
    updated_scheduled = daemonset_instance.status.updatedNumberScheduled
    base_error_message = f"For daemonset: {daemonset_name}, expected: 1, "
    assert current_scheduled == 1, f"{base_error_message} status.currentNumberScheduled: {current_scheduled}"
    assert desired_scheduled == 1, f"{base_error_message} status.desiredNumberScheduled: {desired_scheduled}"
    assert num_available == 1, f"{base_error_message} status.num_available:{num_available}"
    assert num_ready == 1, f"{base_error_message} status.num_ready:{num_ready}"
    assert updated_scheduled == 1, f"{base_error_message} status.updated_scheduled:{updated_scheduled}"
