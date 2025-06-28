import logging
import subprocess

import pytest

from tests.install_upgrade_operators.relationship_labels.constants import ALL_LABEL_KEYS
from tests.install_upgrade_operators.utils import (
    get_ocp_resource_module_name,
    get_resource,
)
from utilities.exceptions import ResourceValueError
from utilities.infra import is_jira_open

pytestmark = pytest.mark.arm64

ALLOWLIST_STRING_LIST = [
    "dockercfg",
    "token",
    "openshift-service-ca.crt",
    "kube-root-ca.crt",
    "builder",
    "default",
    "deployer",
    "system:image-pullers",
    "system:image-builders",
    "virt-template-validator-certs",
    "plugin-serving-cert",
    "console-proxy-serving-cert",
    "hyperconverged-cluster-operator-lock",
    "kubevirt-ipam-controller-webhook-service",
    "istio-ca-root-cert",
]
PRINT_COMMAND = '{printf "%s%s",sep,$0;sep=","}'
AWK_COMMAND = f"awk '{PRINT_COMMAND}'"
COLUMNS = "KIND:.kind,NAME:.metadata.name,NAMESPACE:.metadata.namespace"
COMMAND_OPT = f"--ignore-not-found {{namespace}} -o=custom-columns={COLUMNS} --sort-by='.metadata.namespace'"
ALL_RESOURCE_COMMAND = f"oc get $(oc api-resources --verbs=list -o name | {AWK_COMMAND})"

SKIP_LABEL_CHECKS = [
    "OperatorCondition",
    "Subscription",
    "InstallPlan",
    "ClusterServiceVersion",
    "Event",
    "PackageManifest",
    "HyperConverged",
    "OperatorGroup",
    "CSIStorageCapacity",
    "Lease",
    "ReclaimSpaceJob",
    "ReclaimSpaceCronJob",
]
LOGGER = logging.getLogger(__name__)
OPEN_JIRA = {
    "Endpoints": {
        "CNV-28182": ["virt-controller", "virt-operator"],
    },
    "ConfigMap": {
        "CNV-28182": ["kubevirt-install-strategy"],
    },
}


def is_jira_allowlisted(kind, resource_name):
    jira_key = list(OPEN_JIRA[kind].keys())[0] if OPEN_JIRA.get(kind) else None
    jira_allowlisted_names = OPEN_JIRA[kind][jira_key] if jira_key and is_jira_open(jira_id=jira_key) else []
    return bool(resource_name.startswith(tuple(jira_allowlisted_names))) if jira_allowlisted_names else False


def get_all_api_resources(
    namespace_opt,
):
    resources_dict = {}
    command = f"{ALL_RESOURCE_COMMAND}  {COMMAND_OPT.format(namespace=namespace_opt)} --no-headers  2>/dev/null"
    output = subprocess.getoutput(command).splitlines()
    hco_namespace = namespace_opt.split()[-1]
    for line in output:
        kind, name, namespace = " ".join(line.split()).split(" ")
        if namespace == hco_namespace:
            resources_dict.setdefault(kind, []).append(name)

    return resources_dict


@pytest.fixture()
def cnv_resources(hco_namespace):
    return get_all_api_resources(namespace_opt=f"-n {hco_namespace.name}")


@pytest.mark.polarion("CNV-10307")
@pytest.mark.s390x
def test_relationship_labels_all_cnv_resources(
    ocp_resources_submodule_list, admin_client, cnv_resources, hco_namespace
):
    errors = {}
    for kind in cnv_resources:
        LOGGER.debug(f"Looking at kind: {kind}")
        if kind in SKIP_LABEL_CHECKS:
            LOGGER.warning(f"Skip checking for kind: {kind}")
            continue
        for name in cnv_resources[kind]:
            if any(substring in name for substring in ALLOWLIST_STRING_LIST):
                LOGGER.debug(f"{kind}, {name} is allowlisted")
                continue
            LOGGER.debug(f"Looking at element: {name}, kind: {kind}")
            resource_obj = get_resource(
                related_obj={
                    "kind": kind,
                    "name": name,
                    "namespace": hco_namespace.name,
                },
                module_name=get_ocp_resource_module_name(
                    related_object_kind=kind,
                    list_submodules=ocp_resources_submodule_list,
                ),
                admin_client=admin_client,
            )
            if resource_obj.exists:
                labels = resource_obj.instance.metadata.labels
                if not labels:
                    if not is_jira_allowlisted(kind=kind, resource_name=name):
                        errors.setdefault(kind, []).append(f"{name} has no labels")
                else:
                    if set(ALL_LABEL_KEYS).issubset(set(labels.keys())):
                        continue
                    else:
                        # Some labels are missing, we need to check if the resources are olm managed or
                        # allowlisted.
                        LOGGER.debug(
                            f"Checking for kind: {kind} resource: {name} for allowlisting: {set(labels.keys())}"
                        )
                        if (labels.get("olm.managed") and labels["olm.managed"] == "true") or is_jira_allowlisted(
                            kind=kind, resource_name=name
                        ):
                            LOGGER.warning(f"kind: {kind} resource: {name} is olm managed or allowlisted by jira")
                            continue

                        else:
                            errors.setdefault(kind, []).append(
                                f"{name} has missing labels: {labels} and is not managed by olm"
                            )
            else:
                errors.setdefault(kind, []).append(f"{name} resource not found")
    if errors:
        LOGGER.error(errors)
        raise ResourceValueError(errors)
