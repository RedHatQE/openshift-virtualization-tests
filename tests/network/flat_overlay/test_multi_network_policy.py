import pytest

from tests.network.flat_overlay.constants import CONNECTION_REQUESTS, HTTP_SUCCESS_RESPONSE_STR
from tests.network.flat_overlay.utils import get_vm_connection_reply
from tests.network.utils import assert_no_ping
from utilities.network import assert_ping_successful

pytestmark = pytest.mark.usefixtures(
    "enable_multi_network_policy_usage",
    "flat_l2_port",
)


@pytest.mark.polarion("CNV-10644")
@pytest.mark.s390x
def test_positive_egress_multi_network_policy(
    vma_flat_overlay,
    vmb_flat_overlay_ip_address,
    vma_egress_multi_network_policy,
):
    assert_ping_successful(
        src_vm=vma_flat_overlay,
        dst_ip=vmb_flat_overlay_ip_address,
    )


@pytest.mark.polarion("CNV-10645")
@pytest.mark.s390x
def test_negative_ingress_multi_network_policy(
    vma_flat_overlay,
    vmb_flat_overlay_ip_address,
    vmb_ingress_multi_network_policy,
):
    assert_no_ping(
        src_vm=vma_flat_overlay,
        dst_ip=vmb_flat_overlay_ip_address,
    )


@pytest.mark.dependency(name="test_multi_network_policy_is_effective_post_migration")
@pytest.mark.polarion("CNV-11361")
def test_multi_network_policy_is_effective_post_migration(
    flat_l2_port,
    vmc_flat_overlay_ip_address,
    vmd_flat_overlay,
    vmc_nc_connection_initialization,
    vmc_ingress_multi_network_policy,
    vmd_connection_response,
    migrated_vmc_flat_overlay,
):
    assert (
        get_vm_connection_reply(source_vm=vmd_flat_overlay, dst_ip=vmc_flat_overlay_ip_address, port=flat_l2_port)
        == f"{HTTP_SUCCESS_RESPONSE_STR}-{CONNECTION_REQUESTS}"
    )
