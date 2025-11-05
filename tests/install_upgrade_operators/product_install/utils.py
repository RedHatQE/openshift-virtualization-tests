import json
import logging
import subprocess

from ocp_resources.deployment import Deployment

from tests.utils import wait_for_pod_running_by_prefix
from utilities.constants import (
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_OPERATOR,
    TIMEOUT_15MIN,
)
from utilities.data_collector import write_to_file
from utilities.storage import verify_hpp_pool_health

PRINT_COMMAND = '{printf "%s%s",sep,$0;sep=","}'
AWK_COMMAND = f"awk '{PRINT_COMMAND}'"
COMMAND_OPT = (
    "--ignore-not-found --all-namespaces -o=custom-columns=KIND:.kind,NAME:.metadata.name,"
    "NAMESPACE:.metadata.namespace --sort-by='.metadata.namespace'"
)
ALL_RESOURCE_COMMAND = f"oc get $(oc api-resources --verbs=list -o name | {AWK_COMMAND})  {COMMAND_OPT}"

LOGGER = logging.getLogger(__name__)


def get_all_resources(file_name, base_directory):
    namespaced_resources_dict = {}
    cluster_resources_dict = {}

    output = subprocess.getoutput(ALL_RESOURCE_COMMAND).splitlines()
    for line in output:
        if line.startswith("Warning: ") or line.startswith("KIND "):
            continue
        line = " ".join(line.split())
        temp = line.split(" ")
        kind = temp[0]
        namespace = temp[2]
        name = temp[1]

        if not namespace or "none" in namespace:
            if kind not in cluster_resources_dict:
                cluster_resources_dict[kind] = []
            cluster_resources_dict[kind].append(name)
        else:
            if namespace not in namespaced_resources_dict:
                namespaced_resources_dict[namespace] = {}
            if kind not in namespaced_resources_dict[namespace]:
                namespaced_resources_dict[namespace][kind] = []
            namespaced_resources_dict[namespace][kind].append(name)
    write_to_file(
        base_directory=base_directory,
        file_name=f"{file_name}-namespaced.txt",
        content=json.dumps(namespaced_resources_dict),
    )
    write_to_file(
        base_directory=base_directory,
        file_name=f"{file_name}-cluster-scoped.txt",
        content=json.dumps(cluster_resources_dict),
    )
    LOGGER.info({
        "namespaced": namespaced_resources_dict,
        "cluster-scoped": cluster_resources_dict,
    })
    return {
        "namespaced": namespaced_resources_dict,
        "cluster-scoped": cluster_resources_dict,
    }


def validate_hpp_installation(admin_client, cnv_namespace, schedulable_nodes):
    hpp_deployment = Deployment(name=HOSTPATH_PROVISIONER_OPERATOR, namespace=cnv_namespace.name)
    assert hpp_deployment.exists
    hpp_deployment.wait_for_replicas(timeout=TIMEOUT_15MIN)
    wait_for_pod_running_by_prefix(
        admin_client=admin_client,
        namespace_name=cnv_namespace.name,
        pod_prefix=HOSTPATH_PROVISIONER,
        expected_number_of_pods=len(schedulable_nodes) + int(hpp_deployment.instance.status.replicas),
    )
    verify_hpp_pool_health(
        admin_client=admin_client,
        schedulable_nodes=schedulable_nodes,
        hco_namespace=cnv_namespace,
    )
