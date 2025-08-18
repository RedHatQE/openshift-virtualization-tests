from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable

import pytest
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.resource import ResourceEditor


@contextmanager
def label_mcps(mcps: list[MachineConfigPool], labels: dict):
    updates = [ResourceEditor({mcp: {"metadata": {"labels": labels}}}) for mcp in mcps]

    for update in updates:
        update.update(backup_resources=True)
    yield mcps
    for update in updates:
        update.restore()


def capture_func_elapsed(cache: pytest.Cache, cache_key_prefix: str, func: Callable, **kwargs: Any) -> Any:
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
