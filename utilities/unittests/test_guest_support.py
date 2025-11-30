# Generated using Claude cli

"""Unit tests for guest_support module"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from timeout_sampler import TimeoutExpiredError

# Need to mock circular imports for guest_support
import utilities

mock_virt = MagicMock()
sys.modules["utilities.virt"] = mock_virt
utilities.virt = mock_virt

# Import after setting up mocks to avoid circular dependency
from utilities.guest_support import (  # noqa: E402
    assert_windows_efi,
    check_vm_xml_hyperv,
    check_windows_vm_hvinfo,
)


class TestAssertWindowsEfi:
    """Test cases for assert_windows_efi function"""

    @patch("utilities.guest_support.run_ssh_commands")
    def test_assert_windows_efi_success(self, mock_run_ssh):
        """Test successful EFI verification when EFI path is found in output"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock bcdedit output with EFI path
        mock_run_ssh.return_value = [
            "path            \\EFI\\Microsoft\\Boot\\bootmgfw.efi\ndescription     Windows Boot Manager\n"
        ]

        # Should not raise any exception
        assert_windows_efi(mock_vm)

        mock_run_ssh.assert_called_once()

    @patch("utilities.guest_support.run_ssh_commands")
    def test_assert_windows_efi_failure(self, mock_run_ssh):
        """Test assertion failure when EFI path is not found in output"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock bcdedit output without EFI path
        mock_run_ssh.return_value = [
            "path            \\Windows\\system32\\winload.exe\ndescription     Windows Boot Manager\n"
        ]

        with pytest.raises(AssertionError, match="EFI boot not found in path"):
            assert_windows_efi(mock_vm)

    @patch("utilities.guest_support.run_ssh_commands")
    def test_assert_windows_efi_partial_path(self, mock_run_ssh):
        """Test assertion failure when only partial EFI path is present"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock bcdedit output with partial EFI path
        mock_run_ssh.return_value = ["path            \\EFI\\Microsoft\\Boot\\something.exe"]

        with pytest.raises(AssertionError, match="EFI boot not found in path"):
            assert_windows_efi(mock_vm)


