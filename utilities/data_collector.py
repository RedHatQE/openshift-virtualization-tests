import json
import logging
import os
import shlex
from datetime import UTC, datetime
from functools import cache

from _pytest.nodes import Collector
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance import VirtualMachineInstance
from ocp_utilities.monitoring import Prometheus
from pytest import Item
from pytest_testconfig import config as py_config

import utilities.hco
import utilities.infra
from utilities.cluster import cache_admin_client
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_10MIN, TIMEOUT_20MIN
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

    LOGGER.info(f"Writing data to file: {file_path}")
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


def collect_vnc_screenshot_for_vms(vm: VirtualMachine) -> None:
    """Collect a VNC screenshot for a VM when its state supports VNC access.

    Args:
        vm (VirtualMachine): VM object used to read status, name, and namespace.
    """
    printable_status = vm.instance.get("status", {}).get("printableStatus")
    if printable_status in (VirtualMachine.Status.RUNNING, VirtualMachine.Status.MIGRATING):
        base_dir = get_data_collector_base_directory()
        utilities.infra.run_virtctl_command(
            command=shlex.split(f"vnc screenshot {vm.name} -f {base_dir}/{vm.namespace}-{vm.name}.png"),
            namespace=vm.namespace,
        )
    else:
        LOGGER.warning(f"Skipping VNC screenshot for VM {vm.name}, status is '{printable_status}'.")


def _get_cnv_must_gather_image(admin_client: DynamicClient) -> str:
    """Resolve the CNV must-gather image from the installed HCO CSV.

    Args:
        admin_client: Cluster admin client used to query the CSV.

    Returns:
        The must-gather container image URL.
    """
    cnv_csv = utilities.hco.get_installed_hco_csv(
        admin_client=admin_client,
        hco_namespace=Namespace(client=admin_client, name=py_config["hco_namespace"]),
    )
    return [image["image"] for image in cnv_csv.instance.spec.relatedImages if "must-gather" in image["name"]][0]


def collect_must_gather_for_vm(vm: VirtualMachine, admin_client: DynamicClient | None = None) -> None:
    """Run CNV must-gather --vm-incident for one VM at the current time.

    Uses the product incident collector which gathers only data pertinent to
    the VM: virt-launcher logs, node diagnostics, metrics, and storage chain.
    No cluster-wide noise. Timeboxed to 10 minutes.

    Args:
        vm (VirtualMachine): VM whose incident data should be collected.
        admin_client (DynamicClient | None): Optional cluster admin client; falls back to cache_admin_client().
    """
    try:
        admin_client = admin_client or cache_admin_client()
        must_gather_image = _get_cnv_must_gather_image(admin_client=admin_client)
        incident_time = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        LOGGER.info(f"Collecting vm-incident must-gather for VM {vm.name} at {incident_time}")
        run_must_gather(
            image_url=must_gather_image,
            target_base_dir=os.path.join(get_data_collector_dir(), "vm_must_gather"),
            script_name=f"NS={vm.namespace} VM={vm.name} /usr/bin/gather",
            flag_names=f"vm-incident,incident-time={incident_time}",
            timeout=f"{TIMEOUT_10MIN}s",
            command_timeout=TIMEOUT_10MIN,
        )
    except Exception:
        LOGGER.exception(f"[DATA_COLLECTOR] Failed to collect must-gather for VM {vm.name}")


def collect_ocp_must_gather(since_time):
    base_directory = get_data_collector_dir()
    LOGGER.info(f"Collecting OCP must-gather data under: {base_directory}, for time {since_time} seconds.")
    run_must_gather(target_base_dir=base_directory, since=f"{since_time}s", timeout=f"{TIMEOUT_20MIN}s")


def collect_default_cnv_must_gather_with_vm_gather(since_time, target_dir, admin_client):
    must_gather_image = _get_cnv_must_gather_image(admin_client=admin_client)
    LOGGER.info("Collecting cnv-must gather for VMs")
    run_must_gather(
        image_url=must_gather_image,
        target_base_dir=target_dir,
        since=f"{since_time}s",
        script_name="/usr/bin/gather",
        flag_names="vms_details",
    )


