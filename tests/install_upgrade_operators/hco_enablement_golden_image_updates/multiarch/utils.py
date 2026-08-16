from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.ssp import SSP

KUBEVIRT_HCO_MULTI_ARCH_BOOT_IMAGES_ENABLED = "kubevirt_hco_multi_arch_boot_images_enabled"
MULTIARCH_DICT_ANNOTATION = "ssp.kubevirt.io/dict.architectures"
MULTIARCH_MANAGED_CRS = [SSP, KubeVirt, CDI]

CUSTOM_MULTIARCH_DATASOURCE_NAME = "custom-multiarch-datasource"
CUSTOM_UNSUPPORTED_ARCH_CRON_NAME = "custom-unsupported-arch-cron"
CUSTOM_NO_ARCH_ANNOTATION_CRON_NAME = "custom-no-arch-annotation-cron"

KUBEVIRT_HCO_DATAIMPORTCRONTEMPLATE_WITH_SUPPORTED_ARCHITECTURES_QUERY = (
    "kubevirt_hco_dataimportcrontemplate_with_supported_architectures"
    "{{data_import_cron_name='{cron_name}', managed_data_source_name='{ds_name}'}}"
)
KUBEVIRT_HCO_DATAIMPORTCRONTEMPLATE_WITH_ARCHITECTURE_ANNOTATION_QUERY = (
    "kubevirt_hco_dataimportcrontemplate_with_architecture_annotation"
    "{{data_import_cron_name='{cron_name}', managed_data_source_name='{ds_name}'}}"
)


def get_modified_data_import_cron_template(
    common_templates: list[dict[str, Any]],
    name: str,
    managed_data_source: str,
    annotations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a custom DataImportCronTemplate based on the first common template.

    Args:
        common_templates: List of common templates from HCO status.
        name: Name for the custom template.
        managed_data_source: DataSource name this template manages.
        annotations: Optional annotations to merge into the template metadata.

    Returns:
        dict[str, Any]: A deep copy of the first common template with customized name,
            managed data source, status removed, and optional annotations.
    """
    template = deepcopy(common_templates[0])
    del template["status"]
    template["metadata"]["name"] = name
    template["spec"]["managedDataSource"] = managed_data_source
    if annotations is not None:
        template["metadata"].setdefault("annotations", {}).update(annotations)
    return template


def get_unsupported_arch_template(common_templates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a custom template annotated with an architecture unsupported by the cluster."""
    return get_modified_data_import_cron_template(
        common_templates=common_templates,
        name=CUSTOM_UNSUPPORTED_ARCH_CRON_NAME,
        managed_data_source=CUSTOM_MULTIARCH_DATASOURCE_NAME,
        annotations={MULTIARCH_DICT_ANNOTATION: "arm42"},
    )


def get_no_arch_annotation_template(common_templates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a custom template with the architecture annotation removed."""
    template = get_modified_data_import_cron_template(
        common_templates=common_templates,
        name=CUSTOM_NO_ARCH_ANNOTATION_CRON_NAME,
        managed_data_source=CUSTOM_MULTIARCH_DATASOURCE_NAME,
    )
    # annotations is optional in Kubernetes metadata
    template["metadata"].get("annotations", {}).pop(MULTIARCH_DICT_ANNOTATION, None)
    return template
