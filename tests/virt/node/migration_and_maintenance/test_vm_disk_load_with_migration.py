import logging
import re
import shlex

import pytest
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_LABELS, FEDORA_LATEST_OS
from utilities.constants import TIMEOUT_1MIN
from utilities.virt import migrate_vm_and_verify, running_vm, vm_instance_from_template

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def vm_with_fio(
    request,
    cluster_cpu_model_scope_function,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_scope_function,
    ) as vm_with_fio:
        running_vm(vm=vm_with_fio)
        yield vm_with_fio


@pytest.fixture()
def running_fio_in_vm(vm_with_fio):
    # Random write/read -  create a 1G file, and perform 4KB reads and writes using a 75%/25%
    LOGGER.info("Running fio in VM")
    fio_cmd = shlex.split(
        "sudo nohup /usr/bin/fio --loops=400 --runtime=600 --randrepeat=1 --ioengine=libaio --direct=1 "
        "--gtod_reduce=1 --name=test --filename=/home/fedora/random_read_write.fio --bs=4k --iodepth=64 "
        "--size=1G --readwrite=randrw --rwmixread=75 --numjobs=8 >& /dev/null &"
    )
    run_ssh_commands(host=vm_with_fio.ssh_exec, commands=fio_cmd)


def get_disk_usage(ssh_exec):
    # After migration, the SSH connection may not be accessible for a brief moment ("No route to host")
    # Sometimes fio will stop the writes/read for a brief second and then continue, need to retry to make sure that the
    # IO continues
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=5,
            func=run_ssh_commands,
            host=ssh_exec,
            commands=shlex.split("sudo iotop -b -n 2 -o | grep -E \\'Actual|Current\\' | tail -n 1 "),
        ):
            if sample:
                # Example value of read_write_values : ('3.00', '3.72')
                read_write_values = re.search(r"READ:.*(\d+\.\d+) .*WRITE:.*(\d+\.\d+)", sample[0]).groups()
                if not any([disk_io for disk_io in read_write_values if disk_io == "0.00"]):
                    LOGGER.info(f"Disk load: {read_write_values}")
                    return
    except TimeoutExpiredError:
        LOGGER.error(f"No load on disks: {sample}")
        raise


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_with_fio",
    [
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST.get("image_path"),
                "storage_class": py_config["default_storage_class"],
                "dv_size": FEDORA_LATEST.get("dv_size"),
            },
            {
                "vm_name": "fedora-load-vm",
                "template_labels": FEDORA_LATEST_LABELS,
                "cpu_threads": 2,
            },
            marks=[pytest.mark.polarion("CNV-4663"), pytest.mark.x86_64()],
        ),
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST.get("image_path"),
                "storage_class": py_config["default_storage_class"],
                "dv_size": FEDORA_LATEST.get("dv_size"),
            },
            {
                "vm_name": "fedora-load-vm",
                "template_labels": FEDORA_LATEST_LABELS,
                "cpu_threads": 1,
            },
            marks=[pytest.mark.s390x()],
        ),
    ],
    indirect=True,
)
@pytest.mark.rwx_default_storage
def test_fedora_vm_load_migration(vm_with_fio, running_fio_in_vm):
    LOGGER.info("Test migrate VM with disk load")
    migrate_vm_and_verify(vm=vm_with_fio, check_ssh_connectivity=True)
    get_disk_usage(ssh_exec=vm_with_fio.ssh_exec)
