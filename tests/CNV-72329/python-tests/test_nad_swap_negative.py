"""
Network NAD Hot-Swap Negative Tests

STP Reference: https://gitlab.cee.redhat.com/goron/autonomous-qe-agent/-/blob/main/examples/CNV-72329/CNV-72329_test_plan.md

Markers:
    - tier2
"""

import pytest

pytestmark = [
    pytest.mark.usefixtures("namespace"),
    pytest.mark.tier2,
]


class TestNADSwapNegative:
    """
    Tests for negative NAD swap scenarios.

    Preconditions:
        - LiveUpdateNADRef feature gate enabled
        - Test environment configured for error scenarios
    """

    __test__ = False

    def test_ts_cnv_72329_019_change_nad_to_nonexistent_network(self, admin_client, unprivileged_client, namespace):
        """
        Test that changing NAD to non-existent network is handled gracefully.

        Preconditions:
            - Valid NAD created
            - VM running with valid NAD attached

        Steps:
            1. Change NAD reference to non-existent NAD name
            2. Attempt migration
            3. Verify migration fails with clear error message
            4. Verify VM remains on source node

        Expected:
            - Migration fails with clear error
            - VM remains on source
            - VM continues to function with original NAD
        """


# Mark tests as not ready for collection
TestNADSwapNegative.test_ts_cnv_72329_019_change_nad_to_nonexistent_network.__test__ = False
