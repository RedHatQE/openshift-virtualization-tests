import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.data_source import DataSource
from ocp_resources.resource import ResourceEditor
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.os_params import FEDORA_LATEST
from utilities.constants import OS_FLAVOR_FEDORA, NamespacesNames
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import CustomTemplate, VirtualMachineForTests, VirtualMachineForTestsFromTemplate, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def custom_template_from_base_template(request, admin_client, unprivileged_client, namespace):
    base_template = Template(
        client=admin_client, namespace=NamespacesNames.OPENSHIFT, name=request.param["base_template_name"]
    )
    with CustomTemplate(
        name=request.param["new_template_name"],
        client=unprivileged_client,
        namespace=namespace.name,
        source_template=base_template,
        vm_validation_rule=request.param.get("validation_rule"),
    ) as custom_template:
        yield custom_template


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class",
    [pytest.param({"os_dict": FEDORA_LATEST})],
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
        golden_image_data_volume_template_for_test_scope_class,
        custom_template_from_base_template,
        vm_name,
    ):
        with VirtualMachineForTestsFromTemplate(
            name=vm_name,
            namespace=namespace.name,
            client=unprivileged_client,
            template_object=custom_template_from_base_template,
            data_volume_template=golden_image_data_volume_template_for_test_scope_class,
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
        golden_image_data_volume_template_for_test_scope_class,
        custom_template_from_base_template,
    ):
        with pytest.raises(UnprocessibleEntityError, match=r".*This VM has too many cores.*"):
            with VirtualMachineForTestsFromTemplate(
                name="vm-from-custom-template-core-validation",
                namespace=custom_template_from_base_template.namespace,
                client=unprivileged_client,
                template_object=custom_template_from_base_template,
                data_volume_template=golden_image_data_volume_template_for_test_scope_class,
                cpu_cores=3,
            ) as vm_from_template:
                pytest.fail(f"VM validation failed on {vm_from_template.name}")


class TestCustomTemplatesChangesWebhookValidation:
    """
    Test class contains test for covering change webhook validation.
    Additional class added for lowering code complexity
    """

    @pytest.mark.parametrize(
        "custom_template_from_base_template",
        [
            pytest.param(
                {
                    "base_template_name": f"fedora-{Template.Workload.DESKTOP}-{Template.Flavor.SMALL}",
                    "new_template_name": "custom-fedora-template-webhook-validation",
                    "validation_rule": None,
                },
            )
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-13744")
    def test_no_validation_annotation_missing_parent_template(
        self,
        custom_template_from_base_template,
        unprivileged_client,
        namespace,
        golden_images_namespace,
    ) -> None:
        """
        Tests uses VirtualMachineForTests and its label instance attribute due to a need to:
        - create a VM without metadata.annotations.validations entries
        and
        - adding labels to metadata.labels not to spec.metadata.labels
        Detailed steps are desribed in Polarion CNV-13744
        """
        with VirtualMachineForTests(
            name="vm-from-custom-template-webhook-validation",
            namespace=namespace.name,
            client=unprivileged_client,
            data_volume_template=data_volume_template_with_source_ref_dict(
                data_source=DataSource(name=OS_FLAVOR_FEDORA, namespace=golden_images_namespace.name),
                storage_class=py_config["default_storage_class"],
            ),
            label={
                "vm.kubevirt.io/template": "custom-fedora-template-webhook-validation",
                "vm.kubevirt.io/template.namespace": namespace.name,
            },
        ) as custom_vm:
            custom_template_from_base_template.clean_up()
            ResourceEditor({custom_vm: {"metadata": {"annotations": {"test.annot": "my-test-annotation-1"}}}}).update()
