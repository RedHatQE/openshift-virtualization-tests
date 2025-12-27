# Generated using Claude cli

"""Unit tests for operator module"""

from unittest.mock import MagicMock, patch

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from timeout_sampler import TimeoutExpiredError

# Import after setting up mocks to avoid circular dependency
from utilities.operator import (  # noqa: E402
    apply_icsp_idms,
    approve_install_plan,
    cluster_with_icsp,
    collect_mcp_data_on_update_timeout,
    consecutive_checks_for_mcp_condition,
    create_catalog_source,
    create_icsp_idms_command,
    create_icsp_idms_from_file,
    create_operator,
    create_operator_group,
    create_subscription,
    delete_existing_icsp_idms,
    disable_default_sources_in_operatorhub,
    generate_icsp_idms_file,
    generate_unique_icsp_idms_file,
    get_catalog_source,
    get_cluster_operator_status_conditions,
    get_failed_cluster_operator,
    get_generated_icsp_idms,
    get_hco_csv_name_by_version,
    get_install_plan_from_subscription,
    get_machine_config_pool_by_name,
    get_machine_config_pools_conditions,
    get_mcp_updating_transition_times,
    get_mcps_with_all_machines_ready,
    get_mcps_with_different_transition_times,
    get_nodes_not_ready,
    get_operator_hub,
    update_image_in_catalog_source,
    update_subscription_source,
    wait_for_all_nodes_ready,
    wait_for_catalog_source_disabled,
    wait_for_catalogsource_ready,
    wait_for_cluster_operator_stabilize,
    wait_for_csv_successful_state,
    wait_for_mcp_ready_machine_count,
    wait_for_mcp_update_completion,
    wait_for_mcp_update_end,
    wait_for_mcp_update_start,
    wait_for_mcp_updated_condition_true,
    wait_for_nodes_to_have_same_kubelet_version,
    wait_for_package_manifest_to_exist,
)

TIMEOUT_75MIN = 4500
TIMEOUT_5SEC = 5

# ============================================================================
# SIMPLE FUNCTIONS (8 tests)
# ============================================================================


class TestCreateIcspIdmsCommand:
    """Test cases for create_icsp_idms_command function"""

    def test_create_command_without_pull_secret(self):
        """Test creating ICSP command without pull secret"""
        result = create_icsp_idms_command(
            image="registry.io/image:latest",
            source_url="mirror.io",
            folder_name="/tmp/manifests",
        )
        assert result == (
            "oc adm catalog mirror registry.io/image:latest mirror.io --manifests-only --to-manifests /tmp/manifests "
        )

    def test_create_command_with_pull_secret(self):
        """Test creating ICSP command with pull secret"""
        result = create_icsp_idms_command(
            image="registry.io/image:latest",
            source_url="mirror.io",
            folder_name="/tmp/manifests",
            pull_secret="/path/to/pull-secret.json",
        )
        assert result == (
            "oc adm catalog mirror registry.io/image:latest mirror.io "
            "--manifests-only --to-manifests /tmp/manifests  "
            "--registry-config=/path/to/pull-secret.json"
        )

    def test_create_command_with_filter_options(self):
        """Test creating ICSP command with filter options"""
        result = create_icsp_idms_command(
            image="registry.io/image:latest",
            source_url="mirror.io",
            folder_name="/tmp/manifests",
            filter_options="--filter-by-os=linux/amd64",
        )
        assert result == (
            "oc adm catalog mirror registry.io/image:latest mirror.io "
            "--manifests-only --to-manifests /tmp/manifests --filter-by-os=linux/amd64"
        )

    def test_create_command_with_all_parameters(self):
        """Test creating ICSP command with all parameters"""
        result = create_icsp_idms_command(
            image="registry.io/image:v1.0",
            source_url="mirror.example.com",
            folder_name="/opt/manifests",
            pull_secret="/etc/pull-secret",
            filter_options="--filter-by-os=linux/arm64",
        )
        assert result == (
            "oc adm catalog mirror registry.io/image:v1.0 mirror.example.com "
            "--manifests-only --to-manifests /opt/manifests --filter-by-os=linux/arm64 "
            "--registry-config=/etc/pull-secret"
        )


class TestClusterWithIcsp:
    """Test cases for cluster_with_icsp function"""

    @patch("utilities.operator.ImageContentSourcePolicy")
    def test_cluster_with_icsp_present(self, mock_icsp_class):
        """Test cluster_with_icsp returns True when ICSP exists"""
        mock_icsp1 = MagicMock()
        mock_icsp1.name = "icsp-1"
        mock_icsp2 = MagicMock()
        mock_icsp2.name = "icsp-2"

        mock_icsp_class.get.return_value = [mock_icsp1, mock_icsp2]

        result = cluster_with_icsp()
        assert result is True

    @patch("utilities.operator.ImageContentSourcePolicy")
    def test_cluster_with_icsp_absent(self, mock_icsp_class):
        """Test cluster_with_icsp returns False when no ICSP exists"""
        mock_icsp_class.get.return_value = []

        result = cluster_with_icsp()
        assert result is False


class TestGetCatalogSource:
    """Test cases for get_catalog_source function"""

    @patch("utilities.operator.py_config")
    @patch("utilities.operator.CatalogSource")
    def test_get_catalog_source_exists(self, mock_catalog_source_class, mock_config):
        """Test getting catalog source that exists"""
        mock_config.__getitem__.return_value = "openshift-marketplace"

        mock_catalog = MagicMock()
        mock_catalog.exists = True
        mock_catalog.name = "test-catalog"
        mock_catalog_source_class.return_value = mock_catalog

        result = get_catalog_source("test-catalog")

        assert result == mock_catalog
        mock_catalog_source_class.assert_called_once_with(
            namespace="openshift-marketplace",
            name="test-catalog",
        )

    @patch("utilities.operator.py_config")
    @patch("utilities.operator.CatalogSource")
    def test_get_catalog_source_not_exists(self, mock_catalog_source_class, mock_config):
        """Test getting catalog source that does not exist returns None"""
        mock_config.__getitem__.return_value = "openshift-marketplace"

        mock_catalog = MagicMock()
        mock_catalog.exists = False
        mock_catalog_source_class.return_value = mock_catalog

        result = get_catalog_source("nonexistent-catalog")

        assert result is None


class TestGetHcoCsvNameByVersion:
    """Test cases for get_hco_csv_name_by_version function"""

    def test_get_hco_csv_name_with_version(self):
        """Test getting HCO CSV name with version"""
        result = get_hco_csv_name_by_version("4.20.0")
        assert result == "kubevirt-hyperconverged-operator.v4.20.0"

    def test_get_hco_csv_name_with_different_version(self):
        """Test getting HCO CSV name with different version"""
        result = get_hco_csv_name_by_version("4.21.1")
        assert result == "kubevirt-hyperconverged-operator.v4.21.1"

    def test_get_hco_csv_name_with_z_stream_version(self):
        """Test getting HCO CSV name with z-stream version"""
        result = get_hco_csv_name_by_version("4.20.2")
        assert result == "kubevirt-hyperconverged-operator.v4.20.2"


# ============================================================================
# MEDIUM COMPLEXITY FUNCTIONS (10 tests)
# ============================================================================


class TestGetMachineConfigPoolByName:
    """Test cases for get_machine_config_pool_by_name function"""

    @patch("utilities.operator.MachineConfigPool")
    def test_get_mcp_exists(self, mock_mcp_class):
        """Test getting MCP that exists"""
        mock_mcp = MagicMock()
        mock_mcp.exists = True
        mock_mcp.name = "worker"
        mock_mcp_class.return_value = mock_mcp

        result = get_machine_config_pool_by_name("worker")

        assert result == mock_mcp
        mock_mcp_class.assert_called_once_with(name="worker")

    @patch("utilities.operator.MachineConfigPool")
    def test_get_mcp_not_exists(self, mock_mcp_class):
        """Test getting MCP that does not exist raises ResourceNotFoundError"""
        mock_mcp = MagicMock()
        mock_mcp.exists = False
        mock_mcp_class.return_value = mock_mcp

        with pytest.raises(ResourceNotFoundError, match="OperatorHub nonexistent not found"):
            get_machine_config_pool_by_name("nonexistent")

    @patch("utilities.operator.MachineConfigPool")
    def test_get_mcp_master_pool(self, mock_mcp_class):
        """Test getting master MCP"""
        mock_mcp = MagicMock()
        mock_mcp.exists = True
        mock_mcp.name = "master"
        mock_mcp_class.return_value = mock_mcp

        result = get_machine_config_pool_by_name("master")

        assert result == mock_mcp


