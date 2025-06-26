import base64
import logging
import os
import shlex

import pytest
from ocp_resources.config_map import ConfigMap
from ocp_resources.resource import ResourceEditor
from ocp_resources.secret import Secret
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import py_config
from timeout_sampler import TimeoutSampler

from tests.os_params import WINDOWS_2019, WINDOWS_2019_OS
from utilities.bitwarden import get_cnv_tests_secret_by_name
from utilities.constants import BASE_IMAGES_DIR, OS_FLAVOR_WINDOWS, TCP_TIMEOUT_30SEC, TIMEOUT_5MIN
from utilities.ssp import get_windows_timezone
from utilities.storage import data_volume_template_with_source_ref_dict, get_downloaded_artifact
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, running_vm

LOGGER = logging.getLogger(__name__)

UNATTEND_FILE_NAME = "unattend_win2k19.xml"
ANSWER_FILE_NAME = "autounattend.xml"
NEW_TIMEZONE = "AUS Eastern Standard Time"


def __get_sysprep_missing_autounattend_condition(vm):
    expected_error = f"Sysprep drive should contain {ANSWER_FILE_NAME}"
    return [
        condition for condition in vm.vmi.instance.status.conditions if expected_error in condition.get("message", "")
    ]


def verify_changes_from_autounattend(vm, timezone, hostname):
    # timezone
    LOGGER.info(f"Verifying timezone change from answer file in vm {vm.name}")
    actual_timezone = get_windows_timezone(ssh_exec=vm.ssh_exec, get_standard_name=True).split(":")[1].strip()
    assert actual_timezone == timezone, f"Incorrect timezone, expected {timezone}, found {actual_timezone}"

    # hostname
    LOGGER.info(f"Verifying hostname change from answer file in vm {vm.name}")
    actual_hostname = run_ssh_commands(host=vm.ssh_exec, commands=["hostname"], tcp_timeout=TCP_TIMEOUT_30SEC)[
        0
    ].strip()
    assert actual_hostname == hostname, f"Incorrect hostname, expected {hostname}, found {actual_hostname}"


def verify_failed_boot_without_autounattend(vm):
    """A VM with a sysprep resource attached should not be able to start
    without a file present in that resource named autounattend.xml (case-insensitive).
    This function assumes this is the case and attempts to start the VM, then
    verifies that the expected error condition appears."""

    LOGGER.info(f"Starting VM {vm.name} without {ANSWER_FILE_NAME}")
    vm.start(wait=False)
    LOGGER.info("Waiting for error condition to appear")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=1,
        func=__get_sysprep_missing_autounattend_condition,
        vm=vm,
    ):
        if sample:
            return True


def generate_sysprep_data(xml_string, resource_kind):
    if resource_kind == "ConfigMap":
        data_string = xml_string
    elif resource_kind == "Secret":
        data_string = base64.b64encode(s=bytes(xml_string, "ascii")).decode("ascii")

    return {"Autounattend.xml": data_string, "Unattend.xml": data_string}


@pytest.fixture(scope="session")
def sysprep_vm_credentials_from_bitwarden():
    return get_cnv_tests_secret_by_name(secret_name="sys_prep_credentials")


@pytest.fixture(scope="class")
def sysprep_vm_hostname(sysprep_vm_credentials_from_bitwarden):
    return sysprep_vm_credentials_from_bitwarden["hostname"]


@pytest.fixture(scope="class")
def sysprep_xml_string(tmpdir_factory):
    local_unattend_file_path = os.path.join(tmpdir_factory.mktemp("sysprep-folder"), UNATTEND_FILE_NAME)
    remote_name = f"{BASE_IMAGES_DIR}/test-manifests/sysprep_xmls/{UNATTEND_FILE_NAME}"
    get_downloaded_artifact(remote_name=remote_name, local_name=local_unattend_file_path)

    with open(local_unattend_file_path) as xml_file:
        yield xml_file.read()
    os.remove(local_unattend_file_path)


@pytest.fixture(scope="class")
def sysprep_resource(sysprep_source_matrix__class__, unprivileged_client, namespace, sysprep_xml_string):
    LOGGER.info(f"Creating sysprep {sysprep_source_matrix__class__} resource")
    if sysprep_source_matrix__class__ == "ConfigMap":
        with ConfigMap(
            client=unprivileged_client,
            name="sysprep-config",
            namespace=namespace.name,
            data=generate_sysprep_data(xml_string=sysprep_xml_string, resource_kind="ConfigMap"),
        ) as sysprep:
            yield sysprep
    elif sysprep_source_matrix__class__ == "Secret":
        with Secret(
            client=unprivileged_client,
            name="sysprep-secret",
            namespace=namespace.name,
            data_dict=generate_sysprep_data(xml_string=sysprep_xml_string, resource_kind="Secret"),
        ) as sysprep:
            yield sysprep


@pytest.fixture(scope="class")
def sysprep_vm(
    sysprep_source_matrix__class__,
    golden_image_data_source_scope_class,
    modern_cpu_for_migration,
    unprivileged_client,
    namespace,
    instance_type_for_test_scope_class,
):
    with instance_type_for_test_scope_class as vm_instance_type:
        with VirtualMachineForTests(
            name=f"sysprep-{sysprep_source_matrix__class__.lower()}-vm",
            namespace=namespace.name,
            client=unprivileged_client,
            vm_instance_type=vm_instance_type,
            vm_preference=VirtualMachineClusterPreference(name="windows.2k19"),
            data_volume_template=data_volume_template_with_source_ref_dict(
                data_source=golden_image_data_source_scope_class
            ),
            os_flavor=OS_FLAVOR_WINDOWS,
            disk_type=None,
            cpu_model=modern_cpu_for_migration,
        ) as vm:
            running_vm(vm=vm)
            yield vm


