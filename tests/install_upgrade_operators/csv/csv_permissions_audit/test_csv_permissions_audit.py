import logging

import pytest
import yaml
from ocp_resources.resource import Resource
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.csv.csv_permissions_audit.utils import (
    get_csv_permissions,
)
from utilities.constants.components import (
    AAQ_OPERATOR,
    CDI_OPERATOR,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HOSTPATH_PROVISIONER_OPERATOR,
    HYPERCONVERGED_CLUSTER_OPERATOR,
    KUBEVIRT_MIGRATION_OPERATOR,
    KUBEVIRT_OPERATOR,
    SSP_OPERATOR,
)
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.s390x

JIRA_LINKS = {
    KUBEVIRT_OPERATOR: "CNV-23061",
}

OPERATOR_API_GROUP_MAPPING = {
    AAQ_OPERATOR: Resource.ApiGroup.AAQ_KUBEVIRT_IO,
    CDI_OPERATOR: Resource.ApiGroup.CDI_KUBEVIRT_IO,
    CLUSTER_NETWORK_ADDONS_OPERATOR: Resource.ApiGroup.NETWORKADDONSOPERATOR_NETWORK_KUBEVIRT_IO,
    HOSTPATH_PROVISIONER_OPERATOR: Resource.ApiGroup.HOSTPATHPROVISIONER_KUBEVIRT_IO,
    HYPERCONVERGED_CLUSTER_OPERATOR: Resource.ApiGroup.HCO_KUBEVIRT_IO,
    KUBEVIRT_MIGRATION_OPERATOR: Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO,
    SSP_OPERATOR: Resource.ApiGroup.SSP_KUBEVIRT_IO,
}


@pytest.fixture(scope="module")
def csv_permissions(admin_client):
    return get_csv_permissions(
        namespace=py_config["hco_namespace"],
        csv_name_starts_with=py_config["hco_cr_name"],
        admin_client=admin_client,
    )


@pytest.mark.polarion("CNV-9548")
def test_global_csv_permissions(subtests, csv_permissions):
    for operator_name, all_permissions in csv_permissions.items():
        with subtests.test(msg=operator_name):
            errors = {}
            permissions = {
                "permission": all_permissions.get("permission", []),
                "cluster_permission": all_permissions.get("cluster_permission", []),
            }
            for key, permission_entries in permissions.items():
                error_list = []
                for _permission_entry in permission_entries:
                    LOGGER.info(f"Permission is: {_permission_entry}")
                    if "*" in _permission_entry["verbs"]:
                        operator_api_group = OPERATOR_API_GROUP_MAPPING.get(operator_name)
                        if operator_api_group and all(
                            operator_api_group in entry for entry in _permission_entry["apiGroups"]
                        ):
                            continue
                        else:
                            error_list.append(_permission_entry)
                if error_list:
                    errors[key] = error_list
            if errors:
                error_message = f"Found global permission for {operator_name}"
                LOGGER.error(yaml.dump(errors))
                if operator_name in JIRA_LINKS and is_jira_open(jira_id=JIRA_LINKS[operator_name]):
                    pytest.xfail(error_message)
                pytest.fail(error_message)
