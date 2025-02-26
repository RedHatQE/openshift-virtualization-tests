import getpass
import importlib
import logging
import os
import re
import shutil
import socket
import sys

from ocp_resources.config_map import ConfigMap
from ocp_resources.namespace import Namespace
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import config as py_config

from utilities.bitwarden import get_cnv_tests_secret_by_name
from utilities.constants import (
    CNV_TEST_RUN_IN_PROGRESS,
    CNV_TEST_RUN_IN_PROGRESS_NS,
    CNV_TESTS_CONTAINER,
    HPP_VOLUME_MODE_ACCESS_MODE,
    POD_SECURITY_NAMESPACE_LABELS,
    TIMEOUT_2MIN,
    StorageClassNames,
)
from utilities.exceptions import MissingEnvironmentVariableError
from utilities.infra import exit_pytest_execution
from utilities.storage import HOSTPATH_CSI, HppCsiStorageClass

HPP_STORAGE_CLASSES = {
    HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC: HPP_VOLUME_MODE_ACCESS_MODE,
    HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK: HPP_VOLUME_MODE_ACCESS_MODE,
}

LOGGER = logging.getLogger(__name__)


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

    _matrix_params = py_config.get(matrix_name)
    # If matrix is not in py_config, check if it is a function in utilities.pytest_matrix_utils
    if not _matrix_params:
        _matrix_func_name = matrix_name.split(base_matrix_name)[-1].replace("_", "", 1)
        _base_matrix_params = py_config.get(base_matrix_name)
        if not _base_matrix_params:
            raise ValueError(missing_matrix_error)

        # When running --collect-only or --setup-plan we cannot execute functions from pytest_matrix_utils
        if skip_if_pytest_flags_exists(pytest_config=pytest_config):
            _matrix_params = _base_matrix_params

        else:
            module_name = "utilities.pytest_matrix_utils"
            if module_name not in sys.modules:
                sys.modules[module_name] = importlib.import_module(name=module_name)

            pytest_matrix_utils = sys.modules[module_name]
            matrix_func = getattr(pytest_matrix_utils, _matrix_func_name)
            return matrix_func(matrix=_base_matrix_params)

    if not _matrix_params:
        raise ValueError(missing_matrix_error)

    return _matrix_params if isinstance(_matrix_params, list) else [_matrix_params]


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
    updated_default_sc = None
    if cmd_default_storage_class:
        updated_default_sc = cmd_default_storage_class
    elif cmdline_storage_class_matrix:
        cmdline_storage_class_matrix = cmdline_storage_class_matrix.split(",")
        updated_default_sc = (
            global_config_default_sc
            if global_config_default_sc in cmdline_storage_class_matrix
            else cmdline_storage_class_matrix[0]
        )

    # Update only if the requested default sc is not the same as set in global_config
    if updated_default_sc and updated_default_sc != global_config_default_sc:
        py_config["default_storage_class"] = updated_default_sc
        default_storage_class_configuration = [
            sc_dict
            for sc in py_config["storage_class_matrix"]
            for sc_name, sc_dict in sc.items()
            if sc_name == updated_default_sc
        ][0]

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
    Put fixtures with `pytest.mark.early` first during execution

    This allows patch of configurations before the application is initialized

    Due to the way pytest collects fixtures, marks must be placed below
    @pytest.fixture — which is to say, they must be applied BEFORE @pytest.fixture.
    """
    for fixturedef in metafunc._arg2fixturedefs.values():
        fixturedef = fixturedef[0]
        for mark in getattr(fixturedef.func, "pytestmark", []):
            if mark.name == "early":
                mark_order = mark.kwargs.get("order", 0)
                order = metafunc.fixturenames
                order.insert(mark_order, order.pop(order.index(fixturedef.argname)))
                break


def stop_if_run_in_progress():
    run_in_progress = run_in_progress_config_map()
    if run_in_progress.exists:
        exit_pytest_execution(
            message=f"openshift-virtualization-tests run already in progress: \n{run_in_progress.instance.data}"
            f"\nAfter verifying no one else is performing tests against the cluster, run:"
            f"\n'oc delete configmap -n {run_in_progress.namespace} {run_in_progress.name}'",
            return_code=100,
        )


def deploy_run_in_progress_namespace():
    run_in_progress_namespace = Namespace(name=CNV_TEST_RUN_IN_PROGRESS_NS)
    if not run_in_progress_namespace.exists:
        run_in_progress_namespace.deploy(wait=True)
        run_in_progress_namespace.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_2MIN)
        ResourceEditor({run_in_progress_namespace: {"metadata": {"labels": POD_SECURITY_NAMESPACE_LABELS}}}).update()
    return run_in_progress_namespace


def deploy_run_in_progress_config_map(session):
    run_in_progress_config_map(session=session).deploy()


def run_in_progress_config_map(session=None):
    return ConfigMap(
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
    return pytest_config.getoption("--collect-only") or pytest_config.getoption("--setup-plan")


def get_artifactory_server_url(cluster_host_url):
    LOGGER.info(f"Getting artifactory server information using cluster host url: {cluster_host_url}")
    artifactory_server = os.environ.get("ARTIFACTORY_SERVER")
    if artifactory_server:
        LOGGER.warning(f"Using user requested ARTIFACTORY_SERVER environment variable: {artifactory_server}")
        return artifactory_server
    else:
        servers = get_cnv_tests_secret_by_name(secret_name="artifactory_servers")
        matching_server = [servers[domain_key] for domain_key in servers if domain_key in cluster_host_url]
        if matching_server:
            artifactory_server = matching_server[0]
        else:
            artifactory_server = get_cnv_tests_secret_by_name(secret_name="default_artifactory_server")["server"]
    LOGGER.info(f"Using artifactory server: {artifactory_server}")
    return artifactory_server


def get_cnv_version_explorer_url(pytest_config):
    if pytest_config.getoption("install") or pytest_config.getoption("upgrade") == "eus":
        LOGGER.info("Checking for cnv version explorer url:")
        version_explorer_url = os.environ.get("CNV_VERSION_EXPLORER_URL")
        if not version_explorer_url:
            raise MissingEnvironmentVariableError("Please set CNV_VERSION_EXPLORER_URL environment variable")
        return version_explorer_url


def update_storage_class_matrix_config(session, pytest_config_matrix):
    cmdline_storage_class = session.config.getoption(name="storage_class_matrix")
    matrix_list = pytest_config_matrix
    matrix_names = [[*sc][0] for sc in pytest_config_matrix]
    invald_sc = []
    if cmdline_storage_class:
        cmdline_storage_class_matrix = cmdline_storage_class.split(",")
        if HOSTPATH_CSI in cmdline_storage_class and StorageClassNames.TOPOLVM in cmdline_storage_class:
            raise ValueError(
                f"{HOSTPATH_CSI} storage classes can't be used with {StorageClassNames.TOPOLVM} "
                f": {cmdline_storage_class}"
            )
        for sc in cmdline_storage_class_matrix:
            if sc not in matrix_names:
                if sc in HPP_STORAGE_CLASSES.keys():
                    matrix_list.append({sc: HPP_STORAGE_CLASSES[sc]})
                else:
                    invald_sc.append(sc)
    assert not invald_sc, (
        f"Invalid sc requested via --storage-class-matix: {invald_sc}. Valid options: "
        f"{matrix_names} and {[*HPP_STORAGE_CLASSES]}"
    )
    return matrix_list
