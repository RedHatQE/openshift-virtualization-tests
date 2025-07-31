import logging
import os.path
import re

import pytest
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from ocp_resources.virtual_machine import VirtualMachine
from pytest_testconfig import py_config

from tests.install_upgrade_operators.constants import FILE_SUFFIX, SECTION_TITLE
from tests.install_upgrade_operators.must_gather.utils import (
    BRIDGE_COMMAND,
    BRIDGE_TXT,
    CAPABILITIES_XML,
    DOMBLKLIST_TXT,
    DOMCAPABILITIES_XML,
    DOMJOBINFO_TXT,
    DUMPXML_XML,
    IP_TXT,
    LIST_TXT,
    RULETABLES_TXT,
    TABLE_IP_FILTER,
    TABLE_IP_NAT,
    VALIDATE_FIELDS,
    check_disks_exists_in_blockjob_file,
    check_list_of_resources,
    check_no_duplicate_and_missing_files_collected_from_migrated_vm,
    extracted_data_from_must_gather_on_vm_node,
    validate_files_collected,
    validate_guest_console_logs_collected,
    validate_no_empty_files_collected_must_gather_vm,
)
from tests.os_params import FEDORA_LATEST
from utilities.constants import ARM_64, COUNT_FIVE

pytestmark = [pytest.mark.post_upgrade, pytest.mark.skip_must_gather_collection, pytest.mark.arm64]

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def kubevirt_architecture_configuration_scope_session(
    kubevirt_resource_scope_session,
    nodes_cpu_architecture,
):
    kubevirt_architecture_config = kubevirt_resource_scope_session.instance.to_dict()["spec"]["configuration"][
        "architectureConfiguration"
    ][nodes_cpu_architecture]

    # Default value of kubevirt.spec.configuration.architectureConfiguration.arm64.ovmfPath is
    # '/usr/share/AAVMF' but the files in this location are symlinked to
    # '/usr/share/edk2/aarch64'. VM domain capabilities refer to symlinked file.
    if nodes_cpu_architecture == ARM_64:
        kubevirt_architecture_config["ovmfPath"] = "/usr/share/edk2/aarch64"
    return kubevirt_architecture_config


@pytest.mark.usefixtures("collected_cluster_must_gather_with_vms")
@pytest.mark.sno
class TestMustGatherClusterWithVMs:
    @pytest.mark.parametrize(
        ("resource_type", "resource_path", "checks"),
        [
            pytest.param(
                NetworkAttachmentDefinition,
                "namespaces/{namespace}/"
                f"{NetworkAttachmentDefinition.ApiGroup.K8S_CNI_CNCF_IO}/"
                "network-attachment-definitions/{name}.yaml",
                VALIDATE_FIELDS,
                marks=(pytest.mark.polarion("CNV-2720")),
                id="test_network_attachment_definitions_resources",
            ),
            pytest.param(
                VirtualMachine,
                f"namespaces/{{namespace}}/{VirtualMachine.ApiGroup.KUBEVIRT_IO}/virtualmachines/custom/{{name}}.yaml",
                VALIDATE_FIELDS,
                marks=(pytest.mark.polarion("CNV-3043")),
                id="test_virtualmachine_resources",
            ),
        ],
        indirect=["resource_type"],
    )
    def test_resource_type(
        self,
        admin_client,
        collected_cluster_must_gather_with_vms,
        resource_type,
        resource_path,
        checks,
    ):
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=resource_type,
            temp_dir=collected_cluster_must_gather_with_vms,
            resource_path=resource_path,
            checks=checks,
        )


