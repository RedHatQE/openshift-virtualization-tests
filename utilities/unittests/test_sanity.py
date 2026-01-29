# Generated using Claude cli

"""Unit tests for sanity module"""

from unittest.mock import MagicMock, patch

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_utilities.exceptions import NodeNotReadyError, NodeUnschedulableError
from timeout_sampler import TimeoutExpiredError

from utilities.exceptions import ClusterSanityError


class TestStorageSanityCheck:
    """Test cases for storage_sanity_check function"""

    @patch("utilities.sanity.py_config", {"storage_class_matrix": [{"sc1": {}}, {"sc2": {}}, {"sc3": {}}]})
    @patch("utilities.sanity.LOGGER")
    def test_storage_sanity_check_matching_storage_classes(self, mock_logger):
        """Test with matching storage classes - should return True"""
        from utilities.sanity import storage_sanity_check

        cluster_storage_classes = ["sc1", "sc2", "sc3"]

        result = storage_sanity_check(cluster_storage_classes)

        assert result is True
        mock_logger.error.assert_not_called()

    @patch("utilities.sanity.py_config", {"storage_class_matrix": [{"sc1": {}}, {"sc2": {}}, {"sc3": {}}]})
    @patch("utilities.sanity.LOGGER")
    def test_storage_sanity_check_missing_storage_classes(self, mock_logger):
        """Test with missing storage classes - should return False and log error"""
        from utilities.sanity import storage_sanity_check

        cluster_storage_classes = ["sc1", "sc2"]  # sc3 is missing

        result = storage_sanity_check(cluster_storage_classes)

        assert result is False
        mock_logger.error.assert_called_once()
        error_message = mock_logger.error.call_args[0][0]
        assert "Expected" in error_message
        assert "On cluster" in error_message

    @patch("utilities.sanity.py_config", {"storage_class_matrix": [{"sc1": {}}, {"sc2": {}}, {"sc3": {}}]})
    @patch("utilities.sanity.LOGGER")
    def test_storage_sanity_check_extra_storage_classes(self, mock_logger):
        """Test with extra storage classes on cluster - should return True (extra classes are allowed)"""
        from utilities.sanity import storage_sanity_check

        # The function only checks if all expected storage classes exist
        # Extra storage classes on the cluster are allowed
        cluster_storage_classes = ["sc1", "sc2", "sc3", "sc4"]  # sc4 is extra

        result = storage_sanity_check(cluster_storage_classes)

        # This returns True because sc1, sc2, sc3 all exist in cluster
        # The function checks: are all expected classes present? Not: are there extra classes?
        assert result is True
        mock_logger.error.assert_not_called()

    @patch("utilities.sanity.py_config", {"storage_class_matrix": [{"sc3": {}}, {"sc1": {}}, {"sc2": {}}]})
    @patch("utilities.sanity.LOGGER")
    def test_storage_sanity_check_different_order(self, mock_logger):
        """Test with matching storage classes in different order - should return True"""
        from utilities.sanity import storage_sanity_check

        cluster_storage_classes = ["sc1", "sc2", "sc3"]  # different order from config

        result = storage_sanity_check(cluster_storage_classes)

        assert result is True
        mock_logger.error.assert_not_called()

    @patch("utilities.sanity.py_config", {"storage_class_matrix": []})
    @patch("utilities.sanity.LOGGER")
    def test_storage_sanity_check_empty_storage_class_matrix(self, mock_logger):
        """Test with empty storage class matrix - should return True"""
        from utilities.sanity import storage_sanity_check

        cluster_storage_classes = []

        result = storage_sanity_check(cluster_storage_classes)

        assert result is True
        mock_logger.error.assert_not_called()

    @patch("utilities.sanity.py_config", {"storage_class_matrix": [{"sc1": {}}, {"sc2": {}}]})
    @patch("utilities.sanity.LOGGER")
    def test_storage_sanity_check_logging_behavior(self, mock_logger):
        """Test logging behavior for mismatches"""
        from utilities.sanity import storage_sanity_check

        cluster_storage_classes = ["sc1"]  # sc2 is missing

        storage_sanity_check(cluster_storage_classes)

        mock_logger.error.assert_called_once()
        error_call_args = mock_logger.error.call_args[0][0]
        assert "['sc1', 'sc2']" in error_call_args
        assert "['sc1']" in error_call_args


