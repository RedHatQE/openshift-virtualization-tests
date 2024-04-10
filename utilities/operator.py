from ocp_resources.catalog_source import CatalogSource
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.subscription import Subscription
from kubernetes.dynamic.exceptions import ResourceNotFoundError

from utilities.constants import NamespacesNames


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


def get_cnv_installed_csv(namespace, subscription_name):
    cnv_subscription = get_subscription(
        namespace=namespace,
        subscription_name=subscription_name,
    )
    return get_csv(
        csv_name=cnv_subscription.instance.status.installedCSV,
        namespace=namespace,
    )


def get_catalog_source(catalogsource_name):
    catalog_source = CatalogSource(
        name=catalogsource_name,
        namespace=NamespacesNames.OPENSHIFT_MARKETPLACE,
    )
    if catalog_source.exists:
        return catalog_source
    raise ResourceNotFoundError(
        f"Subscription {catalogsource_name} not found in namespace: {NamespacesNames.OPENSHIFT_MARKETPLACE}"
    )
