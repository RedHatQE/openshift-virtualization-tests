import logging
import os
import re
import shlex
from pathlib import Path

import pytest
import xmltodict
from pyhelper_utils.shell import run_ssh_commands

from utilities.constants import Images
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


def sorted_keys_for_minor_version(s):
    sub_strings = re.split(r"(\d+)", str(s))
    sub_strings = [int(c) if c.isdigit() else c for c in sub_strings]
    return sub_strings


@pytest.fixture()
def rhel_vm(request, unprivileged_client, namespace):
    with VirtualMachineForTests(
        name=request.param["vm_name"],
        client=unprivileged_client,
        namespace=namespace.name,
        image=request.param["image"],
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def libosinfo_rhel_minor_ver_num(request, downloaded_latest_libosinfo_db):
    rhel_version = request.param
    osinfo_file_folder_path = os.path.join(f"{downloaded_latest_libosinfo_db}/os/redhat.com/")

    list_of_rhel_os_files = list(
        sorted(
            Path(osinfo_file_folder_path).glob(f"{rhel_version}.*.xml"), key=sorted_keys_for_minor_version, reverse=True
        )
    )

    for file_path in list_of_rhel_os_files:
        with open(file_path) as file:
            parsed_xml = xmltodict.parse(file.read())["libosinfo"]["os"]
            if parsed_xml.get("release-date"):
                LOGGER.info(f"Latest stable version: {parsed_xml['version']}")
                return parsed_xml["version"].split(".")[-1]
            else:
                LOGGER.info(f"Latest version ({parsed_xml['short-id']}) not released, looking for stable version")


@pytest.fixture()
def rhel_vm_minor_ver_num(rhel_vm):
    rhel_vm_os_ver = run_ssh_commands(
        host=rhel_vm.ssh_exec,
        commands=(shlex.split("cat /etc/redhat-release")),
    )[0]
    return re.findall(r"(?<=\.)(\d+[\.]?[\d+]?)(?= )", rhel_vm_os_ver)[0]


@pytest.mark.parametrize(
    "rhel_vm, libosinfo_rhel_minor_ver_num",
    [
        pytest.param(
            {
                "vm_name": "rhel8-vm",
                "image": Images.Rhel.RHEL8_REGISTRY_GUEST_IMG,
            },
            "rhel-8",
            marks=pytest.mark.polarion("CNV-7666"),
        ),
        pytest.param(
            {
                "vm_name": "rhel9-vm",
                "image": Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
            },
            "rhel-9",
            marks=pytest.mark.polarion("CNV-7716"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_latest_minor_ver_rhel(libosinfo_rhel_minor_ver_num, rhel_vm_minor_ver_num):
    assert libosinfo_rhel_minor_ver_num == rhel_vm_minor_ver_num, (
        f"os versions mismatch, VM minor version: {rhel_vm_minor_ver_num}, "
        f"osinfo DB latest minor version: {libosinfo_rhel_minor_ver_num}"
    )
