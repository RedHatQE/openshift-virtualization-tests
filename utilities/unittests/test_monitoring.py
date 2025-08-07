# Generated using Claude cli

"""Unit tests for monitoring module"""

from unittest.mock import MagicMock, patch

import pytest
from timeout_sampler import TimeoutExpiredError

# Monitoring module can be imported safely with centralized mocking in conftest.py
from utilities.monitoring import (
    get_all_firing_alerts,
    get_metrics_value,
    validate_alert_cnv_labels,
    validate_alerts,
    wait_for_alert,
    wait_for_firing_alert_clean_up,
    wait_for_gauge_metrics_value,
    wait_for_operator_health_metrics_value,
)


class TestWaitForAlert:
    """Test cases for wait_for_alert function"""

    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_alert_success(self, mock_sampler):
        """Test successful alert waiting"""
        mock_prometheus = MagicMock()
        mock_alerts = [{"alert": "test-alert", "state": "firing"}]

        mock_sampler.return_value = [mock_alerts]

        result = wait_for_alert(mock_prometheus, "test-alert")

        assert result == mock_alerts
        mock_sampler.assert_called_once()
        call_args = mock_sampler.call_args[1]
        assert call_args["func"] == mock_prometheus.get_all_alerts_by_alert_name
        assert call_args["alert_name"] == "test-alert"

    @patch("utilities.monitoring.collect_alerts_data")
    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_alert_timeout(self, mock_sampler, mock_collect_alerts):
        """Test alert waiting timeout"""
        mock_prometheus = MagicMock()

        # Create a generator that yields some samples then raises timeout
        def timeout_generator():
            yield None
            yield None
            raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = timeout_generator()

        with pytest.raises(TimeoutExpiredError):
            wait_for_alert(mock_prometheus, "test-alert")

        # Should call collect_alerts_data on timeout
        mock_collect_alerts.assert_called_once()

    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_alert_no_sample(self, mock_sampler):
        """Test alert waiting with no samples found"""
        mock_prometheus = MagicMock()

        mock_sampler.return_value = [None, None]

        # Should timeout if no valid samples are found
        mock_sampler.side_effect = TimeoutExpiredError("Timeout")

        with pytest.raises(TimeoutExpiredError):
            wait_for_alert(mock_prometheus, "test-alert")


class TestValidateAlertCnvLabels:
    """Test cases for validate_alert_cnv_labels function"""

    @patch("utilities.monitoring.collect_alerts_data")
    def test_validate_alert_cnv_labels_success(self, mock_collect_alerts):
        """Test successful CNV label validation"""
        mock_alerts = [
            {
                "labels": {
                    "alertname": "test-alert",
                    "operator_health_impact": "critical",
                    "kubernetes_operator_part_of": "kubevirt",
                    "kubernetes_operator_component": "kubevirt-hyperconverged-operator",
                }
            }
        ]

        labels = {
            "alertname": "test-alert",
            "operator_health_impact": "critical",
            "kubernetes_operator_part_of": "kubevirt",
            "kubernetes_operator_component": "kubevirt-hyperconverged-operator",
        }

        validate_alert_cnv_labels(alerts=mock_alerts, labels=labels)

        # Should not call collect_alerts_data on success
        mock_collect_alerts.assert_not_called()

    @patch("utilities.monitoring.collect_alerts_data")
    def test_validate_alert_cnv_labels_mismatch(self, mock_collect_alerts):
        """Test CNV label validation with mismatched values"""
        mock_alerts = [
            {
                "labels": {
                    "alertname": "test-alert",
                    "operator_health_impact": "warning",  # Different from expected
                    "kubernetes_operator_part_of": "kubevirt",
                    "kubernetes_operator_component": "kubevirt-hyperconverged-operator",
                }
            }
        ]

        labels = {
            "alertname": "test-alert",
            "operator_health_impact": "critical",  # Expected critical
            "kubernetes_operator_part_of": "kubevirt",
            "kubernetes_operator_component": "kubevirt-hyperconverged-operator",
        }

        with pytest.raises(AssertionError):
            validate_alert_cnv_labels(alerts=mock_alerts, labels=labels)


class TestWaitForFiringAlertCleanUp:
    """Test cases for wait_for_firing_alert_clean_up function"""

    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_firing_alert_clean_up_success(self, mock_sampler):
        """Test successful alert cleanup waiting"""
        mock_prometheus = MagicMock()

        # Mock progression: alerts exist, then empty
        mock_sampler.return_value = [
            [{"alert": "test-alert"}],  # Alerts still firing
            [],  # No more alerts
        ]

        wait_for_firing_alert_clean_up(mock_prometheus, "test-alert")

        mock_sampler.assert_called_once()

    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_firing_alert_clean_up_timeout(self, mock_sampler):
        """Test alert cleanup timeout"""
        mock_prometheus = MagicMock()

        mock_sampler.side_effect = TimeoutExpiredError("Timeout")

        with pytest.raises(TimeoutExpiredError):
            wait_for_firing_alert_clean_up(mock_prometheus, "test-alert")


