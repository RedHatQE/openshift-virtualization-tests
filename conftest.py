# -*- coding: utf-8 -*-
"""
Pytest conftest file for CNV tests
"""

import datetime
import logging
import os
import os.path
import pathlib
import re
import shlex
import shutil
import traceback
from typing import Any

import pytest
import shortuuid
from _pytest.config import Config
from _pytest.nodes import Collector, Node
from _pytest.reports import CollectReport, TestReport
from _pytest.runner import CallInfo
from kubernetes.dynamic.exceptions import ConflictError
from ocp_resources.resource import get_client
from pyhelper_utils.shell import run_command
from pytest import Item
from pytest_testconfig import config as py_config

import utilities.infra
from utilities.bitwarden import get_cnv_tests_secret_by_name
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5MIN, NamespacesNames
from utilities.data_collector import (
    collect_default_cnv_must_gather_with_vm_gather,
    get_data_collector_dir,
    set_data_collector_directory,
    set_data_collector_values,
)
from utilities.database import Database
from utilities.exceptions import MissingEnvironmentVariableError, StorageSanityError
from utilities.logger import setup_logging
from utilities.pytest_utils import (
    config_default_storage_class,
    deploy_run_in_progress_config_map,
    deploy_run_in_progress_namespace,
    get_artifactory_server_url,
    get_base_matrix_name,
    get_cnv_version_explorer_url,
    get_matrix_params,
    reorder_early_fixtures,
    run_in_progress_config_map,
    separator,
    skip_if_pytest_flags_exists,
    stop_if_run_in_progress,
    update_storage_class_matrix_config,
)

LOGGER = logging.getLogger(__name__)
BASIC_LOGGER = logging.getLogger("basic")

EXCLUDE_MARKER_FROM_TIER2_MARKER = [
    "destructive",
    "chaos",
    "tier3",
    "install",
    "benchmark",
    "sap_hana",
    "scale",
    "longevity",
    "ovs_brcnv",
    "node_remediation",
    "swap",
]

TEAM_MARKERS = {
    "chaos": ["chaos", "deprecated_api"],
    "virt": ["virt", "deprecated_api"],
    "network": ["network", "deprecated_api"],
    "storage": ["storage", "deprecated_api"],
    "iuo": ["install_upgrade_operators", "deprecated_api"],
    "observability": ["observability", "deprecated_api"],
    "infrastructure": ["infrastructure", "deprecated_api"],
    "data_protection": ["data_protection", "deprecated_api"],
}
NAMESPACE_COLLECTION = {
    "storage": [NamespacesNames.OPENSHIFT_STORAGE],
    "network": ["openshift-nmstate"],
    "virt": [],
}
MUST_GATHER_IGNORE_EXCEPTION_LIST = [MissingEnvironmentVariableError, StorageSanityError, ConflictError]
INSPECT_BASE_COMMAND = "oc adm inspect"


