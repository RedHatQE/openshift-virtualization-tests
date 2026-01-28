# Generated using Claude cli

"""Unit tests for hco module"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from timeout_sampler import TimeoutExpiredError

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock circular imports at module level to avoid circular dependencies
# conftest.py mocks utilities.hco, but we need the real module for these tests
import utilities

# First, set up mocks for hco.py's dependencies
# hco -> ssp -> storage -> virt -> console -> data_collector
mock_virt = MagicMock()
mock_storage = MagicMock()
mock_ssp = MagicMock()
# SSP needs these attributes for hco.py imports
mock_ssp.wait_for_ssp = MagicMock()
mock_ssp.validate_os_info_vmi_vs_windows_os = MagicMock()

sys.modules["utilities.virt"] = mock_virt
sys.modules["utilities.storage"] = mock_storage
sys.modules["utilities.ssp"] = mock_ssp
utilities.virt = mock_virt
utilities.storage = mock_storage
utilities.ssp = mock_ssp

# Remove the mock for utilities.hco from conftest.py so we can import the real module
if "utilities.hco" in sys.modules:
    del sys.modules["utilities.hco"]

# Import after setting up mocks to avoid circular dependency
from utilities.hco import (  # noqa: E402
    DEFAULT_HCO_PROGRESSING_CONDITIONS,
    HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT,
    ResourceEditorValidateHCOReconcile,
    add_labels_to_nodes,
    apply_np_changes,
    disable_common_boot_image_import_hco_spec,
    enable_common_boot_image_import_spec_wait_for_data_import_cron,
    enabled_aaq_in_hco,
    get_hco_namespace,
    get_hco_spec,
    get_hco_version,
    get_installed_hco_csv,
    get_json_patch_annotation_values,
    hco_cr_jsonpatch_annotations_dict,
    is_hco_tainted,
    update_common_boot_image_import_spec,
    update_hco_annotations,
    update_hco_templates_spec,
    wait_for_auto_boot_config_stabilization,
    wait_for_dp,
    wait_for_ds,
    wait_for_hco_conditions,
    wait_for_hco_post_update_stable_state,
    wait_for_hco_version,
)


class TestGetHcoNamespace:
    """Test cases for get_hco_namespace function"""

    @patch("utilities.hco.Namespace")
    def test_get_hco_namespace_exists(self, mock_namespace_class):
        """Test get_hco_namespace when namespace exists"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.exists = True
        mock_namespace_class.return_value = mock_namespace

        result = get_hco_namespace(mock_admin_client, namespace="openshift-cnv")

        assert result == mock_namespace
        mock_namespace_class.assert_called_once_with(client=mock_admin_client, name="openshift-cnv")

    @patch("utilities.hco.Namespace")
    def test_get_hco_namespace_not_exists(self, mock_namespace_class):
        """Test get_hco_namespace when namespace does not exist"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.exists = False
        mock_namespace_class.return_value = mock_namespace

        with pytest.raises(ResourceNotFoundError, match="Namespace: openshift-cnv not found"):
            get_hco_namespace(mock_admin_client, namespace="openshift-cnv")

    @patch("utilities.hco.Namespace")
    def test_get_hco_namespace_custom_namespace(self, mock_namespace_class):
        """Test get_hco_namespace with custom namespace"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.exists = True
        mock_namespace_class.return_value = mock_namespace

        result = get_hco_namespace(mock_admin_client, namespace="custom-cnv")

        assert result == mock_namespace
        mock_namespace_class.assert_called_once_with(client=mock_admin_client, name="custom-cnv")


class TestGetJsonPatchAnnotationValues:
    """Test cases for get_json_patch_annotation_values function"""

    def test_get_json_patch_annotation_values_kubevirt(self):
        """Test get_json_patch_annotation_values for kubevirt component"""
        result = get_json_patch_annotation_values(
            component="kubevirt", path="machineType", value="pc-q35-rhel8.4.0", op="add"
        )

        expected_key = "kubevirt.kubevirt.io/jsonpatch"
        expected_value = json.dumps([
            {"op": "add", "path": "/spec/configuration/machineType", "value": "pc-q35-rhel8.4.0"}
        ])

        assert expected_key in result
        assert result[expected_key] == expected_value

    def test_get_json_patch_annotation_values_cdi(self):
        """Test get_json_patch_annotation_values for cdi component"""
        result = get_json_patch_annotation_values(
            component="cdi", path="scratchSpaceStorageClass", value="local", op="add"
        )

        expected_key = "containerizeddataimporter.kubevirt.io/jsonpatch"
        expected_value = json.dumps([{"op": "add", "path": "/spec/config/scratchSpaceStorageClass", "value": "local"}])

        assert expected_key in result
        assert result[expected_key] == expected_value

    def test_get_json_patch_annotation_values_cnao(self):
        """Test get_json_patch_annotation_values for cnao component"""
        result = get_json_patch_annotation_values(component="cnao", path="linuxBridge", value={}, op="add")

        expected_key = "networkaddonsconfigs.kubevirt.io/jsonpatch"
        expected_value = json.dumps([{"op": "add", "path": "/spec/linuxBridge", "value": {}}])

        assert expected_key in result
        assert result[expected_key] == expected_value

    def test_get_json_patch_annotation_values_ssp(self):
        """Test get_json_patch_annotation_values for ssp component"""
        result = get_json_patch_annotation_values(component="ssp", path="commonTemplates", value=[], op="add")

        expected_key = "ssp.kubevirt.io/jsonpatch"
        expected_value = json.dumps([{"op": "add", "path": "/spec/commonTemplates", "value": []}])

        assert expected_key in result
        assert result[expected_key] == expected_value

    def test_get_json_patch_annotation_values_remove_operation(self):
        """Test get_json_patch_annotation_values with remove operation"""
        result = get_json_patch_annotation_values(component="kubevirt", path="cpuModel", value=None, op="remove")

        expected_value = json.dumps([{"op": "remove", "path": "/spec/configuration/cpuModel", "value": None}])
        assert result["kubevirt.kubevirt.io/jsonpatch"] == expected_value


