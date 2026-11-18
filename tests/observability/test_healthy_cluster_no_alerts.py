import pytest

from tests.observability.constants import SSP_ALERTS_LIST, VIRT_ALERTS_LIST
from tests.observability.utils import verify_no_listed_alerts_on_cluster


@pytest.mark.s390x
@pytest.mark.order(0)
@pytest.mark.conformance
def test_no_virt_alerts_on_healthy_cluster(
    prometheus,
):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-4744 # <skip-jira-utils-check>
    Polarion: CNV-7610
    """
    verify_no_listed_alerts_on_cluster(prometheus=prometheus, alerts_list=VIRT_ALERTS_LIST)


@pytest.mark.s390x
@pytest.mark.order(1)
@pytest.mark.conformance
def test_no_ssp_alerts_on_healthy_cluster(
    prometheus,
):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-11353 # <skip-jira-utils-check>
    Polarion: CNV-7612
    """
    verify_no_listed_alerts_on_cluster(prometheus=prometheus, alerts_list=SSP_ALERTS_LIST)
