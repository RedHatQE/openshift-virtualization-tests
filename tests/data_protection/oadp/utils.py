import logging

from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.restore import Restore

from utilities.constants import (
    ADP_NAMESPACE,
    TIMEOUT_5MIN,
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
)
from utilities.infra import (
    unique_name,
)
from utilities.oadp import delete_velero_resource

LOGGER = logging.getLogger(__name__)


class VeleroRestore(Restore):
    def __init__(
        self,
        name,
        namespace=ADP_NAMESPACE,
        included_namespaces=None,
        backup_name=None,
        client=None,
        teardown=False,
        yaml_file=None,
        wait_complete=True,
        timeout=TIMEOUT_5MIN,
        **kwargs,
    ):
        super().__init__(
            name=unique_name(name=name),
            namespace=namespace,
            included_namespaces=included_namespaces,
            backup_name=backup_name,
            client=client,
            teardown=teardown,
            yaml_file=yaml_file,
            **kwargs,
        )
        self.wait_complete = wait_complete
        self.timeout = timeout

    def __enter__(self):
        super().__enter__()
        if self.wait_complete:
            self.wait_for_status(
                status=self.Status.COMPLETED,
                timeout=self.timeout,
            )
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        delete_velero_resource(resource=self, client=self.client)


def wait_for_restored_dv(dv):
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)
