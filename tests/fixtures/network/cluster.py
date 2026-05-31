from collections.abc import Iterator

import pytest

from libs.net.cluster import cluster_vlans


@pytest.fixture(scope="module")
def cluster_vlan_ids() -> Iterator[int]:
    return iter(cluster_vlans())
