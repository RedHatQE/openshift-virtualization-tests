from subprocess import check_output

import pexpect
import pytest
from ocp_resources.pod import Pod
from pytest_testconfig import config as py_config

from tests.storage.utils import create_cirros_dv
from utilities.constants import TIMEOUT_1MIN, UNPRIVILEGED_PASSWORD, UNPRIVILEGED_USER
from utilities.infra import login_with_user_password

pytestmark = pytest.mark.post_upgrade


@pytest.fixture()
def virtctl_libguestfs_by_user(
    dv_created_by_specific_user,
    unprivileged_client,
):
    fs_group_flag = "" if dv_created_by_specific_user.client == unprivileged_client else "--fsGroup 2000"
    guestfs_proc = pexpect.spawn(
        f"virtctl guestfs {dv_created_by_specific_user.name} -n {dv_created_by_specific_user.namespace} \
        {fs_group_flag}"
    )

    guestfs_proc.send("\n\n")
    guestfs_proc.expect("$", timeout=TIMEOUT_1MIN)
    yield guestfs_proc
    guestfs_proc.send("exit\n")
    guestfs_proc.expect(pexpect.EOF, timeout=TIMEOUT_1MIN)
    guestfs_proc.close()
    Pod(
        name=f"libguestfs-tools-{dv_created_by_specific_user.name}",
        namespace=dv_created_by_specific_user.namespace,
    ).wait_deleted()


@pytest.fixture
def dv_created_by_specific_user(
    request,
    namespace,
    client_for_test,
):
    yield from create_cirros_dv(
        name=request.param["data_volume_name"],
        namespace=namespace.name,
        storage_class=py_config["default_storage_class"],
        client=client_for_test,
    )


@pytest.fixture()
def client_for_test(request, admin_client, unprivileged_client):
    current_user = check_output("oc whoami", shell=True).decode().strip()
    if request.param.get("admin_client"):
        yield admin_client
    else:
        login_with_user_password(
            api_address=admin_client.configuration.host,
            user=UNPRIVILEGED_USER,
            password=UNPRIVILEGED_PASSWORD,
        )
        yield unprivileged_client
        login_with_user_password(
            api_address=admin_client.configuration.host,
            user=current_user.strip(),
        )


@pytest.mark.parametrize(
    (
        "client_for_test",
        "dv_created_by_specific_user",
    ),
    [
        pytest.param(
            {"admin_client": False},
            {"data_volume_name": "guestfs-cnv-9655"},
            marks=(pytest.mark.polarion("CNV-9655")),
        ),
        pytest.param(
            {"admin_client": True},
            {"data_volume_name": "guestfs-cnv-6566"},
            marks=(pytest.mark.polarion("CNV-6566")),
        ),
    ],
    indirect=True,
)
def test_virtctl_libguestfs_with_specific_user(
    client_for_test,
    virtctl_libguestfs_by_user,
):
    virtctl_libguestfs_by_user.sendline("libguestfs-test-tool")
    virtctl_libguestfs_by_user.expect("===== TEST FINISHED OK =====", timeout=TIMEOUT_1MIN)
