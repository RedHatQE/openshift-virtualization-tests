import pytest


@pytest.fixture()
def csv_annotation(openshift_cnv_csv_scope_session):
    return openshift_cnv_csv_scope_session.instance.metadata.annotations.get(
        f"{openshift_cnv_csv_scope_session.ApiGroup.OPERATORS_OPENSHIFT_IO}/infrastructure-features"
    )
