import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_VM_INFO,
    KUBEVIRT_VMI_INFO,
)
from tests.observability.metrics.utils import (
    assert_vm_metric_labels,
    compare_kubevirt_vmi_info_metric_with_vm_info,
)
from utilities.constants.monitoring import KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS
from utilities.monitoring import validate_metrics_value

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


class TestMetricsLinux:
    @pytest.mark.polarion("CNV-11906")
    @pytest.mark.s390x
    def test_cnv_vmi_monitoring_metrics_linux_vm(
        self, admin_client, prometheus, single_metric_vm, cnv_vmi_monitoring_metrics_matrix__function__
    ):
        """
        Tests validating ability to perform various prometheus api queries on various metrics against a given vm
        and validates appropriate label information (node, namespace) exists for those metrics.
        """
        assert_vm_metric_labels(
            prometheus=prometheus,
            query=cnv_vmi_monitoring_metrics_matrix__function__,
            vm=single_metric_vm,
            admin_client=admin_client,
        )


@pytest.mark.tier3
@pytest.mark.windows
class TestMetricsWindows:
    @pytest.mark.polarion("CNV-11880")
    def test_cnv_vmi_monitoring_metrics_windows_vm(
        self,
        admin_client,
        prometheus,
        windows_vm_for_test,
        cnv_vmi_monitoring_metrics_matrix__function__,
    ):
        assert_vm_metric_labels(
            prometheus=prometheus,
            query=cnv_vmi_monitoring_metrics_matrix__function__,
            vm=windows_vm_for_test,
            admin_client=admin_client,
        )


@pytest.mark.polarion("CNV-10438")
@pytest.mark.s390x
@pytest.mark.conformance
def test_cnv_installation_with_hco_cr_metrics(
    prometheus,
):
    validate_metrics_value(
        prometheus=prometheus,
        metric_name=KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS,
        expected_value="1",
    )


class TestVMIMetricsLinuxVms:
    @pytest.mark.polarion("CNV-11862")
    @pytest.mark.s390x
    def test_metric_kubevirt_vm_info(self, prometheus, single_metric_vm, linux_vm_info_to_compare):
        compare_kubevirt_vmi_info_metric_with_vm_info(
            prometheus=prometheus,
            query=KUBEVIRT_VM_INFO.format(vm_name=single_metric_vm.name),
            expected_value="1",
            values_to_compare=linux_vm_info_to_compare,
        )

    @pytest.mark.polarion("CNV-16853")
    def test_vm_info_and_vmi_info_uid_differ(self, prometheus, single_metric_vm):
        """
        Test that kubevirt_vm_info and kubevirt_vmi_info each report the correct Kubernetes uid
        for the same running VM, and that the two uid values differ.

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-95597  # <skip-jira-utils-check>

        Preconditions:
            - Running Linux virtual machine

        Steps:
            1. Query kubevirt_vm_info for the virtual machine and record its uid label value
            2. Query kubevirt_vmi_info for the virtual machine and record its uid label value

        Expected:
            - The uid label value from kubevirt_vm_info equals the virtual machine's Kubernetes uid
            - The uid label value from kubevirt_vmi_info equals the running VMI's Kubernetes uid
            - The uid label value from kubevirt_vm_info does not equal the uid label value from
              kubevirt_vmi_info
        """

    test_vm_info_and_vmi_info_uid_differ.__test__ = False

    @pytest.mark.polarion("CNV-16854")
    def test_join_vmi_memory_unused_bytes_with_vm_info_by_uid(self, prometheus, single_metric_vm):
        """
        Test that joining kubevirt_vmi_memory_unused_bytes with kubevirt_vm_info on namespace and
        name, carrying the uid label across via group_left, surfaces the virtual machine's uid.

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-95597  # <skip-jira-utils-check>

        Preconditions:
            - Running Linux virtual machine

        Steps:
            1. Record the virtual machine's uid from its resource metadata
            2. Run a Prometheus query joining kubevirt_vmi_memory_unused_bytes with
               kubevirt_vm_info on namespace and name, with group_left carrying the uid label
            3. Extract the uid label from the joined query result

        Expected:
            - The uid label value in the joined query result equals the virtual machine's uid
              recorded in step 1
        """

    test_join_vmi_memory_unused_bytes_with_vm_info_by_uid.__test__ = False


