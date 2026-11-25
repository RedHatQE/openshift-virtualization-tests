import pytest


def assert_linux_label_was_added_in_nodes(nodes):
    no_os_labels_nodes = []
    for node in nodes:
        node_os_label = [
            label_name
            for label_name, label_value in node.labels.items()
            if label_name == "kubernetes.io/os" and label_value == "linux"
        ]
        if not node_os_label:
            no_os_labels_nodes.append(node.name)
    assert not no_os_labels_nodes, f"Following Nodes {no_os_labels_nodes} does not have Linux label."


@pytest.mark.gating
@pytest.mark.conformance
@pytest.mark.s390x
def test_linux_label_was_added(schedulable_nodes):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-5163 # <skip-jira-utils-check>
    Polarion: CNV-5758
    """
    assert_linux_label_was_added_in_nodes(nodes=schedulable_nodes)
