import pytest

from utilities.constants import QUARANTINED


@pytest.mark.mtv
@pytest.mark.polarion("CNV-12208")
@pytest.mark.xfail(
    reason=f"{QUARANTINED}: Migration takes very long, tracked in MTV-3947",
    run=False,
)
def test_ip_persistence(mtv_migration):
    mtv_migration.wait_for_condition(
        condition=mtv_migration.Condition.Type.SUCCEEDED,
        status=mtv_migration.Condition.Status.TRUE,
        timeout=1000,
        sleep_time=10,
    )
