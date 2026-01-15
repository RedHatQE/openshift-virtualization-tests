import multiprocessing
from multiprocessing.context import ForkContext

# Use fork context to avoid pickling issues like Kubernetes clients containing thread locks
_FORK_CONTEXT: ForkContext = multiprocessing.get_context("fork")


class UtilityPodNotFoundError(Exception):
    def __init__(self, node):
        self.node = node

    def __str__(self):
        return f"Utility pod not found for node: {self.node}"


class ResourceValueError(Exception):
    pass


class ResourceMissingFieldError(Exception):
    pass


class ResourceMismatch(Exception):
    pass


class MissingEnvironmentVariableError(Exception):
    pass


# code from https://stackoverflow.com/questions/19924104/python-multiprocessing-handling-child-errors-in-parent
class ProcessWithException(_FORK_CONTEXT.Process):  # type: ignore[name-defined]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pconn, self._cconn = multiprocessing.Pipe()
        self._exception = None

    def run(self):
        try:
            super().run()
            self._cconn.send(None)
        except Exception as e:
            self._cconn.send(e)
            raise e

    @property
    def exception(self):
        if self._pconn.poll():
            self._exception = self._pconn.recv()
        return self._exception


class ClusterSanityError(Exception):
    def __init__(self, err_str):
        self.err_str = err_str

    def __str__(self):
        return self.err_str


class OsDictNotFoundError(Exception):
    pass


class StorageCheckupConditionTimeoutExpiredError(Exception):
    pass


class StorageSanityError(Exception):
    def __init__(self, err_str):
        self.err_str = err_str

    def __str__(self):
        return self.err_str


class ServicePortNotFoundError(Exception):
    def __init__(self, port_number, service_name):
        self.port_number = port_number
        self.service_name = service_name

    def __str__(self):
        return f"Port {self.port_number} was not found in service {self.service_name}"


class UrlNotFoundError(Exception):
    def __init__(self, url_request):
        self.url_request = url_request

    def __str__(self):
        return f"{self.url_request.url} not found. status code is: {self.url_request.status_code}"


class MissingResourceException(Exception):
    def __init__(self, resource):
        self.resource = resource

    def __str__(self):
        return f"No resources of type {self.resource} were found. Please check the test environment setup."


class UnsupportedGPUDeviceError(Exception):
    """Exception raised when a GPU device ID is not supported."""


class SSHCommandTimeoutError(Exception):
    pass


def raise_multiple_exceptions(exceptions):
    """Raising multiple exceptions

    TODO: Move to using
    https://docs.python.org/3/tutorial/errors.html#raising-and-handling-multiple-unrelated-exceptions
    To be used when multiple exceptions need to be raised, for example when using TimeoutSampler,
    and additional information should be added (so it is viewable in junit report).
    Example:
        except TimeoutExpiredError as exp:
            raise_multiple_exceptions(
                exceptions=[
                    ValueError(f"Error message: {output}"),
                    exp,
                ]
            )

    Args:
        exceptions (list): List of exceptions to be raised. The 1st exception will appear in pytest error message;
                           all exceptions will appear in the stacktrace.

    """
    # After all exceptions were raised
    if not exceptions:
        return
    try:
        raise exceptions.pop()
    finally:
        raise_multiple_exceptions(exceptions=exceptions)
