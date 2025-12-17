from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Generator

import pytest
import yaml
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.resource import ResourceEditor


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


def pause_mcps(paused: bool, mcps: list[MachineConfigPool]) -> None:  # skip-unused-code
    ResourceEditor(patches={mcp: {"spec": {"paused": paused}} for mcp in mcps}).update()


@contextmanager
def label_mcps(mcps: list[MachineConfigPool], labels: dict) -> Generator[list[MachineConfigPool]]:  # skip-unused-code
    updates = [ResourceEditor({mcp: {"metadata": {"labels": labels}}}) for mcp in mcps]

    for update in updates:
        update.update(backup_resources=True)
    yield mcps
    for update in updates:
        update.restore()


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
