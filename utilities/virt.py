from __future__ import annotations

import io
import ipaddress
import json
import logging
import os
import re
import secrets
import shlex
from collections import defaultdict
from contextlib import contextmanager
from json import JSONDecodeError
from subprocess import run
from typing import TYPE_CHECKING, Any, Dict, Optional

import bitmath
import jinja2
import pexpect
import yaml
from benedict import benedict
from kubernetes.client import ApiException
from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.node import Node
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource, ResourceEditor, get_client
from ocp_resources.service import Service
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.template import Template
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_clone import VirtualMachineClone
from ocp_resources.virtual_machine_instance import VirtualMachineInstance
from ocp_resources.virtual_machine_instance_migration import (
    VirtualMachineInstanceMigration,
)
from ocp_utilities.exceptions import CommandExecFailed
from paramiko import ProxyCommandFailure
from pyhelper_utils.shell import run_command, run_ssh_commands
from pytest_testconfig import config as py_config
from rrmngmnt import Host, ssh, user
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

import utilities.infra
from utilities.console import Console
from utilities.constants import (
    CLOUD_INIT_DISK_NAME,
    CLOUD_INIT_NO_CLOUD,
    CNV_VM_SSH_KEY_PATH,
    DATA_SOURCE_NAME,
    DATA_SOURCE_NAMESPACE,
    DEFAULT_KUBEVIRT_CONDITIONS,
    DV_DISK,
    EVICTIONSTRATEGY,
    IP_FAMILY_POLICY_PREFER_DUAL_STACK,
    LINUX_AMD_64,
    LINUX_STR,
    OS_FLAVOR_CIRROS,
    OS_FLAVOR_FEDORA,
    OS_FLAVOR_WINDOWS,
    OS_PROC_NAME,
    ROOTDISK,
    SSH_PORT_22,
    TCP_TIMEOUT_30SEC,
    TIMEOUT_1MIN,
    TIMEOUT_1SEC,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_6MIN,
    TIMEOUT_8MIN,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_12MIN,
    TIMEOUT_25MIN,
    TIMEOUT_30MIN,
    VIRT_LAUNCHER,
    VIRTCTL,
    Images,
)
from utilities.data_collector import collect_vnc_screenshot_for_vms
from utilities.hco import wait_for_hco_conditions
from utilities.storage import get_default_storage_class

if TYPE_CHECKING:
    from libs.vm.vm import BaseVirtualMachine


LOGGER = logging.getLogger(__name__)

K8S_TAINT = "node.kubernetes.io/unschedulable"
NO_SCHEDULE = "NoSchedule"
CIRROS_IMAGE = "kubevirt/cirros-container-disk-demo:latest"
FLAVORS_EXCLUDED_FROM_CLOUD_INIT = (OS_FLAVOR_WINDOWS, OS_FLAVOR_CIRROS)
VM_ERROR_STATUSES = [
    VirtualMachine.Status.CRASH_LOOPBACK_OFF,
    VirtualMachine.Status.ERROR_UNSCHEDULABLE,
    VirtualMachine.Status.ERROR_PVC_NOT_FOUND,
    VirtualMachine.Status.IMAGE_PULL_BACK_OFF,
    VirtualMachine.Status.ERR_IMAGE_PULL,
]


def wait_for_vm_interfaces(vmi: VirtualMachineInstance, timeout: int = TIMEOUT_12MIN) -> bool:
    """
    Wait until guest agent report VMI network interfaces.

    Args:
        vmi (VirtualMachineInstance): VMI object.
        timeout (int): Maximum time to wait for interfaces status

    Returns:
        bool: True if agent report VMI interfaces.

    Raises:
        TimeoutExpiredError: After timeout reached.
    """
    # Waiting for guest agent connection before checking guest agent interfaces report
    LOGGER.info(f"Wait until guest agent is active on {vmi.name}")
    vmi.wait_for_condition(
        condition=VirtualMachineInstance.Condition.Type.AGENT_CONNECTED,
        status=VirtualMachineInstance.Condition.Status.TRUE,
        timeout=timeout,
    )
    LOGGER.info(f"Wait for {vmi.name} network interfaces")
    sampler = TimeoutSampler(wait_timeout=timeout, sleep=1, func=lambda: vmi.instance)
    for sample in sampler:
        interfaces = sample.get("status", {}).get("interfaces", [])
        active_interfaces = [interface for interface in interfaces if interface.get("interfaceName")]
        if len(active_interfaces) == len(interfaces):
            return True
    return False


def generate_cloud_init_data(data):
    """
    Generate cloud init data from a dictionary.

    Args:
        data (dict): cloud init data to set under desired section.

    Returns:
        str: A generated str for cloud init.

    Example:
        data = {
            "networkData": {
                "version": 2,
                "ethernets": {
                    "eth0": {
                        "dhcp4": True,
                        "addresses": "[ fd10:0:2::2/120 ]",
                        "gateway6": "fd10:0:2::1",
                    }
                }
            }
        }

        with VirtualMachineForTests(
            namespace="namespace",
            name="vm",
            body=fedora_vm_body("vm"),
            cloud_init_data=data,
        ) as vm:
            pass
    """
    dict_data = {}
    for section, _data in data.items():
        str_data = ""
        generated_data = yaml.dump(_data, width=1000)
        if section == "userData":
            str_data += "#cloud-config\n"

        for line in generated_data.splitlines():
            str_data += f"{line}\n"
        dict_data[section] = str_data
    return dict_data


def merge_dicts(source_dict, target_dict):
    """Merge nested source_dict into target_dict"""

    for key, value in source_dict.items():
        if isinstance(value, dict):
            node = target_dict.setdefault(key, {})
            merge_dicts(source_dict=value, target_dict=node)
        else:
            target_dict[key] = value

    return target_dict


