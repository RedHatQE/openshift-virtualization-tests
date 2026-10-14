import multiprocessing
from datetime import UTC, datetime
from signal import SIGINT, SIGTERM, getsignal, signal

import pytest


@pytest.fixture(scope="module")
def multiprocessing_start_method_fork():
    """Temporarily set multiprocessing start method to ``fork``.

    Side effects:
        Changes the process-global multiprocessing start method to ``fork``
        for the module lifetime, then restores the previous method on teardown.
    """
    # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.Process
    # https://github.com/python/cpython/issues/132898
    original_start_method = multiprocessing.get_start_method(allow_none=True)
    multiprocessing.set_start_method("fork", force=True)
    yield
    multiprocessing.set_start_method(original_start_method, force=True)


@pytest.fixture(scope="session")
def session_start_time() -> datetime:
    """
    Capture when test session started in UTC.

    Uses UTC to match the timezone used in audit log file names.

    Returns:
        datetime: UTC timestamp when test session began (timezone-naive)
    """
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(scope="session")
def junitxml_plugin(request, record_testsuite_property):
    return record_testsuite_property if request.config.pluginmanager.hasplugin("junitxml") else None


@pytest.fixture
def term_handler_scope_function():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="class")
def term_handler_scope_class():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="module")
def term_handler_scope_module():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="session")
def term_handler_scope_session():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


# TODO: Replace this fixture with py_config.get("conformance_tests")
@pytest.fixture(scope="session")
def conformance_tests(request):
    return (
        (marker_args := request.config.getoption("-m"))
        and "conformance" in marker_args
        and "not conformance" not in marker_args
    )
