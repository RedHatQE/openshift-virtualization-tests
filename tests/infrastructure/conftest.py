import bitmath
import pytest


@pytest.fixture(scope="session")
def hugepages_gib_values(workers):
    """Return the list of hugepage sizes (in GiB) across all worker nodes."""
    return [
        int(bitmath.parse_string_unsafe(value).GiB)
        for worker in workers
        if (value := worker.instance.status.allocatable.get("hugepages-1Gi"))
    ]


@pytest.fixture(scope="session")
def xfail_if_no_huge_pages(hugepages_gib_values):
    """Mark tests as xfail if the cluster lacks 1Gi hugepages."""
    if not hugepages_gib_values or max(hugepages_gib_values) < 1:
        pytest.xfail("Requires at least 1Gi hugepages on some node")


@pytest.fixture(scope="session")
def hugepages_gib_max(xfail_if_no_huge_pages, hugepages_gib_values):
    """Return the maximum 1Gi hugepage size, capped at 64Gi."""
    return min(max(hugepages_gib_values), 64)