def pytest_addoption(parser):
    matrix_group = parser.getgroup(name="Matrix")
    os_group = parser.getgroup(name="OS")
    install_upgrade_group = parser.getgroup(name="Upgrade")
    storage_group = parser.getgroup(name="Storage")
    cluster_sanity_group = parser.getgroup(name="ClusterSanity")
    data_collector_group = parser.getgroup(name="DataCollector")
    deprecate_api_test_group = parser.getgroup(name="DeprecateTestAPI")
    leftovers_collector = parser.getgroup(name="LeftoversCollector")
    scale_group = parser.getgroup(name="Scale")
    session_group = parser.getgroup(name="Session")
    csv_group = parser.getgroup(name="CSV")
    csv_group.addoption("--update-csv", action="store_true")
    # Upgrade addoption
    install_upgrade_group.addoption(
        "--upgrade",
        choices=["cnv", "ocp", "eus"],
        help="Run OCP or CNV or EUS upgrade tests",
    )
    install_upgrade_group.addoption(
        "--upgrade_custom", choices=["cnv", "ocp"], help="Run OCP or CNV upgrade tests with custom lanes"
    )

    # CNV upgrade options
    install_upgrade_group.addoption("--cnv-version", help="CNV version to install or upgrade to")
    install_upgrade_group.addoption("--cnv-image", help="Path to CNV index-image")
    install_upgrade_group.addoption(
        "--cnv-source",
        help="CNV source lane",
        default="osbs",
        choices=["production", "fbc", "osbs"],
    )

    # OCP upgrade options
    install_upgrade_group.addoption(
        "--ocp-image",
        help="OCP image to upgrade to. Images can be found under "
        "https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com/",
    )
    # EUS Upgrade options
    install_upgrade_group.addoption(
        "--eus-ocp-images",
        help="Comma-separated OCP images to use for EUS-to-EUS upgrade.",
    )
    install_upgrade_group.addoption("--eus-cnv-target-version", help="target CNV version for eus upgrade")
    install_upgrade_group.addoption(
        "--upgrade-skip-default-sc-setup",
        help="Skip the fixture that changes the default sc in upgrade lane",
        action="store_true",
    )
    # CNV install options:
    install_upgrade_group.addoption(
        "--install",
        help="Runs cnv install tests",
        action="store_true",
    )
    # Matrix addoption
    matrix_group.addoption("--storage-class-matrix", help="Storage class matrix to use")
    matrix_group.addoption("--bridge-device-matrix", help="Bridge device matrix to use")
    matrix_group.addoption("--rhel-os-matrix", help="RHEL OS matrix to use")
    matrix_group.addoption("--windows-os-matrix", help="Windows OS matrix to use")
    matrix_group.addoption("--fedora-os-matrix", help="Fedora OS matrix to use")
    matrix_group.addoption("--centos-os-matrix", help="CentOS matrix to use")
    matrix_group.addoption("--provider-matrix", help="External provider matrix to use")
    matrix_group.addoption("--vm-volumes-matrix", help="VM volumes matrix to use")
    matrix_group.addoption("--run-strategy-matrix", help="RunStrategy matrix to use")
    matrix_group.addoption(
        "--sysprep-source-matrix",
        help="Sysprep resource types to use (ConfigMap, Secret)",
    )

    # OS addoption
    os_group.addoption(
        "--latest-rhel",
        action="store_true",
        help="Run matrix tests with latest RHEL OS",
    )
    os_group.addoption(
        "--latest-fedora",
        action="store_true",
        help="Run matrix tests with latest Fedora OS",
    )
    os_group.addoption(
        "--latest-windows",
        action="store_true",
        help="Run matrix tests with latest Windows OS",
    )
    os_group.addoption(
        "--latest-centos",
        action="store_true",
        help="Run matrix tests with latest CentOS",
    )

    # Storage addoption
    storage_group.addoption(
        "--default-storage-class",
        help="Overwrite default storage class in storage_class_matrix",
    )

    # Cluster sanity addoption
    cluster_sanity_group.addoption(
        "--cluster-sanity-skip-storage-check",
        help="Skip storage class check in cluster_sanity fixture",
        action="store_true",
    )
    cluster_sanity_group.addoption(
        "--cluster-sanity-skip-nodes-check",
        help="Skip nodes check in cluster_sanity fixture",
        action="store_true",
    )
    cluster_sanity_group.addoption(
        "--cluster-sanity-skip-check",
        help="Skip cluster_sanity check",
        action="store_true",
    )
    # Log collector group
    data_collector_group.addoption(
        "--data-collector",
        help="If must-gather/alert data should be collected on failure.",
        action="store_true",
    )
    data_collector_group.addoption(
        "--pytest-log-file",
        help="Path to pytest log file",
        default="pytest-tests.log",
    )

    # Deprecate api test_group
    deprecate_api_test_group.addoption(
        "--skip-deprecated-api-test",
        help="By default test_deprecation_audit_logs will always run, pass this flag to skip it",
        action="store_true",
    )

    # LeftoversCollector group
    leftovers_collector.addoption(
        "--leftovers-collector",
        help="By default will not run, to run pass --leftovers-collector.",
        action="store_true",
    )

    # Scale group
    scale_group.addoption(
        "--scale-params-file",
        help="Path to scale test params file, default is tests/scale/scale_params.yaml",
        default="tests/scale/scale_params.yaml",
    )

    # Session group
    session_group.addoption(
        "--session-id",
        help="Session id to use for the test run.",
        default=shortuuid.uuid(),
    )
    # TODO: Remove this option, once tests are marked explicitly with artifactory and bitwarden markers
    session_group.addoption(
        "--skip-artifactory-check",
        action="store_true",
        default=False,
        help="Skip artifactory environment variable checks. To be used for tests that does not need articatory access",
    )