class TestGetOperatorHub:
    """Test cases for get_operator_hub function"""

    @patch("utilities.operator.OperatorHub")
    def test_get_operator_hub_exists(self, mock_operator_hub_class):
        """Test getting OperatorHub that exists"""
        mock_operator_hub = MagicMock()
        mock_operator_hub.exists = True
        mock_operator_hub.name = "cluster"
        mock_operator_hub_class.return_value = mock_operator_hub

        result = get_operator_hub()

        assert result == mock_operator_hub
        mock_operator_hub_class.assert_called_once_with(name="cluster")

    @patch("utilities.operator.OperatorHub")
    def test_get_operator_hub_not_exists(self, mock_operator_hub_class):
        """Test getting OperatorHub that does not exist raises ResourceNotFoundError"""
        mock_operator_hub = MagicMock()
        mock_operator_hub.exists = False
        mock_operator_hub_class.return_value = mock_operator_hub

        with pytest.raises(ResourceNotFoundError, match="OperatorHub cluster not found"):
            get_operator_hub()


class TestGetFailedClusterOperator:
    """Test cases for get_failed_cluster_operator function"""

    @patch("utilities.operator.get_cluster_operator_status_conditions")
    @patch("utilities.operator.DEFAULT_RESOURCE_CONDITIONS", {"Available": "True", "Degraded": "False"})
    def test_get_failed_cluster_operator_all_healthy(self, mock_get_conditions):
        """Test get_failed_cluster_operator returns empty dict when all operators healthy"""
        mock_admin_client = MagicMock()

        mock_get_conditions.return_value = {
            "authentication": {"Available": "True", "Degraded": "False"},
            "console": {"Available": "True", "Degraded": "False"},
        }

        result = get_failed_cluster_operator(mock_admin_client)

        assert result == {}

    @patch("utilities.operator.get_cluster_operator_status_conditions")
    @patch("utilities.operator.DEFAULT_RESOURCE_CONDITIONS", {"Available": "True", "Degraded": "False"})
    def test_get_failed_cluster_operator_some_failed(self, mock_get_conditions):
        """Test get_failed_cluster_operator returns failed operators"""
        mock_admin_client = MagicMock()

        mock_get_conditions.return_value = {
            "authentication": {"Available": "True", "Degraded": "False"},
            "console": {"Available": "False", "Degraded": "True"},
            "network": {"Available": "True", "Degraded": "True"},
        }

        result = get_failed_cluster_operator(mock_admin_client)

        assert "console" in result
        assert "network" in result
        assert "authentication" not in result
        assert result["console"] == {"Available": "False", "Degraded": "True"}
        assert result["network"] == {"Available": "True", "Degraded": "True"}


class TestUpdateSubscriptionSource:
    """Test cases for update_subscription_source function"""

    @patch("utilities.operator.ResourceEditor")
    def test_update_subscription_source(self, mock_editor_class):
        """Test updating subscription source and channel"""
        mock_subscription = MagicMock()
        mock_subscription.name = "test-subscription"

        mock_editor = MagicMock()
        mock_editor_class.return_value = mock_editor

        update_subscription_source(
            subscription=mock_subscription,
            subscription_source="new-catalog",
            subscription_channel="stable-4.20",
        )

        mock_editor_class.assert_called_once_with({
            mock_subscription: {
                "spec": {
                    "channel": "stable-4.20",
                    "installPlanApproval": "Manual",
                    "source": "new-catalog",
                }
            }
        })
        mock_editor.update.assert_called_once()

    @patch("utilities.operator.ResourceEditor")
    def test_update_subscription_source_different_channel(self, mock_editor_class):
        """Test updating subscription with different channel"""
        mock_subscription = MagicMock()
        mock_subscription.name = "cnv-subscription"

        mock_editor = MagicMock()
        mock_editor_class.return_value = mock_editor

        update_subscription_source(
            subscription=mock_subscription,
            subscription_source="iib-catalog",
            subscription_channel="candidate-4.21",
        )

        call_args = mock_editor_class.call_args[0][0]
        assert call_args[mock_subscription]["spec"]["channel"] == "candidate-4.21"
        assert call_args[mock_subscription]["spec"]["source"] == "iib-catalog"
        assert call_args[mock_subscription]["spec"]["installPlanApproval"] == "Manual"


class TestGetClusterOperatorStatusConditions:
    """Test cases for get_cluster_operator_status_conditions function"""

    @patch("utilities.operator.ClusterOperator")
    @patch("utilities.operator.DEFAULT_RESOURCE_CONDITIONS", {"Available": "True", "Degraded": "False"})
    def test_get_cluster_operator_status_basic(self, mock_co_class):
        """Test getting cluster operator status conditions"""
        mock_admin_client = MagicMock()

        mock_co1 = MagicMock()
        mock_co1.name = "authentication"
        mock_co1.instance.get.return_value = {
            "conditions": [
                {"type": "Available", "status": "True", "message": "All is well"},
                {"type": "Degraded", "status": "False", "message": "Not degraded"},
            ]
        }

        mock_co2 = MagicMock()
        mock_co2.name = "console"
        mock_co2.instance.get.return_value = {
            "conditions": [
                {"type": "Available", "status": "True", "message": "Available"},
                {"type": "Degraded", "status": "False", "message": "Not degraded"},
            ]
        }

        mock_co_class.get.return_value = [mock_co1, mock_co2]

        result = get_cluster_operator_status_conditions(mock_admin_client)

        assert "authentication" in result
        assert "console" in result
        assert result["authentication"]["Available"] == "True"
        assert result["authentication"]["Degraded"] == "False"

    @patch("utilities.operator.ClusterOperator")
    @patch("utilities.operator.Resource")
    @patch("utilities.operator.DEFAULT_RESOURCE_CONDITIONS", {"Available": "True", "Degraded": "False"})
    def test_get_cluster_operator_console_notification_degraded(self, mock_resource, mock_co_class):
        """Test console operator with ConsoleNotificationSyncDegraded is handled correctly"""
        mock_admin_client = MagicMock()
        mock_resource.Condition.DEGRADED = "Degraded"
        mock_resource.Condition.Status.FALSE = "False"

        mock_co = MagicMock()
        mock_co.name = "console"
        mock_co.instance.get.return_value = {
            "conditions": [
                {"type": "Available", "status": "True"},
                {
                    "type": "Degraded",
                    "status": "True",
                    "message": "ConsoleNotificationSyncDegraded: some message",
                },
            ]
        }

        mock_co_class.get.return_value = [mock_co]

        result = get_cluster_operator_status_conditions(mock_admin_client)

        # ConsoleNotificationSyncDegraded should be treated as False
        assert result["console"]["Degraded"] == "False"

    @patch("utilities.operator.ClusterOperator")
    def test_get_cluster_operator_custom_conditions(self, mock_co_class):
        """Test getting cluster operator status with custom condition types"""
        mock_admin_client = MagicMock()

        mock_co = MagicMock()
        mock_co.name = "authentication"
        mock_co.instance.get.return_value = {
            "conditions": [
                {"type": "Available", "status": "True"},
                {"type": "Progressing", "status": "False"},
                {"type": "Degraded", "status": "False"},
            ]
        }

        mock_co_class.get.return_value = [mock_co]

        result = get_cluster_operator_status_conditions(
            mock_admin_client,
            operator_conditions={"Available": "True", "Progressing": "False"},
        )

        assert "authentication" in result
        assert "Available" in result["authentication"]
        assert "Progressing" in result["authentication"]
        assert "Degraded" not in result["authentication"]


# ============================================================================
# COMPLEX FUNCTIONS (7 tests)
# ============================================================================


