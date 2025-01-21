import pytest
from ocp_resources.resource import Resource

from tests.network.checkup_framework.constants import NONEXISTING_CONFIGMAP
from tests.network.checkup_framework.utils import (
    assert_failure_reason_in_configmap,
    assert_source_and_target_nodes,
    assert_successful_latency_checkup,
    verify_failure_reason_in_log,
    wait_for_job_finish,
)

pytestmark = [
    pytest.mark.jira("CNV-55124", run=False),
    pytest.mark.usefixtures("framework_resources"),
]

CNCF_IO_RESOURCE = Resource.ApiGroup.K8S_CNI_CNCF_IO
CONNECTIVITY_ISSUE_ERROR_REGEX_MESSAGE = (
    "run: failed to run check: failed due to connectivity issue: \\d+ packets transmitted, 0 packets received"
)
CONDITION_TIMEOUT_REGEX_MESSAGE = (
    r"setup: failed to wait for VMI 'test-checkup-framework/latency-check-target-.*' IP address to "
    "appear on status: timed out waiting for the condition"
)
LATENCY_NONEXISTENT_NAD_CONFIGMAP_ERROR_REGEX_MESSAGE = (
    rf"setup: network-attachment-definitions\.{CNCF_IO_RESOURCE} " '"non-existing-nad" not found'
)
LATENCY_NONEXISTENT_NAMESPACE_CONFIGMAP_ERROR_REGEX_MESSAGE = (
    f'test-checkup-framework-sa" cannot get resource "network-attachment-definitions" in API group "{CNCF_IO_RESOURCE}"'
    ' in the namespace "non-existing-namespace"'
)
LATENCY_ZERO_MILLISECONDS_CONFIGMAP_ERROR_REGEX_MESSAGE = (
    r'Kubevirt VM latency checkup failed: run : actual max latency "[0-9]+|(?:.[0-9]+)[^\W\d_]+" is greater than '
    'desired "0s"'
)
# Real error message example: 'actual max latency "577µs" is greater than desired'
LATENCY_NONEXISTENT_CONFIGMAP_ENV_JOB_ERROR_REGEX_MESSAGE = f'configmaps "{NONEXISTING_CONFIGMAP}" not found'
LATENCY_NO_ENV_VARIABLES_JOB_ERROR_REGEX_MESSAGE = 'missing required environment variable: "CONFIGMAP_NAMESPACE"'


@pytest.mark.jira("CNV-48962", run=False)
@pytest.mark.polarion("CNV-8578")
def test_disconnected_network_job_failure(
    latency_disconnected_configmap, latency_disconnected_network_job, latency_disconnected_network_job_failure
):
    assert_failure_reason_in_configmap(
        configmap=latency_disconnected_configmap,
        expected_failure_message=CONNECTIVITY_ISSUE_ERROR_REGEX_MESSAGE,
    )


@pytest.mark.jira("CNV-48962", run=False)
@pytest.mark.polarion("CNV-9535")
def test_disconnected_network_sriov_job_failure(
    latency_disconnected_configmap_sriov,
    latency_job_disconnected_configmap_sriov,
    latency_disconnected_network_sriov_job_failure,
):
    assert_failure_reason_in_configmap(
        configmap=latency_disconnected_configmap_sriov,
        expected_failure_message=CONNECTIVITY_ISSUE_ERROR_REGEX_MESSAGE,
    )