def pytest_cmdline_main(config):
    # TODO: Reduce cognitive complexity
    # Make pytest tmp dir unique for current session
    config.option.basetemp = f"{config.option.basetemp}-{config.option.session_id}"

    upgrade_option = config.getoption("upgrade")
    if upgrade_option == "ocp" and not config.getoption("ocp_image"):
        raise ValueError("Running with --upgrade ocp: Missing --ocp-image")

    if upgrade_option == "cnv":
        if not config.getoption("cnv_version"):
            raise ValueError("Missing --cnv-version")
        if not config.getoption("cnv_image"):
            if config.getoption("cnv_source") != "production":
                raise ValueError("Missing --cnv-image")

    if upgrade_option == "eus":
        eus_ocp_images = config.getoption("eus_ocp_images")
        if not (eus_ocp_images and len(eus_ocp_images.split(",")) == 2):
            raise ValueError(
                f"Two OCP images are needed to perform EUS-to-EUS upgrade with --eus-ocp-images."
                f" Provided images: {eus_ocp_images}"
            )

    # Default value is set as this value is used to set test name in
    # tests.upgrade_params.UPGRADE_TEST_DEPENDENCY_NODE_ID which is needed for pytest dependency marker
    py_config["upgraded_product"] = upgrade_option or config.getoption("--upgrade_custom") or "cnv"
    py_config["cnv_source"] = config.getoption("--cnv-source")

    # [rhel|fedora|windows|centos]-os-matrix and latest-[rhel|fedora|windows|centos] are mutually exclusive
    rhel_os_violation = config.getoption("rhel_os_matrix") and config.getoption("latest_rhel")
    windows_os_violation = config.getoption("windows_os_matrix") and config.getoption("latest_windows")
    fedora_os_violation = config.getoption("fedora_os_matrix") and config.getoption("latest_fedora")
    centos_os_violation = config.getoption("centos_os_matrix") and config.getoption("latest_centos")
    if rhel_os_violation or windows_os_violation or fedora_os_violation or centos_os_violation:
        raise ValueError("os matrix and latest os options are mutually exclusive.")

    if upgrade_option == "cnv" and config.getoption("cnv_source") and not config.getoption("cnv_version"):
        raise ValueError("Running with --cnv-source: Missing --cnv-version")


def add_polarion_parameters_to_user_properties(item: Item, matrix_name: str) -> None:
    values = re.findall("(#.*?#)", item.name)  # Extract all substrings enclosed in '#' from item.name
    for value in values:
        value = value.strip("#")
        for param in py_config[matrix_name]:
            if isinstance(param, dict):
                param = [*param][0]

            if value == param:
                item.user_properties.append((f"polarion-parameter-{matrix_name}", value))


def add_test_id_markers(item: Item, marker_name: str) -> None:
    for marker in item.iter_markers(name=marker_name):
        test_id = marker.args[0]
        if marker_name == "polarion":
            marker_name = f"{marker_name}-testcase-id"
        item.user_properties.append((marker_name, test_id))


def add_tier2_marker(item: Item) -> None:
    markers = [mark.name for mark in list(item.iter_markers())]
    if not [mark for mark in markers if mark in EXCLUDE_MARKER_FROM_TIER2_MARKER]:
        item.add_marker(marker="tier2")


def mark_tests_by_team(item: Item) -> None:
    for team, vals in TEAM_MARKERS.items():
        if item.location[0].split("/")[1] in vals:
            item.add_marker(marker=team)


def filter_upgrade_tests(
    items: list[Item],
    config: Config,
    upgrade_markers: list[str],
) -> tuple[list[Item], list[Item]]:
    upgrade_tests, non_upgrade_tests = [], []

    for item in items:
        if set(upgrade_markers).intersection(set(item.keywords)):
            upgrade_tests.append(item)
        else:
            non_upgrade_tests.append(item)

    if any(config.getoption(f"--{marker}") for marker in upgrade_markers):
        # If performing OCP upgrade, remove tests marked with pytest.mark.cnv_upgrade.
        # If performing CNV upgrade, remove test marked with pytest.mark.ocp_upgrade,
        # and determine if we are running the cnv upgrade test for production source or for stage/osbs.
        cnv_source = config.getoption("--cnv-source")

        upgrade_tests, discard = remove_upgrade_tests_based_on_config(
            cnv_source=cnv_source,
            upgrade_tests=upgrade_tests,
        )
        return upgrade_tests, [*non_upgrade_tests, *discard]

    return non_upgrade_tests, upgrade_tests


