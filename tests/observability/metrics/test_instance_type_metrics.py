import pytest

from tests.observability.metrics.constants import (
    CNV_VMI_STATUS_RUNNING_COUNT,
    EXPECTED_NAMESPACE_INSTANCE_TYPE_LABELS,
    KUBEVIRT_VMI_PHASE_COUNT,
    KUBEVIRT_VMI_PHASE_COUNT_STR,
    METRIC_SUM_QUERY,
)
from tests.observability.metrics.utils import (
    assert_instancetype_labels,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    INSTANCE_TYPE_STR,
    PREFERENCE_STR,
    RHEL_WITH_INSTANCETYPE_AND_PREFERENCE,
    Images,
)


class TestInstanceType:
    @pytest.mark.polarion("CNV-10181")
    def test_verify_instancetype_labels(
        self,
        prometheus,
        rhel_vm_with_cluster_instance_type_and_preference,
    ):
        assert_instancetype_labels(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_PHASE_COUNT.format(
                node_name=rhel_vm_with_cluster_instance_type_and_preference.vmi.node.name,
                instance_type=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[INSTANCE_TYPE_STR],
                preference=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR],
            ),
            vm=rhel_vm_with_cluster_instance_type_and_preference,
            expected_labels=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
        )

    @pytest.mark.polarion("CNV-10182")
    def test_verify_migrated_instancetype_labels(
        self,
        prometheus,
        rhel_vm_with_cluster_instance_type_and_preference,
        migrated_instance_type_vm,
    ):
        assert_instancetype_labels(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_PHASE_COUNT.format(
                node_name=rhel_vm_with_cluster_instance_type_and_preference.vmi.node.name,
                instance_type=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[INSTANCE_TYPE_STR],
                preference=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR],
            ),
            vm=rhel_vm_with_cluster_instance_type_and_preference,
            expected_labels=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
        )

    @pytest.mark.parametrize(
        "common_instance_type_param_dict, common_vm_preference_param_dict",
        [
            pytest.param(
                {
                    "name": "basic",
                    "memory_requests": Images.Rhel.DEFAULT_MEMORY_SIZE,
                },
                {
                    "name": "basic-vm-preference",
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-10274")
    @pytest.mark.order(after="test_verify_instancetype_labels")
    def test_verify_namespace_instancetype_labels(
        self,
        prometheus,
        running_rhel_vm_with_instance_type_and_preference,
    ):
        assert_instancetype_labels(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_PHASE_COUNT.format(
                node_name=running_rhel_vm_with_instance_type_and_preference.vmi.node.name,
                instance_type=EXPECTED_NAMESPACE_INSTANCE_TYPE_LABELS[INSTANCE_TYPE_STR],
                preference=EXPECTED_NAMESPACE_INSTANCE_TYPE_LABELS[PREFERENCE_STR],
            ),
            vm=running_rhel_vm_with_instance_type_and_preference,
            expected_labels=EXPECTED_NAMESPACE_INSTANCE_TYPE_LABELS,
        )


@pytest.mark.parametrize(
    "cloning_job_scope_class",
    [
        pytest.param(
            {"source_name": RHEL_WITH_INSTANCETYPE_AND_PREFERENCE},
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "kubevirt_vmi_phase_count_metric_no_value",
    "cnv_vmi_status_running_count_metric_no_value",
    "rhel_vm_with_instancetype_and_preference_for_cloning",
    "cloning_job_scope_class",
    "validated_preference_instance_type_of_target_vm",
)
class TestInstanceTypeLabling:
    @pytest.mark.polarion("CNV-10183")
    def test_kubevirt_vmi_phase_count_cloned_instance_types(
        self,
        prometheus,
        rhel_vm_with_instancetype_and_preference_for_cloning,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=METRIC_SUM_QUERY.format(
                metric_name=KUBEVIRT_VMI_PHASE_COUNT_STR,
                instance_type_name=rhel_vm_with_instancetype_and_preference_for_cloning.vm_instance_type.name,
                preference=rhel_vm_with_instancetype_and_preference_for_cloning.vm_preference.name,
            ),
            expected_value="2",
        )

    @pytest.mark.polarion("CNV-10797")
    def test_cnv_vmi_status_running_count_cloned_instance_types(
        self,
        prometheus,
        rhel_vm_with_instancetype_and_preference_for_cloning,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=METRIC_SUM_QUERY.format(
                metric_name=CNV_VMI_STATUS_RUNNING_COUNT,
                instance_type_name=rhel_vm_with_instancetype_and_preference_for_cloning.vm_instance_type.name,
                preference=rhel_vm_with_instancetype_and_preference_for_cloning.vm_preference.name,
            ),
            expected_value="2",
        )