class VirtualMachineForTests(VirtualMachine):
    def __init__(
        self,
        name,
        namespace,
        eviction_strategy=None,
        body=None,
        client=None,
        interfaces=None,
        networks=None,
        node_selector=None,
        service_accounts=None,
        cpu_flags=None,
        cpu_limits=None,
        cpu_requests=None,
        cpu_sockets=None,
        cpu_cores=None,
        cpu_threads=None,
        cpu_model=None,
        cpu_max_sockets=None,
        memory_requests=None,
        memory_limits=None,
        memory_guest=None,
        memory_max_guest=None,
        cloud_init_data=None,
        machine_type=None,
        image=None,
        ssh=True,
        ssh_secret=None,
        network_model=None,
        network_multiqueue=None,
        pvc=None,
        data_volume=None,
        data_volume_template=None,
        teardown=True,
        cloud_init_type=None,
        attached_secret=None,
        cpu_placement=False,
        isolate_emulator_thread=False,
        iothreads_policy=None,
        dedicated_iothread=False,
        smm_enabled=None,
        pvspinlock_enabled=None,
        efi_params=None,
        diskless_vm=False,
        run_strategy=VirtualMachine.RunStrategy.HALTED,
        disk_io_options=None,
        username=None,
        password=None,
        macs=None,
        interfaces_types=None,
        os_flavor=OS_FLAVOR_FEDORA,
        host_device_name=None,
        gpu_name=None,
        vhostmd=False,
        vm_debug_logs=False,
        priority_class_name=None,
        dry_run=None,
        additional_labels=None,
        generate_unique_name=True,
        node_selector_labels=None,
        vm_instance_type=None,
        vm_instance_type_infer=False,
        vm_preference=None,
        vm_preference_infer=False,
        vm_validation_rule=None,
        termination_grace_period=None,
        disk_type="virtio",
        yaml_file=None,
        tpm_params=None,
        hugepages_page_size=None,
        vm_affinity=None,
        annotations=None,
    ):
        """
        Virtual machine creation

        Args:
            name (str): VM name
            namespace (str): Namespace name
            eviction_strategy (str, optional): valid options("None", "LiveMigrate", "LiveMigrateIfPossible", "External")
                Default value None here is same as Null and not the string "None" which is one of the valid options
            body (dict, optional): VM [metadata] and spec
            client (:obj:`DynamicClient`, optional): admin client or unprivileged client
            interfaces (list, optional): list of interfaces names
            networks (dict, optional)
            node_selector (dict, optional): Node name
            service_accounts (list, optional): list of service account names
            cpu_flags (str, optional)
            cpu_limits (quantity, optional): quantity supports string, ints, and floats
            cpu_requests (quantity, optional): quantity supports string, ints, and floats
            cpu_sockets (int, optional)
            cpu_cores (int, optional)
            cpu_threads (int, optional)
            cpu_model (str, optional)
            cpu_max_sockets (int, optional)
            memory_requests (str, optional)
            memory_limits (str, optional)
            memory_guest (str, optional)
            memory_max_guest (str, optional)
            cloud_init_data (dict, optional): cloud-init dict
            machine_type (str, optional)
            image (str, optional)
            ssh (bool, default: True): If True and using "with" (contextmanager) statement, create an SSH service
            ssh_secret (:obj:,`Secret`, optional): Needs cloud_init_type as cloudInitNoCloud
            network_model (str, optional)
            network_multiqueue (None/bool, optional, default: None): If not None, set to True/False
            pvc (:obj:`PersistentVolumeClaim`, optional)
            data_volume (:obj:`DataVolume`, optional)
            data_volume_template (dict, optional)
            teardown (bool, default: True)
            cloud_init_type (str, optional): cloud-init type, for example: cloudInitNoCloud, cloudInitConfigDrive
            attached_secret (dict, optional)
            cpu_placement (bool, default: False): If True, set dedicatedCpuPlacement = True
            isolate_emulator_thread (bool, default: False): If True, set isolateEmulatorThread = True.
                Need to explicitly also set cpu_placement = True, as dedicatedCpuPlacement should also be True.
            iothreads_policy (str, optional, default: None): If not None, set to auto/shared
            dedicated_iothread (bool, optional, default: False): If True, set dedicatedIOThread to True
            smm_enabled (None/bool, optional, default: None): If not None, set to True/False
            pvspinlock_enabled (bool, optional, default: None): If not None, set to True/False
            efi_params (dict, optional)
            diskless_vm (bool, default: False): If True, remove VM disks
            run_strategy (str, default: "Halted"): Set runStrategy
            disk_io_options (str, optional): Set root disk IO
            username (str, optional): SSH username
            password (str, optional): SSH password
            macs (dict, optional): Dict of {interface_name: mac address}
            interfaces_types (dict, optional): Dict of interfaces names and type ({"iface1": "sriov"})
            os_flavor (str, default: fedora): OS flavor to get SSH login parameters.
                (flavor should be exist in constants.py)
            host_device_name (str, optional): PCI Host Device Name (For Example: "nvidia.com/GV100GL_Tesla_V100")
            gpu_name (str, optional): GPU Device Name (For Example: "nvidia.com/GV100GL_Tesla_V100")
            vhostmd (bool, optional, default: False): If True, configure vhostmd.
            vm_debug_logs(bool, default=False): if True, add 'debugLogs' label to VM to
                enable libvirt debug logs in the virt-launcher pod.
                Is set to True if py_config["data_collector"] is True.
            priority_class_name (str, optional): The name of the priority class used for the VM
            dry_run (str, default=None): If "All", the resource will be created using the dry_run flag
            additional_labels (dict, optional): Dict of additional labels for VM (e.g. {"vm-label": "best-vm"})
            generate_unique_name: if True then it will set dynamic name for the vm, False will use the name of vm passed
            node_selector_labels (str, optional): Labels for node selector.
            vm_instance_type (VirtualMachineInstancetype, optional): instance type object for the VM
            vm_instance_type_infer (bool, optional): if True fetch the instance type from the VM volume
            vm_preference (VirtualMachinePreference, optional): preference object for the VM
            vm_preference_infer (bool, optional): if True fetch the preference from the VM volume
            vm_validation_rule (dict, optional): dict defining validation rule to be added to the VM
            termination_grace_period (int, optional): seconds to wait until VMI is force terminated after stopping
            disk_type (str, default: "virtio"): define disk type (e.g "virtio", "sata", None)
            tpm_params (dict, optional):
                {} - for tpm not persistent state (suitable for bypassing windows install tpm check)
                {persistent: true} - for persistent state
            hugepages_page_size (str, optional) defines the size of huge pages,Valid values are 2 Mi and 1 Gi
            vm_affinity (dict, optional): If affinity is specifies, obey all the affinity rules
            annotations (dict, optional): annotations to be added to the VM
        """
        # Sets VM unique name - replaces "." with "-" in the name to handle valid values.

        self.name = utilities.infra.unique_name(name=name) if generate_unique_name else name
        super().__init__(
            name=self.name,
            namespace=namespace,
            client=client,
            teardown=teardown,
            dry_run=dry_run,
            node_selector=node_selector,
            node_selector_labels=node_selector_labels,
            yaml_file=yaml_file,
        )
        self.body = body
        self.interfaces = interfaces or []
        self.service_accounts = service_accounts or []
        self.networks = networks or {}
        self.node_selector = node_selector
        self.eviction_strategy = eviction_strategy
        self.cpu_flags = cpu_flags
        self.cpu_limits = cpu_limits
        self.cpu_requests = cpu_requests
        self.cpu_sockets = cpu_sockets
        self.cpu_cores = cpu_cores
        self.cpu_threads = cpu_threads
        self.cpu_model = cpu_model
        self.cpu_max_sockets = cpu_max_sockets
        self.memory_requests = memory_requests
        self.memory_limits = memory_limits
        self.memory_guest = memory_guest
        self.memory_max_guest = memory_max_guest
        self.cloud_init_data = cloud_init_data
        self.machine_type = machine_type
        self.image = image
        self.ssh = ssh
        self.ssh_secret = ssh_secret
        self.custom_service = None
        self.network_model = network_model
        self.network_multiqueue = network_multiqueue
        self.data_volume_template = data_volume_template
        self.cloud_init_type = cloud_init_type
        self.pvc = pvc
        self.attached_secret = attached_secret
        self.cpu_placement = cpu_placement
        self.isolate_emulator_thread = isolate_emulator_thread
        self.iothreads_policy = iothreads_policy
        self.dedicated_iothread = dedicated_iothread
        self.data_volume = data_volume
        self.smm_enabled = smm_enabled
        self.pvspinlock_enabled = pvspinlock_enabled
        self.efi_params = efi_params
        self.diskless_vm = diskless_vm
        self.is_vm_from_template = False
        self.run_strategy = run_strategy
        self.disk_io_options = disk_io_options
        self.username = username
        self.password = password
        self.macs = macs
        self.interfaces_types = interfaces_types or {}
        self.os_flavor = os_flavor
        self.host_device_name = host_device_name
        self.gpu_name = gpu_name
        self.vhostmd = vhostmd
        self.vm_debug_logs = vm_debug_logs or py_config.get("data_collector")
        self.priority_class_name = priority_class_name
        self.additional_labels = additional_labels
        self.node_selector_labels = node_selector_labels
        self.vm_instance_type = vm_instance_type
        self.vm_instance_type_infer = vm_instance_type_infer
        self.vm_preference = vm_preference
        self.vm_preference_infer = vm_preference_infer
        self.vm_validation_rule = vm_validation_rule
        self.termination_grace_period = termination_grace_period
        self.disk_type = disk_type
        self.tpm_params = tpm_params
        self.hugepages_page_size = hugepages_page_size
        self.vm_affinity = vm_affinity
        self.annotations = annotations

        # Must be here to apply on existing VMs
        self.set_login_params()

    def deploy(self, wait=False):
        super().deploy(wait=wait)
        return self

    def clean_up(self, wait: bool = True, timeout: int | None = None) -> bool:
        if self.exists and self.ready:
            self.stop(wait=True, vmi_delete_timeout=TIMEOUT_8MIN)
        super().clean_up(wait=wait, timeout=timeout)
        if self.custom_service:
            self.custom_service.delete(wait=True)
        return True

    def to_dict(self):
        super().to_dict()
        self.set_labels()
        self.set_rng_device()
        self.generate_body()
        self.set_run_strategy()
        self.set_instance_type()
        self.set_vm_preference()
        self.set_vm_validation_rule()
        self.is_vm_from_template = self._is_vm_from_template()

        template_spec = self.res["spec"]["template"]["spec"]
        if self.eviction_strategy:
            template_spec[EVICTIONSTRATEGY] = self.eviction_strategy
        template_spec = self.set_hugepages_page_size(template_spec=template_spec)
        template_spec = self.update_node_selector(template_spec=template_spec)
        template_spec = self.update_vm_network_configuration(template_spec=template_spec)
        template_spec = self.update_vm_cpu_configuration(template_spec=template_spec)
        template_spec = self.update_vm_memory_configuration(template_spec=template_spec)
        template_spec = self.set_smm(template_spec=template_spec)
        template_spec = self.set_pvspinlock(template_spec=template_spec)
        template_spec = self.set_efi_params(template_spec=template_spec)
        template_spec = self.set_tpm_params(template_spec=template_spec)
        template_spec = self.set_machine_type(template_spec=template_spec)
        template_spec = self.set_iothreads_policy(template_spec=template_spec)
        template_spec = self.set_hostdevice(template_spec=template_spec)
        template_spec = self.set_gpu(template_spec=template_spec)
        template_spec = self.set_disk_io_configuration(template_spec=template_spec)
        template_spec = self.set_priority_class(template_spec=template_spec)
        template_spec = self.set_termination_grace_period(template_spec=template_spec)
        template_spec = self.set_vm_affinity_rule(template_spec=template_spec)

        # Either update storage and cloud-init configuration or remove disks from spec
        if self.diskless_vm:
            template_spec = self.set_diskless_vm(template_spec=template_spec)
        else:
            template_spec = self.update_vm_storage_configuration(template_spec=template_spec)
            template_spec = self.set_service_accounts(template_spec=template_spec)
            # cloud-init disks must be set after DV disks in order to boot from DV.
            template_spec = self.update_vm_cloud_init_data(template_spec=template_spec)
            template_spec = self.set_vhostmd(template_spec=template_spec)

            template_spec = self.update_vm_secret_configuration(template_spec=template_spec)

            # VMs do not necessarily have self.cloud_init_data
            # cloud-init will not be set for OS in FLAVORS_EXCLUDED_FROM_CLOUD_INIT
            if self.ssh and not any(flavor in self.os_flavor for flavor in FLAVORS_EXCLUDED_FROM_CLOUD_INIT):
                if self.ssh_secret is None:
                    template_spec = self.enable_ssh_in_cloud_init_data(template_spec=template_spec)
                if self.ssh_secret:
                    template_spec = self.update_vm_ssh_secret_configuration(template_spec=template_spec)

    def set_hugepages_page_size(self, template_spec):
        if self.hugepages_page_size:
            template_spec.setdefault("domain", {}).setdefault("memory", {})["hugepages"] = {
                "pageSize": self.hugepages_page_size
            }
        return template_spec

    def update_node_selector(self, template_spec):
        if self.node_selector_spec:
            template_spec["nodeSelector"] = self.node_selector_spec
        return template_spec

    def set_disk_io_configuration(self, template_spec):
        if self.disk_io_options or self.dedicated_iothread:
            disks_spec = template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("disks", [])
            for disk in disks_spec:
                if disk["name"] == ROOTDISK:
                    if self.disk_io_options:
                        disk["io"] = self.disk_io_options
                    if self.dedicated_iothread:
                        disk["dedicatedIOThread"] = self.dedicated_iothread
                    break

            template_spec["domain"]["devices"]["disks"] = disks_spec

        return template_spec

    def set_gpu(self, template_spec):
        if self.gpu_name:
            template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("gpus", []).append({
                "deviceName": self.gpu_name,
                "name": "gpu",
            })

        return template_spec

    def set_hostdevice(self, template_spec):
        if self.host_device_name:
            template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("hostDevices", []).append({
                "deviceName": self.host_device_name,
                "name": "hostdevice",
            })

        return template_spec

    def set_diskless_vm(self, template_spec):
        template_spec.get("domain", {}).get("devices", {}).pop("disks", None)
        # As of https://bugzilla.redhat.com/show_bug.cgi?id=1954667 <skip-bug-check>, it is not possible to create a VM
        # with volume(s) without corresponding disks
        template_spec.pop("volumes", None)

        return template_spec

    def set_machine_type(self, template_spec):
        if self.machine_type:
            template_spec.setdefault("domain", {}).setdefault("machine", {})["type"] = self.machine_type

        return template_spec

    def set_iothreads_policy(self, template_spec):
        if self.iothreads_policy:
            template_spec.setdefault("domain", {})["ioThreadsPolicy"] = self.iothreads_policy

        return template_spec

    def set_efi_params(self, template_spec):
        if self.efi_params is not None:
            template_spec.setdefault("domain", {}).setdefault("firmware", {}).setdefault("bootloader", {})["efi"] = (
                self.efi_params
            )

        return template_spec

    def set_tpm_params(self, template_spec):
        if self.tpm_params is not None:
            template_spec.setdefault("domain", {}).setdefault("devices", {})["tpm"] = self.tpm_params

        return template_spec

    def set_smm(self, template_spec):
        if self.smm_enabled is not None:
            template_spec.setdefault("domain", {}).setdefault("features", {}).setdefault("smm", {})["enabled"] = (
                self.smm_enabled
            )

        return template_spec

    def set_pvspinlock(self, template_spec):
        if self.pvspinlock_enabled is not None:
            template_spec.setdefault("domain", {}).setdefault("features", {}).setdefault("pvspinlock", {})[
                "enabled"
            ] = self.pvspinlock_enabled

        return template_spec

    def set_priority_class(self, template_spec):
        if self.priority_class_name:
            template_spec["priorityClassName"] = self.priority_class_name

        return template_spec

    def set_termination_grace_period(self, template_spec):
        if self.termination_grace_period:
            template_spec["terminationGracePeriodSeconds"] = self.termination_grace_period

        return template_spec

    def set_rng_device(self):
        # Create rng device so the vm will be able to use /dev/rnd without
        # waiting for entropy collecting.
        self.res.setdefault("spec", {}).setdefault("template", {}).setdefault("spec", {}).setdefault(
            "domain", {}
        ).setdefault("devices", {}).setdefault("rng", {})

    def set_service_accounts(self, template_spec):
        for sa in self.service_accounts:
            template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("disks", []).append({
                "disk": {},
                "name": sa,
            })
            template_spec.setdefault("volumes", []).append({"name": sa, "serviceAccount": {"serviceAccountName": sa}})

        return template_spec

    def set_vhostmd(self, template_spec):
        name = "vhostmd"
        if self.vhostmd:
            template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("disks", []).append({
                "disk": {"bus": self.disk_type},
                "name": name,
            })
            template_spec.setdefault("volumes", []).append({"name": name, "downwardMetrics": {}})

        return template_spec

    def set_vm_affinity_rule(self, template_spec):
        if self.vm_affinity:
            template_spec["affinity"] = self.vm_affinity
        return template_spec

    def set_labels(self):
        vm_labels = self.res["spec"]["template"].setdefault("metadata", {}).setdefault("labels", {})
        vm_labels.update({
            f"{Resource.ApiGroup.KUBEVIRT_IO}/vm": self.name,
            f"{Resource.ApiGroup.KUBEVIRT_IO}/domain": self.name,
        })

        if self.additional_labels:
            vm_labels.update(self.additional_labels)

        if self.vm_debug_logs:
            vm_labels["debugLogs"] = "true"

    def set_run_strategy(self):
        # when runStrategy is set to Halted the VM will not start on creation
        # when runStrategy is set to Always the VM will start on creation
        # To create a VM resource, but not begin VM cloning, use VirtualMachine.RunStrategy.MANUAL
        self.res["spec"]["runStrategy"] = self.run_strategy

    def set_instance_type(self):
        if self.vm_instance_type:
            self.res["spec"]["instancetype"] = {
                "kind": self.vm_instance_type.kind,
                "name": self.vm_instance_type.name,
            }
        if self.vm_instance_type_infer:
            self.res["spec"].setdefault("instancetype", {})["inferFromVolume"] = DV_DISK

    def set_vm_preference(self):
        if self.vm_preference:
            self.res["spec"]["preference"] = {
                "kind": self.vm_preference.kind,
                "name": self.vm_preference.name,
            }
        if self.vm_preference_infer:
            self.res["spec"].setdefault("preference", {})["inferFromVolume"] = DV_DISK

    def set_vm_validation_rule(self):
        if self.vm_validation_rule:
            add_validation_rule_to_annotation(
                vm_annotation=self.res["metadata"].setdefault("annotations", {}),
                vm_validation_rule=self.vm_validation_rule,
            )

    def _is_vm_from_template(self):
        return f"{self.ApiGroup.VM_KUBEVIRT_IO}/template" in self.res["metadata"].setdefault("labels", {}).keys()

    def generate_body(self):
        if self.body:
            if self.body.get("metadata"):
                # We must set name in Template, since we use a unique name here we override it.
                self.res["metadata"] = self.body["metadata"]
                self.res["metadata"]["name"] = self.name

            self.res["spec"] = self.body["spec"]

            if self.annotations:
                self.res["metadata"].setdefault("annotations", {}).update(self.annotations)

    def update_vm_memory_configuration(self, template_spec):
        # Faster VMI start time
        if (
            OS_FLAVOR_WINDOWS in self.os_flavor
            and not self.memory_guest
            and not self.memory_requests
            and not self.vm_instance_type
            and not self.vm_instance_type_infer
        ):
            self.memory_guest = Images.Windows.DEFAULT_MEMORY_SIZE

        # memory_guest (memory.guest) value is the amount of memory given to VM itself
        # memory_requests (requests.memory) value is the amount of memory given to virt-launcher pod
        # (this also includes virtualization infra overhead)
        # although both values can be set simulteniously on the VM spec, only memory.guest should be used by user
        # (which is meant to reflect VM memory amount)
        if self.memory_guest and self.memory_requests:
            LOGGER.warning(
                "Setting both memory.guest and requests.memory values! (Users should set VM memory via memory.guest!)"
            )
            if bitmath.parse_string_unsafe(self.memory_guest) > bitmath.parse_string_unsafe(self.memory_requests):
                LOGGER.warning(
                    "Setting memory.guest bigger then requests.memory! (This might cause unpredictable issues!)"
                )

        if self.memory_guest:
            template_spec.setdefault("domain", {}).setdefault("memory", {})["guest"] = str(self.memory_guest)

        if self.memory_max_guest:
            template_spec.setdefault("domain", {}).setdefault("memory", {})["maxGuest"] = self.memory_max_guest

        if self.memory_requests:
            LOGGER.warning("Setting requests.memory value! (Users should set VM memory via memory.guest!)")
            template_spec.setdefault("domain", {}).setdefault("resources", {}).setdefault("requests", {})["memory"] = (
                self.memory_requests
            )

        if self.memory_limits:
            template_spec.setdefault("domain", {}).setdefault("resources", {}).setdefault("limits", {})["memory"] = (
                self.memory_limits
            )

        return template_spec

    def update_vm_network_configuration(self, template_spec):
        for iface_name in self.interfaces:
            iface_type = self.interfaces_types.get(iface_name, "bridge")
            network_dict = {"name": iface_name, iface_type: {}}

            if self.macs:
                network_dict["macAddress"] = self.macs.get(iface_name)

            template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("interfaces", []).append(
                network_dict
            )

        for iface_name, network in self.networks.items():
            template_spec.setdefault("networks", []).append({"name": iface_name, "multus": {"networkName": network}})

        if self.network_model:
            template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("interfaces", [{}])[0][
                "model"
            ] = self.network_model

        if self.network_multiqueue is not None:
            template_spec.setdefault("domain", {}).setdefault("devices", {}).update({
                "networkInterfaceMultiqueue": self.network_multiqueue
            })

        return template_spec

    def update_vm_cloud_init_data(self, template_spec):
        if self.cloud_init_data:
            cloud_init_volume = vm_cloud_init_volume(vm_spec=template_spec)
            cloud_init_volume_type = self.cloud_init_type or CLOUD_INIT_NO_CLOUD
            generated_cloud_init = generate_cloud_init_data(data=self.cloud_init_data)
            existing_cloud_init_data = cloud_init_volume.get(cloud_init_volume_type)
            # If spec already contains cloud init data
            if existing_cloud_init_data:
                cloud_init_volume[cloud_init_volume_type]["userData"] += generated_cloud_init["userData"].strip(
                    "#cloud-config"
                )
            else:
                cloud_init_volume[cloud_init_volume_type] = generated_cloud_init

            template_spec = vm_cloud_init_disk(vm_spec=template_spec)

        return template_spec

    def enable_ssh_in_cloud_init_data(self, template_spec):
        cloud_init_volume = vm_cloud_init_volume(vm_spec=template_spec)
        cloud_init_volume_type = self.cloud_init_type or CLOUD_INIT_NO_CLOUD

        template_spec = vm_cloud_init_disk(vm_spec=template_spec)

        cloud_init_volume.setdefault(cloud_init_volume_type, {}).setdefault("userData", "")

        # Saving in an intermediate string for readability
        cloud_init_user_data = cloud_init_volume[cloud_init_volume_type]["userData"]

        # Populate userData with OS-related login credentials; not needed for a VM from template.
        if not self.is_vm_from_template:
            login_generated_data = generate_cloud_init_data(
                data={
                    "userData": {
                        "user": self.username,
                        "password": self.password,
                        "chpasswd": {"expire": False},
                    }
                }
            )
            # 'ssh_pwaut' field is needed for Fedora38 VMs, where PasswordAuthentication in
            # /etc/ssh/sshd_config.d/50-cloud-init.conf is set to 'no', but to allow ssh connection it should be 'yes'.
            if self.os_flavor == OS_FLAVOR_FEDORA:
                login_generated_data["userData"] += "ssh_pwauth: true\n"
            # Newline needed in case userData is not empty
            cloud_init_user_data_newline = "\n" if cloud_init_user_data else ""
            cloud_init_user_data += f"{cloud_init_user_data_newline}{login_generated_data['userData']}"

        # Add RSA to authorized_keys to enable login using an SSH key
        authorized_key = utilities.infra.authorized_key(private_key_path=os.environ[CNV_VM_SSH_KEY_PATH])
        cloud_init_user_data += f"\nssh_authorized_keys:\n [{authorized_key}]"

        # Enable LEGACY crypto policies - needed until keys updated to ECDSA
        # Enable PasswordAuthentication in /etc/ssh/sshd_config
        # Enable SSH service and restart SSH service
        run_cmd_commands = [
            (
                # TODO: Remove LEGACY ssh-rsa support after ECDSA supported by test
                "grep ssh-rsa /etc/crypto-policies/back-ends/opensshserver.config || "
                "sudo update-crypto-policies --set LEGACY || true"
            ),
            (r"sudo sed -i 's/^#\?PasswordAuthentication no/PasswordAuthentication yes/g' " "/etc/ssh/sshd_config"),
            "sudo systemctl enable sshd",
            "sudo systemctl restart sshd",
        ]

        run_ssh_generated_data = generate_cloud_init_data(data={"runcmd": run_cmd_commands})

        # If runcmd already exists in userData, add run_cmd_commands before any other command
        runcmd_prefix = "runcmd:"
        if runcmd_prefix in cloud_init_user_data:
            cloud_init_user_data = re.sub(
                runcmd_prefix,
                f"{runcmd_prefix}\n{run_ssh_generated_data['runcmd']}",
                cloud_init_user_data,
            )
        else:
            cloud_init_user_data += f"\nruncmd: {run_cmd_commands}"

        cloud_init_volume[cloud_init_volume_type]["userData"] = cloud_init_user_data

        return template_spec

    def update_vm_cpu_configuration(self, template_spec):
        # cpu settings
        if self.cpu_flags:
            template_spec.setdefault("domain", {})["cpu"] = self.cpu_flags

        if self.cpu_limits:
            template_spec.setdefault("domain", {}).setdefault("resources", {}).setdefault("limits", {})
            template_spec["domain"]["resources"]["limits"].update({"cpu": self.cpu_limits})

        if self.cpu_requests:
            template_spec.setdefault("domain", {}).setdefault("resources", {}).setdefault("requests", {})
            template_spec["domain"]["resources"]["requests"].update({"cpu": self.cpu_requests})

        if self.cpu_cores:
            template_spec.setdefault("domain", {}).setdefault("cpu", {})["cores"] = self.cpu_cores

        # Faster VMI start time
        if (
            OS_FLAVOR_WINDOWS in self.os_flavor
            and not self.cpu_threads
            and not self.vm_instance_type
            and not self.vm_instance_type_infer
        ):
            self.cpu_threads = Images.Windows.DEFAULT_CPU_THREADS

        if self.cpu_threads:
            template_spec.setdefault("domain", {}).setdefault("cpu", {})["threads"] = self.cpu_threads

        if self.cpu_sockets:
            template_spec.setdefault("domain", {}).setdefault("cpu", {})["sockets"] = self.cpu_sockets

        if self.cpu_placement:
            template_spec.setdefault("domain", {}).setdefault("cpu", {})["dedicatedCpuPlacement"] = True

        if self.isolate_emulator_thread:
            # This setting has to be specified in a combination with
            # cpu_placement = True. Only valid if dedicatedCpuPlacement is True.
            template_spec.setdefault("domain", {}).setdefault("cpu", {})["isolateEmulatorThread"] = True

        if self.cpu_model:
            template_spec.setdefault("domain", {}).setdefault("cpu", {})["model"] = self.cpu_model

        if self.cpu_max_sockets:
            template_spec.setdefault("domain", {}).setdefault("cpu", {})["maxSockets"] = self.cpu_max_sockets

        return template_spec

    def update_vm_storage_configuration(self, template_spec):
        # image must be set before DV in order to boot from it.
        if self.image:
            template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("disks", []).append({
                "disk": {"bus": self.disk_type},
                "name": "containerdisk",
            })
            template_spec.setdefault("volumes", []).append({
                "name": "containerdisk",
                "containerDisk": {"image": self.image},
            })

        # DV/PVC info may be taken from self.data_volume_template, self.data_volume or self.pvc
        # Needed only for VMs which are not created from common templates
        if (self.data_volume_template or self.data_volume or self.pvc) and not self.is_vm_from_template:
            access_mode = self.get_storage_configuration()

            # For storage class that is not ReadWriteMany - evictionStrategy should be set as "None" in the VM
            # (Except when evictionStrategy is explicitly set)
            if not self.eviction_strategy and DataVolume.AccessMode.RWX not in access_mode:
                LOGGER.info(
                    f"{EVICTIONSTRATEGY} explicitly set to 'None' in VM because data volume access mode is not RWX"
                )
                template_spec[EVICTIONSTRATEGY] = "None"
            if self.pvc:
                pvc_disk_name = f"{self.pvc.name}-pvc-disk"
                template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("disks", []).append({
                    "disk": {"bus": self.disk_type},
                    "name": pvc_disk_name,
                })
                template_spec.setdefault("volumes", []).append({
                    "name": pvc_disk_name,
                    "persistentVolumeClaim": {"claimName": self.pvc.name},
                })
            # self.data_volume / self.data_volume_template
            else:
                data_volume_name = (
                    self.data_volume.name if self.data_volume else self.data_volume_template["metadata"]["name"]
                )
                template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("disks", []).append({
                    "disk": {"bus": self.disk_type},
                    "name": DV_DISK,
                })
                template_spec.setdefault("volumes", []).append({
                    "name": DV_DISK,
                    "dataVolume": {"name": data_volume_name},
                })

            if self.data_volume_template:
                self.res["spec"].setdefault("dataVolumeTemplates", []).append(self.data_volume_template)

        return template_spec

    def update_vm_secret_configuration(self, template_spec):
        if self.attached_secret:
            volume_name = self.attached_secret["volume_name"]
            template_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("disks", []).append({
                "disk": {},
                "name": volume_name,
                "serial": self.attached_secret["serial"],
            })
            template_spec.setdefault("volumes", []).append({
                "name": volume_name,
                "secret": {"secretName": self.attached_secret["secret_name"]},
            })

        return template_spec

    def update_vm_ssh_secret_configuration(self, template_spec):
        template_spec.setdefault("accessCredentials", []).append({
            "sshPublicKey": {
                "source": {"secret": {"secretName": self.ssh_secret.name}},
                "propagationMethod": {"noCloud": {}},
            }
        })
        return template_spec

    def custom_service_enable(
        self,
        service_name,
        port,
        service_type=None,
        service_ip=None,
        ip_family_policy=None,
        ip_families=None,
    ):
        """
        service_type is set with K8S default service type (ClusterIP)
        service_ip - relevant for node port; default will be set to vm node IP
        ip_families - list of IP families to be supported in the service (IPv4/6 or both)
        ip_family_policy - SingleStack, RequireDualStack or PreferDualStack
        To use the service: custom_service.service_ip() and custom_service.service_port
        """
        self.custom_service = ServiceForVirtualMachineForTests(
            name=f"{service_name}-{self.name}"[:63],
            namespace=self.namespace,
            vm=self,
            port=port,
            service_type=service_type,
            target_ip=service_ip,
            ip_family_policy=ip_family_policy,
            ip_families=ip_families,
        )
        self.custom_service.create(wait=True)

    def get_storage_configuration(self):
        def _sc_name_for_storage_api():
            spec_storage = self.data_volume_template["spec"].get("storage", {}).get("storageClassName")
            if spec_storage:
                return spec_storage
            if self.vm_preference:
                sc_name = self.vm_preference.instance.spec.get("volumes", {}).get("preferredStorageClassName")
                if sc_name:
                    return sc_name
            else:
                return get_default_storage_class().name

        api_name = "pvc" if self.data_volume_template and self.data_volume_template["spec"].get("pvc") else "storage"
        return (
            self.data_volume.pvc.instance.spec.accessModes
            if self.data_volume
            else self.pvc.instance.spec.accessModes
            if self.pvc
            else self.data_volume_template["spec"][api_name].get("accessModes")
            or StorageProfile(name=_sc_name_for_storage_api()).instance.status["claimPropertySets"][0]["accessModes"]
        )

    @property
    def virtctl_port_forward_cmd(self):
        return f"{VIRTCTL} port-forward --stdio=true vm/{self.name}/{self.namespace} {SSH_PORT_22}"

    @property
    def login_params(self):
        os_login_param = py_config.get("os_login_param", {}).get(self.os_flavor, {})
        if not os_login_param:
            LOGGER.warning(f"`os_login_param` not defined for {self.os_flavor}")

        return os_login_param

    def set_login_params(self):
        _login_params = self.login_params

        if not (self.username and self.password):
            if _login_params:
                self.username = _login_params.get("username")
                self.password = _login_params.get("password")
                return

            # Do not modify the defaults to OS like Windows where the password is already defined in the image
            if not any(flavor in self.os_flavor for flavor in FLAVORS_EXCLUDED_FROM_CLOUD_INIT):
                if self.exists:
                    self.username, self.password = username_password_from_cloud_init(
                        vm_volumes=self.instance.spec.template.spec.volumes
                    )
                    if not self.username or not self.password:
                        LOGGER.warning("Could not find credentials in cloud-init")

                else:
                    LOGGER.info("Setting random username and password")
                    self.username = secrets.token_urlsafe(nbytes=12)
                    self.password = secrets.token_urlsafe(nbytes=12)

    @property
    def ssh_exec(self):
        # In order to use this property VM should be created with ssh=True
        self.username = self.username or self.login_params["username"]
        self.password = self.password or self.login_params["password"]

        LOGGER.info(f"SSH command: ssh -o 'ProxyCommand={self.virtctl_port_forward_cmd}' {self.username}@{self.name}")
        host = Host(hostname=self.name)
        # For SSH using a key, the public key needs to reside on the server.
        # As the tests use a given set of credentials, this cannot be done in Windows/Cirros.
        if any(flavor in self.os_flavor for flavor in FLAVORS_EXCLUDED_FROM_CLOUD_INIT):
            host_user = user.User(name=self.username, password=self.password)
        else:
            host_user = user.UserWithPKey(name=self.username, private_key=os.environ[CNV_VM_SSH_KEY_PATH])
        host.executor_user = host_user
        host.executor_factory = ssh.RemoteExecutorFactory(
            sock=self.virtctl_port_forward_cmd,
        )
        return host

    def wait_for_specific_status(self, status, timeout=TIMEOUT_3MIN, sleep=TIMEOUT_5SEC):
        LOGGER.info(f"Wait for {self.kind} {self.name} status to be {status}")
        samples = TimeoutSampler(wait_timeout=timeout, sleep=sleep, func=lambda: self.printable_status)
        try:
            for sample in samples:
                if sample == status:
                    return
        except TimeoutExpiredError:
            LOGGER.error(f"Status of {self.kind} {self.name} is {status}")
            raise

    @property
    def privileged_vmi(self):
        return VirtualMachineInstance(client=get_client(), name=self.name, namespace=self.namespace)

    def wait_for_agent_connected(self, timeout: int = TIMEOUT_5MIN):
        self.vmi.wait_for_condition(
            condition=VirtualMachineInstance.Condition.Type.AGENT_CONNECTED,
            status=VirtualMachineInstance.Condition.Status.TRUE,
            timeout=timeout,
        )