class TestWaitForClusterOperatorStabilize:
    """Test cases for wait_for_cluster_operator_stabilize function"""

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_failed_cluster_operator")
    def test_wait_stabilize_success_immediate(self, mock_get_failed, mock_sampler):
        """Test cluster operators stabilize immediately"""
        mock_admin_client = MagicMock()

        # No failed operators
        mock_get_failed.return_value = {}

        # Mock TimeoutSampler to return empty dict 3 times
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([{}, {}, {}]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_cluster_operator_stabilize(mock_admin_client)

        mock_sampler.assert_called_once()
        assert mock_sampler.call_args[1]["func"] == mock_get_failed

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_failed_cluster_operator")
    def test_wait_stabilize_success_after_retries(self, mock_get_failed, mock_sampler):
        """Test cluster operators stabilize after some retries"""
        mock_admin_client = MagicMock()

        # Mock TimeoutSampler to return failed operators then empty
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(
            return_value=iter([
                {"console": {"Available": "False"}},  # First check - failed
                {"console": {"Available": "False"}},  # Second check - failed
                {},  # Third check - stable
                {},  # Fourth check - stable
                {},  # Fifth check - stable (3 consecutive)
            ])
        )
        mock_sampler.return_value = mock_sampler_instance

        wait_for_cluster_operator_stabilize(mock_admin_client)

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_failed_cluster_operator")
    def test_wait_stabilize_timeout(self, mock_get_failed, mock_sampler):
        """Test timeout when cluster operators don't stabilize"""
        mock_admin_client = MagicMock()

        # Mock TimeoutSampler to return failed operators then raise timeout
        failed_operators = {"console": {"Available": "False"}}

        class MockSamplerIterator:
            def __init__(self):
                self.count = 0

            def __iter__(self):
                return self

            def __next__(self):
                self.count += 1
                if self.count > 3:
                    raise TimeoutExpiredError("Timeout", failed_operators)
                return failed_operators

        mock_sampler.return_value = MockSamplerIterator()

        with pytest.raises(TimeoutExpiredError):
            wait_for_cluster_operator_stabilize(mock_admin_client)

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_failed_cluster_operator")
    def test_wait_stabilize_custom_timeout(self, mock_get_failed, mock_sampler):
        """Test wait_for_cluster_operator_stabilize with custom timeout"""
        mock_admin_client = MagicMock()

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([{}, {}, {}]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_cluster_operator_stabilize(mock_admin_client, wait_timeout=600)

        # Verify custom timeout was used
        assert mock_sampler.call_args[1]["wait_timeout"] == 600


class TestWaitForMcpUpdatedConditionTrue:
    """Test cases for wait_for_mcp_updated_condition_true function"""

    @patch("utilities.operator.consecutive_checks_for_mcp_condition")
    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_mcps_with_true_condition_status")
    @patch("utilities.operator.MachineConfigPool")
    def test_wait_for_mcp_updated_success(
        self,
        mock_mcp_class,
        mock_get_mcps,
        mock_sampler,
        mock_consecutive_checks,
    ):
        """Test waiting for MCP updated condition successfully"""
        mock_mcp_class.Status.UPDATED = "Updated"

        mock_mcp1 = MagicMock()
        mock_mcp1.name = "worker"
        mock_mcp2 = MagicMock()
        mock_mcp2.name = "master"

        machine_config_pools_list = [mock_mcp1, mock_mcp2]

        wait_for_mcp_updated_condition_true(machine_config_pools_list)

        mock_sampler.assert_called_once()
        mock_consecutive_checks.assert_called_once()

        # Verify sampler was called with correct parameters
        call_kwargs = mock_sampler.call_args[1]
        assert call_kwargs["func"] == mock_get_mcps
        assert call_kwargs["condition_type"] == "Updated"
        assert call_kwargs["machine_config_pools_list"] == machine_config_pools_list

    @patch("utilities.operator.consecutive_checks_for_mcp_condition")
    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_mcps_with_true_condition_status")
    @patch("utilities.operator.MachineConfigPool")
    @patch("utilities.operator.TIMEOUT_75MIN", 4500)
    @patch("utilities.operator.TIMEOUT_5SEC", 5)
    def test_wait_for_mcp_updated_custom_timeouts(
        self,
        mock_mcp_class,
        mock_get_mcps,
        mock_sampler,
        mock_consecutive_checks,
    ):
        """Test waiting for MCP with custom timeout and sleep values"""
        mock_mcp_class.Status.UPDATED = "Updated"

        mock_mcp = MagicMock()
        mock_mcp.name = "worker"

        wait_for_mcp_updated_condition_true([mock_mcp], timeout=1800, sleep=10)

        # Verify custom timeout and sleep were used
        call_kwargs = mock_sampler.call_args[1]
        assert call_kwargs["wait_timeout"] == 1800
        assert call_kwargs["sleep"] == 10

    @patch("utilities.operator.consecutive_checks_for_mcp_condition")
    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.BASE_EXCEPTIONS_DICT", {"Exception": []})
    @patch("utilities.operator.MachineConfigPool")
    def test_wait_for_mcp_updated_with_exception_dict(
        self,
        mock_mcp_class,
        mock_sampler,
        mock_consecutive_checks,
    ):
        """Test that BASE_EXCEPTIONS_DICT is passed to TimeoutSampler"""
        mock_mcp_class.Status.UPDATED = "Updated"

        mock_mcp = MagicMock()
        machine_config_pools_list = [mock_mcp]

        wait_for_mcp_updated_condition_true(machine_config_pools_list)

        # Verify exceptions_dict was passed
        call_kwargs = mock_sampler.call_args[1]
        assert "exceptions_dict" in call_kwargs
        assert call_kwargs["exceptions_dict"] == {"Exception": []}


# ============================================================================
# NEW COMPREHENSIVE TESTS FOR UNCOVERED FUNCTIONS
# ============================================================================


class TestGenerateIcspIdmsFile:
    """Test cases for generate_icsp_idms_file function"""

    @patch("utilities.operator.os.path.isfile")
    @patch("utilities.operator.os.path.join")
    @patch("utilities.operator.run_command")
    @patch("utilities.operator.generate_unique_icsp_idms_file")
    @patch("utilities.operator.IDMS_FILE", "imageDigestMirrorSet.yaml")
    @patch("utilities.operator.ICSP_FILE", "imageContentSourcePolicy.yaml")
    def test_generate_idms_file_success(
        self,
        mock_generate_unique,
        mock_run_command,
        mock_join,
        mock_isfile,
    ):
        """Test generating IDMS file successfully"""
        mock_run_command.return_value = (True, "", "")
        mock_join.return_value = "/tmp/manifests/imageDigestMirrorSet.yaml"
        mock_isfile.return_value = True

        result = generate_icsp_idms_file(
            folder_name="/tmp/manifests",
            command="oc adm catalog mirror ...",
            is_idms_file=True,
        )

        assert result == "/tmp/manifests/imageDigestMirrorSet.yaml"
        mock_run_command.assert_called_once()
        mock_isfile.assert_called_once_with("/tmp/manifests/imageDigestMirrorSet.yaml")
        mock_generate_unique.assert_not_called()

    @patch("utilities.operator.os.path.isfile")
    @patch("utilities.operator.os.path.join")
    @patch("utilities.operator.run_command")
    @patch("utilities.operator.ICSP_FILE", "imageContentSourcePolicy.yaml")
    def test_generate_icsp_file_success(
        self,
        mock_run_command,
        mock_join,
        mock_isfile,
    ):
        """Test generating ICSP file successfully"""
        mock_run_command.return_value = (True, "", "")
        mock_join.return_value = "/tmp/manifests/imageContentSourcePolicy.yaml"
        mock_isfile.return_value = True

        result = generate_icsp_idms_file(
            folder_name="/tmp/manifests",
            command="oc adm catalog mirror ...",
            is_idms_file=False,
        )

        assert result == "/tmp/manifests/imageContentSourcePolicy.yaml"

    @patch("utilities.operator.os.path.isfile")
    @patch("utilities.operator.os.path.join")
    @patch("utilities.operator.run_command")
    @patch("utilities.operator.generate_unique_icsp_idms_file")
    @patch("utilities.operator.IDMS_FILE", "imageDigestMirrorSet.yaml")
    def test_generate_idms_file_with_version(
        self,
        mock_generate_unique,
        mock_run_command,
        mock_join,
        mock_isfile,
    ):
        """Test generating IDMS file with CNV version"""
        mock_run_command.return_value = (True, "", "")
        mock_join.return_value = "/tmp/manifests/imageDigestMirrorSet.yaml"
        mock_isfile.return_value = True
        mock_generate_unique.return_value = "/tmp/manifests/imageDigestMirrorSet4200.yaml"

        result = generate_icsp_idms_file(
            folder_name="/tmp/manifests",
            command="oc adm catalog mirror ...",
            is_idms_file=True,
            cnv_version="v4.20.0",
        )

        assert result == "/tmp/manifests/imageDigestMirrorSet4200.yaml"
        mock_generate_unique.assert_called_once_with(
            file_name="/tmp/manifests/imageDigestMirrorSet.yaml",
            version_string="4200",
        )

    @patch("utilities.operator.os.path.isfile")
    @patch("utilities.operator.os.path.join")
    @patch("utilities.operator.run_command")
    def test_generate_icsp_file_command_failure(
        self,
        mock_run_command,
        mock_join,
        mock_isfile,
    ):
        """Test generating ICSP file when command fails"""
        mock_run_command.return_value = (False, "", "Error")

        with pytest.raises(AssertionError):
            generate_icsp_idms_file(
                folder_name="/tmp/manifests",
                command="oc adm catalog mirror ...",
                is_idms_file=False,
            )

    @patch("utilities.operator.os.path.isfile")
    @patch("utilities.operator.os.path.join")
    @patch("utilities.operator.run_command")
    def test_generate_icsp_file_not_exist(
        self,
        mock_run_command,
        mock_join,
        mock_isfile,
    ):
        """Test generating ICSP file when file doesn't exist"""
        mock_run_command.return_value = (True, "", "")
        mock_join.return_value = "/tmp/manifests/imageContentSourcePolicy.yaml"
        mock_isfile.return_value = False

        with pytest.raises(AssertionError, match="file does not exist"):
            generate_icsp_idms_file(
                folder_name="/tmp/manifests",
                command="oc adm catalog mirror ...",
                is_idms_file=False,
            )


class TestGenerateUniqueIcspIdmsFile:
    """Test cases for generate_unique_icsp_idms_file function"""

    @patch("utilities.operator.os.rename")
    @patch("utilities.operator.yaml.dump")
    @patch("utilities.operator.yaml.safe_load")
    @patch("builtins.open", create=True)
    def test_generate_unique_file_success(
        self,
        mock_open,
        mock_safe_load,
        mock_dump,
        mock_rename,
    ):
        """Test generating unique ICSP/IDMS file"""
        mock_safe_load.return_value = {
            "metadata": {"name": "original-name"},
            "spec": {},
        }

        result = generate_unique_icsp_idms_file(
            file_name="/tmp/imageContentSourcePolicy.yaml",
            version_string="4200",
        )

        assert result == "/tmp/imageContentSourcePolicy4200.yaml"
        mock_rename.assert_called_once_with(
            "/tmp/imageContentSourcePolicy.yaml",
            "/tmp/imageContentSourcePolicy4200.yaml",
        )

    @patch("utilities.operator.os.rename")
    @patch("utilities.operator.yaml.dump")
    @patch("utilities.operator.yaml.safe_load")
    @patch("builtins.open", create=True)
    def test_generate_unique_file_metadata_update(
        self,
        mock_open,
        mock_safe_load,
        mock_dump,
        mock_rename,
    ):
        """Test metadata name is updated correctly"""
        original_yaml = {"metadata": {"name": "original-name"}, "spec": {}}
        mock_safe_load.return_value = original_yaml

        generate_unique_icsp_idms_file(
            file_name="/tmp/imageDigestMirrorSet.yaml",
            version_string="4210",
        )

        # Verify yaml.dump was called with updated metadata
        call_args = mock_dump.call_args[0]
        assert call_args[0]["metadata"]["name"] == "iib-4210"


class TestCreateIcspIdmsFromFile:
    """Test cases for create_icsp_idms_from_file function"""

    @patch("utilities.operator.run_command")
    def test_create_icsp_from_file_success(self, mock_run_command):
        """Test creating ICSP from file successfully"""
        mock_run_command.return_value = (True, "", "")

        create_icsp_idms_from_file("/tmp/imageContentSourcePolicy.yaml")

        mock_run_command.assert_called_once()
        call_args = mock_run_command.call_args[1]["command"]
        assert "oc" in call_args
        assert "create" in call_args
        assert "-f" in call_args

    @patch("utilities.operator.run_command")
    def test_create_icsp_from_file_failure(self, mock_run_command):
        """Test creating ICSP from file when command fails"""
        mock_run_command.return_value = (False, "", "Error")

        with pytest.raises(AssertionError):
            create_icsp_idms_from_file("/tmp/imageContentSourcePolicy.yaml")


class TestDeleteExistingIcspIdms:
    """Test cases for delete_existing_icsp_idms function"""

    @patch("utilities.operator.ImageContentSourcePolicy")
    def test_delete_existing_icsp(self, mock_icsp_class):
        """Test deleting existing ICSP resources"""
        mock_icsp1 = MagicMock()
        mock_icsp1.name = "iib-4200"
        mock_icsp2 = MagicMock()
        mock_icsp2.name = "iib-4210"
        mock_icsp3 = MagicMock()
        mock_icsp3.name = "other-icsp"

        mock_icsp_class.get.return_value = [mock_icsp1, mock_icsp2, mock_icsp3]

        delete_existing_icsp_idms(name="iib", is_idms_file=False)

        mock_icsp1.delete.assert_called_once_with(wait=True)
        mock_icsp2.delete.assert_called_once_with(wait=True)
        mock_icsp3.delete.assert_not_called()

    @patch("utilities.operator.ImageDigestMirrorSet")
    def test_delete_existing_idms(self, mock_idms_class):
        """Test deleting existing IDMS resources"""
        mock_idms1 = MagicMock()
        mock_idms1.name = "iib-4200"

        mock_idms_class.get.return_value = [mock_idms1]

        delete_existing_icsp_idms(name="iib", is_idms_file=True)

        mock_idms1.delete.assert_called_once_with(wait=True)

    @patch("utilities.operator.ImageContentSourcePolicy")
    def test_delete_existing_icsp_no_matches(self, mock_icsp_class):
        """Test deleting ICSP when no resources match"""
        mock_icsp = MagicMock()
        mock_icsp.name = "other-icsp"

        mock_icsp_class.get.return_value = [mock_icsp]

        delete_existing_icsp_idms(name="iib", is_idms_file=False)

        mock_icsp.delete.assert_not_called()


class TestGetMcpsWithDifferentTransitionTimes:
    """Test cases for get_mcps_with_different_transition_times function"""

    def test_get_mcps_with_different_times(self):
        """Test getting MCPs with different transition times"""
        mock_mcp1 = MagicMock()
        mock_mcp1.name = "worker"
        mock_mcp1.instance.status.conditions = [
            {
                "type": "Updated",
                "lastTransitionTime": "2024-01-15T10:30:00Z",
            }
        ]

        mock_mcp2 = MagicMock()
        mock_mcp2.name = "master"
        mock_mcp2.instance.status.conditions = [
            {
                "type": "Updated",
                "lastTransitionTime": "2024-01-15T10:00:00Z",
            }
        ]

        initial_times = {
            "worker": "2024-01-15T10:00:00Z",
            "master": "2024-01-15T10:00:00Z",
        }

        result = get_mcps_with_different_transition_times(
            condition_type="Updated",
            machine_config_pools_list=[mock_mcp1, mock_mcp2],
            initial_transition_times=initial_times,
        )

        assert "worker" in result
        assert "master" not in result

    def test_get_mcps_no_different_times(self):
        """Test when no MCPs have different transition times"""
        mock_mcp = MagicMock()
        mock_mcp.name = "worker"
        mock_mcp.instance.status.conditions = [
            {
                "type": "Updated",
                "lastTransitionTime": "2024-01-15T10:00:00Z",
            }
        ]

        initial_times = {"worker": "2024-01-15T10:00:00Z"}

        result = get_mcps_with_different_transition_times(
            condition_type="Updated",
            machine_config_pools_list=[mock_mcp],
            initial_transition_times=initial_times,
        )

        assert len(result) == 0


class TestGetMcpsWithAllMachinesReady:
    """Test cases for get_mcps_with_all_machines_ready function"""

    def test_get_mcps_all_ready(self):
        """Test getting MCPs where all machines are ready"""
        mock_mcp1 = MagicMock()
        mock_mcp1.name = "worker"
        mock_mcp1.instance.status.readyMachineCount = 3
        mock_mcp1.instance.status.machineCount = 3
        mock_mcp1.instance.status.updatedMachineCount = 3

        mock_mcp2 = MagicMock()
        mock_mcp2.name = "master"
        mock_mcp2.instance.status.readyMachineCount = 3
        mock_mcp2.instance.status.machineCount = 3
        mock_mcp2.instance.status.updatedMachineCount = 2

        result = get_mcps_with_all_machines_ready([mock_mcp1, mock_mcp2])

        assert "worker" in result
        assert "master" not in result

    def test_get_mcps_none_ready(self):
        """Test when no MCPs have all machines ready"""
        mock_mcp = MagicMock()
        mock_mcp.name = "worker"
        mock_mcp.instance.status.readyMachineCount = 2
        mock_mcp.instance.status.machineCount = 3
        mock_mcp.instance.status.updatedMachineCount = 3

        result = get_mcps_with_all_machines_ready([mock_mcp])

        assert len(result) == 0


class TestWaitForMcpReadyMachineCount:
    """Test cases for wait_for_mcp_ready_machine_count function"""

    @patch("utilities.operator.consecutive_checks_for_mcp_condition")
    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_mcps_with_all_machines_ready")
    def test_wait_for_ready_machine_count(
        self,
        mock_get_mcps,
        mock_sampler,
        mock_consecutive_checks,
    ):
        """Test waiting for MCP ready machine count"""
        mock_mcp = MagicMock()
        mock_mcp.name = "worker"

        wait_for_mcp_ready_machine_count([mock_mcp])

        mock_sampler.assert_called_once()
        mock_consecutive_checks.assert_called_once()


class TestConsecutiveChecksForMcpCondition:
    """Test cases for consecutive_checks_for_mcp_condition function"""

    def test_consecutive_checks_success(self):
        """Test consecutive checks succeed after 3 consecutive matches"""
        mock_mcp1 = MagicMock()
        mock_mcp1.name = "worker"
        mock_mcp2 = MagicMock()
        mock_mcp2.name = "master"

        mock_sampler = MagicMock()
        mock_sampler.__iter__ = MagicMock(
            return_value=iter([
                {"worker", "master"},
                {"worker", "master"},
                {"worker", "master"},
            ])
        )
        mock_sampler.wait_timeout = 600

        consecutive_checks_for_mcp_condition(
            mcp_sampler=mock_sampler,
            machine_config_pools_list=[mock_mcp1, mock_mcp2],
        )

    @patch("utilities.operator.collect_mcp_data_on_update_timeout")
    @patch("utilities.operator.MachineConfigPool")
    def test_consecutive_checks_timeout(
        self,
        mock_mcp_class,
        mock_collect_data,
    ):
        """Test consecutive checks timeout"""
        mock_mcp_class.Status.UPDATED = "Updated"

        mock_mcp = MagicMock()
        mock_mcp.name = "worker"

        class MockSamplerIterator:
            wait_timeout = 600

            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutExpiredError("Timeout")

        mock_sampler = MockSamplerIterator()

        with pytest.raises(TimeoutExpiredError):
            consecutive_checks_for_mcp_condition(
                mcp_sampler=mock_sampler,
                machine_config_pools_list=[mock_mcp],
            )

        mock_collect_data.assert_called_once()


class TestWaitForMcpUpdateEnd:
    """Test cases for wait_for_mcp_update_end function"""

    @patch("utilities.operator.wait_for_mcp_ready_machine_count")
    @patch("utilities.operator.wait_for_mcp_updated_condition_true")
    def test_wait_for_update_end(
        self,
        mock_wait_updated,
        mock_wait_ready,
    ):
        """Test waiting for MCP update to end"""
        mock_mcp = MagicMock()

        wait_for_mcp_update_end([mock_mcp])

        mock_wait_updated.assert_called_once_with(
            machine_config_pools_list=[mock_mcp],
            timeout=TIMEOUT_75MIN,
            sleep=TIMEOUT_5SEC,
        )
        mock_wait_ready.assert_called_once_with(machine_config_pools_list=[mock_mcp])

    @patch("utilities.operator.wait_for_mcp_ready_machine_count")
    @patch("utilities.operator.wait_for_mcp_updated_condition_true")
    def test_wait_for_update_end_custom_args(self, mock_wait_updated, mock_wait_ready):
        """Test waiting for MCP update to end with custom timeout and sleep"""
        mock_mcp = MagicMock()
        custom_timeout = 100
        custom_sleep = 1

        wait_for_mcp_update_end([mock_mcp], timeout=custom_timeout, sleep=custom_sleep)

        mock_wait_updated.assert_called_once_with(
            machine_config_pools_list=[mock_mcp],
            timeout=custom_timeout,
            sleep=custom_sleep,
        )
        mock_wait_ready.assert_called_once_with(machine_config_pools_list=[mock_mcp])

    @patch("utilities.operator.wait_for_mcp_ready_machine_count")
    @patch("utilities.operator.wait_for_mcp_updated_condition_true")
    def test_wait_for_update_end_partial_args(self, mock_wait_updated, mock_wait_ready):
        """Test waiting for MCP update to end with only custom timeout"""
        mock_mcp = MagicMock()
        custom_timeout = 500

        wait_for_mcp_update_end([mock_mcp], timeout=custom_timeout)

        mock_wait_updated.assert_called_once_with(
            machine_config_pools_list=[mock_mcp],
            timeout=custom_timeout,
            sleep=TIMEOUT_5SEC,
        )
        mock_wait_ready.assert_called_once_with(machine_config_pools_list=[mock_mcp])


class TestWaitForMcpUpdateStart:
    """Test cases for wait_for_mcp_update_start function"""

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_mcps_with_different_transition_times")
    @patch("utilities.operator.MachineConfigPool")
    def test_wait_for_update_start_success(
        self,
        mock_mcp_class,
        mock_get_mcps,
        mock_sampler,
    ):
        """Test waiting for MCP update to start successfully"""
        mock_mcp_class.Status.UPDATING = "Updating"

        mock_mcp = MagicMock()
        mock_mcp.name = "worker"

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([{"worker"}]))
        mock_sampler.return_value = mock_sampler_instance

        initial_times = {"worker": "2024-01-15T10:00:00Z"}

        wait_for_mcp_update_start([mock_mcp], initial_times)

        mock_sampler.assert_called_once()

    @patch("utilities.operator.collect_mcp_data_on_update_timeout")
    @patch("utilities.operator.get_mcps_with_true_condition_status")
    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.MachineConfigPool")
    def test_wait_for_update_start_timeout_with_updated(
        self,
        mock_mcp_class,
        mock_sampler,
        mock_get_true_status,
        mock_collect_data,
    ):
        """Test timeout but some MCPs reached Updated status"""
        mock_mcp_class.Status.UPDATING = "Updating"
        mock_mcp_class.Status.UPDATED = "Updated"

        mock_mcp = MagicMock()
        mock_mcp.name = "worker"

        class MockSamplerIterator:
            wait_timeout = 600

            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = MockSamplerIterator()
        mock_get_true_status.return_value = {"worker"}

        initial_times = {"worker": "2024-01-15T10:00:00Z"}

        # Should not raise because MCPs reached Updated
        wait_for_mcp_update_start([mock_mcp], initial_times)

        mock_collect_data.assert_called_once()


class TestCollectMcpDataOnUpdateTimeout:
    """Test cases for collect_mcp_data_on_update_timeout function"""

    @patch("utilities.operator.collect_ocp_must_gather")
    def test_collect_mcp_data(self, mock_collect_gather):
        """Test collecting MCP data on timeout"""
        mock_mcp = MagicMock()
        mock_mcp.name = "worker"
        mock_mcp.instance.status.conditions = [{"type": "Updated", "status": "True"}]

        collect_mcp_data_on_update_timeout(
            machine_config_pools_list=[mock_mcp],
            not_matching_mcps={"worker"},
            condition_type="Updated",
            since_time=600,
        )

        mock_collect_gather.assert_called_once_with(since_time=600)


class TestGetMachineConfigPoolsConditions:
    """Test cases for get_machine_config_pools_conditions function"""

    def test_get_mcp_conditions(self):
        """Test getting MCP conditions dictionary"""
        mock_mcp1 = MagicMock()
        mock_mcp1.name = "worker"
        mock_mcp1.instance.status.conditions = [{"type": "Updated", "status": "True"}]

        mock_mcp2 = MagicMock()
        mock_mcp2.name = "master"
        mock_mcp2.instance.status.conditions = [{"type": "Updating", "status": "False"}]

        result = get_machine_config_pools_conditions([mock_mcp1, mock_mcp2])

        assert "worker" in result
        assert "master" in result
        assert result["worker"] == [{"type": "Updated", "status": "True"}]
        assert result["master"] == [{"type": "Updating", "status": "False"}]


class TestDisableDefaultSourcesInOperatorHub:
    """Test cases for disable_default_sources_in_operatorhub function"""

    @patch("utilities.operator.wait_for_catalog_source_disabled")
    @patch("utilities.operator.ResourceEditor")
    @patch("utilities.operator.get_operator_hub")
    def test_disable_sources(
        self,
        mock_get_operator_hub,
        mock_editor_class,
        mock_wait_disabled,
    ):
        """Test disabling default sources in OperatorHub"""
        mock_admin_client = MagicMock()

        mock_operator_hub = MagicMock()
        mock_operator_hub.instance.status.sources = [
            {"name": "redhat-operators"},
            {"name": "community-operators"},
        ]
        mock_get_operator_hub.return_value = mock_operator_hub

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=False)
        mock_editor_class.return_value = mock_editor

        with disable_default_sources_in_operatorhub(mock_admin_client) as result:
            assert result == mock_editor

        assert mock_wait_disabled.call_count == 2


