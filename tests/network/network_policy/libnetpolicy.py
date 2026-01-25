from typing import Final

from kubernetes.dynamic import DynamicClient
from ocp_resources.network_policy import NetworkPolicy

TEST_PORTS: Final[list[int]] = [9080, 9081]
_CURL_TIMEOUT: Final[int] = 5


class ApplyNetworkPolicy(NetworkPolicy):
    def __init__(
        self,
        name: str,
        namespace: str,
        client: DynamicClient,
        ports: list[int] | None = None,
        teardown: bool = True,
    ) -> None:
        super().__init__(name=name, namespace=namespace, client=client, teardown=teardown, pod_selector={})
        self.ports = ports

    def to_dict(self) -> None:
        super().to_dict()
        _ports = []
        if self.ports:
            for port in self.ports:
                _ports.append({"protocol": "TCP", "port": port})

        self.res["spec"]["policyTypes"] = ["Ingress"]

        # Default deny all ingress traffic if no ports specified
        self.res["spec"]["ingress"] = [{"ports": _ports}] if _ports else []


def format_curl_command(ip_address: str, port: int, head: bool = False) -> str:
    url = f"[{ip_address}]:{port}" if ":" in ip_address else f"{ip_address}:{port}"
    head_flag = "--head " if head else ""
    return f"curl {head_flag}{url} --connect-timeout {_CURL_TIMEOUT}"