@pytest.mark.tier3
@pytest.mark.windows
class TestVMIMetricsWindowsVms:
    @pytest.mark.polarion("CNV-11861")
    def test_kubevirt_vmi_info_windows(self, prometheus, windows_vm_for_test, vmi_guest_os_kernel_release_info_windows):
        compare_kubevirt_vmi_info_metric_with_vm_info(
            prometheus=prometheus,
            query=KUBEVIRT_VMI_INFO.format(vm_name=windows_vm_for_test.name),
            expected_value="1",
            values_to_compare=vmi_guest_os_kernel_release_info_windows,
        )

    @pytest.mark.polarion("CNV-11863")
    def test_metric_kubevirt_vm_info_windows(self, prometheus, windows_vm_for_test, windows_vm_info_to_compare):
        compare_kubevirt_vmi_info_metric_with_vm_info(
            prometheus=prometheus,
            query=KUBEVIRT_VM_INFO.format(vm_name=windows_vm_for_test.name),
            expected_value="1",
            values_to_compare=windows_vm_info_to_compare,
        )

    @pytest.mark.polarion("CNV-16859")
    def test_vm_info_and_vmi_info_uid_differ_windows(self, prometheus, windows_vm_for_test):
        """
        Test that kubevirt_vm_info and kubevirt_vmi_info each report the correct Kubernetes uid
        for the same running VM, and that the two uid values differ.

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-95597  # <skip-jira-utils-check>

        Preconditions:
            - Running Windows virtual machine

        Steps:
            1. Query kubevirt_vm_info for the virtual machine and record its uid label value
            2. Query kubevirt_vmi_info for the virtual machine and record its uid label value

        Expected:
            - The uid label value from kubevirt_vm_info equals the virtual machine's Kubernetes uid
            - The uid label value from kubevirt_vmi_info equals the running VMI's Kubernetes uid
            - The uid label value from kubevirt_vm_info does not equal the uid label value from
              kubevirt_vmi_info
        """

    test_vm_info_and_vmi_info_uid_differ_windows.__test__ = False

    @pytest.mark.polarion("CNV-16860")
    def test_join_vmi_memory_unused_bytes_with_vm_info_by_uid_windows(self, prometheus, windows_vm_for_test):
        """
        Test that joining kubevirt_vmi_memory_unused_bytes with kubevirt_vm_info on namespace and
        name, carrying the uid label across via group_left, surfaces the virtual machine's uid.

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-95597  # <skip-jira-utils-check>

        Preconditions:
            - Running Windows virtual machine

        Steps:
            1. Record the virtual machine's uid from its resource metadata
            2. Run a Prometheus query joining kubevirt_vmi_memory_unused_bytes with
               kubevirt_vm_info on namespace and name, with group_left carrying the uid label
            3. Extract the uid label from the joined query result

        Expected:
            - The uid label value in the joined query result equals the virtual machine's uid
              recorded in step 1
        """

    test_join_vmi_memory_unused_bytes_with_vm_info_by_uid_windows.__test__ = False