class TestHcoCrJsonpatchAnnotationsDict:
    """Test cases for hco_cr_jsonpatch_annotations_dict function"""

    def test_hco_cr_jsonpatch_annotations_dict_basic(self):
        """Test hco_cr_jsonpatch_annotations_dict returns correct structure"""
        result = hco_cr_jsonpatch_annotations_dict(component="kubevirt", path="cpuModel", value="Haswell", op="add")

        assert "metadata" in result
        assert "annotations" in result["metadata"]
        assert "kubevirt.kubevirt.io/jsonpatch" in result["metadata"]["annotations"]

    def test_hco_cr_jsonpatch_annotations_dict_with_cdi(self):
        """Test hco_cr_jsonpatch_annotations_dict for CDI component"""
        result = hco_cr_jsonpatch_annotations_dict(
            component="cdi", path="uploadProxyURLOverride", value="https://example.com", op="add"
        )

        expected_key = "containerizeddataimporter.kubevirt.io/jsonpatch"
        assert expected_key in result["metadata"]["annotations"]


class TestIsHcoTainted:
    """Test cases for is_hco_tainted function"""

    @patch("utilities.hco.utilities.infra.get_hyperconverged_resource")
    def test_is_hco_tainted_true(self, mock_get_hco):
        """Test is_hco_tainted when HCO is tainted"""
        mock_admin_client = MagicMock()
        mock_hco = MagicMock()
        mock_hco.instance.status.conditions = [
            {"type": "Available", "status": "True"},
            {"type": "TaintedConfiguration", "status": "True", "message": "Configuration is tainted"},
        ]
        mock_get_hco.return_value = mock_hco

        result = is_hco_tainted(mock_admin_client, "openshift-cnv")

        assert len(result) == 1
        assert result[0]["type"] == "TaintedConfiguration"

    @patch("utilities.hco.utilities.infra.get_hyperconverged_resource")
    def test_is_hco_tainted_false(self, mock_get_hco):
        """Test is_hco_tainted when HCO is not tainted"""
        mock_admin_client = MagicMock()
        mock_hco = MagicMock()
        mock_hco.instance.status.conditions = [
            {"type": "Available", "status": "True"},
            {"type": "Progressing", "status": "False"},
        ]
        mock_get_hco.return_value = mock_hco

        result = is_hco_tainted(mock_admin_client, "openshift-cnv")

        assert len(result) == 0


