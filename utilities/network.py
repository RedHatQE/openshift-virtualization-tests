from ocp_resources.network import Network


class ClusterHosts:
    class Type:
        VIRTUAL = "virtual"
        PHYSICAL = "physical"


def get_cluster_cni_type(admin_client):
    return Network(client=admin_client, name="cluster").instance.status.networkType
