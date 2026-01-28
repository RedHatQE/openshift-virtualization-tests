# Generated using Claude cli

"""Unit tests for ssh module"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from timeout_sampler import TimeoutExpiredError

from utilities.constants import CNV_VM_SSH_KEY_PATH
from utilities.ssh import (
    CommandResult,
    FileSystem,
    KernelInfo,
    NetworkInfo,
    OSInfo,
    PackageManager,
    SSHClient,
    SSHCommandError,
    SSHConnectionError,
    TimezoneInfo,
    _build_virtctl_ssh_command,
    _get_ssh_key_path,
    _get_vm_credentials,
    _parse_timezone_offset,
    _should_use_ssh_key,
    is_connective,
    run_command,
    run_ssh_commands,
    wait_for_ssh_connectivity,
)

pytestmark = pytest.mark.unit


class TestSSHCommandError:
    """Test cases for SSHCommandError exception"""

    def test_ssh_command_error_init(self):
        """Test SSHCommandError initialization"""
        error = SSHCommandError(
            message="Command failed",
            returncode=1,
            stdout="output",
            stderr="error",
        )
        assert str(error) == "Command failed"
        assert error.returncode == 1
        assert error.stdout == "output"
        assert error.stderr == "error"

    def test_ssh_command_error_default_values(self):
        """Test SSHCommandError with default values"""
        error = SSHCommandError(message="Command failed")
        assert error.returncode is None
        assert error.stdout == ""
        assert error.stderr == ""


class TestSSHConnectionError:
    """Test cases for SSHConnectionError exception"""

    def test_ssh_connection_error(self):
        """Test SSHConnectionError can be raised"""
        with pytest.raises(SSHConnectionError):
            raise SSHConnectionError("Connection failed")


class TestTimezoneInfo:
    """Test cases for TimezoneInfo namedtuple"""

    def test_timezone_info_creation(self):
        """Test TimezoneInfo creation"""
        tz_info = TimezoneInfo(name="EST", offset="-500")
        assert tz_info.name == "EST"
        assert tz_info.offset == "-500"


class TestKernelInfo:
    """Test cases for KernelInfo namedtuple"""

    def test_kernel_info_creation(self):
        """Test KernelInfo creation"""
        kernel_info = KernelInfo(
            release="5.14.0-284.el9.x86_64",
            version="#1 SMP PREEMPT_DYNAMIC",
            type="x86_64",
        )
        assert kernel_info.release == "5.14.0-284.el9.x86_64"
        assert kernel_info.version == "#1 SMP PREEMPT_DYNAMIC"
        assert kernel_info.type == "x86_64"


class TestCommandResult:
    """Test cases for CommandResult dataclass"""

    def test_command_result_creation(self):
        """Test CommandResult creation"""
        result = CommandResult(returncode=0, stdout="output", stderr="")
        assert result.returncode == 0
        assert result.stdout == "output"
        assert result.stderr == ""

    def test_command_result_unpacking(self):
        """Test CommandResult can be unpacked as tuple"""
        result = CommandResult(returncode=0, stdout="output", stderr="error")
        returncode, stdout, stderr = result
        assert returncode == 0
        assert stdout == "output"
        assert stderr == "error"

    def test_command_result_iteration(self):
        """Test CommandResult iteration"""
        result = CommandResult(returncode=1, stdout="out", stderr="err")
        values = list(result)
        assert values == [1, "out", "err"]


class TestGetSshKeyPath:
    """Test cases for _get_ssh_key_path function"""

    @patch.dict("os.environ", {CNV_VM_SSH_KEY_PATH: "/path/to/key"})
    def test_get_ssh_key_path_set(self):
        """Test getting SSH key path when environment variable is set"""
        result = _get_ssh_key_path()
        assert result == "/path/to/key"

    @patch.dict("os.environ", {}, clear=True)
    def test_get_ssh_key_path_not_set(self):
        """Test getting SSH key path when environment variable is not set"""
        result = _get_ssh_key_path()
        assert result is None


class TestShouldUseSshKey:
    """Test cases for _should_use_ssh_key function"""

    def test_should_use_ssh_key_linux_vm(self):
        """Test SSH key should be used for Linux VMs"""
        mock_vm = MagicMock()
        mock_vm.os_flavor = "rhel"
        result = _should_use_ssh_key(vm=mock_vm)
        assert result is True

    def test_should_use_ssh_key_windows_vm(self):
        """Test SSH key should not be used for Windows VMs"""
        mock_vm = MagicMock()
        mock_vm.os_flavor = "windows"
        result = _should_use_ssh_key(vm=mock_vm)
        assert result is False

    def test_should_use_ssh_key_cirros_vm(self):
        """Test SSH key should not be used for Cirros VMs"""
        mock_vm = MagicMock()
        mock_vm.os_flavor = "cirros"
        result = _should_use_ssh_key(vm=mock_vm)
        assert result is False

    def test_should_use_ssh_key_no_os_flavor(self):
        """Test SSH key should be used when os_flavor is not set"""
        mock_vm = MagicMock(spec=[])
        result = _should_use_ssh_key(vm=mock_vm)
        assert result is True


class TestParseTimezoneOffset:
    """Test cases for _parse_timezone_offset function"""

    def test_parse_timezone_offset_positive(self):
        """Test parsing positive timezone offset"""
        result = _parse_timezone_offset(offset_str="+0530")
        assert result == 5 * 3600 + 30 * 60

    def test_parse_timezone_offset_negative(self):
        """Test parsing negative timezone offset"""
        result = _parse_timezone_offset(offset_str="-0800")
        assert result == -(8 * 3600)

    def test_parse_timezone_offset_zero(self):
        """Test parsing UTC timezone offset"""
        result = _parse_timezone_offset(offset_str="+0000")
        assert result == 0

    def test_parse_timezone_offset_invalid_empty(self):
        """Test parsing empty string raises ValueError"""
        with pytest.raises(ValueError, match="Invalid timezone offset format"):
            _parse_timezone_offset(offset_str="")

    def test_parse_timezone_offset_invalid_length(self):
        """Test parsing invalid length offset raises ValueError"""
        with pytest.raises(ValueError, match="Invalid timezone offset format"):
            _parse_timezone_offset(offset_str="+05")


class TestBuildVirtctlSshCommand:
    """Test cases for _build_virtctl_ssh_command function"""

    def test_build_command_without_ssh_key(self):
        """Test building virtctl ssh command without SSH key"""
        result = _build_virtctl_ssh_command(
            vm_name="test-vm",
            namespace="default",
            username="testuser",
            command="ls -la",
        )
        assert "virtctl" in result or result[0].endswith("virtctl")
        assert "ssh" in result
        assert "--local-ssh=false" in result
        assert "-n" in result
        assert "-l" in result
        assert "--command" in result
        assert "--identity-file" not in result
        assert "test-vm" in result
        assert "testuser" in result

    def test_build_command_with_ssh_key(self):
        """Test building virtctl ssh command with SSH key"""
        result = _build_virtctl_ssh_command(
            vm_name="test-vm",
            namespace="default",
            username="testuser",
            command="ls -la",
            ssh_key_path="/path/to/key",
        )
        assert "--identity-file" in result
        assert "/path/to/key" in result


class TestGetVmCredentials:
    """Test cases for _get_vm_credentials function"""

    def test_get_credentials_from_attributes(self):
        """Test getting credentials from VM attributes"""
        mock_vm = MagicMock()
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        username, password = _get_vm_credentials(vm=mock_vm)
        assert username == "testuser"
        assert password == "testpass"

    def test_get_credentials_from_login_params(self):
        """Test getting credentials from login_params"""
        mock_vm = MagicMock()
        mock_vm.username = None
        mock_vm.password = None
        mock_vm.login_params = {"username": "loginuser", "password": "loginpass"}

        username, password = _get_vm_credentials(vm=mock_vm)
        assert username == "loginuser"
        assert password == "loginpass"


class TestRunCommand:
    """Test cases for run_command function"""

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    def test_run_command_success(self, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test successful command execution"""
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = "default"
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        mock_should_use_key.return_value = True
        mock_get_key.return_value = "/path/to/key"
        mock_shell_run.return_value = (True, "output", "")

        result = run_command(vm=mock_vm, command="ls -la")

        assert result.returncode == 0
        assert result.stdout == "output"
        assert result.stderr == ""

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    def test_run_command_failure(self, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test failed command execution"""
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = "default"
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        mock_should_use_key.return_value = False
        mock_get_key.return_value = None
        mock_shell_run.return_value = (False, "", "error")

        result = run_command(vm=mock_vm, command="invalid-command")

        assert result.returncode == 1
        assert result.stderr == "error"

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    def test_run_command_check_raises_error(self, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test command with check=True raises SSHCommandError on failure"""
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = "default"
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        mock_should_use_key.return_value = False
        mock_get_key.return_value = None
        mock_shell_run.return_value = (False, "", "error")

        with pytest.raises(SSHCommandError, match="Command failed"):
            run_command(vm=mock_vm, command="invalid-command", check=True)

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    def test_run_command_with_list(self, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test command as list is converted to string"""
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = "default"
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        mock_should_use_key.return_value = False
        mock_get_key.return_value = None
        mock_shell_run.return_value = (True, "output", "")

        result = run_command(vm=mock_vm, command=["ls", "-la"])

        assert result.returncode == 0

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    def test_run_command_timeout(self, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test command timeout raises SSHCommandError"""
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = "default"
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        mock_should_use_key.return_value = False
        mock_get_key.return_value = None

        timeout_error = subprocess.TimeoutExpired(cmd="test", timeout=60)
        timeout_error.stdout = b"partial output"
        timeout_error.stderr = b"timeout error"
        mock_shell_run.side_effect = timeout_error

        with pytest.raises(SSHCommandError, match="Command timed out"):
            run_command(vm=mock_vm, command="sleep 1000", timeout=60)

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    def test_run_command_os_error(self, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test OS error raises SSHConnectionError"""
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"
        mock_vm.namespace = "default"
        mock_vm.username = "testuser"
        mock_vm.password = "testpass"
        mock_vm.login_params = {}

        mock_should_use_key.return_value = False
        mock_get_key.return_value = None
        mock_shell_run.side_effect = OSError("virtctl not found")

        with pytest.raises(SSHConnectionError, match="Failed to execute virtctl ssh"):
            run_command(vm=mock_vm, command="ls")


class TestRunSshCommands:
    """Test cases for run_ssh_commands function"""

    @patch("utilities.ssh.run_command")
    def test_run_ssh_commands_success(self, mock_run_command):
        """Test successful SSH commands execution"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout="output",
            stderr="",
        )

        result = run_ssh_commands(vm=mock_vm, commands=["ls", "-la"])

        assert result == ["output"]
        mock_run_command.assert_called_once()

    @patch("utilities.ssh.run_command")
    def test_run_ssh_commands_returns_list(self, mock_run_command):
        """Test run_ssh_commands returns list"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout="test output",
            stderr="",
        )

        result = run_ssh_commands(vm=mock_vm, commands=["echo", "hello"])

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "test output"


class TestWaitForSshConnectivity:
    """Test cases for wait_for_ssh_connectivity function"""

    @patch("utilities.ssh.TimeoutSampler")
    @patch("utilities.ssh.is_connective")
    def test_wait_for_ssh_connectivity_success(self, mock_is_connective, mock_sampler):
        """Test successful SSH connectivity wait"""
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"

        mock_sampler.return_value = [True]

        wait_for_ssh_connectivity(vm=mock_vm)

        mock_sampler.assert_called_once()

    @patch("utilities.ssh.TimeoutSampler")
    @patch("utilities.ssh.is_connective")
    def test_wait_for_ssh_connectivity_timeout(self, mock_is_connective, mock_sampler):
        """Test SSH connectivity timeout"""
        mock_vm = MagicMock()
        mock_vm.name = "test-vm"

        mock_sampler.side_effect = TimeoutExpiredError("Timeout")

        with pytest.raises(TimeoutExpiredError):
            wait_for_ssh_connectivity(vm=mock_vm)


class TestIsConnective:
    """Test cases for is_connective function"""

    @patch("utilities.ssh.run_command")
    def test_is_connective_true(self, mock_run_command):
        """Test is_connective returns True when connection works"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
        )

        result = is_connective(vm=mock_vm)

        assert result is True

    @patch("utilities.ssh.run_command")
    def test_is_connective_false_on_failure(self, mock_run_command):
        """Test is_connective returns False when connection fails"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="connection failed",
        )

        result = is_connective(vm=mock_vm)

        assert result is False

    @patch("utilities.ssh.run_command")
    def test_is_connective_false_on_exception(self, mock_run_command):
        """Test is_connective returns False when exception occurs"""
        mock_vm = MagicMock()
        mock_run_command.side_effect = SSHCommandError(message="Error")

        result = is_connective(vm=mock_vm)

        assert result is False


class TestOSInfo:
    """Test cases for OSInfo class"""

    @patch("utilities.ssh.run_command")
    def test_os_info_release_str(self, mock_run_command):
        """Test OSInfo.release_str property"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout='NAME="Red Hat Enterprise Linux"\nPRETTY_NAME="RHEL 9.2"\nVERSION="9.2"\n',
            stderr="",
        )

        os_info = OSInfo(vm=mock_vm)
        result = os_info.release_str

        assert result == "RHEL 9.2"

    @patch("utilities.ssh.run_command")
    def test_os_info_release_info(self, mock_run_command):
        """Test OSInfo.release_info property"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout='NAME="Red Hat Enterprise Linux"\nVERSION="9.2"\n',
            stderr="",
        )

        os_info = OSInfo(vm=mock_vm)
        result = os_info.release_info

        assert "NAME" in result
        assert "VERSION" in result

    @patch("utilities.ssh.run_command")
    def test_os_info_kernel_info(self, mock_run_command):
        """Test OSInfo.kernel_info property"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout="5.14.0-284.el9.x86_64\n#1 SMP PREEMPT_DYNAMIC\nx86_64",
            stderr="",
        )

        os_info = OSInfo(vm=mock_vm)
        result = os_info.kernel_info

        assert isinstance(result, KernelInfo)
        assert result.release == "5.14.0-284.el9.x86_64"
        assert result.version == "#1 SMP PREEMPT_DYNAMIC"
        assert result.type == "x86_64"

    @patch("utilities.ssh.run_command")
    def test_os_info_kernel_info_partial_raises_index_error(self, mock_run_command):
        """Test OSInfo.kernel_info raises IndexError with partial output"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout="5.14.0-284.el9.x86_64",
            stderr="",
        )

        os_info = OSInfo(vm=mock_vm)

        with pytest.raises(IndexError):
            _ = os_info.kernel_info

    @patch("utilities.ssh.run_command")
    def test_os_info_timezone(self, mock_run_command):
        """Test OSInfo.timezone property"""
        mock_vm = MagicMock()
        mock_run_command.side_effect = [
            CommandResult(returncode=0, stdout="EST", stderr=""),
            CommandResult(returncode=0, stdout="-0500", stderr=""),
        ]

        os_info = OSInfo(vm=mock_vm)
        result = os_info.timezone

        assert isinstance(result, TimezoneInfo)
        assert result.name == "EST"

    @patch("utilities.ssh.run_command")
    def test_os_info_caches_release(self, mock_run_command):
        """Test OSInfo caches os-release data"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout='NAME="RHEL"\n',
            stderr="",
        )

        os_info = OSInfo(vm=mock_vm)
        _ = os_info.release_str
        _ = os_info.release_info

        # Should only call run_command once due to caching
        assert mock_run_command.call_count == 1


