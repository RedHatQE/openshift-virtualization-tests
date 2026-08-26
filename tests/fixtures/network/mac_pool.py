import logging

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.config_map import ConfigMap
from ocp_resources.deployment import Deployment
from ocp_resources.mutating_webhook_config import MutatingWebhookConfiguration

from utilities.constants.components import KUBEMACPOOL_MAC_CONTROLLER_MANAGER
from utilities.constants.networking import KMP_ENABLED_LABEL, KMP_VM_ASSIGNMENT_LABEL, KUBEMACPOOL_MAC_RANGE_CONFIG
from utilities.infra import create_ns
from utilities.network import MacPool

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def mac_pool(admin_client, hco_namespace):
    return MacPool(
        kmp_range=ConfigMap(
            namespace=hco_namespace.name, name=KUBEMACPOOL_MAC_RANGE_CONFIG, client=admin_client
        ).instance["data"]
    )


@pytest.fixture(scope="session")
def kmp_vm_label(admin_client):
    kmp_webhook_config = MutatingWebhookConfiguration(client=admin_client, name="kubemacpool-mutator")

    for webhook in kmp_webhook_config.instance.to_dict()["webhooks"]:
        if webhook["name"] == KMP_VM_ASSIGNMENT_LABEL:
            return {
                ldict["key"]: ldict["values"][0]
                for ldict in webhook["namespaceSelector"]["matchExpressions"]
                if ldict["key"] == KMP_VM_ASSIGNMENT_LABEL
            }

    raise ResourceNotFoundError(f"Webhook {KMP_VM_ASSIGNMENT_LABEL} was not found")


@pytest.fixture(scope="class")
def kmp_enabled_ns(admin_client, kmp_vm_label):
    # Enabling label "allocate" (or any other non-configured label) - Allocates.
    kmp_vm_label[KMP_VM_ASSIGNMENT_LABEL] = KMP_ENABLED_LABEL
    yield from create_ns(admin_client=admin_client, name="kmp-enabled", labels=kmp_vm_label)


@pytest.fixture(scope="session")
def kmp_enabled_namespace(kmp_vm_label, unprivileged_client, admin_client):
    # Enabling label "allocate" (or any other non-configured label) - Allocates.
    kmp_vm_label[KMP_VM_ASSIGNMENT_LABEL] = KMP_ENABLED_LABEL
    yield from create_ns(
        name="kmp-enabled-for-upgrade",
        labels=kmp_vm_label,
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
    )


@pytest.fixture(scope="module")
def kmp_deployment(admin_client, hco_namespace):
    return Deployment(namespace=hco_namespace.name, name=KUBEMACPOOL_MAC_CONTROLLER_MANAGER, client=admin_client)