class VirtualMachineForTestsFromTemplate(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client,
        eviction_strategy=None,
        labels=None,
        data_source=None,
        data_volume_template=None,
        existing_data_volume=None,
        networks=None,
        interfaces=None,
        ssh=True,
        vm_dict=None,
        cpu_cores=None,
        cpu_threads=None,
        cpu_sockets=None,
        cpu_model=None,
        cpu_flags=None,
        cpu_placement=False,
        cpu_max_sockets=None,
        isolate_emulator_thread=False,
        memory_requests=None,
        memory_guest=None,
        memory_max_guest=None,
        network_model=None,
        network_multiqueue=None,
        cloud_init_data=None,
        node_selector=None,
        attached_secret=None,
        termination_grace_period=180,
        diskless_vm=False,
        run_strategy=VirtualMachine.RunStrategy.HALTED,
        disk_options_vm=None,
        smm_enabled=None,
        pvspinlock_enabled=None,
        efi_params=None,
        macs=None,
        interfaces_types=None,
        host_device_name=None,
        gpu_name=None,
        iothreads_policy=None,
        dedicated_iothread=False,
        cloned_dv_size=None,
        vhostmd=False,
        machine_type=None,
        teardown=True,
        use_full_storage_api=False,
        dry_run=None,
        template_params=None,
        template_object=None,
        non_existing_pvc=False,
        data_volume_template_from_vm_spec=False,
        sno_cluster=False,
        tpm_params=None,
        additional_labels=None,
        vm_affinity=None,
    ):
        """
        VM creation using common templates.

        Args:
            eviction_strategy (str, optional): valid options("None", "LiveMigrate", "LiveMigrateIfPossible", "External")
                Default value None here is same as Null and not the string "None" which is one of the valid options
            data_source (obj `DataSource`): DS object points to a golden image PVC.
                VM's disk will be cloned from the PVC.
            data_volume_template (dict): dataVolumeTemplates dict to replace template's default dataVolumeTemplates
            existing_data_volume (obj `DataVolume`): An existing DV object that will be used as the VM's volume. Cloning
                will not be done and the template's dataVolumeTemplates will be removed.
            use_full_storage_api (bool, default=False): Target PVC storage params are not explicitly set if True.
                IF False, storage api will be used but target PVC storage name will be taken from self.dv. This is done
                to avoid modifying cluster default SC.
            dry_run (str, default=None): If "All", the VM will be created using the dry_run flag
            template_params (dict, optional): dict with template parameters as keys and values
            template_object (Template, optional): Template object to create the VM from
            non_existing_pvc(bool, default=False): If True, referenced PVC in DataSource is missing
            data_volume_template_from_vm_spec (bool, default=False): Use (and don't manipulate) VM's DataVolumeTemplates
            vm_affinity (dict, optional): Affinity rules for scheduling the VM on specific nodes
        Returns:
            obj `VirtualMachine`: VM resource
        """
        # Must be set here to set VM flavor (used to set username and password)
        self.template_labels = labels
        self.template_object = template_object
        self.os_flavor = self._extract_os_from_template()

        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            networks=networks,
            interfaces=interfaces,
            ssh=ssh,
            network_model=network_model,
            network_multiqueue=network_multiqueue,
            cpu_cores=cpu_cores,
            cpu_threads=cpu_threads,
            cpu_model=cpu_model,
            cpu_sockets=cpu_sockets,
            cpu_flags=cpu_flags,
            cpu_placement=cpu_placement,
            cpu_max_sockets=cpu_max_sockets,
            isolate_emulator_thread=isolate_emulator_thread,
            memory_requests=memory_requests,
            memory_guest=memory_guest,
            memory_max_guest=memory_max_guest,
            cloud_init_data=cloud_init_data,
            node_selector=node_selector,
            attached_secret=attached_secret,
            data_volume_template=data_volume_template,
            diskless_vm=diskless_vm,
            run_strategy=run_strategy,
            disk_io_options=disk_options_vm,
            smm_enabled=smm_enabled,
            pvspinlock_enabled=pvspinlock_enabled,
            efi_params=efi_params,
            macs=macs,
            interfaces_types=interfaces_types,
            host_device_name=host_device_name,
            gpu_name=gpu_name,
            iothreads_policy=iothreads_policy,
            dedicated_iothread=dedicated_iothread,
            vhostmd=vhostmd,
            machine_type=machine_type,
            teardown=teardown,
            dry_run=dry_run,
            tpm_params=tpm_params,
            eviction_strategy=eviction_strategy,
            additional_labels=additional_labels,
            vm_affinity=vm_affinity,
            os_flavor=self.os_flavor,
        )
        self.data_source = data_source
        self.data_volume_template = data_volume_template
        self.existing_data_volume = existing_data_volume
        self.vm_dict = vm_dict
        self.cpu_threads = cpu_threads
        self.node_selector = node_selector
        self.termination_grace_period = termination_grace_period
        self.cloud_init_data = cloud_init_data
        self.cloned_dv_size = cloned_dv_size
        self.use_full_storage_api = use_full_storage_api
        self.access_modes = None  # required for evictionStrategy policy
        self.template_params = template_params
        self.non_existing_pvc = non_existing_pvc
        self.data_volume_template_from_vm_spec = data_volume_template_from_vm_spec
        self.eviction_strategy = eviction_strategy
        self.sno_cluster = sno_cluster
        self.vm_affinity = vm_affinity

    def to_dict(self):
        self.set_login_params()
        self.body = self.process_template()
        super().to_dict()

        if self.vm_dict:
            merge_dicts(source_dict=self.vm_dict, target_dict=self.res)

        spec = self.res["spec"]["template"]["spec"]

        # terminationGracePeriodSeconds for Windows is set to 1hr; this may affect VMI deletion
        # If termination_grace_period is not provided, terminationGracePeriodSeconds will be set to 180
        spec["terminationGracePeriodSeconds"] = self.termination_grace_period

        # Nothing to do if source PVC (referenced in DataSource) does not exist
        if self.non_existing_pvc:
            LOGGER.info("Referenced PVC does not exist")
        # Nothing to do if consuming dataVolumeTemplates already set in the VM spec
        elif self.data_volume_template_from_vm_spec:
            LOGGER.info("VM spec includes DataVolume, which will be used for storing the VM image.")
            self.access_modes = self.res["spec"]["dataVolumeTemplates"][0]["spec"]["storage"].get("accessModes", [])
        # For diskless_vm, volumes are removed so dataVolumeTemplates (referencing volumes) should be removed as well
        elif self.diskless_vm:
            del self.res["spec"]["dataVolumeTemplates"]
        # Existing DV will be used as the VM's DV; dataVolumeTemplates is not needed
        elif self.existing_data_volume:
            del self.res["spec"]["dataVolumeTemplates"]
            spec = self._update_vm_storage_config(spec=spec, name=self.existing_data_volume.name)
            self.access_modes = self.existing_data_volume.pvc.instance.spec.accessModes
        # Template's dataVolumeTemplates will be replaced with self.data_volume_template
        elif self.data_volume_template:
            self.res["spec"]["dataVolumeTemplates"] = [self.data_volume_template]
            spec = self._update_vm_storage_config(spec=spec, name=self.data_volume_template["metadata"]["name"])
            self.access_modes = self.data_volume_template["spec"].get("pvc", {}).get(
                "accessModes", []
            ) or self.data_volume_template["spec"].get("storage", {}).get("accessModes", [])
        # Otherwise clone volume referenced in self.data_source
        else:
            # If storage params are not in source.spec (for e.g. source is VolumeSnapshot),
            # params will be taken from cluster configured default storage
            volume_source_spec = self.data_source.source.instance.spec
            data_source_status = self.data_source.instance.status
            storage_spec = self.res["spec"]["dataVolumeTemplates"][0]["spec"]["storage"]
            self.access_modes = volume_source_spec.accessModes
            # dataVolumeTemplates needs to be updated with the needed storage size,
            # if the size of the golden_image is more than the Template's default storage size.
            # else use the source DV storage size.
            storage_spec.setdefault("resources", {}).setdefault("requests", {})["storage"] = (
                self.cloned_dv_size
                or volume_source_spec.get("resources", {}).get("requests", {}).get("storage")
                or data_source_status.get("restoreSize")
            )
            if not self.use_full_storage_api:
                storage_spec["storageClassName"] = volume_source_spec.storageClassName

        # For storage class that is not ReadWriteMany- evictionStrategy should be set as "None" in the VM
        # (Except when evictionStrategy is explicitly set)
        # To apply this logic, self.access_modes should be available.
        if not self.sno_cluster and (not self.eviction_strategy and not (self.diskless_vm or self.non_existing_pvc)):
            if not self.access_modes:
                self.access_modes = get_default_storage_class().storage_profile.first_claim_property_set_access_modes()
            if DataVolume.AccessMode.RWX not in self.access_modes:
                spec[EVICTIONSTRATEGY] = "None"

    def _update_vm_storage_config(self, spec, name):
        # volume name should be updated
        for volume in spec["volumes"]:
            if "dataVolume" in volume:
                volume["dataVolume"]["name"] = name

        return spec

    def _extract_os_from_template(self):
        os_name = (
            [label for label in self.template_labels if Template.Labels.OS in label][0]
            if self.template_labels is not None
            else self.template_object.instance.objects[0].spec.template.metadata.annotations[
                f"{self.ApiGroup.VM_KUBEVIRT_IO}/os"
            ]
        )
        # Extract only from strings such as: "fedora37", "os.template.kubevirt.io/fedora37" will return "fedora"
        return re.search(r"(.*/)?(?P<os>[a-z]+)", os_name)["os"]

    def process_template(self):
        # Common templates use golden image clone as a default for VM DV
        # DATA_SOURCE_NAME - to support minor releases, this value needs to be passed. Currently
        # the templates only have one name per major OS.
        # DATA_SOURCE_NAMESPACE parameters is not passed so the default value will be used.
        # If existing DV or custom dataVolumeTemplates are used, use mock source PVC name and namespace
        template_kwargs = {
            "NAME": self.name,
            DATA_SOURCE_NAME: self.data_source.name if self.data_source else "mock-data-source",
            DATA_SOURCE_NAMESPACE: self.data_source.namespace if self.data_source else "mock-data-source-ns",
        }

        template_object = self.template_object or get_template_by_labels(
            admin_client=self.client, template_labels=self.template_labels
        )

        # Set password for non-Windows VMs; for Windows VM, the password is already set in the image
        if OS_FLAVOR_WINDOWS not in self.os_flavor:
            username, _ = username_password_from_cloud_init(
                vm_volumes=template_object.instance.objects[0].spec.template.spec.volumes
            )

            self.username = username
            template_kwargs["CLOUD_USER_PASSWORD"] = self.password

        if self.template_params:
            template_kwargs.update(self.template_params)

        resources_list = template_object.process(client=get_client(), **template_kwargs)
        for resource in resources_list:
            if resource["kind"] == VirtualMachine.kind and resource["metadata"]["name"] == self.name:
                return resource

        raise ValueError(f"Template not found for {self.name}")