class TestWaitForCatalogSourceDisabled:
    """Test cases for wait_for_catalog_source_disabled function"""

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_catalog_source")
    def test_wait_catalog_disabled_success(
        self,
        mock_get_catalog,
        mock_sampler,
    ):
        """Test waiting for catalog source to be disabled"""
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([None]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_catalog_source_disabled("test-catalog")

        mock_sampler.assert_called_once()

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_catalog_source")
    def test_wait_catalog_disabled_timeout(
        self,
        mock_get_catalog,
        mock_sampler,
    ):
        """Test timeout when catalog source doesn't get disabled"""

        class MockSamplerIterator:
            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = MockSamplerIterator()

        with pytest.raises(TimeoutExpiredError):
            wait_for_catalog_source_disabled("test-catalog")


class TestCreateCatalogSource:
    """Test cases for create_catalog_source function"""

    @patch("utilities.operator.py_config")
    @patch("utilities.operator.CatalogSource")
    def test_create_catalog_source(self, mock_catalog_class, mock_config):
        """Test creating catalog source"""
        mock_config.__getitem__.return_value = "openshift-marketplace"

        mock_catalog = MagicMock()
        mock_catalog.__enter__ = MagicMock(return_value=mock_catalog)
        mock_catalog.__exit__ = MagicMock(return_value=False)
        mock_catalog_class.return_value = mock_catalog

        result = create_catalog_source(
            catalog_name="test-catalog",
            image="registry.io/catalog:latest",
        )

        assert result == mock_catalog
        mock_catalog_class.assert_called_once()


class TestWaitForCatalogsourceReady:
    """Test cases for wait_for_catalogsource_ready function"""

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.utilities.infra.get_pods")
    @patch("utilities.operator.py_config")
    @patch("utilities.operator.Namespace")
    @patch("utilities.operator.Pod")
    def test_wait_catalogsource_ready_success(
        self,
        mock_pod_class,
        mock_namespace_class,
        mock_config,
        mock_get_pods,
        mock_sampler,
    ):
        """Test waiting for catalog source pods to be ready"""
        mock_admin_client = MagicMock()
        mock_config.__getitem__.return_value = "openshift-marketplace"
        mock_pod_class.Status.RUNNING = "Running"

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[]]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_catalogsource_ready(mock_admin_client, "test-catalog")

        mock_sampler.assert_called_once()

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.utilities.infra.get_pods")
    @patch("utilities.operator.py_config")
    @patch("utilities.operator.Namespace")
    @patch("utilities.operator.Pod")
    def test_wait_catalogsource_ready_timeout(
        self,
        mock_pod_class,
        mock_namespace_class,
        mock_config,
        mock_get_pods,
        mock_sampler,
    ):
        """Test timeout when catalog source pods don't become ready"""
        mock_admin_client = MagicMock()
        mock_config.__getitem__.return_value = "openshift-marketplace"

        class MockSamplerIterator:
            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = MockSamplerIterator()

        with pytest.raises(TimeoutExpiredError):
            wait_for_catalogsource_ready(mock_admin_client, "test-catalog")


