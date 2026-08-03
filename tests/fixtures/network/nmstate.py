import pytest


@pytest.fixture(scope="session")
def nmstate_dependent_placeholder():
    """
    Placeholder fixture that serves as a dependency marker for fixtures that interact
    with NMState Custom Resources (NNCP, NNCE, NNS).

    This fixture is used by pytest_collection_modifyitems to automatically detect
    and mark tests that depend on NMState functionality.
    """
    return
