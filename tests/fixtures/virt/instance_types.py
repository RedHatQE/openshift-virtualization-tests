import copy

import pytest
from ocp_resources.virtual_machine_instancetype import VirtualMachineInstancetype
from ocp_resources.virtual_machine_preference import VirtualMachinePreference


@pytest.fixture(scope="class")
def common_instance_type_param_dict(request):
    common_instance_dict = {
        "name": request.param["name"],
        "cpu": {"guest": request.param.get("preferred_cpu_topology_value", 1)},
        "memory": {"guest": request.param["memory_requests"]},
    }
    if request.param.get("dedicated_cpu_placement"):
        common_instance_dict["cpu"]["dedicated_cpu_placement"] = request.param["dedicated_cpu_placement"]
    if request.param.get("cpu_model"):
        common_instance_dict["cpu"]["model"] = request.param["cpu_model"]
    if request.param.get("cpu_isolate_emulator_thread") is not None:
        common_instance_dict["cpu"]["isolateEmulatorThread"] = request.param["cpu_isolate_emulator_thread"]
    if request.param.get("cpu_numa"):
        common_instance_dict["cpu"]["numa"] = request.param["cpu_numa"]
    if request.param.get("cpu_realtime"):
        common_instance_dict["cpu"]["realtime"] = request.param["cpu_realtime"]
    if request.param.get("cpu_max_sockets"):
        common_instance_dict["cpu"]["maxSockets"] = request.param["cpu_max_sockets"]
    if request.param.get("gpus_list"):
        common_instance_dict["gpus"] = request.param["gpus_list"]
    if request.param.get("host_devices_list"):
        common_instance_dict["host_devices"] = request.param["host_devices_list"]
    if request.param.get("io_thread_policy"):
        common_instance_dict["io_threads_policy"] = request.param["io_thread_policy"]
    if request.param.get("memory_huge_pages"):
        common_instance_dict["memory"]["hugepages"] = request.param["memory_huge_pages"]
    if request.param.get("memory_max_guest"):
        common_instance_dict["memory"]["maxGuest"] = request.param["memory_max_guest"]
    return common_instance_dict


@pytest.fixture(scope="class")
def instance_type_for_test_scope_class(namespace, common_instance_type_param_dict):
    instance_type_param_dict = copy.deepcopy(common_instance_type_param_dict)
    instance_type_param_dict["namespace"] = namespace.name
    return VirtualMachineInstancetype(**instance_type_param_dict)


@pytest.fixture(scope="class")
def common_vm_preference_param_dict(request):
    common_preference_dict = {
        "name": request.param["name"],
        "client": request.param.get("client"),
        "teardown": request.param.get("teardown", True),
        "yaml_file": request.param.get("yaml_file"),
    }
    if request.param.get("clock_timezone") or request.param.get("clock_utc_seconds_offset"):
        common_preference_dict["clock"] = {
            "preferredClockOffset": {
                "timezone": request.param.get("clock_timezone"),
                "utc": {"offsetSeconds": request.param.get("clock_utc_seconds_offset")},
            }
        }
    if request.param.get("clock_preferred_timer"):
        common_preference_dict.setdefault("clock", {})["preferredTimer"] = request.param["clock_preferred_timer"]

    if request.param.get("cpu_topology"):
        common_preference_dict["cpu"] = {"preferredCPUTopology": request.param["cpu_topology"]}
    if request.param.get("devices"):
        common_preference_dict["devices"] = request.param["devices"]
    if request.param.get("features"):
        common_preference_dict["features"] = request.param["features"]
    if request.param.get("firmware"):
        common_preference_dict["firmware"] = request.param["firmware"]
    if request.param.get("machine_type"):
        common_preference_dict["machine"] = {"preferredMachineType": request.param["machine_type"]}
    if request.param.get("storage_class"):
        common_preference_dict["volumes"] = {"preferredStorageClassName": request.param["storage_class"]}
    if request.param.get("cpu_spread_option"):
        common_preference_dict.setdefault("cpu", {}).update({"spreadOption": request.param.get("cpu_spread_option")})
    return common_preference_dict


@pytest.fixture(scope="class")
def vm_preference_for_test(namespace, common_vm_preference_param_dict):
    vm_preference_param_dict = copy.deepcopy(common_vm_preference_param_dict)
    vm_preference_param_dict["namespace"] = namespace.name
    return VirtualMachinePreference(**vm_preference_param_dict)
