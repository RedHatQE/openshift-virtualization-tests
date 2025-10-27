import multiprocessing
from multiprocessing import Process


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
class ProcessWithException(Process):
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
