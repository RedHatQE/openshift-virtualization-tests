from base64 import b64decode

import pytest


EXPECTED_KEYWORDS_SET = {
    "KubeVirt",
    "Virtualization",
    "VM",
    "CNV",
    "Container-native virtualization",
    "Container native virtualization",
    "Virt",
    "Virtual",
}

EXPECTED_LINK_MAP = {
    "Source Code": "https://github.com/kubevirt",
    "OpenShift Virtualization": "https://www.openshift.com/learn/topics/virtualization/",
    "KubeVirt Project": "https://kubevirt.io",
}


def test_hco_csv_keywords(openshift_cnv_csv_scope_session):
    assert EXPECTED_KEYWORDS_SET == set(
        openshift_cnv_csv_scope_session.instance.spec.keywords
    )


def test_hco_csv_links(openshift_cnv_csv_scope_session):
    csv_link_map = {
        link_dict.get("name"): link_dict.get("url")
        for link_dict in openshift_cnv_csv_scope_session.instance.spec.links
    }
    assert EXPECTED_LINK_MAP == csv_link_map
    assert len(EXPECTED_LINK_MAP) == len(
        openshift_cnv_csv_scope_session.instance.spec.links
    )


def test_hco_csv_icon(openshift_cnv_csv_scope_session):
    assert len(openshift_cnv_csv_scope_session.instance.spec.icon) == 1
    assert (
        openshift_cnv_csv_scope_session.instance.spec.icon[0].mediatype
        == "image/svg+xml"
    )
    svg = b64decode(s=openshift_cnv_csv_scope_session.instance.spec.icon[0].base64data)
    with open("tests/installation/csv/logo.svg", "rb") as logo_file:
        expected_svg = logo_file.read().rstrip()

    assert svg == expected_svg, f"Expected icon: {expected_svg} and actual icon: {svg}"


def test_hco_csv_properties(openshift_cnv_csv_scope_session):
    assert openshift_cnv_csv_scope_session.instance.spec.provider.name == "Red Hat"
    assert (
        openshift_cnv_csv_scope_session.instance.spec.displayName
        == "OpenShift Virtualization"
    )

    annotations = openshift_cnv_csv_scope_session.instance.metadata.annotations
    assert annotations.get("capabilities") == "Deep Insights"
    assert annotations.get("support") == "Red Hat"


@pytest.mark.parametrize(
    "expected_value",
    [
        pytest.param(
            "fips",
            id="test_csv_fips_annotation",
        ),
        pytest.param(
            "sno",
            id="test_csv_sno_annotation",
        ),
    ],
)
def test_hco_csv_annotations(
    openshift_cnv_csv_scope_session, csv_annotation, expected_value
):
    assert expected_value in csv_annotation, (
        f"For csv: {openshift_cnv_csv_scope_session.name} annotation "
        f"{openshift_cnv_csv_scope_session.ApiGroup.OPERATORS_OPENSHIFT_IO}/infrastructure-features:"
        f" {csv_annotation} does not contain expected value: {expected_value}"
    )