class TestCheckVmXmlHyperv:
    """Test cases for check_vm_xml_hyperv function"""

    def test_check_vm_xml_hyperv_all_features_on(self):
        """Test successful validation when all HyperV features are enabled"""
        mock_vm = MagicMock()

        # Mock VM XML with all features enabled
        hyperv_features = {
            "relaxed": {"@state": "on"},
            "vapic": {"@state": "on"},
            "spinlocks": {"@state": "on", "@retries": "8191"},
            "vpindex": {"@state": "on"},
            "synic": {"@state": "on"},
            "stimer": {"@state": "on", "direct": {"@state": "on"}},
            "frequencies": {"@state": "on"},
            "ipi": {"@state": "on"},
            "reset": {"@state": "on"},
            "runtime": {"@state": "on"},
            "tlbflush": {"@state": "on"},
            "reenlightenment": {"@state": "on"},
        }

        mock_vm.privileged_vmi.xml_dict = {"domain": {"features": {"hyperv": hyperv_features}}}

        # Should not raise any exception
        check_vm_xml_hyperv(mock_vm)

    def test_check_vm_xml_hyperv_feature_off(self):
        """Test assertion failure when one HyperV feature is disabled"""
        mock_vm = MagicMock()

        # Mock VM XML with one feature disabled
        hyperv_features = {
            "relaxed": {"@state": "on"},
            "vapic": {"@state": "off"},  # This feature is disabled
            "spinlocks": {"@state": "on", "@retries": "8191"},
            "vpindex": {"@state": "on"},
            "synic": {"@state": "on"},
            "stimer": {"@state": "on", "direct": {"@state": "on"}},
            "frequencies": {"@state": "on"},
            "ipi": {"@state": "on"},
            "reset": {"@state": "on"},
            "runtime": {"@state": "on"},
            "tlbflush": {"@state": "on"},
            "reenlightenment": {"@state": "on"},
        }

        mock_vm.privileged_vmi.xml_dict = {"domain": {"features": {"hyperv": hyperv_features}}}

        with pytest.raises(AssertionError, match="hyperV flags are not set correctly"):
            check_vm_xml_hyperv(mock_vm)

    def test_check_vm_xml_hyperv_spinlocks_wrong(self):
        """Test assertion failure when spinlocks retries value is incorrect"""
        mock_vm = MagicMock()

        # Mock VM XML with wrong spinlocks value
        hyperv_features = {
            "relaxed": {"@state": "on"},
            "vapic": {"@state": "on"},
            "spinlocks": {"@state": "on", "@retries": "4096"},  # Wrong value
            "vpindex": {"@state": "on"},
            "synic": {"@state": "on"},
            "stimer": {"@state": "on", "direct": {"@state": "on"}},
            "frequencies": {"@state": "on"},
            "ipi": {"@state": "on"},
            "reset": {"@state": "on"},
            "runtime": {"@state": "on"},
            "tlbflush": {"@state": "on"},
            "reenlightenment": {"@state": "on"},
        }

        mock_vm.privileged_vmi.xml_dict = {"domain": {"features": {"hyperv": hyperv_features}}}

        with pytest.raises(AssertionError, match="hyperV flags are not set correctly"):
            check_vm_xml_hyperv(mock_vm)

    def test_check_vm_xml_hyperv_stimer_direct_off(self):
        """Test assertion failure when stimer direct feature is disabled"""
        mock_vm = MagicMock()

        # Mock VM XML with stimer direct disabled
        hyperv_features = {
            "relaxed": {"@state": "on"},
            "vapic": {"@state": "on"},
            "spinlocks": {"@state": "on", "@retries": "8191"},
            "vpindex": {"@state": "on"},
            "synic": {"@state": "on"},
            "stimer": {"@state": "on", "direct": {"@state": "off"}},  # Direct is disabled
            "frequencies": {"@state": "on"},
            "ipi": {"@state": "on"},
            "reset": {"@state": "on"},
            "runtime": {"@state": "on"},
            "tlbflush": {"@state": "on"},
            "reenlightenment": {"@state": "on"},
        }

        mock_vm.privileged_vmi.xml_dict = {"domain": {"features": {"hyperv": hyperv_features}}}

        with pytest.raises(AssertionError, match="hyperV flags are not set correctly"):
            check_vm_xml_hyperv(mock_vm)

    def test_check_vm_xml_hyperv_multiple_failures(self):
        """Test assertion failure with multiple incorrect HyperV settings"""
        mock_vm = MagicMock()

        # Mock VM XML with multiple failures
        hyperv_features = {
            "relaxed": {"@state": "off"},  # Feature disabled
            "vapic": {"@state": "on"},
            "spinlocks": {"@state": "on", "@retries": "1024"},  # Wrong value
            "vpindex": {"@state": "on"},
            "synic": {"@state": "on"},
            "stimer": {"@state": "on", "direct": {"@state": "off"}},  # Direct disabled
            "frequencies": {"@state": "on"},
            "ipi": {"@state": "on"},
            "reset": {"@state": "on"},
            "runtime": {"@state": "on"},
            "tlbflush": {"@state": "on"},
            "reenlightenment": {"@state": "on"},
        }

        mock_vm.privileged_vmi.xml_dict = {"domain": {"features": {"hyperv": hyperv_features}}}

        with pytest.raises(AssertionError, match="hyperV flags are not set correctly"):
            check_vm_xml_hyperv(mock_vm)


