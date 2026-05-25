import logging
from copy import deepcopy
from typing import Any

from ocp_resources.node import Node

from utilities.constants import KUBERNETES_ARCH_LABEL

LOGGER = logging.getLogger(__name__)

KUBEVIRT_HCO_MULTI_ARCH_BOOT_IMAGES_ENABLED = "kubevirt_hco_multi_arch_boot_images_enabled"
MULTIARCH_DICT_ANNOTATION = "ssp.kubevirt.io/dict.architectures"

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


def get_control_plane_architecture(control_plane_nodes: list[Node]) -> str:
    """Return the architecture of the first control plane node.

    Assumes all control plane nodes share the same architecture.

    Args:
        control_plane_nodes: List of control plane Node objects.

    Returns:
        str: Architecture label value (e.g. "amd64", "arm64").
    """
    return control_plane_nodes[0].labels[KUBERNETES_ARCH_LABEL]


def get_modified_data_import_cron_template(
    common_templates: list[dict[str, Any]],
    name: str,
    managed_data_source: str,
    annotations: dict[str, str] | None = None,
) -> dict[str, Any]:
    template = deepcopy(common_templates[0])
    del template["status"]
    template["metadata"]["name"] = name
    template["spec"]["managedDataSource"] = managed_data_source
    if annotations is not None:
        template["metadata"].setdefault("annotations", {}).update(annotations)
    return template


def get_unsupported_arch_template(common_templates: list[dict[str, Any]]) -> dict[str, Any]:
    return get_modified_data_import_cron_template(
        common_templates=common_templates,
        name=CUSTOM_UNSUPPORTED_ARCH_CRON_NAME,
        managed_data_source=CUSTOM_MULTIARCH_DATASOURCE_NAME,
        annotations={MULTIARCH_DICT_ANNOTATION: "arm42"},
    )


def get_no_arch_annotation_template(common_templates: list[dict[str, Any]]) -> dict[str, Any]:
    template = get_modified_data_import_cron_template(
        common_templates=common_templates,
        name=CUSTOM_NO_ARCH_ANNOTATION_CRON_NAME,
        managed_data_source=CUSTOM_MULTIARCH_DATASOURCE_NAME,
    )
    template["metadata"].get("annotations", {}).pop(MULTIARCH_DICT_ANNOTATION, None)
    return template
