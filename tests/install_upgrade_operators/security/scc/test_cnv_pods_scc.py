# -*- coding: utf-8 -*-

"""
Tests to check, HCO Namespace Pod's, Security Context Constraint
"""

import logging

import pytest

from utilities.constants import (
    BRIDGE_MARKER,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_CSI,
    LINUX_BRIDGE,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.gating]


LOGGER = logging.getLogger(__name__)
POD_SCC_ALLOWLIST = [
    "restricted",
    "restricted-v2",
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_CSI,
    "containerized-data-importer",
    BRIDGE_MARKER,
    LINUX_BRIDGE,
    "nmstate",
    "ovs-cni-marker",
    "kubevirt-handler",
    "kubevirt-node-labeller",
]


def verify_cnv_pods_with_scc(cnv_pods):
    failed_pods = []
    for pod in cnv_pods:
        if not pod.instance.metadata.annotations.get("openshift.io/scc"):
            failed_pods.append(pod.name)
    assert not failed_pods, f"The following pods do not have scc annotation: {failed_pods}"


@pytest.mark.polarion("CNV-4438")
def test_openshift_io_scc_exists(cnv_pods):
    """
    Validate that Pods in openshift-cnv have 'openshift.io/scc' annotation
    """
    verify_cnv_pods_with_scc(cnv_pods=cnv_pods)


@pytest.fixture()
def pods_not_allowlisted_or_anyuid(cnv_pods):
    pod_names = []
    for pod in cnv_pods:
        annotations = pod.instance.metadata.annotations.get("openshift.io/scc")
        if (
            annotations != "anyuid" or not pod.name.startswith(CLUSTER_NETWORK_ADDONS_OPERATOR)
        ) and annotations not in POD_SCC_ALLOWLIST:
            pod_names.append(pod.name)
    return pod_names


@pytest.mark.polarion("CNV-4211")
def test_pods_scc_in_allowlist(pods_not_allowlisted_or_anyuid):
    """
    Validate that Pods in openshift-cnv have SCC from a predefined allowlist
    """
    assert not pods_not_allowlisted_or_anyuid, (
        f"Pods not conforming to SCC annotation conditions: pods={pods_not_allowlisted_or_anyuid}"
    )
