# Generated using Claude cli

"""Unit tests for oadp module"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Need to mock circular imports for oadp
import utilities

mock_virt = MagicMock()
mock_infra = MagicMock()
sys.modules["utilities.virt"] = mock_virt
sys.modules["utilities.infra"] = mock_infra
utilities.virt = mock_virt
utilities.infra = mock_infra

# Import after setting up mocks to avoid circular dependency
from utilities.oadp import (  # noqa: E402
    VeleroBackup,
    create_rhel_vm,
    delete_velero_resource,
)


class TestDeleteVeleroResource:
    """Test cases for delete_velero_resource function"""

    @patch("utilities.oadp.get_pod_by_name_prefix")
    def test_delete_velero_resource_success(self, mock_get_pod):
        """Test successful deletion of Velero resource"""
        mock_client = MagicMock()
        mock_resource = MagicMock()
        mock_resource.kind = "Backup"
        mock_resource.name = "test-backup"

        mock_pod = MagicMock()
        mock_pod.execute = MagicMock()
        mock_get_pod.return_value = mock_pod

        delete_velero_resource(resource=mock_resource, client=mock_client)

        mock_get_pod.assert_called_once_with(dyn_client=mock_client, pod_prefix="velero", namespace="openshift-adp")
        mock_pod.execute.assert_called_once_with(command=["./velero", "delete", "backup", "test-backup", "--confirm"])

    @patch("utilities.oadp.get_pod_by_name_prefix")
    def test_delete_velero_resource_restore(self, mock_get_pod):
        """Test successful deletion of Velero restore resource"""
        mock_client = MagicMock()
        mock_resource = MagicMock()
        mock_resource.kind = "Restore"
        mock_resource.name = "test-restore"

        mock_pod = MagicMock()
        mock_pod.execute = MagicMock()
        mock_get_pod.return_value = mock_pod

        delete_velero_resource(resource=mock_resource, client=mock_client)

        mock_get_pod.assert_called_once_with(dyn_client=mock_client, pod_prefix="velero", namespace="openshift-adp")
        mock_pod.execute.assert_called_once_with(command=["./velero", "delete", "restore", "test-restore", "--confirm"])

    @patch("utilities.oadp.get_pod_by_name_prefix")
    def test_delete_velero_resource_pod_not_found(self, mock_get_pod):
        """Test delete_velero_resource when velero pod is not found"""
        mock_client = MagicMock()
        mock_resource = MagicMock()
        mock_resource.kind = "Backup"
        mock_resource.name = "test-backup"

        mock_get_pod.return_value = None

        with pytest.raises(AttributeError):
            delete_velero_resource(resource=mock_resource, client=mock_client)

    @patch("utilities.oadp.get_pod_by_name_prefix")
    def test_delete_velero_resource_pod_exception(self, mock_get_pod):
        """Test delete_velero_resource when getting pod raises exception"""
        mock_client = MagicMock()
        mock_resource = MagicMock()
        mock_resource.kind = "Backup"
        mock_resource.name = "test-backup"

        mock_get_pod.side_effect = Exception("Pod not found")

        with pytest.raises(Exception, match="Pod not found"):
            delete_velero_resource(resource=mock_resource, client=mock_client)


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
        assert backup.wait_complete is True
        assert backup.timeout == 600

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Backup.__init__")
    def test_velero_backup_init_defaults(self, mock_backup_init, mock_unique_name):
        """Test VeleroBackup constructor with default parameters"""
        mock_backup_init.return_value = None
        mock_unique_name.return_value = "test-backup-unique"
        mock_client = MagicMock()

        backup = VeleroBackup(name="test-backup", client=mock_client)

        mock_unique_name.assert_called_once_with(name="test-backup")
        assert backup.wait_complete is True
        assert backup.timeout == 300  # TIMEOUT_5MIN

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
        assert result == backup

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
        assert result == backup

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Backup.__init__")
    @patch("utilities.oadp.Backup.__exit__")
    @patch("utilities.oadp.delete_velero_resource")
    def test_velero_backup_exit_with_teardown(
        self, mock_delete_resource, mock_backup_exit, mock_backup_init, mock_unique_name
    ):
        """Test VeleroBackup __exit__ calls delete_velero_resource when teardown=True"""
        # Mock Backup.__init__ to not raise error and allow attribute setting
        mock_backup_init.return_value = None
        mock_unique_name.return_value = "test-backup-unique"
        mock_client = MagicMock()

        backup = VeleroBackup(name="test-backup", client=mock_client, teardown=True)
        # Manually set teardown since the mock doesn't do it
        backup.teardown = True
        backup.client = mock_client
        backup.kind = "Backup"
        backup.name = "test-backup-unique"

        backup.__exit__(None, None, None)

        mock_delete_resource.assert_called_once_with(resource=backup, client=mock_client)
        mock_backup_exit.assert_called_once_with(None, None, None)

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Backup.__init__")
    @patch("utilities.oadp.Backup.__exit__")
    @patch("utilities.oadp.delete_velero_resource")
    @patch("utilities.oadp.LOGGER")
    def test_velero_backup_exit_without_teardown(
        self, mock_logger, mock_delete_resource, mock_backup_exit, mock_backup_init, mock_unique_name
    ):
        """Test VeleroBackup __exit__ skips delete when teardown=False"""
        # Mock Backup.__init__ to not raise error and allow attribute setting
        mock_backup_init.return_value = None
        mock_unique_name.return_value = "test-backup-unique"
        mock_client = MagicMock()

        backup = VeleroBackup(name="test-backup", client=mock_client, teardown=False)
        # Manually set teardown since the mock doesn't do it
        backup.teardown = False
        backup.kind = "Backup"
        backup.name = "test-backup-unique"

        backup.__exit__(None, None, None)

        mock_delete_resource.assert_not_called()
        mock_logger.info.assert_called_once_with(
            "Skipping Velero delete for Backup test-backup-unique (teardown=False)"
        )
        mock_backup_exit.assert_called_once_with(None, None, None)

    @patch("utilities.oadp.unique_name")
    @patch("utilities.oadp.Backup.__init__")
    @patch("utilities.oadp.Backup.__exit__")
    @patch("utilities.oadp.delete_velero_resource")
    @patch("utilities.oadp.LOGGER")
    def test_velero_backup_exit_delete_exception(
        self, mock_logger, mock_delete_resource, mock_backup_exit, mock_backup_init, mock_unique_name
    ):
        """Test VeleroBackup __exit__ handles delete exception gracefully"""
        # Mock Backup.__init__ to not raise error and allow attribute setting
        mock_backup_init.return_value = None
        mock_unique_name.return_value = "test-backup-unique"
        mock_client = MagicMock()

        backup = VeleroBackup(name="test-backup", client=mock_client, teardown=True)
        # Manually set teardown since the mock doesn't do it
        backup.teardown = True
        backup.client = mock_client
        backup.kind = "Backup"
        backup.name = "test-backup-unique"

        mock_delete_resource.side_effect = Exception("Delete failed")

        # Should not raise exception
        backup.__exit__(None, None, None)

        mock_delete_resource.assert_called_once_with(resource=backup, client=mock_client)
        mock_logger.exception.assert_called_once_with("Failed to delete Velero Backup test-backup-unique")
        # Parent __exit__ should still be called
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
