import pytest

from utilities.constants import QUARANTINED


@pytest.mark.mtv
@pytest.mark.polarion("CNV-12458")
@pytest.mark.xfail(
    reason=f"{QUARANTINED}: Migration takes very long, tracked in MTV-3947",
    run=False,
)
def test_vm_import(mtv_migration_to_cudn_ns, mtv_migration_plan_to_cudn_ns):
    mtv_migration_plan_to_cudn_ns.wait_for_condition(
        condition=mtv_migration_plan_to_cudn_ns.Condition.Type.SUCCEEDED,
        status=mtv_migration_plan_to_cudn_ns.Condition.Status.TRUE,
        timeout=1000,
        sleep_time=10,
    )