def remove_upgrade_tests_based_on_config(
    cnv_source: str,
    upgrade_tests: list[Item],
) -> tuple[list[Item], list[Item]]:
    """
    Filter the correct upgrade tests to execute based on config, since only one lane can be chosen.

    Args:
        cnv_source(str): cnv source option.
        upgrade_tests(list): list of upgrade tests.
    """
    ocp_upgrade_test = None
    cnv_upgrade_test_with_prod_src = None
    cnv_upgrade_test_no_prod_src = None
    eus_upgrade_test = None
    cnv_upgrade_tests: list[Item] = []

    for test in upgrade_tests:
        if "ocp_upgrade" in test.keywords:
            ocp_upgrade_test = test
        elif "eus_upgrade" in test.keywords:
            eus_upgrade_test = test
        elif "cnv_upgrade" in test.keywords:
            cnv_upgrade_tests.append(test)
            if "production_source" in test.name:
                cnv_upgrade_test_with_prod_src = test
            else:
                cnv_upgrade_test_no_prod_src = test

    if py_config["upgraded_product"] == "cnv":
        tests_to_remove = [
            cnv_upgrade_test_no_prod_src if cnv_source == "production" else cnv_upgrade_test_with_prod_src,
            ocp_upgrade_test,
            eus_upgrade_test,
        ]
    elif py_config["upgraded_product"] == "ocp":
        tests_to_remove = [*cnv_upgrade_tests, eus_upgrade_test]
    else:
        tests_to_remove = [*cnv_upgrade_tests, ocp_upgrade_test]

    discard = [test for test in tests_to_remove if test is not None]
    keep = [test for test in upgrade_tests if test not in discard]
    return keep, discard


def filter_deprecated_api_tests(items: list[Item], config: Config) -> list[Item]:
    # filter out deprecated api tests, if explicitly asked or if running upgrade/install tests
    if (
        config.getoption("--skip-deprecated-api-test")
        or config.getoption("--install")
        or config.getoption("--upgrade")
        or config.getoption("--upgrade_custom")
    ):
        discard_tests, items_to_return = remove_tests_from_list(items=items, filter_str="deprecated_api")
        config.hook.pytest_deselected(items=discard_tests)
        return items_to_return
    return items


def filter_sno_only_tests(items: list[Item], config: Config) -> list[Item]:
    if config.getoption("-m") and "sno" not in config.getoption("-m"):
        discard_tests, items_to_return = remove_tests_from_list(items=items, filter_str="single_node_tests")
        config.hook.pytest_deselected(items=discard_tests)
        return items_to_return
    return items


def remove_tests_from_list(items: list[Item], filter_str: str) -> tuple[list[Item], list[Item]]:
    discard_tests: list[Item] = []
    items_to_return: list[Item] = []
    for item in items:
        if filter_str in item.keywords:
            discard_tests.append(item)
        else:
            items_to_return.append(item)
    return discard_tests, items_to_return


def pytest_configure(config):
    # test_deprecation_audit_logs should always run regardless the path that passed to pytest.
    deprecation_tests_dir_path = "tests/deprecated_api"
    file_or_dir = config.option.file_or_dir
    if file_or_dir and deprecation_tests_dir_path not in file_or_dir and file_or_dir != ["tests"]:
        config.option.file_or_dir.append(deprecation_tests_dir_path)


