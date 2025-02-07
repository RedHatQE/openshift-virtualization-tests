from __future__ import annotations

import logging
from typing import Any, Type

import requests
from ocp_resources.api_service import APIService
from ocp_resources.resource import Resource

from tests.infrastructure.vm_console_proxy.constants import (
    TOKEN_API_VERSION,
    TOKEN_ENDPOINT,
    VM_CONSOLE_PROXY,
)

LOGGER = logging.getLogger(__name__)


def create_vnc_console_token(
    url: str,
    endpoint: str,
    api_version: str,
    namespace: str,
    virtual_machine: str,
    duration: int,
    runtime_headers: dict[str, str] | None,
) -> str:
    """
    Requests a VNC console token for a virtual machine

    Args:
        url (str): The base URL of API server.
        endpoint (str): The API endpoint for VM console proxy.
        api_version (str): The API version for the VM console proxy.
        namespace (str): The namespace of the virtual machine.
        virtual_machine (str): The name of the virtual machine.
        duration (int): The duration in seconds for which the token should be valid.
        runtime_headers (dict): Optional headers to include in the request.

    Returns:
        str: The token received from the API server.

    Raises:
        Exception: If an error occurs during the request process.
    """
    headers = {"Content-Type": "application/json"}
    if runtime_headers:
        headers.update(runtime_headers)
    full_url = (
        f"{url}/apis/{endpoint}/{api_version}/namespaces/{namespace}/virtualmachines/{virtual_machine}"
        f"/vnc?duration={duration}"
    )
    try:
        response = requests.get(full_url, headers=headers, verify=False)
        response.raise_for_status()  # Raise HTTPError for bad responses <4xx><5xx>
        return response.json()["token"]
    except requests.RequestException as exp:
        logging.error(f"Request error occurred: {exp}")
        raise


def get_vm_console_proxy_resource(resource_kind: Type, namespace: str | None = None) -> Type:
    if namespace:
        vm_console_proxy_resource_object = resource_kind(
            name=VM_CONSOLE_PROXY,
            namespace=namespace,
        )
    else:
        vm_console_proxy_resource_object = resource_kind(
            name=f"{TOKEN_API_VERSION}.{TOKEN_ENDPOINT}" if resource_kind == APIService else VM_CONSOLE_PROXY
        )
    return vm_console_proxy_resource_object


def assert_resource_existence_and_availability(resource: Any, timeout: int) -> None:
    if resource.kind in {"APIService", "Deployment"}:
        LOGGER.info(f"Wait for availability/condition check for {resource.kind}.")
        resource.wait_for_condition(
            condition=Resource.Condition.AVAILABLE,
            status=Resource.Condition.Status.TRUE,
            timeout=timeout,
        )
        return

    assert resource.exists, (
        f"Missing: {resource.kind}/{resource.name} under {getattr(resource, 'namespace', 'cluster')}"
    )
