# Generated using Claude cli

"""Unit tests for ssp module"""

import sys
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.dynamic.exceptions import NotFoundError
from timeout_sampler import TimeoutExpiredError

# Need to mock additional circular imports for ssp
import utilities

mock_virt = MagicMock()
mock_storage = MagicMock()
mock_infra = MagicMock()
sys.modules["utilities.virt"] = mock_virt
sys.modules["utilities.storage"] = mock_storage
sys.modules["utilities.infra"] = mock_infra
utilities.virt = mock_virt
utilities.storage = mock_storage
utilities.infra = mock_infra

# Clear any mock of utilities.ssp from other test modules (e.g., test_hco.py)
# to ensure we can import the real module for testing
if "utilities.ssp" in sys.modules:
    del sys.modules["utilities.ssp"]

# Import after setting up mocks to avoid circular dependency
from utilities.ssp import (  # noqa: E402
    cluster_instance_type_for_hot_plug,
    create_custom_template_from_url,
    get_cim_instance_json,
    get_data_import_crons,
    get_ga_version,
    get_reg_product_name,
    get_ssp_resource,
    get_windows_os_info,
    get_windows_timezone,
    guest_agent_version_parser,
    is_ssp_pod_running,
    matrix_auto_boot_data_import_cron_prefixes,
    validate_os_info_vmi_vs_windows_os,
    verify_ssp_pod_is_running,
    wait_for_at_least_one_auto_update_data_import_cron,
    wait_for_condition_message_value,
    wait_for_deleted_data_import_crons,
    wait_for_ssp_conditions,
)


class TestWaitForDeletedDataImportCrons:
    """Test cases for wait_for_deleted_data_import_crons function"""

    @patch("utilities.ssp.matrix_auto_boot_data_import_cron_prefixes")
    @patch("utilities.ssp.TimeoutSampler")
    def test_wait_for_deleted_data_import_crons_success(self, mock_sampler, mock_matrix_prefixes):
        """Test successful deletion of data import crons"""
        mock_matrix_prefixes.return_value = ["rhel9", "fedora41"]

        # Mock data import crons
        mock_cron1 = MagicMock()
        mock_cron1.name = "rhel9-auto-update"
        mock_cron1.exists = False

        mock_cron2 = MagicMock()
        mock_cron2.name = "fedora41-auto-update"
        mock_cron2.exists = False

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[]]))  # Empty list means no existing crons
        mock_sampler.return_value = mock_sampler_instance

        result = wait_for_deleted_data_import_crons([mock_cron1, mock_cron2])

        assert result is None  # Function should complete without returning anything
        mock_sampler.assert_called_once()

    @patch("utilities.ssp.matrix_auto_boot_data_import_cron_prefixes")
    @patch("utilities.ssp.TimeoutSampler")
    def test_wait_for_deleted_data_import_crons_timeout(self, mock_sampler, mock_matrix_prefixes):
        """Test timeout when data import crons don't get deleted"""
        mock_matrix_prefixes.return_value = ["rhel9"]

        # Mock data import cron that still exists
        mock_cron = MagicMock()
        mock_cron.name = "rhel9-auto-update"
        mock_cron.exists = True

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "test_value"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            wait_for_deleted_data_import_crons([mock_cron])


class TestWaitForAtLeastOneAutoUpdateDataImportCron:
    """Test cases for wait_for_at_least_one_auto_update_data_import_cron function"""

    @patch("utilities.ssp.get_data_import_crons")
    @patch("utilities.ssp.TimeoutSampler")
    def test_wait_for_at_least_one_auto_update_data_import_cron_success(self, mock_sampler, mock_get_crons):
        """Test successful waiting for at least one auto-update data import cron"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "test-namespace"

        # Mock data import crons
        mock_cron1 = MagicMock()
        mock_cron1.name = "rhel9-auto-update"
        mock_get_crons.return_value = [mock_cron1]

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[mock_cron1]]))
        mock_sampler.return_value = mock_sampler_instance

        result = wait_for_at_least_one_auto_update_data_import_cron(mock_admin_client, mock_namespace)

        assert result is None
        mock_sampler.assert_called_once()

    @patch("utilities.ssp.get_data_import_crons")
    @patch("utilities.ssp.TimeoutSampler")
    def test_wait_for_at_least_one_auto_update_data_import_cron_timeout(self, mock_sampler, mock_get_crons):
        """Test timeout when no auto-update data import crons exist"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "test-namespace"

        mock_get_crons.return_value = []

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "test_value"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            wait_for_at_least_one_auto_update_data_import_cron(mock_admin_client, mock_namespace)


