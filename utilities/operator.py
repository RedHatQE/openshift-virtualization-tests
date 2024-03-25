from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.subscription import Subscription
from kubernetes.dynamic.exceptions import ResourceNotFoundError


def get_csv(csv_name, namespace):
    csv = ClusterServiceVersion(name=csv_name, namespace=namespace)
    if csv.exists:
        return csv
    raise ResourceNotFoundError(f"CSV: {csv_name} not found in namespace: {namespace}")


def get_subscription(namespace, subscription_name):
    subscription = Subscription(
        name=subscription_name,
        namespace=namespace,
    )
    if subscription.exists:
        return subscription
    raise ResourceNotFoundError(
        f"Subscription {subscription_name} not found in namespace: {namespace}"
    )