def pytest_collection_modifyitems(session, config, items):
    """
    Pytest builtin function.
    Modify the test items during pytest collection to include necessary test metadata.

    This function performs the following actions:
    1. Adds Polarion parameters to user properties.
    2. Adds test ID markers for Polarion and Jira.
    3. Adds the tier2 marker for tests without an exclusion marker.
    4. Marks tests by team.
    5. Filters upgrade tests based on the --upgrade option.

    Args:
        session (pytest.Session): The pytest session object.
        config (pytest.Config): The pytest configuration object.
        items (list): A list of pytest.Item objects representing the tests.
    """
    scope_match = re.compile(r"__(module|class|function)__$")
    for item in items:
        for fixture_name in [fixture_name for fixture_name in item.fixturenames if "_matrix" in fixture_name]:
            _matrix_name = scope_match.sub("", fixture_name)
            # In case we got dynamic matrix (see get_matrix_params() in infra.py)
            matrix_name = get_base_matrix_name(matrix_name=_matrix_name)

            if _matrix_name != matrix_name:
                matrix_params = get_matrix_params(pytest_config=config, matrix_name=_matrix_name)
                if not matrix_params:
                    skip = pytest.mark.skip(reason=f"Dynamic matrix {_matrix_name} returned empty list")
                    item.add_marker(marker=skip)

            add_polarion_parameters_to_user_properties(item=item, matrix_name=matrix_name)

        add_test_id_markers(item=item, marker_name="polarion")
        add_test_id_markers(item=item, marker_name="jira")

        # Add tier2 marker for tests without an exclusion marker.
        add_tier2_marker(item=item)

        mark_tests_by_team(item=item)
    #  Collect only 'upgrade_custom' tests when running pytest with --upgrade_custom
    if config.getoption("--upgrade_custom"):
        keep, discard = filter_upgrade_tests(items=items, config=config, upgrade_markers=["upgrade_custom"])
    #  Collect only 'upgrade' tests when running pytest with --upgrade
    elif config.getoption("--upgrade"):
        keep, discard = filter_upgrade_tests(items=items, config=config, upgrade_markers=["upgrade"])
    #  For non-upgrade tests we should exclude both markers: 'upgrade' and 'upgrade_custom'
    else:
        keep, discard = filter_upgrade_tests(items=items, config=config, upgrade_markers=["upgrade", "upgrade_custom"])

    items[:] = keep
    if discard:
        config.hook.pytest_deselected(items=discard)
    items[:] = filter_deprecated_api_tests(items=items, config=config)
    items[:] = filter_sno_only_tests(items=items, config=config)


def pytest_report_teststatus(report, config):
    test_name = report.head_line
    when = report.when
    call_str = "call"
    if report.passed:
        if when == call_str:
            BASIC_LOGGER.info(f"\nTEST: {test_name} STATUS: \033[0;32mPASSED\033[0m")

    elif report.skipped:
        BASIC_LOGGER.info(f"\nTEST: {test_name} STATUS: \033[1;33mSKIPPED\033[0m")

    elif report.failed:
        if when != call_str:
            BASIC_LOGGER.info(f"\nTEST: {test_name} [{when}] STATUS: \033[0;31mERROR\033[0m")
        else:
            BASIC_LOGGER.info(f"\nTEST: {test_name} STATUS: \033[0;31mFAILED\033[0m")


def pytest_runtest_makereport(item, call):
    """
    incremental tests implementation
    """
    if call.excinfo is not None and "incremental" in item.keywords:
        parent = item.parent
        parent._previousfailed = item


def pytest_fixture_setup(fixturedef, request):
    LOGGER.info(f"Executing {fixturedef.scope} fixture: {fixturedef.argname}")


def pytest_runtest_setup(item):
    """
    Use incremental
    """
    # set the data collector directory irrespective of --data-collector. This is to enable collecting pexcpect logs
    set_data_collector_directory(item=item, directory_path=get_data_collector_dir())
    if item.config.getoption("--data-collector"):
        # before the setup work starts, insert current epoch time into the database
        try:
            db = Database()
            db.insert_test_start_time(
                test_name=f"{item.fspath}::{item.name}",
                start_time=int(datetime.datetime.now().strftime("%s")),
            )
        except Exception as db_exception:
            LOGGER.error(f"Database error: {db_exception}. Must-gather collection may not be accurate")
    BASIC_LOGGER.info(f"\n{separator(symbol_='-', val=item.name)}")
    BASIC_LOGGER.info(f"{separator(symbol_='-', val='SETUP')}")
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed (%s)" % previousfailed.name)


def pytest_runtest_call(item):
    BASIC_LOGGER.info(f"{separator(symbol_='-', val='CALL')}")


def pytest_runtest_teardown(item):
    BASIC_LOGGER.info(f"{separator(symbol_='-', val='TEARDOWN')}")
    # reset data collector after each tests
    py_config["data_collector"]["collector_directory"] = py_config["data_collector"]["data_collector_base_directory"]


