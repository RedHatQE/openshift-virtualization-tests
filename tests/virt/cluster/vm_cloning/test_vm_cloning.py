import shlex

import pytest
from ocp_resources.datavolume import DataVolume
from pyhelper_utils.shell import run_ssh_commands

from tests.virt.cluster.vm_cloning.constants import (
    ROOT_DISK_TEST_FILE_STR,
    SECOND_DISK_PATH,
    SECOND_DISK_TEST_FILE_STR,
)
from tests.virt.cluster.vm_cloning.utils import (
    assert_target_vm_has_new_pvc_disks,
    check_if_files_present_after_cloning,
)
from utilities.constants import RHEL_WITH_INSTANCETYPE_AND_PREFERENCE, Images
from utilities.infra import get_artifactory_config_map, get_artifactory_secret
from utilities.storage import (
    add_dv_to_vm,
    check_disk_count_in_vm,
    get_test_artifact_server_url,
)
from utilities.virt import (
    VirtualMachineForCloning,
    create_vm_cloning_job,
    migrate_vm_and_verify,
    running_vm,
    target_vm_from_cloning_job,
)

LABEL_TO_COPY_STR = "label-to-copy"
LABEL_TO_EXCLUDE_STR = "label-to-exclude"
ANNOTATION_TO_COPY_STR = "annotation-to-copy"
ANNOTATION_TO_EXCLUDE_STR = "annotation-to-exclude"

NEW_MAC_ADDRESS_CLONE_STR = "02-03-04-05-06-07"
NEW_SMBIOS_SERIAL_CLONE_STR = "target-serial"

RHEL_VM_WITH_TWO_PVC = "rhel-vm-with-two-pvc"
WINDOWS_VM_FOR_CLONING = "win-vm-for-cloning"
FEDORA_VM_FOR_CLONING = "fedora-vm-with-labels-annotations-mac-smbios"


def dv_dict_for_vm_cloning(namespace, storage_class, dv_template):
    dv = DataVolume(
        name=dv_template["name"],
        namespace=namespace.name,
        source=dv_template["source"],
        url=dv_template.get("url"),
        size=dv_template["size"],
        storage_class=storage_class,
        api_name="storage",
        secret=get_artifactory_secret(namespace=namespace.name),
        cert_configmap=get_artifactory_config_map(namespace=namespace.name).name,
    )
    dv.to_dict()
    return dv.res


@pytest.fixture()
def dv_template_for_vm_cloning(
    skip_if_no_storage_class_for_snapshot,
    request,
    namespace,
    storage_class_for_snapshot,
):
    source = request.param["source"]
    request.param["url"] = f"{get_test_artifact_server_url()}{request.param['image']}" if source == "http" else None

    return dv_dict_for_vm_cloning(
        namespace=namespace,
        storage_class=storage_class_for_snapshot,
        dv_template=request.param,
    )


@pytest.fixture()
def vm_with_dv_for_cloning(request, namespace, dv_template_for_vm_cloning, storage_class_for_snapshot):
    with VirtualMachineForCloning(
        name=request.param["vm_name"],
        namespace=namespace.name,
        data_volume_template=dv_template_for_vm_cloning,
        memory_requests=request.param["memory_requests"],
        cpu_cores=request.param.get("cpu_cores", 1),
        os_flavor=request.param["vm_name"].split("-")[0],
        smm_enabled=True,
        efi_params={"secureBoot": True},
    ) as vm:
        # Add second DV when needed
        if request.param.get("dv_extra"):
            add_dv_to_vm(
                vm=vm,
                template_dv=dv_dict_for_vm_cloning(
                    namespace=namespace,
                    storage_class=storage_class_for_snapshot,
                    dv_template=request.param["dv_extra"],
                ),
            )
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def cloning_job_fedora_vm(request, namespace):
    with create_vm_cloning_job(
        name=f"clone-job-{request.param['source_name']}",
        namespace=namespace.name,
        source_name=request.param["source_name"],
        target_name=request.param["target_name"],
        label_filters=request.param["label_filters"],
        annotation_filters=request.param["annotation_filters"],
        new_mac_addresses={"default": request.param["new_mac_addresses"]},
        new_smbios_serial=request.param["new_smbios_serial"],
    ) as vmc:
        yield vmc


