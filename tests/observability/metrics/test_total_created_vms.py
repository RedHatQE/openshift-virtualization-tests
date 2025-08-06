import pytest

from tests.observability.metrics.constants import KUBEVIRT_VM_CREATED_TOTAL_STR
from tests.observability.metrics.utils import wait_for_expected_metric_value_sum
from utilities.constants import RHEL_WITH_INSTANCETYPE_AND_PREFERENCE


class TestTotalCreatedInstanceType:
    @pytest.mark.polarion("CNV-10771")
    @pytest.mark.s390x
    def test_kubevirt_vm_created_total_instance_type(
        self, prometheus, namespace, initial_total_created_vms, rhel_vm_with_instancetype_and_preference_for_cloning
    ):
        wait_for_expected_metric_value_sum(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VM_CREATED_TOTAL_STR.format(namespace=namespace.name),
            expected_value=initial_total_created_vms + 1,
        )

    @pytest.mark.parametrize(
        "cloning_job_scope_function",
        [
            pytest.param(
                {"source_name": RHEL_WITH_INSTANCETYPE_AND_PREFERENCE},
                marks=pytest.mark.polarion("CNV-10770"),
            )
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_kubevirt_vm_created_total_cloned_instancetype(
        self,
        prometheus,
        namespace,
        initial_total_created_vms,
        cloning_job_scope_function,
        target_vm_scope_function,
    ):
        wait_for_expected_metric_value_sum(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VM_CREATED_TOTAL_STR.format(namespace=namespace.name),
            expected_value=initial_total_created_vms + 2,
        )
