import getpass
import importlib
import json
import logging
import os
import re
import shutil
import socket
import sys
import tempfile
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import TypedDict

    class _FailureInfoDict(TypedDict):
        message: str
        log_message: str
        return_code: int


from xml.etree import ElementTree

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.config_map import ConfigMap
from ocp_resources.namespace import Namespace
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import config as py_config

from utilities.bitwarden import get_cnv_tests_secret_by_name
from utilities.constants import (
    CNV_TEST_RUN_IN_PROGRESS,
    CNV_TEST_RUN_IN_PROGRESS_NS,
    CNV_TESTS_CONTAINER,
    POD_SECURITY_NAMESPACE_LABELS,
    SANITY_TESTS_FAILURE,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
)
from utilities.data_collector import (
    collect_default_cnv_must_gather_with_vm_gather,
    get_data_collector_base_directory,
    write_to_file,
)
from utilities.exceptions import MissingEnvironmentVariableError

LOGGER = logging.getLogger(__name__)


_failure_info: _FailureInfoDict | None = None


def _inject_failure_junit(session: pytest.Session) -> None:
    """Inject a synthetic error testcase into JUnit XML for pytest exit failures.

    When exit_pytest_execution aborts the session, the exit reason may not appear
    in the JUnit XML report. CI systems can miss the failure — either because the
    report is empty (no tests ran) or because the exit reason is not captured as a
    testcase. This function re-opens the XML file after LogXML writes it and adds
    a synthetic error testcase to ensure the exit failure is always reported.

    Note:
        Must be called during pytest_sessionfinish, after LogXML has written the
        XML file. Pluggy calls hooks in LIFO (last-in-first-out) registration
        order: conftest is registered before the junitxml plugin, so the
        conftest hook runs after LogXML has written its output.

    Args:
        session: The pytest session object, used to access the junitxml file path.
    """
    if _failure_info is None:
        return

    xml_path = getattr(session.config.option, "xmlpath", None)
    if not xml_path or not os.path.exists(xml_path):
        LOGGER.info("No JUnit XML file found, skipping synthetic testcase injection")
        return

    return_code = _failure_info["return_code"]
    log_message = _failure_info["log_message"]

    sanitized_name = re.sub(r"[^a-z0-9_]", "", _failure_info["message"].lower().replace(" ", "_"))
    sanitized_name = re.sub(r"_+", "_", sanitized_name).strip("_")[:80]
    name = sanitized_name or "execution_failure"

    tree = ElementTree.parse(xml_path)
    root = tree.getroot()

    testsuite = root.find("testsuite")
    if testsuite is None:
        LOGGER.warning("No <testsuite> element found in JUnit XML, skipping injection")
        return

    testcase = ElementTree.SubElement(
        testsuite,
        "testcase",
        attrib={"classname": "pytest_exit", "name": name, "time": "0.000"},
    )
    error_node = ElementTree.SubElement(
        testcase,
        "error",
        attrib={"message": f"Pytest execution failed (exit code: {return_code})"},
    )
    # Strip XML 1.0 illegal control characters — ElementTree passes them through, corrupting the file.
    error_node.text = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]", "\ufffd", log_message)

    current_errors = int(testsuite.get("errors", "0"))
    testsuite.set("errors", str(current_errors + 1))
    current_tests = int(testsuite.get("tests", "0"))
    testsuite.set("tests", str(current_tests + 1))

    xml_dir = os.path.dirname(os.path.abspath(xml_path))
    fd, tmp_path = tempfile.mkstemp(dir=xml_dir, suffix=".xml")
    try:
        with os.fdopen(fd, mode="w") as tmp_file:
            tree.write(tmp_file, encoding="unicode", xml_declaration=True)
        os.replace(tmp_path, xml_path)
    except BaseException:
        os.unlink(tmp_path)
        raise

    LOGGER.info(f"Injected synthetic failure testcase into JUnit XML (exit code: {return_code})")


def get_base_matrix_name(matrix_name):
    match = re.match(r".*?(.*?_matrix)_(?:.*_matrix)+", matrix_name)
    if match:
        return match.group(1)

    return matrix_name