class TestCreateOperatorGroup:
    """Test cases for create_operator_group function"""

    @patch("utilities.operator.OperatorGroup")
    def test_create_operator_group_basic(self, mock_og_class):
        """Test creating operator group"""
        mock_og = MagicMock()
        mock_og.__enter__ = MagicMock(return_value=mock_og)
        mock_og.__exit__ = MagicMock(return_value=False)
        mock_og_class.return_value = mock_og

        result = create_operator_group(
            operator_group_name="test-og",
            namespace_name="test-namespace",
        )

        assert result == mock_og
        mock_og_class.assert_called_once_with(
            name="test-og",
            namespace="test-namespace",
            target_namespaces=None,
            teardown=False,
        )

    @patch("utilities.operator.OperatorGroup")
    def test_create_operator_group_with_targets(self, mock_og_class):
        """Test creating operator group with target namespaces"""
        mock_og = MagicMock()
        mock_og.__enter__ = MagicMock(return_value=mock_og)
        mock_og.__exit__ = MagicMock(return_value=False)
        mock_og_class.return_value = mock_og

        create_operator_group(
            operator_group_name="test-og",
            namespace_name="test-namespace",
            target_namespaces=["ns1", "ns2"],
        )

        call_kwargs = mock_og_class.call_args[1]
        assert call_kwargs["target_namespaces"] == ["ns1", "ns2"]


