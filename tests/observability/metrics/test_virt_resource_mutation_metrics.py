import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.config_map import ConfigMap
from ocp_resources.console_cli_download import ConsoleCLIDownload
from ocp_resources.console_quick_start import ConsoleQuickStart
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.priority_class import PriorityClass
from ocp_resources.prometheus_rule import PrometheusRule
from ocp_resources.service import Service
from ocp_resources.service_monitor import ServiceMonitor
from ocp_resources.ssp import SSP

from tests.observability.metrics.utils import (
    COUNT_THREE,
    COUNT_TWO,
    get_changed_mutation_component_value,
    wait_for_summary_count_to_be_expected,
)
from utilities.constants import (
    CDI_KUBEVIRT_HYPERCONVERGED,
    COUNT_FIVE,
    SSP_KUBEVIRT_HYPERCONVERGED,
    VIRTCTL_CLI_DOWNLOADS,
)

pytestmark = pytest.mark.sno
LOGGER = logging.getLogger(__name__)

COMPONENT_CONFIG = {
    "ssp": {
        "resource_info": {
            "comp_name": f"ssp/{SSP_KUBEVIRT_HYPERCONVERGED}",
            "name": SSP_KUBEVIRT_HYPERCONVERGED,
            "resource": SSP,
            "count": COUNT_FIVE,
        },
    },
    "kubevirt": {
        "resource_info": {
            "comp_name": "kubevirt/kubevirt-kubevirt-hyperconverged",
            "name": "kubevirt-kubevirt-hyperconverged",
            "resource": KubeVirt,
            "count": COUNT_FIVE,
        },
    },
    "cdi": {
        "resource_info": {
            "comp_name": f"cdi/{CDI_KUBEVIRT_HYPERCONVERGED}",
            "name": "cdi-kubevirt-hyperconverged",
            "resource": CDI,
            "count": COUNT_FIVE,
        },
    },
    "cluster": {
        "resource_info": {
            "comp_name": "networkaddonsconfig/cluster",
            "name": "cluster",
            "resource": NetworkAddonsConfig,
            "count": COUNT_TWO,
        },
    },
    "config_map_kubevirt_storage": {
        "resource_info": {
            "comp_name": "configmap/kubevirt-storage-class-defaults",
            "resource": ConfigMap,
            "name": "kubevirt-storage-class-defaults",
            "count": COUNT_TWO,
        },
    },
    "priority_class": {
        "resource_info": {
            "comp_name": "priorityclass/kubevirt-cluster-critical",
            "name": "kubevirt-cluster-critical",
            "resource": PriorityClass,
            "count": COUNT_TWO,
        },
    },
    "console_cli_download": {
        "resource_info": {
            "comp_name": f"consoleclidownload/{VIRTCTL_CLI_DOWNLOADS}",
            "name": VIRTCTL_CLI_DOWNLOADS,
            "resource": ConsoleCLIDownload,
            "count": COUNT_TWO,
        },
    },
    "prometheus_rule": {
        "resource_info": {
            "comp_name": "prometheusrule/kubevirt-hyperconverged-prometheus-rule",
            "name": "kubevirt-hyperconverged-prometheus-rule",
            "resource": PrometheusRule,
            "count": COUNT_THREE,
        },
    },
    "service_monitor": {
        "resource_info": {
            "comp_name": "servicemonitor/kubevirt-hyperconverged-operator-metrics",
            "name": "kubevirt-hyperconverged-operator-metrics",
            "resource": ServiceMonitor,
            "count": COUNT_TWO,
        },
    },
    "service": {
        "resource_info": {
            "comp_name": "service/kubevirt-hyperconverged-operator-metrics",
            "name": "kubevirt-hyperconverged-operator-metrics",
            "resource": Service,
            "count": COUNT_THREE,
        },
    },
    "console_quick_start_creating_virtual_machine": {
        "resource_info": {
            "comp_name": "consolequickstart/creating-virtual-machine",
            "resource": ConsoleQuickStart,
            "name": "creating-virtual-machine",
            "count": COUNT_TWO,
        },
    },
    "console_quick_start_upload_boot_source": {
        "resource_info": {
            "comp_name": "consolequickstart/upload-boot-source",
            "resource": ConsoleQuickStart,
            "name": "upload-boot-source",
            "count": COUNT_TWO,
        },
    },
}