@pytest.fixture()
def files_created_on_pvc_disks(vm_with_dv_for_cloning):
    run_ssh_commands(
        host=vm_with_dv_for_cloning.ssh_exec,
        commands=[
            # create file on root disk
            shlex.split(f"echo 'TEST' > {ROOT_DISK_TEST_FILE_STR}"),
            # create partition and file on second disk
            shlex.split(f"sudo mkfs.ext4 {SECOND_DISK_PATH}"),
            shlex.split(f"sudo mount {SECOND_DISK_PATH} /mnt"),
            shlex.split(f"echo 'TEST' | sudo tee {SECOND_DISK_TEST_FILE_STR}"),
            # update selinux: allow snapshot for second disk
            shlex.split("sudo setsebool -P virt_qemu_ga_read_nonsecurity_files 1"),
        ],
    )


@pytest.fixture(scope="class")
def fedora_target_vm(cloning_job_fedora_vm):
    with target_vm_from_cloning_job(cloning_job=cloning_job_fedora_vm) as target_vm:
        yield target_vm


@pytest.fixture(scope="class")
def fedora_target_vm_instance(fedora_target_vm):
    yield fedora_target_vm.instance


@pytest.mark.parametrize(
    "dv_template_for_vm_cloning, vm_with_dv_for_cloning, cloning_job_scope_function",
    [
        pytest.param(
            {
                "name": "rhel-dv-root-disk",
                "source": "http",
                "image": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL9_4_IMG}",
                "size": Images.Rhel.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": RHEL_VM_WITH_TWO_PVC,
                "memory_requests": Images.Rhel.DEFAULT_MEMORY_SIZE,
                "dv_extra": {"name": "dv-extra", "source": "blank", "size": "10Gi"},
            },
            {"source_name": RHEL_VM_WITH_TWO_PVC},
            marks=(
                pytest.mark.polarion("CNV-10295"),
                pytest.mark.gating(),
            ),
        )
    ],
    indirect=True,
)
def test_clone_vm_two_pvc_disks(
    vm_with_dv_for_cloning,
    files_created_on_pvc_disks,
    cloning_job_scope_function,
    target_vm_scope_function,
):
    assert_target_vm_has_new_pvc_disks(source_vm=vm_with_dv_for_cloning, target_vm=target_vm_scope_function)
    check_disk_count_in_vm(vm=target_vm_scope_function)
    check_if_files_present_after_cloning(vm=target_vm_scope_function)


