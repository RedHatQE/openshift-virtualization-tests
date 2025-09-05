import pytest
from ocp_resources.network_policy import NetworkPolicy
from ocp_resources.pod import Pod
from pyhelper_utils.shell import run_command

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64, pytest.mark.s390x]


cnv_network_policy_parametrize = pytest.mark.parametrize(
    "component_name,port",
    [
        (
            "kubevirt-console-plugin",
            9443,
        ),
        (
            "kubevirt-apiserver-proxy",
            8080,
        ),
    ],
)


@pytest.fixture(scope="module")
def cnv_network_policies(admin_client, hco_namespace):
    """Get all network policies in the CNV namespace"""
    return list(NetworkPolicy.get(dyn_client=admin_client, namespace=hco_namespace.name))


@pytest.fixture
def component_pods_for_test(admin_client, hco_namespace, component_name):
    """Get component pods and return source/target pod info for connectivity testing"""

    def _get_component_pods(admin_client, namespace, component_label, component_name):
        """Helper function to get CNV component pods with their IPs"""
        # Build full label selector with common CNV label + component-specific label
        full_label_selector = f"app=kubevirt-hyperconverged,{component_label}"

        pods = list(Pod.get(dyn_client=admin_client, namespace=namespace, label_selector=full_label_selector))
        pod_list = [(pod.name, pod.instance.status.podIP) for pod in pods if pod.instance.status.podIP]

        assert len(pod_list) >= 2, f"Need at least 2 {component_name} pods for connectivity test, found {len(pod_list)}"

        return pod_list

    component_label = f"app.kubernetes.io/component={component_name}"
    component_pods = _get_component_pods(
        admin_client=admin_client,
        namespace=hco_namespace.name,
        component_label=component_label,
        component_name=component_name,
    )

    source_pod_name, _ = component_pods[0]
    _, target_ip = component_pods[1]

    return source_pod_name, target_ip


@pytest.mark.gating
@pytest.mark.polarion("CNV-10001")  # TBD
@pytest.mark.dependency(name="network_policies_exist")
def test_cnv_network_policies_exist(cnv_network_policies):
    """
    Verify that expected HCO network policies are created in the openshift-cnv namespace.
    This test ensures that all required network policies for CNV components are properly installed.
    """
    network_policy_names = [np.name for np in cnv_network_policies]

    # Get expected network policies from parametrize decorator data
    expected_network_policies = [f"{data[0]}-np" for data in cnv_network_policy_parametrize.args[1]]

    missing_policies = [policy for policy in expected_network_policies if policy not in network_policy_names]
    assert not missing_policies, f"Missing CNV network policies: {missing_policies}"


@pytest.mark.gating
@pytest.mark.polarion("CNV-10007")  # TBD
@pytest.mark.dependency(depends=["network_policies_exist"])
@cnv_network_policy_parametrize
def test_cnv_component_network_policy_blocks_unauthorized_traffic(
    component_pods_for_test, hco_namespace, component_name, port
):
    """
    Test that NetworkPolicies block unauthorized pod-to-pod traffic within CNV components.

    This test verifies that NetworkPolicies are actively blocking traffic that would
    normally succeed without the policy. It uses component pods trying to reach each
    other on their service ports, which should be blocked by the NetworkPolicy.

    Note: This tests the negative case - that unauthorized traffic is blocked.
    Positive cases (authorized traffic) are covered by functional tests elsewhere.

    Args:
        component_name: Name of the component being tested
        port: Port to test connectivity on (component's actual service port)
    """
    source_pod_name, target_ip = component_pods_for_test

    # Test connectivity from source pod to target pod
    cmd = [
        "oc",
        "exec",
        "-n",
        hco_namespace.name,
        source_pod_name,
        "--",
        "curl",
        "-s",
        "--connect-timeout",
        "5",
        f"{target_ip}:{port}",
    ]
    success, stdout, stderr = run_command(command=cmd, check=False)

    # Extract return code from stderr message
    import re

    returncode_match = re.search(r"exit code (\d+)", stderr)
    if returncode_match:
        returncode = int(returncode_match.group(1))
    else:
        returncode = 0 if success else 1

    assert returncode != 0, (
        f"NetworkPolicy test FAILED: {component_name} connection should be blocked but curl succeeded! "
        f"return_code={returncode}, stdout={stdout}"
    )

    # Verify it failed specifically due to NetworkPolicy blocking (timeout)
    assert returncode == 28, (
        f"NetworkPolicy test FAILED: {component_name} connection failed with unexpected error code. "
        f"Expected timeout (28) indicating NetworkPolicy blocking, but got return_code={returncode}, "
        f"stderr={stderr}"
    )
