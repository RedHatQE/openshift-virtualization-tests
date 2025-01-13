import pytest


@pytest.mark.polarion("CNV-5949")
def test_hypervstrictcheck_feature_gate_present(kubevirt_feature_gates):
    """
    This test will ensure that 'HypervStrictCheck' feature gate enabled by default.
    """
    assert "HypervStrictCheck" in kubevirt_feature_gates
