import logging

import pytest
from kubernetes.client import ApiException
from kubernetes.dynamic.exceptions import ForbiddenError
from ocp_resources.namespace import Namespace
from ocp_resources.template import Template
from timeout_sampler import TimeoutExpiredError

from tests.virt.cluster.common_templates.custom_namespace.utils import (
    verify_base_templates_exist_in_namespace,
    wait_for_edited_label_reconciliation,
    wait_for_template_by_name,
)
from utilities.constants import UNPRIVILEGED_USER, NamespacesNames

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.post_upgrade

TESTS_CLASS_NAME = "TestCustomNamespace"


@pytest.mark.s390x
@pytest.mark.usefixtures("base_templates", "opt_in_custom_template_namespace")
class TestCustomNamespace:
    @pytest.mark.polarion("CNV-8144")
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_custom_namespace")
    def test_base_templates_exist_in_custom_namespace(
        self,
        admin_client,
        base_templates,
        custom_vm_template_namespace,
    ):
        verify_base_templates_exist_in_namespace(
            client=admin_client,
            original_base_templates=base_templates,
            namespace=custom_vm_template_namespace,
        )

    @pytest.mark.polarion("CNV-8238")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_unprivileged_user_cannot_access_custom_namespace",
        depends=[f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_custom_namespace"],
    )
    def test_unprivileged_user_cannot_access_custom_namespace(
        self,
        unprivileged_client,
        custom_vm_template_namespace,
    ):
        template_name = "rhel8-server-tiny"
        with pytest.raises(
            ForbiddenError,
            match=rf'.*[\\]+"{template_name}[\\]+" is forbidden: '
            rf'User [\\]+"{UNPRIVILEGED_USER}[\\]+" cannot get resource [\\]+"templates[\\]+".*',
        ):
            Template(
                client=unprivileged_client,
                name=template_name,
                namespace=custom_vm_template_namespace.name,
            ).instance

    @pytest.mark.polarion("CNV-8142")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_deleted_template_in_custom_namespace_reconciled",
        depends=[f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_custom_namespace"],
    )
    def test_deleted_template_in_custom_namespace_reconciled(
        self,
        admin_client,
        custom_vm_template_namespace,
        deleted_custom_namespace_template,
    ):
        try:
            wait_for_template_by_name(
                client=admin_client,
                namespace_name=custom_vm_template_namespace.name,
                name=deleted_custom_namespace_template.name,
            )
        except TimeoutExpiredError:
            LOGGER.error(
                f"Template {deleted_custom_namespace_template.name} in custom namespace "
                f"{custom_vm_template_namespace.name} not reconciled after deletion."
            )
            raise

    @pytest.mark.polarion("CNV-8164")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_edited_template_in_custom_namespace_reconciled",
        depends=[f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_custom_namespace"],
    )
    def test_edited_template_in_custom_namespace_reconciled(
        self,
        admin_client,
        custom_vm_template_namespace,
        edited_custom_namespace_template,
    ):
        try:
            wait_for_edited_label_reconciliation(template=edited_custom_namespace_template)
        except TimeoutExpiredError:
            LOGGER.error(
                f"Template {edited_custom_namespace_template.name} in custom namespace "
                f"{custom_vm_template_namespace.name} not reconciled after label edit."
            )
            raise

    @pytest.mark.polarion("CNV-8163")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_create_vm_custom_template_namespace",
        depends=[f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_custom_namespace"],
    )
    def test_create_vm_custom_template_namespace(
        self,
        first_base_template,
        custom_vm_template_namespace,
        vm_from_template_labels,
    ):
        try:
            vm_from_template_labels.deploy()
        except ApiException:
            LOGGER.error(
                f"Failed to create VM using template {first_base_template.name} "
                f"from custom namespace {custom_vm_template_namespace.name}"
            )
            raise

    @pytest.mark.polarion("CNV-8143")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_default_namespace_after_revert",
        depends=[f"{TESTS_CLASS_NAME}::test_unprivileged_user_cannot_access_custom_namespace"],
    )
    def test_base_templates_exist_in_default_namespace_after_revert(
        self,
        admin_client,
        hco_namespace,
        base_templates,
        deleted_base_templates,
        opted_out_custom_template_namespace,
    ):
        verify_base_templates_exist_in_namespace(
            client=admin_client,
            original_base_templates=base_templates,
            namespace=Namespace(name=NamespacesNames.OPENSHIFT),
        )

    @pytest.mark.polarion("CNV-8152")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_deleted_template_default_namespace_reconciled_after_revert",
        depends=[
            f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_default_namespace_after_revert",
        ],
    )
    def test_deleted_template_default_namespace_reconciled_after_revert(
        self, admin_client, deleted_default_namespace_template
    ):
        try:
            wait_for_template_by_name(
                client=admin_client,
                namespace_name=NamespacesNames.OPENSHIFT,
                name=deleted_default_namespace_template.name,
            )
        except TimeoutExpiredError:
            LOGGER.error(
                f"Template {deleted_default_namespace_template.name} in default namespace "
                f"{NamespacesNames.OPENSHIFT} not reconciled after deletion."
            )
            raise

    @pytest.mark.polarion("CNV-8189")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_edited_template_default_namespace_reconciled_after_revert",
        depends=[
            f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_default_namespace_after_revert",
        ],
    )
    def test_edited_template_default_namespace_reconciled_after_revert(
        self, admin_client, edited_default_namespace_template
    ):
        try:
            wait_for_edited_label_reconciliation(template=edited_default_namespace_template)
        except TimeoutExpiredError:
            LOGGER.error(
                f"Template {edited_default_namespace_template.name} in default namespace "
                f"{NamespacesNames.OPENSHIFT} not reconciled after label edit."
            )
            raise

    @pytest.mark.polarion("CNV-8190")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_edited_template_custom_namespace_not_reconciled_after_revert",
        depends=[
            f"{TESTS_CLASS_NAME}::test_base_templates_exist_in_default_namespace_after_revert",
        ],
    )
    def test_edited_template_custom_namespace_not_reconciled_after_revert(
        self,
        admin_client,
        custom_vm_template_namespace,
        edited_custom_namespace_template,
    ):
        with pytest.raises(TimeoutExpiredError):
            wait_for_edited_label_reconciliation(template=edited_custom_namespace_template)
            LOGGER.error(
                f"Template {edited_custom_namespace_template.name} in custom namespace "
                f"{custom_vm_template_namespace.name} reconciled after label edit post-revert."
            )