class TestPackageManager:
    """Test cases for PackageManager class"""

    @patch("utilities.ssh.run_command")
    def test_package_manager_exist_rpm_success(self, mock_run_command):
        """Test package exists via rpm"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout="qemu-guest-agent-7.0.0",
            stderr="",
        )

        pkg_manager = PackageManager(vm=mock_vm)
        result = pkg_manager.exist(package="qemu-guest-agent")

        assert result is True

    @patch("utilities.ssh.run_command")
    def test_package_manager_exist_dpkg_fallback(self, mock_run_command):
        """Test package exists via dpkg fallback"""
        mock_vm = MagicMock()
        mock_run_command.side_effect = [
            CommandResult(returncode=1, stdout="", stderr="package not found"),
            CommandResult(returncode=0, stdout="qemu-guest-agent installed", stderr=""),
        ]

        pkg_manager = PackageManager(vm=mock_vm)
        result = pkg_manager.exist(package="qemu-guest-agent")

        assert result is True
        assert mock_run_command.call_count == 2

    @patch("utilities.ssh.run_command")
    def test_package_manager_exist_not_found(self, mock_run_command):
        """Test package does not exist"""
        mock_vm = MagicMock()
        mock_run_command.side_effect = [
            CommandResult(returncode=1, stdout="", stderr="not found"),
            CommandResult(returncode=1, stdout="", stderr="not found"),
        ]

        pkg_manager = PackageManager(vm=mock_vm)
        result = pkg_manager.exist(package="nonexistent-package")

        assert result is False

    @patch("utilities.ssh.run_command")
    def test_package_manager_info_rpm(self, mock_run_command):
        """Test getting package info via rpm"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout="Name: qemu-guest-agent\nVersion: 7.0.0",
            stderr="",
        )

        pkg_manager = PackageManager(vm=mock_vm)
        result = pkg_manager.info(package="qemu-guest-agent")

        assert "qemu-guest-agent" in result

    @patch("utilities.ssh.run_command")
    def test_package_manager_info_dpkg_fallback(self, mock_run_command):
        """Test getting package info via dpkg fallback"""
        mock_vm = MagicMock()
        mock_run_command.side_effect = [
            CommandResult(returncode=1, stdout="", stderr="not found"),
            CommandResult(returncode=0, stdout="Package: test\nVersion: 1.0", stderr=""),
        ]

        pkg_manager = PackageManager(vm=mock_vm)
        result = pkg_manager.info(package="test")

        assert "Package:" in result


