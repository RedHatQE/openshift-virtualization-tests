import pytest

from utilities.constants import ALL_CNV_DAEMONSETS, HOSTPATH_PROVISIONER_CSI
from utilities.infra import get_daemonsets

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.sno,
    pytest.mark.arm64,
    pytest.mark.s390x,
    pytest.mark.skip_must_gather_collection,
]


@pytest.fixture(scope="module")
def cnv_daemonset_names(admin_client, hco_namespace):
    return [daemonset.name for daemonset in get_daemonsets(admin_client=admin_client, namespace=hco_namespace.name)]


@pytest.mark.gating
@pytest.mark.polarion("CNV-8509")
# Not marked as `conformance` as this is a "utility" test to match against test matrix
def test_no_new_cnv_daemonset_added(hpp_cr_installed, cnv_daemonset_names):
    cnv_daemonsets = ALL_CNV_DAEMONSETS.copy()
    # Remove Hostpath Provisioner CSI daemonset if HPP CR is not installed
    if not hpp_cr_installed:
        cnv_daemonsets.remove(HOSTPATH_PROVISIONER_CSI)

    assert sorted(cnv_daemonset_names) == sorted(cnv_daemonsets), (
        f"New cnv daemonsets found: {set(cnv_daemonset_names) - set(cnv_daemonsets)}"
    )
