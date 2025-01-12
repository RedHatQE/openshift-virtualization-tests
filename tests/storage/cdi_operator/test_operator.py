import pytest
from ocp_resources.cdi import CDI
from ocp_resources.pod import Pod


@pytest.mark.destructive
@pytest.mark.polarion("CNV-2512")
def test_cr_deletion(admin_client, hco_namespace, cdi):
    # Ensure 'Deployed' status
    assert cdi.status == CDI.Status.DEPLOYED

    # Delete CDI resource
    cdi.delete()

    # Ensure CDI resource was deleted
    cdi.wait_for_status(status=CDI.Status.DEPLOYING)

    # Wait for 'Deployed' status again
    cdi.wait_for_status(status=CDI.Status.DEPLOYED)

    # Get CDI pods
    cdi_pods = list(
        Pod.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            label_selector="cdi.kubevirt.io",
        )
    )
    for pod in cdi_pods:
        pod.wait_for_status(status=Pod.Status.RUNNING)
