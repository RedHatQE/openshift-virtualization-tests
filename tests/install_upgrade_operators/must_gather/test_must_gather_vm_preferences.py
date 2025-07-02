import pytest

from tests.install_upgrade_operators.must_gather.utils import check_list_of_resources

pytestmark = [pytest.mark.sno, pytest.mark.post_upgrade, pytest.mark.skip_must_gather_collection, pytest.mark.arm64]


class TestInstanceTypesAndPreferencesCollected:
    @pytest.mark.parametrize(
        "common_instance_type_param_dict,common_vm_preference_param_dict",
        [
            pytest.param(
                {
                    "name": "basic",
                    "memory_requests": "2Gi",
                },
                {
                    "name": "basic-preference",
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-9648")
    @pytest.mark.s390x
    def test_instancestypes_collected(
        self,
        admin_client,
        resource_types_and_pathes_dict,
        gathered_instancetypes,
    ):
        for resource_type in resource_types_and_pathes_dict:
            check_list_of_resources(
                dyn_client=admin_client,
                resource_type=resource_type,
                temp_dir=gathered_instancetypes,
                resource_path=resource_types_and_pathes_dict[resource_type],
                checks=(("metadata", "name"), ("metadata", "uid")),
            )
