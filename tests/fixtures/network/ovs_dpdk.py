from typing import Final

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

OVS_DPDK_DRA_DRIVER_NAMESPACE: Final[str] = "dra-driver-ovsdpdk"


@pytest.fixture(scope="session")
def ovs_dpdk_dra_driver_namespace(admin_client: DynamicClient) -> Namespace:
    return Namespace(name=OVS_DPDK_DRA_DRIVER_NAMESPACE, client=admin_client)
