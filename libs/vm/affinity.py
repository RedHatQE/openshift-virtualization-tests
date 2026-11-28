from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Final

from dacite import from_dict
from ocp_resources.resource import Resource

from libs.vm.spec import (
    Affinity,
    LabelSelector,
    LabelSelectorRequirement,
    NodeAffinity,
    NodeSelectorTerm,
    NodeSelectorTerms,
    PodAffinity,
    PodAffinityTerm,
    PodAntiAffinity,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import ResourceInstance

    from libs.vm.vm import BaseVirtualMachine

WAIT_FOR_VMI_TEMPLATE_AFFINITY_TIMEOUT_SEC: Final[int] = 120


class VMIAffinityNotSyncedError(Exception):
    pass


def new_label(key_prefix: str) -> tuple[str, str]:
    return f"{key_prefix}-{uuid.uuid4().hex[:8]}", "true"


def new_pod_anti_affinity(label: tuple[str, str], namespaces: list[str] | None = None) -> Affinity:
    """Create pod anti-affinity to schedule pods on different nodes.

    Kubernetes behavior: Omitting both namespaceSelector and namespaces limits
    anti-affinity to pods in the same namespace. Setting namespaceSelector={} makes the
    rule cross-namespace.

    Args:
        label: Tuple of (key, value) to match pods for anti-affinity.
        namespaces: Optional list of namespaces to search for matching pods.
            If None, matches pods across all namespaces (cluster-wide).
            If provided, limits matching to those specific namespaces.

    Returns:
        Affinity: Affinity object with podAntiAffinity configured.
    """
    (key, value) = label
    return Affinity(
        podAntiAffinity=PodAntiAffinity(
            requiredDuringSchedulingIgnoredDuringExecution=[
                PodAffinityTerm(
                    labelSelector=LabelSelector(
                        matchExpressions=[LabelSelectorRequirement(key=key, values=[value], operator="In")]
                    ),
                    topologyKey=f"{Resource.ApiGroup.KUBERNETES_IO}/hostname",
                    namespaces=namespaces,
                    namespaceSelector={} if namespaces is None else None,
                )
            ]
        )
    )


def new_pod_affinity(label: tuple[str, str], namespaces: list[str] | None = None) -> Affinity:
    """Create pod affinity to co-locate with pods matching the label.

    Kubernetes behavior: Omitting both namespaceSelector and namespaces limits
    affinity to pods in the same namespace. Setting namespaceSelector={} makes the
    rule cross-namespace.

    Args:
        label: Tuple of (key, value) to match pods for co-location.
        namespaces: Optional list of namespaces to search for matching pods.
            If None, matches pods across all namespaces (cluster-wide).
            If provided, limits matching to those specific namespaces.

    Returns:
        Affinity: Affinity object with podAffinity configured.
    """
    (key, value) = label
    return Affinity(
        podAffinity=PodAffinity(
            requiredDuringSchedulingIgnoredDuringExecution=[
                PodAffinityTerm(
                    labelSelector=LabelSelector(
                        matchExpressions=[LabelSelectorRequirement(key=key, values=[value], operator="In")]
                    ),
                    topologyKey=f"{Resource.ApiGroup.KUBERNETES_IO}/hostname",
                    namespaces=namespaces,
                    namespaceSelector={} if namespaces is None else None,
                )
            ]
        )
    )


def new_node_affinity(key: str, exists: bool) -> Affinity:
    """Create a node affinity based on whether target nodes must carry the given label.

    Args:
        key: Node role label key to match.
        exists: If True, target nodes must carry the label (Exists operator).
            If False, target nodes must NOT carry the label (DoesNotExist operator).

    Returns:
        Affinity object with nodeAffinity configured.
    """
    operator = "Exists" if exists else "DoesNotExist"
    return Affinity(
        nodeAffinity=NodeAffinity(
            requiredDuringSchedulingIgnoredDuringExecution=NodeSelectorTerms(
                nodeSelectorTerms=[
                    NodeSelectorTerm(matchExpressions=[LabelSelectorRequirement(key=key, operator=operator)])
                ]
            )
        )
    )


def wait_for_vmi_template_affinity(
    vm: BaseVirtualMachine,
    affinity: Affinity | None,
    timeout: int = WAIT_FOR_VMI_TEMPLATE_AFFINITY_TIMEOUT_SEC,
    resource_version: str | None = None,
) -> None:
    """Wait until the running VMI's affinity matches the expected configuration.

    virt-controller propagates VM template affinity changes onto the running VMI
    asynchronously, not as part of the patch itself. Callers that depend on the
    VMI already reflecting the new affinity should wait for this rather than
    assume it applies synchronously.

    Args:
        vm: The virtual machine whose VMI should be updated.
        affinity: Affinity applied on the VM template, or None if cleared.
        timeout: Maximum seconds to wait.
        resource_version: VMI resource version captured before patching the VM.

    Raises:
        VMIAffinityNotSyncedError: If the VMI spec does not match within timeout.
    """
    vmi = vm.vmi
    vmi_instance = vmi.instance
    if _vmi_spec_affinity(vmi_object=vmi_instance) == affinity:
        return

    watch_from_resource_version = resource_version or vmi_instance.metadata.resourceVersion
    for event in vmi.watcher(timeout=timeout, resource_version=watch_from_resource_version):
        if event["type"] != "MODIFIED":
            continue
        if _vmi_spec_affinity(vmi_object=event["object"]) == affinity:
            return

    last_observed_affinity = _vmi_spec_affinity(vmi_object=vmi.instance)
    raise VMIAffinityNotSyncedError(
        f"VMI {vm.name}: template affinity was not synced to the running VMI within {timeout}s. "
        f"Expected affinity: {affinity!r}. Last observed affinity: {last_observed_affinity!r}."
    )


def _vmi_spec_affinity(vmi_object: ResourceInstance) -> Affinity | None:
    spec_affinity = vmi_object.to_dict()["spec"].get("affinity")
    return from_dict(data_class=Affinity, data=spec_affinity) if spec_affinity else None
