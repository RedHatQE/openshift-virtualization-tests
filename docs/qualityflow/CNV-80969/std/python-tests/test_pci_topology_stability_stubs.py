"""
Windows VM Disk PCI Address Stability After Upgrade Tests

STP: outputs/CNV-80969/stp/CNV-80969_test_plan.md
Jira: CNV-80969
"""


class TestUpgradeFromCnv419:
    """
    Upgrade-path tests for a Windows VM that starts life on CNV 4.19.

    Preconditions:
        - Windows Server 2022 VM with 5 VirtIO disks, memory > 2 GiB, running on CNV 4.19
        - All disks online with simple volumes before any upgrade
    """
    __test__ = False

    def test_running_vm_manual_reonline_keeps_v2(self):
        """
        Test that a VM upgraded 4.19 -> broken -> fixed while running, with disks
        manually re-onlined on the broken build, ends up v2 with disks online.

        Priority: P1 — core upgrade path; running VM with manual re-online produces v2 annotation.

        Preconditions:
            - Windows Server 2022 VM with 5 VirtIO disks, memory > 2 GiB, running on CNV 4.19, disks online

        Steps:
            1. Upgrade CNV to 4.20.7 (broken build)
            2. Stop and start VM; observe disks go offline (bug reproduced)
            3. Manually re-online all disks in the guest
            4. Upgrade CNV to 4.20.8 (fixed build)
            5. Stop and start VM

        Expected: VMI carries the v2 PCI topology annotation and all 5 disks remain online after the final reboot.
        """

    def test_running_vm_no_reonline_keeps_v2_frozen(self):
        """
        Test that a VM rebooted on the broken build without re-onlining disks
        ends up v2 with no further PCI address shift after the fix.

        Priority: P1 — verifies v2 freeze semantics when disks are NOT re-onlined on the broken build.

        Preconditions:
            - Windows Server 2022 VM with 5 VirtIO disks, memory > 2 GiB, running on CNV 4.19, disks online

        Steps:
            1. Upgrade CNV to 4.20.7 (broken build)
            2. Stop and start VM; observe disks go offline
            3. Upgrade CNV to 4.20.8 (fixed build) without re-onlining disks
            4. Stop and start VM

        Expected: VMI carries the v2 PCI topology annotation and disk PCI addresses do not shift further after the fix.
        """

    def test_running_vm_never_rebooted_becomes_v3(self):
        """
        Test that a VM kept running through both upgrades (never rebooted on the
        broken build) becomes v3 with disks online and addresses preserved.

        Priority: P1 — VM never rebooted on broken build should upgrade cleanly to v3.

        Preconditions:
            - Windows Server 2022 VM with 5 VirtIO disks, memory > 2 GiB, running on CNV 4.19, not rebooted during upgrades

        Steps:
            1. Upgrade CNV to 4.20.7 (broken build) without touching the VM
            2. Upgrade CNV to 4.20.8 (fixed build)
            3. Stop and start VM

        Expected: VMI carries the v3 PCI topology annotation and all disks remain online at the original 4.19 PCI addresses.
        """

    def test_stopped_vm_starts_as_v3(self):
        """
        Test that a VM stopped before any upgrade starts as v3 with all disks
        online after the fixed build is installed.

        Priority: P1 — stopped-before-upgrade VM should start as v3 with stable disks.

        Preconditions:
            - Windows Server 2022 VM with 5 VirtIO disks, memory > 2 GiB, stopped on CNV 4.19 before upgrades

        Steps:
            1. Upgrade CNV to 4.20.7 (broken build) without touching the VM
            2. Upgrade CNV to 4.20.8 (fixed build)
            3. Start VM

        Expected: VMI carries the v3 PCI topology annotation and all disks are online after start.
        """

    def test_direct_upgrade_to_fixed_build_becomes_v3(self):
        """
        Test that upgrading directly from 4.19 to fixed 4.20.8 (skipping the
        broken build) yields v3 with all disks online and addresses unchanged.

        Priority: P2 — direct 4.19->4.20.8 upgrade (no broken build) should yield stable v3.

        Preconditions:
            - Windows Server 2022 VM with 5 VirtIO disks, running on CNV 4.19, all disks online

        Steps:
            1. Upgrade CNV directly from 4.19 to 4.20.8 (fixed build)
            2. Reboot VM

        Expected: VMI carries the v3 PCI topology annotation and all 5 disks remain online at unchanged PCI addresses.
        """