def vm_console_run_commands(
    vm: VirtualMachineForTests | BaseVirtualMachine,
    commands: list[str],
    timeout: int = TIMEOUT_1MIN,
    return_code_validation: bool = True,
) -> dict[str, list[str]]:
    """
    Run a list of commands inside VM and (if verify_commands_output) check all commands return 0.
    If return code other than 0 then it will break execution and raise exception.

    Args:
        vm (obj): VirtualMachine
        commands (list): List of commands
        timeout (int): Time to wait for the command output
        return_code_validation (bool): Check commands return 0

    Returns:
        Dict of the commands outputs, where the key is the command and the value is the output as a list of lines.
    """
    output = {}
    # Source: https://www.tutorialspoint.com/how-can-i-remove-the-ansi-escape-sequences-from-a-string-in-python
    ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
    prompt = r"\$ "
    with Console(vm=vm, prompt=prompt) as vmc:
        for command in commands:
            LOGGER.info(f"Execute {command} on {vm.name}")
            try:
                vmc.sendline(command)
                vmc.expect(prompt)
                output[command] = ansi_escape.sub("", vmc.before).replace("\r", "").split("\n")
                if return_code_validation:
                    vmc.sendline("echo rc==$?==")  # This construction rc==$?== is unique. Return code validation
                    vmc.expect("rc==0==", timeout=timeout)  # Expected return code is 0
                    vmc.expect(prompt)
            except pexpect.exceptions.TIMEOUT:
                raise CommandExecFailed(str(output.get(command, [])), err=f"timeout: {vmc.before}")
            except pexpect.exceptions.EOF:
                raise CommandExecFailed(str(output.get(command, [])), err=f"EOF: {vmc.before}")
            except Exception as e:
                e.add_note(vmc.before)
                raise CommandExecFailed(str(output.get(command, [])), err=f"Error: {e}")
    return output


