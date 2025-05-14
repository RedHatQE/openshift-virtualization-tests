import logging

import pytest
from ocp_resources.virtual_machine_clone import VirtualMachineClone

from tests.virt.cluster.vm_cloning.utils import wait_cloning_job_source_not_exist_reason

LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "cloning_job_bad_params",
    [
        pytest.param(
            {"source_name": "non-existing-vm", "source_kind": "VirtualMachine"},
            marks=pytest.mark.polarion("CNV-10302"),
            id="VirtualMachine_as_source",
        ),
        pytest.param(
            {
                "source_name": "non-existing-vm-snapshot",
                "source_kind": "VirtualMachineSnapshot",
            },
            marks=[
                pytest.mark.polarion("CNV-10303"),
                # TODO: this won't be backported to 4.19; need to remove test after 4.19 branch created
                pytest.mark.jira("CNV-42213", run=False),
            ],
            id="VirtualMachineSnapshot_as_source",
        ),
    ],
)
def test_cloning_job_if_source_not_exist_negative(namespace, cloning_job_bad_params):
    with VirtualMachineClone(
        name="clone-job-negative-test",
        namespace=namespace.name,
        source_name=cloning_job_bad_params["source_name"],
        source_kind=cloning_job_bad_params["source_kind"],
    ) as vmc:
        wait_cloning_job_source_not_exist_reason(vmc=vmc)
