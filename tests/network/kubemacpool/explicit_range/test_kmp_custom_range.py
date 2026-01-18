import pytest


@pytest.mark.polarion("CNV-12568")
def test_kmp_random_custom_range_hco(
    custom_range_hco_mac_pool,
    custom_mac_range_vm,
):
    for iface in custom_mac_range_vm.get_interfaces():
        assert custom_range_hco_mac_pool.mac_is_within_range(mac=iface.macAddress), (
            f"Testing interface {iface.name} failed"
        )
