from __future__ import annotations

import time
from typing import Any

from ocp_scale_utilities.threaded.scale import ThreadedScaleResources
from ocp_scale_utilities.threaded.utils import (
    threaded_delete_resources,
    threaded_deploy_requested_resources,
    threaded_deploy_resources,
    threaded_wait_deleted_resources,
    threaded_wait_for_resources_status,
)


class LocalThreadedScaleResources(ThreadedScaleResources):
    def __enter__(self) -> ThreadedScaleResources:
        with self._cleanup_on_error(stack_exit=super().__exit__):
            start_time = time.time()
            if self.request_resources:
                threaded_deploy_requested_resources(
                    resources=self.resources, request_resources=self.request_resources, exit_stack=self
                )
            else:
                threaded_deploy_resources(resources=self.resources, exit_stack=self)

            if self.wait_for_status:
                threaded_wait_for_resources_status(resources=self.resources, status=self.wait_for_status)

            stop_time = time.time()
            if self.pytest_cache and self.cache_key_prefix:
                self.pytest_cache.set(f"{self.cache_key_prefix}-deploy-count", len(self.resources))
                self.pytest_cache.set(f"{self.cache_key_prefix}-deploy-start", start_time)
                self.pytest_cache.set(f"{self.cache_key_prefix}-deploy-stop", stop_time)
                self.pytest_cache.set(f"{self.cache_key_prefix}-deploy-elapsed", stop_time - start_time)
        return self

    def __exit__(self: ThreadedScaleResources, *exc_arguments: Any) -> Any:
        """
        Delete all resources, mark the start and end fields.
        Deletion when exiting context manager will unwind ExitStack,
        including any sleeps between batches.
        Wait for resources to be deleted in reverse order of creation.
        """
        with self._cleanup_on_error(stack_exit=super().__exit__):
            start_time = time.time()
            threaded_delete_resources(resources=self.resources)
            threaded_wait_deleted_resources(resources=self.resources)
            stop_time = time.time()
            if self.pytest_cache and self.cache_key_prefix:
                self.pytest_cache.set(f"{self.cache_key_prefix}-delete-count", len(self.resources))
                self.pytest_cache.set(f"{self.cache_key_prefix}-delete-start", start_time)
                self.pytest_cache.set(f"{self.cache_key_prefix}-delete-stop", stop_time)
                self.pytest_cache.set(f"{self.cache_key_prefix}-delete-elapsed", stop_time - start_time)
