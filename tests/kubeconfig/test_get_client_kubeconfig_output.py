# flake8: noqa: PID001
import os
import shutil
import stat

import pytest
import yaml
from ocp_resources.node import Node
from ocp_resources.resource import get_client


@pytest.fixture()
def output_dir(tmp_path):
    yield tmp_path
    shutil.rmtree(str(tmp_path), ignore_errors=True)


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


class TestGetClientNoOutputFile:
    """Regression: get_client without kubeconfig_output_path."""

    def test_get_client_without_output_path(self, kubeconfig_path):
        client = get_client(config_file=kubeconfig_path)
        assert client is not None
        _assert_nodes(client=client)

    def test_get_client_without_output_path_no_kube_set(self):
        client = get_client()
        assert client is not None
        _assert_nodes(client=client)


class TestGetClientKubeconfigOutput:
    """Each code path with kubeconfig_output_path, then use saved file."""

    def test_config_dict_path(self, kubeconfig_dict, output_dir):
        """config_dict provided: writes dict as YAML, then use it."""
        output = str(output_dir / "from_config_dict.kubeconfig")

        client = get_client(config_dict=kubeconfig_dict, kubeconfig_output_path=output)
        assert client is not None
        _assert_nodes(client=client)

        assert os.path.isfile(output)
        _assert_file_permissions(path=output)

        with open(output) as f:
            saved = yaml.safe_load(f)
        assert saved == kubeconfig_dict

        new_client = get_client(config_file=output)
        _assert_nodes(client=new_client)

    def test_host_token_path(self, host_and_token, output_dir):
        """host+token provided: builds kubeconfig from scratch, then use it."""
        host, token, verify_ssl = host_and_token
        output = str(output_dir / "from_host_token.kubeconfig")

        client = get_client(
            host=host,
            token=token,
            verify_ssl=verify_ssl,
            kubeconfig_output_path=output,
        )
        assert client is not None
        _assert_nodes(client=client)

        assert os.path.isfile(output)
        _assert_file_permissions(path=output)

        with open(output) as f:
            saved = yaml.safe_load(f)
        assert saved["clusters"][0]["cluster"]["server"] == host
        assert "users" in saved
        assert "contexts" in saved

        new_client = get_client(config_file=output)
        _assert_nodes(client=new_client)

    def test_host_username_password_path(self, host_username_and_password, output_dir):
        """host+username+password provided: builds kubeconfig, then use it."""
        host, username, password, verify_ssl = host_username_and_password
        output = str(output_dir / "from_host_username_password.kubeconfig")

        client = get_client(
            host=host,
            username=username,
            password=password,
            verify_ssl=verify_ssl,
            kubeconfig_output_path=output,
        )
        assert client is not None
        _assert_nodes(client=client)

        assert os.path.isfile(output)
        _assert_file_permissions(path=output)

        with open(output) as fh:
            saved = yaml.safe_load(fh)
        assert saved["clusters"][0]["cluster"]["server"] == host
        assert "users" in saved
        assert "contexts" in saved

        new_client = get_client(config_file=output)
        _assert_nodes(client=new_client)

    def test_nested_directory_creation(self, kubeconfig_path, output_dir):
        """Verify parent directories are created automatically."""
        output = str(output_dir / "deep" / "nested" / "dir" / "output.kubeconfig")

        client = get_client(config_file=kubeconfig_path, kubeconfig_output_path=output)
        assert client is not None
        assert os.path.isfile(output)
        _assert_file_permissions(path=output)

        new_client = get_client(config_file=output)
        _assert_nodes(client=new_client)