def pytest_generate_tests(metafunc):
    scope_match = re.compile(r"__(module|class|function)__$")
    for fixture_name in [fname for fname in metafunc.fixturenames if "_matrix" in fname]:
        scope = scope_match.findall(fixture_name)
        if not scope:
            raise ValueError(f"{fixture_name} is missing scope (__<scope>__)")

        matrix_name = scope_match.sub("", fixture_name)
        matrix_params = get_matrix_params(pytest_config=metafunc.config, matrix_name=matrix_name)
        ids = []
        for matrix_param in matrix_params:
            if isinstance(matrix_param, dict):
                ids.append(f"#{[*matrix_param][0]}#")
            else:
                ids.append(f"#{matrix_param}#")

        if matrix_params:
            metafunc.parametrize(
                fixture_name,
                matrix_params,
                ids=ids,
                scope=scope[0],
            )

    reorder_early_fixtures(metafunc=metafunc)


def pytest_sessionstart(session):
    # TODO: Reduce cognitive complexity
    def _update_os_related_config():
        # Save the default windows_os_matrix before it is updated
        # with runtime windows_os_matrix value(s).
        # Some tests extract a single OS from the matrix and may fail if running with
        # passed values from cli
        py_config["system_windows_os_matrix"] = py_config["windows_os_matrix"]
        py_config["system_rhel_os_matrix"] = py_config["rhel_os_matrix"]

        # Update OS matrix list with the latest OS if running with os_group
        if session.config.getoption("latest_rhel"):
            py_config["rhel_os_matrix"] = [utilities.infra.generate_latest_os_dict(os_list=py_config["rhel_os_matrix"])]
        if session.config.getoption("latest_windows"):
            py_config["windows_os_matrix"] = [
                utilities.infra.generate_latest_os_dict(os_list=py_config["windows_os_matrix"])
            ]
        if session.config.getoption("latest_centos"):
            py_config["centos_os_matrix"] = [
                utilities.infra.generate_latest_os_dict(os_list=py_config["centos_os_matrix"])
            ]
        if session.config.getoption("latest_fedora"):
            py_config["fedora_os_matrix"] = [
                utilities.infra.generate_latest_os_dict(os_list=py_config["fedora_os_matrix"])
            ]

    data_collector_dict = set_data_collector_values()
    shutil.rmtree(
        data_collector_dict["data_collector_base_directory"],
        ignore_errors=True,
    )

    tests_log_file = session.config.getoption("pytest_log_file")
    if os.path.exists(tests_log_file):
        pathlib.Path(tests_log_file).unlink()

    session.config.option.log_listener = setup_logging(
        log_file=tests_log_file,
        log_level=session.config.getoption("log_cli_level") or logging.INFO,
    )
    # Add HPP-CSI-BASIC/HPP-CSI-PVC-BLOCK to global config's storage_class_matrix, only
    # if command line option --storage-class-matrix includes them:
    py_config_scs = update_storage_class_matrix_config(
        session=session, pytest_config_matrix=py_config.get("storage_class_matrix", [])
    )

    # Save the default storage_class_matrix before it is updated
    # with runtime storage_class_matrix value(s)
    py_config["system_storage_class_matrix"] = py_config_scs

    _update_os_related_config()

    matrix_addoptions = [matrix for matrix in session.config.invocation_params.args if "-matrix=" in matrix]
    for matrix_addoption in matrix_addoptions:
        items_list = []
        key, vals = matrix_addoption.split("=")
        key = key.strip("--").replace("-", "_")
        vals = vals.split(",")

        for val in vals:
            for item in py_config[key]:
                # Extract only the dicts item which has the requested key from
                if isinstance(item, dict) and [*item][0] == val:
                    items_list.append(item)

                # Extract only the items item which has the requested key from
                if isinstance(item, str) and item == val:
                    items_list.append(item)

        py_config[key] = items_list
    config_default_storage_class(session=session)
    # Set py_config["servers"] and py_config["os_login_param"]
    # Send --tc=server_url:<url> to override servers URL
    if not skip_if_pytest_flags_exists(pytest_config=session.config):
        py_config["version_explorer_url"] = get_cnv_version_explorer_url(pytest_config=session.config)
        if not session.config.getoption("--skip-artifactory-check"):
            py_config["server_url"] = py_config["server_url"] or get_artifactory_server_url(
                cluster_host_url=get_client().configuration.host
            )
            py_config["servers"] = {
                name: _server.format(server=py_config["server_url"]) for name, _server in py_config["servers"].items()
            }
            py_config["os_login_param"] = get_cnv_tests_secret_by_name(secret_name="os_login")

    # must be at the end to make sure we create it only after all pytest_sessionstart checks pass.
    if not skip_if_pytest_flags_exists(pytest_config=session.config):
        stop_if_run_in_progress()
        deploy_run_in_progress_namespace()
        deploy_run_in_progress_config_map(session=session)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(path=session.config.option.basetemp, ignore_errors=True)
    if not skip_if_pytest_flags_exists(pytest_config=session.config):
        run_in_progress_config_map().clean_up()
        deploy_run_in_progress_namespace().clean_up()

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    reporter.summary_stats()
    if session.config.getoption("--data-collector"):
        db = Database()
        file_path = db.database_file_path
        LOGGER.info(f"Removing database file path {file_path}")
        os.remove(file_path)
    # clean up the empty folders
    collector_directory = py_config["data_collector"]["data_collector_base_directory"]
    if os.path.exists(collector_directory):
        for root, dirs, files in os.walk(collector_directory, topdown=False):
            for _dir in dirs:
                dir_path = os.path.join(root, _dir)
                if not os.listdir(dir_path):
                    shutil.rmtree(dir_path, ignore_errors=True)
    session.config.option.log_listener.stop()