@pytest.fixture(scope="class")
def sealed_vm(sysprep_vm):
    """Runs the sysprep tool on sysprep_vm, preparing it to do an OS refresh using
    the provided answer file on next boot"""

    LOGGER.info(f"Sealing VM {sysprep_vm.name}")
    run_ssh_commands(
        host=sysprep_vm.ssh_exec,
        commands=shlex.split(
            "%WINDIR%\\system32\\sysprep\\sysprep.exe /generalize /quit /oobe /mode:vm",
            posix=False,
        ),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )


@pytest.fixture(scope="class")
def attached_sysprep_volume_to_vm(sysprep_vm_credentials_from_bitwarden, sysprep_resource, sysprep_vm):
    LOGGER.info(f"Attaching sysprep volume {sysprep_resource.name} to vm {sysprep_vm.name}")

    disks = sysprep_vm.instance.spec.template.spec.domain.devices.disks
    disks.append({"name": "sysprep", "cdrom": {"bus": "sata"}})

    sysprep_resource_kind = "configMap" if sysprep_resource.kind == "ConfigMap" else "secret"

    volumes = sysprep_vm.instance.spec.template.spec.volumes
    volumes.append({
        "name": "sysprep",
        "sysprep": {sysprep_resource_kind: {"name": sysprep_resource.name}},
    })

    with ResourceEditor(
        patches={
            sysprep_vm: {
                "spec": {
                    "template": {
                        "spec": {
                            "domain": {
                                "devices": {"disks": disks},
                            },
                            "volumes": volumes,
                        },
                    }
                }
            }
        },
    ) as edits:
        sysprep_vm.username = sysprep_vm_credentials_from_bitwarden["username"]
        sysprep_vm.password = sysprep_vm_credentials_from_bitwarden["password"]

        sysprep_vm.stop(wait=True)
        running_vm(vm=sysprep_vm)

        yield edits


@pytest.fixture()
def migrated_sysprep_vm(sysprep_vm):
    migrate_vm_and_verify(vm=sysprep_vm, check_ssh_connectivity=True)


@pytest.fixture()
def shutdown_and_removed_autounattend_from_sysprep_resource(sysprep_vm, sysprep_resource):
    """Shuts down sysprep_vm and renames both answerfiles in the sysprep volume
    to prepare for a negative test case where a VM attached to a sysprep volume
    missing these files will fail to boot"""

    LOGGER.info(f"Removing {ANSWER_FILE_NAME} from sysprep volume")
    sysprep_vm.stop(wait=True)

    answer_file_str = sysprep_resource.instance.data["Autounattend.xml"]
    bad_data = {"aun.xml": answer_file_str, "un.xml": answer_file_str}

    edits = ResourceEditor(patches={sysprep_resource: {"data": None}})
    edits.update(backup_resources=True)

    ResourceEditor(patches={sysprep_resource: {"data": bad_data}}).update()

    yield

    LOGGER.info(f"Returning {ANSWER_FILE_NAME} to sysprep volume")
    sysprep_vm.stop(wait=True)
    edits.restore()
    running_vm(vm=sysprep_vm)


@pytest.fixture()
def detached_sysprep_resource_and_restarted_vm(sysprep_vm, attached_sysprep_volume_to_vm):
    LOGGER.info(f"Detaching sysprep volume from vm {sysprep_vm.name}")
    sysprep_vm.stop(wait=True)
    attached_sysprep_volume_to_vm.restore()
    running_vm(vm=sysprep_vm)

    yield

    LOGGER.info(f"Re-attaching sysprep volume to vm {sysprep_vm.name}")
    sysprep_vm.stop(wait=True)
    attached_sysprep_volume_to_vm.update(backup_resources=True)
    running_vm(vm=sysprep_vm)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, common_instance_type_param_dict",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_2019_OS,
                "image": WINDOWS_2019.get("image_path"),
                "dv_size": WINDOWS_2019.get("dv_size"),
                "storage_class": py_config["default_storage_class"],
            },
            {
                "name": "basic",
                "memory_requests": "8Gi",
            },
        )
    ],
    indirect=True,
)
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
@pytest.mark.usefixtures("sysprep_vm", "sealed_vm", "attached_sysprep_volume_to_vm")
class TestSysprep:
    @pytest.mark.polarion("CNV-6760")
    def test_admin_user_locale_computer_name_after_boot(self, sysprep_vm, sysprep_vm_hostname):
        verify_changes_from_autounattend(vm=sysprep_vm, timezone=NEW_TIMEZONE, hostname=sysprep_vm_hostname)

    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-6761")
    def test_migrate_vm_with_sysprep_cm(self, sysprep_vm, migrated_sysprep_vm, sysprep_vm_hostname):
        verify_changes_from_autounattend(vm=sysprep_vm, timezone=NEW_TIMEZONE, hostname=sysprep_vm_hostname)

    @pytest.mark.polarion("CNV-6762")
    def test_remove_sysprep_volume_and_check_data_persistence(
        self, sysprep_vm, detached_sysprep_resource_and_restarted_vm, sysprep_vm_hostname
    ):
        verify_changes_from_autounattend(vm=sysprep_vm, timezone=NEW_TIMEZONE, hostname=sysprep_vm_hostname)

    @pytest.mark.polarion("CNV-6763")
    def test_remove_autounattend_and_boot(self, sysprep_vm, shutdown_and_removed_autounattend_from_sysprep_resource):
        assert verify_failed_boot_without_autounattend(vm=sysprep_vm), (
            f"Error condition for missing {ANSWER_FILE_NAME} not met when attempting to start VM {sysprep_vm.name}"
        )