def get_matrix_params(pytest_config, matrix_name):
    """
    Customize matrix based on existing matrix
    Name should be <base_matrix><_extra_matrix>_<scope>
    base_matrix should exist in py_config.
    _extra_matrix should be a function in utilities.pytest_matrix_utils

    Args:
       pytest_config (_pytest.config.Config): pytest config
       matrix_name (str): matrix name

    Example:
       storage_class_matrix_snapshot_matrix__class__

       storage_class_matrix is in py_config
       snapshot_matrix is a function in utilities.pytest_matrix_utils
       all function in utilities.pytest_matrix_utils accept only matrix args.

    Returns:
         list: list of matrix params
    """
    missing_matrix_error = f"{matrix_name} is missing in config file"
    base_matrix_name = get_base_matrix_name(matrix_name=matrix_name)
    _skip_if_pytest_flags_exists = skip_if_pytest_flags_exists(pytest_config=pytest_config)

    _matrix_params = py_config.get(matrix_name)
    # If matrix is not in py_config, check if it is a function in utilities.pytest_matrix_utils
    if not _matrix_params:
        _matrix_func_name = matrix_name.split(base_matrix_name)[-1].replace("_", "", 1)
        _base_matrix_params = py_config.get(base_matrix_name)

        # Do not raise when running --collect-only or --setup-plan
        if not _base_matrix_params and not _skip_if_pytest_flags_exists:
            LOGGER.warning(missing_matrix_error)
            return []

        # When running --collect-only or --setup-plan we cannot execute functions from pytest_matrix_utils
        if _skip_if_pytest_flags_exists:
            _matrix_params = _base_matrix_params

        else:
            module_name = "utilities.pytest_matrix_utils"
            if module_name not in sys.modules:
                sys.modules[module_name] = importlib.import_module(name=module_name)

            pytest_matrix_utils = sys.modules[module_name]
            matrix_func = getattr(pytest_matrix_utils, _matrix_func_name, None)
            return matrix_func(matrix=_base_matrix_params)

    return _matrix_params if isinstance(_matrix_params, list) else [_matrix_params]


def _validate_storage_class_options(
    cmd_default_storage_class: str | None = None,
    cmdline_storage_class_matrix: list[str] | None = None,
) -> None:
    """Validates that storage class CLI options reference existing storage classes.

    Args:
        cmd_default_storage_class: Value from --default-storage-class CLI option.
        cmdline_storage_class_matrix: Parsed values from --storage-class-matrix CLI option.

    Raises:
        ValueError: If any storage class name is not found in py_config["system_storage_class_matrix"].
    """
    available_sc_names = [sc_name for sc in py_config["system_storage_class_matrix"] for sc_name in sc]

    if cmdline_storage_class_matrix:
        # Verify storage classes passed via --storage-class-matrix are supported
        if invalid_sc_names := set(cmdline_storage_class_matrix) - set(available_sc_names):
            raise ValueError(
                f"Storage class(es) {sorted(invalid_sc_names)} from --storage-class-matrix not found. "
                f"Available storage classes: {available_sc_names}"
            )

        # Verify default storage class passed via --default-storage-class exists in --storage-class-matrix
        if cmd_default_storage_class and cmd_default_storage_class not in cmdline_storage_class_matrix:
            raise ValueError(
                f"Default storage class '{cmd_default_storage_class}' not in --storage-class-matrix. "
                f"Matrix storage classes: {cmdline_storage_class_matrix}"
            )

        return

    # Verify default storage class passed via --default-storage-class is supported (when matrix is not passed from cli)
    if cmd_default_storage_class and cmd_default_storage_class not in available_sc_names:
        raise ValueError(
            f"Default storage class '{cmd_default_storage_class}' not found in system storage class matrix. "
            f"Available storage classes: {available_sc_names}"
        )


def config_default_storage_class(session):
    # Default storage class selection order:
    # 1. --default-storage-class from command line
    # 2. --storage-class-matrix:
    #     * if default sc from global_config storage_class_matrix appears in the commandline, use this sc
    #     * if default sc from global_config storage_class_matrix does not appear in the commandline, use the first
    #       sc in --storage-class-matrix options
    # 3. global_config default_storage_class
    global_config_default_sc = py_config["default_storage_class"]
    cmd_default_storage_class = session.config.getoption(name="default_storage_class")
    cmdline_storage_class_matrix = session.config.getoption(name="storage_class_matrix")
    system_storage_class_matrix = py_config["system_storage_class_matrix"]

    parsed_cmdline_matrix = cmdline_storage_class_matrix.split(",") if cmdline_storage_class_matrix else None
    try:
        _validate_storage_class_options(
            cmd_default_storage_class=cmd_default_storage_class,
            cmdline_storage_class_matrix=parsed_cmdline_matrix,
        )
    except ValueError as error:
        error_message = str(error)
        target_location = os.path.join(get_data_collector_base_directory(), "utilities", "pytest_exit_errors")
        write_to_file(
            file_name="storage_class_validation_error",
            content=error_message,
            base_directory=target_location,
        )
        pytest.exit(reason=error_message, returncode=4)

    updated_default_sc = None
    if cmd_default_storage_class:
        updated_default_sc = cmd_default_storage_class
    elif parsed_cmdline_matrix:
        updated_default_sc = (
            global_config_default_sc if global_config_default_sc in parsed_cmdline_matrix else parsed_cmdline_matrix[0]
        )

    # Update only if the requested default sc is not the same as set in global_config
    if updated_default_sc and updated_default_sc != global_config_default_sc:
        py_config["default_storage_class"] = updated_default_sc
        matching_configurations = [
            sc_dict
            for sc in system_storage_class_matrix
            for sc_name, sc_dict in sc.items()
            if sc_name == updated_default_sc
        ]

        default_storage_class_configuration = matching_configurations[0]

        py_config["default_volume_mode"] = default_storage_class_configuration["volume_mode"]
        py_config["default_access_mode"] = default_storage_class_configuration["access_mode"]


