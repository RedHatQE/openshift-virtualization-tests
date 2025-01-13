import pytest
from ocp_resources.pod_disruption_budget import PodDisruptionBudget

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.fixture()
def cnv_pdb_resources(admin_client, hco_namespace):
    return list(PodDisruptionBudget.get(dyn_client=admin_client, namespace=hco_namespace.name))


@pytest.mark.polarion("CNV-8514")
def test_virt_pdbs_not_found_in_sno_cluster(skip_if_not_sno_cluster, cnv_pdb_resources):
    pdbs_failed = [pdb.name for pdb in cnv_pdb_resources if pdb.name.startswith("virt-")]
    assert not pdbs_failed, f"Virt PDBs {pdbs_failed} found in sno cluster."
