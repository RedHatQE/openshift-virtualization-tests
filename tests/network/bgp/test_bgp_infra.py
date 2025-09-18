import shlex

import pytest

from utilities.constants import QUARANTINED

pytestmark = pytest.mark.usefixtures("bgp_setup_ready")


@pytest.mark.polarion("CNV-12276")
@pytest.mark.bgp
@pytest.mark.xfail(
    reason=f"{QUARANTINED}: BGP test suite infra dependencies are not met, tracked in CNV-69734",
    run=False,
)
def test_bgp_infra(frr_external_pod, workers):
    """Simple test to check BGP infra is up and running and routes are advertised"""
    bgp_connection_info = frr_external_pod.execute(command=shlex.split('vtysh -c "show bgp neighbors"'))
    assert bgp_connection_info.count("Connections established 1; dropped 0") == len(workers)
