import logging

import pytest
from ocp_utilities.monitoring import Prometheus

from utilities.infra import get_prometheus_k8s_token

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def prometheus():
    return Prometheus(
        verify_ssl=False,
        bearer_token=get_prometheus_k8s_token(duration="86400s"),
    )
