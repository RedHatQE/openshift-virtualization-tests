# Generated using Claude cli

"""Unit tests for oadp module"""

# flake8: noqa: E402
import sys
from re import escape
from shlex import quote
from unittest.mock import MagicMock, patch

import pexpect
import pytest

# Need to mock circular imports for oadp
import utilities

# mock must be before importing oadp to prevent circular import
mock_virt = MagicMock()
mock_infra = MagicMock()
sys.modules["utilities.virt"] = mock_virt
sys.modules["utilities.infra"] = mock_infra
utilities.virt = mock_virt
utilities.infra = mock_infra

# Import after setting up mocks to avoid circular dependency
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.exceptions import ResourceTeardownError

from utilities.constants import (
    ADP_NAMESPACE,
    LS_COMMAND,
    TIMEOUT_20SEC,
)
from utilities.oadp import (
    VeleroBackup,
    VeleroRestore,
    _velero_teardown,
    check_file_in_running_vm,
    create_rhel_vm,
    delete_velero_resource,
    is_storage_class_support_volume_mode,
)


class TestDeleteVeleroResource:
    """Test cases for delete_velero_resource function"""

    @pytest.mark.parametrize(
        ("kind", "name"),
        [
            ("Backup", "test-backup"),
            ("Restore", "test-restore"),
        ],
    )
    @patch("utilities.oadp.get_pod_by_name_prefix")
    @patch("utilities.oadp.LOGGER")
    def test_delete_velero_resource_success(self, mock_logger, mock_get_pod, kind, name):
        mock_client = MagicMock()
        mock_resource = MagicMock()
        mock_resource.kind = kind
        mock_resource.name = name

        mock_pod = MagicMock()
        mock_get_pod.return_value = mock_pod

        delete_velero_resource(resource=mock_resource, client=mock_client)

        mock_get_pod.assert_called_once_with(
            client=mock_client,
            pod_prefix="velero",
            namespace=ADP_NAMESPACE,
        )

        mock_pod.execute.assert_called_once_with(command=["./velero", "delete", kind.lower(), name, "--confirm"])
        expected_message = (
            f"Deleting Velero resource: kind={kind} name={name} command=./velero delete {kind.lower()} {name} --confirm"
        )
        mock_logger.info.assert_called_once_with(expected_message)

    @pytest.mark.parametrize(
        ("kind", "name"),
        [
            ("Backup", "test-backup"),
            ("Restore", "test-restore"),
        ],
    )
    @patch("utilities.oadp.get_pod_by_name_prefix")
    @patch("utilities.oadp.LOGGER")
    def test_delete_velero_resource_not_found_exception(self, mock_logger, mock_get_pod, kind, name):
        """Test delete_velero_resource when get_pod_by_name_prefix raises exception"""
        mock_client = MagicMock()
        mock_resource = MagicMock()
        mock_resource.kind = kind
        mock_resource.name = name

        # simulate get_pod_by_name_prefix raising an exception
        mock_get_pod.side_effect = ResourceNotFoundError("Velero resource not found")

        with pytest.raises(ResourceNotFoundError, match="Velero resource not found"):
            delete_velero_resource(resource=mock_resource, client=mock_client)

        # ensure exception logging is called
        mock_logger.error.assert_called_once()

        log_call = mock_logger.error.call_args
        log_message = log_call.args[0]
        expected_message = (
            f"Failed to delete Velero resource: kind={kind} "
            f"name={name} command=./velero delete {kind.lower()} {name} --confirm"
        )
        assert log_message == expected_message, "Unexpected delete_velero_resource error log message"


