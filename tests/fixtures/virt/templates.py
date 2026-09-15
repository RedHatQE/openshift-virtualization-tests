import pytest

from utilities.virt import get_base_templates_list


@pytest.fixture(scope="module")
def base_templates(admin_client):
    return get_base_templates_list(client=admin_client)
