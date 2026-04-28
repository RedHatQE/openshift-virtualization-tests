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

    Args:
        label: Tuple of (key, value) to match pods for anti-affinity.
        namespaces: Optional list of namespaces to search for matching pods.
                   If None, searches all namespaces (cluster-wide).

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
