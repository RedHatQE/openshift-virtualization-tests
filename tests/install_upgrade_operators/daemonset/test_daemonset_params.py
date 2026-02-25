import pytest

from tests.install_upgrade_operators.constants import VALID_PRIORITY_CLASS
from tests.install_upgrade_operators.daemonset.utils import validate_daemonset_request_fields
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


@pytest.mark.polarion("CNV-14634")
def test_daemonset_priority_class_name(cnv_daemonset_by_name):
    if cnv_daemonset_by_name == HOSTPATH_PROVISIONER_CSI:
        assert not cnv_daemonset_by_name.instance.spec.template.spec.priorityClassName, (
            "HPP daemonset shouldn't have priority class name."
        )
    else:
        assert cnv_daemonset_by_name.instance.spec.template.spec.priorityClassName, (
            f"For daemonset {cnv_daemonset_by_name.name}, spec.template.spec.priorityClassName has not been set."
        )
        assert cnv_daemonset_by_name.instance.spec.template.spec.priorityClassName in VALID_PRIORITY_CLASS, (
            f"For daemonset {cnv_daemonset_by_name.name}, \
            unexpected priority class found: {cnv_daemonset_by_name.instance.spec.template.spec.priorityClassName}"
        )


@pytest.mark.polarion("CNV-14636")
def test_daemonset_request_param(cnv_daemonset_by_name):
    """Validates resources.requests fields keys and default cpu values for different daemonset objects"""
    validate_daemonset_request_fields(daemonset=cnv_daemonset_by_name, cpu_min_value=5)
