import pytest
from kubernetes.client import ApiException
from ocp_resources.virtual_machine_clone import VirtualMachineClone


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
            marks=pytest.mark.polarion("CNV-10303"),
            id="VirtualMachineSnapshot_as_source",
        ),
    ],
)
def test_cloning_job_if_source_not_exist_negative(namespace, cloning_job_bad_params):
    with pytest.raises(
        ApiException,
        match=rf".* {cloning_job_bad_params['source_kind']} {cloning_job_bad_params['source_name']} does not exist .*",
    ):
        with VirtualMachineClone(
            name="clone-job-negative-test",
            namespace=namespace.name,
            source_name=cloning_job_bad_params["source_name"],
            source_kind=cloning_job_bad_params["source_kind"],
        ):
            pytest.fail("Cloning job created with non-existing source")