def separator(symbol_, val=None):
    terminal_width = shutil.get_terminal_size(fallback=(120, 40))[0]
    if not val:
        return f"{symbol_ * terminal_width}"

    sepa = int((terminal_width - len(val) - 2) // 2)
    return f"{symbol_ * sepa} {val} {symbol_ * sepa}"


def reorder_early_fixtures(metafunc):
    """
    Reorders fixtures based on a predefined list of fixtures which must run first.

    Args:
        metafunc: pytest metafunc
    """
    use_early_fixture_names = ["autouse_fixtures"]

    for fixturedef in metafunc._arg2fixturedefs.values():
        name = fixturedef[0].argname
        if name in use_early_fixture_names:
            order = use_early_fixture_names.index(name)
            fixtures_list = metafunc.fixturenames
            fixtures_list.insert(order, fixtures_list.pop(fixtures_list.index(name)))
            break


def stop_if_run_in_progress(client: DynamicClient) -> None:
    run_in_progress = run_in_progress_config_map(client=client)
    if run_in_progress.exists:
        exit_pytest_execution(
            log_message=f"openshift-virtualization-tests run already in progress: \n{run_in_progress.instance.data}"
            f"\nAfter verifying no one else is performing tests against the cluster, run:"
            f"\n'oc delete configmap -n {run_in_progress.namespace} {run_in_progress.name}'",
            return_code=100,
            message="openshift-virtualization-tests run already in progress",
            filename="cnv_tests_run_in_progress_failure.txt",
            admin_client=client,
        )


def deploy_run_in_progress_namespace(client: DynamicClient) -> Namespace:
    run_in_progress_namespace = Namespace(client=client, name=CNV_TEST_RUN_IN_PROGRESS_NS)
    if not run_in_progress_namespace.exists:
        run_in_progress_namespace.deploy(wait=True)
        run_in_progress_namespace.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_2MIN)
        ResourceEditor({run_in_progress_namespace: {"metadata": {"labels": POD_SECURITY_NAMESPACE_LABELS}}}).update()
    return run_in_progress_namespace


def deploy_run_in_progress_config_map(client: DynamicClient, session) -> None:
    run_in_progress_config_map(client=client, session=session).deploy(wait=True)


def run_in_progress_config_map(client: DynamicClient, session=None) -> ConfigMap:
    return ConfigMap(
        client=client,
        name=CNV_TEST_RUN_IN_PROGRESS,
        namespace=CNV_TEST_RUN_IN_PROGRESS_NS,
        data=get_current_running_data(session=session) if session else None,
    )


def get_current_running_data(session):
    return {
        "user": getpass.getuser(),
        "host": socket.gethostname(),
        "running_from_dir": os.getcwd(),
        "pytest_cmd": ", ".join(session.config.invocation_params.args),
        "session-id": session.config.option.session_id,
        "run-in-container": os.environ.get(CNV_TESTS_CONTAINER, "No"),
    }


def skip_if_pytest_flags_exists(pytest_config):
    """
    In some cases we want to skip some operation when pytest got executed with some flags
    Used in dynamic fixtures and in check if run already in progress.

    Args:
        pytest_config (_pytest.config.Config): Pytest config object

    Returns:
        bool: True if skip is needed, otherwise False
    """
    return (
        pytest_config.getoption("--collect-only")
        or pytest_config.getoption("--collectonly")
        or pytest_config.getoption("--setup-plan")
        or pytest_config.getoption("--collect-tests-markers")
    )


