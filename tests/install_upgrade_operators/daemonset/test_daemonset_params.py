import pytest

from utilities.constants import ALL_CNV_DAEMONSETS, HOSTPATH_PROVISIONER_CSI
from utilities.infra import get_daemonsets
from utilities.storage import get_hostpath_provisioner

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.fixture(scope="module")
def cnv_daemonset_names(admin_client, hco_namespace):
    return [daemonset.name for daemonset in get_daemonsets(admin_client=admin_client, namespace=hco_namespace.name)]


@pytest.mark.gating
@pytest.mark.polarion("CNV-8509")
def test_no_new_cnv_daemonset_added(is_jira_53226_open, sno_cluster, cnv_daemonset_names):
    """
    Since cnv deployments image validations are done via polarion parameterization, this test has been added
    to catch any new cnv deployments that is not part of cnv_deployment_matrix
    """
    cnv_daemonsets = ALL_CNV_DAEMONSETS.copy()
    if sno_cluster or not get_hostpath_provisioner():
        cnv_daemonsets.remove(HOSTPATH_PROVISIONER_CSI)

    # daemonset passt-binding-cni will be removed with upcoming builds
    if is_jira_53226_open:
        cnv_daemonset_names.remove("passt-binding-cni")

    assert sorted(cnv_daemonset_names) == sorted(cnv_daemonsets), (
        f"New cnv daemonsets found: {set(cnv_daemonset_names) - set(cnv_daemonsets)}"
    )


@pytest.mark.polarion("CNV-8378")
def test_cnv_daemonset_sno_one_scheduled(skip_if_not_sno_cluster, cnv_daemonset_by_name):
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
