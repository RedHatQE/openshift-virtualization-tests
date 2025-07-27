import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.template import Template
from pytest_testconfig import py_config

from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_OS
from utilities.constants import NamespacesNames
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    add_validation_rule_to_annotation,
    running_vm,
)

LOGGER = logging.getLogger(__name__)


class CustomTemplate(Template):
    def __init__(
        self,
        name,
        namespace,
        source_template,
        vm_validation_rule=None,
    ):
        """
        Custom template based on a common template.

        Args:
            source_template (Template): Template to be based on
            vm_validation_rule (str, optional): VM validation rule added to the VM annotation

        """
        super().__init__(
            name=name,
            namespace=namespace,
        )
        self.source_template = source_template
        self.vm_validation_rule = vm_validation_rule

    def to_dict(self):
        template_dict = self.source_template.instance.to_dict()
        self.remove_template_metadata_unique_keys(template_metadata=template_dict["metadata"])
        template_dict["metadata"].update({
            "labels": {f"{self.ApiGroup.APP_KUBERNETES_IO}/name": self.name},
            "name": self.name,
            "namespace": self.namespace,
        })
        if self.vm_validation_rule:
            template_dict = self.get_template_dict_with_added_vm_validation_rule(template_dict=template_dict)
        self.res = template_dict

    def get_template_dict_with_added_vm_validation_rule(self, template_dict):
        modified_template_dict = template_dict.copy()
        vm_annotation = modified_template_dict["objects"][0]["metadata"]["annotations"]
        add_validation_rule_to_annotation(vm_annotation=vm_annotation, vm_validation_rule=self.vm_validation_rule)
        return modified_template_dict

    @staticmethod
    def remove_template_metadata_unique_keys(template_metadata):
        del template_metadata["resourceVersion"]
        del template_metadata["uid"]
        del template_metadata["creationTimestamp"]


@pytest.fixture()
def custom_template_from_base_template(request, namespace):
    base_template = Template(namespace=NamespacesNames.OPENSHIFT, name=request.param["base_template_name"])
    with CustomTemplate(
        name=request.param["new_template_name"],
        namespace=namespace.name,
        source_template=base_template,
        vm_validation_rule=request.param.get("validation_rule"),
    ) as custom_template:
        yield custom_template


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class",
    [
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST.get("image_path"),
                "dv_size": FEDORA_LATEST.get("dv_size"),
                "storage_class": py_config["default_storage_class"],
            },
        ),
    ],
    indirect=True,
)
class TestBaseCustomTemplates:
    @pytest.mark.parametrize(
        "custom_template_from_base_template, vm_name",
        [
            pytest.param(
                {
                    "base_template_name": f"fedora-{Template.Workload.DESKTOP}-{Template.Flavor.SMALL}",
                    "new_template_name": "fedora-custom-template-for-test",
                },
                "vm-from-custom-template",
                marks=pytest.mark.polarion("CNV-7957"),
            ),
            pytest.param(
                {
                    "base_template_name": f"fedora-{Template.Workload.DESKTOP}-{Template.Flavor.SMALL}",
                    "new_template_name": "fedora-custom-template-disks-wildcard",
                    "validation_rule": {
                        "name": "volumes-validation",
                        "path": "jsonpath::.spec.volumes[*].name",
                        "rule": "string",
                        "message": "the volumes name must be non-empty",
                        "values": ["rootdisk", "cloudinitdisk"],
                    },
                },
                "vm-from-custom-template-volumes-validation",
                marks=pytest.mark.polarion("CNV-5588"),
            ),
        ],
        indirect=["custom_template_from_base_template"],
    )
    def test_vm_from_base_custom_template(
        self,
        unprivileged_client,
        namespace,
        golden_image_data_source_scope_class,
        custom_template_from_base_template,
        vm_name,
    ):
        with VirtualMachineForTestsFromTemplate(
            name=vm_name,
            namespace=namespace.name,
            client=unprivileged_client,
            template_object=custom_template_from_base_template,
            data_source=golden_image_data_source_scope_class,
        ) as custom_vm:
            running_vm(vm=custom_vm)

    @pytest.mark.parametrize(
        "custom_template_from_base_template",
        [
            pytest.param(
                {
                    "base_template_name": f"fedora-{Template.Workload.DESKTOP}-{Template.Flavor.SMALL}",
                    "new_template_name": "custom-fedora-template-core-validation",
                    "validation_rule": {
                        "name": "minimal-required-cpu-core",
                        "path": "jsonpath::.spec.domain.cpu.cores.",
                        "rule": "integer",
                        "message": "This VM has too many cores",
                        "max": 2,
                    },
                },
            )
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-7958")
    def test_custom_template_vm_validation(
        self,
        unprivileged_client,
        namespace,
        golden_image_data_source_scope_class,
        custom_template_from_base_template,
    ):
        with pytest.raises(UnprocessibleEntityError, match=r".*This VM has too many cores.*"):
            with VirtualMachineForTestsFromTemplate(
                name="vm-from-custom-template-core-validation",
                namespace=custom_template_from_base_template.namespace,
                client=unprivileged_client,
                template_object=custom_template_from_base_template,
                data_source=golden_image_data_source_scope_class,
                cpu_cores=3,
            ) as vm_from_template:
                pytest.fail(f"VM validation failed on {vm_from_template.name}")