def fedora_vm_body(name: str) -> dict[str, Any]:
    pull_secret = utilities.infra.generate_openshift_pull_secret_file()

    # Make sure we can find the file even if utilities was installed via pip.
    yaml_file = os.path.abspath("utilities/manifests/vm-fedora.yaml")

    with open(yaml_file) as fd:
        data = fd.read()

    image = Images.Fedora.FEDORA_CONTAINER_IMAGE
    image_info = get_oc_image_info(
        image=image,
        pull_secret=pull_secret,
        architecture=utilities.infra.get_nodes_cpu_architecture(
            nodes=list(Node.get(dyn_client=get_client())),
        ),
    )
    image_digest = image_info["digest"]
    return generate_dict_from_yaml_template(
        stream=io.StringIO(data),
        name=name,
        image=f"{image}@{image_digest}",
    )


def kubernetes_taint_exists(node):
    taints = node.instance.spec.taints
    if taints:
        return any(taint.key == K8S_TAINT and taint.effect == NO_SCHEDULE for taint in taints)


class ServiceForVirtualMachineForTests(Service):
    def __init__(
        self,
        name,
        namespace,
        vm,
        port,
        service_type=Service.Type.CLUSTER_IP,
        target_ip=None,
        ip_family_policy=IP_FAMILY_POLICY_PREFER_DUAL_STACK,
        ip_families=None,
        teardown=True,
        dry_run=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            teardown=teardown,
            dry_run=dry_run,
        )
        self.vm = vm
        self.vmi = vm.vmi
        self.port = port
        self.service_type = service_type
        self.target_ip = target_ip
        self.ip_family_policy = ip_family_policy
        self.ip_families = ip_families

    def to_dict(self):
        super().to_dict()
        self.res["spec"] = {
            "ports": [{"port": self.port, "protocol": "TCP"}],
            "selector": {"kubevirt.io/domain": self.vm.name},
            "sessionAffinity": "None",
            "type": self.service_type,
        }

        self.res["spec"]["ipFamilyPolicy"] = self.ip_family_policy
        if self.ip_families:
            self.res["spec"]["ipFamilies"] = self.ip_families

    def service_ip(self, ip_family=None):
        if self.service_type == Service.Type.CLUSTER_IP:
            if ip_family:
                cluster_ips = [
                    cluster_ip
                    for cluster_ip in self.vm.custom_service.instance.spec.clusterIPs
                    if str(ipaddress.ip_address(cluster_ip).version) in ip_family
                ]
                assert cluster_ips, f"No {ip_family} addresses in service {self.vm.custom_service.name}"
                return cluster_ips[0]

            return self.instance.spec.clusterIP

        vm_node = Node(
            client=get_client(),
            name=self.vmi.instance.status.nodeName,
        )
        if self.service_type == Service.Type.NODE_PORT:
            if ip_family:
                internal_ips = [
                    internal_ip
                    for internal_ip in vm_node.instance.status.addresses
                    if str(ipaddress.ip_address(internal_ip).version) in ip_family
                ]
                assert internal_ips, f"No {ip_family} addresses in node {vm_node.name}"
                return internal_ips[0]

            return self.target_ip or vm_node.internal_ip

    @property
    def service_port(self):
        if self.service_type == Service.Type.CLUSTER_IP:
            return self.instance.attributes.spec.ports[0]["port"]

        if self.service_type == Service.Type.NODE_PORT:
            node_port = utilities.infra.camelcase_to_mixedcase(camelcase_str=self.service_type)
            return self.instance.attributes.spec.ports[0][node_port]


def wait_for_ssh_connectivity(
    vm: VirtualMachineForTests, timeout: int = TIMEOUT_2MIN, tcp_timeout: int = TIMEOUT_1MIN
) -> None:
    LOGGER.info(f"Wait for {vm.name} SSH connectivity.")

    for sample in TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=vm.ssh_exec.run_command,
        command=["exit"],
        tcp_timeout=tcp_timeout,
    ):
        if sample:
            return


def wait_for_console(vm):
    with Console(vm=vm, timeout=TIMEOUT_25MIN):
        LOGGER.info(f"Successfully connected to {vm.name} console")


def generate_dict_from_yaml_template(stream, **kwargs):
    """
    Generate YAML from yaml template.

    Args:
        stream (io.StringIO): Yaml file content.

    Returns:
        dict: Generated from template file

    Raises:
        MissingTemplateVariables: If not all template variables exists
    """
    data = stream.read()
    # Find all template variables
    template_vars = [i.split()[1] for i in re.findall(r"{{ .* }}", data)]
    for var in template_vars:
        if var not in kwargs.keys():
            raise MissingTemplateVariables(var=var, template=data)
    template = jinja2.Template(data)
    out = template.render(**kwargs)
    return yaml.safe_load(out)


class MissingTemplateVariables(Exception):
    def __init__(self, var, template):
        self.var = var
        self.template = template

    def __str__(self):
        return f"Missing variables {self.var} for template {self.template}"


def wait_for_windows_vm(vm, version, timeout=TIMEOUT_25MIN):
    """
    Samples Windows VM; wait for it to complete the boot process.
    """

    LOGGER.info(f"Windows VM {vm.name} booting up, will attempt to access it up to {round(timeout / 60)} minutes.")

    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=15,
        func=vm.ssh_exec.run_command,
        command=shlex.split("wmic os get Caption /value"),
    )
    for sample in sampler:
        if version in str(sample):
            return True


# TODO: Remove once bug 1945703 is fixed
def get_guest_os_info(vmi):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_6MIN,
        sleep=5,
        func=lambda: vmi.instance.status.guestOSInfo,
    )

    try:
        for sample in sampler:
            if sample.get("id"):
                return dict(sample)
    except TimeoutExpiredError:
        LOGGER.error("VMI doesn't have guest agent data")
        raise


def get_windows_os_dict(windows_version: str) -> dict[str, Any]:
    """
    Returns a dictionary of Windows os information from the system_windows_os_matrix in py_config.

    Args:
        windows_version: The version of windows to get the os information for.

    Returns:
        dict: OS dictionary for the version, or empty dict if matrix is missing

    Raises:
        KeyError: If matrix exists but version is not found
    """
    if system_windows_os_matrix := py_config.get("system_windows_os_matrix"):
        windows_os_dict = [
            os_dict
            for win_os in system_windows_os_matrix
            for os_name, os_dict in win_os.items()
            if os_name == windows_version
        ]
        if windows_os_dict:
            return windows_os_dict[0]
        raise KeyError(f"Failed to extract {windows_version} from system_windows_os_matrix")

    return {}


def get_rhel_os_dict(rhel_version: str) -> dict[str, Any]:
    """
    Returns a dictionary of RHEL os information from the system_rhel_os_matrix in py_config.

    Args:
        rhel_version: The version of RHEL to get the os information for.

    Returns:
        dict: OS dictionary for the version, or empty dict if matrix is missing

    Raises:
        KeyError: If matrix exists but version is not found
    """
    if py_system_rhel_os_matrix := py_config.get("system_rhel_os_matrix"):
        rhel_os_dict = [
            os_dict
            for rhel_os in py_system_rhel_os_matrix
            for os_name, os_dict in rhel_os.items()
            if os_name == rhel_version
        ]
        if rhel_os_dict:
            return rhel_os_dict[0]
        raise KeyError(f"Failed to extract {rhel_version} from system_rhel_os_matrix")

    return {}


def assert_vm_not_error_status(vm: VirtualMachineForTests, timeout: int = TIMEOUT_5SEC) -> None:
    try:
        for status in TimeoutSampler(
            wait_timeout=timeout, sleep=TIMEOUT_1SEC, func=lambda: vm.instance.get("status", {})
        ):
            if status:
                printable_status = status.get("printableStatus")
                error_list = VM_ERROR_STATUSES.copy()
                if vm.instance.spec.template.spec.domain.devices.gpus:
                    error_list.remove(VirtualMachine.Status.ERROR_UNSCHEDULABLE)
                assert printable_status not in error_list, (
                    f"VM {vm.name} error printable status: {printable_status}\nVM status:\n{status}"
                )
                return
    except TimeoutExpiredError:
        LOGGER.error(f"VM {vm.name} status did not populate within {timeout}")
        raise


