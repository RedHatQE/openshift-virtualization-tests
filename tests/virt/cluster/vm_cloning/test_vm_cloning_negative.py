import logging

import pytest
from ocp_resources.virtual_machine_clone import VirtualMachineClone
from timeout_sampler import retry

from utilities.constants import TIMEOUT_1SEC, TIMEOUT_10SEC

LOGGER = logging.getLogger(__name__)


class VirtualMachineCloneConditionRunningError(Exception):
    pass


@retry(
    wait_timeout=TIMEOUT_10SEC,
    sleep=TIMEOUT_1SEC,
    exceptions_dict={VirtualMachineCloneConditionRunningError: []},
)
def wait_cloning_job_source_not_exist_reason(vmc: VirtualMachineClone) -> bool:
    vmc_source = vmc.instance.spec.source
    expected_reason = f"Source doesnt exist: {vmc_source.kind} {vmc.namespace}/{vmc_source.name}"
    current_reason = [
        condition.reason
        for condition in vmc.instance.status.conditions
        if condition.type == VirtualMachineClone.Condition.READY
    ][0]
    if current_reason == expected_reason:
        return True
    raise VirtualMachineCloneConditionRunningError(
        f'VMClone error reason is "{current_reason}" expected is "{expected_reason}"'
    )


@pytest.mark.parametrize(
    "cloning_job_bad_params",
    [
        pytest.param(
            {"source_name": "non-existing-vm", "source_kind": "VirtualMachine"},
            marks=pytest.mark.polarion("CNV-10302"),
            id="VirtualMachine_as_source",
        ),
        pytest.param(  # TODO: this won't be backported to 4.19; need to remove test after 4.19 created
            {
                "source_name": "non-existing-vm-snapshot",
                "source_kind": "VirtualMachineSnapshot",
            },
            marks=[pytest.mark.polarion("CNV-10303"), pytest.mark.jira("CNV-42213", run=False)],
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
