import json
import logging
import os
import shlex
from functools import cache

from ocp_resources.namespace import Namespace
from ocp_resources.resource import get_client
from ocp_utilities.monitoring import Prometheus
from pytest_testconfig import config as py_config

import utilities.hco
import utilities.infra
from utilities.constants import TIMEOUT_20MIN
from utilities.must_gather import run_must_gather

LOGGER = logging.getLogger(__name__)
BASE_DIRECTORY_NAME = "tests-collected-info"


@cache
def get_data_collector_base(base_dir: str | None = None) -> str:
    """
    Returns base directory for data collection.

    Priority is set as follows:
        1. Dir is set by passing --data-collector-output-dir.
        2. A "/data" prefix when running in a CNV tests container
            (i.e., when `CNV_TESTS_CONTAINER` environment variable is set).
        3. The current working directory.

    Args:
        base_dir (str): base directory to use.

    Returns:
        str: base directory for data collection.
    """
    # TODO: move to pathlib when data collection logic is refactored

    if base_dir:
        base_path = base_dir

    elif os.environ.get("CNV_TESTS_CONTAINER"):
        base_path = "/data"

    else:
        base_path = os.getcwd()

    base_path = os.path.normpath(os.path.expanduser(base_path))
    if not base_path.endswith(os.sep):
        base_path = f"{base_path}{os.sep}"

    return base_path


def get_data_collector_base_directory() -> str:
    return py_config["data_collector"]["data_collector_base_directory"]


def set_data_collector_values(base_dir: str | None = None) -> str:
    py_config["data_collector"] = {
        "data_collector_base_directory": f"{get_data_collector_base(base_dir=base_dir)}tests-collected-info",
    }
    return py_config["data_collector"]


def set_data_collector_directory(item, directory_path):
    data_collector_dict = py_config["data_collector"]
    data_collector_dict["collector_directory"] = prepare_pytest_item_data_dir(item=item, output_dir=directory_path)


def get_data_collector_dir():
    data_collector_dict = py_config["data_collector"]
    return data_collector_dict.get(
        "collector_directory",
        data_collector_dict["data_collector_base_directory"],
    )


def write_to_file(file_name, content, base_directory, mode="w"):
    """
    Write to a file that will be available after the run execution.

    Args:
        file_name (str): name of the file to write, including full path.
        content (str): the content of the file to write.
        base_directory (str): the base directory to write the file
        mode (str, optional): specifies the mode in which the file is opened.
    """
    os.makedirs(base_directory, exist_ok=True)
    file_path = os.path.join(base_directory, file_name)

    try:
        with open(file_path, mode) as fd:
            fd.write(content)
    except Exception as exp:
        LOGGER.warning(f"Failed to write extras to file: {file_path} {exp}")


def collect_alerts_data():
    base_dir = get_data_collector_dir()
    LOGGER.warning(f"Collecting alert data under: {base_dir}")
    alerts = Prometheus(
        verify_ssl=False,
        bearer_token=utilities.infra.get_prometheus_k8s_token(duration="900s"),
    ).alerts()
    write_to_file(
        base_directory=base_dir,
        file_name="firing_alerts.json",
        content=json.dumps(alerts),
    )


def collect_vnc_screenshot_for_vms(vm_name: str, vm_namespace: str) -> None:
    base_dir = get_data_collector_base_directory()
    utilities.infra.run_virtctl_command(
        command=shlex.split(f"vnc screenshot {vm_name} -f {base_dir}/{vm_namespace}-{vm_name}.png"),
        namespace=vm_namespace,
    )


def collect_ocp_must_gather(since_time):
    base_directory = get_data_collector_dir()
    LOGGER.info(f"Collecting OCP must-gather data under: {base_directory}, for time {since_time} seconds.")
    run_must_gather(target_base_dir=base_directory, since=f"{since_time}s", timeout=f"{TIMEOUT_20MIN}s")


def collect_default_cnv_must_gather_with_vm_gather(since_time, target_dir):
    cnv_csv = utilities.hco.get_installed_hco_csv(
        admin_client=get_client(), hco_namespace=Namespace(name=py_config["hco_namespace"])
    )
    LOGGER.info(f"Collecting cnv-must gather using CSV: {cnv_csv.name}")
    must_gather_image = [
        image["image"] for image in cnv_csv.instance.spec.relatedImages if "must-gather" in image["name"]
    ][0]
    run_must_gather(
        image_url=must_gather_image,
        target_base_dir=target_dir,
        since=f"{since_time}s",
        script_name="/usr/bin/gather",
        flag_names="vms_details",
    )


def prepare_pytest_item_data_dir(item, output_dir):
    """
    Prepare output directory for pytest item

    "testpaths" must be configured in pytest.ini.

    Args:
        item (pytest item): test invocation item
        output_dir (str): output directory

    Example:
        item.fspath= "/home/user/git/tests-repo/tests/test_dir/test_something.py"
        data_collector base directory = "collected-info"
        item.name = "test1"
        item_dir_log = "collected-info/test_dir/test_something/test1"

    Returns:
        str: output dir full path
    """
    item_cls_name = item.cls.__name__ if item.cls else ""
    tests_path = item.session.config.inicfg.get("testpaths")
    assert tests_path, "pytest.ini must include testpaths"

    fspath_split_str = "/" if tests_path != os.path.split(item.fspath.dirname)[1] else ""
    item_dir_log = os.path.join(
        output_dir,
        item.fspath.dirname.split(f"/{tests_path}{fspath_split_str}")[-1],
        item.fspath.basename.partition(".py")[0],
        item_cls_name,
        item.name,
    )
    os.makedirs(item_dir_log, exist_ok=True)
    return item_dir_log
