from base64 import b64decode

import pytest

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64]

# Check CSV properties like keywords, title, provided by, links etc.

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


@pytest.mark.polarion("CNV-4456")
@pytest.mark.smoke
@pytest.mark.ocp_interop
@pytest.mark.s390x
def test_csv_keywords(csv_scope_session):
    """
    Assert keywords. Check that each one of the expected keywords are actually there
    """
    assert EXPECTED_KEYWORDS_SET == set(csv_scope_session.instance.spec.keywords)


@pytest.mark.polarion("CNV-4457")
@pytest.mark.smoke
@pytest.mark.ocp_interop
@pytest.mark.s390x
def test_csv_links(csv_scope_session):
    """
    Check links list.
    """
    # links is a list of dicts, with keys of "name" and "url"
    # translate the links list to a single name:url dict
    csv_link_map = {link_dict.get("name"): link_dict.get("url") for link_dict in csv_scope_session.instance.spec.links}
    # check that the links list contains all the required name:url pairs
    assert EXPECTED_LINK_MAP == csv_link_map
    # check that there are no duplication in links list
    assert len(EXPECTED_LINK_MAP) == len(csv_scope_session.instance.spec.links)


@pytest.mark.polarion("CNV-4458")
@pytest.mark.smoke
@pytest.mark.ocp_interop
@pytest.mark.s390x
def test_csv_icon(csv_scope_session):
    """
    Assert Icon/Logo.
    """
    assert len(csv_scope_session.instance.spec.icon) == 1
    assert csv_scope_session.instance.spec.icon[0].mediatype == "image/svg+xml"
    svg = b64decode(s=csv_scope_session.instance.spec.icon[0].base64data)
    with open("tests/install_upgrade_operators/csv/logo.svg", "rb") as logo_file:
        expected_svg = logo_file.read().rstrip()

    assert svg == expected_svg, f"Expected icon: {expected_svg} and actual icon: {svg}"


@pytest.mark.polarion("CNV-4376")
@pytest.mark.smoke
@pytest.mark.ocp_interop
@pytest.mark.s390x
def test_csv_properties(csv_scope_session):
    """
    Asserting remaining csv properties.
    """
    assert csv_scope_session.instance.spec.provider.name == "Red Hat"
    assert csv_scope_session.instance.spec.displayName == "OpenShift Virtualization"

    annotations = csv_scope_session.instance.metadata.annotations
    assert annotations.get("capabilities") == "Deep Insights"
    assert annotations.get("support") == "Red Hat"


@pytest.mark.parametrize(
    "expected_value",
    [
        pytest.param(
            "fips",
            marks=pytest.mark.polarion("CNV-7297"),
            id="test_csv_fips_annotation",
        ),
        pytest.param(
            "sno",
            marks=(pytest.mark.polarion("CNV-7397"), pytest.mark.sno()),
            id="test_csv_sno_annotation",
        ),
    ],
)
def test_csv_annotations(csv_scope_session, csv_annotation, expected_value):
    """
    Validates badges have been added to csv's operators.openshift.io/infrastructure-features annotation
    """
    assert expected_value in csv_annotation, (
        f"For csv: {csv_scope_session.name} annotation "
        f"{csv_scope_session.ApiGroup.OPERATORS_OPENSHIFT_IO}/infrastructure-features:"
        f" {csv_annotation} does not contain expected value: {expected_value}"
    )
