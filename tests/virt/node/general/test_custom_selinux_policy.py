import pytest

from utilities.infra import ExecCommandOnPod


@pytest.mark.s390x
def test_customselinuxpolicy(workers_utility_pods, schedulable_nodes):
    """
    Jira: https://redhat.atlassian.net/browse/KNIP-1268 # <skip-jira-utils-check>
    Polarion: CNV-9918
    """
    nodes = []
    for node in schedulable_nodes:
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
        out = pod_exec.exec(command="sudo semodule -l")
        if "virt_launcher" in out:
            nodes.append(node.name)
    assert not nodes, f"node: {nodes} still have virt_launcher policies."