def get_artifactory_server_url(cluster_host_url, session):
    LOGGER.info(f"Getting artifactory server information using cluster host url: {cluster_host_url}")
    if artifactory_server := os.environ.get("ARTIFACTORY_SERVER"):
        LOGGER.info(f"Using user requested `ARTIFACTORY_SERVER` environment variable: {artifactory_server}")
        return artifactory_server
    else:
        if session and session.config.getoption("--disabled-bitwarden"):
            raise MissingEnvironmentVariableError(
                "Bitwarden access is disabled (`--disabled-bitwarden`) and `ARTIFACTORY_SERVER` env var is not set. "
                "Please set `ARTIFACTORY_SERVER` or remove `--disabled-bitwarden`."
            )

        servers = get_cnv_tests_secret_by_name(secret_name="artifactory_servers", session=session)
        matching_server = [servers[domain_key] for domain_key in servers if domain_key in cluster_host_url]
        if matching_server:
            artifactory_server = matching_server[0]
        else:
            default_server_data = get_cnv_tests_secret_by_name(
                secret_name="default_artifactory_server", session=session
            )
            if not default_server_data or "server" not in default_server_data:
                raise MissingEnvironmentVariableError(
                    "Could not retrieve default artifactory server from Bitwarden. "
                    "Please set ARTIFACTORY_SERVER environment variable."
                )
            artifactory_server = default_server_data["server"]
    LOGGER.info(f"Using artifactory server: {artifactory_server}")
    return artifactory_server


def get_cnv_version_explorer_url(pytest_config):
    if pytest_config.getoption("install") or pytest_config.getoption("upgrade") in ("eus", "cnv"):
        LOGGER.info("Checking for cnv version explorer url:")
        version_explorer_url = os.environ.get("CNV_VERSION_EXPLORER_URL")
        if not version_explorer_url:
            raise MissingEnvironmentVariableError("Please set CNV_VERSION_EXPLORER_URL environment variable")
        return version_explorer_url


def get_tests_cluster_markers(items, filepath=None) -> None:
    test_markers = set([marker.name for item in items for marker in item.iter_markers()])

    pytest_cluster_markers = []
    is_config_section = False
    with open("pytest.ini") as fd:
        for line in fd:
            # Get markers from configuration and hardware sections only
            if "## Configuration requirements" in line or "## Hardware requirements" in line:
                is_config_section = True
                continue

            if is_config_section:
                # Skip empty lines and sections which are not configuration or hardware requirements
                if (_line := line.strip()) and _line.startswith("#") or line == "\n":
                    is_config_section = False
                    continue
                else:
                    pytest_cluster_markers.append(line.strip().split(":")[0])

    tests_cluster_markers = [marker for marker in test_markers if marker in pytest_cluster_markers]
    LOGGER.info(f"Cluster-related test markers: {tests_cluster_markers}")

    if filepath:
        LOGGER.info(f"Write cluster-related test markers in {filepath}")
        with open(filepath, "w") as fd:
            fd.write(json.dumps(tests_cluster_markers))


def exit_pytest_execution(
    admin_client,
    log_message,
    return_code=SANITY_TESTS_FAILURE,
    filename=None,
    junitxml_property=None,
    message=None,
):
    """Exit pytest execution

    Exit pytest execution; invokes pytest_sessionfinish.
    Optionally, log an error message to tests-collected-info/utilities/pytest_exit_errors/<filename>

    Args:
        log_message (str): Message to display upon exit and to log in errors file
        return_code (int. Default: 99): Exit return code
        filename (str, optional. Default: None): filename where the given message will be saved
        junitxml_property (pytest plugin): record_testsuite_property
        message (str): Message to log in an error file. If not provided, `log_message` will be used.
        admin_client (DynamicClient): cluster admin client

    Note:
        Records the failure details in a module-level store so that
        _inject_failure_junit can emit a synthetic JUnit XML testcase
        during pytest_sessionfinish.
    """
    target_location = os.path.join(get_data_collector_base_directory(), "utilities", "pytest_exit_errors")
    # collect must-gather for past 5 minutes:
    if return_code == SANITY_TESTS_FAILURE:
        try:
            collect_default_cnv_must_gather_with_vm_gather(
                since_time=TIMEOUT_5MIN, target_dir=target_location, admin_client=admin_client
            )
        except Exception as current_exception:
            LOGGER.warning(f"Failed to collect logs cnv must-gather after cluster_sanity failure: {current_exception}")

    if filename:
        write_to_file(
            file_name=filename,
            content=message or log_message,
            base_directory=target_location,
        )
    if junitxml_property:
        junitxml_property(name="exit_code", value=return_code)

    global _failure_info
    _failure_info = {
        "message": message or log_message,
        "log_message": log_message,
        "return_code": return_code,
    }

    pytest.exit(reason=log_message, returncode=return_code)