def wait_for_running_vm(
    vm: VirtualMachineForTests,
    wait_until_running_timeout: int = TIMEOUT_4MIN,
    wait_for_interfaces: bool = True,
    check_ssh_connectivity: bool = True,
    ssh_timeout: int = TIMEOUT_2MIN,
) -> None:
    """
    Wait for the VMI to be in Running state.

    Args:
        vm (VirtualMachine): VM object.
        wait_until_running_timeout (int): how much time to wait for VMI to reach Running state
        wait_for_interfaces (bool): Is waiting for VM's interfaces mandatory for declaring VM as running.
        check_ssh_connectivity (bool): Enable SSh service in the VM.
        ssh_timeout (int): how much time to wait for SSH connectivity

    Raises:
        TimeoutExpiredError: After timeout is reached for any of the steps
    """
    assert_vm_not_error_status(vm=vm)
    try:
        vm.vmi.wait_until_running(timeout=wait_until_running_timeout)

        if wait_for_interfaces:
            wait_for_vm_interfaces(vmi=vm.vmi)

        if check_ssh_connectivity:
            wait_for_ssh_connectivity(vm=vm, timeout=ssh_timeout)
    except TimeoutExpiredError:
        collect_vnc_screenshot_for_vms(vm_name=vm.name, vm_namespace=vm.namespace)
        raise


def running_vm(
    vm: VirtualMachineForTests,
    wait_for_interfaces=True,
    check_ssh_connectivity=True,
    ssh_timeout=TIMEOUT_2MIN,
    wait_for_cloud_init=False,
    dv_wait_timeout=TIMEOUT_30MIN,
):
    """
    Wait for the VMI to be in Running state.

    Args:
        vm (VirtualMachine): VM object.
        wait_for_interfaces (bool): Is waiting for VM's interfaces mandatory for declaring VM as running.
        check_ssh_connectivity (bool): Enable SSh service in the VM.
        ssh_timeout (int): how much time to wait for SSH connectivity
        wait_for_cloud_init (bool): Is waiting for cloud-init required.
        dv_wait_timeout (int): dv success timeout.

    Returns:
        VirtualMachine: VM object.
    """

    def _wait_for_dv_success(_vm, _vm_dv_volumes_names_list, _dv_wait_timeout):
        """
        In case VM is not starting because it's DV is not ready, wait for DV to be succeeded.
        """
        assert_vm_not_error_status(vm=vm)

        LOGGER.info(f"VM {_vm.name} status before dv check: {_vm.printable_status}")
        LOGGER.info(f"Volume(s) in VM spec: {_vm_dv_volumes_names_list} ")
        for dv_name in _vm_dv_volumes_names_list:
            DataVolume(name=dv_name, namespace=_vm.namespace).wait_for_dv_success(timeout=_dv_wait_timeout)

    # To support all use cases of: 'runStrategy', container/VM from template, VM started outside this function
    allowed_vm_start_exceptions_list = [
        "Always does not support manual start requests",
        "VM is already running",
        "Internal error occurred: unable to complete request: stop/start already underway",
    ]
    vm_dv_volumes_names_list = [
        volume.dataVolume.name for volume in vm.instance.spec.template.spec.volumes if "dataVolume" in volume.keys()
    ]

    try:
        vm.start()
    except ApiException as exception:
        if any([message in exception.body for message in allowed_vm_start_exceptions_list]):
            LOGGER.warning(f"VM {vm.name} is already running; will not be started.")
        else:
            raise

    if vm_dv_volumes_names_list:
        _wait_for_dv_success(
            _vm=vm,
            _vm_dv_volumes_names_list=vm_dv_volumes_names_list,
            _dv_wait_timeout=dv_wait_timeout,
        )
    wait_for_running_vm(
        vm=vm,
        wait_for_interfaces=wait_for_interfaces,
        check_ssh_connectivity=check_ssh_connectivity,
        ssh_timeout=ssh_timeout,
    )
    if wait_for_cloud_init:
        wait_for_cloud_init_complete(vm=vm)
    return vm


def wait_for_cloud_init_complete(vm, timeout=TIMEOUT_4MIN):
    cloud_init_status = "cloud-init status"
    for sample in TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=vm.ssh_exec.run_command,
        command=shlex.split(cloud_init_status),
    ):
        # ignore Exit Code 2 (recoverable errors)
        if sample[0] in [0, 2] and "done" in sample[1]:
            return True


def migrate_vm_and_verify(
    vm: VirtualMachineForTests | BaseVirtualMachine,
    client: DynamicClient | None = None,
    timeout: int = TIMEOUT_12MIN,
    wait_for_interfaces: bool = True,
    check_ssh_connectivity: bool = False,
    wait_for_migration_success: bool = True,
) -> VirtualMachineInstanceMigration | None:
    """
    Create a migration instance. You may choose to wait for migration
    success or not.

    Args:
        vm (VirtualMachine): VM to be migrated.
        client (DynamicClient, default=None): Client to use for migration.
        timeout (int, default=12 minutes): Maximum time to wait for the migration to finish.
        wait_for_interfaces (bool, default=True): Wait for VM network interfaces after migration completes.
        check_ssh_connectivity (bool, default=False): Verify SSH connectivity to the VM after migration completes.
        wait_for_migration_success (bool, default=True):
            True = Full teardown will be applied.
            False = No teardown (responsibility on the programmer), and no
                    wait for migration process to finish.

    Returns:
        VirtualMachineInstanceMigration: If wait_for_migration_success == false, else returns None
    """
    node_before = vm.vmi.node

    LOGGER.info(f"VMI {vm.vmi.name} is running on {node_before.name} before migration.")
    with VirtualMachineInstanceMigration(
        name=vm.name,
        client=client,
        namespace=vm.namespace,
        vmi_name=vm.vmi.name,
        teardown=wait_for_migration_success,
    ) as migration:
        if not wait_for_migration_success:
            return migration
        wait_for_migration_finished(namespace=vm.namespace, migration=migration, timeout=timeout)

    verify_vm_migrated(
        vm=vm,
        node_before=node_before,
        wait_for_interfaces=wait_for_interfaces,
        check_ssh_connectivity=check_ssh_connectivity,
    )
    return None


def wait_for_migration_finished(namespace, migration, timeout=TIMEOUT_12MIN):
    sleep = TIMEOUT_10SEC
    samples = TimeoutSampler(wait_timeout=timeout, sleep=sleep, func=lambda: migration.instance.status.phase)
    counter = 0
    sample = None
    try:
        for sample in samples:
            if sample == migration.Status.SUCCEEDED:
                break
            elif sample == "Scheduling":
                counter += 1
                # If migration stuck in Scheduling state for more than 4 minutes - most likely it will be failed
                # Need to collect data before 5 min timeout reached and target POD is removed
                if counter >= TIMEOUT_4MIN / sleep:
                    # Get status/events for PODs in non-running or failed state
                    for pod in utilities.infra.get_pod_by_name_prefix(
                        dyn_client=get_client(),
                        pod_prefix=VIRT_LAUNCHER,
                        namespace=namespace,
                        get_all=True,
                    ):
                        if pod.status not in (Pod.Status.RUNNING, Pod.Status.COMPLETED, Pod.Status.SUCCEEDED):
                            pod_events = [
                                event["raw_object"]["message"]
                                for event in pod.events(timeout=TIMEOUT_5SEC, field_selector="type==Warning")
                            ]
                            LOGGER.error(
                                f"POD Conditions:\n {pod.instance.status.conditions[0]}\n"
                                f"POD Events:\n {', '.join(pod_events)}"
                            )
                    raise TimeoutExpiredError(
                        f"VMIM {migration.name} stuck in Scheduling state and probably will be failed"
                    )
    except TimeoutExpiredError:
        if sample:
            LOGGER.error(f"Status of VMIM {migration.name} is {sample}")
        raise


def verify_vm_migrated(
    vm,
    node_before,
    wait_for_interfaces=True,
    check_ssh_connectivity=False,
):
    vmi_name = vm.vmi.name
    vmi_node_name = vm.vmi.node.name
    assert vmi_node_name != node_before.name, f"VMI: {vmi_name} still running on the same node: {vmi_node_name}"

    assert vm.vmi.instance.status.migrationState.completed, (
        f"VMI {vmi_name} migration state is: {vm.vmi.instance.status.migrationState}"
    )
    if wait_for_interfaces:
        wait_for_vm_interfaces(vmi=vm.vmi)

    if check_ssh_connectivity:
        wait_for_ssh_connectivity(vm=vm)


def vm_cloud_init_volume(vm_spec):
    cloud_init_volume = [vol for vol in vm_spec.setdefault("volumes", []) if vol["name"] == CLOUD_INIT_DISK_NAME]

    if cloud_init_volume:
        return cloud_init_volume[0]

    # If cloud init volume needs to be added
    vm_spec["volumes"].append({"name": CLOUD_INIT_DISK_NAME})
    return vm_spec["volumes"][-1]


def vm_cloud_init_disk(vm_spec):
    disks_spec = vm_spec.setdefault("domain", {}).setdefault("devices", {}).setdefault("disks", [])

    if not [disk for disk in disks_spec if disk["name"] == CLOUD_INIT_DISK_NAME]:
        disks_spec.append({"disk": {"bus": "virtio"}, "name": CLOUD_INIT_DISK_NAME})

    return vm_spec


def prepare_cloud_init_user_data(section, data):
    """
    Generates userData dict to be used with cloud init and add data under the required section.

    section (str): key name under userData
    data: value to be added under "section" key
    """
    cloud_init_data = defaultdict(dict)
    cloud_init_data["userData"][section] = data

    return cloud_init_data


@contextmanager
def vm_instance_from_template(
    request,
    unprivileged_client,
    namespace,
    data_source=None,
    data_volume_template=None,
    existing_data_volume=None,
    cloud_init_data=None,
    node_selector=None,
    vm_cpu_model=None,
    vm_cpu_flags=None,
    host_device_name=None,
    gpu_name=None,
    vm_affinity=None,
):
    """Create a VM from template and start it (start step could be skipped by setting
    request.param['start_vm'] to False.

    Prerequisite - a DV must be created prior to VM creation.

    Args:
        data_source (obj `DataSource`): DS object points to a golden image PVC.
        data_volume_template (dict): dataVolumeTemplates dict; will replace dataVolumeTemplates in VM yaml
        existing_data_volume (obj `DataVolume`: DV resource): existing DV to be consumed directly (not cloned)

    Yields:
        obj `VirtualMachine`: VM resource

    """
    params = request.param if hasattr(request, "param") else request
    vm_name = params["vm_name"].replace(".", "-").lower()
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**params["template_labels"]),
        data_source=data_source,
        data_volume_template=data_volume_template,
        existing_data_volume=existing_data_volume,
        vm_dict=params.get("vm_dict"),
        cpu_cores=params.get("cpu_cores"),
        cpu_threads=params.get("cpu_threads"),
        memory_requests=params.get("memory_requests"),
        network_model=params.get("network_model"),
        network_multiqueue=params.get("network_multiqueue"),
        cloud_init_data=cloud_init_data,
        attached_secret=params.get("attached_secret"),
        node_selector=node_selector,
        diskless_vm=params.get("diskless_vm"),
        cpu_model=params.get("cpu_model") or vm_cpu_model,
        cpu_flags=params.get("cpu_flags") or vm_cpu_flags,
        cpu_placement=params.get("cpu_placement"),
        isolate_emulator_thread=params.get("isolate_emulator_thread"),
        iothreads_policy=params.get("iothreads_policy"),
        dedicated_iothread=params.get("dedicated_iothread"),
        ssh=params.get("ssh", True),
        disk_options_vm=params.get("disk_io_option"),
        host_device_name=params.get("host_device_name") or host_device_name,
        gpu_name=params.get("gpu_name") or gpu_name,
        cloned_dv_size=params.get("cloned_dv_size"),
        vhostmd=params.get("vhostmd"),
        machine_type=params.get("machine_type"),
        eviction_strategy=params.get("eviction_strategy"),
        vm_affinity=vm_affinity,
    ) as vm:
        if params.get("start_vm", True):
            running_vm(
                vm=vm,
                wait_for_interfaces=params.get("guest_agent", True),
                check_ssh_connectivity=vm.ssh,
            )
        yield vm


