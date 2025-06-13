"""
Test VM with static key injection.
"""

import os

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.secret import Secret
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_OS
from utilities.constants import CLOUD_INIT_NO_CLOUD, CNV_VM_SSH_KEY_PATH, OS_FLAVOR_RHEL
from utilities.infra import authorized_key, base64_encode_str
from utilities.virt import VirtualMachineForTests, running_vm

NAME = "static-access-creds-injection"


@pytest.fixture(scope="class")
def ssh_secret(namespace):
    with Secret(
        name=f"{NAME}-secret",
        namespace=namespace.name,
        data_dict={
            "id_rsa.pub": base64_encode_str(text=authorized_key(private_key_path=os.environ[CNV_VM_SSH_KEY_PATH]))
        },
    ) as secret:
        yield secret


@pytest.fixture(scope="class")
def vm_with_ssh_secret(
    namespace,
    ssh_secret,
    unprivileged_client,
    data_volume_scope_class,
):
    """VM with Static Access Credentials Injection"""
    with VirtualMachineForTests(
        name=NAME,
        namespace=namespace.name,
        client=unprivileged_client,
        data_volume=data_volume_scope_class,
        memory_requests="1Gi",
        os_flavor=OS_FLAVOR_RHEL,
        cloud_init_data={
            "userData": "",
        },
        cloud_init_type=CLOUD_INIT_NO_CLOUD,
        ssh_secret=ssh_secret,
    ) as vm:
        yield vm


@pytest.mark.gating
@pytest.mark.s390x
@pytest.mark.parametrize(
    "data_volume_scope_class",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
        ),
    ],
    indirect=True,
)
class TestVMWithStaticKeyInjection:
    """
    Test VM with static key injection.
    """

    @pytest.mark.polarion("CNV-5875")
    def test_static_ssh_key_injection(self, vm_with_ssh_secret):
        running_vm(vm=vm_with_ssh_secret)

    @pytest.mark.polarion("CNV-6061")
    def test_ssh_access_is_successful_with_updated_secret(self, ssh_secret, vm_with_ssh_secret):
        with ResourceEditor(
            patches={
                ssh_secret: {"data": {"id_rsa.pub": base64_encode_str(text="ssh-rsa junk-pub-key root@exec1.rdocloud")}}
            }
        ):
            vm_with_ssh_secret.ssh_exec.executor().is_connective()