class TestGetHcoSpec:
    """Test cases for get_hco_spec function"""

    @patch("utilities.hco.utilities.infra.get_hyperconverged_resource")
    @patch("utilities.hco.Namespace")
    def test_get_hco_spec_success(self, mock_namespace_class, mock_get_hco):
        """Test get_hco_spec returns HCO spec"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"
        mock_namespace_class.return_value = mock_namespace

        mock_hco = MagicMock()
        mock_hco.instance.to_dict.return_value = {
            "spec": {"infra": {}, "workloads": {}, "featureGates": {"enableCommonBootImageImport": True}}
        }
        mock_get_hco.return_value = mock_hco

        result = get_hco_spec(mock_admin_client, mock_namespace)

        assert "infra" in result
        assert "workloads" in result
        assert "featureGates" in result
        mock_get_hco.assert_called_once_with(client=mock_admin_client, hco_ns_name="openshift-cnv")


class TestGetInstalledHcoCsv:
    """Test cases for get_installed_hco_csv function"""

    @patch("utilities.hco.utilities.infra.get_csv_by_name")
    @patch("utilities.hco.utilities.infra.get_subscription")
    @patch("utilities.hco.py_config", {"hco_subscription": "kubevirt-hyperconverged"})
    @patch("utilities.hco.Namespace")
    def test_get_installed_hco_csv_success(self, mock_namespace_class, mock_get_subscription, mock_get_csv):
        """Test get_installed_hco_csv returns CSV successfully"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"
        mock_namespace_class.return_value = mock_namespace

        mock_subscription = MagicMock()
        mock_subscription.instance.status.installedCSV = "kubevirt-hyperconverged-operator.v4.20.0"
        mock_get_subscription.return_value = mock_subscription

        mock_csv = MagicMock()
        mock_csv.name = "kubevirt-hyperconverged-operator.v4.20.0"
        mock_get_csv.return_value = mock_csv

        result = get_installed_hco_csv(mock_admin_client, mock_namespace)

        assert result == mock_csv
        mock_get_subscription.assert_called_once_with(
            admin_client=mock_admin_client, namespace="openshift-cnv", subscription_name="kubevirt-hyperconverged"
        )
        mock_get_csv.assert_called_once_with(
            csv_name="kubevirt-hyperconverged-operator.v4.20.0",
            admin_client=mock_admin_client,
            namespace="openshift-cnv",
        )

    @patch("utilities.hco.utilities.infra.get_csv_by_name")
    @patch("utilities.hco.utilities.infra.get_subscription")
    @patch("utilities.hco.py_config", {"hco_subscription": None})
    @patch("utilities.hco.Namespace")
    def test_get_installed_hco_csv_default_subscription_name(
        self, mock_namespace_class, mock_get_subscription, mock_get_csv
    ):
        """Test get_installed_hco_csv with default subscription name"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"

        mock_subscription = MagicMock()
        mock_subscription.instance.status.installedCSV = "kubevirt-hyperconverged-operator.v4.20.0"
        mock_get_subscription.return_value = mock_subscription

        mock_csv = MagicMock()
        mock_get_csv.return_value = mock_csv

        get_installed_hco_csv(mock_admin_client, mock_namespace)

        # Should use HCO_SUBSCRIPTION constant when py_config["hco_subscription"] is None
        mock_get_subscription.assert_called_once()


class TestGetHcoVersion:
    """Test cases for get_hco_version function"""

    @patch("utilities.hco.utilities.infra.get_hyperconverged_resource")
    def test_get_hco_version_success(self, mock_get_hco):
        """Test get_hco_version returns version string"""
        mock_client = MagicMock()
        mock_hco = MagicMock()
        mock_version_obj = MagicMock()
        mock_version_obj.version = "4.20.0"
        mock_hco.instance.status.versions = [mock_version_obj]
        mock_get_hco.return_value = mock_hco

        result = get_hco_version(mock_client, "openshift-cnv")

        assert result == "4.20.0"
        mock_get_hco.assert_called_once_with(client=mock_client, hco_ns_name="openshift-cnv")


class TestWaitForHcoVersion:
    """Test cases for wait_for_hco_version function"""

    @patch("utilities.hco.TimeoutSampler")
    @patch("utilities.hco.get_hco_version")
    def test_wait_for_hco_version_success(self, mock_get_version, mock_sampler):
        """Test wait_for_hco_version succeeds when version matches"""
        mock_client = MagicMock()
        mock_get_version.return_value = "4.20.0"

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter(["4.20.0"]))
        mock_sampler.return_value = mock_sampler_instance

        result = wait_for_hco_version(mock_client, "openshift-cnv", "4.20.0")

        assert result == "4.20.0"

    @patch("utilities.hco.TimeoutSampler")
    @patch("utilities.hco.get_hco_version")
    def test_wait_for_hco_version_timeout(self, mock_get_version, mock_sampler):
        """Test wait_for_hco_version raises timeout when version doesn't match"""
        mock_client = MagicMock()
        mock_get_version.return_value = "4.19.0"

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "4.19.0"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            wait_for_hco_version(mock_client, "openshift-cnv", "4.20.0")


class TestAddLabelsToNodes:
    """Test cases for add_labels_to_nodes function"""

    @patch("utilities.hco.ResourceEditor")
    def test_add_labels_to_nodes_single_node(self, mock_resource_editor_class):
        """Test add_labels_to_nodes with single node"""
        mock_node = MagicMock()
        mock_node.name = "worker-0"

        mock_editor = MagicMock()
        mock_resource_editor_class.return_value = mock_editor

        node_labels = {"cpumanager": "true"}
        result = add_labels_to_nodes([mock_node], node_labels)

        assert len(result) == 1
        assert mock_editor in result
        assert result[mock_editor]["node"] == "worker-0"
        assert result[mock_editor]["labels"] == {"cpumanager": "true1"}
        mock_editor.update.assert_called_once_with(backup_resources=True)

    @patch("utilities.hco.ResourceEditor")
    def test_add_labels_to_nodes_multiple_nodes(self, mock_resource_editor_class):
        """Test add_labels_to_nodes with multiple nodes"""
        mock_node1 = MagicMock()
        mock_node1.name = "worker-0"
        mock_node2 = MagicMock()
        mock_node2.name = "worker-1"
        mock_node3 = MagicMock()
        mock_node3.name = "worker-2"

        mock_editors = [MagicMock(), MagicMock(), MagicMock()]
        mock_resource_editor_class.side_effect = mock_editors

        node_labels = {"cpumanager": "true", "numa": "enabled"}
        result = add_labels_to_nodes([mock_node1, mock_node2, mock_node3], node_labels)

        assert len(result) == 3
        # Verify incrementing label values
        assert result[mock_editors[0]]["labels"] == {"cpumanager": "true1", "numa": "enabled1"}
        assert result[mock_editors[1]]["labels"] == {"cpumanager": "true2", "numa": "enabled2"}
        assert result[mock_editors[2]]["labels"] == {"cpumanager": "true3", "numa": "enabled3"}


