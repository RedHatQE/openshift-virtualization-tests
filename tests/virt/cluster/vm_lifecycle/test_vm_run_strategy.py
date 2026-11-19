from __future__ import annotations

# Run strategies logic can be found under
# https://kubevirt.io/user-guide/#/creation/run-strategies?id=run-strategies
import logging
from typing import TYPE_CHECKING

import pytest

from tests.os_params import RHEL_LATEST
from tests.virt.cluster.vm_lifecycle.utils import (
    ALWAYS,
    HALTED,
    MANUAL,
    RERUNONFAILURE,
    RUN_STRATEGY_SHUTDOWN_STATUS,
    migrate_validate_run_strategy_vm,
    pause_unpause_vmi_and_verify_status,
    shutdown_vm_guest_os,
    verify_vm_action,
)
from utilities.virt import running_vm

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

pytestmark = pytest.mark.post_upgrade

LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "run_strategy",
    [
        pytest.param(MANUAL, id="Manual"),
        pytest.param(ALWAYS, id="Always"),
        pytest.param(HALTED, id="Halted"),
        pytest.param(RERUNONFAILURE, id="RerunOnFailure"),
    ],
    scope="class",
)
@pytest.mark.arm64
@pytest.mark.s390x
@pytest.mark.gating
class TestRunStrategyPolicy:
    """RunStrategy start, restart, and stop policy checks.

    Jira: https://redhat.atlassian.net/browse/KNIP-1160 # <skip-jira-utils-check>
        Polarion: CNV-4685
        Polarion: CNV-4686
        Polarion: CNV-4687

    Preconditions:
        - A container-disk VM exists created with the parametrized runStrategy
    """

    @pytest.mark.dependency(name="start", scope="class")
    def test_start(self, run_strategy_container_vm: VirtualMachineForTests, run_strategy: str) -> None:
        """Verify VM start honors the configured runStrategy.

        Jira: https://redhat.atlassian.net/browse/KNIP-1160 # <skip-jira-utils-check>
        Polarion: CNV-4685

        Preconditions:
            - A container-disk VM exists created with the parametrized runStrategy

        Steps:
            - Request start on the VM

        Expected:
            - VM Ready status and runStrategy match the start policy for that runStrategy
        """
        LOGGER.info(f"Verify VM start with runStrategy {run_strategy}")
        verify_vm_action(
            vm=run_strategy_container_vm,
            vm_action="start",
            run_strategy=run_strategy,
        )

    # WHY: class-scoped VM; restart requires successful start for this strategy
    @pytest.mark.dependency(name="restart", depends=["start"], scope="class")
    def test_restart(self, run_strategy_container_vm: VirtualMachineForTests, run_strategy: str) -> None:
        """Verify VM restart honors the configured runStrategy.

        Jira: https://redhat.atlassian.net/browse/KNIP-1160 # <skip-jira-utils-check>
        Polarion: CNV-4686

        Preconditions:
            - A container-disk VM exists created with the parametrized runStrategy
            - Start for this runStrategy succeeded

        Steps:
            - Request restart on the VM

        Expected:
            - VM Ready status and runStrategy match the restart policy for that runStrategy
        """
        LOGGER.info(f"Verify VM restart with runStrategy {run_strategy}")
        verify_vm_action(
            vm=run_strategy_container_vm,
            vm_action="restart",
            run_strategy=run_strategy,
        )

    # WHY: class-scoped VM; stop requires successful restart for this strategy
    @pytest.mark.dependency(depends=["restart"], scope="class")
    def test_stop(self, run_strategy_container_vm: VirtualMachineForTests, run_strategy: str) -> None:
        """Verify VM stop honors the configured runStrategy.

        Jira: https://redhat.atlassian.net/browse/KNIP-1160 # <skip-jira-utils-check>
        Polarion: CNV-4687

        Preconditions:
            - A container-disk VM exists created with the parametrized runStrategy
            - Restart for this runStrategy succeeded

        Steps:
            - Request stop on the VM

        Expected:
            - VM Ready status and runStrategy match the stop policy for that runStrategy
        """
        LOGGER.info(f"Verify VM stop with runStrategy {run_strategy}")
        verify_vm_action(
            vm=run_strategy_container_vm,
            vm_action="stop",
            run_strategy=run_strategy,
        )


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_module",
    [{"os_dict": RHEL_LATEST}],
    indirect=True,
)
@pytest.mark.parametrize(
    "run_strategy",
    [
        pytest.param(MANUAL, id="Manual"),
        pytest.param(ALWAYS, id="Always"),
        pytest.param(RERUNONFAILURE, id="RerunOnFailure"),
    ],
    scope="class",
)
class TestRunStrategyGuestShutdown:
    """Guest OS shutdown behavior under runStrategy.

    Preconditions:
        - A data-volume VM exists created with the parametrized runStrategy
    """

    def test_run_strategy_shutdown(
        self,
        admin_client: DynamicClient,
        run_strategy_dv_vm: VirtualMachineForTests,
        run_strategy: str,
    ) -> None:
        """Verify guest OS shutdown results match the runStrategy policy.

        Jira: https://redhat.atlassian.net/browse/KNIP-1160 # <skip-jira-utils-check>
        Polarion: CNV-5054

        Preconditions:
            - A data-volume VM exists created with the parametrized runStrategy
            - The VM is running

        Steps:
            - Power off the guest operating system from inside the VM
            - Observe VMI and virt-launcher pod lifecycle

        Expected:
            - VMI and virt-launcher pod reach the statuses defined for that runStrategy after guest shutdown
        """
        running_vm(vm=run_strategy_dv_vm)
        vmi = run_strategy_dv_vm.vmi
        launcher_pod = vmi.get_virt_launcher_pod(privileged_client=admin_client)
        status_dict = RUN_STRATEGY_SHUTDOWN_STATUS[run_strategy]

        shutdown_vm_guest_os(vm=run_strategy_dv_vm)

        # runStrategy "Always" and "RerunOnFailure" first terminates the pod, then re-raises it
        if run_strategy in (ALWAYS, RERUNONFAILURE):
            launcher_pod.wait_deleted()

        if run_strategy == RERUNONFAILURE:
            # RerunOnFailure deletes VMI
            vmi.wait_deleted()
        else:
            # wait for vmi and launcher pod status by matrix
            vmi.wait_for_status(status=status_dict["vmi"])
            vmi.get_virt_launcher_pod(privileged_client=admin_client).wait_for_status(
                status=status_dict["launcher_pod"]
            )


