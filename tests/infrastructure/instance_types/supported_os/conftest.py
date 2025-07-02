import pytest


@pytest.fixture(scope="class")
def skip_if_rhel8(instance_type_rhel_os_matrix__module__):
    current_rhel_name = [*instance_type_rhel_os_matrix__module__][0]
    if current_rhel_name == "rhel-8":
        pytest.xfail("EFI is not enabled by default before RHEL9")