class TestWaitForDs:
    """Test cases for wait_for_ds function"""

    @patch("utilities.hco.TimeoutSampler")
    def test_wait_for_ds_success(self, mock_sampler):
        """Test wait_for_ds succeeds when daemonset is up to date"""
        mock_ds = MagicMock()
        mock_ds.name = "test-daemonset"
        mock_ds.instance.to_dict.return_value = {
            "metadata": {"generation": 5},
            "status": {
                "observedGeneration": 5,
                "desiredNumberScheduled": 3,
                "currentNumberScheduled": 3,
                "updatedNumberScheduled": 3,
            },
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([mock_ds.instance.to_dict()]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_ds(mock_ds)

        mock_sampler.assert_called_once()

    @patch("utilities.hco.TimeoutSampler")
    def test_wait_for_ds_timeout(self, mock_sampler):
        """Test wait_for_ds raises timeout when daemonset is not up to date"""
        mock_ds = MagicMock()
        mock_ds.name = "test-daemonset"

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "test_value"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            wait_for_ds(mock_ds)


class TestWaitForDp:
    """Test cases for wait_for_dp function"""

    @patch("utilities.hco.TimeoutSampler")
    def test_wait_for_dp_success(self, mock_sampler):
        """Test wait_for_dp succeeds when deployment is up to date"""
        mock_dp = MagicMock()
        mock_dp.name = "test-deployment"
        mock_dp.instance.to_dict.return_value = {
            "metadata": {"generation": 3},
            "status": {"observedGeneration": 3, "replicas": 2, "updatedReplicas": 2},
        }

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([mock_dp.instance.to_dict()]))
        mock_sampler.return_value = mock_sampler_instance

        wait_for_dp(mock_dp)

        mock_sampler.assert_called_once()

    @patch("utilities.hco.TimeoutSampler")
    def test_wait_for_dp_timeout(self, mock_sampler):
        """Test wait_for_dp raises timeout when deployment is not up to date"""
        mock_dp = MagicMock()
        mock_dp.name = "test-deployment"

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "test_value"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            wait_for_dp(mock_dp)


class TestWaitForHcoConditions:
    """Test cases for wait_for_hco_conditions function"""

    @patch("utilities.hco.utilities.infra.wait_for_consistent_resource_conditions")
    @patch("utilities.hco.Namespace")
    def test_wait_for_hco_conditions_no_dependent_crs(self, mock_namespace_class, mock_wait_conditions):
        """Test wait_for_hco_conditions without dependent CRs"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"
        mock_namespace_class.return_value = mock_namespace

        wait_for_hco_conditions(mock_admin_client, mock_namespace)

        # Should call wait_for_consistent_resource_conditions once for HCO only
        assert mock_wait_conditions.call_count == 1

    @patch("utilities.hco.utilities.infra.wait_for_consistent_resource_conditions")
    @patch("utilities.hco.Namespace")
    def test_wait_for_hco_conditions_with_dependent_crs(self, mock_namespace_class, mock_wait_conditions):
        """Test wait_for_hco_conditions with dependent CRs"""
        from utilities.hco import CDI, KubeVirt

        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"

        # Use actual resource classes that exist in EXPECTED_STATUS_CONDITIONS
        wait_for_hco_conditions(mock_admin_client, mock_namespace, list_dependent_crs_to_check=[KubeVirt, CDI])

        # Should call wait_for_consistent_resource_conditions 3 times: KubeVirt, CDI, HCO
        assert mock_wait_conditions.call_count == 3

    @patch("utilities.hco.utilities.infra.wait_for_consistent_resource_conditions")
    @patch("utilities.hco.Namespace")
    def test_wait_for_hco_conditions_timeout(self, mock_namespace_class, mock_wait_conditions):
        """Test wait_for_hco_conditions raises timeout"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"

        mock_wait_conditions.side_effect = TimeoutExpiredError("Timeout", "test_value")

        with pytest.raises(TimeoutExpiredError):
            wait_for_hco_conditions(mock_admin_client, mock_namespace)


class TestApplyNpChanges:
    """Test cases for apply_np_changes function"""

    @patch("utilities.hco.wait_for_hco_post_update_stable_state")
    @patch("utilities.hco.ResourceEditor")
    @patch("utilities.hco.Namespace")
    def test_apply_np_changes_infra_only(self, mock_namespace_class, mock_resource_editor_class, mock_wait_stable):
        """Test apply_np_changes with only infra placement change"""
        mock_admin_client = MagicMock()
        mock_hco = MagicMock()
        mock_namespace = MagicMock()

        mock_hco.instance.to_dict.return_value = {"spec": {"infra": None, "workloads": None}}

        new_infra_placement = {"nodeSelector": {"node-role.kubernetes.io/worker": ""}}

        apply_np_changes(mock_admin_client, mock_hco, mock_namespace, infra_placement=new_infra_placement)

        mock_resource_editor_class.assert_called_once()
        mock_wait_stable.assert_called_once()

    @patch("utilities.hco.wait_for_hco_post_update_stable_state")
    @patch("utilities.hco.ResourceEditor")
    @patch("utilities.hco.Namespace")
    def test_apply_np_changes_no_changes(self, mock_namespace_class, mock_resource_editor_class, mock_wait_stable):
        """Test apply_np_changes with no actual changes"""
        mock_admin_client = MagicMock()
        mock_hco = MagicMock()
        mock_namespace = MagicMock()

        existing_placement = {"nodeSelector": {"node-role.kubernetes.io/worker": ""}}
        mock_hco.instance.to_dict.return_value = {"spec": {"infra": existing_placement, "workloads": None}}

        apply_np_changes(mock_admin_client, mock_hco, mock_namespace, infra_placement=existing_placement)

        # Should not call ResourceEditor or wait_for_hco_post_update_stable_state
        mock_resource_editor_class.assert_not_called()
        mock_wait_stable.assert_not_called()


class TestResourceEditorValidateHCOReconcile:
    """Test cases for ResourceEditorValidateHCOReconcile class"""

    @patch("utilities.hco.get_client")
    @patch("utilities.hco.Namespace")
    def test_resource_editor_init(self, mock_namespace_class, mock_get_client):
        """Test ResourceEditorValidateHCOReconcile initialization"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_namespace = MagicMock()
        mock_namespace_class.return_value = mock_namespace

        mock_resource = MagicMock()
        patches = {mock_resource: {"spec": {"test": "value"}}}

        editor = ResourceEditorValidateHCOReconcile(
            patches=patches, hco_namespace="openshift-cnv", consecutive_checks_count=5
        )

        assert editor.hco_namespace == mock_namespace
        assert editor._consecutive_checks_count == 5
        assert editor.list_resource_reconcile == []

    @patch("utilities.hco.wait_for_hco_conditions")
    @patch("utilities.hco.get_client")
    @patch("utilities.hco.Namespace")
    def test_resource_editor_update_without_reconcile(self, mock_namespace_class, mock_get_client, mock_wait_hco):
        """Test ResourceEditorValidateHCOReconcile update without wait_for_reconcile_post_update"""
        mock_resource = MagicMock()
        patches = {mock_resource: {"spec": {"test": "value"}}}

        editor = ResourceEditorValidateHCOReconcile(patches=patches, wait_for_reconcile_post_update=False)

        with patch("utilities.hco.ResourceEditor.update") as mock_parent_update:
            editor.update(backup_resources=True)
            mock_parent_update.assert_called_once_with(backup_resources=True)
            mock_wait_hco.assert_not_called()

    @patch("utilities.hco.wait_for_hco_conditions")
    @patch("utilities.hco.get_client")
    @patch("utilities.hco.Namespace")
    def test_resource_editor_update_with_reconcile(self, mock_namespace_class, mock_get_client, mock_wait_hco):
        """Test ResourceEditorValidateHCOReconcile update with wait_for_reconcile_post_update"""
        mock_resource = MagicMock()
        patches = {mock_resource: {"spec": {"test": "value"}}}

        editor = ResourceEditorValidateHCOReconcile(patches=patches, wait_for_reconcile_post_update=True)

        with patch("utilities.hco.ResourceEditor.update") as mock_parent_update:
            editor.update(backup_resources=False)
            mock_parent_update.assert_called_once_with(backup_resources=False)
            mock_wait_hco.assert_called_once()

    @patch("utilities.hco.wait_for_hco_conditions")
    @patch("utilities.hco.get_client")
    @patch("utilities.hco.Namespace")
    def test_resource_editor_restore(self, mock_namespace_class, mock_get_client, mock_wait_hco):
        """Test ResourceEditorValidateHCOReconcile restore"""
        mock_resource = MagicMock()
        patches = {mock_resource: {"spec": {"test": "value"}}}

        editor = ResourceEditorValidateHCOReconcile(patches=patches)

        with patch("utilities.hco.ResourceEditor.restore") as mock_parent_restore:
            editor.restore()
            mock_parent_restore.assert_called_once()
            mock_wait_hco.assert_called_once()


class TestModuleConstants:
    """Test cases for module constants"""

    def test_default_hco_progressing_conditions(self):
        """Test DEFAULT_HCO_PROGRESSING_CONDITIONS constant"""
        from utilities.hco import Resource

        assert "Progressing" in DEFAULT_HCO_PROGRESSING_CONDITIONS
        assert DEFAULT_HCO_PROGRESSING_CONDITIONS[Resource.Condition.PROGRESSING] == Resource.Condition.Status.TRUE

    def test_hco_jsonpatch_annotation_component_dict(self):
        """Test HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT constant"""
        assert "kubevirt" in HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT
        assert "cdi" in HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT
        assert "cnao" in HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT
        assert "ssp" in HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT

        # Verify structure
        assert "api_group_prefix" in HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT["kubevirt"]
        assert "config" in HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT["kubevirt"]


class TestWaitForHcoPostUpdateStableState:
    """Test cases for wait_for_hco_post_update_stable_state function"""

    @patch("utilities.hco.utilities.infra.wait_for_pods_running")
    @patch("utilities.hco.wait_for_dp")
    @patch("utilities.hco.utilities.infra.get_deployments")
    @patch("utilities.hco.wait_for_ds")
    @patch("utilities.hco.utilities.infra.get_daemonsets")
    @patch("utilities.hco.wait_for_hco_conditions")
    @patch("utilities.hco.Namespace")
    def test_wait_for_hco_post_update_stable_state_success(
        self,
        mock_namespace_class,
        mock_wait_hco_conditions,
        mock_get_daemonsets,
        mock_wait_ds,
        mock_get_deployments,
        mock_wait_dp,
        mock_wait_pods,
    ):
        """Test wait_for_hco_post_update_stable_state with successful completion"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"

        # Mock daemonsets
        mock_ds1 = MagicMock()
        mock_ds1.name = "virt-handler"
        mock_ds2 = MagicMock()
        mock_ds2.name = "hostpath-provisioner-csi"  # Should be skipped
        mock_get_daemonsets.return_value = [mock_ds1, mock_ds2]

        # Mock deployments
        mock_dp = MagicMock()
        mock_dp.name = "virt-api"
        mock_get_deployments.return_value = [mock_dp]

        wait_for_hco_post_update_stable_state(mock_admin_client, mock_namespace)

        mock_wait_hco_conditions.assert_called_once()
        mock_wait_ds.assert_called_once_with(ds=mock_ds1)  # Only non-hostpath ds
        mock_wait_dp.assert_called_once_with(dp=mock_dp)
        mock_wait_pods.assert_called_once()

    @patch("utilities.hco.utilities.infra.wait_for_pods_running")
    @patch("utilities.hco.wait_for_dp")
    @patch("utilities.hco.utilities.infra.get_deployments")
    @patch("utilities.hco.wait_for_ds")
    @patch("utilities.hco.utilities.infra.get_daemonsets")
    @patch("utilities.hco.wait_for_hco_conditions")
    @patch("utilities.hco.Namespace")
    def test_wait_for_hco_post_update_with_excluded_deployments(
        self,
        mock_namespace_class,
        mock_wait_hco_conditions,
        mock_get_daemonsets,
        mock_wait_ds,
        mock_get_deployments,
        mock_wait_dp,
        mock_wait_pods,
    ):
        """Test wait_for_hco_post_update_stable_state with excluded deployments"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"

        mock_get_daemonsets.return_value = []

        # Mock deployments
        mock_dp1 = MagicMock()
        mock_dp1.name = "virt-api"
        mock_dp2 = MagicMock()
        mock_dp2.name = "excluded-deployment"
        mock_get_deployments.return_value = [mock_dp1, mock_dp2]

        wait_for_hco_post_update_stable_state(
            mock_admin_client, mock_namespace, exclude_deployments=["excluded-deployment"]
        )

        # Only virt-api should be waited on
        mock_wait_dp.assert_called_once_with(dp=mock_dp1)


class TestDisableCommonBootImageImportHcoSpec:
    """Test cases for disable_common_boot_image_import_hco_spec function"""

    @patch("utilities.hco.enable_common_boot_image_import_spec_wait_for_data_import_cron")
    @patch("utilities.hco.wait_for_deleted_data_import_crons")
    @patch("utilities.hco.update_common_boot_image_import_spec")
    def test_disable_when_enabled(self, mock_update_spec, mock_wait_deleted, mock_enable_spec):
        """Test disabling common boot image import when it's enabled"""
        mock_admin_client = MagicMock()
        mock_hco = MagicMock()
        mock_hco.instance.spec = {"enableCommonBootImageImport": True}
        mock_namespace = MagicMock()
        mock_dics = [MagicMock()]

        gen = disable_common_boot_image_import_hco_spec(mock_admin_client, mock_hco, mock_namespace, mock_dics)
        next(gen)  # Enter context

        mock_update_spec.assert_called_once_with(hco_resource=mock_hco, enable=False)
        mock_wait_deleted.assert_called_once_with(data_import_crons=mock_dics)

        # Exit context
        try:
            next(gen)
        except StopIteration:
            pass

        mock_enable_spec.assert_called_once()

    @patch("utilities.hco.enable_common_boot_image_import_spec_wait_for_data_import_cron")
    @patch("utilities.hco.wait_for_deleted_data_import_crons")
    @patch("utilities.hco.update_common_boot_image_import_spec")
    def test_disable_when_already_disabled(self, mock_update_spec, mock_wait_deleted, mock_enable_spec):
        """Test context manager when common boot image import is already disabled"""
        mock_admin_client = MagicMock()
        mock_hco = MagicMock()
        mock_hco.instance.spec = {"enableCommonBootImageImport": False}
        mock_namespace = MagicMock()
        mock_dics = [MagicMock()]

        gen = disable_common_boot_image_import_hco_spec(mock_admin_client, mock_hco, mock_namespace, mock_dics)
        next(gen)  # Enter context

        # Should not call update when already disabled
        mock_update_spec.assert_not_called()
        mock_wait_deleted.assert_not_called()

        try:
            next(gen)
        except StopIteration:
            pass

        mock_enable_spec.assert_not_called()


class TestEnableCommonBootImageImportSpecWaitForDataImportCron:
    """Test cases for enable_common_boot_image_import_spec_wait_for_data_import_cron"""

    @patch("utilities.hco.wait_for_hco_conditions")
    @patch("utilities.hco.wait_for_ssp_conditions")
    @patch("utilities.hco.wait_for_at_least_one_auto_update_data_import_cron")
    @patch("utilities.hco.update_common_boot_image_import_spec")
    @patch("utilities.hco.Namespace")
    def test_enable_spec(
        self,
        mock_namespace_class,
        mock_update_spec,
        mock_wait_dic,
        mock_wait_ssp,
        mock_wait_hco,
    ):
        """Test enabling common boot image import spec"""
        mock_hco = MagicMock()
        mock_hco.namespace = "openshift-cnv"
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()

        enable_common_boot_image_import_spec_wait_for_data_import_cron(mock_hco, mock_admin_client, mock_namespace)

        mock_update_spec.assert_called_once_with(hco_resource=mock_hco, enable=True)
        mock_wait_dic.assert_called_once()
        mock_wait_ssp.assert_called_once()
        mock_wait_hco.assert_called_once()


class TestUpdateCommonBootImageImportSpec:
    """Test cases for update_common_boot_image_import_spec function"""

    @patch("utilities.hco.TimeoutSampler")
    @patch("utilities.hco.ResourceEditor")
    def test_update_spec_enable(self, mock_editor_class, mock_sampler):
        """Test enabling common boot image import spec"""
        mock_hco = MagicMock()
        mock_hco.instance.spec = {"enableCommonBootImageImport": True}

        mock_editor = MagicMock()
        mock_editor_class.return_value = mock_editor

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([True]))
        mock_sampler.return_value = mock_sampler_instance

        update_common_boot_image_import_spec(mock_hco, enable=True)

        mock_editor.update.assert_called_once_with(backup_resources=True)
        mock_sampler.assert_called_once()

    @patch("utilities.hco.TimeoutSampler")
    @patch("utilities.hco.ResourceEditor")
    def test_update_spec_timeout(self, mock_editor_class, mock_sampler):
        """Test timeout when spec doesn't update"""
        mock_hco = MagicMock()
        mock_hco.instance.spec = {"enableCommonBootImageImport": False}

        mock_editor = MagicMock()
        mock_editor_class.return_value = mock_editor

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "test_value"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            update_common_boot_image_import_spec(mock_hco, enable=True)