@contextmanager
def node_mgmt_console(node, node_mgmt):
    try:
        LOGGER.info(f"{node_mgmt.capitalize()} the node {node.name}")
        extra_opts = "--delete-emptydir-data --ignore-daemonsets=true --force" if node_mgmt == "drain" else ""
        run(
            f"nohup oc adm {node_mgmt} {node.name} {extra_opts} &",
            shell=True,
        )
        yield
    finally:
        LOGGER.info(f"Uncordon node {node.name}")
        run(f"oc adm uncordon {node.name}", shell=True)
        wait_for_node_schedulable_status(node=node, status=True)


@contextmanager
def create_vm_cloning_job(
    name,
    namespace,
    source_name,
    source_kind=None,
    target_name=None,
    label_filters=None,
    annotation_filters=None,
    new_mac_addresses=None,
    new_smbios_serial=None,
):
    """
    Create VirtualMachineClone object.

    Args:
        name (str): the name of cloning job
        source_name (str): the clone's source name
        source_kind (str, optional): the clone's source type, default - VirtualMachine.kind
        target_name (str, optional): the clone's target name, default - randomly generated name
        label_filters (list, optional): List of label filters, e.g. ["*", "!someKey/*"]
        annotation_filters (list, optional): List of annotation filters, e.g. ["firstKey/*", "secondKey/*"]
        new_mac_addresses (dict, optional): Dict of new MAC addresses, {interface_name: mac_address}
        new_smbios_serial (str, optional): the clone's new smbios serial
    """
    with VirtualMachineClone(
        name=name,
        namespace=namespace,
        source_name=source_name,
        source_kind=source_kind,
        target_name=target_name,
        label_filters=label_filters,
        annotation_filters=annotation_filters,
        new_mac_addresses=new_mac_addresses,
        new_smbios_serial=new_smbios_serial,
    ) as vmc:
        vmc.wait_for_status(status=VirtualMachineClone.Status.SUCCEEDED)
        yield vmc


def wait_for_node_schedulable_status(node, status, timeout=60):
    """
    Wait for node status to be ready (status=True) or unschedulable (status=False)
    """
    LOGGER.info(f"Wait for node {node.name} to be {Node.Status.READY if status else Node.Status.SCHEDULING_DISABLED}.")

    sampler = TimeoutSampler(wait_timeout=timeout, sleep=1, func=lambda: node.instance.spec.unschedulable)
    for sample in sampler:
        if status:
            if not sample and not kubernetes_taint_exists(node):
                return
        else:
            if sample and kubernetes_taint_exists(node):
                return


def get_hyperconverged_kubevirt(admin_client, hco_namespace):
    for kv in KubeVirt.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
        name="kubevirt-kubevirt-hyperconverged",
    ):
        return kv


def get_kubevirt_hyperconverged_spec(admin_client, hco_namespace):
    return get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace).instance.to_dict()[
        "spec"
    ]


def get_hyperconverged_ovs_annotations(hyperconverged):
    return (hyperconverged.instance.to_dict()["metadata"].get("annotations", {})).get("deployOVS")


def get_base_templates_list(client):
    """Return SSP base templates"""
    common_templates_list = list(
        Template.get(
            dyn_client=client,
            singular_name=Template.singular_name,
            label_selector=Template.Labels.BASE,
        )
    )
    return [
        template
        for template in common_templates_list
        if not template.instance.metadata.annotations.get(template.Annotations.DEPRECATED)
    ]


def get_template_by_labels(admin_client, template_labels):
    template = list(
        Template.get(
            dyn_client=admin_client,
            singular_name=Template.singular_name,
            namespace="openshift",
            label_selector=",".join([f"{label}=true" for label in template_labels if OS_FLAVOR_FEDORA not in label]),
        ),
    )
    if any(
        f"{Template.ApiGroup.OS_TEMPLATE_KUBEVIRT_IO}/{OS_FLAVOR_FEDORA}" in template_label
        for template_label in template_labels
    ):
        template = [fedora_template for fedora_template in template if OS_FLAVOR_FEDORA in fedora_template.name]
    matched_templates = len(template)
    assert matched_templates == 1, f"{matched_templates} templates found which match {template_labels} labels"

    return template[0]


def wait_for_updated_kv_value(admin_client, hco_namespace, path, value, timeout=15):
    """
    Waits for updated values in KV CR configuration

    Args:
        admin_client (:obj:`DynamicClient`): DynamicClient object
        hco_namespace (:obj:`Namespace`): HCO namespace object
        path (list): list of nested keys to be looked up in KV CR configuration dict
        value (any): the expected value of the last key in path
        timeout (int): timeout in seconds

    Example:
        path - ['minCPUModel'], value - 'Haswell-noTSX'
        {"configuration": {"minCPUModel": "Haswell-noTSX"}} will be matched against KV CR spec.

    Raises:
        TimeoutExpiredError: After timeout is reached if the expected key value does not match the actual value
    """
    base_path = ["configuration"]
    base_path.extend(path)
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=1,
        func=lambda: benedict(
            get_kubevirt_hyperconverged_spec(admin_client=admin_client, hco_namespace=hco_namespace),
            keypath_separator=None,
        ).get(base_path),
    )
    try:
        for sample in samples:
            if sample == value:
                break
    except TimeoutExpiredError:
        hco_annotations = utilities.infra.get_hyperconverged_resource(
            client=admin_client, hco_ns_name=hco_namespace.name
        ).instance.metadata.annotations
        LOGGER.error(f"KV CR is not updated, path: {path}, expected value: {value}, HCO annotations: {hco_annotations}")
        raise
    # After updating KV need to be sure HCO is stable
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )


# function waits when VMIM resource created by cluster automatically (e.g. after node drain OR hotplug)
def get_created_migration_job(vm, timeout=TIMEOUT_1MIN, client=None):
    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=VirtualMachineInstanceMigration.get,
        namespace=vm.namespace,
        vmi_name=vm.vmi.name,
        dyn_client=client,
    )
    try:
        for sample in sampler:
            # sample - generator, check if it is not empty
            vmim = next(sample, None)
            if vmim:
                return vmim
    except TimeoutExpiredError:
        LOGGER.error("Migration job not created!")
        raise


def check_migration_process_after_node_drain(dyn_client, vm):
    """
    Wait for migration process to succeed and verify that VM indeed moved to new node.
    """
    vmi_old_uid = vm.vmi.instance.metadata.uid
    source_node = vm.privileged_vmi.virt_launcher_pod.node
    LOGGER.info(f"The VMI was running on {source_node.name}")
    wait_for_node_schedulable_status(node=source_node, status=False)
    vmim = get_created_migration_job(vm=vm, client=dyn_client, timeout=TIMEOUT_5MIN)
    wait_for_migration_finished(
        namespace=vm.namespace, migration=vmim, timeout=TIMEOUT_30MIN if "windows" in vm.name else TIMEOUT_10MIN
    )

    target_pod = vm.privileged_vmi.virt_launcher_pod
    target_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_3MIN)
    target_node = target_pod.node
    LOGGER.info(f"The VMI is currently running on {target_node.name}")
    assert target_node != source_node, f"Target node is same as source node: {source_node.name}"
    vmi_new_uid = vm.vmi.instance.metadata.uid
    assert vmi_old_uid == vmi_new_uid, (
        f"vmi uid before migration:{vmi_old_uid} is not same as vmi uid after migration{vmi_new_uid}"
    )


def restart_vm_wait_for_running_vm(vm, wait_for_interfaces=True, check_ssh_connectivity=True, ssh_timeout=TIMEOUT_2MIN):
    vm.restart(wait=True)
    # Calling running_vm() to ensure the VM is up and connective
    return running_vm(
        vm=vm,
        wait_for_interfaces=wait_for_interfaces,
        check_ssh_connectivity=check_ssh_connectivity,
        ssh_timeout=ssh_timeout,
    )


def wait_for_kubevirt_conditions(
    admin_client,
    hco_namespace,
    expected_conditions=None,
    wait_timeout=TIMEOUT_10MIN,
    sleep=5,
    consecutive_checks_count=3,
    condition_key1="type",
    condition_key2="status",
):
    """
    Checking Kubevirt status.conditions
    """
    utilities.infra.wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        namespace=hco_namespace.name,
        expected_conditions=expected_conditions or DEFAULT_KUBEVIRT_CONDITIONS,
        resource_kind=KubeVirt,
        condition_key1=condition_key1,
        condition_key2=condition_key2,
        total_timeout=wait_timeout,
        polling_interval=sleep,
        consecutive_checks_count=consecutive_checks_count,
    )


def get_all_virt_pods_with_running_status(dyn_client, hco_namespace):
    virt_pods_with_status = {
        pod.name: pod.status
        for pod in Pod.get(
            dyn_client=dyn_client,
            namespace=hco_namespace.name,
        )
        if pod.name.startswith("virt")
    }
    assert all(pod_status == Pod.Status.RUNNING for pod_status in virt_pods_with_status.values()), (
        f"All virt pods were expected to be in running state.Here are all virt pods:{virt_pods_with_status}"
    )
    return virt_pods_with_status


def wait_for_kv_stabilize(admin_client, hco_namespace):
    wait_for_kubevirt_conditions(admin_client=admin_client, hco_namespace=hco_namespace)
    wait_for_hco_conditions(admin_client=admin_client, hco_namespace=hco_namespace)


def get_oc_image_info(  # type: ignore[return]
    image: str, pull_secret: str | None = None, architecture: str = LINUX_AMD_64
) -> dict[str, Any]:
    def _get_image_json(cmd: str) -> dict[str, Any]:
        return json.loads(run_command(command=shlex.split(cmd), check=False)[1])

    base_command = f"oc image -o json info {image} --filter-by-os {architecture}"
    if pull_secret:
        base_command = f"{base_command} --registry-config={pull_secret}"

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10SEC,
            sleep=TIMEOUT_1SEC,
            exceptions_dict={JSONDecodeError: [], TypeError: []},
            func=_get_image_json,
            cmd=base_command,
        ):
            if sample:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(f"Failed to parse {base_command}")
        raise


def taint_node_no_schedule(node):
    return ResourceEditor(
        patches={
            node: {
                "spec": {
                    "taints": [
                        {
                            "effect": "NoSchedule",
                            "key": f"{Resource.ApiGroup.KUBEVIRT_IO}/drain",
                            "value": "draining",
                        }
                    ]
                }
            }
        }
    )


def add_validation_rule_to_annotation(vm_annotation, vm_validation_rule):
    kubevirt_validation = f"{Resource.ApiGroup.VM_KUBEVIRT_IO}/validations"
    validation_list_string = vm_annotation.setdefault(kubevirt_validation, "[]")
    validation_list = json.loads(validation_list_string)
    validation_list.append(vm_validation_rule)
    vm_annotation[kubevirt_validation] = json.dumps(validation_list)


def start_and_fetch_processid_on_linux_vm(vm, process_name, args="", use_nohup=False):
    utilities.virt.wait_for_ssh_connectivity(vm=vm)
    nohup_cmd = "nohup" if use_nohup else ""
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"killall -9 {process_name}; {nohup_cmd} {process_name} {args} </dev/null &>/dev/null &"),
    )
    return fetch_pid_from_linux_vm(vm=vm, process_name=process_name)


def fetch_pid_from_linux_vm(vm, process_name):
    cmd_res = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"pgrep {process_name} -x || true"),
    )[0].strip()
    assert cmd_res, f"VM {vm.name}, '{process_name}' process not found"
    return int(cmd_res)


def start_and_fetch_processid_on_windows_vm(vm, process_name):
    wait_for_ssh_connectivity(vm=vm)
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(
            f"powershell Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList {process_name}"
        ),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )
    return fetch_pid_from_windows_vm(vm=vm, process_name=process_name)


def fetch_pid_from_windows_vm(vm, process_name):
    cmd_res = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"powershell -Command (Get-Process -Name {process_name.removesuffix('.exe')}).Id"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0].strip()
    assert cmd_res, f"Process '{process_name}' not in output: {cmd_res}"
    return int(cmd_res)


def kill_processes_by_name_linux(vm, process_name, check_rc=True):
    cmd = shlex.split(f"pkill {process_name}")
    run_ssh_commands(host=vm.ssh_exec, commands=cmd, check_rc=check_rc)


