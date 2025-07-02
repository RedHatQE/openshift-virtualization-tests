import logging

import pytest
import yaml
from dictdiffer import diff
from ocp_resources.resource import Resource
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.csv.csv_permissions_audit.utils import (
    get_csv_permissions,
    get_yaml_file_path,
)
from utilities.constants import (
    CDI_OPERATOR,
    CNV_OPERATORS,
    HOSTPATH_PROVISIONER_OPERATOR,
)
from utilities.infra import is_jira_open

LOGGER = logging.getLogger(__name__)

JIRA_LINKS = {
    "kubevirt-operator": "CNV-23061",
}


@pytest.fixture()
def global_permission_from_csv(cnv_operators_matrix__function__, csv_permissions):
    for service_account_name, all_permissions in csv_permissions.items():
        if cnv_operators_matrix__function__ == service_account_name:
            return {
                "permission": all_permissions.get("permission", []),
                "cluster_permission": all_permissions.get("cluster_permission", []),
            }


@pytest.fixture(scope="module")
def operators_from_csv(csv_permissions):
    return {service_account_name for service_account_name, all_permissions in csv_permissions.items()}


@pytest.fixture(scope="module")
def csv_permissions():
    return get_csv_permissions(
        namespace=py_config["hco_namespace"],
        csv_name_starts_with=py_config["hco_cr_name"],
    )


@pytest.fixture(scope="module")
def csv_permissions_from_yaml(pytestconfig):
    file_path = get_yaml_file_path()
    if pytestconfig.option.update_csv:
        LOGGER.warning(f"Updating content for {file_path}.")
        with open(file_path, "w") as fd:
            fd.write(
                yaml.dump(
                    get_csv_permissions(
                        namespace=py_config["hco_namespace"],
                        csv_name_starts_with=py_config["hco_cr_name"],
                    )
                )
            )
    with open(file_path, "r") as fd:
        return yaml.safe_load(fd)


@pytest.mark.polarion("CNV-9805")
@pytest.mark.s390x
def test_new_operator_in_csv(operators_from_csv):
    assert sorted(list(operators_from_csv)) == sorted(CNV_OPERATORS), (
        f"Expected cnv operators:{CNV_OPERATORS} does not match operators {operators_from_csv} "
    )


@pytest.mark.polarion("CNV-9547")
@pytest.mark.s390x
def test_compare_csv_permissions(cnv_operators_matrix__function__, csv_permissions_from_yaml, csv_permissions):
    from_yaml = csv_permissions_from_yaml.get(cnv_operators_matrix__function__, {})
    from_csv = csv_permissions.get(cnv_operators_matrix__function__, {})
    _diff = list(diff(from_yaml, from_csv))
    if _diff:
        LOGGER.error(f"CSV permission comparison failed for {cnv_operators_matrix__function__} with diff: {_diff}")
        raise AssertionError(
            f"For {cnv_operators_matrix__function__} unexpected differences in CNV CSV permissions compare to saved "
            f"permissions in {get_yaml_file_path()}"
        )


@pytest.mark.polarion("CNV-9548")
@pytest.mark.s390x
def test_global_csv_permissions(cnv_operators_matrix__function__, global_permission_from_csv):
    error_message = f"Found global permission for {cnv_operators_matrix__function__}"
    errors = {}
    for key in global_permission_from_csv:
        error_list = []
        for _permission_entry in global_permission_from_csv[key]:
            LOGGER.info(f"Permission is: {_permission_entry}")
            if "*" in _permission_entry["verbs"]:
                # whitelist the cdi/hpp owned resources for cdi operator or hpp operator
                if (
                    cnv_operators_matrix__function__ == CDI_OPERATOR
                    and all(Resource.ApiGroup.CDI_KUBEVIRT_IO in entry for entry in _permission_entry["apiGroups"])
                ) or (
                    cnv_operators_matrix__function__ == HOSTPATH_PROVISIONER_OPERATOR
                    and all(
                        Resource.ApiGroup.HOSTPATHPROVISIONER_KUBEVIRT_IO in entry
                        for entry in _permission_entry["apiGroups"]
                    )
                ):
                    continue
                else:
                    error_list.append(_permission_entry)
        if error_list:
            errors[key] = error_list
    if errors:
        LOGGER.error(yaml.dump(errors))
        if cnv_operators_matrix__function__ in JIRA_LINKS.keys() and is_jira_open(
            jira_id=JIRA_LINKS[cnv_operators_matrix__function__]
        ):
            pytest.xfail(error_message)
        raise AssertionError(error_message)