@pytest.mark.parametrize(
    "cloning_job_scope_function",
    [
        pytest.param(
            {"source_name": RHEL_WITH_INSTANCETYPE_AND_PREFERENCE},
        )
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-10766")
def test_clone_vm_with_instance_type_and_preference(
    rhel_vm_with_instancetype_and_preference_for_cloning,
    cloning_job_scope_function,
    target_vm_scope_function,
):
    check_disk_count_in_vm(vm=target_vm_scope_function)


@pytest.mark.parametrize(
    "dv_template_for_vm_cloning, vm_with_dv_for_cloning, cloning_job_scope_function",
    [
        pytest.param(
            {
                "name": "windows-dv-root-disk",
                "source": "http",
                "image": f"{Images.Windows.HA_DIR}/{Images.Windows.WIN2k19_HA_IMG}",
                "size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": WINDOWS_VM_FOR_CLONING,
                "memory_requests": Images.Windows.DEFAULT_MEMORY_SIZE,
                "cpu_cores": Images.Windows.DEFAULT_CPU_CORES,
            },
            {"source_name": WINDOWS_VM_FOR_CLONING},
            marks=pytest.mark.polarion("CNV-10296"),
        )
    ],
    indirect=True,
)
@pytest.mark.ibm_bare_metal
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
def test_clone_windows_vm(
    vm_with_dv_for_cloning,
    cloning_job_scope_function,
    target_vm_scope_function,
):
    assert_target_vm_has_new_pvc_disks(source_vm=vm_with_dv_for_cloning, target_vm=target_vm_scope_function)


@pytest.mark.parametrize(
    "fedora_vm_for_cloning, cloning_job_fedora_vm",
    [
        pytest.param(
            {
                "vm_name": FEDORA_VM_FOR_CLONING,
                "labels": {LABEL_TO_COPY_STR: "label1", LABEL_TO_EXCLUDE_STR: "label2"},
                "annotations": {
                    ANNOTATION_TO_COPY_STR: "annotation1",
                    ANNOTATION_TO_EXCLUDE_STR: "annotation2",
                },
                "smbios_serial": "source-serial",
            },
            {
                "source_name": FEDORA_VM_FOR_CLONING,
                "target_name": f"{FEDORA_VM_FOR_CLONING}-clone",
                "label_filters": ["*", f"!{LABEL_TO_EXCLUDE_STR}/*"],
                "annotation_filters": ["*", f"!{ANNOTATION_TO_EXCLUDE_STR}/*"],
                "new_mac_addresses": NEW_MAC_ADDRESS_CLONE_STR,
                "new_smbios_serial": NEW_SMBIOS_SERIAL_CLONE_STR,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.arm64
@pytest.mark.gating
@pytest.mark.usefixtures(
    "fedora_vm_for_cloning",
    "cloning_job_fedora_vm",
)
class TestVMCloneAndMigrate:
    @pytest.mark.polarion("CNV-10333")
    def test_clone_vm_with_labels_annotations_smbios(
        self,
        fedora_target_vm,
    ):
        check_disk_count_in_vm(vm=fedora_target_vm)

    @pytest.mark.polarion("CNV-10352")
    def test_check_labels_on_clone(self, fedora_target_vm_instance):
        labels = dict(fedora_target_vm_instance.metadata.labels)
        assert LABEL_TO_COPY_STR in labels, (
            f"Not all expected labels present on the clone: \n Current labels: {labels}, Expected: {LABEL_TO_COPY_STR}"
        )
        assert LABEL_TO_EXCLUDE_STR not in labels, (
            f"Excluded labels present on the clone: \n Current labels: {labels}, Excluded: {LABEL_TO_EXCLUDE_STR}"
        )

    @pytest.mark.polarion("CNV-10353")
    def test_check_annotations_on_clone(self, fedora_target_vm_instance):
        annotations = dict(fedora_target_vm_instance.metadata.annotations)
        assert ANNOTATION_TO_COPY_STR in annotations, (
            f"Not all expected annotations present on the clone: \n Current labels: {annotations}, "
            f"Expected: {ANNOTATION_TO_COPY_STR}"
        )
        assert ANNOTATION_TO_EXCLUDE_STR not in annotations, (
            f"Excluded labels present on the clone: \n Current labels: {annotations}, "
            f"Excluded: {ANNOTATION_TO_EXCLUDE_STR}"
        )

    @pytest.mark.polarion("CNV-10354")
    def test_check_new_mac_address_on_clone(self, fedora_target_vm_instance):
        for iface in fedora_target_vm_instance.spec.template.spec.domain.devices.interfaces:
            assert iface.macAddress == NEW_MAC_ADDRESS_CLONE_STR, (
                f"MAC Address on the target VM is not correct: {iface.macAddress}"
            )

    @pytest.mark.polarion("CNV-10355")
    def test_check_new_smbios_serial_on_clone(self, fedora_target_vm_instance):
        current_serial = fedora_target_vm_instance.spec.template.spec.domain.get("firmware", {}).get("serial")
        assert current_serial == NEW_SMBIOS_SERIAL_CLONE_STR, (
            f"SMBIOS Serial is not correct on the target VM. Current: {current_serial}, "
            f"Expected: {NEW_SMBIOS_SERIAL_CLONE_STR}"
        )

    @pytest.mark.polarion("CNV-10320")
    def test_migrate_the_vm_clone(self, fedora_target_vm):
        migrate_vm_and_verify(vm=fedora_target_vm)

    @pytest.mark.parametrize(
        "cloning_job_scope_function",
        [
            pytest.param(
                {
                    "source_name": f"{FEDORA_VM_FOR_CLONING}-clone",
                    "label_filters": ["*", f"!{LABEL_TO_EXCLUDE_STR}/*"],
                    "annotation_filters": ["*", f"!{ANNOTATION_TO_EXCLUDE_STR}/*"],
                },
            )
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-10294")
    def test_clone_vm_with_clone_as_source(self, cloning_job_scope_function, target_vm_scope_function):
        check_disk_count_in_vm(vm=target_vm_scope_function)