class TestUpdateHcoAnnotations:
    """Test cases for update_hco_annotations context manager"""

    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_update_annotations_basic(self, mock_editor_class):
        """Test basic annotation update"""
        mock_hco = MagicMock()
        mock_hco.instance.metadata = {"annotations": {}}

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        with update_hco_annotations(
            resource=mock_hco,
            path="machineType",
            value="pc-q35-rhel8.4.0",
        ):
            pass

        mock_editor_class.assert_called_once()

    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_update_annotations_with_existing(self, mock_editor_class):
        """Test annotation update with existing annotations"""
        mock_hco = MagicMock()
        existing_annotation = '[{"op": "add", "path": "/spec/configuration/cpuModel", "value": "Haswell"}]'
        mock_hco.instance.metadata = {"annotations": {"kubevirt.kubevirt.io/jsonpatch": existing_annotation}}

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        with update_hco_annotations(
            resource=mock_hco,
            path="machineType",
            value="pc-q35-rhel8.4.0",
            overwrite_patches=False,
        ):
            pass

        mock_editor_class.assert_called_once()

    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_update_annotations_overwrite(self, mock_editor_class):
        """Test annotation update with overwrite_patches=True"""
        mock_hco = MagicMock()
        mock_hco.instance.metadata = {"annotations": {"kubevirt.kubevirt.io/jsonpatch": "existing"}}

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        with update_hco_annotations(
            resource=mock_hco,
            path="machineType",
            value="pc-q35-rhel8.4.0",
            overwrite_patches=True,
        ):
            pass

        mock_editor_class.assert_called_once()


