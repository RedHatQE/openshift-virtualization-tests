from ocp_resources.network_policy import NetworkPolicy


class ApplyNetworkPolicy(NetworkPolicy):
    def __init__(self, name, namespace, client, ports=None, teardown=True):
        super().__init__(name=name, namespace=namespace, client=client, teardown=teardown, pod_selector={})
        self.ports = ports

    def to_dict(self):
        super().to_dict()
        _ports = []
        if self.ports:
            for port in self.ports:
                _ports.append({"protocol": "TCP", "port": port})

        if _ports:
            self.res["spec"]["ingress"] = [{"ports": _ports}]