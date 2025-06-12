"""
Base templates test
"""

import json
import logging
import os
import re
from xml.etree import ElementTree

import bitmath
import jsons
import pytest
from ocp_resources.resource import Resource
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.os_params import FEDORA_LATEST_LABELS
from tests.virt.cluster.common_templates.constants import HYPERV_FEATURES_LABELS_VM_YAML
from utilities.constants import DATA_SOURCE_NAME, DATA_SOURCE_NAMESPACE, Images

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]

LOGGER = logging.getLogger(__name__)

LINUX_WORKLOADS_LIST = list(jsons.dump(Template.Workload).values())
# SAP HANA templates are no more part of base templates
LINUX_WORKLOADS_LIST.remove(Template.Workload.SAPHANA)
LINUX_FLAVORS_LIST = list(jsons.dump(Template.Flavor).values())
FEDORA_FLAVORS_LIST = [Template.Flavor.SMALL, Template.Flavor.MEDIUM, Template.Flavor.LARGE]
WINDOWS_FLAVOR_LIST = [Template.Flavor.MEDIUM, Template.Flavor.LARGE]
WINDOWS2K_WORKLOAD_LIST = [Template.Workload.SERVER, Template.Workload.HIGHPERFORMANCE]
WINDOWS_FOR_DESKTOP_WORKLOAD_LIST = [
    Template.Workload.DESKTOP,
    Template.Workload.HIGHPERFORMANCE,
]
VM_EXPECTED_ANNOTATION_KEYS = [
    Template.VMAnnotations.FLAVOR,
    Template.VMAnnotations.OS,
    Template.VMAnnotations.WORKLOAD,
]


def fetch_osinfo_memory(osinfo_file_path, memory_test, resources_arch):
    """Fetch memory min and max values from the osinfo files."""

    xml_doc = ElementTree.parse(osinfo_file_path)
    root = xml_doc.getroot()
    resources = root.findall("./os/resources")
    return [
        int(resource.findtext(f"./{memory_test}/ram"))
        for resource in resources
        if resources_arch == resource.attrib["arch"]
    ]


def validate_memory(memory_test, template_memory_value, osinfo_memory_value):
    """Validate the minimum and maximum memory values."""
    if memory_test == "minimum":
        return bitmath.parse_string_unsafe(template_memory_value) >= bitmath.Byte(osinfo_memory_value)
    elif memory_test == "maximum":
        return bitmath.parse_string_unsafe(template_memory_value) < bitmath.Byte(osinfo_memory_value)


def check_default_and_validation_memory(get_base_templates, osinfo_memory_value, os_type, memory_test, osinfo_filename):
    for template in [template for template in get_base_templates if os_type in template.name]:
        LOGGER.info(f"Currently validating template {template.name} against osinfo file {osinfo_filename}.xml")
        template_instance = template.instance
        memory_guest = template_instance.objects[0].spec.template.spec.domain.get("memory", {}).get("guest")
        assert memory_guest, "Guest memory value not set in template!"

        validation_map = json.loads(
            template_instance.to_dict()["objects"][0]["metadata"]["annotations"]["vm.kubevirt.io/validations"]
        )
        min_validation_memory_value = validation_map[0]["min"]

        LOGGER.info(f"Checking default requests.memory value against osinfo file {osinfo_filename}.xml")
        assert validate_memory(
            memory_test=memory_test,
            template_memory_value=memory_guest,
            osinfo_memory_value=osinfo_memory_value[0],
        )

        LOGGER.info(f"Checking validations minimal-required-memory value against osinfo file {osinfo_filename}.xml")
        assert validate_memory(
            memory_test=memory_test,
            template_memory_value=min_validation_memory_value,
            osinfo_memory_value=osinfo_memory_value[0],
        )


def get_rhel_templates_list():
    rhel_major_releases_list = ["7", "8", "9"]
    return [
        f"rhel{release}-{workload}-{flavor}"
        for release in rhel_major_releases_list
        for flavor in LINUX_FLAVORS_LIST
        for workload in LINUX_WORKLOADS_LIST
    ]