class TestMatrixAutoBootDataImportCronPrefixes:
    """Test cases for matrix_auto_boot_data_import_cron_prefixes function"""

    @patch("utilities.ssp.py_config")
    def test_matrix_auto_boot_data_import_cron_prefixes_returns_list(self, mock_config):
        """Test that matrix_auto_boot_data_import_cron_prefixes returns a list"""
        mock_config.__getitem__.return_value = [
            {"rhel8": {"data_import_cron_prefix": "rhel8"}},
            {"rhel9": {"data_import_cron_prefix": "rhel9"}},
        ]

        result = matrix_auto_boot_data_import_cron_prefixes()
        assert isinstance(result, list)
        assert len(result) == 2
        assert "rhel8" in result
        assert "rhel9" in result


class TestGetDataImportCrons:
    """Test cases for get_data_import_crons function"""

    @patch("utilities.ssp.DataImportCron")
    def test_get_data_import_crons_success(self, mock_dic_class):
        """Test successful retrieval of data import crons"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "test-namespace"

        mock_cron1 = MagicMock()
        mock_cron1.name = "rhel9-auto-update"
        mock_cron2 = MagicMock()
        mock_cron2.name = "fedora41-auto-update"

        mock_dic_class.get.return_value = [mock_cron1, mock_cron2]

        result = get_data_import_crons(mock_admin_client, mock_namespace)

        assert result == [mock_cron1, mock_cron2]
        mock_dic_class.get.assert_called_once_with(dyn_client=mock_admin_client, namespace=mock_namespace.name)


class TestGetSspResource:
    """Test cases for get_ssp_resource function"""

    @patch("utilities.ssp.SSP")
    def test_get_ssp_resource_success(self, mock_ssp_class):
        """Test successful retrieval of SSP resource"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "test-namespace"

        mock_ssp = MagicMock()
        mock_ssp.name = "ssp-sample"
        mock_ssp_class.get.return_value = [mock_ssp]

        result = get_ssp_resource(mock_admin_client, mock_namespace)

        assert result == mock_ssp
        mock_ssp_class.get.assert_called_once()

    @patch("utilities.ssp.SSP")
    def test_get_ssp_resource_not_found(self, mock_ssp_class):
        """Test SSP resource not found"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "test-namespace"

        mock_ssp_class.get.side_effect = NotFoundError(MagicMock(status=404))

        with pytest.raises(NotFoundError):
            get_ssp_resource(mock_admin_client, mock_namespace)


class TestIsSspPodRunning:
    """Test cases for is_ssp_pod_running function"""

    @patch("utilities.ssp.utilities.infra.get_pod_by_name_prefix")
    def test_is_ssp_pod_running_true(self, mock_get_pod):
        """Test SSP pod is running"""
        mock_dyn_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "test-namespace"

        mock_pod = MagicMock()
        mock_pod.status = "Running"
        mock_pod.Status.RUNNING = "Running"
        mock_pod.instance.status.containerStatuses = [{"ready": True}]
        mock_get_pod.return_value = mock_pod

        result = is_ssp_pod_running(mock_dyn_client, mock_namespace)

        assert result is True

    @patch("utilities.ssp.utilities.infra.get_pod_by_name_prefix")
    def test_is_ssp_pod_running_false_not_running(self, mock_get_pod):
        """Test SSP pod is not running"""
        mock_dyn_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "test-namespace"

        mock_pod = MagicMock()
        mock_pod.status = "Pending"
        mock_pod.Status.RUNNING = "Running"
        mock_get_pod.return_value = mock_pod

        result = is_ssp_pod_running(mock_dyn_client, mock_namespace)

        assert result is False


class TestVerifySspPodIsRunning:
    """Test cases for verify_ssp_pod_is_running function"""

    @patch("utilities.ssp.is_ssp_pod_running")
    @patch("utilities.ssp.TimeoutSampler")
    def test_verify_ssp_pod_is_running_success(self, mock_sampler, mock_is_running):
        """Test successful verification of SSP pod running"""
        mock_dyn_client = MagicMock()
        mock_namespace = MagicMock()

        mock_is_running.return_value = True
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([True, True, True]))
        mock_sampler.return_value = mock_sampler_instance

        result = verify_ssp_pod_is_running(mock_dyn_client, mock_namespace)

        assert result is None
        mock_sampler.assert_called_once()

    @patch("utilities.ssp.is_ssp_pod_running")
    @patch("utilities.ssp.TimeoutSampler")
    def test_verify_ssp_pod_is_running_timeout(self, mock_sampler, mock_is_running):
        """Test timeout when SSP pod is not running"""
        mock_dyn_client = MagicMock()
        mock_namespace = MagicMock()

        mock_is_running.return_value = False
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "test_value"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            verify_ssp_pod_is_running(mock_dyn_client, mock_namespace)


class TestWaitForSspConditions:
    """Test cases for wait_for_ssp_conditions function"""

    @patch("utilities.ssp.utilities.infra.wait_for_consistent_resource_conditions")
    def test_wait_for_ssp_conditions_success(self, mock_wait_conditions):
        """Test successful waiting for SSP conditions"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "test-namespace"

        result = wait_for_ssp_conditions(mock_admin_client, mock_namespace)

        assert result is None
        mock_wait_conditions.assert_called_once()


