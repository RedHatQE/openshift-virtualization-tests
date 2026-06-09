# Generated using Claude cli

"""Unit tests for console module"""

import os
import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pexpect
import pytest
from console import Console


class SingleAttemptTimeoutSampler:
    """Run a TimeoutSampler-wrapped function once without retries.

    Patch ``timeout_sampler.TimeoutSampler`` (not ``console.TimeoutSampler``):
    ``connect()`` uses ``@retry`` from timeout_sampler, which resolves
    TimeoutSampler from that module at runtime. ``console_eof_sampler`` uses
    the separate ``console.TimeoutSampler`` import binding.
    """

    def __init__(self, func, func_args=(), **kwargs):
        self.func = func
        self.func_args = func_args

    def __iter__(self):
        yield self.func(*self.func_args)


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
        assert console.prompt == [r"#", r"\$"]

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
            mock_sampler.side_effect = lambda *args, **kwargs: setattr(console, "child", mock_child)
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

    def test_console_generate_cmd_with_kubeconfig(self, mock_vm):
        """Test _generate_cmd method with kubeconfig parameter"""
        mock_vm.username = "user"
        mock_vm.password = "pass"

        with patch("console.VIRTCTL", "virtctl"):
            console = Console(vm=mock_vm, kubeconfig="/path/to/kubeconfig")

        # Should include --kubeconfig flag
        assert console.cmd == "virtctl console test-vm -n test-namespace --kubeconfig /path/to/kubeconfig"

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
        console.child.expect.assert_any_call("login:")
        console.child.sendline.assert_any_call("testuser")
        console.child.expect.assert_any_call("Password:")
        console.child.sendline.assert_any_call("testpass")
        console.child.expect.assert_any_call([r"#", r"\$"])

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
        console.child.expect.assert_any_call("login:")
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
        console.child.expect.assert_any_call([r"#", r"\$"])
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
        console.child.expect.assert_any_call([r"#", r"\$"])
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
        console.child.expect.assert_any_call([r"#", r"\$"])
        # Should not send exit command
        exit_calls = [call for call in console.child.send.call_args_list if "exit" in str(call)]
        assert len(exit_calls) == 0

    @patch("console.get_data_collector_base_directory")
    def test_console_disconnect_terminated_child(self, mock_get_dir):
        """Test disconnect method when the console subprocess has exited"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        console.child = MagicMock()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        console._proc = mock_proc

        with patch.object(console, "console_eof_sampler") as mock_eof_sampler:
            console.disconnect()

        mock_eof_sampler.assert_called_once_with()

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

        console.console_eof_sampler()

        # Should create TimeoutSampler with _spawn_console as the retry function
        mock_timeout_sampler.assert_called_once()
        call_args = mock_timeout_sampler.call_args
        assert call_args[1]["func"] == console._spawn_console

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

        console.console_eof_sampler()

        # Should not change child when no valid sample is found
        assert console.child == original_child

    @patch("console.os.close")
    @patch("console.pexpect.fdpexpect.fdspawn")
    @patch("console.subprocess.Popen")
    @patch("console.pty.openpty")
    @patch("console.get_data_collector_base_directory")
    def test_spawn_console_success(
        self,
        mock_get_dir,
        mock_openpty,
        mock_popen,
        mock_fdspawn,
        mock_os_close,
    ):
        """Test _spawn_console creates fdspawn and stores subprocess handle"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None

        mock_openpty.return_value = (10, 11)
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        mock_child = MagicMock()
        mock_fdspawn.return_value = mock_child

        console = Console(vm=mock_vm)
        result = console._spawn_console()

        assert result == mock_child
        assert console._proc == mock_proc
        mock_popen.assert_called_once()
        mock_fdspawn.assert_called_once_with(fd=10, encoding="utf-8", timeout=30)
        mock_os_close.assert_called_once_with(11)

    @patch("console.os.close")
    @patch("console.subprocess.Popen")
    @patch("console.pty.openpty")
    @patch("console.get_data_collector_base_directory")
    def test_spawn_console_popen_failure(self, mock_get_dir, mock_openpty, mock_popen, mock_os_close):
        """Test _spawn_console closes pty fds when subprocess spawn fails"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None

        mock_openpty.return_value = (10, 11)
        mock_popen.side_effect = OSError("spawn failed")

        console = Console(vm=mock_vm)
        with pytest.raises(OSError, match="spawn failed"):
            console._spawn_console()

        mock_os_close.assert_any_call(10)
        mock_os_close.assert_any_call(11)
        assert console._proc is None

    @patch("console.os.close")
    @patch("console.pexpect.fdpexpect.fdspawn")
    @patch("console.subprocess.Popen")
    @patch("console.pty.openpty")
    @patch("console.get_data_collector_base_directory")
    def test_spawn_console_fdspawn_failure(
        self,
        mock_get_dir,
        mock_openpty,
        mock_popen,
        mock_fdspawn,
        mock_os_close,
    ):
        """Test _spawn_console terminates subprocess when fdspawn fails"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None

        mock_openpty.return_value = (10, 11)
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        mock_fdspawn.side_effect = pexpect.exceptions.ExceptionPexpect("fdspawn failed")

        console = Console(vm=mock_vm)
        with pytest.raises(pexpect.exceptions.ExceptionPexpect, match="fdspawn failed"):
            console._spawn_console()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()
        mock_os_close.assert_any_call(10)
        mock_os_close.assert_any_call(11)
        assert console._proc is None

    @patch("console.os.close")
    @patch("console.pexpect.fdpexpect.fdspawn")
    @patch("console.subprocess.Popen")
    @patch("console.pty.openpty")
    @patch("console.get_data_collector_base_directory")
    def test_spawn_console_fdspawn_failure_force_kill(
        self,
        mock_get_dir,
        mock_openpty,
        mock_popen,
        mock_fdspawn,
        mock_os_close,
    ):
        """Test _spawn_console force-kills subprocess when terminate times out"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None

        mock_openpty.return_value = (10, 11)
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="virtctl", timeout=10), None]
        mock_fdspawn.side_effect = pexpect.exceptions.ExceptionPexpect("fdspawn failed")

        console = Console(vm=mock_vm)
        with pytest.raises(pexpect.exceptions.ExceptionPexpect, match="fdspawn failed"):
            console._spawn_console()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2

    @patch("console.get_data_collector_base_directory")
    def test_terminate_proc_running_process(self, mock_get_dir):
        """Test _terminate_proc gracefully terminates a running subprocess"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        console = Console(vm=mock_vm)
        console._proc = mock_proc
        console._terminate_proc()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=10)
        assert console._proc is None

    @patch("console.get_data_collector_base_directory")
    def test_terminate_proc_force_kill(self, mock_get_dir):
        """Test _terminate_proc force-kills subprocess when terminate times out"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="virtctl", timeout=10), None]

        console = Console(vm=mock_vm)
        console._proc = mock_proc
        console._terminate_proc()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2
        assert console._proc is None

    @patch("console.get_data_collector_base_directory")
    def test_terminate_proc_already_exited(self, mock_get_dir):
        """Test _terminate_proc waits without terminate when process already exited"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0

        console = Console(vm=mock_vm)
        console._proc = mock_proc
        console._terminate_proc()

        mock_proc.terminate.assert_not_called()
        mock_proc.wait.assert_called_once_with(timeout=10)
        assert console._proc is None

    @patch("console.get_data_collector_base_directory")
    def test_console_connect_failure_cleanup(self, mock_get_dir):
        """Test connect cleans up child and subprocess on failure"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "user"
        mock_vm.password = "pass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)
        mock_child = MagicMock()

        with (
            patch("timeout_sampler.TimeoutSampler", SingleAttemptTimeoutSampler),
            patch.object(console, "console_eof_sampler") as mock_sampler,
            patch.object(console, "_connect", side_effect=RuntimeError("connect failed")),
            patch.object(console, "_terminate_proc") as mock_terminate,
        ):
            mock_sampler.side_effect = lambda: setattr(console, "child", mock_child)
            with pytest.raises(RuntimeError, match="connect failed"):
                console.connect()

        mock_child.close.assert_called_once()
        mock_terminate.assert_called_once()

    @patch("console.get_data_collector_base_directory")
    def test_console_connect_failure_no_child(self, mock_get_dir):
        """Test connect terminates subprocess when child was never set"""
        mock_get_dir.return_value = "/tmp/data"
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = None
        mock_vm.username = "user"
        mock_vm.password = "pass"
        mock_vm.login_params = {}

        console = Console(vm=mock_vm)

        with (
            patch("timeout_sampler.TimeoutSampler", SingleAttemptTimeoutSampler),
            patch.object(console, "console_eof_sampler"),
            patch.object(console, "_connect", side_effect=RuntimeError("connect failed")),
            patch.object(console, "_terminate_proc") as mock_terminate,
        ):
            with pytest.raises(RuntimeError, match="connect failed"):
                console.connect()

        mock_terminate.assert_called_once()
