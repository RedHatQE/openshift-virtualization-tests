import logging
import os
import shlex

from pyhelper_utils.shell import run_command

from utilities.constants import TIMEOUT_15MIN, TIMEOUT_20MIN

LOGGER = logging.getLogger(__name__)


def run_must_gather(
    image_url: str = "",
    target_base_dir: str = "",
    script_name: str = "",
    node_name: str = "",
    flag_names: str = "",
    timeout: str = f"{TIMEOUT_15MIN}s",
    command_timeout: int = TIMEOUT_20MIN,
    since: str | None = None,
) -> str:
    """
    Run must gather command with an option to create target directory.

    Args:
        image_url (str, optional): must-gather plugin image to run.
            If not specified, OpenShift's default must-gather image will be used.
        target_base_dir (str, optional): path to base directory
        script_name (str, optional): must-gather script name or path
        node_name (str, optional): node name to run the must gather pod on.
        flag_names (str, optional): comma separated list of must-gather flags
            Examples: "oc adm must-gather --image=quay.io/kubevirt/must-gather -- /usr/bin/gather --default"

            Note: flag is optional parameter for must-gather. When it is not passed "--default" flag is used by
            must-gather. However, flag_names can not be passed without script_name
        since (str, optional): since when the data should be collected. format is: '(+|-)[0-9]+(s|m|h|d)'
        timeout (str, optional): runs the debug pods for specified duration

    Returns:
        str: command output
    """
    base_command = "oc adm must-gather"
    if target_base_dir:
        base_command += f" --dest-dir={target_base_dir}"
    if image_url:
        base_command += f" --image={image_url}"
    if node_name:
        base_command += f" --node-name={node_name}"
    if since:
        base_command += f" --since={since}"
    if timeout:  # Only applies to gathering and not copying stage - https://issues.redhat.com/browse/OCPBUGS-64591
        base_command += f" --timeout={timeout}"
    if script_name:
        base_command += f" -- {script_name}"
    # flag_name must be the last argument
    if flag_names:
        flag_string = "".join([f" --{flag_name}" for flag_name in flag_names.split(",")])
        base_command += f" {flag_string}"
    did_succeed, output, error = run_command(
        command=shlex.split(base_command),
        check=False,
        timeout=command_timeout,
        log_errors=False,
    )
    if not did_succeed and error:
        log_func = LOGGER.warning if "Warning" in error else LOGGER.error
        log_func(f"must-gather raised the following error: {error}")
    return output


def get_must_gather_output_file(path):
    return f"{path}/../output.log"


def get_must_gather_output_dir(must_gather_path):
    for item in os.listdir(must_gather_path):
        new_path = os.path.join(must_gather_path, item)
        if os.path.isdir(new_path):
            return new_path
    raise FileNotFoundError(f"No log directory was created in '{must_gather_path}'")


def collect_must_gather(
    must_gather_tmpdir,
    must_gather_image_url,
    script_name="/usr/bin/gather",
    flag_names="",
    timeout="",
    node_name="",
    command_timeout=TIMEOUT_20MIN,
):
    """
    Run must gather command and puts the content in directory.

    Args:
        must_gather_tmpdir (str): tmp dir for must gather data
        must_gather_image_url (str): image url for must gather command
        script_name (str): must-gather script name or path
        flag_names (str, optional): comma separated list of must-gather flags
        timeout (str, optional): runs the debug pods for specified duration
        node_name (str, optional): node name to run the debug pods on.

    Returns:
        str: output directory with must gather content
    """
    output = run_must_gather(
        image_url=must_gather_image_url,
        target_base_dir=must_gather_tmpdir,
        script_name=script_name,
        node_name=node_name,
        flag_names=flag_names,
        timeout=timeout,
        command_timeout=command_timeout,
    )

    with open(os.path.join(must_gather_tmpdir, "output.log"), "w") as _file:
        _file.write(output)
    return get_must_gather_output_dir(must_gather_path=must_gather_tmpdir)