class TestWaitForConditionMessageValue:
    """Test cases for wait_for_condition_message_value function"""

    @patch("utilities.ssp.TimeoutSampler")
    def test_wait_for_condition_message_value_success(self, mock_sampler):
        """Test successful waiting for condition message value"""
        mock_resource = MagicMock()
        mock_resource.name = "test-resource"
        mock_resource.instance.status.conditions = [{"type": "Available", "message": "All components are available"}]

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([mock_resource.instance.status.conditions]))
        mock_sampler.return_value = mock_sampler_instance

        result = wait_for_condition_message_value(mock_resource, "All components are available")

        assert result is None
        mock_sampler.assert_called_once()

    @patch("utilities.ssp.TimeoutSampler")
    def test_wait_for_condition_message_value_timeout(self, mock_sampler):
        """Test timeout when condition message value is not met"""
        mock_resource = MagicMock()
        mock_resource.name = "test-resource"
        mock_resource.instance.status.conditions = [{"type": "Available", "message": "Components are not ready"}]

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "test_value"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            wait_for_condition_message_value(mock_resource, "All components are available")


class TestCreateCustomTemplateFromUrl:
    """Test cases for create_custom_template_from_url function"""

    @patch("utilities.ssp.urllib.request.urlretrieve")
    @patch("utilities.ssp.Template")
    def test_create_custom_template_from_url_success(self, mock_template_class, mock_urlretrieve):
        """Test successful creation of custom template from URL"""
        mock_template = MagicMock()
        mock_template_class.return_value.__enter__ = MagicMock(return_value=mock_template)
        mock_template_class.return_value.__exit__ = MagicMock(return_value=None)

        mock_namespace = MagicMock()

        with create_custom_template_from_url(
            url="https://example.com/template.yaml",
            template_name="custom-template",
            template_dir="/tmp",
            namespace=mock_namespace,
        ) as template:
            assert template == mock_template

        mock_urlretrieve.assert_called_once_with(
            url="https://example.com/template.yaml", filename="/tmp/custom-template"
        )
        mock_template_class.assert_called_once()