class VirtualMachineForCloning(VirtualMachineForTests):
    def __init__(
        self,
        vm_labels=None,
        vm_annotations=None,
        smbios_serial=None,
        **kwargs,
    ):
        super().__init__(
            generate_unique_name=False,
            **kwargs,
        )
        self.vm_labels = vm_labels
        self.vm_annotations = vm_annotations
        self.smbios_serial = smbios_serial

    def to_dict(self):
        super().to_dict()

        if self.vm_labels:
            self.res["metadata"].setdefault("labels", {}).update(self.vm_labels)

        if self.vm_annotations:
            self.res["metadata"].setdefault("annotations", {}).update(self.vm_annotations)

        if self.smbios_serial:
            self.res["spec"]["template"]["spec"].setdefault("domain", {}).setdefault("firmware", {}).update({
                "serial": self.smbios_serial,
            })


@contextmanager
def target_vm_from_cloning_job(cloning_job):
    cloning_job_spec = cloning_job.instance.spec
    target_vm = VirtualMachineForTests(
        name=cloning_job_spec.target.name,
        namespace=cloning_job.namespace,
        os_flavor=cloning_job_spec.source.name.split("-")[0],
        generate_unique_name=False,
    )
    assert target_vm.exists, f"{target_vm.name} VM was not created."
    running_vm(vm=target_vm)

    yield target_vm
    target_vm.clean_up()


def wait_for_vmi_relocation_and_running(initial_node, vm, timeout=TIMEOUT_5MIN):
    try:
        for sample in TimeoutSampler(
            wait_timeout=timeout,
            sleep=TIMEOUT_5SEC,
            func=lambda: vm.vmi.node.name != initial_node.name
            and vm.vmi.status == VirtualMachineInstance.Status.RUNNING,
        ):
            if sample:
                LOGGER.info(
                    f"The VM was created on {initial_node.name}, "
                    f"and has successfully been relocated to {vm.vmi.node.name}"
                )
                return True
    except TimeoutExpiredError:
        LOGGER.error(f"The VMI on {initial_node.name} has not been relocated to a different node.")
        raise


def check_qemu_guest_agent_installed(ssh_exec: Host) -> bool:
    ssh_exec.sudo = True
    return ssh_exec.package_manager.exist(package="qemu-guest-agent")


def validate_libvirt_persistent_domain(vm):
    domain = vm.privileged_vmi.virt_launcher_pod.execute(
        command=shlex.split("virsh list --persistent"), container="compute"
    )
    assert vm.vmi.Status.RUNNING.lower() in domain


def get_nodes_gpu_info(util_pods, node):
    pod_exec = utilities.infra.ExecCommandOnPod(utility_pods=util_pods, node=node)
    return pod_exec.exec(command="sudo /sbin/lspci -nnk | grep -A 3 '3D controller'")


def assert_linux_efi(vm: VirtualMachineForTests) -> None:
    """
    Verify guest OS is using EFI.
    """
    return run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("ls -ld /sys/firmware/efi"))[0]


def pause_optional_migrate_unpause_and_check_connectivity(vm: VirtualMachineForTests, migrate: bool = False) -> None:
    vmi = VirtualMachineInstance(client=get_client(), name=vm.vmi.name, namespace=vm.vmi.namespace)
    vmi.pause(wait=True)
    if migrate:
        migrate_vm_and_verify(vm=vm, wait_for_interfaces=False)
    vmi.unpause(wait=True)
    LOGGER.info("Verify VM is running and ready after unpause")
    wait_for_running_vm(vm=vm)


def validate_pause_optional_migrate_unpause_linux_vm(
    vm: VirtualMachineForTests, pre_pause_pid: int | None = None, migrate: bool = False
) -> None:
    proc_name = OS_PROC_NAME["linux"]
    if not pre_pause_pid:
        pre_pause_pid = start_and_fetch_processid_on_linux_vm(vm=vm, process_name=proc_name, args="localhost")
    pause_optional_migrate_unpause_and_check_connectivity(vm=vm, migrate=migrate)
    post_pause_pid = fetch_pid_from_linux_vm(vm=vm, process_name=proc_name)
    kill_processes_by_name_linux(vm=vm, process_name=proc_name)
    assert post_pause_pid == pre_pause_pid, (
        f"PID mismatch!\n Pre pause PID is: {pre_pause_pid}\n Post pause PID is: {post_pause_pid}"
    )


def check_vm_xml_smbios(vm: VirtualMachineForTests, cm_values: Dict[str, str]) -> None:
    """
    Verify SMBIOS on VM XML [sysinfo type=smbios][system] match kubevirt-config
    config map.
    """

    LOGGER.info("Verify VM XML - SMBIOS values.")
    smbios_vm = vm.privileged_vmi.xml_dict["domain"]["sysinfo"]["system"]["entry"]
    smbios_vm_dict = {entry["@name"]: entry["#text"] for entry in smbios_vm}
    assert smbios_vm, "VM XML missing SMBIOS values."
    results = {
        "manufacturer": smbios_vm_dict["manufacturer"] == cm_values["manufacturer"],
        "product": smbios_vm_dict["product"] == cm_values["product"],
        "family": smbios_vm_dict["family"] == cm_values["family"],
        "version": smbios_vm_dict["version"] == cm_values["version"],
    }
    LOGGER.info(f"Results: {results}")
    assert all(results.values())


def assert_vm_xml_efi(vm: VirtualMachineForTests, secure_boot_enabled: bool = True) -> None:
    LOGGER.info("Verify VM XML - EFI secureBoot values.")
    xml_dict_os = vm.privileged_vmi.xml_dict["domain"]["os"]
    ovmf_path = "/usr/share/OVMF"
    efi_path = f"{ovmf_path}/OVMF_CODE.secboot.fd"
    # efi vars path when secure boot is enabled: /usr/share/OVMF/OVMF_VARS.secboot.fd
    # efi vars path when secure boot is disabled: /usr/share/OVMF/OVMF_VARS.fd
    efi_vars_path = f"{ovmf_path}/OVMF_VARS.{'secboot.' if secure_boot_enabled else ''}fd"
    vmi_xml_efi_path = xml_dict_os["loader"]["#text"]
    vmi_xml_efi_vars_path = xml_dict_os["nvram"]["@template"]
    vmi_xml_os_secure = xml_dict_os["loader"]["@secure"]
    os_secure = "yes" if secure_boot_enabled else "no"
    assert vmi_xml_efi_path == efi_path, f"EFIPath value {vmi_xml_efi_path} does not match expected {efi_path} value"
    assert vmi_xml_os_secure == os_secure, (
        f"EFI secure value {vmi_xml_os_secure} does not seem to be set as {os_secure}"
    )
    assert vmi_xml_efi_vars_path == efi_vars_path, (
        f"EFIVarsPath value {vmi_xml_efi_vars_path} does not match expected {efi_vars_path} value"
    )


def update_vm_efi_spec_and_restart(
    vm: VirtualMachineForTests, spec: dict[str, Any] | None = None, wait_for_interfaces: bool = True
) -> None:
    ResourceEditor({
        vm: {"spec": {"template": {"spec": {"domain": {"firmware": {"bootloader": {"efi": spec or {}}}}}}}}
    }).update()
    restart_vm_wait_for_running_vm(vm=vm, wait_for_interfaces=wait_for_interfaces)


def delete_guestosinfo_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    supportedCommands - removed as the data is used for internal guest agent validations
    fsInfo, userList - checked in validate_fs_info_virtctl_vs_linux_os / validate_user_info_virtctl_vs_linux_os
    fsFreezeStatus - removed as it is not related to GA validations
    """
    removed_keys = ["supportedCommands", "fsInfo", "userList", "fsFreezeStatus"]
    [data.pop(key, None) for key in removed_keys]

    return data


# Guest agent info gather functions.
def get_virtctl_os_info(vm: VirtualMachineForTests) -> dict[str, Any] | None:
    """
    Returns OS data dict in format:
    {
        "guestAgentVersion": guestAgentVersion,
        "hostname": hostname,
        "os": {
            "name": name,
            "kernelRelease": kernelRelease,
            "version": version,
            "prettyName": prettyName,
            "versionId": versionId,
            "kernelVersion": kernelVersion,
            "machine": machine,
            "id": id,
        },
        "timezone": timezone",
    }

    """
    cmd = ["guestosinfo", vm.name]
    res, output, err = utilities.infra.run_virtctl_command(command=cmd, namespace=vm.namespace)
    if not res:
        LOGGER.error(f"Failed to get guest-agent info via virtctl. Error: {err}")
        return None
    data = json.loads(output)

    return delete_guestosinfo_keys(data=data)


def validate_virtctl_guest_agent_data_over_time(vm: VirtualMachineForTests) -> bool:
    """
    Validates that virtctl guest info is available over time. (BZ 1886453 <skip-bug-check>)

    Returns:
        bool: True - if virtctl guest info is available after timeout else False
    """
    samples = TimeoutSampler(wait_timeout=TIMEOUT_3MIN, sleep=TIMEOUT_5SEC, func=get_virtctl_os_info, vm=vm)
    consecutive_check = 0
    try:
        for sample in samples:
            if not sample:
                consecutive_check += 1
                if consecutive_check == 3:
                    return False
            else:
                consecutive_check = 0
    except TimeoutExpiredError:
        return True
    return False


def get_vm_boot_time(vm: VirtualMachineForTests) -> str:
    boot_command = 'net statistics workstation | findstr "Statistics since"' if "windows" in vm.name else "who -b"
    return run_ssh_commands(host=vm.ssh_exec, commands=shlex.split(boot_command))[0]


def username_password_from_cloud_init(vm_volumes: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Get username and password from cloud-init data.

    Args:
        vm_volumes (list[dict[str, Any]]): List of volumes with cloud-init data.

    Returns:
            tuple[str, str]: Username and password. If not found, empty strings.
    """

    if cloud_init := [volume[CLOUD_INIT_NO_CLOUD] for volume in vm_volumes if volume.get(CLOUD_INIT_NO_CLOUD)]:
        if (user_data := cloud_init[0].get("userData")) and (
            _match := re.search(r"user: (?P<user>.*)\npassword: (?P<password>.*)\n", user_data)
        ):
            LOGGER.info("Get VM credentials from cloud-init")
            return _match["user"], _match["password"]

    return "", ""


def validate_virtctl_guest_agent_after_guest_reboot(vm: VirtualMachineForTests, os_type: str) -> None:
    guest_reboot(vm=vm, os_type=os_type)
    wait_for_running_vm(vm=vm, ssh_timeout=TIMEOUT_30MIN if os_type == OS_FLAVOR_WINDOWS else TIMEOUT_5MIN)
    assert validate_virtctl_guest_agent_data_over_time(vm=vm), "Guest agent stopped responding after guest reboot"


def guest_reboot(vm: VirtualMachineForTests, os_type: str) -> None:
    commands = {
        "stop-user-agent": {
            LINUX_STR: "sudo systemctl stop qemu-guest-agent",
            OS_FLAVOR_WINDOWS: "powershell -command \"Stop-Service -Name 'QEMU-GA'\"",
        },
        "reboot": {
            LINUX_STR: "sudo reboot",
            OS_FLAVOR_WINDOWS: 'powershell -command "Restart-Computer -Force"',
        },
    }

    LOGGER.info("Stopping user agent")
    run_os_command(vm=vm, command=commands["stop-user-agent"][os_type])
    wait_for_user_agent_down(vm=vm, timeout=TIMEOUT_2MIN)

    LOGGER.info(f"Rebooting {vm.name} from guest")
    run_os_command(vm=vm, command=commands["reboot"][os_type])


def run_os_command(vm: VirtualMachineForTests, command: str) -> Optional[str]:
    try:
        return run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(command),
            timeout=5,
            tcp_timeout=TCP_TIMEOUT_30SEC,
        )[0]
    except ProxyCommandFailure:
        # On RHEL on successful reboot command execution ssh gets stuck
        if "reboot" not in command:
            raise
        return None


def wait_for_user_agent_down(vm: VirtualMachineForTests, timeout: int) -> None:
    LOGGER.info(f"Waiting up to {round(timeout / 60)} minutes for user agent to go down on {vm.name}")
    for sample in TimeoutSampler(
        wait_timeout=timeout,
        sleep=2,
        func=lambda: [
            condition for condition in vm.vmi.instance.status.conditions if condition["type"] == "AgentConnected"
        ],
    ):
        # Consider agent "down" when condition is absent OR explicitly not True
        if not sample or all(condition.get("status") != "True" for condition in sample):
            break
