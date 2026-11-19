import logging

import pytest
from ocp_resources.virtual_machine_clone import VirtualMachineClone

from tests.virt.cluster.vm_cloning.utils import wait_cloning_job_source_not_exist_reason

LOGGER = logging.getLogger(__name__)


@pytest.mark.s390x
@pytest.mark.parametrize(
    "cloning_job_bad_params",
    [
        pytest.param(
            {"source_name": "non-existing-vm", "source_kind": "VirtualMachine"},
            id="VirtualMachine_as_source",
        ),
        pytest.param(
            {
                "source_name": "non-existing-vm-snapshot",
                "source_kind": "VirtualMachineSnapshot",
            },
            id="VirtualMachineSnapshot_as_source",
        ),
    ],
)
def test_cloning_job_if_source_not_exist_negative(unprivileged_client, namespace, cloning_job_bad_params):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-6042 # <skip-jira-utils-check>
    Polarion: CNV-10302
    Polarion: CNV-10303
    """
    with VirtualMachineClone(
        name="clone-job-negative-test",
        namespace=namespace.name,
        client=unprivileged_client,
        source_name=cloning_job_bad_params["source_name"],
        source_kind=cloning_job_bad_params["source_kind"],
    ) as vmc:
        wait_cloning_job_source_not_exist_reason(vmc=vmc)