def get_fedora_templates_list():
    return [f"fedora-{workload}-{flavor}" for flavor in FEDORA_FLAVORS_LIST for workload in LINUX_WORKLOADS_LIST]


def get_windows_templates_list():
    windows10 = "windows10"
    windows11 = "windows11"
    windows_os_list = [windows10, windows11, "windows2k16", "windows2k19", "windows2k22", "windows2k25"]
    windows_for_desktop_names_list = [windows10, windows11]

    windows_workload_list = []
    for release in windows_os_list:
        if release in windows_for_desktop_names_list:
            windows_workload_list.extend([f"{release}-{workload}" for workload in WINDOWS_FOR_DESKTOP_WORKLOAD_LIST])
        else:
            windows_workload_list.extend([f"{release}-{workload}" for workload in WINDOWS2K_WORKLOAD_LIST])

    return [f"{release}-{flavor}" for release in windows_workload_list for flavor in WINDOWS_FLAVOR_LIST]


def get_centos_templates_list():
    centos_releases_list = ["-stream9"]
    return [
        f"centos{release}-{workload}-{flavor}"
        for release in centos_releases_list
        for flavor in LINUX_FLAVORS_LIST
        for workload in [Template.Workload.SERVER, Template.Workload.DESKTOP]
    ]


@pytest.fixture()
def common_templates_expected_list():
    common_templates_list = get_rhel_templates_list()
    common_templates_list += get_fedora_templates_list()
    common_templates_list += get_windows_templates_list()
    common_templates_list += get_centos_templates_list()
    return common_templates_list


@pytest.fixture()
def os_base_templates(request, base_templates):
    os_name = request.param
    os_templates = [
        template
        for template in base_templates
        if any(label.startswith(f"{Template.Labels.OS}/{os_name}") for label in template.labels.keys())
    ]
    assert os_templates, f"No {os_name} templates found"
    return os_templates


@pytest.fixture()
def templates_provider_support_dict():
    provider_url_annotation = Template.Annotations.PROVIDER_URL
    support_level_annotation = Template.Annotations.PROVIDER_SUPPORT_LEVEL
    provider_annotation = Template.Annotations.PROVIDER
    general_provider_support_dict = {provider_annotation: "Red Hat"}
    redhat_support_dict = {
        support_level_annotation: "Full",
        provider_url_annotation: "https://www.redhat.com",
    }
    provider_support_dict = {
        "windows": {**redhat_support_dict, **general_provider_support_dict},
        "rhel": {**redhat_support_dict, **general_provider_support_dict},
        "fedora": {
            support_level_annotation: "Community",
            provider_url_annotation: "https://www.fedoraproject.org",
            **general_provider_support_dict,
        },
        "centos": {
            support_level_annotation: "Community",
            provider_url_annotation: "https://www.centos.org",
            **general_provider_support_dict,
        },
        "windows_experimental": {
            support_level_annotation: "Experimental",
            provider_url_annotation: "https://www.redhat.com",
            provider_annotation: "Red Hat - Tech Preview",
        },
    }
    return provider_support_dict


def verify_annotations_match(obj_annotations, expected):
    return sorted(obj_annotations) == sorted(expected)


@pytest.mark.gating
@pytest.mark.polarion("CNV-1069")
def test_base_templates_annotations(base_templates, common_templates_expected_list):
    """
    Check all CNV templates exists, by label: template.kubevirt.io/type=base
    """
    base_templates = [template.name.split("-v")[0] for template in base_templates]
    extra_templates = set(base_templates) - set(common_templates_expected_list)
    missing_templates = set(common_templates_expected_list) - set(base_templates)

    assert not set(base_templates) ^ set(common_templates_expected_list), (
        f"Not all base CNV templates exist\n extra templates: {extra_templates}\n "
        f"missing templates: {missing_templates}",
    )


