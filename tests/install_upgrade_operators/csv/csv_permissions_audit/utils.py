import os
import pathlib

from kubernetes.dynamic import DynamicClient
from ocp_resources.cluster_service_version import ClusterServiceVersion


def get_yaml_file_path():
    file_path = pathlib.Path(__file__).parent.resolve()
    return os.path.join(str(file_path), "csv-permissions.yaml")


def get_csv_permissions(
    csv_name_starts_with: str, namespace: str, admin_client: DynamicClient
) -> dict[str, dict[str, list[dict[str, str]]]]:
    result_dict: dict[str, dict[str, list[dict[str, str]]]] = {}
    service_account_name_str = "serviceAccountName"
    csvs = list(ClusterServiceVersion.get(namespace=namespace, client=admin_client))
    csv = [csv for csv in csvs if csv.name.startswith(csv_name_starts_with)]
    assert csv, f"CSV name starting with {csv_name_starts_with} not found under {namespace} namespace"
    csv_dict = csv[0].instance.to_dict()
    spec = csv_dict["spec"]["install"]["spec"]
    permissions_dict = spec["permissions"]
    cluster_permissions_dict = spec["clusterPermissions"]
    for permissions in permissions_dict:
        result_dict.setdefault(permissions[service_account_name_str], {})["permission"] = permissions["rules"]
    for cluster_permissions in cluster_permissions_dict:
        result_dict.setdefault(cluster_permissions[service_account_name_str], {})["cluster_permission"] = (
            cluster_permissions["rules"]
        )
    return result_dict