@pytest.mark.sno
class TestMustGatherVmDetails:
    @pytest.mark.parametrize(
        "extracted_data_from_must_gather_file, format_regex",
        [
            pytest.param(
                {FILE_SUFFIX: BRIDGE_TXT, SECTION_TITLE: "bridge fdb show:"},
                "{mac_address}",
                marks=(pytest.mark.polarion("CNV-2735")),
                id="test_bridge_fdb_show_mac_address",
            ),
            pytest.param(
                {FILE_SUFFIX: BRIDGE_TXT, SECTION_TITLE: f"{BRIDGE_COMMAND}:"},
                "{bridge_link_show}",
                marks=(pytest.mark.polarion("CNV-10280")),
                id="test_bridge_link_show",
            ),
            pytest.param(
                {FILE_SUFFIX: BRIDGE_TXT, SECTION_TITLE: "bridge vlan show:"},
                "{interface_name}",
                marks=(pytest.mark.polarion("CNV-2736")),
                id="test_bridge_vlan_show",
            ),
            pytest.param(
                {FILE_SUFFIX: IP_TXT, SECTION_TITLE: None},
                "{interface_name}",
                marks=(pytest.mark.polarion("CNV-2734")),
                id="test_ip",
            ),
            pytest.param(
                {FILE_SUFFIX: RULETABLES_TXT, SECTION_TITLE: None},
                TABLE_IP_FILTER,
                marks=(pytest.mark.polarion("CNV-2737"),),
                id="test_ruletables_ip_filter",
            ),
            pytest.param(
                {FILE_SUFFIX: RULETABLES_TXT, SECTION_TITLE: None},
                TABLE_IP_NAT,
                marks=(pytest.mark.polarion("CNV-2741"),),
                id="test_ruletables_nat_table",
            ),
            pytest.param(
                {FILE_SUFFIX: "qemu.log", SECTION_TITLE: None},
                "-name guest={namespace}_{name},debug-threads=on \\\\$",
                marks=(pytest.mark.polarion("CNV-2725")),
                id="test_qemu",
            ),
            pytest.param(
                {FILE_SUFFIX: DUMPXML_XML, SECTION_TITLE: None},
                "^ +<name>{namespace}_{name}</name>$",
                marks=(pytest.mark.polarion("CNV-3477")),
                id="test_dumpxml",
            ),
            pytest.param(
                {FILE_SUFFIX: CAPABILITIES_XML, SECTION_TITLE: None},
                "{machine_type}</machine>",
                marks=(pytest.mark.polarion("CNV-10518")),
                id="test_capabilities",
            ),
            pytest.param(
                {FILE_SUFFIX: DOMBLKLIST_TXT, SECTION_TITLE: None},
                "{namespace}/{name}",
                marks=(pytest.mark.polarion("CNV-10517")),
                id="test_domblklist",
            ),
            pytest.param(
                {FILE_SUFFIX: LIST_TXT, SECTION_TITLE: None},
                "{namespace}_{name}",
                marks=(pytest.mark.polarion("CNV-10516")),
                id="test_list",
            ),
            pytest.param(
                {FILE_SUFFIX: DOMCAPABILITIES_XML, SECTION_TITLE: None},
                "<value>{ovmfpath}",
                marks=(pytest.mark.polarion("CNV-10519")),
                id="test_domcapabilities",
            ),
            pytest.param(
                {FILE_SUFFIX: DOMJOBINFO_TXT, SECTION_TITLE: None},
                r"Job type:(\s*)None",
                marks=(pytest.mark.polarion("CNV-10520")),
                id="test_domjobinfo",
            ),
        ],
        indirect=["extracted_data_from_must_gather_file"],
    )
    def test_data_collected_from_virt_launcher(
        self,
        kubevirt_architecture_configuration_scope_session,
        must_gather_vm,
        collected_vm_details_must_gather,
        nad_mac_address,
        vm_interface_name,
        extracted_data_from_must_gather_file,
        nftables_ruleset_from_utility_pods,
        format_regex,
        executed_bridge_link_show_command,
    ):
        if "name" in format_regex and "namespace" in format_regex:
            format_regex = format_regex.format(namespace=must_gather_vm.namespace, name=must_gather_vm.name)
        elif "mac_address" in format_regex:
            format_regex = format_regex.format(mac_address=nad_mac_address)
        elif "interface_name" in format_regex:
            format_regex = format_regex.format(interface_name=vm_interface_name)
        elif "bridge_link_show" in format_regex:
            format_regex = executed_bridge_link_show_command
        elif "machine_type" in format_regex:
            format_regex = format_regex.format(
                # TODO: directly use the object.machineType when the bug CNV-45481 is resolved
                # and the fixture was updated to return the kubevirt architectureConfiguration object directly
                machine_type=kubevirt_architecture_configuration_scope_session["machineType"]
            )
        elif "ovmfpath" in format_regex:
            # TODO: directly use the object.ovmfPath when the bug CNV-45481 is resolved
            # and the fixture was updated to return the kubevirt architectureConfiguration object directly
            format_regex = format_regex.format(ovmfpath=kubevirt_architecture_configuration_scope_session["ovmfPath"])
        LOGGER.info(
            f"Results from search: "
            f"{re.search(format_regex, extracted_data_from_must_gather_file, re.MULTILINE | re.IGNORECASE)}"
        )
        # Make sure that gathered data roughly matches expected format.
        matches = re.search(
            format_regex,
            extracted_data_from_must_gather_file,
            re.MULTILINE | re.IGNORECASE,
        )

        if not matches:
            if format_regex in (TABLE_IP_NAT, TABLE_IP_FILTER):
                if nftables_ruleset_from_utility_pods.values():
                    assert extracted_data_from_must_gather_file, (
                        f"{format_regex} does not contains nftables output: "
                        f"{nftables_ruleset_from_utility_pods}, file is empty"
                    )
                else:
                    LOGGER.warning(
                        f"For vm: {must_gather_vm.name} data collected from virt launcher associated with section "
                        f"{format_regex}: {extracted_data_from_must_gather_file} while nftables output collected from "
                        f"the cluster is: {nftables_ruleset_from_utility_pods}"
                    )
            else:
                raise AssertionError(
                    f"Gathered data are not matching expected format.\nExpected format:\n{format_regex}\n "
                    f"Gathered data:\n{extracted_data_from_must_gather_file}"
                )

    @pytest.mark.parametrize(
        "data_volume_scope_class",
        [
            pytest.param(
                {
                    "dv_name": "dv-fedora",
                    "image": FEDORA_LATEST.get("image_path"),
                    "storage_class": py_config["default_storage_class"],
                    "dv_size": FEDORA_LATEST.get("dv_size"),
                },
                marks=(pytest.mark.polarion("CNV-10515")),
                id="test_blockjob",
            ),
        ],
        indirect=True,
    )
    def test_blockjob_file_collected_from_virt_launcher(
        self,
        data_volume_scope_class,
        multiple_disks_vm,
        disks_from_multiple_disks_vm,
        collected_vm_details_must_gather_function_scope,
        extracted_data_from_must_gather_file_multiple_disks,
    ):
        check_disks_exists_in_blockjob_file(
            disks_from_multiple_disks_vm=disks_from_multiple_disks_vm,
            extracted_data_from_must_gather_file_multiple_disks=extracted_data_from_must_gather_file_multiple_disks,
        )

    @pytest.mark.polarion("CNV-10243")
    def test_must_gather_and_vm_same_node(
        self,
        must_gather_vm,
        collected_vm_details_must_gather_from_vm_node,
    ):
        extracted_data_from_must_gather_on_vm_node(
            collected_vm_details_must_gather_from_vm_node=collected_vm_details_must_gather_from_vm_node,
            must_gather_vm=must_gather_vm,
        )


