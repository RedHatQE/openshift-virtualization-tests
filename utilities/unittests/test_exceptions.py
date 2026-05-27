# Generated using Claude cli

"""Unit tests for exceptions module"""

from unittest.mock import MagicMock, patch

import pytest

from utilities.exceptions import (
    ClusterSanityError,
    DataVolumeConditionMessageNotFoundError,
    MissingEnvironmentVariableError,
    MissingResourceException,
    OsDictNotFoundError,
    ProcessWithException,
    ResourceMismatch,
    ResourceMissingFieldError,
    ResourceValueError,
    ServicePortNotFoundError,
    StorageSanityError,
    UnsupportedCPUArchitectureError,
    UnsupportedGPUDeviceError,
    UrlNotFoundError,
    UtilityPodNotFoundError,
)


class TestUtilityPodNotFoundError:
    """Test cases for UtilityPodNotFoundError exception"""

    def test_utility_pod_not_found_error_init(self):
        """Test UtilityPodNotFoundError initialization"""
        node = "test-node"
        error = UtilityPodNotFoundError(node)
        assert error.node == node

    def test_utility_pod_not_found_error_str(self):
        """Test UtilityPodNotFoundError string representation"""
        node = "test-node"
        error = UtilityPodNotFoundError(node)
        expected = "Utility pod not found for node: test-node"
        assert str(error) == expected


class TestResourceExceptions:
    """Test cases for Resource related exceptions"""

    def test_resource_value_error(self):
        """Test ResourceValueError can be raised"""
        with pytest.raises(ResourceValueError):
            raise ResourceValueError("Test error")

    def test_resource_missing_field_error(self):
        """Test ResourceMissingFieldError can be raised"""
        with pytest.raises(ResourceMissingFieldError):
            raise ResourceMissingFieldError("Test error")

    def test_resource_mismatch(self):
        """Test ResourceMismatch can be raised"""
        with pytest.raises(ResourceMismatch):
            raise ResourceMismatch("Test error")


class TestMissingEnvironmentVariableError:
    """Test cases for MissingEnvironmentVariableError exception"""

    def test_missing_environment_variable_error(self):
        """Test MissingEnvironmentVariableError can be raised"""
        with pytest.raises(MissingEnvironmentVariableError):
            raise MissingEnvironmentVariableError("Test error")


class TestProcessWithException:
    """Test cases for ProcessWithException class"""

    def test_process_with_exception_init(self):
        """Test ProcessWithException initialization"""
        process = ProcessWithException()
        assert hasattr(process, "_pconn")
        assert hasattr(process, "_cconn")
        assert process._exception is None

    @patch("multiprocessing.Pipe")
    def test_process_with_exception_init_with_pipe(self, mock_pipe):
        """Test ProcessWithException initialization with mocked pipe"""
        mock_pconn = MagicMock()
        mock_cconn = MagicMock()
        mock_pipe.return_value = (mock_pconn, mock_cconn)

        process = ProcessWithException()
        assert process._pconn == mock_pconn
        assert process._cconn == mock_cconn

    def test_process_with_exception_exception_property_no_poll(self):
        """Test exception property when no data to poll"""
        process = ProcessWithException()
        process._pconn = MagicMock()
        process._pconn.poll.return_value = False

        assert process.exception is None

    def test_process_with_exception_exception_property_with_poll(self):
        """Test exception property when data available to poll"""
        process = ProcessWithException()
        process._pconn = MagicMock()
        process._pconn.poll.return_value = True
        test_exception = Exception("Test exception")
        process._pconn.recv.return_value = test_exception

        assert process.exception == test_exception

    @patch("utilities.exceptions._FORK_CONTEXT.Process.run")
    def test_process_with_exception_run_success(self, mock_super_run):
        """Test run method when no exception occurs"""
        process = ProcessWithException()
        process._cconn = MagicMock()

        process.run()

        mock_super_run.assert_called_once()
        process._cconn.send.assert_called_once_with(None)

    @patch("utilities.exceptions._FORK_CONTEXT.Process.run")
    def test_process_with_exception_run_with_exception(self, mock_super_run):
        """Test run method when exception occurs"""
        process = ProcessWithException()
        process._cconn = MagicMock()

        test_exception = Exception("Test exception")
        mock_super_run.side_effect = test_exception

        with pytest.raises(Exception, match="Test exception"):
            process.run()

        mock_super_run.assert_called_once()
        process._cconn.send.assert_called_once_with(test_exception)


class TestClusterSanityError:
    """Test cases for ClusterSanityError exception"""

    def test_cluster_sanity_error_init(self):
        """Test ClusterSanityError initialization"""
        err_str = "Cluster sanity check failed"
        error = ClusterSanityError(err_str)
        assert error.err_str == err_str

    def test_cluster_sanity_error_str(self):
        """Test ClusterSanityError string representation"""
        err_str = "Cluster sanity check failed"
        error = ClusterSanityError(err_str)
        assert str(error) == err_str


class TestOsDictNotFoundError:
    """Test cases for OsDictNotFoundError exception"""

    def test_os_dict_not_found_error(self):
        """Test OsDictNotFoundError can be raised"""
        with pytest.raises(OsDictNotFoundError):
            raise OsDictNotFoundError("Test error")


