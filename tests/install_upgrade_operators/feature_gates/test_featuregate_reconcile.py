import pytest

pytestmark = [pytest.mark.sno, pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


class TestHardcodedFeatureGates:
    @pytest.mark.polarion("CNV-6427")
    def test_managed_cr_featuregate_reconcile_kubevirt(
        self, initial_kubevirt_fg, removed_kubevirt_fg, kubevirt_fg_after_removed
    ):
        assert initial_kubevirt_fg == kubevirt_fg_after_removed, (
            f"KubeVirt featureGates not reconciled. Expected: {initial_kubevirt_fg}, actual: {kubevirt_fg_after_removed}"
        )

    @pytest.mark.polarion("CNV-6640")
    def test_managed_cr_featuregate_reconcile_cdi(self, initial_cdi_fg, removed_cdi_fg, cdi_fg_after_removed):
        assert initial_cdi_fg == cdi_fg_after_removed, (
            f"CDI featureGates not reconciled. Expected: {initial_cdi_fg}, actual: {cdi_fg_after_removed}"
        )