class TestGuestAgentVersionParser:
    """Test cases for guest_agent_version_parser function"""

    def test_guest_agent_version_parser_standard_format(self):
        """Test parsing of standard version format"""
        result = guest_agent_version_parser("7.4.0")
        assert result == "7.4.0"

    def test_guest_agent_version_parser_with_extra_info(self):
        """Test parsing of version with extra information"""
        result = guest_agent_version_parser("7.4.0-1.el8")
        assert result == "7.4.0-1"

    def test_guest_agent_version_parser_four_part_version(self):
        """Test parsing of four-part version"""
        result = guest_agent_version_parser("100.0.0.0")
        assert result == "100.0.0.0"

    def test_guest_agent_version_parser_invalid_format(self):
        """Test parsing of invalid format"""
        with pytest.raises(AttributeError):
            guest_agent_version_parser("invalid")


class TestGetWindowsTimezone:
    """Test cases for get_windows_timezone function"""

    @patch("utilities.ssp.run_ssh_commands")
    def test_get_windows_timezone_success(self, mock_run_ssh):
        """Test successful extraction of Windows timezone"""
        mock_ssh_exec = MagicMock()
        mock_run_ssh.return_value = ["UTC"]

        result = get_windows_timezone(mock_ssh_exec)

        assert result == "UTC"
        mock_run_ssh.assert_called_once()

    @patch("utilities.ssp.run_ssh_commands")
    def test_get_windows_timezone_with_standard_name(self, mock_run_ssh):
        """Test timezone extraction with standard name only"""
        mock_ssh_exec = MagicMock()
        mock_run_ssh.return_value = ["StandardName: UTC"]

        result = get_windows_timezone(mock_ssh_exec, get_standard_name=True)

        assert result == "StandardName: UTC"
        mock_run_ssh.assert_called_once()


class TestGetGaVersion:
    """Test cases for get_ga_version function"""

    @patch("utilities.ssp.run_ssh_commands")
    def test_get_ga_version_success(self, mock_run_ssh):
        """Test successful extraction of GA version"""
        mock_ssh_exec = MagicMock()
        mock_run_ssh.return_value = ["7.4.0  "]  # With trailing space to test strip()

        result = get_ga_version(mock_ssh_exec)

        assert result == "7.4.0"
        mock_run_ssh.assert_called_once()


class TestGetCimInstanceJson:
    """Test cases for get_cim_instance_json function"""

    @patch("utilities.ssp.run_ssh_commands")
    def test_get_cim_instance_json_success(self, mock_run_ssh):
        """Test successful extraction of CIM instance JSON"""
        mock_ssh_exec = MagicMock()
        test_json = '{"CSName": "test-host", "BuildNumber": "19042"}'
        mock_run_ssh.return_value = [test_json]

        result = get_cim_instance_json(mock_ssh_exec)

        expected = {"CSName": "test-host", "BuildNumber": "19042"}
        assert result == expected
        mock_run_ssh.assert_called_once()


class TestGetRegProductName:
    """Test cases for get_reg_product_name function"""

    @patch("utilities.ssp.run_ssh_commands")
    def test_get_reg_product_name_success(self, mock_run_ssh):
        """Test successful extraction of registry product name"""
        mock_ssh_exec = MagicMock()
        mock_run_ssh.return_value = ["REG_SZ    Microsoft Windows Server 2019\r\n"]

        result = get_reg_product_name(mock_ssh_exec)

        assert result == "REG_SZ    Microsoft Windows Server 2019\r\n"
        mock_run_ssh.assert_called_once()


