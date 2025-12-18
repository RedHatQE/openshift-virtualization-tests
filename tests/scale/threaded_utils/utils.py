from __future__ import annotations

import os
import time
from typing import Sequence

from kubernetes.dynamic import DynamicClient
from ocp_resources.resource import Resource
from ocp_scale_utilities.threaded.scale import ThreadedScaleResources
from pytest import Cache

from utilities.data_collector import (
    collect_alerts_data,
    collect_default_cnv_must_gather_with_vm_gather,
    collect_ocp_must_gather,
    get_data_collector_dir,
)


class LocalThreadedScaleResources(ThreadedScaleResources):  # skip-unused-code
    def __init__(
        self,
        resources: Sequence[Resource],
        request_resources: Sequence[Resource] | None = None,
        pytest_cache: Cache | None = None,
        cache_key_prefix: str | None = None,
        wait_for_status: str | None = None,
        admin_client: DynamicClient | None = None,
    ) -> None:  # skip-unused-code
        self.admin_client = admin_client
        super().__init__(
            resources=resources,
            request_resources=request_resources,
            pytest_cache=pytest_cache,
            cache_key_prefix=cache_key_prefix,
            wait_for_status=wait_for_status,
        )

    def collect_data(self, id: str, start_time: float) -> None:  # skip-unused-code
        target_dir = os.path.join(get_data_collector_dir(), "ThreadedScaleResources", id)

        collect_alerts_data()
        collect_ocp_must_gather(since_time=int(time.time() - start_time))
        if self.admin_client:
            collect_default_cnv_must_gather_with_vm_gather(
                since_time=int(time.time() - start_time), target_dir=target_dir, admin_client=self.admin_client
            )
