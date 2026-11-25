def test_hypervstrictcheck_feature_gate_present(kubevirt_feature_gates):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-5968 # <skip-jira-utils-check>
    Polarion: CNV-5949

    This test will ensure that 'HypervStrictCheck' feature gate enabled by default.
    """
    assert "HypervStrictCheck" in kubevirt_feature_gates
