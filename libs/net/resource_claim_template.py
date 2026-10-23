from __future__ import annotations

from typing import Any

from kubernetes.dynamic import DynamicClient
from ocp_resources.resource import NamespacedResource


class ResourceClaimTemplate(NamespacedResource):
    api_group: str = "resource.k8s.io"
    kind: str = "ResourceClaimTemplate"

    def __init__(
        self,
        name: str,
        namespace: str,
        client: DynamicClient,
        claim_template_spec: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Create and manage a ResourceClaimTemplate.

        Args:
            name: ResourceClaimTemplate name.
            namespace: Namespace for the template.
            client: Kubernetes dynamic client.
            claim_template_spec: ``spec`` field of the ResourceClaimTemplate manifest
                (nested ``spec.devices`` structure). Ignored when ``kind_dict`` or
                ``yaml_file`` is provided.
            **kwargs: Additional arguments forwarded to ``NamespacedResource``.
        """
        super().__init__(name=name, namespace=namespace, client=client, **kwargs)
        self._claim_template_spec = claim_template_spec

    def to_dict(self) -> None:
        """Populate ``self.res`` with the resource manifest.

        If neither ``kind_dict`` nor ``yaml_file`` is set, assign the supplied claim
        template spec to ``self.res["spec"]``.
        """
        super().to_dict()
        if not self.kind_dict and not self.yaml_file:
            self.res["spec"] = self._claim_template_spec