class TestClusterSanity:
    """Test cases for cluster_sanity function"""

    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_skip_cluster_health_check_marker(self, mock_logger):
        """Test skip when '-m cluster_health_check' marker is present"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = "cluster_health_check"

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=[],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        mock_logger.warning.assert_called_once_with("Skipping cluster sanity test, got -m cluster_health_check")

    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_skip_check_flag(self, mock_logger):
        """Test skip when --cluster-sanity-skip-check flag is set"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.side_effect = lambda flag: flag == "--cluster-sanity-skip-check"

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=[],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        # Should have warning about skipping
        warning_calls = list(mock_logger.warning.call_args_list)
        assert any("Skipping cluster sanity check" in str(call) for call in warning_calls)

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_skip_storage_check(
        self, mock_logger, _mock_wait_hco, mock_storage_sanity, _mock_check_vm, _mock_check_webhook
    ):
        """Test skip storage check when --cluster-sanity-skip-storage-check flag is set"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.side_effect = lambda flag: flag == "--cluster-sanity-skip-storage-check"

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=[],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        mock_storage_sanity.assert_not_called()
        # Should have warning about skipping storage check
        warning_calls = list(mock_logger.warning.call_args_list)
        assert any("Skipping storage classes check" in str(call) for call in warning_calls)

    @patch("utilities.sanity.py_config", {"storage_class_matrix": []})
    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_skip_nodes_check(
        self,
        mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test skip nodes check when --cluster-sanity-skip-nodes-check flag is set"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.side_effect = lambda flag: flag == "--cluster-sanity-skip-nodes-check"
        mock_storage_sanity.return_value = True

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=[],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        mock_assert_healthy.assert_not_called()
        mock_assert_schedulable.assert_not_called()
        mock_wait_pods.assert_not_called()
        # Should have warning about skipping nodes check
        warning_calls = list(mock_logger.warning.call_args_list)
        assert any("Skipping nodes check" in str(call) for call in warning_calls)

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_successful_full_check(
        self,
        _mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        mock_check_vm,
        mock_check_webhook,
    ):
        """Test successful full sanity check (all checks pass)"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        mock_admin_client = MagicMock()
        mock_nodes = MagicMock()
        mock_hco_namespace = MagicMock()
        cluster_storage_classes = ["sc1", "sc2"]

        cluster_sanity(
            request=mock_request,
            admin_client=mock_admin_client,
            cluster_storage_classes_names=cluster_storage_classes,
            nodes=mock_nodes,
            hco_namespace=mock_hco_namespace,
        )

        # Verify all checks were called
        mock_storage_sanity.assert_called_once_with(cluster_storage_classes_names=cluster_storage_classes)
        mock_assert_healthy.assert_called_once()
        mock_assert_schedulable.assert_called_once_with(nodes=mock_nodes)
        mock_wait_pods.assert_called_once()
        mock_wait_hco.assert_called_once()
        mock_check_webhook.assert_called_once()
        mock_check_vm.assert_called_once()

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_storage_sanity_error(
        self,
        _mock_logger,
        mock_wait_hco,
        mock_exit_pytest,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test StorageSanityError raised and exit_pytest_execution called"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = False

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        mock_exit_pytest.assert_called_once()
        call_args = mock_exit_pytest.call_args
        assert call_args[1]["filename"] == "cluster_sanity_failure.txt"
        assert "Cluster is missing storage class" in call_args[1]["log_message"]

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_node_unschedulable_error(
        self,
        _mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test NodeUnschedulableError caught and exit_pytest_execution called"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        error_message = "Node is unschedulable"
        mock_assert_healthy.side_effect = NodeUnschedulableError(error_message)

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        mock_exit_pytest.assert_called_once()
        call_args = mock_exit_pytest.call_args
        assert call_args[1]["filename"] == "cluster_sanity_failure.txt"
        assert error_message in call_args[1]["log_message"]

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_node_not_ready_error(
        self,
        _mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test NodeNotReadyError caught and exit_pytest_execution called"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        error_message = "Node is not ready"
        mock_assert_healthy.side_effect = NodeNotReadyError(error_message)

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        mock_exit_pytest.assert_called_once()
        call_args = mock_exit_pytest.call_args
        assert call_args[1]["filename"] == "cluster_sanity_failure.txt"
        assert error_message in call_args[1]["log_message"]

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_cluster_sanity_error(
        self,
        _mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test ClusterSanityError caught and exit_pytest_execution called"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        error_message = "Cluster sanity failed"
        mock_assert_healthy.side_effect = ClusterSanityError(error_message)

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        mock_exit_pytest.assert_called_once()
        call_args = mock_exit_pytest.call_args
        assert call_args[1]["filename"] == "cluster_sanity_failure.txt"
        assert error_message in call_args[1]["log_message"]

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_timeout_expired_error_converted(
        self,
        _mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test TimeoutExpiredError during wait_for_pods_running converted to ClusterSanityError"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "test-namespace"

        mock_wait_pods.side_effect = TimeoutExpiredError("Timeout waiting for pods")

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=mock_hco_namespace,
        )

        mock_exit_pytest.assert_called_once()
        call_args = mock_exit_pytest.call_args
        assert call_args[1]["filename"] == "cluster_sanity_failure.txt"
        assert "Timed out waiting for all pods" in call_args[1]["log_message"]
        assert "test-namespace" in call_args[1]["log_message"]

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_components_called_in_order(
        self,
        _mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        mock_check_vm,
        mock_check_webhook,
    ):
        """Test all components called in correct order (storage, nodes, webhook, HCO)"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        call_order = []

        def track_storage(*args, **kwargs):
            call_order.append("storage")
            return True

        def track_healthy(*args, **kwargs):
            call_order.append("healthy")

        def track_schedulable(*args, **kwargs):
            call_order.append("schedulable")

        def track_pods(*args, **kwargs):
            call_order.append("pods")

        def track_webhook(*args, **kwargs):
            call_order.append("webhook")

        def track_vm(*args, **kwargs):
            call_order.append("vm")

        def track_hco(*args, **kwargs):
            call_order.append("hco")

        mock_storage_sanity.side_effect = track_storage
        mock_assert_healthy.side_effect = track_healthy
        mock_assert_schedulable.side_effect = track_schedulable
        mock_wait_pods.side_effect = track_pods
        mock_check_webhook.side_effect = track_webhook
        mock_check_vm.side_effect = track_vm
        mock_wait_hco.side_effect = track_hco

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        # Verify the order: storage -> healthy -> schedulable -> pods -> webhook -> vm -> hco
        assert call_order == ["storage", "healthy", "schedulable", "pods", "webhook", "vm", "hco"]

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.KUBELET_READY_CONDITION", "Ready")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_assert_nodes_healthy_parameters(
        self,
        _mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test assert_nodes_in_healthy_condition called with correct parameters"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        mock_nodes = MagicMock()

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=mock_nodes,
            hco_namespace=MagicMock(),
        )

        mock_assert_healthy.assert_called_once_with(nodes=mock_nodes, healthy_node_condition_type="Ready")

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_assert_nodes_schedulable_called(
        self,
        _mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test assert_nodes_schedulable called"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        mock_nodes = MagicMock()

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=mock_nodes,
            hco_namespace=MagicMock(),
        )

        mock_assert_schedulable.assert_called_once_with(nodes=mock_nodes)

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.IMAGE_CRON_STR", "cron-job")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_wait_for_pods_running_parameters(
        self,
        _mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test wait_for_pods_running called with correct namespace and filter"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()

        cluster_sanity(
            request=mock_request,
            admin_client=mock_admin_client,
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=mock_hco_namespace,
        )

        mock_wait_pods.assert_called_once_with(
            admin_client=mock_admin_client,
            namespace=mock_hco_namespace,
            filter_pods_by_name="cron-job",
        )

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_wait_for_hco_conditions_called(
        self,
        _mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test wait_for_hco_conditions called"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = True

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()

        cluster_sanity(
            request=mock_request,
            admin_client=mock_admin_client,
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=mock_hco_namespace,
        )

        mock_wait_hco.assert_called_once_with(
            admin_client=mock_admin_client,
            hco_namespace=mock_hco_namespace,
        )

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_with_junitxml_property(
        self,
        _mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
        _mock_check_vm,
        _mock_check_webhook,
    ):
        """Test junitxml_property passed to exit_pytest_execution"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.return_value = False
        mock_storage_sanity.return_value = False

        mock_junitxml_property = MagicMock()

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
            junitxml_property=mock_junitxml_property,
        )

        mock_exit_pytest.assert_called_once()
        call_args = mock_exit_pytest.call_args
        assert call_args[1]["junitxml_property"] == mock_junitxml_property

    @patch("utilities.sanity.check_webhook_endpoints_health")
    @patch("utilities.sanity.check_vm_creation_capability")
    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_skip_webhook_check(
        self, mock_logger, _mock_wait_hco, mock_storage_sanity, mock_check_vm, mock_check_webhook
    ):
        """Test skip webhook check when --cluster-sanity-skip-webhook-check flag is set"""
        from utilities.sanity import cluster_sanity

        mock_request = MagicMock()
        mock_request.config.getoption.return_value = ""
        mock_request.session.config.getoption.side_effect = lambda flag: flag == "--cluster-sanity-skip-webhook-check"
        mock_storage_sanity.return_value = True

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=[],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        mock_check_webhook.assert_not_called()
        mock_check_vm.assert_not_called()
        # Should have warning about skipping webhook check
        warning_calls = list(mock_logger.warning.call_args_list)
        assert any("Skipping webhook health check" in str(call) for call in warning_calls), (
            "Expected warning about skipping webhook health check"
        )


class TestDiscoverWebhookServices:
    """Test cases for _discover_webhook_services function"""

    @patch("utilities.sanity.ValidatingWebhookConfiguration")
    @patch("utilities.sanity.MutatingWebhookConfiguration")
    @patch("utilities.sanity.LOGGER")
    def test_discover_webhook_services_finds_services_in_hco_namespace(
        self, _mock_logger, mock_mutating_class, mock_validating_class
    ):
        """Test discovery finds services in the HCO namespace"""
        from utilities.sanity import _discover_webhook_services

        # Set __name__ attributes for the mocks
        mock_mutating_class.__name__ = "MutatingWebhookConfiguration"
        mock_validating_class.__name__ = "ValidatingWebhookConfiguration"

        # Create mock webhook configs with services in HCO namespace
        mock_mutating_config = MagicMock()
        mock_mutating_config.instance.webhooks = [
            {"clientConfig": {"service": {"name": "virt-api", "namespace": "openshift-cnv"}}},
            {"clientConfig": {"service": {"name": "cdi-api", "namespace": "openshift-cnv"}}},
        ]
        mock_mutating_class.get.return_value = [mock_mutating_config]

        mock_validating_config = MagicMock()
        mock_validating_config.instance.webhooks = [
            {"clientConfig": {"service": {"name": "kubevirt-operator-webhook", "namespace": "openshift-cnv"}}},
        ]
        mock_validating_class.get.return_value = [mock_validating_config]

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        result = _discover_webhook_services(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert result == {"virt-api", "cdi-api", "kubevirt-operator-webhook"}, (
            "Expected all three webhook services to be discovered in HCO namespace"
        )

    @patch("utilities.sanity.ValidatingWebhookConfiguration")
    @patch("utilities.sanity.MutatingWebhookConfiguration")
    @patch("utilities.sanity.LOGGER")
    def test_discover_webhook_services_ignores_other_namespaces(
        self, _mock_logger, mock_mutating_class, mock_validating_class
    ):
        """Test discovery ignores services in other namespaces"""
        from utilities.sanity import _discover_webhook_services

        # Set __name__ attributes for the mocks
        mock_mutating_class.__name__ = "MutatingWebhookConfiguration"
        mock_validating_class.__name__ = "ValidatingWebhookConfiguration"

        mock_mutating_config = MagicMock()
        mock_mutating_config.instance.webhooks = [
            {"clientConfig": {"service": {"name": "virt-api", "namespace": "openshift-cnv"}}},
            {"clientConfig": {"service": {"name": "other-service", "namespace": "other-namespace"}}},
        ]
        mock_mutating_class.get.return_value = [mock_mutating_config]
        mock_validating_class.get.return_value = []

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        result = _discover_webhook_services(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert result == {"virt-api"}, "Expected only virt-api service, other namespace services should be ignored"

    @patch("utilities.sanity.ValidatingWebhookConfiguration")
    @patch("utilities.sanity.MutatingWebhookConfiguration")
    @patch("utilities.sanity.LOGGER")
    def test_discover_webhook_services_skips_url_webhooks(
        self, _mock_logger, mock_mutating_class, mock_validating_class
    ):
        """Test discovery skips URL-based webhooks (no service config)"""
        from utilities.sanity import _discover_webhook_services

        # Set __name__ attributes for the mocks
        mock_mutating_class.__name__ = "MutatingWebhookConfiguration"
        mock_validating_class.__name__ = "ValidatingWebhookConfiguration"

        mock_mutating_config = MagicMock()
        mock_mutating_config.instance.webhooks = [
            {"clientConfig": {"service": {"name": "virt-api", "namespace": "openshift-cnv"}}},
            {"clientConfig": {"url": "https://external-webhook.example.com"}},  # URL-based, no service
            {"clientConfig": {}},  # Empty clientConfig
        ]
        mock_mutating_class.get.return_value = [mock_mutating_config]
        mock_validating_class.get.return_value = []

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        result = _discover_webhook_services(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert result == {"virt-api"}, "Expected only virt-api service, URL-based webhooks should be skipped"

    @patch("utilities.sanity.ValidatingWebhookConfiguration")
    @patch("utilities.sanity.MutatingWebhookConfiguration")
    @patch("utilities.sanity.LOGGER")
    def test_discover_webhook_services_empty_webhooks(self, _mock_logger, mock_mutating_class, mock_validating_class):
        """Test discovery handles webhook configs with no webhooks"""
        from utilities.sanity import _discover_webhook_services

        # Set __name__ attributes for the mocks
        mock_mutating_class.__name__ = "MutatingWebhookConfiguration"
        mock_validating_class.__name__ = "ValidatingWebhookConfiguration"

        mock_mutating_config = MagicMock()
        mock_mutating_config.instance.webhooks = None
        mock_mutating_class.get.return_value = [mock_mutating_config]
        mock_validating_class.get.return_value = []

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        result = _discover_webhook_services(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert result == set(), "Expected empty set when webhook config has no webhooks"

    @patch("utilities.sanity.ValidatingWebhookConfiguration")
    @patch("utilities.sanity.MutatingWebhookConfiguration")
    @patch("utilities.sanity.LOGGER")
    def test_discover_webhook_services_deduplicates(self, _mock_logger, mock_mutating_class, mock_validating_class):
        """Test discovery deduplicates services referenced by multiple webhooks"""
        from utilities.sanity import _discover_webhook_services

        # Set __name__ attributes for the mocks
        mock_mutating_class.__name__ = "MutatingWebhookConfiguration"
        mock_validating_class.__name__ = "ValidatingWebhookConfiguration"

        # Same service referenced by both mutating and validating webhooks
        mock_mutating_config = MagicMock()
        mock_mutating_config.instance.webhooks = [
            {"clientConfig": {"service": {"name": "virt-api", "namespace": "openshift-cnv"}}},
        ]
        mock_mutating_class.get.return_value = [mock_mutating_config]

        mock_validating_config = MagicMock()
        mock_validating_config.instance.webhooks = [
            {"clientConfig": {"service": {"name": "virt-api", "namespace": "openshift-cnv"}}},  # Same service
        ]
        mock_validating_class.get.return_value = [mock_validating_config]

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        result = _discover_webhook_services(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert result == {"virt-api"}, "Expected single virt-api service after deduplication"


class TestCheckWebhookEndpointsHealth:
    """Test cases for check_webhook_endpoints_health function"""

    @patch("utilities.sanity._discover_webhook_services")
    @patch("utilities.sanity.Endpoints")
    @patch("utilities.sanity.LOGGER")
    def test_check_webhook_endpoints_health_all_healthy(self, _mock_logger, mock_endpoints_class, mock_discover):
        """Test successful check when all endpoints are healthy"""
        from utilities.sanity import check_webhook_endpoints_health

        mock_discover.return_value = {"virt-api", "cdi-api", "kubevirt-operator-webhook"}

        mock_endpoint = MagicMock()
        mock_endpoint.exists = True
        mock_subset = MagicMock()
        mock_subset.addresses = [MagicMock()]  # At least one address
        mock_endpoint.instance.subsets = [mock_subset]
        mock_endpoints_class.return_value = mock_endpoint

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        # Should not raise
        check_webhook_endpoints_health(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        # Verify endpoints were checked for all discovered services
        assert mock_endpoints_class.call_count == 3, "Expected endpoints to be checked for all 3 discovered services"

    @patch("utilities.sanity._discover_webhook_services")
    @patch("utilities.sanity.Endpoints")
    @patch("utilities.sanity.LOGGER")
    def test_check_webhook_endpoints_health_missing_endpoint(self, _mock_logger, mock_endpoints_class, mock_discover):
        """Test error when endpoint does not exist"""
        from utilities.sanity import check_webhook_endpoints_health

        mock_discover.return_value = {"virt-api"}

        # Simulate ResourceNotFoundError when endpoint doesn't exist (ensure_exists=True)
        mock_endpoints_class.side_effect = ResourceNotFoundError(MagicMock())

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        with pytest.raises(ClusterSanityError) as exc_info:
            check_webhook_endpoints_health(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert "no available endpoints" in str(exc_info.value), (
            "Expected 'no available endpoints' in exception message for missing endpoint"
        )

    @patch("utilities.sanity._discover_webhook_services")
    @patch("utilities.sanity.Endpoints")
    @patch("utilities.sanity.LOGGER")
    def test_check_webhook_endpoints_health_no_subsets(self, _mock_logger, mock_endpoints_class, mock_discover):
        """Test error when endpoint has no subsets"""
        from utilities.sanity import check_webhook_endpoints_health

        mock_discover.return_value = {"virt-api"}

        mock_endpoint = MagicMock()
        mock_endpoint.exists = True
        mock_endpoint.instance.subsets = None
        mock_endpoints_class.return_value = mock_endpoint

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        with pytest.raises(ClusterSanityError) as exc_info:
            check_webhook_endpoints_health(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert "no available endpoints" in str(exc_info.value), (
            "Expected 'no available endpoints' in exception message for no subsets"
        )

    @patch("utilities.sanity._discover_webhook_services")
    @patch("utilities.sanity.Endpoints")
    @patch("utilities.sanity.LOGGER")
    def test_check_webhook_endpoints_health_no_addresses(self, _mock_logger, mock_endpoints_class, mock_discover):
        """Test error when endpoint has no ready addresses"""
        from utilities.sanity import check_webhook_endpoints_health

        mock_discover.return_value = {"virt-api"}

        mock_endpoint = MagicMock()
        mock_endpoint.exists = True
        mock_subset = MagicMock()
        mock_subset.addresses = None
        mock_endpoint.instance.subsets = [mock_subset]
        mock_endpoints_class.return_value = mock_endpoint

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        with pytest.raises(ClusterSanityError) as exc_info:
            check_webhook_endpoints_health(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert "no available endpoints" in str(exc_info.value), (
            "Expected 'no available endpoints' in exception message for no addresses"
        )

    @patch("utilities.sanity._discover_webhook_services")
    @patch("utilities.sanity.Endpoints")
    @patch("utilities.sanity.LOGGER")
    def test_check_webhook_endpoints_health_no_webhooks_discovered(
        self, _mock_logger, mock_endpoints_class, mock_discover
    ):
        """Test that warning is logged when no webhooks are discovered"""
        from utilities.sanity import check_webhook_endpoints_health

        mock_discover.return_value = set()  # No webhooks discovered

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        # Should log warning and return, not raise error
        check_webhook_endpoints_health(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        # Verify warning was logged
        _mock_logger.warning.assert_called()
        mock_endpoints_class.assert_not_called()

    @patch("utilities.sanity._discover_webhook_services")
    @patch("utilities.sanity.Endpoints")
    @patch("utilities.sanity.LOGGER")
    def test_check_webhook_endpoints_health_api_exception(self, _mock_logger, mock_endpoints_class, mock_discover):
        """Test error when API exception occurs while checking endpoints"""
        from kubernetes.client import ApiException

        from utilities.sanity import check_webhook_endpoints_health

        mock_discover.return_value = {"virt-api"}
        mock_endpoints_class.side_effect = ApiException(status=500, reason="Internal Server Error")

        mock_admin_client = MagicMock()
        mock_hco_namespace = MagicMock()
        mock_hco_namespace.name = "openshift-cnv"

        with pytest.raises(ClusterSanityError) as exc_info:
            check_webhook_endpoints_health(admin_client=mock_admin_client, namespace=mock_hco_namespace)

        assert "no available endpoints" in str(exc_info.value), "Expected 'no available endpoints' in exception message"
        _mock_logger.error.assert_called()


class TestCheckVmCreationCapability:
    """Test cases for check_vm_creation_capability function"""

    @patch("utilities.sanity.VirtualMachine")
    @patch("utilities.sanity.LOGGER")
    def test_check_vm_creation_capability_success(self, _mock_logger, mock_vm_class):
        """Test successful dry-run VM creation"""
        from utilities.sanity import check_vm_creation_capability

        mock_vm = MagicMock()
        mock_vm_class.return_value = mock_vm

        mock_admin_client = MagicMock()

        # Should not raise
        check_vm_creation_capability(admin_client=mock_admin_client, namespace="openshift-cnv")

        mock_vm.create.assert_called_once()

    @patch("utilities.sanity.VirtualMachine")
    @patch("utilities.sanity.LOGGER")
    def test_check_vm_creation_capability_api_error(self, _mock_logger, mock_vm_class):
        """Test error when VM creation fails due to API error"""
        from kubernetes.client import ApiException

        from utilities.sanity import check_vm_creation_capability

        mock_vm = MagicMock()
        mock_vm.create.side_effect = ApiException(status=400, reason="Bad Request")
        mock_vm_class.return_value = mock_vm

        mock_admin_client = MagicMock()

        with pytest.raises(ClusterSanityError) as exc_info:
            check_vm_creation_capability(admin_client=mock_admin_client, namespace="openshift-cnv")

        assert "Dry-run VM creation failed" in str(exc_info.value), (
            "Expected 'Dry-run VM creation failed' in exception message for API error"
        )

    @patch("utilities.sanity.VirtualMachine")
    @patch("utilities.sanity.LOGGER")
    def test_check_vm_creation_capability_unexpected_error(self, _mock_logger, mock_vm_class):
        """Test error when VM creation fails due to unexpected error"""
        from utilities.sanity import check_vm_creation_capability

        mock_vm = MagicMock()
        mock_vm.create.side_effect = Exception("Unexpected error")
        mock_vm_class.return_value = mock_vm

        mock_admin_client = MagicMock()

        with pytest.raises(ClusterSanityError) as exc_info:
            check_vm_creation_capability(admin_client=mock_admin_client, namespace="openshift-cnv")

        assert "Unexpected error during dry-run VM creation" in str(exc_info.value), (
            "Expected 'Unexpected error during dry-run VM creation' in exception message"
        )

    @patch("utilities.sanity.VirtualMachine")
    @patch("utilities.sanity.LOGGER")
    def test_check_vm_creation_capability_connection_error(self, _mock_logger, mock_vm_class):
        """Test error when VM creation fails due to connection error"""
        from utilities.sanity import check_vm_creation_capability

        mock_vm = MagicMock()
        mock_vm.create.side_effect = ConnectionError("Connection refused")
        mock_vm_class.return_value = mock_vm

        mock_admin_client = MagicMock()

        with pytest.raises(ClusterSanityError) as exc_info:
            check_vm_creation_capability(admin_client=mock_admin_client, namespace="openshift-cnv")

        assert "Connection error during dry-run VM creation" in str(exc_info.value), (
            "Expected 'Connection error during dry-run VM creation' in exception message"
        )

    @patch("utilities.sanity.VirtualMachine")
    @patch("utilities.sanity.LOGGER")
    def test_check_vm_creation_capability_timeout_error(self, _mock_logger, mock_vm_class):
        """Test error when VM creation fails due to timeout"""
        from utilities.sanity import check_vm_creation_capability

        mock_vm = MagicMock()
        mock_vm.create.side_effect = TimeoutError("Connection timed out")
        mock_vm_class.return_value = mock_vm

        mock_admin_client = MagicMock()

        with pytest.raises(ClusterSanityError) as exc_info:
            check_vm_creation_capability(admin_client=mock_admin_client, namespace="openshift-cnv")

        assert "Connection error during dry-run VM creation" in str(exc_info.value), (
            "Expected 'Connection error during dry-run VM creation' in exception message for timeout"
        )