@pytest.mark.parametrize(
    "mutation_count_before_change, updated_resource_with_invalid_label, component_name",
    [
        pytest.param(
            COMPONENT_CONFIG["ssp"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["ssp"]["resource_info"],
            COMPONENT_CONFIG["ssp"]["resource_info"]["comp_name"],
            id="ssp",
            marks=(pytest.mark.polarion("CNV-6129")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["comp_name"],
            id="console_cli_download",
            marks=(pytest.mark.polarion("CNV-6130")),
        ),
        pytest.param(
            COMPONENT_CONFIG["priority_class"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["priority_class"]["resource_info"],
            COMPONENT_CONFIG["priority_class"]["resource_info"]["comp_name"],
            id="priority_class",
            marks=pytest.mark.polarion("CNV-6131"),
        ),
        pytest.param(
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["comp_name"],
            id="kubevirt",
            marks=(pytest.mark.polarion("CNV-6132")),
        ),
        pytest.param(
            COMPONENT_CONFIG["cdi"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cdi"]["resource_info"],
            COMPONENT_CONFIG["cdi"]["resource_info"]["comp_name"],
            id="cdi",
            marks=(pytest.mark.polarion("CNV-6133")),
        ),
        pytest.param(
            COMPONENT_CONFIG["cluster"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cluster"]["resource_info"],
            COMPONENT_CONFIG["cluster"]["resource_info"]["comp_name"],
            id="networkaddonsconfig",
            marks=(pytest.mark.polarion("CNV-6135")),
        ),
        pytest.param(
            COMPONENT_CONFIG["service"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service"]["resource_info"],
            COMPONENT_CONFIG["service"]["resource_info"]["comp_name"],
            id="service",
            marks=(pytest.mark.polarion("CNV-6137")),
        ),
        pytest.param(
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["comp_name"],
            id="service_monitor",
            marks=(pytest.mark.polarion("CNV-6138")),
        ),
        pytest.param(
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["comp_name"],
            id="prometheus_rule",
            marks=(pytest.mark.polarion("CNV-6139")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_creating_virtual_machine"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_quick_start_creating_virtual_machine"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_creating_virtual_machine"]["resource_info"]["comp_name"],
            id="console_quick_start_creating_virtual_machine",
            marks=(pytest.mark.polarion("CNV-8975")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_upload_boot_source"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_quick_start_upload_boot_source"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_upload_boot_source"]["resource_info"]["comp_name"],
            id="console_quick_start_upload_boot_source",
            marks=(pytest.mark.polarion("CNV-8974")),
        ),
    ],
    indirect=[
        "updated_resource_with_invalid_label",
        "mutation_count_before_change",
    ],
)
@pytest.mark.dependency(name="test_metric_invalid_change")
@pytest.mark.s390x
def test_metric_invalid_change(
    prometheus,
    mutation_count_before_change,
    updated_resource_with_invalid_label,
    component_name,
):
    """
    Any single change to Kubevirt spec will trigger the kubevirt_hco_out_of_band_modifications_total' metrics with
    component name with it's value.
    """
    mutation_count_after_change = get_changed_mutation_component_value(
        prometheus=prometheus,
        component_name=component_name,
        previous_value=mutation_count_before_change,
    )
    assert mutation_count_after_change - mutation_count_before_change == 1, (
        f"'{component_name}' Count before '{mutation_count_before_change}',and after '{mutation_count_after_change}'"
    )

    # Check an alert state is firing after metric is generated.


@pytest.mark.parametrize(
    "mutation_count_before_change, updated_resource_multiple_times_with_invalid_label, component_name, change_count",
    [
        pytest.param(
            COMPONENT_CONFIG["ssp"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["ssp"]["resource_info"],
            COMPONENT_CONFIG["ssp"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["ssp"]["resource_info"]["count"],
            id="ssp",
            marks=(pytest.mark.polarion("CNV-6148")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_cli_download"]["resource_info"]["count"],
            id="console_cli_download",
            marks=(pytest.mark.polarion("CNV-6149")),
        ),
        pytest.param(
            COMPONENT_CONFIG["priority_class"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["priority_class"]["resource_info"],
            COMPONENT_CONFIG["priority_class"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["priority_class"]["resource_info"]["count"],
            id="priority_class",
            marks=pytest.mark.polarion("CNV-6150"),
        ),
        pytest.param(
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["kubevirt"]["resource_info"]["count"],
            id="kubevirt",
            marks=(pytest.mark.polarion("CNV-6151")),
        ),
        pytest.param(
            COMPONENT_CONFIG["cdi"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cdi"]["resource_info"],
            COMPONENT_CONFIG["cdi"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cdi"]["resource_info"]["count"],
            id="cdi",
            marks=(pytest.mark.polarion("CNV-6152")),
        ),
        pytest.param(
            COMPONENT_CONFIG["cluster"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cluster"]["resource_info"],
            COMPONENT_CONFIG["cluster"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["cluster"]["resource_info"]["count"],
            id="networkaddonsconfig",
            marks=(pytest.mark.polarion("CNV-6154")),
        ),
        pytest.param(
            COMPONENT_CONFIG["service"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service"]["resource_info"],
            COMPONENT_CONFIG["service"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service"]["resource_info"]["count"],
            id="service",
            marks=(pytest.mark.polarion("CNV-6156")),
        ),
        pytest.param(
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["service_monitor"]["resource_info"]["count"],
            id="service_monitor",
            marks=(pytest.mark.polarion("CNV-6157")),
        ),
        pytest.param(
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["prometheus_rule"]["resource_info"]["count"],
            id="prometheus_rule",
            marks=(pytest.mark.polarion("CNV-6158")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_creating_virtual_machine"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_quick_start_creating_virtual_machine"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_creating_virtual_machine"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_quick_start_creating_virtual_machine"]["resource_info"]["count"],
            id="console_quick_start_creating_virtual_machine",
            marks=(pytest.mark.polarion("CNV-8976")),
        ),
        pytest.param(
            COMPONENT_CONFIG["console_quick_start_upload_boot_source"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_quick_start_upload_boot_source"]["resource_info"],
            COMPONENT_CONFIG["console_quick_start_upload_boot_source"]["resource_info"]["comp_name"],
            COMPONENT_CONFIG["console_quick_start_upload_boot_source"]["resource_info"]["count"],
            id="console_quick_start_upload_boot_source",
            marks=(pytest.mark.polarion("CNV-8977")),
        ),
    ],
    indirect=[
        "updated_resource_multiple_times_with_invalid_label",
        "mutation_count_before_change",
    ],
)
@pytest.mark.dependency(name="test_metric_multiple_invalid_change")
@pytest.mark.s390x
def test_metric_multiple_invalid_change(
    prometheus,
    mutation_count_before_change,
    updated_resource_multiple_times_with_invalid_label,
    component_name,
    change_count,
):
    """
    Multiple time change to resource spec will trigger the kubevirt_hco_out_of_band_modifications_total' metrics with
    component name with it's summary.
    Alert "KubeVirtCRModified" is generated
    for each component name with it's state and summary (integer).
    """
    assert updated_resource_multiple_times_with_invalid_label - mutation_count_before_change == change_count, (
        f"'{component_name}' Count before '{mutation_count_before_change}',and "
        f"after '{updated_resource_multiple_times_with_invalid_label}'"
    )

    # Check an alert state is firing after metric is generated.
    wait_for_summary_count_to_be_expected(
        prometheus=prometheus,
        component_name=component_name,
        expected_summary_value=change_count,
    )