class TestValidateAlerts:
    """Test cases for validate_alerts function"""

    @patch("utilities.monitoring.wait_for_operator_health_metrics_value")
    @patch("utilities.monitoring.validate_alert_cnv_labels")
    def test_validate_alerts_success(self, mock_validate_labels, mock_wait_health):
        """Test successful alert validation"""
        mock_prometheus = MagicMock()
        mock_prometheus.wait_for_alert_by_state_sampler.return_value = [{"labels": {"alertname": "test-alert"}}]

        alert_dict = {"alert_name": "test-alert", "labels": {"operator_health_impact": "critical"}}

        validate_alerts(prometheus=mock_prometheus, alert_dict=alert_dict)

        mock_prometheus.wait_for_alert_by_state_sampler.assert_called_once()
        mock_validate_labels.assert_called_once()
        mock_wait_health.assert_called_once()

    @patch("utilities.monitoring.wait_for_operator_health_metrics_value")
    @patch("utilities.monitoring.collect_alerts_data")
    @patch("utilities.monitoring.validate_alert_cnv_labels")
    def test_validate_alerts_timeout_with_recovery(self, mock_validate_labels, mock_collect_alerts, mock_wait_health):
        """Test alert validation with timeout but alert found in different state"""
        mock_prometheus = MagicMock()
        mock_prometheus.wait_for_alert_by_state_sampler.side_effect = TimeoutExpiredError("Timeout")
        mock_prometheus.get_all_alerts_by_alert_name.return_value = [{"labels": {"alertname": "test-alert"}}]

        alert_dict = {"alert_name": "test-alert", "labels": {"operator_health_impact": "critical"}}

        validate_alerts(prometheus=mock_prometheus, alert_dict=alert_dict)

        mock_prometheus.get_all_alerts_by_alert_name.assert_called_once()
        mock_validate_labels.assert_called_once()
        # Should call wait_for_operator_health_metrics_value because state defaults to FIRING_STATE
        mock_wait_health.assert_called_once()

    @patch("utilities.monitoring.collect_alerts_data")
    def test_validate_alerts_timeout_no_recovery(self, mock_collect_alerts):
        """Test alert validation with timeout and no alert found"""
        mock_prometheus = MagicMock()
        mock_prometheus.wait_for_alert_by_state_sampler.side_effect = TimeoutExpiredError("Timeout")
        mock_prometheus.get_all_alerts_by_alert_name.return_value = []

        alert_dict = {"alert_name": "test-alert", "labels": {"operator_health_impact": "critical"}}

        with pytest.raises(TimeoutExpiredError):
            validate_alerts(prometheus=mock_prometheus, alert_dict=alert_dict)

        mock_collect_alerts.assert_called_once()

    @patch("utilities.monitoring.collect_alerts_data")
    @patch("utilities.monitoring.validate_alert_cnv_labels")
    def test_validate_alerts_cnv_timeout(self, mock_validate_labels, mock_collect_alerts):
        """Test alert validation with timeout in CNV labels validation"""
        mock_prometheus = MagicMock()
        mock_prometheus.wait_for_alert_by_state_sampler.return_value = [{"labels": {"alertname": "test-alert"}}]
        mock_validate_labels.side_effect = TimeoutExpiredError("Timeout")

        alert_dict = {"alert_name": "test-alert", "labels": {"operator_health_impact": "critical"}}

        with pytest.raises(TimeoutExpiredError):
            validate_alerts(prometheus=mock_prometheus, alert_dict=alert_dict)

        mock_collect_alerts.assert_called_once()