class TestCheckWindowsVmHvinfo:
    """Test cases for check_windows_vm_hvinfo function"""

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_success(self, mock_sampler):
        """Test successful validation when all HyperV settings are correct"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock valid hvinfo.exe output
        hvinfo_data = {
            "HyperVsupport": True,
            "Recommendations": {
                "RelaxedTiming": True,
                "MSRAPICRegisters": True,
                "HypercallRemoteTLBFlush": True,
                "SyntheticClusterIPI": True,
                "SpinlockRetries": "8191",
            },
            "Privileges": {
                "AccessVpRunTimeReg": True,
                "AccessSynicRegs": True,
                "AccessSyntheticTimerRegs": True,
                "AccessVpIndex": True,
            },
            "Features": {
                "TimerFrequenciesQuery": True,
            },
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[json.dumps(hvinfo_data)]]))
        mock_sampler.return_value = mock_sampler_instance

        # Should not raise any exception
        check_windows_vm_hvinfo(mock_vm)

        mock_sampler.assert_called_once()

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_failed_recommendations(self, mock_sampler):
        """Test assertion failure when HyperV recommendation is missing"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock hvinfo.exe output with missing recommendation
        hvinfo_data = {
            "HyperVsupport": True,
            "Recommendations": {
                "RelaxedTiming": False,  # Missing recommendation
                "MSRAPICRegisters": True,
                "HypercallRemoteTLBFlush": True,
                "SyntheticClusterIPI": True,
                "SpinlockRetries": "8191",
            },
            "Privileges": {
                "AccessVpRunTimeReg": True,
                "AccessSynicRegs": True,
                "AccessSyntheticTimerRegs": True,
                "AccessVpIndex": True,
            },
            "Features": {
                "TimerFrequenciesQuery": True,
            },
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[json.dumps(hvinfo_data)]]))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(AssertionError, match="hyperV flags are not set correctly in the guest"):
            check_windows_vm_hvinfo(mock_vm)

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_wrong_spinlocks(self, mock_sampler):
        """Test assertion failure when spinlock retries value is incorrect"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock hvinfo.exe output with wrong spinlock value
        hvinfo_data = {
            "HyperVsupport": True,
            "Recommendations": {
                "RelaxedTiming": True,
                "MSRAPICRegisters": True,
                "HypercallRemoteTLBFlush": True,
                "SyntheticClusterIPI": True,
                "SpinlockRetries": "4096",  # Wrong value
            },
            "Privileges": {
                "AccessVpRunTimeReg": True,
                "AccessSynicRegs": True,
                "AccessSyntheticTimerRegs": True,
                "AccessVpIndex": True,
            },
            "Features": {
                "TimerFrequenciesQuery": True,
            },
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[json.dumps(hvinfo_data)]]))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(AssertionError, match="SpinlockRetries"):
            check_windows_vm_hvinfo(mock_vm)

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_failed_privileges(self, mock_sampler):
        """Test assertion failure when HyperV privilege is missing"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock hvinfo.exe output with missing privilege
        hvinfo_data = {
            "HyperVsupport": True,
            "Recommendations": {
                "RelaxedTiming": True,
                "MSRAPICRegisters": True,
                "HypercallRemoteTLBFlush": True,
                "SyntheticClusterIPI": True,
                "SpinlockRetries": "8191",
            },
            "Privileges": {
                "AccessVpRunTimeReg": False,  # Missing privilege
                "AccessSynicRegs": True,
                "AccessSyntheticTimerRegs": True,
                "AccessVpIndex": True,
            },
            "Features": {
                "TimerFrequenciesQuery": True,
            },
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[json.dumps(hvinfo_data)]]))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(AssertionError, match="hyperV flags are not set correctly in the guest"):
            check_windows_vm_hvinfo(mock_vm)

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_failed_features(self, mock_sampler):
        """Test assertion failure when HyperV feature is missing"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock hvinfo.exe output with missing feature
        hvinfo_data = {
            "HyperVsupport": True,
            "Recommendations": {
                "RelaxedTiming": True,
                "MSRAPICRegisters": True,
                "HypercallRemoteTLBFlush": True,
                "SyntheticClusterIPI": True,
                "SpinlockRetries": "8191",
            },
            "Privileges": {
                "AccessVpRunTimeReg": True,
                "AccessSynicRegs": True,
                "AccessSyntheticTimerRegs": True,
                "AccessVpIndex": True,
            },
            "Features": {
                "TimerFrequenciesQuery": False,  # Missing feature
            },
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[json.dumps(hvinfo_data)]]))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(AssertionError, match="hyperV flags are not set correctly in the guest"):
            check_windows_vm_hvinfo(mock_vm)

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_no_hyperv_support(self, mock_sampler):
        """Test assertion failure when HyperVsupport is False"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock hvinfo.exe output with HyperVsupport disabled
        hvinfo_data = {
            "HyperVsupport": False,  # HyperV support disabled
            "Recommendations": {
                "RelaxedTiming": True,
                "MSRAPICRegisters": True,
                "HypercallRemoteTLBFlush": True,
                "SyntheticClusterIPI": True,
                "SpinlockRetries": "8191",
            },
            "Privileges": {
                "AccessVpRunTimeReg": True,
                "AccessSynicRegs": True,
                "AccessSyntheticTimerRegs": True,
                "AccessVpIndex": True,
            },
            "Features": {
                "TimerFrequenciesQuery": True,
            },
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[json.dumps(hvinfo_data)]]))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(AssertionError, match="HyperVsupport"):
            check_windows_vm_hvinfo(mock_vm)

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_timeout(self, mock_sampler):
        """Test assertion failure when hvinfo output cannot be retrieved"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock TimeoutSampler that never gets valid output
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(
            side_effect=TimeoutExpiredError("Timeout waiting for hvinfo output", "test_value")
        )
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            check_windows_vm_hvinfo(mock_vm)

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_connection_refused(self, mock_sampler):
        """Test assertion failure when connection is refused during sampling"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock TimeoutSampler with connection refused errors followed by timeout
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(
            return_value=iter([
                ["connect: connection refused"],
                ["connect: connection refused"],
                ["connect: connection refused"],
            ])
        )

        # Add side_effect to simulate timeout after connection refused attempts
        def side_effect_generator():
            for _ in range(3):
                yield ["connect: connection refused"]
            raise TimeoutExpiredError("Timeout", "test_value")

        mock_sampler_instance.__iter__ = MagicMock(side_effect=side_effect_generator)
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            check_windows_vm_hvinfo(mock_vm)

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_multiple_failures(self, mock_sampler):
        """Test assertion failure with multiple incorrect HyperV settings"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock hvinfo.exe output with multiple failures
        hvinfo_data = {
            "HyperVsupport": False,  # HyperV support disabled
            "Recommendations": {
                "RelaxedTiming": False,  # Missing recommendation
                "MSRAPICRegisters": True,
                "HypercallRemoteTLBFlush": True,
                "SyntheticClusterIPI": False,  # Missing recommendation
                "SpinlockRetries": "1024",  # Wrong value
            },
            "Privileges": {
                "AccessVpRunTimeReg": False,  # Missing privilege
                "AccessSynicRegs": True,
                "AccessSyntheticTimerRegs": True,
                "AccessVpIndex": True,
            },
            "Features": {
                "TimerFrequenciesQuery": False,  # Missing feature
            },
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[json.dumps(hvinfo_data)]]))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(AssertionError, match="hyperV flags are not set correctly in the guest"):
            check_windows_vm_hvinfo(mock_vm)

    @patch("utilities.guest_support.TimeoutSampler")
    def test_check_windows_vm_hvinfo_empty_output(self, mock_sampler):
        """Test handling of empty output from hvinfo.exe"""
        mock_vm = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        # Mock TimeoutSampler with empty output
        mock_sampler_instance = MagicMock()

        def side_effect_generator():
            yield [""]  # Empty string output
            yield [None]  # None output
            raise TimeoutExpiredError("Timeout", "test_value")

        mock_sampler_instance.__iter__ = MagicMock(side_effect=side_effect_generator)
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            check_windows_vm_hvinfo(mock_vm)
