# Constants for vm-console-proxy
from ocp_resources.resource import Resource

KUBE_SYSTEM_NAMESPACE = "kube-system"
TOKEN_API_VERSION = Resource.ApiVersion.V1
TOKEN_ENDPOINT = "token.kubevirt.io"
VM_CONSOLE_PROXY = "vm-console-proxy"
VM_CONSOLE_PROXY_USER = f"{VM_CONSOLE_PROXY}-user"
