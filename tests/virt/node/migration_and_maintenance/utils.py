import json
import logging
import re
from contextlib import contextmanager

from kubernetes.dynamic.exceptions import InternalServerError, NotFoundError
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from ocp_resources.pod import Pod
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_3MIN, TIMEOUT_10MIN, TIMEOUT_10SEC, VIRT_HANDLER
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import ExecCommandOnPod, get_hyperconverged_resource, get_pods
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


def get_virt_handler_pods(client, namespace):
    return get_pods(
        dyn_client=client,
        namespace=namespace,
        label=f"{Pod.ApiGroup.KUBEVIRT_IO}={VIRT_HANDLER}",
    )


def check_virt_handler_pods_for_migration_network(client, namespace, network_name, migration_network=True):
    """
    Checks whether virt-handler pods have migration network.

    Args:
        client (:obj:`DynamicClient`): DynamicClient object
        namespace (:obj:`Namespace`): HCO namespace object
        network_name (str): string name of migration network to check
        migration_network (bool): if migration_network=True check that pods have network <network_name>
                                  if migration_network=False check that pods don't have network <network_name>
    """
    virt_handler_pods = get_virt_handler_pods(client=client, namespace=namespace)
    verified_pods_list = []

    for pod in virt_handler_pods:
        pod_network_annotations = pod.instance.metadata.annotations.get(
            f"{Pod.ApiGroup.K8S_V1_CNI_CNCF_IO}/networks", ""
        )
        migration_network_on_pod = pod_network_annotations.split("@")[0] == network_name
        if migration_network and migration_network_on_pod:
            verified_pods_list.append(pod)
        elif not migration_network and not migration_network_on_pod:
            verified_pods_list.append(pod)
    return verified_pods_list


def wait_for_virt_handler_pods_network_updated(
    client, namespace, network_name, virt_handler_daemonset, migration_network=True
):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_10SEC,
        func=check_virt_handler_pods_for_migration_network,
        client=client,
        namespace=namespace,
        network_name=network_name,
        migration_network=migration_network,
        exceptions_dict={NotFoundError: []},
    )
    LOGGER.info(
        "Waiting for all virt-handler pods to restart with "
        f"{'new network' if migration_network else 'default'} configuration"
    )
    desired_number_of_pods = virt_handler_daemonset.instance.status.desiredNumberScheduled
    try:
        for sample in samples:
            if sample and desired_number_of_pods == len(sample):
                for pod in sample:
                    pod.wait_for_status(status=Pod.Status.RUNNING)
                return True
    except TimeoutExpiredError:
        LOGGER.error(
            f"Some virt-handler pods {'dont' if migration_network else 'still'} have migration network\n"
            f"Updated pods: {[pod.name for pod in sample]}"
        )
        raise


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


def assert_node_drain_and_vm_migration(admin_client, vm, virt_handler_pods):
    source_node = vm.privileged_vmi.node
    with node_mgmt_console(admin_client=admin_client, node=source_node, node_mgmt="drain"):
        check_migration_process_after_node_drain(client=admin_client, vm=vm)
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
