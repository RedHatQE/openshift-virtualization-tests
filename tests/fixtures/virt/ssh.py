import os

import paramiko
import pytest

from utilities.constants.virt import CNV_VM_SSH_KEY_PATH


@pytest.fixture(scope="session")
def ssh_key_tmpdir_scope_session(tmpdir_factory):
    yield tmpdir_factory.mktemp("vm-ssh-key-folder")


@pytest.fixture(scope="session")
def generated_ssh_key_for_vm_access(ssh_key_tmpdir_scope_session):
    key_generated = paramiko.RSAKey.generate(bits=2048)
    vm_ssh_key_file = os.path.join(ssh_key_tmpdir_scope_session, "vm_ssh_key.key")
    os.environ[CNV_VM_SSH_KEY_PATH] = vm_ssh_key_file
    key_generated.write_private_key_file(filename=vm_ssh_key_file)
    yield
    if os.path.isfile(vm_ssh_key_file):
        os.unlink(vm_ssh_key_file)
    del os.environ[CNV_VM_SSH_KEY_PATH]
