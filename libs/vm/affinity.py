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
                )
            ]
        )
    )
