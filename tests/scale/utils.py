from __future__ import annotations

import time
from contextlib import ExitStack, contextmanager
from typing import Any, Callable, Generator, Sequence

import pytest
import yaml
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.resource import Resource, ResourceEditor

from utilities.operator import (
    get_machine_config_pools_conditions,
    get_mcp_updating_transition_times,
    wait_for_mcp_update_end,
    wait_for_mcp_update_start,
)


def get_user_kubeconfig_context(kubeconfig_filename: str, username: str) -> str:  # skip-unused-code
    """
    In order to modify the kubeconfig client configuration with additional args,
    the context that is required for a specific user must be specified when calling get_client()

    eg:
        client_configuration = kubernetes.client.Configuration()
        client_configuration.connection_pool_maxsize = request.param["connection_pool_maxsize"]
        get_client(
            client_configuration=deepcopy(client_configuration),
            config_file=exported_kubeconfig,
            context=get_user_kubeconfig_context(kubeconfig_filename=exported_kubeconfig, username=UNPRIVILEGED_USER),
        )
    """
    with open(kubeconfig_filename, "r") as file:
        kubeconfig_content = yaml.safe_load(file)

    all_contexts = kubeconfig_content["contexts"]
    current_context = kubeconfig_content["current-context"]
    current_cluster = next(
        (entry["context"]["cluster"] for entry in all_contexts if entry["name"] == current_context),
        None,
    )
    assert current_cluster, f"No context found named {current_context!r}"

    user_context = None
    for entry in all_contexts:
        context = entry["context"]
        if context["cluster"] == current_cluster and context["user"] == f"{username}/{current_cluster}":
            user_context = entry["name"]
            break

    assert user_context, "No context found for user"
    return user_context


def capture_func_elapsed(
    cache: pytest.Cache, cache_key_prefix: str, func: Callable, **kwargs: Any
) -> Any:  # skip-unused-code
    """
    Capture the start/stop/elapsed of arbitrary functions
    """
    start_time = time.time()
    return_value = func(**kwargs)
    stop_time = time.time()
    cache.set(f"{cache_key_prefix}-start", start_time)
    cache.set(f"{cache_key_prefix}-stop", stop_time)
    cache.set(f"{cache_key_prefix}-elapsed", stop_time - start_time)
    return return_value


class MachineConfigPoolConfiguration(ExitStack):
    def __init__(
        self,
        resources: Sequence[Resource],
        mcp_labels: dict[MachineConfigPool, dict[str, str]],
        timeout: int,
        sleep: int,
    ) -> None:
        """
        Control the machine config pool rollout process for changes,
        such as KubeletConfigs, that affect the cluster behavior

        Args:
            resources (Sequence[Resource]): Resources to create while MCP is paused
            mcp_labels (dict[MachineConfigPool, dict]): Labels to be applied to machine config pools while paused
            timeout (int): Timeout for wait_for_mcp_update_end
            sleep (int): Sleep for wait_for_mcp_update_end

        Example:
            with MachineConfigPoolConfiguration(
                resources=[KubeletConfig(...)],
                mcp_labels={worker_machine_config_pool: {"label": "value"}},
                timeout=TIMEOUT_20MIN * len(workers)
                sleep=TIMEOUT_30SEC
            ):
                yield  # Use cluster with new configuration
        """
        super().__init__()
        self.resources = resources
        self.mcp_labels = mcp_labels
        self.timeout = timeout
        self.sleep = sleep

        self.machine_config_pools = mcp_labels.keys()
        self.mcp_updates = [
            ResourceEditor({mcp: {"metadata": {"labels": labels}}}) for mcp, labels in self.mcp_labels.items()
        ]

    @contextmanager
    def _cleanup_on_error(self, stack_exit) -> Generator[None, Any, None]:
        with ExitStack() as stack:
            stack.push(exit=stack_exit)
            yield
            stack.pop_all()

    def __enter__(self) -> MachineConfigPoolConfiguration:
        initial_updating_transition_times = get_mcp_updating_transition_times(
            mcp_conditions=get_machine_config_pools_conditions(machine_config_pools=self.machine_config_pools)
        )
        with self._cleanup_on_error(stack_exit=super().__exit__):
            with ResourceEditor(patches={mcp: {"spec": {"paused": True}} for mcp in self.machine_config_pools}):
                for resource in self.resources:
                    self.enter_context(cm=resource)
                for mcp_update in self.mcp_updates:
                    mcp_update.update(backup_resources=True)

        wait_for_mcp_update_start(
            machine_config_pools_list=self.machine_config_pools,
            initial_transition_times=initial_updating_transition_times,
        )
        wait_for_mcp_update_end(
            machine_config_pools_list=self.machine_config_pools,
            timeout=self.timeout,
            sleep=self.sleep,
        )
        return self

    def __exit__(self, *exc_arguments: Any) -> Any:
        teardown_updating_transition_times = get_mcp_updating_transition_times(
            mcp_conditions=get_machine_config_pools_conditions(machine_config_pools=self.machine_config_pools)
        )
        with self._cleanup_on_error(stack_exit=super().__exit__):
            with ResourceEditor(patches={mcp: {"spec": {"paused": True}} for mcp in self.machine_config_pools}):
                for mcp_update in self.mcp_updates:
                    mcp_update.restore()
                for resource in self.resources:
                    resource.clean_up()

        wait_for_mcp_update_start(
            machine_config_pools_list=self.machine_config_pools,
            initial_transition_times=teardown_updating_transition_times,
        )
        wait_for_mcp_update_end(
            machine_config_pools_list=self.machine_config_pools,
            timeout=self.timeout,
            sleep=self.sleep,
        )