class TestVeleroTeardown:
    """Test cases for _velero_teardown function"""

    @patch("utilities.oadp.delete_velero_resource")
    def test_velero_teardown_with_teardown_true_calls_delete(self, mock_delete):
        mock_resource = MagicMock()
        mock_resource.teardown = True
        mock_resource.client = MagicMock()

        _velero_teardown(resource=mock_resource, exception_type=None, exception_value=None, traceback=None)

        mock_delete.assert_called_once_with(resource=mock_resource, client=mock_resource.client)

    @pytest.mark.parametrize(
        ("kind", "name"),
        [
            ("Backup", "test-backup"),
            ("Restore", "test-restore"),
        ],
    )
    @patch("utilities.oadp.LOGGER")
    @patch("utilities.oadp.delete_velero_resource")
    def test_velero_teardown_with_teardown_false_logs_and_no_delete(self, mock_delete, mock_logger, kind, name):
        mock_resource = MagicMock()
        mock_resource.teardown = False
        mock_resource.kind = kind
        mock_resource.name = name

        _velero_teardown(resource=mock_resource, exception_type=None, exception_value=None, traceback=None)

        mock_delete.assert_not_called()

        mock_logger.info.assert_called_once()
        log_call = mock_logger.info.call_args
        log_message = log_call.args[0]

        expected_message = f"Skipping Velero delete: kind={kind} name={name} teardown=False"

        assert log_message == expected_message, "Unexpected _velero_teardown skip log message"

    @patch("utilities.oadp.delete_velero_resource")
    def test_velero_teardown_raises_resource_teardown_error_when_delete_fails(self, mock_delete):
        mock_resource = MagicMock()
        mock_resource.teardown = True
        mock_resource.client = MagicMock()

        mock_delete.side_effect = Exception("delete failed")

        with pytest.raises(ResourceTeardownError):
            _velero_teardown(resource=mock_resource, exception_type=None, exception_value=None, traceback=None)

        mock_delete.assert_called_once_with(resource=mock_resource, client=mock_resource.client)


class TestVeleroBackup:
    """Test cases for VeleroBackup class"""

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Backup.__init__")
    def test_velero_backup_init(self, mock_backup_init, mock_unique_name):
        """Test VeleroBackup constructor with various parameters"""
        mock_backup_init.return_value = None
        mock_unique_name.return_value = "test-backup-unique"
        mock_client = MagicMock()

        backup = VeleroBackup(
            name="test-backup",
            namespace="test-namespace",
            included_namespaces=["ns1", "ns2"],
            client=mock_client,
            teardown=True,
            excluded_resources=["secrets"],
            wait_complete=True,
            snapshot_move_data=True,
            storage_location="default",
            timeout=600,
        )

        mock_unique_name.assert_called_once_with(name="test-backup")
        mock_backup_init.assert_called_once_with(
            name="test-backup-unique",
            namespace="test-namespace",
            included_namespaces=["ns1", "ns2"],
            client=mock_client,
            teardown=True,
            yaml_file=None,
            excluded_resources=["secrets"],
            storage_location="default",
            snapshot_move_data=True,
        )
        assert backup.wait_complete, "wait_complete should default to True"
        assert backup.timeout == 600, "Expected timeout to be 600 seconds when provided"

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Backup.__init__")
    def test_velero_backup_init_defaults(self, mock_backup_init, mock_unique_name):
        """Test VeleroBackup constructor with default parameters"""
        mock_backup_init.return_value = None
        mock_unique_name.return_value = "test-backup-unique"
        mock_client = MagicMock()

        backup = VeleroBackup(name="test-backup", client=mock_client)

        mock_unique_name.assert_called_once_with(name="test-backup")
        assert backup.wait_complete, "wait_complete should default to True"
        assert backup.timeout == 300, "Expected timeout to be 300 seconds when provided"  # TIMEOUT_5MIN

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Backup.__init__")
    @patch("utilities.oadp.Backup.__enter__")
    def test_velero_backup_enter_with_wait_complete(self, mock_backup_enter, mock_backup_init, mock_unique_name):
        """Test VeleroBackup __enter__ waits for completion when wait_complete=True"""
        mock_backup_init.return_value = None
        mock_unique_name.return_value = "test-backup-unique"
        mock_client = MagicMock()

        backup = VeleroBackup(name="test-backup", client=mock_client, wait_complete=True)
        backup.wait_for_status = MagicMock()
        backup.Status = MagicMock()
        backup.Status.COMPLETED = "Completed"
        mock_backup_enter.return_value = backup

        result = backup.__enter__()

        mock_backup_enter.assert_called_once()
        backup.wait_for_status.assert_called_once_with(status="Completed", timeout=300)
        assert result == backup, "Expected __enter__ to return the backup instance"

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Backup.__init__")
    @patch("utilities.oadp.Backup.__enter__")
    def test_velero_backup_enter_without_wait_complete(self, mock_backup_enter, mock_backup_init, mock_unique_name):
        """Test VeleroBackup __enter__ skips wait when wait_complete=False"""
        mock_backup_init.return_value = None
        mock_unique_name.return_value = "test-backup-unique"
        mock_client = MagicMock()

        backup = VeleroBackup(name="test-backup", client=mock_client, wait_complete=False)
        backup.wait_for_status = MagicMock()
        mock_backup_enter.return_value = backup

        result = backup.__enter__()

        mock_backup_enter.assert_called_once()
        backup.wait_for_status.assert_not_called()
        assert result == backup, "Expected __enter__ to return the backup instance"

    @patch("utilities.oadp._velero_teardown")
    @patch("utilities.oadp.Backup.__exit__")
    @patch("utilities.oadp.Backup.__init__")
    def test_velero_backup_exit_calls_teardown_and_super(self, mock_backup_init, mock_backup_exit, mock_teardown):
        mock_backup_init.return_value = None

        backup = VeleroBackup(name="test-backup", client=MagicMock(), teardown=True)

        backup.__exit__(None, None, None)

        # 1. Ensure _velero_teardown was called
        mock_teardown.assert_called_once_with(
            resource=backup,
            exception_type=None,
            exception_value=None,
            traceback=None,
        )

        # 2. Ensure super().__exit__ was called
        mock_backup_exit.assert_called_once_with(None, None, None)


