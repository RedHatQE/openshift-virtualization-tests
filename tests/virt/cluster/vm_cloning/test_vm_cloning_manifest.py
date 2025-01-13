import io
import logging
import shlex

import pytest
from ocp_resources.virtual_machine_clone import VirtualMachineClone
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from utilities.infra import run_virtctl_command

LOGGER = logging.getLogger(__name__)


VIRTCTL_CREATE_CLONE_COMMAND = (
    "create clone --source-type {source_type} --source-name {source_name} "
    "--target-name {target_name} --name {cloning_job_name} --annotation-filter '*' "
    "--annotation-filter '!someKey/*' --label-filter 'firstKey/*' "
    "--label-filter 'secondKey/*' --new-mac-address 'default:02-03-04-02-03-{mac}' "
    "--new-smbios-serial new-serial"
)


def create_cloning_job_from_manifest_and_wait_for_success(manifest):
    with VirtualMachineClone(yaml_file=manifest) as vmc:
        vmc.wait_for_status(status=VirtualMachineClone.Status.SUCCEEDED)


@pytest.fixture()
def virtctl_cloning_manifest(request, fedora_vm_for_cloning):
    source_type = request.param
    cmd = VIRTCTL_CREATE_CLONE_COMMAND.format(
        source_type=source_type,
        source_name=fedora_vm_for_cloning.name,
        target_name=f"{fedora_vm_for_cloning.name}-{source_type}-clone",
        cloning_job_name=f"manifest-clone-{source_type}",
        mac="01" if source_type == "vm" else "02",
    )
    _, out, _ = run_virtctl_command(command=shlex.split(cmd), namespace=fedora_vm_for_cloning.namespace, check=True)
    LOGGER.info(f"Manifest:\n {out}")
    return io.StringIO(out)


@pytest.fixture()
def vmsnapshot_created(fedora_vm_for_cloning):
    with VirtualMachineSnapshot(
        name=fedora_vm_for_cloning.name,
        namespace=fedora_vm_for_cloning.namespace,
        vm_name=fedora_vm_for_cloning.name,
    ) as snapshot:
        snapshot.wait_snapshot_done()
        yield


@pytest.mark.parametrize(
    "fedora_vm_for_cloning",
    [
        pytest.param(
            {
                "vm_name": "fedora-vm-for-manifest-clone-test",
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "fedora_vm_for_cloning",
)
class TestVMCloneVirtctlManifest:
    @pytest.mark.parametrize(
        "virtctl_cloning_manifest",
        [
            pytest.param("vm"),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-10300")
    def test_clone_vm_with_virtctl_manifest(self, virtctl_cloning_manifest):
        create_cloning_job_from_manifest_and_wait_for_success(manifest=virtctl_cloning_manifest)

    @pytest.mark.parametrize(
        "virtctl_cloning_manifest",
        [
            pytest.param("vmsnapshot"),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-10301")
    def test_clone_vmsnapshot_with_virtctl_manifest(self, vmsnapshot_created, virtctl_cloning_manifest):
        create_cloning_job_from_manifest_and_wait_for_success(manifest=virtctl_cloning_manifest)
