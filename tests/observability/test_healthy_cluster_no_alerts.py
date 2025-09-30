import pytest

from tests.observability.constants import SSP_ALERTS_LIST, VIRT_ALERTS_LIST
from tests.observability.utils import verify_no_listed_alerts_on_cluster


@pytest.mark.polarion("CNV-7610")
@pytest.mark.s390x
@pytest.mark.order(0)
def test_no_virt_alerts_on_healthy_cluster(
    prometheus,
):
    verify_no_listed_alerts_on_cluster(prometheus=prometheus, alerts_list=VIRT_ALERTS_LIST)


@pytest.mark.polarion("CNV-7612")
@pytest.mark.s390x
@pytest.mark.order(1)
def test_no_ssp_alerts_on_healthy_cluster(
    prometheus,
):
    verify_no_listed_alerts_on_cluster(prometheus=prometheus, alerts_list=SSP_ALERTS_LIST)
