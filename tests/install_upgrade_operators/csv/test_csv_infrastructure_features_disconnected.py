import ast

import pytest

pytestmark = [pytest.mark.sno, pytest.mark.arm64]


@pytest.mark.polarion("CNV-5840")
@pytest.mark.s390x
def test_csv_infrastructure_features_disconnected(csv_annotation):
    """
    In the Cluster Service Version annotations for Infrastructure Feature disconnected looks like:
    '["disconnected", "proxy-aware"]'.
    check an annotation 'Infrastructure Features' with value 'disconnected'
    """
    csv_annotations = ast.literal_eval(node_or_string=csv_annotation)
    for infra_feature in csv_annotations:
        if infra_feature.lower() == "disconnected":
            return True
    else:
        pytest.fail(f"Disconnected Infrastructure feature is not found {csv_annotations}")
