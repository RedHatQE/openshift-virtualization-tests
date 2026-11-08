import copy

import pytest
from ocp_resources.virtual_machine_instancetype import VirtualMachineInstancetype
from ocp_resources.virtual_machine_preference import VirtualMachinePreference

# Fixture parameter name to instancetype API field name, per spec section.
INSTANCE_TYPE_CPU_PARAM_TO_FIELD = {
    "dedicated_cpu_placement": "dedicated_cpu_placement",
    "cpu_model": "model",
    "cpu_numa": "numa",
    "cpu_realtime": "realtime",
    "cpu_max_sockets": "maxSockets",
}
INSTANCE_TYPE_MEMORY_PARAM_TO_FIELD = {
    "memory_huge_pages": "hugepages",
    "memory_max_guest": "maxGuest",
}
INSTANCE_TYPE_TOP_LEVEL_PARAM_TO_FIELD = {
    "gpus_list": "gpus",
    "host_devices_list": "host_devices",
    "io_thread_policy": "io_threads_policy",
}


def _add_optional_params(*, param_dict: dict, spec: dict, param_to_field: dict[str, str]) -> None:
    """Copy the optional fixture parameters that are set into the spec under their API field names."""
    for param_name, field_name in param_to_field.items():
        if param_dict.get(param_name):
            spec[field_name] = param_dict[param_name]


@pytest.fixture(scope="class")
def common_instance_type_param_dict(request):
    cpu_spec = {"guest": request.param.get("preferred_cpu_topology_value", 1)}
    if request.param.get("cpu_isolate_emulator_thread") is not None:
        cpu_spec["isolateEmulatorThread"] = request.param["cpu_isolate_emulator_thread"]
    _add_optional_params(param_dict=request.param, spec=cpu_spec, param_to_field=INSTANCE_TYPE_CPU_PARAM_TO_FIELD)

    memory_spec = {"guest": request.param["memory_requests"]}
    _add_optional_params(param_dict=request.param, spec=memory_spec, param_to_field=INSTANCE_TYPE_MEMORY_PARAM_TO_FIELD)

    common_instance_dict = {"name": request.param["name"], "cpu": cpu_spec, "memory": memory_spec}
    _add_optional_params(
        param_dict=request.param, spec=common_instance_dict, param_to_field=INSTANCE_TYPE_TOP_LEVEL_PARAM_TO_FIELD
    )
    return common_instance_dict


@pytest.fixture(scope="class")
def instance_type_for_test_scope_class(namespace, common_instance_type_param_dict):
    instance_type_param_dict = copy.deepcopy(common_instance_type_param_dict)
    instance_type_param_dict["namespace"] = namespace.name
    instance_type_param_dict["client"] = namespace.client
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
    if vm_preference_param_dict.get("client") is None:
        vm_preference_param_dict["client"] = namespace.client
    return VirtualMachinePreference(**vm_preference_param_dict)
