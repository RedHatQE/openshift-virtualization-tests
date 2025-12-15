from __future__ import annotations

import os
import time

from ocp_scale_utilities.threaded.scale import ThreadedScaleResources

from utilities.data_collector import (
    collect_alerts_data,
    collect_default_cnv_must_gather_with_vm_gather,
    collect_ocp_must_gather,
    get_data_collector_dir,
)


class LocalThreadedScaleResources(ThreadedScaleResources):  # skip-unused-code
    def collect_data(self, id: str, start_time: float):  # skip-unused-code
        target_dir = os.path.join(get_data_collector_dir(), "ThreadedScaleResources", id)

        collect_alerts_data()
        collect_ocp_must_gather(since_time=int(time.time() - start_time))
        collect_default_cnv_must_gather_with_vm_gather(since_time=int(time.time() - start_time), target_dir=target_dir)
