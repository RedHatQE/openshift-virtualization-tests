import logging

import pytest
import yaml
from ocp_resources.resource import Resource
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.csv.csv_permissions_audit.utils import (
    get_csv_permissions,
)
from utilities.constants import (
    CDI_OPERATOR,
    HOSTPATH_PROVISIONER_OPERATOR,
)
from utilities.infra import is_jira_open

LOGGER = logging.getLogger(__name__)

JIRA_LINKS = {
    "kubevirt-operator": "CNV-23061",
}


@pytest.fixture(scope="module")
def csv_permissions():
    return get_csv_permissions(
        namespace=py_config["hco_namespace"],
        csv_name_starts_with=py_config["hco_cr_name"],
    )


@pytest.mark.polarion("CNV-9548")
def test_global_csv_permissions(subtests, csv_permissions):
    for operator_name, all_permissions in csv_permissions.items():
        with subtests.test(msg=operator_name):
            errors = {}
            for key, permission_entries in (
                ("permission", all_permissions.get("permission", [])),
                ("cluster_permission", all_permissions.get("cluster_permission", [])),
            ):
                error_list = []
                for _permission_entry in permission_entries:
                    LOGGER.info(f"Permission is: {_permission_entry}")
                    if "*" in _permission_entry["verbs"]:
                        # whitelist the cdi/hpp owned resources for cdi operator or hpp operator
                        if (
                            operator_name == CDI_OPERATOR
                            and all(
                                Resource.ApiGroup.CDI_KUBEVIRT_IO in entry for entry in _permission_entry["apiGroups"]
                            )
                        ) or (
                            operator_name == HOSTPATH_PROVISIONER_OPERATOR
                            and all(
                                Resource.ApiGroup.HOSTPATHPROVISIONER_KUBEVIRT_IO in entry
                                for entry in _permission_entry["apiGroups"]
                            )
                        ):
                            continue
                        error_list.append(_permission_entry)
                if error_list:
                    errors[key] = error_list
            if errors:
                error_message = f"Found global permission for {operator_name}"
                LOGGER.error(yaml.dump(errors))
                if operator_name in JIRA_LINKS and is_jira_open(jira_id=JIRA_LINKS[operator_name]):
                    pytest.xfail(error_message)
                raise AssertionError(error_message)
