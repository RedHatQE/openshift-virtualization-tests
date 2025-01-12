import logging
from contextlib import contextmanager

from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.template import Template
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_1MIN, TIMEOUT_2MIN, TIMEOUT_3MIN
from utilities.hco import wait_for_hco_conditions
from utilities.ssp import wait_for_ssp_conditions
from utilities.virt import VirtualMachineForTestsFromTemplate, get_base_templates_list

TEMPLATE_PATCH_LABEL = f"{Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"
TEMPLATE_PATCH_LABEL_VALUE = "general-kenobi"

LOGGER = logging.getLogger(__name__)


def wait_for_ssp_custom_template_namespace(ssp_resource, namespace):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=2,
            func=lambda: ssp_resource.instance.spec.commonTemplates.namespace == namespace.name,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"SSP Resource not updated with commonTemplates.namespace: {namespace.name}")
        raise


def get_template_by_name(client, namespace_name, name):
    template = Template(client=client, name=name, namespace=namespace_name)
    assert template.exists, f"Template {name} was not found in namespace {namespace_name}"
    return template


def wait_for_template_by_name(client, namespace_name, name, timeout=TIMEOUT_3MIN):
    for sample in TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=get_template_by_name,
        exceptions_dict={AssertionError: []},
        client=client,
        namespace_name=namespace_name,
        name=name,
    ):
        if sample:
            LOGGER.info(f"Template {name} found in namespace {namespace_name}")
            return


def delete_template_by_name(admin_client, namespace_name, template_name):
    template = get_template_by_name(
        client=admin_client,
        namespace_name=namespace_name,
        name=template_name,
    )
    template.clean_up()
    return template


def patch_template_labels(admin_client, hco_namespace, template):
    with ResourceEditor(
        patches={template: {"metadata": {"labels": {TEMPLATE_PATCH_LABEL: TEMPLATE_PATCH_LABEL_VALUE}}}}
    ):
        yield template

    wait_for_ssp_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )


def wait_for_edited_label_reconciliation(template, timeout=TIMEOUT_3MIN):
    for sample in TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=lambda: template.instance.metadata.labels[TEMPLATE_PATCH_LABEL] != TEMPLATE_PATCH_LABEL_VALUE,
    ):
        if sample:
            return


def verify_base_templates_exist_in_namespace(client, original_base_templates, namespace):
    expected_template_names = {template.name for template in original_base_templates}
    missing_template_names = set()
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=2,
            func=get_base_templates_list,
            client=client,
        ):
            if sample:
                current_template_names = {template.name for template in sample if template.namespace == namespace.name}
                missing_template_names = expected_template_names - current_template_names
                if not missing_template_names:
                    return True

    except TimeoutExpiredError:
        LOGGER.error(f"Templates not in namespace {namespace.name}: {missing_template_names}")
        raise


def extract_template_labels(template_labels):
    extracted_vm_template_labels = {}
    for key in template_labels.keys():
        label_prefix, label_name = key.split("/")
        if label_prefix in (
            Template.Labels.OS,
            Template.Labels.WORKLOAD,
            Template.Labels.FLAVOR,
        ):
            extracted_vm_template_labels[label_prefix] = label_name

    return extracted_vm_template_labels


@contextmanager
def diskless_vm_from_template(client, name, namespace, base_template_labels):
    extracted_template_labels = extract_template_labels(template_labels=base_template_labels)
    template_labels = Template.generate_template_labels(
        os=extracted_template_labels[Template.Labels.OS],
        workload=extracted_template_labels[Template.Labels.WORKLOAD],
        flavor=extracted_template_labels[Template.Labels.FLAVOR],
    )
    vm = VirtualMachineForTestsFromTemplate(
        client=client,
        name=name,
        namespace=namespace.name,
        labels=template_labels,
        diskless_vm=True,
    )
    yield vm
    if vm.exists:
        vm.clean_up()


def remove_templates(templates_list):
    for template in templates_list:
        template.delete()
    for template in templates_list:
        template.wait_deleted(timeout=TIMEOUT_2MIN)