class TestCreateRhelVm:
    """Test cases for create_rhel_vm context manager"""

    @patch("utilities.oadp.cleanup_artifactory_secret_and_config_map")
    @patch("utilities.oadp.running_vm")
    @patch("utilities.oadp.VirtualMachineForTests")
    @patch("utilities.oadp.DataVolume")
    @patch("utilities.oadp.get_http_image_url")
    @patch("utilities.oadp.get_artifactory_config_map")
    @patch("utilities.oadp.get_artifactory_secret")
    def test_create_rhel_vm_success_with_wait(
        self,
        mock_get_secret,
        mock_get_config_map,
        mock_get_url,
        mock_dv_class,
        mock_vm_class,
        mock_running_vm,
        mock_cleanup,
    ):
        """Test create_rhel_vm creates VM and waits for running"""
        mock_client = MagicMock()
        mock_secret = MagicMock()
        mock_config_map = MagicMock()
        mock_config_map.name = "artifactory-cert"
        mock_get_secret.return_value = mock_secret
        mock_get_config_map.return_value = mock_config_map
        mock_get_url.return_value = "http://example.com/rhel-9.6.qcow2"

        mock_dv = MagicMock()
        mock_dv.res = {
            "metadata": {"name": "test-dv", "namespace": "test-namespace"},
            "spec": {"source": "http"},
        }
        mock_dv_class.return_value = mock_dv

        mock_vm = MagicMock()
        mock_vm.__enter__ = MagicMock(return_value=mock_vm)
        mock_vm.__exit__ = MagicMock(return_value=None)
        mock_vm_class.return_value = mock_vm

        with create_rhel_vm(
            storage_class="ocs-storagecluster-ceph-rbd",
            namespace="test-namespace",
            dv_name="test-dv",
            vm_name="test-vm",
            rhel_image="rhel-9.6.qcow2",
            client=mock_client,
            wait_running=True,
        ) as vm:
            assert vm == mock_vm

        mock_get_secret.assert_called_once_with(namespace="test-namespace")
        mock_get_config_map.assert_called_once_with(namespace="test-namespace")
        mock_get_url.assert_called_once()
        mock_dv.to_dict.assert_called_once()
        mock_running_vm.assert_called_once_with(vm=mock_vm, wait_for_interfaces=True)
        mock_cleanup.assert_called_once_with(artifactory_secret=mock_secret, artifactory_config_map=mock_config_map)

    @patch("utilities.oadp.cleanup_artifactory_secret_and_config_map")
    @patch("utilities.oadp.running_vm")
    @patch("utilities.oadp.VirtualMachineForTests")
    @patch("utilities.oadp.DataVolume")
    @patch("utilities.oadp.get_http_image_url")
    @patch("utilities.oadp.get_artifactory_config_map")
    @patch("utilities.oadp.get_artifactory_secret")
    def test_create_rhel_vm_success_without_wait(
        self,
        mock_get_secret,
        mock_get_config_map,
        mock_get_url,
        mock_dv_class,
        mock_vm_class,
        mock_running_vm,
        mock_cleanup,
    ):
        """Test create_rhel_vm creates VM without waiting for running"""
        mock_client = MagicMock()
        mock_secret = MagicMock()
        mock_config_map = MagicMock()
        mock_config_map.name = "artifactory-cert"
        mock_get_secret.return_value = mock_secret
        mock_get_config_map.return_value = mock_config_map
        mock_get_url.return_value = "http://example.com/rhel-9.6.qcow2"

        mock_dv = MagicMock()
        mock_dv.res = {
            "metadata": {"name": "test-dv", "namespace": "test-namespace"},
            "spec": {"source": "http"},
        }
        mock_dv_class.return_value = mock_dv

        mock_vm = MagicMock()
        mock_vm.__enter__ = MagicMock(return_value=mock_vm)
        mock_vm.__exit__ = MagicMock(return_value=None)
        mock_vm_class.return_value = mock_vm

        with create_rhel_vm(
            storage_class="ocs-storagecluster-ceph-rbd",
            namespace="test-namespace",
            dv_name="test-dv",
            vm_name="test-vm",
            rhel_image="rhel-9.6.qcow2",
            client=mock_client,
            wait_running=False,
        ) as vm:
            assert vm == mock_vm

        mock_running_vm.assert_not_called()
        mock_cleanup.assert_called_once_with(artifactory_secret=mock_secret, artifactory_config_map=mock_config_map)

    @patch("utilities.oadp.cleanup_artifactory_secret_and_config_map")
    @patch("utilities.oadp.running_vm")
    @patch("utilities.oadp.VirtualMachineForTests")
    @patch("utilities.oadp.DataVolume")
    @patch("utilities.oadp.get_http_image_url")
    @patch("utilities.oadp.get_artifactory_config_map")
    @patch("utilities.oadp.get_artifactory_secret")
    def test_create_rhel_vm_with_volume_mode(
        self,
        mock_get_secret,
        mock_get_config_map,
        mock_get_url,
        mock_dv_class,
        mock_vm_class,
        mock_running_vm,
        mock_cleanup,
    ):
        """Test create_rhel_vm with volume_mode parameter"""
        mock_client = MagicMock()
        mock_secret = MagicMock()
        mock_config_map = MagicMock()
        mock_config_map.name = "artifactory-cert"
        mock_get_secret.return_value = mock_secret
        mock_get_config_map.return_value = mock_config_map
        mock_get_url.return_value = "http://example.com/rhel-9.6.qcow2"

        mock_dv = MagicMock()
        mock_dv.res = {
            "metadata": {"name": "test-dv", "namespace": "test-namespace"},
            "spec": {"source": "http"},
        }
        mock_dv_class.return_value = mock_dv

        mock_vm = MagicMock()
        mock_vm.__enter__ = MagicMock(return_value=mock_vm)
        mock_vm.__exit__ = MagicMock(return_value=None)
        mock_vm_class.return_value = mock_vm

        with create_rhel_vm(
            storage_class="ocs-storagecluster-ceph-rbd",
            namespace="test-namespace",
            dv_name="test-dv",
            vm_name="test-vm",
            rhel_image="rhel-9.6.qcow2",
            client=mock_client,
            wait_running=True,
            volume_mode="Block",
        ) as vm:
            assert vm == mock_vm

        # Verify DataVolume was created with volume_mode
        assert mock_dv_class.call_args.kwargs["volume_mode"] == "Block"
        mock_cleanup.assert_called_once_with(artifactory_secret=mock_secret, artifactory_config_map=mock_config_map)

    @patch("utilities.oadp.cleanup_artifactory_secret_and_config_map")
    @patch("utilities.oadp.running_vm")
    @patch("utilities.oadp.VirtualMachineForTests")
    @patch("utilities.oadp.DataVolume")
    @patch("utilities.oadp.get_http_image_url")
    @patch("utilities.oadp.get_artifactory_config_map")
    @patch("utilities.oadp.get_artifactory_secret")
    def test_create_rhel_vm_cleanup_on_exception(
        self,
        mock_get_secret,
        mock_get_config_map,
        mock_get_url,
        mock_dv_class,
        mock_vm_class,
        mock_running_vm,
        mock_cleanup,
    ):
        """Test create_rhel_vm cleanup happens on exception"""
        mock_client = MagicMock()
        mock_secret = MagicMock()
        mock_config_map = MagicMock()
        mock_config_map.name = "artifactory-cert"
        mock_get_secret.return_value = mock_secret
        mock_get_config_map.return_value = mock_config_map
        mock_get_url.return_value = "http://example.com/rhel-9.6.qcow2"

        mock_dv = MagicMock()
        mock_dv.res = {
            "metadata": {"name": "test-dv", "namespace": "test-namespace"},
            "spec": {"source": "http"},
        }
        mock_dv_class.return_value = mock_dv

        # Make VirtualMachineForTests raise exception on enter
        mock_vm_class.return_value.__enter__.side_effect = Exception("VM creation failed")

        with pytest.raises(Exception, match="VM creation failed"):
            with create_rhel_vm(
                storage_class="ocs-storagecluster-ceph-rbd",
                namespace="test-namespace",
                dv_name="test-dv",
                vm_name="test-vm",
                rhel_image="rhel-9.6.qcow2",
                client=mock_client,
                wait_running=True,
            ):
                pass

        # Cleanup should still be called
        mock_cleanup.assert_called_once_with(artifactory_secret=mock_secret, artifactory_config_map=mock_config_map)

    @patch("utilities.oadp.cleanup_artifactory_secret_and_config_map")
    @patch("utilities.oadp.running_vm")
    @patch("utilities.oadp.VirtualMachineForTests")
    @patch("utilities.oadp.DataVolume")
    @patch("utilities.oadp.get_http_image_url")
    @patch("utilities.oadp.get_artifactory_config_map")
    @patch("utilities.oadp.get_artifactory_secret")
    def test_create_rhel_vm_cleanup_on_success(
        self,
        mock_get_secret,
        mock_get_config_map,
        mock_get_url,
        mock_dv_class,
        mock_vm_class,
        mock_running_vm,
        mock_cleanup,
    ):
        """Test create_rhel_vm cleanup happens on successful completion"""
        mock_client = MagicMock()
        mock_secret = MagicMock()
        mock_config_map = MagicMock()
        mock_config_map.name = "artifactory-cert"
        mock_get_secret.return_value = mock_secret
        mock_get_config_map.return_value = mock_config_map
        mock_get_url.return_value = "http://example.com/rhel-9.6.qcow2"

        mock_dv = MagicMock()
        mock_dv.res = {
            "metadata": {"name": "test-dv", "namespace": "test-namespace"},
            "spec": {"source": "http"},
        }
        mock_dv_class.return_value = mock_dv

        mock_vm = MagicMock()
        mock_vm.__enter__ = MagicMock(return_value=mock_vm)
        mock_vm.__exit__ = MagicMock(return_value=None)
        mock_vm_class.return_value = mock_vm

        with create_rhel_vm(
            storage_class="ocs-storagecluster-ceph-rbd",
            namespace="test-namespace",
            dv_name="test-dv",
            vm_name="test-vm",
            rhel_image="rhel-9.6.qcow2",
            client=mock_client,
            wait_running=True,
        ):
            pass

        # Cleanup should be called
        mock_cleanup.assert_called_once_with(artifactory_secret=mock_secret, artifactory_config_map=mock_config_map)

    @patch("utilities.oadp.cleanup_artifactory_secret_and_config_map")
    @patch("utilities.oadp.running_vm")
    @patch("utilities.oadp.VirtualMachineForTests")
    @patch("utilities.oadp.DataVolume")
    @patch("utilities.oadp.get_http_image_url")
    @patch("utilities.oadp.get_artifactory_config_map")
    @patch("utilities.oadp.get_artifactory_secret")
    def test_create_rhel_vm_running_vm_exception(
        self,
        mock_get_secret,
        mock_get_config_map,
        mock_get_url,
        mock_dv_class,
        mock_vm_class,
        mock_running_vm,
        mock_cleanup,
    ):
        """Test create_rhel_vm handles running_vm exception and still cleans up"""
        mock_client = MagicMock()
        mock_secret = MagicMock()
        mock_config_map = MagicMock()
        mock_config_map.name = "artifactory-cert"
        mock_get_secret.return_value = mock_secret
        mock_get_config_map.return_value = mock_config_map
        mock_get_url.return_value = "http://example.com/rhel-9.6.qcow2"

        mock_dv = MagicMock()
        mock_dv.res = {
            "metadata": {"name": "test-dv", "namespace": "test-namespace"},
            "spec": {"source": "http"},
        }
        mock_dv_class.return_value = mock_dv

        mock_vm = MagicMock()
        mock_vm.__enter__ = MagicMock(return_value=mock_vm)
        mock_vm.__exit__ = MagicMock(return_value=None)
        mock_vm_class.return_value = mock_vm

        mock_running_vm.side_effect = Exception("VM failed to start")

        with pytest.raises(Exception, match="VM failed to start"):
            with create_rhel_vm(
                storage_class="ocs-storagecluster-ceph-rbd",
                namespace="test-namespace",
                dv_name="test-dv",
                vm_name="test-vm",
                rhel_image="rhel-9.6.qcow2",
                client=mock_client,
                wait_running=True,
            ):
                pass

        # Cleanup should still be called
        mock_cleanup.assert_called_once_with(artifactory_secret=mock_secret, artifactory_config_map=mock_config_map)