@pytest.mark.s390x
@pytest.mark.parametrize(
    ("os_type", "osinfo_filename", "memory_test"),
    [
        pytest.param(
            "rhel7",
            "rhel-7.7",
            "minimum",
            marks=pytest.mark.polarion("CNV-3619"),
            id="test_rhel7_minimum_memory",
        ),
        pytest.param(
            "rhel8",
            "rhel-8.1",
            "minimum",
            marks=pytest.mark.polarion("CNV-3620"),
            id="test_rhel8_minimum_memory",
        ),
        pytest.param(
            "rhel9",
            "rhel-9.0",
            "minimum",
            marks=pytest.mark.polarion("CNV-6989"),
            id="test_rhel9_minimum_memory",
        ),
        pytest.param(
            "rhel7",
            "rhel-7.7",
            "maximum",
            marks=pytest.mark.polarion("CNV-3622"),
            id="test_rhel7_maximum_memory",
        ),
        pytest.param(
            "rhel8",
            "rhel-8.1",
            "maximum",
            marks=pytest.mark.polarion("CNV-3623"),
            id="test_rhel8_maximum_memory",
        ),
        pytest.param(
            "rhel9",
            "rhel-9.0",
            "maximum",
            marks=pytest.mark.polarion("CNV-6988"),
            id="test_rhel9_maximum_memory",
        ),
    ],
)
def test_validate_rhel_min_max_memory(
    base_templates,
    downloaded_latest_libosinfo_db,
    os_type,
    osinfo_filename,
    memory_test,
):
    """
    Validate CNV RHEL templates for minimum and maximum memory, against osinfo db files.
    """

    osinfo_file_path = os.path.join(f"{downloaded_latest_libosinfo_db}/os/redhat.com/{osinfo_filename}.xml")
    # libosinfo "all" architecture does not include maximum values
    resources_arch = "all" if memory_test == "minimum" else "x86_64"

    osinfo_memory_value = fetch_osinfo_memory(
        osinfo_file_path=osinfo_file_path,
        memory_test=memory_test,
        resources_arch=resources_arch,
    )

    check_default_and_validation_memory(
        get_base_templates=base_templates,
        osinfo_memory_value=osinfo_memory_value,
        os_type=os_type,
        memory_test=memory_test,
        osinfo_filename=osinfo_filename,
    )


@pytest.mark.s390x
@pytest.mark.parametrize(
    ("osinfo_filename", "os_template", "memory_test"),
    [
        pytest.param(
            "win-2k16",
            "windows2k16",
            "minimum",
            marks=pytest.mark.polarion("CNV-3625"),
            id="test_win2k16_minimum_memory",
        ),
        pytest.param(
            "win-2k19",
            "windows2k19",
            "minimum",
            marks=pytest.mark.polarion("CNV-3626"),
            id="test_win2k19_minimum_memory",
        ),
        pytest.param(
            "win-10",
            "windows10",
            "minimum",
            marks=pytest.mark.polarion("CNV-3627"),
            id="test_win10_minimum_memory",
        ),
        pytest.param(
            "win-2k16",
            "windows2k16",
            "maximum",
            marks=pytest.mark.polarion("CNV-3629"),
            id="test_win2k16_maximum_memory",
        ),
        pytest.param(
            "win-2k19",
            "windows2k19",
            "maximum",
            marks=pytest.mark.polarion("CNV-3630"),
            id="test_win2k19_maximum_memory",
        ),
        pytest.param(
            "win-10",
            "windows10",
            "maximum",
            marks=pytest.mark.polarion("CNV-3631"),
            id="test_win10_maximum_memory",
        ),
    ],
)
def test_validate_windows_min_max_memory(
    base_templates,
    downloaded_latest_libosinfo_db,
    osinfo_filename,
    os_template,
    memory_test,
):
    """
    Validate CNV Windows templates for minimum and maximum memory, against osinfo db files.
    """

    osinfo_file_path = os.path.join(f"{downloaded_latest_libosinfo_db}/os/microsoft.com/{osinfo_filename}.xml")
    osinfo_memory_value = fetch_osinfo_memory(
        osinfo_file_path=osinfo_file_path,
        memory_test=memory_test,
        resources_arch="x86_64",
    )

    check_default_and_validation_memory(
        get_base_templates=base_templates,
        osinfo_memory_value=osinfo_memory_value,
        os_type=os_template,
        memory_test=memory_test,
        osinfo_filename=osinfo_filename,
    )


