import pytest

from tests.install_upgrade_operators.must_gather.utils import (
    MUST_GATHER_VM_NAME_PREFIX,
    assert_files_exists_for_running_vms,
    assert_must_gather_stopped_vm_yaml_file_collection,
    assert_path_not_exists_for_stopped_vms,
    validate_must_gather_vm_file_collection,
)

pytestmark = [pytest.mark.sno, pytest.mark.post_upgrade, pytest.mark.skip_must_gather_collection, pytest.mark.arm64]


@pytest.mark.usefixtures("must_gather_vms_from_alternate_namespace", "nftables_ruleset_from_utility_pods")
class TestMustGatherVmDetailsWithParams:
    @pytest.mark.parametrize(
        "collected_vm_details_must_gather_with_params, expected",
        [
            pytest.param(
                {"command": "NS={alternate_namespace}"},
                None,
                marks=(pytest.mark.polarion("CNV-7882"),),
                id="test_vm_gather_alternate_namespace",
            ),
            pytest.param(
                {"command": "NS={alternate_namespace} VM={vm_name}"},
                {"alt_ns_vm": [0]},
                marks=(pytest.mark.polarion("CNV-7868"),),
                id="test_vm_gather_specific_vm",
            ),
            pytest.param(
                {"command": "NS={alternate_namespace} VM={vm_list}"},
                {"alt_ns_vm": [0, 1, 2]},
                marks=(pytest.mark.polarion("CNV-7865"),),
                id="test_vm_gather_vm_list",
            ),
            pytest.param(
                {"command": f'NS={{alternate_namespace}} VM_EXP="^{MUST_GATHER_VM_NAME_PREFIX}-[1,4]"'},
                {"alt_ns_vm": [1, 4]},
                marks=(pytest.mark.polarion("CNV-7867"),),
                id="test_vm_gather_regex_namespace",
            ),
            pytest.param(
                {"command": f'VM_EXP="^{MUST_GATHER_VM_NAME_PREFIX}-[2-4]"'},
                {"alt_ns_vm": [2, 3, 4], "must_gather_ns_vm": [0]},
                marks=(pytest.mark.polarion("CNV-7866"),),
                id="test_vm_gather_regex",
            ),
        ],
        indirect=["collected_vm_details_must_gather_with_params"],
    )
    @pytest.mark.s390x
    def test_must_gather_params(
        self,
        must_gather_vm,
        collected_vm_details_must_gather_with_params,
        expected,
        must_gather_vms_from_alternate_namespace,
        nftables_ruleset_from_utility_pods,
    ):
        validate_must_gather_vm_file_collection(
            collected_vm_details_must_gather_with_params=collected_vm_details_must_gather_with_params,
            expected=expected,
            must_gather_vm=must_gather_vm,
            must_gather_vms_from_alternate_namespace=must_gather_vms_from_alternate_namespace,
            nftables_ruleset_from_utility_pods=nftables_ruleset_from_utility_pods,
        )

    @pytest.mark.polarion("CNV-9039")
    @pytest.mark.s390x
    def test_must_gather_stopped_vm(
        self,
        must_gather_vms_from_alternate_namespace,
        must_gather_stopped_vms,
        must_gather_vms_alternate_namespace_base_path,
    ):
        """
        Test must-gather collects information for stopped virtual machines.
        Also test colletion of other files of running virtual machines.
        """
        assert_must_gather_stopped_vm_yaml_file_collection(
            base_path=must_gather_vms_alternate_namespace_base_path,
            must_gather_stopped_vms=must_gather_stopped_vms,
        )
        running_vms = list(set(must_gather_vms_from_alternate_namespace) - set(must_gather_stopped_vms))
        assert_files_exists_for_running_vms(
            base_path=must_gather_vms_alternate_namespace_base_path,
            running_vms=running_vms,
        )

        assert_path_not_exists_for_stopped_vms(
            base_path=must_gather_vms_alternate_namespace_base_path,
            stopped_vms=must_gather_stopped_vms,
        )
