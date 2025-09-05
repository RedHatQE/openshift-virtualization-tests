from ocp_resources.network_policy import NetworkPolicy

TEST_SERVER_PORT = 9876
TEST_SERVER_APP_LABEL = "network-policy-server"


class AllowAllNetworkPolicy(NetworkPolicy):
    def __init__(self, name, namespace, client, match_labels):
        super().__init__(name=name, namespace=namespace, client=client)
        self.match_labels = match_labels

    def to_dict(self):
        super().to_dict()
        self.res["spec"] = {
            "podSelector": {"matchLabels": self.match_labels},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [{}],
            "egress": [{}],
        }