class TestCreateSubscription:
    """Test cases for create_subscription function"""

    @patch("utilities.operator.py_config")
    @patch("utilities.operator.Subscription")
    def test_create_subscription_basic(self, mock_sub_class, mock_config):
        """Test creating subscription with default values"""
        mock_config.__getitem__.return_value = "openshift-marketplace"

        mock_sub = MagicMock()
        mock_sub.__enter__ = MagicMock(return_value=mock_sub)
        mock_sub.__exit__ = MagicMock(return_value=False)
        mock_sub_class.return_value = mock_sub

        result = create_subscription(
            subscription_name="test-sub",
            package_name="test-package",
            namespace_name="test-namespace",
            catalogsource_name="test-catalog",
        )

        assert result == mock_sub
        call_kwargs = mock_sub_class.call_args[1]
        assert call_kwargs["channel"] == "stable"
        assert call_kwargs["install_plan_approval"] == "Automatic"

    @patch("utilities.operator.py_config")
    @patch("utilities.operator.Subscription")
    def test_create_subscription_custom(self, mock_sub_class, mock_config):
        """Test creating subscription with custom values"""
        mock_config.__getitem__.return_value = "openshift-marketplace"

        mock_sub = MagicMock()
        mock_sub.__enter__ = MagicMock(return_value=mock_sub)
        mock_sub.__exit__ = MagicMock(return_value=False)
        mock_sub_class.return_value = mock_sub

        create_subscription(
            subscription_name="test-sub",
            package_name="test-package",
            namespace_name="test-namespace",
            catalogsource_name="test-catalog",
            channel_name="candidate",
            install_plan_approval="Manual",
        )

        call_kwargs = mock_sub_class.call_args[1]
        assert call_kwargs["channel"] == "candidate"
        assert call_kwargs["install_plan_approval"] == "Manual"


