import pytest

pytestmark = pytest.mark.remote_cluster


def test_remote_client(remote_admin_client):
    assert remote_admin_client is not None
