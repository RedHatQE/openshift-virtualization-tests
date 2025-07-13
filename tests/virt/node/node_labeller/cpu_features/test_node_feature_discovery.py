"""
Test node feature discovery.
"""

import pytest

from utilities.constants import CPU_MODEL_LABEL_PREFIX
from utilities.hco import update_hco_annotations
from utilities.virt import wait_for_kv_stabilize, wait_for_updated_kv_value

OBSOLETE_CPU = "obsoleteCPUModels"


pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.fixture()
def nodes_labels_dict(nodes):
    """
    Collects all labels from nodes and creates dict of cpu-models/features/kvm-info per node.
    Return dict:
    {'<node_name>': {'cpu_models': [<cpu_models>], 'cpu_features': [<cpu_features>], 'kvm-info': [<kvm-info>]}}
    """
    node_labels_dict = {}

    for node in nodes:
        node_labels_dict[node.name] = {}
        labels_dict = dict(node.instance.metadata.labels)
        node_labels_dict[node.name]["cpu_models"] = [
            label.split("/")[1] for label in labels_dict if label.startswith(CPU_MODEL_LABEL_PREFIX)
        ]
        node_labels_dict[node.name]["cpu_features"] = [
            label.split("/")[1] for label in labels_dict if label.startswith("cpu-feature.node.kubevirt.io/")
        ]
        node_labels_dict[node.name]["kvm-info"] = [
            label.split("/")[1] for label in labels_dict if label.startswith("hyperv.node.kubevirt.io/")
        ]

    return node_labels_dict


@pytest.fixture()
def updated_kubevirt_cpus(
    hyperconverged_resource_scope_function,
    cluster_common_node_cpu,
    admin_client,
    hco_namespace,
):
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_function,
        path=OBSOLETE_CPU,
        value={cluster_common_node_cpu: True},
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=[OBSOLETE_CPU, cluster_common_node_cpu],
            value=True,
            timeout=60,
        )
        wait_for_kv_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
        yield
    wait_for_kv_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


def node_label_checker(node_label_dict, label_list, dict_key):
    """
    Check node labels for either cpu_models, cpu_features or kvm-info depending on dict_key value.
    Return dict:
    {'<node_name>': [<cpu_models | cpu_features | kvm-info>]}
    """
    return {
        node: [value for value in label_list if value in node_label_dict[node][dict_key]] for node in node_label_dict
    }


@pytest.mark.x86_64
@pytest.mark.s390x
@pytest.mark.polarion("CNV-2797")
def test_obsolete_cpus_in_node_labels(nodes_labels_dict, kubevirt_config):
    """
    Test obsolete CPUs. Obsolete CPUs don't appear in node labels.
    """
    test_dict = node_label_checker(
        node_label_dict=nodes_labels_dict,
        label_list=kubevirt_config[OBSOLETE_CPU].keys(),
        dict_key="cpu_models",
    )
    assert not any(test_dict.values()), f"Obsolete CPU found in labels\n{test_dict}"


@pytest.mark.gating
@pytest.mark.polarion("CNV-3607")
@pytest.mark.x86_64  # On s390x, hyperv features aren't supported, so hyperv feature labels are not expected
def test_hardware_required_node_labels(nodes_labels_dict):
    kvm_info_nfd_labels = [
        "vpindex",
        "runtime",
        "time",
        "synic",
        "synic2",
        "tlbflush",
        "reset",
        "frequencies",
        "reenlightenment",
        "base",
        "ipi",
        "synictimer",
    ]
    test_dict = node_label_checker(
        node_label_dict=nodes_labels_dict,
        label_list=kvm_info_nfd_labels,
        dict_key="kvm-info",
    )
    assert any(test_dict.values()), f"KVM info not found in labels\n{test_dict}"


@pytest.mark.gating
@pytest.mark.x86_64
@pytest.mark.s390x
@pytest.mark.polarion("CNV-6088")
def test_hardware_non_required_node_labels(nodes_labels_dict):
    hw_supported_hyperv_features = [
        "vapic",
        "relaxes",
        "spinlocks",
        "vendorid",
        "evmcs",
    ]

    test_dict = node_label_checker(
        node_label_dict=nodes_labels_dict,
        label_list=hw_supported_hyperv_features,
        dict_key="kvm-info",
    )
    assert not any(test_dict.values()), f"Some nodes have non required KVM labels: {test_dict}"


@pytest.mark.gating
@pytest.mark.polarion("CNV-6103")
@pytest.mark.x86_64
@pytest.mark.s390x
def test_updated_obsolete_cpus_in_node_labels(updated_kubevirt_cpus, nodes_labels_dict, kubevirt_config):
    """
    Test user-added obsolete CPU does not appear in node labels.
    """
    test_dict = node_label_checker(
        node_label_dict=nodes_labels_dict,
        label_list=kubevirt_config[OBSOLETE_CPU].keys(),
        dict_key="cpu_models",
    )
    assert not any(test_dict.values()), f"Obsolete CPU found in labels\n{test_dict}"