class TestVeleroRestore:
    """Test cases for VeleroRestore class"""

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Restore.__init__")
    def test_velero_restore_init(self, mock_restore_init, mock_unique_name):
        mock_restore_init.return_value = None
        mock_unique_name.return_value = "test-restore-unique"
        mock_client = MagicMock()

        restore = VeleroRestore(
            name="test-restore",
            namespace="test-namespace",
            included_namespaces=["ns1"],
            backup_name="backup-1",
            client=mock_client,
            teardown=True,
            wait_complete=True,
            timeout=600,
        )

        mock_unique_name.assert_called_once_with(name="test-restore")
        mock_restore_init.assert_called_once_with(
            name="test-restore-unique",
            namespace="test-namespace",
            included_namespaces=["ns1"],
            backup_name="backup-1",
            client=mock_client,
            teardown=True,
        )

        assert restore.wait_complete, "wait_complete should default to True"
        assert restore.timeout == 600, "Expected timeout to be 600 seconds when provided"

    @patch("utilities.oadp.Restore.__init__")
    @patch("utilities.oadp.Restore.__enter__")
    def test_velero_restore_enter_with_wait_complete(self, mock_restore_enter, mock_restore_init):
        mock_restore_init.return_value = None

        restore = VeleroRestore(name="test-restore", client=MagicMock(), wait_complete=True)
        restore.wait_for_status = MagicMock()
        restore.Status = MagicMock()
        restore.Status.COMPLETED = "Completed"

        mock_restore_enter.return_value = restore

        result = restore.__enter__()

        mock_restore_enter.assert_called_once()
        restore.wait_for_status.assert_called_once_with(status="Completed", timeout=300)
        assert result == restore, "Expected __enter__ to return the restore instance"

    @patch("utilities.oadp.Restore.__init__")
    @patch("utilities.oadp.Restore.__enter__")
    def test_velero_restore_enter_without_wait_complete(self, mock_restore_enter, mock_restore_init):
        mock_restore_init.return_value = None

        restore = VeleroRestore(name="test-restore", client=MagicMock(), wait_complete=False)
        restore.wait_for_status = MagicMock()

        mock_restore_enter.return_value = restore

        restore.__enter__()

        restore.wait_for_status.assert_not_called()

    @patch("utilities.oadp._velero_teardown")
    @patch("utilities.oadp.Restore.__exit__")
    @patch("utilities.oadp.Restore.__init__")
    def test_velero_restore_exit_calls_teardown_and_super(self, mock_restore_init, mock_restore_exit, mock_teardown):
        mock_restore_init.return_value = None

        restore = VeleroRestore(name="test-restore", client=MagicMock(), teardown=True)

        restore.__exit__(None, None, None)

        # 1. Ensure _velero_teardown was called
        mock_teardown.assert_called_once_with(
            resource=restore,
            exception_type=None,
            exception_value=None,
            traceback=None,
        )

        # 2. Ensure super().__exit__ was called
        mock_restore_exit.assert_called_once_with(None, None, None)


