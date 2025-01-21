import logging

import pytest
from kubernetes.dynamic.exceptions import ForbiddenError

from tests.install_upgrade_operators.node_component.utils import (
    CNV_INFRA_PODS_COMPONENTS,
    CNV_OPERATOR_PODS_COMPONENTS,
    CNV_WORKLOADS_PODS_COMPONENTS,
    INFRA_LABEL_1,
    INFRA_LABEL_2,
    INFRA_LABEL_3,
    SUBSCRIPTION_NODE_SELCTOR_1,
    SUBSCRIPTION_NODE_SELCTOR_2,
    SUBSCRIPTION_NODE_SELCTOR_3,
    SUBSCRIPTION_TOLERATIONS,
    WORK_LABEL_1,
    WORK_LABEL_2,
    WORK_LABEL_3,
    verify_all_components_on_node,
    verify_no_components_on_nodes,
)
from utilities.hco import ResourceEditorValidateHCOReconcile

pytestmark = [pytest.mark.post_upgrade, pytest.mark.gating]


LOGGER = logging.getLogger(__name__)


@pytest.mark.usefixtures(
    "node_placement_labels",
    "hyperconverged_resource_before_np",
    "cnv_subscription_resource_before_np",
)
class TestDeployCNVOnSubsetOfClusterNodes:
    @pytest.mark.polarion("CNV-5226")
    @pytest.mark.parametrize(
        "alter_cnv_subscription_configuration",
        [
            {
                "node_selector": SUBSCRIPTION_NODE_SELCTOR_2,
                "tolerations": SUBSCRIPTION_TOLERATIONS,
            }
        ],
        indirect=True,
    )
    def test_change_subscription_on_selected_node_before_workload(
        self,
        skip_on_rosa_cluster,
        admin_client,
        hco_namespace,
        alter_cnv_subscription_configuration,
        subscription_pods_per_nodes_after_altering_placement,
        expected_node_by_label,
        nodes_labeled,
    ):
        assert nodes_labeled["op2"] == expected_node_by_label["op2"]
        # Verify all operator components are removed from control plane node-0 and created on control plane node-1.
        verify_all_components_on_node(
            component_list=CNV_OPERATOR_PODS_COMPONENTS,
            node_name=nodes_labeled["op2"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        verify_no_components_on_nodes(
            component_list=CNV_OPERATOR_PODS_COMPONENTS,
            node_names=[nodes_labeled["op1"][0], nodes_labeled["op3"][0]],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    @pytest.mark.polarion("CNV-5228")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"infra": INFRA_LABEL_2, "workloads": WORK_LABEL_1},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(name="test_change_infrastructure_components_on_selected_node_before_workload")
    def test_change_infrastructure_components_on_selected_node_before_workload(
        self,
        skip_on_rosa_cluster,
        admin_client,
        hco_namespace,
        alter_np_configuration,
        hco_pods_per_nodes_after_altering_placement,
        expected_node_by_label,
        nodes_labeled,
    ):
        assert nodes_labeled["infra2"] == expected_node_by_label["infra2"]
        # Verify all Infra components are moved to worker-2.
        verify_all_components_on_node(
            component_list=CNV_INFRA_PODS_COMPONENTS,
            node_name=nodes_labeled["infra2"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        verify_no_components_on_nodes(
            component_list=CNV_INFRA_PODS_COMPONENTS,
            node_names=[nodes_labeled["infra1"][0], nodes_labeled["infra3"][0]],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    @pytest.mark.polarion("CNV-5229")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"infra": INFRA_LABEL_2, "workloads": WORK_LABEL_3},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        name="test_change_workload_components_on_selected_node_before_workload",
        depends=["test_change_infrastructure_components_on_selected_node_before_workload"],
    )
    def test_change_workload_components_on_selected_node_before_workload(
        self,
        admin_client,
        hco_namespace,
        alter_np_configuration,
        hco_pods_per_nodes_after_altering_placement,
        nodes_labeled,
        expected_node_by_label,
    ):
        assert nodes_labeled["work3"] == expected_node_by_label["work3"]
        # Verify all Workloads Pods are moved to worker-3.
        verify_all_components_on_node(
            component_list=CNV_WORKLOADS_PODS_COMPONENTS,
            node_name=nodes_labeled["work3"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        verify_no_components_on_nodes(
            component_list=CNV_WORKLOADS_PODS_COMPONENTS,
            node_names=[nodes_labeled["work1"][0], nodes_labeled["work2"][0]],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    @pytest.mark.polarion("CNV-5230")
    @pytest.mark.dependency(
        name="test_deploying_workloads_on_selected_nodes",
        depends=["test_change_workload_components_on_selected_node_before_workload"],
    )
    def test_deploying_workloads_on_selected_nodes(
        self,
        vm_placement_vm_work3,
        nodes_labeled,
    ):
        assert vm_placement_vm_work3.vmi.node.name == nodes_labeled["work3"][0]

    @pytest.mark.polarion("CNV-5231")
    @pytest.mark.dependency(
        depends=["test_deploying_workloads_on_selected_nodes"],
    )
    def test_workload_components_selection_change_denied_with_workloads(
        self,
        nodes_labeled,
        vm_placement_vm_work3,
        hyperconverged_resource_scope_function,
    ):
        LOGGER.info("Attempting to update HCO with node placement, expecting it to fail")
        try:
            with ResourceEditorValidateHCOReconcile(
                patches={hyperconverged_resource_scope_function: {"spec": {"workloads": WORK_LABEL_1}}},
            ):
                LOGGER.info("Expected ability to change workloads label {WORK_LABEL_1} while VM/Workload is present.")
        except ForbiddenError:
            LOGGER.error("Unable to change workload label  {WORK_LABEL_1} while vm/workload is present")
            raise

    @pytest.mark.polarion("CNV-5232")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"infra": INFRA_LABEL_1},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        name="test_infrastructure_components_selection_change_allowed_with_workloads",
        depends=["test_deploying_workloads_on_selected_nodes"],
    )
    def test_infrastructure_components_selection_change_allowed_with_workloads(
        self,
        admin_client,
        hco_namespace,
        alter_np_configuration,
        vm_placement_vm_work3,
        hco_pods_per_nodes_after_altering_placement,
        nodes_labeled,
        expected_node_by_label,
    ):
        assert nodes_labeled["infra1"] == expected_node_by_label["infra1"]
        # Verify all infra components are removed from worker-2 and created on worker-1.
        verify_all_components_on_node(
            component_list=CNV_INFRA_PODS_COMPONENTS,
            node_name=nodes_labeled["infra1"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        verify_no_components_on_nodes(
            component_list=CNV_INFRA_PODS_COMPONENTS,
            node_names=[nodes_labeled["infra2"][0], nodes_labeled["infra3"][0]],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    @pytest.mark.polarion("CNV-5233")
    @pytest.mark.parametrize(
        "alter_cnv_subscription_configuration",
        [
            {
                "node_selector": SUBSCRIPTION_NODE_SELCTOR_3,
                "tolerations": SUBSCRIPTION_TOLERATIONS,
            }
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        depends=["test_infrastructure_components_selection_change_allowed_with_workloads"],
    )
    def test_operator_components_selection_change_allowed_with_workloads(
        self,
        admin_client,
        hco_namespace,
        vm_placement_vm_work3,
        alter_cnv_subscription_configuration,
        subscription_pods_per_nodes_after_altering_placement,
        expected_node_by_label,
        nodes_labeled,
    ):
        assert nodes_labeled["op3"] == expected_node_by_label["op3"]
        # Verify all operator components are removed from control plane node -2 and created on control plane node-3.
        verify_all_components_on_node(
            component_list=CNV_OPERATOR_PODS_COMPONENTS,
            node_name=nodes_labeled["op3"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        verify_no_components_on_nodes(
            component_list=CNV_OPERATOR_PODS_COMPONENTS,
            node_names=[nodes_labeled["op1"][0], nodes_labeled["op2"][0]],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    @pytest.mark.polarion("CNV-5236")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"infra": INFRA_LABEL_3},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        name="test_infrastructure_components_selection_change_allowed_after_workloads",
        depends=["test_infrastructure_components_selection_change_allowed_with_workloads"],
    )
    def test_infrastructure_components_selection_change_allowed_after_workloads(
        self,
        admin_client,
        hco_namespace,
        alter_np_configuration,
        delete_vm_after_placement,
        hco_pods_per_nodes_after_altering_placement,
        nodes_labeled,
        expected_node_by_label,
    ):
        assert nodes_labeled["infra3"] == expected_node_by_label["infra3"]
        # Verify all infrastructure components are removed from worker-1 and created on worker-3
        verify_all_components_on_node(
            component_list=CNV_INFRA_PODS_COMPONENTS,
            node_name=nodes_labeled["infra3"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        verify_no_components_on_nodes(
            component_list=CNV_INFRA_PODS_COMPONENTS,
            node_names=[nodes_labeled["infra2"][0], nodes_labeled["infra1"][0]],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    @pytest.mark.polarion("CNV-5237")
    @pytest.mark.parametrize(
        "alter_cnv_subscription_configuration",
        [
            {
                "node_selector": SUBSCRIPTION_NODE_SELCTOR_1,
                "tolerations": SUBSCRIPTION_TOLERATIONS,
            }
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        depends=["test_infrastructure_components_selection_change_allowed_after_workloads"],
    )
    def test_operator_components_selection_change_allowed_after_workloads(
        self,
        admin_client,
        hco_namespace,
        alter_cnv_subscription_configuration,
        subscription_pods_per_nodes_after_altering_placement,
        expected_node_by_label,
        nodes_labeled,
    ):
        assert nodes_labeled["op1"] == expected_node_by_label["op1"]
        # Verify all the operators are moved to master-0
        verify_all_components_on_node(
            component_list=CNV_OPERATOR_PODS_COMPONENTS,
            node_name=nodes_labeled["op1"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        verify_no_components_on_nodes(
            component_list=CNV_OPERATOR_PODS_COMPONENTS,
            node_names=[nodes_labeled["op3"][0], nodes_labeled["op2"][0]],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    @pytest.mark.polarion("CNV-5235")
    @pytest.mark.parametrize(
        "alter_np_configuration",
        [
            {"workloads": WORK_LABEL_2},
        ],
        indirect=True,
    )
    @pytest.mark.dependency(
        depends=["test_infrastructure_components_selection_change_allowed_after_workloads"],
    )
    def test_workload_components_selection_change_allowed_after_workloads(
        self,
        admin_client,
        hco_namespace,
        alter_np_configuration,
        hco_pods_per_nodes_after_altering_placement,
        nodes_labeled,
        expected_node_by_label,
    ):
        assert nodes_labeled["work2"] == expected_node_by_label["work2"]
        # Verify all workloads components are removed from worker-3 and created on worker-2
        verify_all_components_on_node(
            component_list=CNV_WORKLOADS_PODS_COMPONENTS,
            node_name=nodes_labeled["work2"][0],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        verify_no_components_on_nodes(
            component_list=CNV_WORKLOADS_PODS_COMPONENTS,
            node_names=[nodes_labeled["work1"][0], nodes_labeled["work3"][0]],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