class TestApproveInstallPlan:
    """Test cases for approve_install_plan function"""

    @patch("utilities.operator.ResourceEditor")
    def test_approve_install_plan(self, mock_editor_class):
        """Test approving install plan"""
        mock_install_plan = MagicMock()
        mock_install_plan.Status.COMPLETE = "Complete"

        mock_editor = MagicMock()
        mock_editor_class.return_value = mock_editor

        approve_install_plan(mock_install_plan)

        mock_editor.update.assert_called_once()
        mock_install_plan.wait_for_status.assert_called_once()


class TestGetInstallPlanFromSubscription:
    """Test cases for get_install_plan_from_subscription function"""

    @patch("utilities.operator.TimeoutSampler")
    def test_get_install_plan_success(self, mock_sampler):
        """Test getting install plan from subscription"""
        mock_subscription = MagicMock()
        mock_subscription.name = "test-sub"
        mock_subscription.instance.status.installplan = {"name": "install-plan-abc123"}

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([{"name": "install-plan-abc123"}]))
        mock_sampler.return_value = mock_sampler_instance

        result = get_install_plan_from_subscription(mock_subscription)

        assert result == "install-plan-abc123"

    @patch("utilities.operator.TimeoutSampler")
    def test_get_install_plan_timeout(self, mock_sampler):
        """Test timeout when install plan not created"""
        mock_subscription = MagicMock()
        mock_subscription.name = "test-sub"

        class MockSamplerIterator:
            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = MockSamplerIterator()

        with pytest.raises(TimeoutExpiredError):
            get_install_plan_from_subscription(mock_subscription)


class TestWaitForCsvSuccessfulState:
    """Test cases for wait_for_csv_successful_state function"""

    @patch("utilities.operator.utilities.infra.get_csv_by_name")
    @patch("utilities.operator.Subscription")
    @patch("utilities.operator.ClusterServiceVersion")
    def test_wait_csv_success(
        self,
        mock_csv_class,
        mock_sub_class,
        mock_get_csv,
    ):
        """Test waiting for CSV to reach Succeeded state"""
        mock_admin_client = MagicMock()
        mock_csv_class.Status.SUCCEEDED = "Succeeded"

        mock_subscription = MagicMock()
        mock_subscription.exists = True
        mock_subscription.instance.status.installedCSV = "csv-v1.0.0"
        mock_sub_class.return_value = mock_subscription

        mock_csv = MagicMock()
        mock_get_csv.return_value = mock_csv

        wait_for_csv_successful_state(
            mock_admin_client,
            "test-namespace",
            "test-sub",
        )

        mock_csv.wait_for_status.assert_called_once_with(
            status="Succeeded",
            timeout=600,
        )

    @patch("utilities.operator.Subscription")
    def test_wait_csv_subscription_not_found(self, mock_sub_class):
        """Test error when subscription not found"""
        mock_admin_client = MagicMock()

        mock_subscription = MagicMock()
        mock_subscription.exists = False
        mock_sub_class.return_value = mock_subscription

        with pytest.raises(ResourceNotFoundError):
            wait_for_csv_successful_state(
                mock_admin_client,
                "test-namespace",
                "test-sub",
            )


class TestWaitForMcpUpdateCompletion:
    """Test cases for wait_for_mcp_update_completion function"""

    @patch("utilities.operator.wait_for_all_nodes_ready")
    @patch("utilities.operator.wait_for_nodes_to_have_same_kubelet_version")
    @patch("utilities.operator.wait_for_mcp_update_end")
    @patch("utilities.operator.wait_for_mcp_update_start")
    @patch("utilities.operator.get_mcp_updating_transition_times")
    def test_wait_mcp_update_completion(
        self,
        mock_get_times,
        mock_wait_start,
        mock_wait_end,
        mock_wait_kubelet,
        mock_wait_nodes,
    ):
        """Test waiting for MCP update completion"""
        mock_mcp = MagicMock()
        mock_node = MagicMock()

        mock_get_times.return_value = {"worker": "2024-01-15T10:00:00Z"}

        initial_conditions = {"worker": [{"type": "Updating", "lastTransitionTime": "2024-01-15T10:00:00Z"}]}

        wait_for_mcp_update_completion(
            machine_config_pools_list=[mock_mcp],
            initial_mcp_conditions=initial_conditions,
            nodes=[mock_node],
        )

        mock_get_times.assert_called_once_with(mcp_conditions=initial_conditions)
        mock_wait_start.assert_called_once()
        mock_wait_end.assert_called_once()
        mock_wait_kubelet.assert_called_once()
        mock_wait_nodes.assert_called_once()


class TestWaitForAllNodesReady:
    """Test cases for wait_for_all_nodes_ready function"""

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_nodes_not_ready")
    def test_wait_all_nodes_ready_success(
        self,
        mock_get_nodes,
        mock_sampler,
    ):
        """Test waiting for all nodes to be ready"""
        mock_node = MagicMock()

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[], [], []]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_all_nodes_ready([mock_node])

        mock_sampler.assert_called_once()

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.get_nodes_not_ready")
    def test_wait_all_nodes_ready_timeout(
        self,
        mock_get_nodes,
        mock_sampler,
    ):
        """Test timeout when nodes don't become ready"""

        class MockSamplerIterator:
            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = MockSamplerIterator()

        with pytest.raises(TimeoutExpiredError):
            wait_for_all_nodes_ready([MagicMock()])


class TestGetNodesNotReady:
    """Test cases for get_nodes_not_ready function"""

    def test_get_nodes_not_ready(self):
        """Test getting nodes that are not ready"""
        mock_node1 = MagicMock()
        mock_node1.kubelet_ready = True

        mock_node2 = MagicMock()
        mock_node2.kubelet_ready = False

        mock_node3 = MagicMock()
        mock_node3.kubelet_ready = False

        result = get_nodes_not_ready([mock_node1, mock_node2, mock_node3])

        assert len(result) == 2
        assert mock_node1 not in result
        assert mock_node2 in result
        assert mock_node3 in result