class TestLinuxVMAndVMIInfoUidLifecycle:
    """
    kubevirt_vm_info / kubevirt_vmi_info uid behavior across virtual machine stop/start and
    delete/recreate lifecycle transitions.

    No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-95597  # <skip-jira-utils-check>

    Preconditions:
        - Running Linux virtual machine, not shared with other tests in this module
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16855")
    def test_vm_info_uid_unchanged_vmi_info_uid_changes_across_stop_start(self, prometheus):
        """
        Test that kubevirt_vm_info's uid stays unchanged and kubevirt_vmi_info's uid changes to a
        new value across a virtual machine stop/start cycle.

        Steps:
            1. Query kubevirt_vm_info for the virtual machine and record its uid label value
            2. Query kubevirt_vmi_info for the virtual machine and record its uid label value
            3. Stop the virtual machine
            4. Query kubevirt_vmi_info for the virtual machine
            5. Query kubevirt_vm_info for the virtual machine and record its uid label value
            6. Start the virtual machine
            7. Query kubevirt_vmi_info for the virtual machine and record its uid label value

        Expected:
            - After the virtual machine is stopped, kubevirt_vmi_info for the virtual machine is
              absent, and the kubevirt_vm_info uid label value from step 5 equals the value from
              step 1
            - After the virtual machine is started, the kubevirt_vmi_info uid label value from
              step 7 does not equal the value from step 2
        """

    @pytest.mark.polarion("CNV-16856")
    def test_vm_info_series_replaced_after_delete_and_recreate_with_same_name(self, prometheus):
        """
        Test that deleting a virtual machine and recreating a new virtual machine with the same
        name produces a kubevirt_vm_info series with a new uid, replacing the series for the
        deleted virtual machine's uid.

        Steps:
            1. Query kubevirt_vm_info for the virtual machine and record its uid label value
            2. Delete the virtual machine
            3. Create and start a new virtual machine with the same name and namespace as the
               deleted virtual machine
            4. Query kubevirt_vm_info for the virtual machine

        Expected:
            - The kubevirt_vm_info uid label value from step 4 does not equal the value from
              step 1, and no active kubevirt_vm_info series reports the uid value from step 1
        """


@pytest.mark.tier3
@pytest.mark.windows
class TestWindowsVMAndVMIInfoUidLifecycle:
    """
    kubevirt_vm_info / kubevirt_vmi_info uid behavior across virtual machine stop/start and
    delete/recreate lifecycle transitions.

    No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-95597  # <skip-jira-utils-check>

    Preconditions:
        - Running Windows virtual machine, not shared with other tests in this module
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16861")
    def test_vm_info_uid_unchanged_vmi_info_uid_changes_across_stop_start_windows(self, prometheus):
        """
        Test that kubevirt_vm_info's uid stays unchanged and kubevirt_vmi_info's uid changes to a
        new value across a virtual machine stop/start cycle.

        Steps:
            1. Query kubevirt_vm_info for the virtual machine and record its uid label value
            2. Query kubevirt_vmi_info for the virtual machine and record its uid label value
            3. Stop the virtual machine
            4. Query kubevirt_vmi_info for the virtual machine
            5. Query kubevirt_vm_info for the virtual machine and record its uid label value
            6. Start the virtual machine
            7. Query kubevirt_vmi_info for the virtual machine and record its uid label value

        Expected:
            - After the virtual machine is stopped, kubevirt_vmi_info for the virtual machine is
              absent, and the kubevirt_vm_info uid label value from step 5 equals the value from
              step 1
            - After the virtual machine is started, the kubevirt_vmi_info uid label value from
              step 7 does not equal the value from step 2
        """

    @pytest.mark.polarion("CNV-16862")
    def test_vm_info_series_replaced_after_delete_and_recreate_with_same_name_windows(self, prometheus):
        """
        Test that deleting a virtual machine and recreating a new virtual machine with the same
        name produces a kubevirt_vm_info series with a new uid, replacing the series for the
        deleted virtual machine's uid.

        Steps:
            1. Query kubevirt_vm_info for the virtual machine and record its uid label value
            2. Delete the virtual machine
            3. Create and start a new virtual machine with the same name and namespace as the
               deleted virtual machine
            4. Query kubevirt_vm_info for the virtual machine

        Expected:
            - The kubevirt_vm_info uid label value from step 4 does not equal the value from
              step 1, and no active kubevirt_vm_info series reports the uid value from step 1
        """
