import uuid

from ocp_resources.resource import Resource

from libs.vm.spec import (
    Affinity,
    LabelSelector,
    LabelSelectorRequirement,
    PodAffinityTerm,
    PodAntiAffinity,
)


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
