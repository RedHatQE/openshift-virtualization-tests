# flake8: noqa: PID001
import os
import stat

import pytest
import yaml
from ocp_resources.node import Node
from ocp_resources.resource import get_client


@pytest.fixture()
def kubeconfig_path():
    path = os.environ.get("KUBECONFIG")
    if not path:
        pytest.xfail("KUBECONFIG env var not set")
    if not os.path.isfile(path):
        pytest.xfail(f"KUBECONFIG file not found: {path}")
    return path


@pytest.fixture()
def kubeconfig_dict(kubeconfig_path):
    with open(kubeconfig_path) as f:
        return yaml.safe_load(f)


@pytest.fixture()
def host_and_token(kubeconfig_dict):
    cluster = kubeconfig_dict["clusters"][0]["cluster"]
    host = cluster["server"]

    user = kubeconfig_dict["users"][0]["user"]
    token = user.get("token")
    if not token:
        pytest.xfail("No token in kubeconfig (may use client certs)")

    verify_ssl = not cluster.get("insecure-skip-tls-verify", False)
    return host, token, verify_ssl


@pytest.fixture()
def host_username_and_password(request):
    host = request.session.config.getoption("--remote_cluster_host")
    username = request.session.config.getoption("--remote_cluster_username")
    password = request.session.config.getoption("--remote_cluster_password")

    if not all([host, username, password]):
        pytest.xfail(
            "--remote_cluster_host, --remote_cluster_username, and/or --remote_cluster_password CLI args not provided"
        )

    verify_ssl = False
    return host, username, password, verify_ssl


def _assert_nodes(client):
    nodes = list(Node.get(dyn_client=client))
    assert nodes, "Should find at least one node"
    return nodes


def _assert_file_permissions(path):
    perms = stat.S_IMODE(os.stat(path).st_mode)
    assert perms == 0o600, f"Expected 0o600, got {oct(perms)}"


def _cleanup_kubeconfig(path):
    if path and os.path.exists(path):
        os.unlink(path)


class TestGetClientNoGenerateKubeconfig:
    """Regression: get_client without generate_kubeconfig."""

    def test_get_client_without_generate_kubeconfig(self, kubeconfig_path):
        client = get_client(config_file=kubeconfig_path)
        assert client is not None
        _assert_nodes(client=client)

    def test_get_client_without_generate_kubeconfig_no_kube_set(self):
        client = get_client()
        assert client is not None
        _assert_nodes(client=client)


class TestGetClientGenerateKubeconfig:
    """Each code path with generate_kubeconfig=True, then use saved file."""

    def test_generate_kubeconfig_config_dict(self, kubeconfig_dict):
        """config_dict provided with generate_kubeconfig=True: writes dict as YAML, then use it."""
        kubeconfig_output_path = None
        try:
            client, kubeconfig_output_path = get_client(config_dict=kubeconfig_dict, generate_kubeconfig=True)
            assert client is not None
            _assert_nodes(client=client)

            assert os.path.isfile(kubeconfig_output_path)
            _assert_file_permissions(path=kubeconfig_output_path)

            with open(kubeconfig_output_path) as f:
                saved = yaml.safe_load(f)
            assert saved == kubeconfig_dict

            new_client = get_client(config_file=kubeconfig_output_path)
            _assert_nodes(client=new_client)
        finally:
            _cleanup_kubeconfig(path=kubeconfig_output_path)

    def test_generate_kubeconfig_host_token(self, host_and_token):
        """host+token provided with generate_kubeconfig=True: builds kubeconfig from scratch, then use it."""
        host, token, verify_ssl = host_and_token
        kubeconfig_output_path = None
        try:
            client, kubeconfig_output_path = get_client(
                host=host,
                token=token,
                verify_ssl=verify_ssl,
                generate_kubeconfig=True,
            )
            assert client is not None
            _assert_nodes(client=client)

            assert os.path.isfile(kubeconfig_output_path)
            _assert_file_permissions(path=kubeconfig_output_path)

            with open(kubeconfig_output_path) as f:
                saved = yaml.safe_load(f)
            assert saved["clusters"][0]["cluster"]["server"] == host
            assert "users" in saved
            assert "contexts" in saved

            new_client = get_client(config_file=kubeconfig_output_path)
            _assert_nodes(client=new_client)
        finally:
            _cleanup_kubeconfig(path=kubeconfig_output_path)

    def test_generate_kubeconfig_host_username_password(self, host_username_and_password):
        """host+username+password provided with generate_kubeconfig=True: builds kubeconfig, then use it.

        Note: the saved kubeconfig will contain a token (extracted via _resolve_bearer_token
        from the bearer auth), not username+password.
        """
        host, username, password, verify_ssl = host_username_and_password
        kubeconfig_output_path = None
        try:
            client, kubeconfig_output_path = get_client(
                host=host,
                username=username,
                password=password,
                verify_ssl=verify_ssl,
                generate_kubeconfig=True,
            )
            assert client is not None
            _assert_nodes(client=client)

            assert os.path.isfile(kubeconfig_output_path)
            _assert_file_permissions(path=kubeconfig_output_path)

            with open(kubeconfig_output_path) as fh:
                saved = yaml.safe_load(fh)
            assert saved["clusters"][0]["cluster"]["server"] == host
            assert "users" in saved
            assert "contexts" in saved

            new_client = get_client(config_file=kubeconfig_output_path)
            _assert_nodes(client=new_client)
        finally:
            _cleanup_kubeconfig(path=kubeconfig_output_path)
