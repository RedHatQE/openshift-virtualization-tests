from ocp_resources.namespace import Namespace
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from utilities.operator import get_subscription, get_csv


def get_namespace(name):
    namespace = Namespace(name=name)
    if namespace.exists:
        return namespace
    raise ResourceNotFoundError(f"Namespace: {name} not found")


def get_cnv_installed_csv(namespace, subscription_name):
    cnv_subscription = get_subscription(
        namespace=namespace,
        subscription_name=subscription_name,
    )
    return get_csv(
        csv_name=cnv_subscription.instance.status.installedCSV,
        namespace=namespace,
    )