class TestWaitForAutoBootConfigStabilization:
    """Test cases for wait_for_auto_boot_config_stabilization function"""

    @patch("utilities.hco.wait_for_hco_conditions")
    @patch("utilities.hco.wait_for_ssp_conditions")
    def test_wait_for_stabilization(self, mock_wait_ssp, mock_wait_hco):
        """Test waiting for auto boot config stabilization"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()

        wait_for_auto_boot_config_stabilization(mock_admin_client, mock_namespace)

        mock_wait_ssp.assert_called_once_with(admin_client=mock_admin_client, hco_namespace=mock_namespace)
        mock_wait_hco.assert_called_once_with(admin_client=mock_admin_client, hco_namespace=mock_namespace)


class TestUpdateHcoTemplatesSpec:
    """Test cases for update_hco_templates_spec context manager"""

    @patch("utilities.hco.DataSource")
    @patch("utilities.hco.wait_for_auto_boot_config_stabilization")
    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_update_templates_spec(self, mock_editor_class, mock_wait_stabilization, mock_datasource_class):
        """Test updating HCO templates spec"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_hco = MagicMock()
        mock_template = {"name": "test-template"}

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        # update_hco_templates_spec is a generator context manager
        gen = update_hco_templates_spec(mock_admin_client, mock_namespace, mock_hco, mock_template)
        result = next(gen)
        assert result == mock_template

        mock_wait_stabilization.assert_called_once()

        # Exit the generator
        try:
            next(gen)
        except StopIteration:
            pass

        mock_datasource_class.assert_not_called()  # No custom_datasource_name

    @patch("utilities.hco.DataSource")
    @patch("utilities.hco.wait_for_auto_boot_config_stabilization")
    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_update_templates_spec_with_custom_datasource(
        self, mock_editor_class, mock_wait_stabilization, mock_datasource_class
    ):
        """Test updating HCO templates spec with custom datasource cleanup"""
        mock_admin_client = MagicMock()
        mock_namespace = MagicMock()
        mock_hco = MagicMock()
        mock_template = {"name": "test-template"}
        mock_gi_namespace = MagicMock()
        mock_gi_namespace.name = "openshift-virtualization-os-images"

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        mock_datasource = MagicMock()
        mock_datasource_class.return_value = mock_datasource

        # update_hco_templates_spec is a generator context manager
        gen = update_hco_templates_spec(
            mock_admin_client,
            mock_namespace,
            mock_hco,
            mock_template,
            custom_datasource_name="custom-ds",
            golden_images_namespace=mock_gi_namespace,
        )
        next(gen)

        # Exit the generator
        try:
            next(gen)
        except StopIteration:
            pass

        # After context exit, DataSource cleanup should be called
        mock_datasource.clean_up.assert_called_once()


