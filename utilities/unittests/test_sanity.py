# Generated using Claude cli

"""Unit tests for sanity module"""

from unittest.mock import MagicMock, patch

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
        warning_calls = [call for call in mock_logger.warning.call_args_list]
        assert any("Skipping cluster sanity check" in str(call) for call in warning_calls)

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_skip_storage_check(self, mock_logger, mock_wait_hco, mock_storage_sanity):
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
        warning_calls = [call for call in mock_logger.warning.call_args_list]
        assert any("Skipping storage classes check" in str(call) for call in warning_calls)

    @patch("utilities.sanity.py_config", {"storage_class_matrix": []})
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
        warning_calls = [call for call in mock_logger.warning.call_args_list]
        assert any("Skipping nodes check" in str(call) for call in warning_calls)

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_successful_full_check(
        self,
        mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
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

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_storage_sanity_error(
        self,
        mock_logger,
        mock_wait_hco,
        mock_exit_pytest,
        mock_storage_sanity,
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
        assert "Cluster is missing storage class" in call_args[1]["message"]

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_node_unschedulable_error(
        self,
        mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_assert_healthy,
        mock_storage_sanity,
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
        assert error_message in call_args[1]["message"]

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_node_not_ready_error(
        self,
        mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_assert_healthy,
        mock_storage_sanity,
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
        assert error_message in call_args[1]["message"]

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_cluster_sanity_error(
        self,
        mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_assert_healthy,
        mock_storage_sanity,
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
        assert error_message in call_args[1]["message"]

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_timeout_expired_error_converted(
        self,
        mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
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
        assert "Timed out waiting for all pods" in call_args[1]["message"]
        assert "test-namespace" in call_args[1]["message"]

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_components_called_in_order(
        self,
        mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
    ):
        """Test all components called in correct order (storage, nodes, HCO)"""
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

        def track_hco(*args, **kwargs):
            call_order.append("hco")

        mock_storage_sanity.side_effect = track_storage
        mock_assert_healthy.side_effect = track_healthy
        mock_assert_schedulable.side_effect = track_schedulable
        mock_wait_pods.side_effect = track_pods
        mock_wait_hco.side_effect = track_hco

        cluster_sanity(
            request=mock_request,
            admin_client=MagicMock(),
            cluster_storage_classes_names=["sc1"],
            nodes=MagicMock(),
            hco_namespace=MagicMock(),
        )

        # Verify the order: storage -> healthy -> schedulable -> pods -> hco
        assert call_order == ["storage", "healthy", "schedulable", "pods", "hco"]

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.KUBELET_READY_CONDITION", "Ready")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_assert_nodes_healthy_parameters(
        self,
        mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
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

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_assert_nodes_schedulable_called(
        self,
        mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
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

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.IMAGE_CRON_STR", "cron-job")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_wait_for_pods_running_parameters(
        self,
        mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
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

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_wait_for_hco_conditions_called(
        self,
        mock_logger,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
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

    @patch("utilities.sanity.storage_sanity_check")
    @patch("utilities.sanity.assert_nodes_in_healthy_condition")
    @patch("utilities.sanity.assert_nodes_schedulable")
    @patch("utilities.sanity.wait_for_pods_running")
    @patch("utilities.sanity.wait_for_hco_conditions")
    @patch("utilities.sanity.exit_pytest_execution")
    @patch("utilities.sanity.LOGGER")
    def test_cluster_sanity_with_junitxml_property(
        self,
        mock_logger,
        mock_exit_pytest,
        mock_wait_hco,
        mock_wait_pods,
        mock_assert_schedulable,
        mock_assert_healthy,
        mock_storage_sanity,
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
