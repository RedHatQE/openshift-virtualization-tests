import pytest
from ocp_resources.resource import Resource

from utilities.constants import KUBEVIRT_VIRT_OPERATOR_UP, VIRT_API, VIRT_CONTROLLER, VIRT_HANDLER, VIRT_OPERATOR

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]

virt_label_dict = {
    VIRT_API: f"{Resource.ApiGroup.KUBEVIRT_IO}={VIRT_API}",
    VIRT_HANDLER: f"{Resource.ApiGroup.KUBEVIRT_IO}={VIRT_HANDLER}",
    VIRT_OPERATOR: f"{Resource.ApiGroup.KUBEVIRT_IO}={VIRT_OPERATOR}",
    VIRT_CONTROLLER: f"{Resource.ApiGroup.KUBEVIRT_IO}={VIRT_CONTROLLER} ",
}
KUBEVIRT_VIRT_CONTROLLER_READY_STATUS = "kubevirt_virt_controller_ready_status"
KUBEVIRT_VIRT_OPERATOR_READY_STATUS = "kubevirt_virt_operator_ready_status"
KUBEVIRT_VIRT_OPERATOR_LEADING_STATUS = "kubevirt_virt_operator_leading_status"
KUBEVIRT_VIRT_CONTROLLER_LEADING_STATUS = "kubevirt_virt_controller_leading_status"
KUBEVIRT_VIRT_API_UP = "kubevirt_virt_api_up"
KUBEVIRT_VIRT_HANDLER_UP = "kubevirt_virt_handler_up"
KUBEVIRT_VIRT_CONTROLLER_UP = "kubevirt_virt_controller_up"


@pytest.mark.parametrize(
    "virt_pod_info_from_prometheus, virt_pod_names_by_label",
    [
        pytest.param(
            KUBEVIRT_VIRT_CONTROLLER_READY_STATUS,
            virt_label_dict[VIRT_CONTROLLER],
            marks=pytest.mark.polarion("CNV-7110"),
            id=KUBEVIRT_VIRT_CONTROLLER_READY_STATUS,
        ),
        pytest.param(
            KUBEVIRT_VIRT_OPERATOR_READY_STATUS,
            virt_label_dict[VIRT_OPERATOR],
            marks=pytest.mark.polarion("CNV-7111"),
            id=KUBEVIRT_VIRT_OPERATOR_READY_STATUS,
        ),
        pytest.param(
            KUBEVIRT_VIRT_OPERATOR_LEADING_STATUS,
            virt_label_dict[VIRT_OPERATOR],
            marks=pytest.mark.polarion("CNV-7112"),
            id=KUBEVIRT_VIRT_OPERATOR_LEADING_STATUS,
        ),
        pytest.param(
            KUBEVIRT_VIRT_CONTROLLER_LEADING_STATUS,
            virt_label_dict[VIRT_CONTROLLER],
            marks=pytest.mark.polarion("CNV-7113"),
            id=KUBEVIRT_VIRT_CONTROLLER_LEADING_STATUS,
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_virt_recording_rules(
    prometheus,
    admin_client,
    hco_namespace,
    virt_pod_info_from_prometheus,
    virt_pod_names_by_label,
):
    """
    This test will check that recording rules for 'virt-operator and virt-controller'
    showing the pod information in the output.
    """
    # Check Pod names.
    assert set(virt_pod_names_by_label) == virt_pod_info_from_prometheus, (
        f"Actual pods {virt_pod_names_by_label} not matching with expected pods {virt_pod_info_from_prometheus}"
    )


@pytest.mark.parametrize(
    "virt_up_metrics_values, virt_pod_names_by_label",
    [
        pytest.param(
            KUBEVIRT_VIRT_API_UP,
            virt_label_dict[VIRT_API],
            marks=pytest.mark.polarion("CNV-7106"),
            id=KUBEVIRT_VIRT_API_UP,
        ),
        pytest.param(
            KUBEVIRT_VIRT_OPERATOR_UP,
            virt_label_dict[VIRT_OPERATOR],
            marks=pytest.mark.polarion("CNV-7107"),
            id=KUBEVIRT_VIRT_OPERATOR_UP,
        ),
        pytest.param(
            KUBEVIRT_VIRT_HANDLER_UP,
            virt_label_dict[VIRT_HANDLER],
            marks=pytest.mark.polarion("CNV-7108"),
            id=KUBEVIRT_VIRT_HANDLER_UP,
        ),
        pytest.param(
            KUBEVIRT_VIRT_CONTROLLER_UP,
            virt_label_dict[VIRT_CONTROLLER],
            marks=pytest.mark.polarion("CNV-7109"),
            id=KUBEVIRT_VIRT_CONTROLLER_UP,
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_virt_up_recording_rules(
    prometheus,
    admin_client,
    hco_namespace,
    virt_up_metrics_values,
    virt_pod_names_by_label,
):
    """
    This test will check that 'up' recording rules for 'virt_api',
    'virt_controller','virt_operator', 'virt_handler' showing 'sum()' of pods in the output.
    More details on 'up': https://help.sumologic.com/Metrics/Kubernetes_Metrics#up-metrics

    Example:
        For 2 virt-api pods, 'kubevirt_virt_api_up_total' recording rule show 2 as output.
    """
    # Check values from Prometheus and acutal Pods.
    assert len(virt_pod_names_by_label) == virt_up_metrics_values, (
        f"Actual pod count {virt_pod_names_by_label} not matching with expected pod count {virt_up_metrics_values}"
    )
