from tests.fixtures.network.multiarch import get_worker_arch_pairs


def pytest_generate_tests(metafunc):
    if "arch_pair_vms" in metafunc.fixturenames:
        pairs = get_worker_arch_pairs()
        metafunc.parametrize(
            "arch_pair_vms",
            pairs,
            indirect=True,
            ids=[f"{a}-{b}" for a, b in pairs],
            scope="class",
        )
