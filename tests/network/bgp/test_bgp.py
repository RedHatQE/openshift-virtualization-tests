import pytest


@pytest.mark.polarion("CNV-0000")
@pytest.mark.skip(reason="BGP test is not implemented yet")
def test_bgp(frr_external_pod, cudn_route_advertisements, frr_configuration):
    # Placeholder for BGP test implementation
    pass