class TestGetWindowsOsInfo:
    """Test cases for get_windows_os_info function"""

    @patch("utilities.ssp.get_windows_timezone")
    @patch("utilities.ssp.get_reg_product_name")
    @patch("utilities.ssp.get_ga_version")
    @patch("utilities.ssp.get_cim_instance_json")
    @patch("utilities.ssp.guest_agent_version_parser")
    def test_get_windows_os_info_success(self, mock_parser, mock_cim, mock_ga, mock_reg, mock_tz):
        """Test successful extraction of Windows OS info"""
        mock_ssh_exec = MagicMock()

        mock_cim.return_value = {
            "CSName": "test-host",
            "BuildNumber": "19042",
            "Caption": "Microsoft Windows Server 2019",
            "Version": "10.0.19042",
            "OSArchitecture": "64-bit",
        }
        mock_ga.return_value = "7.4.0"
        mock_parser.return_value = "7.4.0"
        mock_reg.return_value = "REG_SZ    Windows Server 2019 Standard\r\n"
        mock_tz.return_value = "UTC"

        result = get_windows_os_info(mock_ssh_exec)

        expected = {
            "guestAgentVersion": "7.4.0",
            "hostname": "test-host",
            "os": {
                "name": "Microsoft Windows",
                "kernelRelease": "19042",
                "version": "Microsoft Windows Server 2019",
                "prettyName": "Windows Server 2019 Standard",
                "versionId": "2019",
                "kernelVersion": "10.0",
                "machine": "x86_64",
                "id": "mswindows",
            },
            "timezone": "UTC",
        }
        assert result == expected


class TestValidateOsInfoVmiVsWindowsOs:
    """Test cases for validate_os_info_vmi_vs_windows_os function"""

    @patch("utilities.ssp.get_windows_os_info")
    @patch("utilities.virt.get_guest_os_info")
    def test_validate_os_info_vmi_vs_windows_os_success(self, mock_get_vmi_info, mock_get_windows_info):
        """Test successful validation when OS info matches"""
        mock_vm = MagicMock()
        mock_vm.vmi = MagicMock()
        mock_vm.ssh_exec = MagicMock()

        mock_get_vmi_info.return_value = {"name": "Microsoft Windows"}
        mock_get_windows_info.return_value = {"os": {"name": "Microsoft Windows Server 2019"}}

        # Should not raise any exception
        validate_os_info_vmi_vs_windows_os(mock_vm)

    @patch("utilities.ssp.get_windows_os_info")
    @patch("utilities.virt.get_guest_os_info")
    def test_validate_os_info_vmi_vs_windows_os_no_vmi_info(self, mock_get_vmi_info, mock_get_windows_info):
        """Test validation failure when VMI has no guest agent data"""
        mock_vm = MagicMock()
        mock_vm.vmi = MagicMock()

        mock_get_vmi_info.return_value = None

        with pytest.raises(AssertionError, match="VMI doesn't have guest agent data"):
            validate_os_info_vmi_vs_windows_os(mock_vm)


class TestClusterInstanceTypeForHotPlug:
    """Test cases for cluster_instance_type_for_hot_plug function"""

    @patch("utilities.ssp.VirtualMachineClusterInstancetype")
    def test_cluster_instance_type_for_hot_plug_success(self, mock_instance_type_class):
        """Test successful creation of cluster instance type for hot plug"""
        mock_instance_type = MagicMock()
        mock_instance_type_class.return_value = mock_instance_type

        result = cluster_instance_type_for_hot_plug(guest_sockets=2, cpu_model="host-model")

        assert result == mock_instance_type
        mock_instance_type_class.assert_called_once()

    @patch("utilities.ssp.VirtualMachineClusterInstancetype")
    def test_cluster_instance_type_for_hot_plug_with_none_cpu_model(self, mock_instance_type_class):
        """Test cluster instance type creation with None CPU model"""
        mock_instance_type = MagicMock()
        mock_instance_type_class.return_value = mock_instance_type

        result = cluster_instance_type_for_hot_plug(guest_sockets=4, cpu_model=None)

        assert result == mock_instance_type
        mock_instance_type_class.assert_called_once()