class TestWaitForNodesToHaveSameKubeletVersion:
    """Test cases for wait_for_nodes_to_have_same_kubelet_version function"""

    @patch("utilities.operator.TimeoutSampler")
    def test_wait_same_version_success(self, mock_sampler):
        """Test waiting for nodes to have same kubelet version"""
        mock_node1 = MagicMock()
        mock_node1.name = "node1"
        mock_node1.instance.status.nodeInfo.kubeletVersion = "v1.25.0"

        mock_node2 = MagicMock()
        mock_node2.name = "node2"
        mock_node2.instance.status.nodeInfo.kubeletVersion = "v1.25.0"

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([{"node1": "v1.25.0", "node2": "v1.25.0"}]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_nodes_to_have_same_kubelet_version([mock_node1, mock_node2])

        mock_sampler.assert_called_once()

    @patch("utilities.operator.TimeoutSampler")
    def test_wait_same_version_timeout(self, mock_sampler):
        """Test timeout when nodes have different versions"""

        class MockSamplerIterator:
            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = MockSamplerIterator()

        with pytest.raises(TimeoutExpiredError):
            wait_for_nodes_to_have_same_kubelet_version([MagicMock()])


class TestGetMcpUpdatingTransitionTimes:
    """Test cases for get_mcp_updating_transition_times function"""

    @patch("utilities.operator.MachineConfigPool")
    def test_get_updating_times(self, mock_mcp_class):
        """Test extracting updating transition times"""
        mock_mcp_class.Status.UPDATING = "Updating"

        mcp_conditions = {
            "worker": [
                {"type": "Updating", "lastTransitionTime": "2024-01-15T10:00:00Z"},
                {"type": "Updated", "lastTransitionTime": "2024-01-15T09:00:00Z"},
            ],
            "master": [
                {"type": "Updating", "lastTransitionTime": "2024-01-15T10:30:00Z"},
            ],
        }

        result = get_mcp_updating_transition_times(mcp_conditions)

        assert result["worker"] == "2024-01-15T10:00:00Z"
        assert result["master"] == "2024-01-15T10:30:00Z"


class TestCreateOperator:
    """Test cases for create_operator function"""

    def test_create_operator_with_namespace(self):
        """Test creating operator with namespace"""
        mock_operator_class = MagicMock()
        mock_operator = MagicMock()
        mock_operator.exists = False
        mock_operator_class.return_value = mock_operator

        result = create_operator(
            mock_operator_class,
            "test-operator",
            namespace_name="test-namespace",
        )

        mock_operator_class.assert_called_once_with(
            name="test-operator",
            namespace="test-namespace",
        )
        mock_operator.deploy.assert_called_once_with(wait=True)
        assert result == mock_operator

    def test_create_operator_without_namespace(self):
        """Test creating operator without namespace"""
        mock_operator_class = MagicMock()
        mock_operator = MagicMock()
        mock_operator.exists = False
        mock_operator_class.return_value = mock_operator

        create_operator(mock_operator_class, "test-operator")

        mock_operator_class.assert_called_once_with(name="test-operator")
        mock_operator.deploy.assert_called_once_with(wait=True)

    def test_create_operator_already_exists(self):
        """Test creating operator that already exists"""
        mock_operator_class = MagicMock()
        mock_operator = MagicMock()
        mock_operator.exists = True
        mock_operator_class.return_value = mock_operator

        result = create_operator(
            mock_operator_class,
            "test-operator",
            namespace_name="test-namespace",
        )

        mock_operator.deploy.assert_not_called()
        assert result is None


class TestWaitForPackageManifestToExist:
    """Test cases for wait_for_package_manifest_to_exist function"""

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.utilities.infra.get_raw_package_manifest")
    def test_wait_package_manifest_success(
        self,
        mock_get_manifest,
        mock_sampler,
    ):
        """Test waiting for package manifest to exist"""
        mock_dyn_client = MagicMock()

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([{"name": "test"}]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_package_manifest_to_exist(
            mock_dyn_client,
            "test-cr",
            "test-catalog",
        )

        mock_sampler.assert_called_once()

    @patch("utilities.operator.TimeoutSampler")
    @patch("utilities.operator.utilities.infra.get_raw_package_manifest")
    def test_wait_package_manifest_timeout(
        self,
        mock_get_manifest,
        mock_sampler,
    ):
        """Test timeout when package manifest not created"""

        class MockSamplerIterator:
            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = MockSamplerIterator()

        with pytest.raises(TimeoutExpiredError):
            wait_for_package_manifest_to_exist(
                MagicMock(),
                "test-cr",
                "test-catalog",
            )


class TestUpdateImageInCatalogSource:
    """Test cases for update_image_in_catalog_source function"""

    @patch("utilities.operator.wait_for_package_manifest_to_exist")
    @patch("utilities.operator.create_catalog_source")
    @patch("utilities.operator.ResourceEditor")
    @patch("utilities.operator.get_catalog_source")
    def test_update_existing_catalog(
        self,
        mock_get_catalog,
        mock_editor_class,
        mock_create_catalog,
        mock_wait_manifest,
    ):
        """Test updating image in existing catalog source"""
        mock_dyn_client = MagicMock()

        mock_catalog = MagicMock()
        mock_get_catalog.return_value = mock_catalog

        mock_editor = MagicMock()
        mock_editor_class.return_value = mock_editor

        update_image_in_catalog_source(
            mock_dyn_client,
            "registry.io/catalog:v2",
            "test-catalog",
            "test-cr",
        )

        mock_editor.update.assert_called_once()
        mock_create_catalog.assert_not_called()

    @patch("utilities.operator.wait_for_package_manifest_to_exist")
    @patch("utilities.operator.create_catalog_source")
    @patch("utilities.operator.get_catalog_source")
    def test_create_new_catalog(
        self,
        mock_get_catalog,
        mock_create_catalog,
        mock_wait_manifest,
    ):
        """Test creating new catalog source when it doesn't exist"""
        mock_dyn_client = MagicMock()

        mock_get_catalog.return_value = None

        update_image_in_catalog_source(
            mock_dyn_client,
            "registry.io/catalog:v2",
            "test-catalog",
            "test-cr",
        )

        mock_create_catalog.assert_called_once()
        mock_wait_manifest.assert_called_once()


class TestGetGeneratedIcspIdms:
    """Test cases for get_generated_icsp_idms function"""

    @patch("utilities.operator.generate_icsp_idms_file")
    @patch("utilities.operator.create_icsp_idms_command")
    @patch("utilities.operator.BREW_REGISTERY_SOURCE", "brew.registry.io")
    def test_get_generated_idms_with_brew(
        self,
        mock_create_command,
        mock_generate_file,
    ):
        """Test generating IDMS with brew registry"""
        mock_create_command.return_value = "oc adm catalog mirror ..."
        mock_generate_file.return_value = "/tmp/manifests/idms.yaml"

        result = get_generated_icsp_idms(
            image_url="brew.registry.io/image:latest",
            registry_source="mirror.io",
            generated_pulled_secret="/tmp/pull-secret.json",
            pull_secret_directory="/tmp/manifests",
            is_idms_cluster=True,
        )

        assert result == "/tmp/manifests/idms.yaml"
        # Verify pull_secret was used for brew registry
        call_kwargs = mock_create_command.call_args[1]
        assert call_kwargs["pull_secret"] == "/tmp/pull-secret.json"
        assert call_kwargs["source_url"] == "brew.registry.io"

    @patch("utilities.operator.generate_icsp_idms_file")
    @patch("utilities.operator.create_icsp_idms_command")
    def test_get_generated_icsp_without_brew(
        self,
        mock_create_command,
        mock_generate_file,
    ):
        """Test generating ICSP without brew registry"""
        mock_create_command.return_value = "oc adm catalog mirror ..."
        mock_generate_file.return_value = "/tmp/manifests/icsp.yaml"

        result = get_generated_icsp_idms(
            image_url="registry.io/image:latest",
            registry_source="mirror.io",
            generated_pulled_secret="/tmp/pull-secret.json",
            pull_secret_directory="/tmp/manifests",
            is_idms_cluster=False,
        )

        assert result == "/tmp/manifests/icsp.yaml"
        # Verify pull_secret was None for non-brew registry
        call_kwargs = mock_create_command.call_args[1]
        assert call_kwargs["pull_secret"] is None


class TestApplyIcspIdms:
    """Test cases for apply_icsp_idms function"""

    @patch("utilities.operator.wait_for_mcp_update_completion")
    @patch("utilities.operator.create_icsp_idms_from_file")
    @patch("utilities.operator.delete_existing_icsp_idms")
    @patch("utilities.operator.ResourceEditor")
    def test_apply_icsp_with_delete(
        self,
        mock_editor_class,
        mock_delete,
        mock_create,
        mock_wait_completion,
    ):
        """Test applying ICSP with delete option"""
        mock_mcp = MagicMock()
        mock_node = MagicMock()

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=False)
        mock_editor_class.return_value = mock_editor

        apply_icsp_idms(
            file_paths=["/tmp/icsp1.yaml", "/tmp/icsp2.yaml"],
            machine_config_pools=[mock_mcp],
            mcp_conditions={"worker": []},
            nodes=[mock_node],
            is_idms_file=False,
            delete_file=True,
        )

        mock_delete.assert_called_once_with(name="iib", is_idms_file=False)
        assert mock_create.call_count == 2
        mock_wait_completion.assert_called_once()

    @patch("utilities.operator.wait_for_mcp_update_completion")
    @patch("utilities.operator.create_icsp_idms_from_file")
    @patch("utilities.operator.delete_existing_icsp_idms")
    @patch("utilities.operator.ResourceEditor")
    def test_apply_idms_without_delete(
        self,
        mock_editor_class,
        mock_delete,
        mock_create,
        mock_wait_completion,
    ):
        """Test applying IDMS without delete option"""
        mock_mcp = MagicMock()
        mock_node = MagicMock()

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=False)
        mock_editor_class.return_value = mock_editor

        apply_icsp_idms(
            file_paths=["/tmp/idms.yaml"],
            machine_config_pools=[mock_mcp],
            mcp_conditions={"master": []},
            nodes=[mock_node],
            is_idms_file=True,
            delete_file=False,
        )

        mock_delete.assert_not_called()
        mock_create.assert_called_once_with(file_path="/tmp/idms.yaml")
        mock_wait_completion.assert_called_once()
