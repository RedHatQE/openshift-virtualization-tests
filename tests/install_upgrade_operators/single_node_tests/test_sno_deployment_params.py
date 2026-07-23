import pytest

from utilities.constants.components import VIRT_OPERATOR

pytestmark = pytest.mark.sno


@pytest.mark.polarion("CNV-8374")
def test_cnv_deployment_sno_one_replica_set(subtests, discovered_cnv_deployments):
    for deployment in discovered_cnv_deployments:
        with subtests.test(msg=deployment.name):
            deployment_instance = deployment.instance
            deployment_name = deployment.name
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
                f"spec.replicas: {deployment_spec_replicas}, expected number of replicas: {expected_replica}"
            )
