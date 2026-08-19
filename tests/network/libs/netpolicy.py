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
        pod_selector: dict | None = None,
        ingress_from_pod_selector: dict | None = None,
    ) -> None:
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            teardown=teardown,
            pod_selector={"matchLabels": pod_selector} if pod_selector else {},
        )
        self.ports = ports
        self.ingress_from_pod_selector = ingress_from_pod_selector

    def to_dict(self) -> None:
        super().to_dict()
        _ports = []
        if self.ports:
            for port in self.ports:
                _ports.append({"protocol": "TCP", "port": port})

        self.res["spec"]["policyTypes"] = ["Ingress"]

        ingress_rule: dict = {}
        if self.ingress_from_pod_selector is not None:
            ingress_rule["from"] = [{"podSelector": {"matchLabels": self.ingress_from_pod_selector}}]
        if _ports:
            ingress_rule["ports"] = _ports

        # Default deny all ingress traffic if no source selector or ports specified
        self.res["spec"]["ingress"] = [ingress_rule] if ingress_rule else []


def format_curl_command(ip_address: str, port: int, head: bool = False) -> str:
    url = f"[{ip_address}]:{port}" if ":" in ip_address else f"{ip_address}:{port}"
    head_flag = "--head " if head else ""
    return f"curl {head_flag}{url} --connect-timeout {_CURL_TIMEOUT}"