class TestCheckupLatencyLinuxBridgeNad:
    @pytest.mark.polarion("CNV-9404")
    def test_basic_configmap_linux_bridge_nad(
        self,
        checkup_ns,
        checkup_nad,
        default_latency_configmap,
        default_latency_job,
        default_latency_job_success,
    ):
        assert_source_and_target_nodes(
            configmap=default_latency_configmap,
            expected_nodes_identical=False,
        )

    @pytest.mark.polarion("CNV-8581")
    def test_basic_configmap_linux_bridge_nad_on_same_node(
        self,
        checkup_ns,
        checkup_nad,
        latency_same_node_configmap,
        latency_same_node_job,
        latency_same_node_job_success,
    ):
        assert_source_and_target_nodes(
            configmap=latency_same_node_configmap,
            expected_nodes_identical=True,
        )

    @pytest.mark.polarion("CNV-9474")
    def test_two_configmaps_and_jobs_with_success_linux_bridge_nad(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        latency_two_configmaps,
        latency_two_jobs,
    ):
        for index in range(len(latency_two_jobs)):
            wait_for_job_finish(
                client=unprivileged_client,
                job=latency_two_jobs[index],
                checkup_ns=checkup_ns,
            )
            assert_successful_latency_checkup(configmap=latency_two_configmaps[index])

    @pytest.mark.polarion("CNV-8453")
    def test_concurrent_checkup_jobs_linux_bridge_nad(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        default_latency_configmap,
        default_latency_job,
        latency_concurrent_job,
        latency_concurrent_job_failure,
    ):
        # Make sure the second, concurrent, job failed due to the configMap being already in use:
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_concurrent_job,
            checkup_ns=checkup_ns,
            failure_message_regex="configMap is already in use",
        )

    @pytest.mark.polarion("CNV-8535")
    def test_job_failure_linux_bridge_nad_nonexistent_configmap(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        default_latency_configmap,
        latency_nonexistent_configmap_env_job,
        latency_nonexistent_configmap_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_nonexistent_configmap_env_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_NONEXISTENT_CONFIGMAP_ENV_JOB_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-9482")
    def test_job_failure_linux_bridge_nad_no_env_variables(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        default_latency_configmap,
        latency_no_env_variables_job,
        latency_no_env_variables_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_no_env_variables_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_NO_ENV_VARIABLES_JOB_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-9479")
    def test_configmap_error_job_failure_linux_bridge_nad_nonexistent_nad(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        latency_nonexistent_nad_configmap,
        latency_configmap_error_job,
        latency_configmap_error_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_configmap_error_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_NONEXISTENT_NAD_CONFIGMAP_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-9481")
    def test_configmap_error_job_failure_linux_bridge_nad_nonexistent_namespace(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        latency_nonexistent_namespace_configmap,
        latency_nonexistent_namespace_job,
        latency_nonexistent_namespace_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_nonexistent_namespace_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_NONEXISTENT_NAMESPACE_CONFIGMAP_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-8656")
    def test_configmap_error_job_failure_linux_bridge_nad_one_second_timeout(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        latency_one_second_timeout_configmap,
        latency_one_second_timeout_job,
        latency_one_second_timeout_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_one_second_timeout_job,
            checkup_ns=checkup_ns,
            failure_message_regex=CONDITION_TIMEOUT_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-9475")
    def test_configmap_error_job_failure_linux_bridge_nad_zero_milliseconds(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        latency_zero_milliseconds_configmap,
        latency_zero_milliseconds_job,
        latency_zero_milliseconds_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_zero_milliseconds_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_ZERO_MILLISECONDS_CONFIGMAP_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-9476")
    def test_configmap_error_job_failure_linux_bridge_nad_nonexistent_node(
        self,
        unprivileged_client,
        checkup_ns,
        checkup_nad,
        latency_nonexistent_node_configmap,
        latency_nonexistent_node_job,
        latency_nonexistent_node_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_nonexistent_node_job,
            checkup_ns=checkup_ns,
            failure_message_regex=CONDITION_TIMEOUT_REGEX_MESSAGE,
        )


class TestCheckupLatencySriovNetwork:
    @pytest.mark.polarion("CNV-10418")
    def test_basic_configmap_sriov_network(
        self,
        skip_when_no_sriov,
        checkup_ns,
        checkup_sriov_network,
        default_latency_configmap,
        default_latency_job,
        default_latency_job_success,
    ):
        assert_source_and_target_nodes(
            configmap=default_latency_configmap,
            expected_nodes_identical=False,
        )

    @pytest.mark.polarion("CNV-10419")
    def test_basic_configmap_sriov_network_on_same_node(
        self,
        skip_when_no_sriov,
        checkup_ns,
        checkup_sriov_network,
        latency_same_node_configmap,
        latency_same_node_job,
        latency_same_node_job_success,
    ):
        assert_source_and_target_nodes(
            configmap=latency_same_node_configmap,
            expected_nodes_identical=True,
        )

    @pytest.mark.polarion("CNV-10420")
    def test_two_configmaps_and_jobs_with_success_sriov_network(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_sriov_network,
        checkup_ns,
        latency_two_configmaps,
        latency_two_jobs,
    ):
        for index in range(len(latency_two_jobs)):
            wait_for_job_finish(
                client=unprivileged_client,
                job=latency_two_jobs[index],
                checkup_ns=checkup_ns,
            )
            assert_successful_latency_checkup(configmap=latency_two_configmaps[index])

    @pytest.mark.polarion("CNV-10421")
    def test_concurrent_checkup_jobs_sriov_network(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_ns,
        checkup_sriov_network,
        default_latency_configmap,
        default_latency_job,
        latency_concurrent_job,
        latency_concurrent_job_failure,
    ):
        # Make sure the second, concurrent, job failed due to the configMap being already in use:
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_concurrent_job,
            checkup_ns=checkup_ns,
            failure_message_regex="configMap is already in use",
        )

    @pytest.mark.polarion("CNV-10422")
    def test_job_failure_sriov_network_nonexistent_configmap_env(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_ns,
        checkup_sriov_network,
        default_latency_configmap,
        latency_nonexistent_configmap_env_job,
        latency_nonexistent_configmap_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_nonexistent_configmap_env_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_NONEXISTENT_CONFIGMAP_ENV_JOB_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-10423")
    def test_job_failure_sriov_network(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_ns,
        checkup_sriov_network,
        default_latency_configmap,
        latency_no_env_variables_job,
        latency_no_env_variables_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_no_env_variables_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_NO_ENV_VARIABLES_JOB_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-10424")
    def test_configmap_error_job_failure_sriov_network_nonexistent_nad(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_ns,
        checkup_sriov_network,
        latency_nonexistent_nad_configmap,
        latency_configmap_error_job,
        latency_configmap_error_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_configmap_error_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_NONEXISTENT_NAD_CONFIGMAP_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-10425")
    def test_configmap_error_job_failure_sriov_network_nonexistent_namespace(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_ns,
        checkup_sriov_network,
        latency_nonexistent_namespace_configmap,
        latency_nonexistent_namespace_job,
        latency_nonexistent_namespace_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_nonexistent_namespace_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_NONEXISTENT_NAMESPACE_CONFIGMAP_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-10426")
    def test_configmap_error_job_failure_sriov_network_one_second_timeout(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_ns,
        checkup_sriov_network,
        latency_one_second_timeout_configmap,
        latency_one_second_timeout_job,
        latency_one_second_timeout_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_one_second_timeout_job,
            checkup_ns=checkup_ns,
            failure_message_regex=CONDITION_TIMEOUT_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-10427")
    def test_configmap_error_job_failure_sriov_network_zero_milliseconds(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_ns,
        checkup_sriov_network,
        latency_zero_milliseconds_configmap,
        latency_zero_milliseconds_job,
        latency_zero_milliseconds_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_zero_milliseconds_job,
            checkup_ns=checkup_ns,
            failure_message_regex=LATENCY_ZERO_MILLISECONDS_CONFIGMAP_ERROR_REGEX_MESSAGE,
        )

    @pytest.mark.polarion("CNV-10428")
    def test_configmap_error_job_failure_sriov_network_nonexistent_node(
        self,
        skip_when_no_sriov,
        unprivileged_client,
        checkup_ns,
        checkup_sriov_network,
        latency_nonexistent_node_configmap,
        latency_nonexistent_node_job,
        latency_nonexistent_node_job_failure,
    ):
        verify_failure_reason_in_log(
            unprivileged_client=unprivileged_client,
            job=latency_nonexistent_node_job,
            checkup_ns=checkup_ns,
            failure_message_regex=CONDITION_TIMEOUT_REGEX_MESSAGE,
        )
