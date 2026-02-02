from collections import defaultdict

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment

from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR

EXPECTED_CNAO_COMP_NAMES = [
    "multus",
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    "kubemacpool",
    "bridge",
    "ovs-cni",
]

pytestmark = pytest.mark.sno


@pytest.fixture()
def network_daemonset_deployment_resources(admin_client, hco_namespace):
    return [
        resource
        for _type in [DaemonSet, Deployment]
        for resource in _type.get(client=admin_client, namespace=hco_namespace.name)
        if any(component in resource.name for component in EXPECTED_CNAO_COMP_NAMES)
    ]


@pytest.mark.polarion("CNV-8255")
@pytest.mark.single_nic
def test_desired_number_of_cnao_pods_on_sno_cluster(
    network_daemonset_deployment_resources,
):
    desired_num_pods = 1
    invalid_resources = defaultdict(list)
    for resource in network_daemonset_deployment_resources:
        if (
            resource.kind == "DaemonSet"
            and resource.instance.status.desiredNumberScheduled != desired_num_pods
            or resource.kind == "Deployment"
            and resource.instance.status.replicas != desired_num_pods
        ):
            invalid_resources[resource.kind].append({
                resource.name: resource.instance.status.get("desiredNumberScheduled", resource.instance.status.replicas)
            })
    assert not invalid_resources, (
        f"The following resources do not have {desired_num_pods} desired number of pods: {invalid_resources}"
    )