class TestWaitForOperatorHealthMetricsValue:
    """Test cases for wait_for_operator_health_metrics_value function"""

    @patch("utilities.monitoring.get_all_firing_alerts")
    @patch("utilities.monitoring.get_metrics_value")
    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_operator_health_metrics_value_success(self, mock_sampler, mock_get_metrics, mock_get_alerts):
        """Test successful operator health metrics waiting"""
        mock_prometheus = MagicMock()
        mock_get_metrics.side_effect = ["2", "2"]  # operator health and system health (critical = 2)

        # Mock the sampler to return the expected value
        mock_sampler.return_value = ["2"]

        result = wait_for_operator_health_metrics_value(prometheus=mock_prometheus, health_impact_value="critical")

        assert result is True
        mock_sampler.assert_called_once()

    @patch("utilities.monitoring.get_all_firing_alerts")
    @patch("utilities.monitoring.get_metrics_value")
    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_operator_health_metrics_value_timeout(self, mock_sampler, mock_get_metrics, mock_get_alerts):
        """Test operator health metrics timeout"""
        mock_prometheus = MagicMock()
        mock_get_alerts.return_value = {}

        mock_sampler.side_effect = TimeoutExpiredError("Timeout")

        with pytest.raises(TimeoutExpiredError):
            wait_for_operator_health_metrics_value(prometheus=mock_prometheus, health_impact_value="critical")

    @patch("utilities.monitoring.get_all_firing_alerts")
    @patch("utilities.monitoring.get_metrics_value")
    def test_wait_for_operator_health_metrics_value_with_higher_alerts(self, mock_get_metrics, mock_get_alerts):
        """Test operator health metrics with higher priority alerts"""
        mock_prometheus = MagicMock()
        mock_get_metrics.side_effect = ["0", "1"]  # Different system metrics
        mock_get_alerts.return_value = {"2": ["high-priority-alert"]}  # Higher health impact alerts (string keys)

        # Mock the actual function to patch the timeout behavior
        with patch("utilities.monitoring.TimeoutSampler") as mock_sampler:
            # Create a mock iterator that raises TimeoutExpiredError
            def timeout_side_effect(*args, **kwargs):
                # Return a generator that yields a few values then raises timeout
                def generator():
                    yield "0"
                    yield "0"
                    raise TimeoutExpiredError("Timeout")

                return generator()

            mock_sampler.return_value = timeout_side_effect()

            result = wait_for_operator_health_metrics_value(
                prometheus=mock_prometheus,
                health_impact_value="warning",  # warning = "1", so higher alerts with value "2" exist
            )

            assert result is True


class TestGetAllFiringAlerts:
    """Test cases for get_all_firing_alerts function"""

    def test_get_all_firing_alerts_success(self):
        """Test getting all firing alerts"""
        mock_prometheus = MagicMock()
        mock_alerts_response = {
            "data": {
                "alerts": [
                    {"state": "firing", "labels": {"alertname": "alert1", "operator_health_impact": "critical"}},
                    {"state": "pending", "labels": {"alertname": "alert2", "operator_health_impact": "warning"}},
                    {"state": "firing", "labels": {"alertname": "alert3", "operator_health_impact": "critical"}},
                ]
            }
        }
        mock_prometheus.alerts.return_value = mock_alerts_response

        result = get_all_firing_alerts(mock_prometheus)

        # Should return firing alerts grouped by health impact value
        # critical = "2", so health_value = "2" for critical alerts (string keys)
        expected = {"2": ["alert1", "alert3"]}  # critical alerts
        assert result == expected
        mock_prometheus.alerts.assert_called_once()

    def test_get_all_firing_alerts_no_firing(self):
        """Test getting firing alerts when none are firing"""
        mock_prometheus = MagicMock()
        mock_alerts_response = {
            "data": {
                "alerts": [
                    {"state": "pending", "labels": {"alertname": "alert1", "operator_health_impact": "warning"}},
                    {"state": "resolved", "labels": {"alertname": "alert2", "operator_health_impact": "critical"}},
                ]
            }
        }
        mock_prometheus.alerts.return_value = mock_alerts_response

        result = get_all_firing_alerts(mock_prometheus)

        assert result == {}


class TestGetMetricsValue:
    """Test cases for get_metrics_value function"""

    def test_get_metrics_value_success(self):
        """Test getting metrics value"""
        mock_prometheus = MagicMock()
        mock_metrics_response = {"data": {"result": [{"value": ["timestamp", "42"]}]}}
        mock_prometheus.query.return_value = mock_metrics_response

        result = get_metrics_value(mock_prometheus, "test_metric")

        assert result == "42"
        mock_prometheus.query.assert_called_once_with(query="test_metric")

    def test_get_metrics_value_no_data(self):
        """Test getting metrics value with no data"""
        mock_prometheus = MagicMock()
        mock_prometheus.query.return_value = {"data": {}}

        result = get_metrics_value(mock_prometheus, "test_metric")

        assert result == 0


class TestWaitForGaugeMetricsValue:
    """Test cases for wait_for_gauge_metrics_value function"""

    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_gauge_metrics_value_success(self, mock_sampler):
        """Test successful gauge metrics value waiting"""
        mock_prometheus = MagicMock()
        mock_sample = {"data": {"result": [{"value": ["timestamp", "1.0"]}]}}

        mock_sampler.return_value = [mock_sample]

        wait_for_gauge_metrics_value(prometheus=mock_prometheus, query="test_query", expected_value="1.0")

        mock_sampler.assert_called_once()

    @patch("utilities.monitoring.TimeoutSampler")
    def test_wait_for_gauge_metrics_value_timeout(self, mock_sampler):
        """Test gauge metrics value timeout"""
        mock_prometheus = MagicMock()

        mock_sampler.side_effect = TimeoutExpiredError("Timeout")

        with pytest.raises(TimeoutExpiredError):
            wait_for_gauge_metrics_value(prometheus=mock_prometheus, query="test_query", expected_value="1.0")