class TestDataVolumeConditionMessageNotFoundError:
    """Test cases for DataVolumeConditionMessageNotFoundError exception"""

    def test_data_volume_condition_message_not_found_error_init(self):
        """Test DataVolumeConditionMessageNotFoundError initialization"""
        dv_name = "test-dv"
        expected_message = "Test message"
        error = DataVolumeConditionMessageNotFoundError(dv_name=dv_name, expected_message=expected_message)
        assert error.dv_name == dv_name
        assert error.expected_message == expected_message
        assert error.last_conditions is None

    def test_data_volume_condition_message_not_found_error_init_with_conditions(self):
        """Test DataVolumeConditionMessageNotFoundError initialization with last conditions"""
        dv_name = "test-dv"
        expected_message = "Test message"
        last_conditions = [{"type": "Ready", "message": "some other message"}]
        error = DataVolumeConditionMessageNotFoundError(
            dv_name=dv_name, expected_message=expected_message, last_conditions=last_conditions
        )
        assert error.last_conditions == last_conditions

    def test_data_volume_condition_message_not_found_error_str(self):
        """Test DataVolumeConditionMessageNotFoundError string representation"""
        dv_name = "test-dv"
        expected_message = "Test message"
        error = DataVolumeConditionMessageNotFoundError(dv_name=dv_name, expected_message=expected_message)
        expected = f"Expected message '{expected_message}' not found in DataVolume '{dv_name}' conditions."
        assert str(error) == expected

    def test_data_volume_condition_message_not_found_error_str_with_conditions(self):
        """Test DataVolumeConditionMessageNotFoundError string includes last conditions when provided"""
        dv_name = "test-dv"
        expected_message = "Test message"
        last_conditions = [{"type": "Ready", "message": "Import complete"}]
        error = DataVolumeConditionMessageNotFoundError(
            dv_name=dv_name, expected_message=expected_message, last_conditions=last_conditions
        )
        error_str = str(error)
        assert expected_message in error_str
        assert dv_name in error_str
        assert "Import complete" in error_str

    def test_data_volume_condition_message_not_found_error_args(self):
        """Test DataVolumeConditionMessageNotFoundError populates args via super().__init__()"""
        dv_name = "test-dv"
        expected_message = "Test message"
        error = DataVolumeConditionMessageNotFoundError(dv_name=dv_name, expected_message=expected_message)
        # Verify args is populated (not empty tuple)
        assert len(error.args) == 1
        assert error.args[0] == str(error)

    def test_data_volume_condition_message_not_found_error_raise_and_catch(self):
        """Test DataVolumeConditionMessageNotFoundError can be raised and caught"""
        dv_name = "test-dv"
        expected_message = "Test message"
        with pytest.raises(DataVolumeConditionMessageNotFoundError) as exc_info:
            raise DataVolumeConditionMessageNotFoundError(dv_name=dv_name, expected_message=expected_message)
        assert exc_info.value.dv_name == dv_name
        assert exc_info.value.expected_message == expected_message
        assert isinstance(exc_info.value, Exception)


class TestStorageSanityError:
    """Test cases for StorageSanityError exception"""

    def test_storage_sanity_error_init(self):
        """Test StorageSanityError initialization"""
        err_str = "Storage sanity check failed"
        error = StorageSanityError(err_str)
        assert error.err_str == err_str

    def test_storage_sanity_error_str(self):
        """Test StorageSanityError string representation"""
        err_str = "Storage sanity check failed"
        error = StorageSanityError(err_str)
        assert str(error) == err_str


class TestServicePortNotFoundError:
    """Test cases for ServicePortNotFoundError exception"""

    def test_service_port_not_found_error_init(self):
        """Test ServicePortNotFoundError initialization"""
        port_number = 8080
        service_name = "test-service"
        error = ServicePortNotFoundError(port_number, service_name)
        assert error.port_number == port_number
        assert error.service_name == service_name

    def test_service_port_not_found_error_str(self):
        """Test ServicePortNotFoundError string representation"""
        port_number = 8080
        service_name = "test-service"
        error = ServicePortNotFoundError(port_number, service_name)
        expected = "Port 8080 was not found in service test-service"
        assert str(error) == expected


class TestUrlNotFoundError:
    """Test cases for UrlNotFoundError exception"""

    def test_url_not_found_error_init(self):
        """Test UrlNotFoundError initialization"""
        url_request = MagicMock()
        url_request.url = "http://example.com"
        url_request.status_code = 404
        error = UrlNotFoundError(url_request)
        assert error.url_request == url_request

    def test_url_not_found_error_str(self):
        """Test UrlNotFoundError string representation"""
        url_request = MagicMock()
        url_request.url = "http://example.com"
        url_request.status_code = 404
        error = UrlNotFoundError(url_request)
        expected = "http://example.com not found. status code is: 404"
        assert str(error) == expected


class TestMissingResourceException:
    """Test cases for MissingResourceException exception"""

    def test_missing_resource_exception_init(self):
        """Test MissingResourceException initialization"""
        resource = "Pod"
        error = MissingResourceException(resource)
        assert error.resource == resource

    def test_missing_resource_exception_str(self):
        """Test MissingResourceException string representation"""
        resource = "Pod"
        error = MissingResourceException(resource)
        expected = "No resources of type Pod were found. Please check the test environment setup."
        assert str(error) == expected


class TestUnsupportedGPUDeviceError:
    """Test cases for UnsupportedGPUDeviceError exception"""

    def test_unsupported_gpu_device_error(self):
        """Test UnsupportedGPUDeviceError can be raised"""
        with pytest.raises(UnsupportedGPUDeviceError):
            raise UnsupportedGPUDeviceError("Test error")


class TestUnsupportedCPUArchitectureError:
    """Test cases for UnsupportedCPUArchitectureError exception"""

    def test_unsupported_cpu_architecture_error(self):
        """Test UnsupportedCPUArchitectureError can be raised"""
        with pytest.raises(UnsupportedCPUArchitectureError):
            raise UnsupportedCPUArchitectureError("Test error")