@pytest.mark.s390x
@pytest.mark.polarion("CNV-5002")
def test_common_templates_golden_images_params(base_templates):
    unmatched_templates = {}
    for template in base_templates:
        template_parameters_dict = template.instance.to_dict()["parameters"]
        # Extract golden images parameters from template's parameters
        golden_images_params = [
            gi_params
            for gi_params in template_parameters_dict
            if gi_params["name"] in [DATA_SOURCE_NAME, DATA_SOURCE_NAMESPACE]
        ]
        if not len(golden_images_params) == 2:
            unmatched_templates.update({template.name: "Missing golden images parameters"})
        for gi_params in golden_images_params:
            # DATA_SOURCE_NAME contains either:
            # fedora OS ("fedora")
            # rhel latest major release (e.g rhel7)
            # Windows relevant OS (e.g win2k19)
            if (
                gi_params["name"] == DATA_SOURCE_NAME
                and re.match(r"^([a-z]+).*", template.name).group(1)[:3] not in gi_params["value"]
            ):
                unmatched_templates.update({template.name: f"{DATA_SOURCE_NAME} wrong value {gi_params['value']}"})
            if (
                gi_params["name"] == DATA_SOURCE_NAMESPACE
                and gi_params["value"] != py_config["golden_images_namespace"]
            ):
                unmatched_templates.update({
                    template.name: f"{DATA_SOURCE_NAMESPACE} wrong namespace {gi_params['value']}"
                })
    assert not unmatched_templates, f"The following templates fail on golden images verification: {unmatched_templates}"


@pytest.mark.s390x
@pytest.mark.polarion("CNV-5599")
def test_provide_support_annotations(base_templates, templates_provider_support_dict):
    """Verify provider, provider-support-level and provider-url annotations"""

    unmatched_annotations = {}
    for template in base_templates:
        template_annotations_dict = template.instance.to_dict()["metadata"]["annotations"]
        template_os_name = re.search(r"([a-z]+).*", template.name).group(1)
        for key, value in templates_provider_support_dict[template_os_name].items():
            annotation = template_annotations_dict.get(key)
            if annotation != value:
                unmatched_annotations[template.name] = {key: annotation}
    assert not unmatched_annotations, (
        f"The following templates annotations fail on provider and support verification: {unmatched_annotations}"
    )


@pytest.mark.s390x
@pytest.mark.polarion("CNV-6874")
def test_vm_annotations_in_template(base_templates):
    """Verify template VM object has os, workload and flavor annotations which match corresponding template labels"""

    def _verify_labels_annotations_match(vm_annotations, template_labels):
        """Verify VM annotations match template corresponding labels.
        For example: annotation = vm.kubevirt.io/flavor: medium, label = flavor.template.kubevirt.io/medium: "true"

        Returns:
            True if all annotations are matched else False
        """
        for annotation_name, annotation_value in vm_annotations.items():
            # Construct template label name from the annotation
            # Windows OS in annotation = "windows2k19", in label = "win2k19"
            annotation_value = re.sub("windows", "win", annotation_value)
            label_name = f"{annotation_name.split('/')[-1]}.{Resource.ApiGroup.TEMPLATE_KUBEVIRT_IO}/{annotation_value}"

            # Linux-based OS annotation includes only a major release ("vm.kubevirt.io/os: rhel8")
            # whereas the label includes a minor release ("os.template.kubevirt.io/rhel8.4")
            if not (
                (
                    annotation_name == Template.VMAnnotations.OS
                    and [True for label in template_labels.keys() if label_name in label]
                )
                or template_labels.get(label_name)
            ):
                return False
        return True

    unmatched_templates = {}
    for template in base_templates:
        vm_object_annotations = template.instance.objects[0].spec.template.metadata.annotations
        template_labels = template.instance.metadata.labels

        if not (
            verify_annotations_match(
                obj_annotations=vm_object_annotations.keys(),
                expected=VM_EXPECTED_ANNOTATION_KEYS,
            )
            and _verify_labels_annotations_match(vm_annotations=vm_object_annotations, template_labels=template_labels)
        ):
            unmatched_templates[template.name] = {
                "annotations": vm_object_annotations,
                "labels": template_labels,
            }

    assert not unmatched_templates, f"Some templates do not have the right VM annotations:\n{unmatched_templates}."