@pytest.mark.sno
class TestGuestConsoleLog:
    @pytest.mark.usefixtures("updated_disable_serial_console_log_false", "must_gather_vm_scope_class")
    @pytest.mark.polarion("CNV-10630")
    def test_guest_console_logs(
        self,
        must_gather_vm_scope_class,
        collected_vm_details_must_gather,
    ):
        validate_guest_console_logs_collected(
            vm=must_gather_vm_scope_class,
            collected_vm_details_must_gather=collected_vm_details_must_gather,
        )


@pytest.mark.sno
class TestMustGatherVmLongNameDetails:
    @pytest.mark.polarion("CNV-9233")
    def test_data_collected_from_virt_launcher_long(
        self,
        must_gather_long_name_vm,
        collected_vm_details_must_gather,
        nftables_ruleset_from_utility_pods,
    ):
        validate_files_collected(
            base_path=collected_vm_details_must_gather,
            vm_list=[must_gather_long_name_vm],
            nftables_ruleset_from_utility_pods=nftables_ruleset_from_utility_pods,
        )


class TestNoMultipleFilesCollected:
    @pytest.mark.parametrize(
        "vm_for_migration_test, migrated_vm_multiple_times",
        [
            pytest.param(
                "vm-migrate",
                COUNT_FIVE,
                marks=(pytest.mark.polarion("CNV-10643")),
            )
        ],
        indirect=True,
    )
    def test_no_multiple_empty_files_collected_from_must_gather_migrated_vm(
        self,
        skip_if_no_common_cpu,
        vm_for_migration_test,
        migrated_vm_multiple_times,
        collected_vm_details_must_gather,
        must_gather_vm_files_path,
    ):
        check_no_duplicate_and_missing_files_collected_from_migrated_vm(
            must_gather_vm_file_list=must_gather_vm_files_path,
            vm_namespace=vm_for_migration_test.namespace,
            vm_name=vm_for_migration_test.name,
        )
        validate_no_empty_files_collected_must_gather_vm(
            vm=vm_for_migration_test,
            must_gather_vm_file_list=must_gather_vm_files_path,
            must_gather_vm_path=collected_vm_details_must_gather,
        )


@pytest.mark.sno
class TestControllerRevisionCollected:
    @pytest.mark.polarion("CNV-10978")
    def test_controller_revision_collected(
        self,
        rhel_vm_with_cluster_instance_type_and_preference,
        collected_vm_details_must_gather,
        extracted_controller_revision_from_must_gather,
    ):
        assert os.path.getsize(extracted_controller_revision_from_must_gather) > 0