class TestEnabledAaqInHco:
    """Test cases for enabled_aaq_in_hco context manager"""

    @patch("utilities.hco.TimeoutSampler")
    @patch("utilities.hco.utilities.infra.get_pod_by_name_prefix")
    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_enable_aaq_basic(self, mock_editor_class, mock_get_pod, mock_sampler):
        """Test enabling AAQ in HCO"""
        mock_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"
        mock_hco = MagicMock()

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        # Mock TimeoutSampler to return empty list (pods removed)
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[]]))
        mock_sampler.return_value = mock_sampler_instance

        with enabled_aaq_in_hco(mock_client, mock_namespace, mock_hco):
            pass

        # Verify editor was called with correct patches
        call_args = mock_editor_class.call_args
        patches = call_args[1]["patches"]
        assert mock_hco in patches
        assert patches[mock_hco]["spec"]["enableApplicationAwareQuota"] is True

    @patch("utilities.hco.TimeoutSampler")
    @patch("utilities.hco.utilities.infra.get_pod_by_name_prefix")
    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_enable_aaq_with_acrq_support(self, mock_editor_class, mock_get_pod, mock_sampler):
        """Test enabling AAQ with ACRQ support"""
        mock_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"
        mock_hco = MagicMock()

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(return_value=iter([[]]))
        mock_sampler.return_value = mock_sampler_instance

        with enabled_aaq_in_hco(mock_client, mock_namespace, mock_hco, enable_acrq_support=True):
            pass

        # Verify ACRQ support is included
        call_args = mock_editor_class.call_args
        patches = call_args[1]["patches"]
        assert patches[mock_hco]["spec"]["applicationAwareConfig"] == {
            "allowApplicationAwareClusterResourceQuota": True
        }

    @patch("utilities.hco.TimeoutSampler")
    @patch("utilities.hco.utilities.infra.get_pod_by_name_prefix")
    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_enable_aaq_timeout_waiting_for_pods(self, mock_editor_class, mock_get_pod, mock_sampler):
        """Test timeout when AAQ pods don't get removed"""
        mock_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"
        mock_hco = MagicMock()

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        # Mock timeout
        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=TimeoutExpiredError("Timeout", "aaq-pod"))
        mock_sampler.return_value = mock_sampler_instance

        with pytest.raises(TimeoutExpiredError):
            with enabled_aaq_in_hco(
                client=mock_client,
                hco_namespace=mock_namespace,
                hyperconverged_resource=mock_hco,
            ):
                pass

    @patch("utilities.hco.LOGGER")
    @patch("utilities.hco.TimeoutSampler")
    @patch("utilities.hco.utilities.infra.get_pod_by_name_prefix")
    @patch("utilities.hco.ResourceEditorValidateHCOReconcile")
    def test_enable_aaq_handles_resource_not_found(self, mock_editor_class, mock_get_pod, mock_sampler, mock_logger):
        mock_client = MagicMock()
        mock_namespace = MagicMock()
        mock_namespace.name = "openshift-cnv"
        mock_hco = MagicMock()

        mock_editor = MagicMock()
        mock_editor.__enter__ = MagicMock(return_value=mock_editor)
        mock_editor.__exit__ = MagicMock(return_value=None)
        mock_editor_class.return_value = mock_editor

        mock_sampler_instance = MagicMock()
        mock_sampler_instance.__iter__ = MagicMock(side_effect=ResourceNotFoundError("not found"))
        mock_sampler.return_value = mock_sampler_instance

        with enabled_aaq_in_hco(
            client=mock_client,
            hco_namespace=mock_namespace,
            hyperconverged_resource=mock_hco,
        ):
            pass

        mock_logger.info.assert_called_with("AAQ system PODs removed.")