class TestCreatedOnBrokenBuild:
    """
    Tests for a Windows VM that is born on the broken 4.20.7 build (v2-native)
    and then upgraded to the fixed 4.20.8 build.

    Preconditions:
        - CNV 4.20.7 (broken build) cluster with no prior VMs
        - Windows VM with 5 VirtIO disks created directly on the broken build, disks onlined with simple volumes
    """
    __test__ = False

    def test_running_v2_native_vm_stays_v2_frozen(self):
        """
        Test that a running v2-native VM keeps its frozen v2 placeholder count and
        online disks after upgrading to the fixed build.

        Priority: P1 — VM born on broken build (v2) must have placeholder count frozen on upgrade.

        Preconditions:
            - Windows VM with 5 VirtIO disks created and running on CNV 4.20.7, all disks online

        Steps:
            1. Upgrade CNV to 4.20.8 (fixed build)
            2. Stop and start VM

        Expected: VMI retains the v2 PCI topology annotation and all disks remain online after the reboot.
        """

    def test_stopped_v2_native_vm_rerenders_as_v3(self):
        """
        Test that a stopped v2-native VM is re-rendered as v3 on the fixed build
        and, after a one-time re-online, keeps disk state across reboots.

        Priority: P2 — v2-native VM stopped then upgraded re-renders as v3; documents one-time re-online.

        Preconditions:
            - Windows VM with 5 VirtIO disks created on CNV 4.20.7, disks onlined, then stopped before upgrade

        Steps:
            1. Upgrade CNV to 4.20.8 (fixed build)
            2. Start VM and re-online disks once
            3. Stop and start VM again

        Expected: VMI carries the v3 PCI topology annotation and disks stay online across subsequent reboots after the one-time re-online.
        """


class TestNewVmOnFixedBuild:
    """
    Tests for green-field VMs created directly on the fixed 4.20.8 build.

    Preconditions:
        - Clean CNV 4.20.8 (fixed build) cluster with no prior VMs
    """
    __test__ = False

    def test_new_vm_defaults_to_v3(self):
        """
        Test that a new Windows VM created on the fixed build defaults to v3
        topology with online disks and stable addresses across reboot.

        Priority: P2 — new VM on fixed build should default to v3 via mutating webhook.

        Preconditions:
            - New Windows VM with 5 VirtIO disks created on a clean CNV 4.20.8 cluster

        Steps:
            1. Start VM
            2. Online all disks in the guest
            3. Stop and start VM

        Expected: The mutating webhook sets the v3 PCI topology annotation and all disks stay online at stable PCI addresses across the reboot.
        """


class TestLinuxUdevRules:
    """
    Tests that Linux VMs relying on PCI-based udev rules survive the upgrade.

    Preconditions:
        - Linux VM with 4 VirtIO disks on CNV 4.19
        - udev rules mapping PCI bus addresses to disk names configured in the guest
    """
    __test__ = False

    def test_linux_udev_rules_survive_upgrade(self):
        """
        Test that a Linux VM with PCI-based udev rules keeps identical device
        names after upgrading directly to the fixed build.

        Priority: P2 — Linux VM with PCI-based udev rules must survive the upgrade.

        Preconditions:
            - Linux VM with 4 VirtIO disks on CNV 4.19 and udev rules referencing PCI bus addresses for disk naming

        Steps:
            1. Upgrade CNV directly to 4.20.8 (skip broken build)
            2. Reboot VM

        Expected: Disk PCI bus addresses are unchanged and udev rules produce the same device names as before the upgrade.
        """


class TestStorageClassIndependence:
    """
    Tests that PCI address stability is independent of the backing storage class.

    Preconditions:
        - Windows VM on CNV 4.19 with disks split across two distinct storage classes, all online
    """
    __test__ = False

    def test_disks_online_across_two_storage_classes(self):
        """
        Test that all disks remain online after upgrade regardless of which
        storage class backs them.

        Priority: P2 — behavior must be storage-class independent (confirmed in Jira).

        Preconditions:
            - Windows VM on CNV 4.19 with disks on two different storage classes, all disks online

        Steps:
            1. Upgrade CNV to 4.20.8 (fixed build)
            2. Reboot VM

        Expected: Every disk on both storage classes reports online after the reboot.
        """


class TestMemoryThreshold:
    """
    Tests the ambiguous memory-detection edge case at exactly 2 GiB.

    Preconditions:
        - Windows VM with memory == 2 GiB and 3 VirtIO disks on CNV 4.19, all online
    """
    __test__ = False

    def test_two_gib_vm_annotated_v3_disks_online(self):
        """
        Test that a VM with exactly 2 GiB memory is annotated v3 (documented as
        harmless) and keeps disks online after upgrade.

        Priority: P2 — memory threshold edge case (<=2GB) documented as harmless; annotate v3.

        Preconditions:
            - Windows VM with memory == 2 GiB and 3 VirtIO disks on CNV 4.19, all disks online

        Steps:
            1. Upgrade CNV to 4.20.8 (fixed build)
            2. Reboot VM

        Expected: VMI carries the v3 PCI topology annotation and all 3 disks remain online after the reboot.
        """


class TestLiveMigration:
    """
    Tests that the PCI topology annotation survives live migration.

    Preconditions:
        - Multi-node cluster with at least two schedulable nodes
        - Windows VM on CNV 4.20.8 with the v3 PCI topology annotation, running
    """
    __test__ = False

    def test_annotation_persists_across_live_migration(self):
        """
        Test that a live-migrated VM keeps its v3 topology annotation and stable
        disk addresses on the target node.

        Priority: P2 — annotation must persist across live migration (controller propagation).

        Preconditions:
            - Windows VM on CNV 4.20.8 with the v3 PCI topology annotation, running on a multi-node cluster

        Steps:
            1. Execute live migration of the VM to another node
            2. Stop and start VM after migration

        Expected: The v3 PCI topology annotation is preserved on the target node and disk PCI addresses remain unchanged after the stop/start.
        """
