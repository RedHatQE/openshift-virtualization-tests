"""
Test virtctl guestfs command with specific user.

Jira: https://redhat.atlassian.net/browse/CNV-7487 # <skip-jira-utils-check>
"""

from subprocess import check_output

import pexpect
import pytest
from ocp_resources.pod import Pod
from pytest_testconfig import config as py_config

from utilities.constants.pytest import UNPRIVILEGED_PASSWORD, UNPRIVILEGED_USER
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_10MIN
from utilities.infra import login_with_user_password
from utilities.storage import create_dv, get_dv_size_from_datasource

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
    libguestfs_pod = Pod(
        client=unprivileged_client,
        name=f"libguestfs-tools-{dv_created_by_specific_user.name}",
        namespace=dv_created_by_specific_user.namespace,
    )
    libguestfs_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_10MIN)
    guestfs_proc.send("\n\n")
    guestfs_proc.expect(r"\$", timeout=TIMEOUT_1MIN)
    yield guestfs_proc
    guestfs_proc.send("exit\n")
    guestfs_proc.expect(pexpect.EOF, timeout=TIMEOUT_1MIN)
    guestfs_proc.close()
    libguestfs_pod.wait_deleted()


@pytest.fixture
def dv_created_by_specific_user(
    request,
    namespace,
    client_for_test,
    fedora_data_source_scope_module,
):
    with create_dv(
        dv_name=request.param["data_volume_name"],
        storage_class=py_config["default_storage_class"],
        client=client_for_test,
        namespace=namespace.name,
        source_ref={
            "kind": fedora_data_source_scope_module.kind,
            "name": fedora_data_source_scope_module.name,
            "namespace": fedora_data_source_scope_module.namespace,
        },
        size=get_dv_size_from_datasource(data_source=fedora_data_source_scope_module),
    ) as dv:
        dv.wait_for_dv_success()
        yield dv


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
@pytest.mark.s390x
def test_virtctl_libguestfs_with_specific_user(
    virtctl_libguestfs_by_user,
):
    virtctl_libguestfs_by_user.sendline("libguestfs-test-tool")
    virtctl_libguestfs_by_user.expect("===== TEST FINISHED OK =====", timeout=TIMEOUT_1MIN)
