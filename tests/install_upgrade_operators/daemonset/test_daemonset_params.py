import pytest

from utilities.constants import ALL_CNV_DAEMONSETS, ALL_CNV_DAEMONSETS_NO_HPP_CSI
from utilities.infra import get_daemonsets

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.fixture(scope="module")
def cnv_daemonset_names(admin_client, hco_namespace):
    return [daemonset.name for daemonset in get_daemonsets(admin_client=admin_client, namespace=hco_namespace.name)]


@pytest.mark.gating
@pytest.mark.polarion("CNV-8509")
def test_no_new_cnv_daemonset_added(sno_cluster, cnv_daemonset_names):
    """
    Since cnv deployments image validations are done via polarion parameterization, this test has been added
    to catch any new cnv deployments that is not part of cnv_deployment_matrix
    """
    cnv_daemonsets = ALL_CNV_DAEMONSETS.copy() if not sno_cluster else ALL_CNV_DAEMONSETS_NO_HPP_CSI.copy()

    assert sorted(cnv_daemonset_names) == sorted(cnv_daemonsets), (
        f"New cnv daemonsets found: {set(cnv_daemonset_names) - set(cnv_daemonsets)}"
    )
