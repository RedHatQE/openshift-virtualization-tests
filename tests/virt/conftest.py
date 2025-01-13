import pytest

from utilities.constants import AMD, INTEL


@pytest.fixture(scope="session")
def nodes_intel_cpu_model(cluster_common_modern_node_cpu, nodes_cpu_vendor):
    return cluster_common_modern_node_cpu if nodes_cpu_vendor == INTEL else None


@pytest.fixture(scope="session")
def nodes_cpu_virt_extension(nodes_cpu_vendor):
    if nodes_cpu_vendor == INTEL:
        return "vmx"
    elif nodes_cpu_vendor == AMD:
        return "svm"
    else:
        return None


@pytest.fixture(scope="session")
def vm_cpu_flags(nodes_cpu_virt_extension):
    return (
        {
            "features": [
                {
                    "name": nodes_cpu_virt_extension,
                    "policy": "require",
                }
            ]
        }
        if nodes_cpu_virt_extension
        else None
    )


@pytest.fixture(scope="session")
def skip_on_psi_cluster(is_psi_cluster):
    if is_psi_cluster:
        pytest.skip("This test should be skipped on a PSI cluster")
