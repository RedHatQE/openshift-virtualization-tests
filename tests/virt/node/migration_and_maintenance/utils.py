import json
import logging
import re
from contextlib import contextmanager

from kubernetes.dynamic.exceptions import InternalServerError
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_3MIN, TIMEOUT_10SEC
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import ExecCommandOnPod, get_hyperconverged_resource
from utilities.virt import check_migration_process_after_node_drain, node_mgmt_console

LOGGER = logging.getLogger(__name__)
WHEREABOUTS_NETWORK = "10.200.5.0/24"
TCPDUMP_LOG_FILE = "/tmp/mig_tcpdump.log"


class MACVLANNetworkAttachmentDefinition(NetworkAttachmentDefinition):
    def __init__(
        self,
        name,
        namespace,
        master,
        client=None,
        teardown=True,
    ):
        super().__init__(name=name, namespace=namespace, client=client, teardown=teardown)
        self.master = master

    def to_dict(self):
        super().to_dict()
        spec_config = {
            "cniVersion": "0.3.1",
            "type": "macvlan",
            "master": self.master,
            "mode": "bridge",
            "ipam": {
                "type": "whereabouts",
                "range": WHEREABOUTS_NETWORK,
            },
        }

        self.res["spec"]["config"] = json.dumps(spec_config)


def assert_vm_migrated_through_dedicated_network_with_logs(source_node, vm, virt_handler_pods):
    def _get_source_migration_logs():
        for pod in virt_handler_pods:
            if pod.node.name == source_node.name:
                return pod.log()

    LOGGER.info(f"Checking virt-handler logs of VM {vm.name} migrated via dedicated network")
    # get first 3 octets of network address
    parsed_ip = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}\/\d{1,2}", WHEREABOUTS_NETWORK).group(1)
    parsed_ip = parsed_ip.replace(".", "\\.")
    search_pattern = rf"\"proxy \w+? listening\".+?{parsed_ip}.+?\"uid\":\"{vm.vmi.instance.metadata.uid}\""

    # matches list should contain 3 matches for start of migration and 3 for end of it
    # start log - ... "msg": "proxy started listening", "ourbound": ...
    # end log - ... "msg": "proxy stopped listening", "outbound": ...
    # 3 started/stoped logs should exist since 3 different proxies are created during migration process
    matches = re.findall(search_pattern, _get_source_migration_logs())
    assert len(matches) == 6, f"Not all migration logs found. Found {len(matches)} of 6"


def assert_node_drain_and_vm_migration(dyn_client, vm, virt_handler_pods):
    source_node = vm.privileged_vmi.node
    with node_mgmt_console(node=source_node, node_mgmt="drain"):
        check_migration_process_after_node_drain(dyn_client=dyn_client, vm=vm)
        assert_vm_migrated_through_dedicated_network_with_logs(
            source_node=source_node, vm=vm, virt_handler_pods=virt_handler_pods
        )


def assert_vm_migrated_through_dedicated_network_with_tcpdump(utility_pods, node, vm):
    LOGGER.info(f"Checking tcpdump logs of VM {vm.name} migration")
    tcpdump_out = ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(
        command=f"cat {TCPDUMP_LOG_FILE}", chroot_host=False
    )
    assert tcpdump_out, "Migration didn't go through dedicated network!"


@contextmanager
def run_tcpdump_on_source_node(utility_pods, node, iface_name):
    pod_exec = ExecCommandOnPod(utility_pods=utility_pods, node=node)
    pod_exec.exec(
        command=f"tcpdump -i {iface_name} net {WHEREABOUTS_NETWORK} -nnn > {TCPDUMP_LOG_FILE} 2> /dev/null &",
        chroot_host=False,
    )

    yield

    pod_exec.exec(command=f"pkill tcpdump; rm -f {TCPDUMP_LOG_FILE}")


@contextmanager
def update_hco_migration_config(client, hco_ns_name, param, value):
    def _wait_restore(_resource_editor):
        # Sometime in tests that do node draining in process, the virt-operator
        # pods are not yet running again after the test if finished therefore the
        # attempt to update HCO recource will fail with InternalServerError
        samples = TimeoutSampler(
            wait_timeout=TIMEOUT_3MIN,
            sleep=TIMEOUT_10SEC,
            func=_resource_editor.restore,
            exceptions_dict={InternalServerError: []},
        )
        try:
            for sample in samples:
                if not sample:
                    break
        except TimeoutExpiredError:
            raise

    hco_cr = get_hyperconverged_resource(client=client, hco_ns_name=hco_ns_name)
    editor = ResourceEditorValidateHCOReconcile(
        patches={hco_cr: {"spec": {"liveMigrationConfig": {param: value}}}},
    )
    editor.update(backup_resources=True)
    yield
    _wait_restore(_resource_editor=editor)
