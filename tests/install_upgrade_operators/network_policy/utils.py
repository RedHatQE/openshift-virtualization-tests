import shlex

TEST_SERVER_PORT = 9876
TEST_SERVER_APP_LABEL = "network-policy-server"


def build_curl_command(service_ip: str, server_port: int, https: bool = False) -> list[str]:
    """
    Build a curl command to test connectivity to a service.

    Args:
        service_ip: The IP address of the service
        server_port: The port number of the service
        https: Whether to use HTTPS (default: False)

    Returns:
        List of command arguments ready to be passed to pod.execute()
    """
    protocol = "https" if https else "http"
    insecure_flag = "-k" if https else ""
    curl_cmd = f"curl -sS {insecure_flag} --connect-timeout 5 {protocol}://{service_ip}:{server_port}"
    return shlex.split(curl_cmd)