@pytest.mark.parametrize(
    "run_strategy",
    [
        pytest.param(MANUAL, id="Manual"),
        pytest.param(ALWAYS, id="Always"),
    ],
    scope="class",
)
class TestRunStrategyPause:
    """VMI pause and unpause under runStrategy.

    Preconditions:
        - A container-disk VM exists created with the parametrized runStrategy
    """

    def test_pause_unpause_vmi(
        self,
        run_strategy_container_vm: VirtualMachineForTests,
        run_strategy: str,
    ) -> None:
        """Verify VMI pause and unpause keep the VM usable under runStrategy.

        Jira: https://redhat.atlassian.net/browse/KNIP-1160 # <skip-jira-utils-check>
        Polarion: CNV-4688
        Polarion: CNV-4689

        Preconditions:
            - A container-disk VM exists created with the parametrized runStrategy
            - The VM is running

        Steps:
            - Pause the VMI
            - Unpause the VMI

        Expected:
            - The VM is paused after pause and Ready again after unpause
        """
        LOGGER.info(f"Verify VMI pause/un-pause with runStrategy: {run_strategy}")
        running_vm(vm=run_strategy_container_vm)
        pause_unpause_vmi_and_verify_status(vm=run_strategy_container_vm)


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_module",
    [{"os_dict": RHEL_LATEST}],
    indirect=True,
)
@pytest.mark.parametrize(
    "run_strategy",
    [
        pytest.param(MANUAL, id="Manual"),
        pytest.param(ALWAYS, id="Always"),
    ],
    scope="class",
)
@pytest.mark.special_infra
@pytest.mark.rwx_default_storage
class TestRunStrategyMigrate:
    """Live migration under runStrategy.

    Preconditions:
        - A data-volume VM exists created with the parametrized runStrategy
        - Default storage supports ReadWriteMany
    """

    def test_migrate_vm(
        self,
        admin_client: DynamicClient,
        run_strategy_dv_vm: VirtualMachineForTests,
        run_strategy: str,
    ) -> None:
        """Verify live migration preserves Ready status and runStrategy.

        Jira: https://redhat.atlassian.net/browse/KNIP-1160 # <skip-jira-utils-check>
        Polarion: CNV-5893
        Polarion: CNV-4690

        Preconditions:
            - A data-volume VM exists created with the parametrized runStrategy
            - The VM is running
            - Default storage supports ReadWriteMany

        Steps:
            - Live-migrate the VM

        Expected:
            - The VM is Ready after migration and runStrategy is unchanged
        """
        running_vm(vm=run_strategy_dv_vm)
        migrate_validate_run_strategy_vm(
            vm=run_strategy_dv_vm,
            client=admin_client,
            run_strategy=run_strategy,
        )
