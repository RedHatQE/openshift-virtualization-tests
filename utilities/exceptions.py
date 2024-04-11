class ClusterSanityError(Exception):
    def __init__(self, err_str):
        self.err_str = err_str

    def __str__(self):
        return self.err_str


class UtilityPodNotFoundError(Exception):
    def __init__(self, node):
        self.node = node

    def __str__(self):
        return f"Utility pod not found for node: {self.node}"


class UrlNotFoundError(Exception):
    def __init__(self, url_request):
        self.url_request = url_request

    def __str__(self):
        return f"{self.url_request.url} not found. status code is: {self.url_request.status_code}"


class HyperconvergedNotHealthyCondition(Exception):
    def __init__(self, err_str):
        self.err_str = err_str

    def __str__(self):
        return self.err_str


class HyperconvergedSystemHealthException(Exception):
    def __init__(self, err_str):
        self.err_str = err_str

    def __str__(self):
        return self.err_str
