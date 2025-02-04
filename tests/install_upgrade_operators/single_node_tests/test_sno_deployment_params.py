import pytest

from utilities.constants import VIRT_OPERATOR

pytestmark = pytest.mark.sno


@pytest.mark.polarion("CNV-8374")
def test_cnv_deployment_sno_one_replica_set(cnv_deployment_by_name):
    deployment_instance = cnv_deployment_by_name.instance
    deployment_name = cnv_deployment_by_name.name
    deployment_status_replicas = deployment_instance.status.replicas
    deployment_spec_replicas = deployment_instance.spec.replicas

    expected_replica = 2 if deployment_name == VIRT_OPERATOR else 1

    assert deployment_status_replicas == expected_replica, (
        f"On SNO cluster deployment {deployment_name} number of "
        f"status.replicas: {deployment_status_replicas}, expected number of "
        f"replicas: {expected_replica}"
    )
    assert deployment_spec_replicas == expected_replica, (
        f"On SNO cluster deployment {deployment_name} number of "
        f"spec.replicas: {deployment_spec_replicas}, expected number of  replicas: {expected_replica}"
    )
