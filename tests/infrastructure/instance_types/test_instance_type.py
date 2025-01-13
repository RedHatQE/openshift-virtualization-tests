import pytest

pytestmark = pytest.mark.gating


MEMORY_REQUESTS_FOR_TEST = {"memory_requests": "2Gi"}


@pytest.fixture()
def created_instance_type_for_test_scope_function(instance_type_for_test_scope_function):
    with instance_type_for_test_scope_function as instance_type:
        yield instance_type


@pytest.fixture()
def created_cluster_instance_type_for_test_scope_function(cluster_instance_type_for_test_scope_function):
    with cluster_instance_type_for_test_scope_function as cluster_instance_type:
        yield cluster_instance_type


@pytest.mark.parametrize(
    "common_instance_type_param_dict",
    [
        pytest.param(
            {
                **{
                    "name": "all-options-instance-type",
                    "cpu_isolate_emulator_thread": False,
                    "cpu_model": "demi-cpu-model",
                    "cpu_numa": {"guestMappingPassthrough": {}},
                    "gpus_list": [
                        {
                            "deviceName": "demi-gpu-device-name",
                            "name": "demi-gpu-name",
                            "tag": "demi-gpu-tag",
                            "virtualGPUOptions": {
                                "display": {
                                    "enabled": False,
                                    "ramFB": {"enabled": True},
                                },
                            },
                        }
                    ],
                    "host_devices_list": [
                        {
                            "deviceName": "demi-host-device-name",
                            "name": "demi-host-name",
                            "tag": "demi-host-tag",
                        }
                    ],
                    "io_thread_policy": "demi-io-thread-policy",
                    "launch_security": {"sev": {}},
                    "memory_huge_pages": {"pageSize": "1Gi"},
                    "cpu_max_sockets": 4,
                    "memory_max_guest": "4Gi",
                },
                **MEMORY_REQUESTS_FOR_TEST,
            },
        ),
    ],
    indirect=True,
)
class TestInstanceTypesCreation:
    @pytest.mark.polarion("CNV-9082")
    def test_create_instance_type(self, created_instance_type_for_test_scope_function):
        assert created_instance_type_for_test_scope_function.exists

    @pytest.mark.polarion("CNV-9103")
    def test_create_cluster_instance_type(self, created_cluster_instance_type_for_test_scope_function):
        assert created_cluster_instance_type_for_test_scope_function.exists