def collect_virt_launcher_debug_data(node: Item | Collector) -> None:
    """Collect best-effort diagnostics from only the failed test's VM pod.

    The collector executes diagnostic commands in the VM's virt-launcher pod
    and writes the command output to the data collector directory. Failures
    are logged and do not propagate to the failed test handling flow.

    Args:
        node: The pytest item or collector associated with the failed test.
    """
    output_dir = os.path.join(get_data_collector_dir(), "virt_launcher_debug")
    funcargs = getattr(node, "funcargs", {})
    vm_candidates = sorted(
        (
            value
            for value in funcargs.values()
            if isinstance(value, (VirtualMachine, VirtualMachineInstance))
            and getattr(value, "name", None)
            and getattr(value, "namespace", None)
        ),
        key=lambda resource: (resource.namespace, resource.name),
    )
    if len(vm_candidates) > 1:
        LOGGER.warning(
            "[DATA_COLLECTOR] Multiple VM/VMI resources were available; "
            "skipping virt-launcher diagnostics to avoid selecting the wrong resource"
        )
        return
    vm = vm_candidates[0] if vm_candidates else None
    if vm is None:
        LOGGER.warning("[DATA_COLLECTOR] Failed test VM/VMI was not available; skipping virt-launcher diagnostics")
        return

    try:
        # A privileged client is required to resolve and exec into virt-launcher.
        admin_client = cache_admin_client()
        vmi = getattr(vm, "vmi", vm)
        pod = vmi.get_virt_launcher_pod(privileged_client=admin_client)
        pod_name = pod.name
        pod_namespace = pod.namespace
    except Exception as exc:
        LOGGER.warning(f"[DATA_COLLECTOR] Failed to resolve virt-launcher for {vm.namespace}/{vm.name}: {exc}")
        return

    diagnostic_script = r"""set +e
echo '=== collected-at ==='; date -u
echo '=== threads ==='; ps -eLf 2>&1
for process in /proc/[0-9]*; do
  read -r process_name 2>/dev/null < "$process/comm" || continue
  case "$process_name" in
    virtqemud|libvirtd|qemu-kvm|qemu-system-*) ;;
    *) continue ;;
  esac
  pid="${process##*/}"
  echo "=== PID $pid cmdline ==="; tr '\0' ' ' < "/proc/$pid/cmdline"; echo
  echo "=== PID $pid status ==="; cat "/proc/$pid/status"
  echo "=== PID $pid kernel stack ==="; cat "/proc/$pid/stack"
  for task in /proc/$pid/task/*; do
    echo "=== $task status ==="; cat "$task/status"
    echo "=== $task scheduler ==="; cat "$task/sched" 2>&1
    echo "=== $task scheduler counters ==="; cat "$task/schedstat" 2>&1
    echo "=== $task kernel stack ==="; cat "$task/stack"
  done
done
echo '=== monitor sockets ==='; find /var/run/kubevirt-private -type s -o -type p 2>/dev/null
VIRSH_URI=qemu:///session
timeout 10 virsh -c "$VIRSH_URI" list --all >/dev/null 2>&1 || VIRSH_URI=qemu:///system
echo "=== virsh uri === $VIRSH_URI"
echo '=== virsh list ==='; timeout 10 virsh -c "$VIRSH_URI" list --all 2>&1
for domain in $(timeout 10 virsh -c "$VIRSH_URI" list --name 2>/dev/null); do
  [ -z "$domain" ] && continue
  echo "=== $domain dumpxml ==="; timeout 10 virsh -c "$VIRSH_URI" dumpxml "$domain" 2>&1
  echo "=== $domain query-status ==="; timeout 10 virsh -c "$VIRSH_URI" qemu-monitor-command "$domain" --pretty '{"execute":"query-status"}' 2>&1
  echo "=== $domain query-cpus-fast ==="; timeout 10 virsh -c "$VIRSH_URI" qemu-monitor-command "$domain" --pretty '{"execute":"query-cpus-fast"}' 2>&1
  echo "=== $domain query-chardev ==="; timeout 10 virsh -c "$VIRSH_URI" qemu-monitor-command "$domain" --pretty '{"execute":"query-chardev"}' 2>&1
  echo "=== $domain guest-agent ping ==="; timeout 10 virsh -c "$VIRSH_URI" qemu-agent-command "$domain" '{"execute":"guest-ping"}' 2>&1
done
"""

    try:
        output = pod.execute(
            command=["sh", "-c", diagnostic_script],
            container="compute",
            timeout=TIMEOUT_2MIN,
            ignore_rc=True,
        )
        write_to_file(
            file_name=f"{pod_namespace}_{pod_name}.txt".replace("/", "_"),
            content=f"=== pod-namespace ===\n{pod_namespace}\n=== pod-name ===\n{pod_name}\n{output}",
            base_directory=output_dir,
        )
    except Exception as exc:
        LOGGER.warning(f"[DATA_COLLECTOR] Failed diagnostics for {pod_namespace}/{pod_name}: {exc}")


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
    testpaths = item.session.config.getini(name="testpaths")
    assert testpaths, "pytest.ini must include testpaths"
    tests_path = testpaths[0]

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


def get_scope_identifier(node: Item | Collector, scope_value: str | None) -> str:
    """
    Get the identifier name based on data collection scope.

    Args:
        node: Pytest node (Item or Collector).
        scope_value: Scope value from marker ("module", "class", or None for test).

    Returns:
        Database key for this scope.
    """
    if scope_value == "module":
        return str(node.fspath)
    elif scope_value == "class":
        return f"{node.fspath}::{node.parent.name}" if node.parent else str(node.fspath)
    else:
        return f"{node.fspath}::{node.name}"
