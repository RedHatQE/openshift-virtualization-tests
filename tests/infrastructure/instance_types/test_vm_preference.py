import pytest

from tests.infrastructure.instance_types.constants import ALL_OPTIONS_VM_PREFERENCE_SPEC


@pytest.mark.gating
class TestVmPreference:
    @pytest.mark.parametrize(
        "common_vm_preference_param_dict",
        [
            pytest.param(
                {
                    "name": "basic-preference",
                },
            ),
            pytest.param(
                {
                    **{"name": "all-options-vm-preference"},
                    **ALL_OPTIONS_VM_PREFERENCE_SPEC,
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-9084")
    def test_create_preference(self, vm_preference_for_test):
        with vm_preference_for_test as vm_preference:
            assert vm_preference.exists


@pytest.mark.gating
class TestVmClusterPreference:
    @pytest.mark.parametrize(
        "common_vm_preference_param_dict",
        [
            pytest.param(
                {
                    "name": "basic-cluster-preference",
                },
            ),
            pytest.param(
                {
                    **{"name": "all-options-vm-cluster-preference"},
                    **ALL_OPTIONS_VM_PREFERENCE_SPEC,
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-9335")
    def test_create_cluster_preference(self, vm_cluster_preference_for_test):
        with vm_cluster_preference_for_test as vm_cluster_preference:
            assert vm_cluster_preference.exists
