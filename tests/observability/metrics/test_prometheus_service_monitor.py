import pytest
from ocp_resources.service_monitor import ServiceMonitor

from utilities.constants.components import VIRT_OPERATOR


@pytest.fixture()
def kubevirt_prometheus_service_monitor_list(admin_client):
    return list(
        ServiceMonitor.get(
            client=admin_client,
            label_selector=f"{ServiceMonitor.ApiGroup.APP_KUBERNETES_IO}/managed-by={VIRT_OPERATOR}",
        )
    )


@pytest.fixture()
def kubevirt_service_monitor_namespace(kubevirt_hyperconverged_spec_scope_function):
    return kubevirt_hyperconverged_spec_scope_function["serviceMonitorNamespace"]


class TestPrometheusServiceMonitor:
    @pytest.mark.s390x
    def test_kubevirt_service_monitor_namespace(self, kubevirt_service_monitor_namespace, hco_namespace):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-883 # <skip-jira-utils-check>
        Polarion: CNV-9287
        """
        assert kubevirt_service_monitor_namespace == hco_namespace.name

    @pytest.mark.s390x
    @pytest.mark.conformance
    def test_prometheus_service_monitor_in_our_namespace(
        self,
        kubevirt_prometheus_service_monitor_list,
        kubevirt_service_monitor_namespace,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-883 # <skip-jira-utils-check>
        Polarion: CNV-9264
        """
        for service_monitor_object in kubevirt_prometheus_service_monitor_list:
            assert service_monitor_object.namespace == kubevirt_service_monitor_namespace