class TestNetworkInfo:
    """Test cases for NetworkInfo class"""

    @patch("utilities.ssh.run_command")
    def test_network_info_hostname(self, mock_run_command):
        """Test NetworkInfo.hostname property"""
        mock_vm = MagicMock()
        mock_run_command.return_value = CommandResult(
            returncode=0,
            stdout="test-vm.example.com\n",
            stderr="",
        )

        network_info = NetworkInfo(vm=mock_vm)
        result = network_info.hostname

        assert result == "test-vm.example.com"


class TestFileSystem:
    """Test cases for FileSystem class"""

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    @patch("utilities.ssh._get_vm_credentials")
    def test_file_system_transfer_success(self, mock_get_creds, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test FileSystem.transfer success"""
        mock_vm_src = MagicMock()
        mock_vm_src.name = "src-vm"
        mock_vm_src.namespace = "default"

        mock_vm_dst = MagicMock()
        mock_vm_dst.name = "dst-vm"
        mock_vm_dst.namespace = "default"

        mock_get_creds.side_effect = [("srcuser", "srcpass"), ("dstuser", "dstpass")]
        mock_should_use_key.return_value = True
        mock_get_key.return_value = "/path/to/key"
        mock_shell_run.return_value = (True, "", "")

        file_system = FileSystem(vm=mock_vm_src)
        file_system.transfer(
            path_src="/home/user/file.txt",
            target_host=mock_vm_dst,
            path_dst="/tmp/file.txt",
        )

        mock_shell_run.assert_called_once()

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    @patch("utilities.ssh._get_vm_credentials")
    def test_file_system_transfer_failure(self, mock_get_creds, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test FileSystem.transfer failure"""
        mock_vm_src = MagicMock()
        mock_vm_src.name = "src-vm"
        mock_vm_src.namespace = "default"

        mock_vm_dst = MagicMock()
        mock_vm_dst.name = "dst-vm"
        mock_vm_dst.namespace = "default"

        mock_get_creds.side_effect = [("srcuser", "srcpass"), ("dstuser", "dstpass")]
        mock_should_use_key.return_value = False
        mock_get_key.return_value = None
        mock_shell_run.return_value = (False, "", "transfer failed")

        file_system = FileSystem(vm=mock_vm_src)

        with pytest.raises(SSHCommandError, match="File transfer failed"):
            file_system.transfer(
                path_src="/home/user/file.txt",
                target_host=mock_vm_dst,
                path_dst="/tmp/file.txt",
            )

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    @patch("utilities.ssh._get_vm_credentials")
    def test_file_system_transfer_timeout(self, mock_get_creds, mock_should_use_key, mock_get_key, mock_shell_run):
        """Test FileSystem.transfer timeout"""
        mock_vm_src = MagicMock()
        mock_vm_src.name = "src-vm"
        mock_vm_src.namespace = "default"

        mock_vm_dst = MagicMock()
        mock_vm_dst.name = "dst-vm"
        mock_vm_dst.namespace = "default"

        mock_get_creds.side_effect = [("srcuser", "srcpass"), ("dstuser", "dstpass")]
        mock_should_use_key.return_value = False
        mock_get_key.return_value = None
        mock_shell_run.side_effect = subprocess.TimeoutExpired(cmd="scp", timeout=120)

        file_system = FileSystem(vm=mock_vm_src)

        with pytest.raises(SSHCommandError, match="File transfer timed out"):
            file_system.transfer(
                path_src="/home/user/file.txt",
                target_host=mock_vm_dst,
                path_dst="/tmp/file.txt",
            )

    @patch("utilities.ssh.shell_run_command")
    @patch("utilities.ssh._get_ssh_key_path")
    @patch("utilities.ssh._should_use_ssh_key")
    @patch("utilities.ssh._get_vm_credentials")
    def test_file_system_transfer_to_file_system(
        self, mock_get_creds, mock_should_use_key, mock_get_key, mock_shell_run
    ):
        """Test FileSystem.transfer to another FileSystem object"""
        mock_vm_src = MagicMock()
        mock_vm_src.name = "src-vm"
        mock_vm_src.namespace = "default"

        mock_vm_dst = MagicMock()
        mock_vm_dst.name = "dst-vm"
        mock_vm_dst.namespace = "default"

        mock_get_creds.side_effect = [("srcuser", "srcpass"), ("dstuser", "dstpass")]
        mock_should_use_key.return_value = False
        mock_get_key.return_value = None
        mock_shell_run.return_value = (True, "", "")

        fs_src = FileSystem(vm=mock_vm_src)
        fs_dst = FileSystem(vm=mock_vm_dst)

        fs_src.transfer(
            path_src="/home/user/file.txt",
            target_host=fs_dst,
            path_dst="/tmp/file.txt",
        )

        mock_shell_run.assert_called_once()


class TestSSHClient:
    """Test cases for SSHClient class"""

    def test_ssh_client_initialization(self):
        """Test SSHClient initialization"""
        mock_vm = MagicMock()

        client = SSHClient(vm=mock_vm)

        assert isinstance(client.os, OSInfo)
        assert isinstance(client.network, NetworkInfo)
        assert isinstance(client.package_manager, PackageManager)
        assert isinstance(client.fs, FileSystem)
        assert client.sudo is False

    @patch("utilities.ssh.run_command")
    def test_ssh_client_run_command(self, mock_run_cmd):
        """Test SSHClient.run_command"""
        mock_vm = MagicMock()
        mock_run_cmd.return_value = CommandResult(
            returncode=0,
            stdout="output",
            stderr="",
        )

        client = SSHClient(vm=mock_vm)
        returncode, stdout, stderr = client.run_command(command=["ls", "-la"])

        assert returncode == 0
        assert stdout == "output"
        assert stderr == ""

    @patch("utilities.ssh.run_command")
    def test_ssh_client_run_command_with_sudo(self, mock_run_cmd):
        """Test SSHClient.run_command with sudo"""
        mock_vm = MagicMock()
        mock_run_cmd.return_value = CommandResult(
            returncode=0,
            stdout="output",
            stderr="",
        )

        client = SSHClient(vm=mock_vm)
        client.sudo = True
        client.run_command(command=["ls", "-la"])

        # Verify sudo was prepended
        call_kwargs = mock_run_cmd.call_args[1]
        assert "sudo" in call_kwargs["command"]

    @patch("utilities.ssh.run_command")
    def test_ssh_client_run_command_with_timeout(self, mock_run_cmd):
        """Test SSHClient.run_command with custom timeout"""
        mock_vm = MagicMock()
        mock_run_cmd.return_value = CommandResult(
            returncode=0,
            stdout="output",
            stderr="",
        )

        client = SSHClient(vm=mock_vm)
        client.run_command(command=["ls"], tcp_timeout=120.5)

        call_kwargs = mock_run_cmd.call_args[1]
        assert call_kwargs["timeout"] == 120