class TestCheckFileInRunningVm:
    """Test cases for check_file_in_running_vm function that verifies file existence and content in a running VM."""

    @patch("utilities.oadp.Console")
    def test_check_file_in_running_vm(self, mock_console_cls):
        mock_vm = MagicMock()
        mock_vm.ready = True

        mock_console = MagicMock()
        mock_console_cls.return_value.__enter__.return_value = mock_console

        check_file_in_running_vm(
            vm=mock_vm,
            file_name="test-file",
            file_content="hello world",
        )

        mock_vm.start.assert_not_called()

        mock_console.sendline.assert_any_call(LS_COMMAND)
        mock_console.expect.assert_any_call(pattern=escape("test-file"), timeout=TIMEOUT_20SEC)
        mock_console.sendline.assert_any_call(f"cat {quote('test-file')}")
        mock_console.expect.assert_any_call(pattern=escape("hello world"), timeout=TIMEOUT_20SEC)

    @patch("utilities.oadp.Console")
    def test_check_file_in_running_vm_file_not_found(self, mock_console_cls):
        mock_vm = MagicMock()
        mock_vm.ready = True

        mock_console = MagicMock()
        mock_console.expect.side_effect = pexpect.TIMEOUT("file not found")
        mock_console_cls.return_value.__enter__.return_value = mock_console

        with pytest.raises(pexpect.TIMEOUT):
            check_file_in_running_vm(
                vm=mock_vm,
                file_name="missing-file",
                file_content="hello world",
            )

    @patch("utilities.oadp.Console")
    def test_check_file_in_running_vm_content_mismatch(self, mock_console_cls):
        mock_vm = MagicMock()
        mock_vm.ready = True

        mock_console = MagicMock()
        mock_console.sendline.side_effect = [
            None,  # ls
            None,  # cat
        ]
        mock_console.expect.side_effect = [
            None,  # find file
            Exception("content mismatch"),
        ]

        mock_console_cls.return_value.__enter__.return_value = mock_console

        with pytest.raises(Exception, match="content mismatch"):
            check_file_in_running_vm(
                vm=mock_vm,
                file_name="test-file",
                file_content="expected content",
            )


