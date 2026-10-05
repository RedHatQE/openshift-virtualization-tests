import pytest

from utilities.virt import start_and_fetch_processid_on_linux_vm


@pytest.fixture(scope="class")
def ping_process_in_rhel_os():
    def _start_ping(vm):
        return start_and_fetch_processid_on_linux_vm(
            vm=vm,
            process_name="ping",
            args="localhost",
        )

    return _start_ping