@pytest.mark.s390x
@pytest.mark.parametrize(
    "data_volume_scope_function, vm_from_template_with_existing_dv",
    [
        pytest.param(
            {
                "dv_name": "dv-fedora",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "fedora-vm",
                "template_labels": FEDORA_LATEST_LABELS,
                "ssh": False,
                "guest_agent": False,
            },
            marks=pytest.mark.polarion("CNV-6890"),
        ),
    ],
    indirect=True,
)
def test_vmi_annotations(data_volume_scope_function, vm_from_template_with_existing_dv):
    """Verify that VM annotations are copied to the VMI object.
    For this test the underlying OS is not important; using Cirros to reduce runtime.
    """
    vm_annotations = vm_from_template_with_existing_dv.instance.spec.template.metadata.annotations
    # Use only relevant os/flavor/workload annotations
    vmi_annotations = {
        annotation: value
        for annotation, value in vm_from_template_with_existing_dv.vmi.instance.metadata.annotations.items()
        if annotation.startswith(Resource.ApiGroup.VM_KUBEVIRT_IO)
    }

    assert verify_annotations_match(obj_annotations=vmi_annotations.keys(), expected=VM_EXPECTED_ANNOTATION_KEYS), (
        f"Unexpected VMI annotations: {vmi_annotations}, expected: {VM_EXPECTED_ANNOTATION_KEYS}"
    )

    assert all([
        vmi_ann_value == vm_annotations[vmi_ann_name] for vmi_ann_name, vmi_ann_value in vmi_annotations.items()
    ]), f"vmi annotations {vmi_annotations} do no match vm annotations {vm_annotations}"


@pytest.mark.parametrize(
    "os_base_templates",
    [
        pytest.param(
            "win",
            marks=pytest.mark.polarion("CNV-7249"),
        ),
    ],
    indirect=True,
)
def test_hyperv_features_exist_in_windows_templates(os_base_templates):
    templates_with_wrong_hyperv_labels = {}
    for template in os_base_templates:
        template_hyperv_features = template.instance.objects[0].spec.template.spec.domain.features.get("hyperv")
        if sorted(list(template_hyperv_features.keys())) != sorted(HYPERV_FEATURES_LABELS_VM_YAML):
            templates_with_wrong_hyperv_labels[template.name] = list(template_hyperv_features.keys())
    assert not templates_with_wrong_hyperv_labels, (
        f"Windows templates are missing hyperV labels.\n"
        f"Expected Hyper-V features: {HYPERV_FEATURES_LABELS_VM_YAML}\n"
        f"Current templates Hyper-V labels :{templates_with_wrong_hyperv_labels}"
    )


@pytest.mark.s390x
@pytest.mark.parametrize(
    "annotation_list, os_base_templates",
    [
        pytest.param(
            ["images", "containerdisks"],
            "fedora",
            marks=pytest.mark.polarion("CNV-8476"),
        ),
        pytest.param(
            ["images", "containerdisks"],
            "centos",
            marks=pytest.mark.polarion("CNV-8477"),
        ),
        pytest.param(
            ["containerdisks"],
            "rhel8",
            marks=pytest.mark.polarion("CNV-8478"),
        ),
        pytest.param(
            ["containerdisks"],
            "rhel9",
            marks=pytest.mark.polarion("CNV-8483"),
        ),
    ],
    indirect=["os_base_templates"],
)
def test_suggested_image_annotation_exists(os_base_templates, annotation_list):
    failed_templates_dict = {}
    for template in os_base_templates:
        for annotation in annotation_list:
            if f"{template.ApiGroup.TEMPLATE_KUBEVIRT_IO}/{annotation}" not in dict(
                template.instance.metadata.annotations
            ):
                failed_templates_dict.setdefault(annotation, []).append(template.name)
    assert not failed_templates_dict, ", ".join(
        f"{template.ApiGroup.TEMPLATE_KUBEVIRT_IO}/{annotation}, was not found in {failed_templates_dict[annotation]}"
        for annotation in failed_templates_dict
    )