class TestIsStorageClassSupportVolumeMode:
    """Test cases for is_storage_class_support_volume_mode function that checks StorageProfile volume mode support."""

    @patch("utilities.oadp.StorageProfile")
    def test_volume_mode_supported(self, mock_profile):
        admin_client = MagicMock()
        mock_profile.return_value.claim_property_sets = [
            MagicMock(volumeMode="Filesystem"),
            MagicMock(volumeMode="Block"),
        ]

        assert is_storage_class_support_volume_mode(
            admin_client=admin_client, storage_class_name="sc-name", requested_volume_mode="Block"
        ), "Expected Block volume mode to be supported"

    @patch("utilities.oadp.StorageProfile")
    def test_volume_mode_not_supported(self, mock_profile):
        admin_client = MagicMock()
        mock_profile.return_value.claim_property_sets = [
            MagicMock(volumeMode="Filesystem"),
        ]

        assert not is_storage_class_support_volume_mode(
            admin_client=admin_client, storage_class_name="sc-name", requested_volume_mode="Block"
        ), "Expected Block volume mode to be unsupported"

    @pytest.mark.parametrize(
        "claim_property_sets",
        [
            None,
            [],
        ],
    )
    @patch("utilities.oadp.StorageProfile")
    def test_volume_mode_no_claim_property_sets(self, mock_profile, claim_property_sets):
        admin_client = MagicMock()
        mock_profile.return_value.claim_property_sets = claim_property_sets

        assert not is_storage_class_support_volume_mode(
            admin_client=admin_client, storage_class_name="sc-name", requested_volume_mode="Block"
        ), "Expected Block volume mode to be unsupported when claim_property_sets is empty"