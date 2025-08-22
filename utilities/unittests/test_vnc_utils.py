# Generated using Claude cli

"""Unit tests for vnc_utils module"""

from unittest.mock import MagicMock, mock_open, patch

from utilities.vnc_utils import VNCConnection


class TestVNCConnection:
    """Test cases for VNCConnection class"""

    def test_vnc_connection_init(self, mock_vm):
        """Test VNCConnection initialization"""
        vnc_conn = VNCConnection(mock_vm)

        assert vnc_conn.vm == mock_vm
        assert vnc_conn.child is None
        assert vnc_conn.base_dir == "/tmp/data"

    @patch("utilities.vnc_utils.TimeoutSampler")
    @patch("builtins.open", new_callable=mock_open)
    @patch("utilities.vnc_utils.pexpect")
    def test_vnc_connection_enter_success(self, mock_pexpect, mock_file_open, mock_sampler, mock_vm):
        """Test VNCConnection __enter__ method success"""

        # Mock pexpect.spawn
        mock_child = MagicMock()
        mock_pexpect.spawn.return_value = mock_child

        # Mock TimeoutSampler iterator
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__.return_value = iter([mock_child])
        mock_sampler.return_value = mock_sampler_instance

        vnc_conn = VNCConnection(mock_vm)

        result = vnc_conn.__enter__()

        assert result == mock_child
        assert vnc_conn.child == mock_child
        mock_child.expect.assert_called_once_with('"port":', timeout=300)
        mock_file_open.assert_called_once_with("/tmp/data/test-vm.pexpect.log", "a")

    @patch("utilities.vnc_utils.TimeoutSampler")
    def test_vnc_connection_enter_no_sample(self, mock_sampler, mock_vm):
        """Test VNCConnection __enter__ method when no sample is returned"""

        # Mock TimeoutSampler iterator with no valid samples
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__.return_value = iter([None, None])
        mock_sampler.return_value = mock_sampler_instance

        vnc_conn = VNCConnection(mock_vm)

        result = vnc_conn.__enter__()

        assert result is None

    def test_vnc_connection_exit(self, mock_vm):
        """Test VNCConnection __exit__ method"""

        vnc_conn = VNCConnection(mock_vm)

        # Mock child object
        mock_child = MagicMock()
        vnc_conn.child = mock_child

        vnc_conn.__exit__(None, None, None)

        mock_child.close.assert_called_once()

    @patch("utilities.vnc_utils.TimeoutSampler")
    @patch("builtins.open", new_callable=mock_open)
    @patch("utilities.vnc_utils.pexpect")
    def test_vnc_connection_context_manager(self, mock_pexpect, mock_file_open, mock_sampler, mock_vm):
        """Test VNCConnection as context manager"""

        # Mock pexpect.spawn
        mock_child = MagicMock()
        mock_pexpect.spawn.return_value = mock_child

        # Mock TimeoutSampler iterator
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__.return_value = iter([mock_child])
        mock_sampler.return_value = mock_sampler_instance

        with VNCConnection(mock_vm) as vnc_child:
            assert vnc_child == mock_child

        mock_child.close.assert_called_once()

    def test_vnc_connection_virtctl_command_format(self, mock_vm):
        """Test that VNCConnection formats the virtctl command correctly"""

        with patch("utilities.vnc_utils.TimeoutSampler") as mock_sampler:
            mock_sampler_instance = MagicMock()
            mock_sampler_instance.__iter__.return_value = iter([None])
            mock_sampler.return_value = mock_sampler_instance

            vnc_conn = VNCConnection(mock_vm)
            vnc_conn.__enter__()

            # Check that TimeoutSampler was called with correct command
            call_args = mock_sampler.call_args
            expected_command = "virtctl vnc test-vm --proxy-only  -n test-namespace"
            assert call_args[1]["command"] == expected_command