def get_all_node_markers(node: Node) -> list[str]:
    return [mark.name for mark in list(node.iter_markers())]


def is_skip_must_gather(node: Node) -> bool:
    return "skip_must_gather_collection" in get_all_node_markers(node=node)


def get_inspect_command_namespace_string(node: Node, test_name: str) -> str:
    namespace_str = ""
    components = [key for key in NAMESPACE_COLLECTION.keys() if f"tests/{key}/" in test_name]
    if not components:
        LOGGER.warning(f"{test_name} does not require special data collection on failure")
    else:
        component = components[0]
        namespaces_to_collect: list[str] = NAMESPACE_COLLECTION[component]
        if component == "virt":
            all_markers = get_all_node_markers(node=node)
            if "gpu" in all_markers:
                namespaces_to_collect.append(NamespacesNames.NVIDIA_GPU_OPERATOR)
            if "swap" in all_markers:
                namespaces_to_collect.append(NamespacesNames.WASP)
        namespace_str = " ".join([f"namespace/{namespace}" for namespace in namespaces_to_collect])
    return namespace_str


def pytest_exception_interact(node: Item | Collector, call: CallInfo[Any], report: TestReport | CollectReport) -> None:
    BASIC_LOGGER.error(report.longreprtext)
    if node.config.getoption("--data-collector") and not is_skip_must_gather(node=node):
        test_name = f"{node.fspath}::{node.name}"
        LOGGER.info(f"Must-gather collection is enabled for {test_name}.")
        inspect_str = get_inspect_command_namespace_string(test_name=test_name, node=node)
        if call.excinfo and any([
            isinstance(call.excinfo.value, exception_type) for exception_type in MUST_GATHER_IGNORE_EXCEPTION_LIST
        ]):
            LOGGER.warning(f"Must-gather collection would be skipped for exception: {call.excinfo.type}")
        else:
            try:
                db = Database()
                test_start_time = db.get_test_start_time(test_name=test_name)
            except Exception as db_exception:
                test_start_time = 0
                LOGGER.warning(f"Error: {db_exception} in accessing database.")
            if not test_start_time:
                since_time = TIMEOUT_5MIN
                LOGGER.warning(
                    f"Could not get start time of test: {test_name}. Collecting must-gather for {since_time}s"
                )
            else:
                # if the test duration is 0 seconds, collect must-gather for past 60 seconds
                since_time = (int(datetime.datetime.now().strftime("%s")) - test_start_time) or TIMEOUT_1MIN
            try:
                collection_dir = os.path.join(get_data_collector_dir(), "pytest_exception_interact")
                collect_default_cnv_must_gather_with_vm_gather(since_time=since_time, target_dir=collection_dir)
                if inspect_str:
                    target_dir = os.path.join(collection_dir, "inspect_collection")
                    inspect_command = (
                        f"{INSPECT_BASE_COMMAND} {inspect_str} --since={since_time}s --dest-dir={target_dir}"
                    )
                    LOGGER.info(f"running inspect command on {inspect_command}")
                    run_command(
                        command=shlex.split(inspect_command),
                        check=False,
                        verify_stderr=False,
                    )
            except Exception as current_exception:
                LOGGER.warning(f"Failed to collect logs: {test_name}: {current_exception} {traceback.format_exc()}")
