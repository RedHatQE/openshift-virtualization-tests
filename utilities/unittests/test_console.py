"""Unit tests for console module"""

import os
from unittest.mock import MagicMock, mock_open, patch

from console import Console


class TestConsole:
    """Test cases for Console class"""

    def test_console_init_with_defaults(self, mock_vm_no_namespace):
        """Test Console initialization with default values"""
        mock_vm_no_namespace.username = "default-user"
        mock_vm_no_namespace.password = "default-pass"

        console = Console(vm=mock_vm_no_namespace)

        assert console.vm == mock_vm_no_namespace
        assert console.username == "default-user"
        assert console.password == "default-pass"
        assert console.timeout == 30
        assert console.child is None
        assert console.login_prompt == "login:"
        assert console.prompt == [r"\$"]

    def test_console_init_with_custom_values(self, mock_vm_no_namespace):
        """Test Console initialization with custom values"""
        console = Console(
            vm=mock_vm_no_namespace,
            username="custom-user",
            password="custom-pass",
            timeout=60,
            prompt=["#", ">"],
        )

        assert console.username == "custom-user"
        assert console.password == "custom-pass"
        assert console.timeout == 60
        assert console.prompt == ["#", ">"]

    def test_console_init_with_login_params(self, mock_vm_with_login_params):
        """Test Console initialization with VM login_params"""
        console = Console(vm=mock_vm_with_login_params)

        # Should prefer login_params over default vm attributes
        assert console.username == "login-user"
        assert console.password == "login-pass"

    @patch("console.pexpect")
    @patch("console.get_data_collector_base_directory")
    def test_console_connect(self, mock_get_dir, mock_pexpect):
        """Test console connect method"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "user"
        mock_vm.password = "pass"
        mock_vm.login_params = {}

        mock_child = MagicMock()
        mock_pexpect.spawn.return_value = mock_child

        console = Console(vm=mock_vm)

        with (
            patch.object(console, "console_eof_sampler") as mock_sampler,
            patch.object(
                console,
                "_connect",
            ) as mock_connect,
        ):
            result = console.connect()

            assert result == console.child
            mock_sampler.assert_called_once()
            mock_connect.assert_called_once()

    def test_console_generate_cmd(self, mock_vm):
        """Test _generate_cmd method"""
        mock_vm.username = "user"
        mock_vm.password = "pass"

        with patch.dict(os.environ, {"VIRTCTL": "custom-virtctl"}):
            console = Console(vm=mock_vm)

        # Should use the virtctl from environment
        assert console.cmd == "custom-virtctl console test-vm -n test-namespace"

        # Test without namespace
        mock_vm.namespace = None
        with patch("console.VIRTCTL", "virtctl"):
            console = Console(vm=mock_vm)

        assert console.cmd == "virtctl console test-vm"

    @patch("console.pexpect.spawn")
    def test_console_enter(self, mock_spawn, mock_vm_no_namespace):
        """Test __enter__ method"""
        mock_vm_no_namespace.username = "user"
        mock_vm_no_namespace.password = "pass"

        mock_child = MagicMock()
        mock_spawn.return_value = mock_child

        console = Console(vm=mock_vm_no_namespace)

        with patch.object(console, "console_eof_sampler") as mock_sampler:
            # Mock that console_eof_sampler sets self.child
            def set_child(*args, **kwargs):
                console.child = mock_child

            mock_sampler.side_effect = set_child

            with patch.object(console, "_connect"):
                result = console.__enter__()

        # __enter__ returns the result of connect(), which returns self.child
        assert result == mock_child

    @patch("builtins.open", new_callable=mock_open)
    @patch("console.get_data_collector_base_directory")
    def test_console_exit(self, mock_get_dir, mock_file_open):
        """Test __exit__ method"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "user"
        mock_vm.password = "pass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        mock_child = MagicMock()
        mock_child.terminated = False
        console.child = mock_child

        with patch.object(console, "disconnect") as mock_disconnect:
            console.__exit__(None, None, None)
            mock_disconnect.assert_called_once()

    @patch("console.get_data_collector_base_directory")
    def test_console_sendline_through_child(self, mock_get_dir):
        """Test sendline through child object"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "user"
        mock_vm.password = "pass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        mock_child = MagicMock()
        console.child = mock_child

        # The user would call sendline on the child object returned by __enter__
        console.child.sendline("test command")

        mock_child.sendline.assert_called_once_with("test command")

    @patch("console.get_data_collector_base_directory")
    def test_console_expect_through_child(self, mock_get_dir):
        """Test expect through child object"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "user"
        mock_vm.password = "pass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        mock_child = MagicMock()
        mock_child.expect.return_value = 0
        console.child = mock_child

        # The user would call expect on the child object returned by __enter__
        result = console.child.expect(["pattern1", "pattern2"], timeout=60)

        assert result == 0
        mock_child.expect.assert_called_once_with(["pattern1", "pattern2"], timeout=60)

    @patch("console.get_data_collector_base_directory")
    def test_console_connect_with_username_and_password(self, mock_get_dir):
        """Test _connect method with username and password"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        console.child = MagicMock()

        console._connect()

        # Verify connection sequence
        console.child.send.assert_any_call("\n\n")
        console.child.expect.assert_any_call("login:", timeout=300)
        console.child.sendline.assert_any_call("testuser")
        console.child.expect.assert_any_call("Password:")
        console.child.sendline.assert_any_call("testpass")
        console.child.expect.assert_any_call([r"\$"], timeout=150)

    @patch("console.get_data_collector_base_directory")
    def test_console_connect_username_only(self, mock_get_dir):
        """Test _connect method with username only"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "testuser"
        mock_vm.password = None
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        console.child = MagicMock()

        console._connect()

        # Verify connection sequence without password
        console.child.send.assert_any_call("\n\n")
        console.child.expect.assert_any_call("login:", timeout=300)
        console.child.sendline.assert_any_call("testuser")
        # Should not expect or send password
        password_calls = [call for call in console.child.expect.call_args_list if "Password:" in str(call)]
        assert len(password_calls) == 0

    @patch("console.get_data_collector_base_directory")
    def test_console_connect_no_username(self, mock_get_dir):
        """Test _connect method without username"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = None
        mock_vm.password = None
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        console.child = MagicMock()

        console._connect()

        # Should only send newlines and expect prompt
        console.child.send.assert_any_call("\n\n")
        console.child.expect.assert_any_call([r"\$"], timeout=150)
        # Should not expect login prompt
        login_calls = [call for call in console.child.expect.call_args_list if "login:" in str(call)]
        assert len(login_calls) == 0

    @patch("console.get_data_collector_base_directory")
    def test_console_disconnect_with_username(self, mock_get_dir):
        """Test disconnect method with username"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        console.child = MagicMock()
        console.child.terminated = False

        console.disconnect()

        console.child.send.assert_any_call("\n\n")
        console.child.expect.assert_any_call([r"\$"])
        console.child.send.assert_any_call("exit")
        console.child.send.assert_any_call("\n\n")
        console.child.expect.assert_any_call("login:")

    @patch("console.get_data_collector_base_directory")
    def test_console_disconnect_no_username(self, mock_get_dir):
        """Test disconnect method without username"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = None
        mock_vm.password = None
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        console.child = MagicMock()
        console.child.terminated = False

        console.disconnect()

        console.child.send.assert_any_call("\n\n")
        console.child.expect.assert_any_call([r"\$"])
        # Should not send exit command
        exit_calls = [call for call in console.child.send.call_args_list if "exit" in str(call)]
        assert len(exit_calls) == 0

    @patch("console.pexpect")
    @patch("console.get_data_collector_base_directory")
    def test_console_disconnect_terminated_child(self, mock_get_dir, mock_pexpect):
        """Test disconnect method when child is terminated"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        console.child = MagicMock()
        console.child.terminated = True

        # Mock the console_eof_sampler
        console.console_eof_sampler = MagicMock()

        console.disconnect()

        # Should call console_eof_sampler when child is terminated
        console.console_eof_sampler.assert_called_once_with(
            func=mock_pexpect.spawn,
            command=console.cmd,
            timeout=console.timeout,
        )

    @patch("console.TimeoutSampler")
    @patch("builtins.open", new_callable=mock_open)
    @patch("console.get_data_collector_base_directory")
    def test_console_eof_sampler_success(self, mock_get_dir, mock_file_open, mock_timeout_sampler):
        """Test console_eof_sampler method when sample is found"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)

        # Mock successful sampling
        mock_sample = MagicMock()
        mock_sample.logfile = None
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__.return_value = [mock_sample]
        mock_timeout_sampler.return_value = mock_sampler_instance

        mock_func = MagicMock()
        command = "test-command"
        timeout = 30

        console.console_eof_sampler(func=mock_func, command=command, timeout=timeout)

        # Should create TimeoutSampler with correct parameters
        mock_timeout_sampler.assert_called_once()
        call_args = mock_timeout_sampler.call_args
        assert call_args[1]["func"] == mock_func
        assert call_args[1]["command"] == command
        assert call_args[1]["timeout"] == timeout

        # Should set child and logfile
        assert console.child == mock_sample
        mock_file_open.assert_called_once_with("/tmp/data/test-vm.pexpect.log", "a")

    @patch("console.TimeoutSampler")
    @patch("console.get_data_collector_base_directory")
    def test_console_eof_sampler_no_sample(self, mock_get_dir, mock_timeout_sampler):
        """Test console_eof_sampler method when no sample is found"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        original_child = console.child

        # Mock no successful sampling (empty iterator or None values)
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__.return_value = [None]
        mock_timeout_sampler.return_value = mock_sampler_instance

        mock_func = MagicMock()
        command = "test-command"
        timeout = 30

        console.console_eof_sampler(func=mock_func, command=command, timeout=timeout)

        # Should not change child when no valid sample is found
        assert console.child == original_child
