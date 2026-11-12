"""Unit tests for utilities.virt helpers."""

import importlib
import sys
from unittest.mock import MagicMock, call, patch

# conftest.py mocks utilities.virt; clear and reload the real module for these tests.
if "utilities.virt" in sys.modules:
    del sys.modules["utilities.virt"]

import utilities.virt

importlib.reload(utilities.virt)

from utilities.constants.timeouts import TIMEOUT_30MIN
from utilities.constants.virt import (
    DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION,
    ES_LIVE_MIGRATE_IF_POSSIBLE,
    ES_NONE,
    EVICTIONSTRATEGY,
)
from utilities.virt import VirtualMachineForTests, running_vm


def _dv_volume(name: str) -> MagicMock:
    volume = MagicMock()
    volume.keys.return_value = ["dataVolume"]
    volume.dataVolume.name = name
    return volume


def _running_vm_stub(*, volume_names: list[str]) -> MagicMock:
    vm = MagicMock()
    vm.name = "test-vm"
    vm.namespace = "test-ns"
    vm.client = MagicMock()
    vm.instance.spec.template.spec.volumes = [_dv_volume(name=name) for name in volume_names]
    return vm


def _build_vm_stub(
    eviction_strategy: str | None = None, *, exclude_from_descheduler: bool = False
) -> VirtualMachineForTests:
    """Create a minimal VirtualMachineForTests stub with enough state for _set_descheduler_exclusion."""
    vm = VirtualMachineForTests.__new__(VirtualMachineForTests)
    vm.name = "test-vm"
    vm.exclude_from_descheduler = exclude_from_descheduler
    template_spec = {"domain": {}}
    if eviction_strategy:
        template_spec[EVICTIONSTRATEGY] = eviction_strategy
    vm.res = {"spec": {"template": {"metadata": {}, "spec": template_spec}}}
    return vm


class TestDeschedulerExclusion:
    def test_explicit_true_sets_annotation(self):
        vm = _build_vm_stub(exclude_from_descheduler=True)
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"]["annotations"]
        assert annotations[DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION] == "true", (
            "Annotation not set when explicitly requested"
        )

    def test_explicit_false_does_not_override_eviction_strategy(self):
        # False is the default (do not force exclusion); it must NOT suppress the
        # eviction-strategy-driven auto-exclusion for ES_NONE / ES_LIVE_MIGRATE_IF_POSSIBLE.
        vm = _build_vm_stub(exclude_from_descheduler=False, eviction_strategy=ES_NONE)
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"]["annotations"]
        assert annotations[DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION] == "true", (
            "Annotation not auto-set for ES_NONE when False"
        )

    def test_auto_exclude_for_es_none(self):
        vm = _build_vm_stub(eviction_strategy=ES_NONE)
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"]["annotations"]
        assert annotations[DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION] == "true", "Annotation not auto-set for ES_NONE"

    def test_auto_exclude_for_es_live_migrate_if_possible(self):
        vm = _build_vm_stub(eviction_strategy=ES_LIVE_MIGRATE_IF_POSSIBLE)
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"]["annotations"]
        assert annotations[DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION] == "true", (
            "Annotation not auto-set for ES_LIVE_MIGRATE_IF_POSSIBLE"
        )

    def test_no_annotation_without_matching_eviction_strategy(self):
        vm = _build_vm_stub(eviction_strategy="LiveMigrate")
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"].get("annotations", {})
        assert DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION not in annotations, (
            "Annotation set for non-excluded eviction strategy"
        )

    def test_no_annotation_when_no_eviction_strategy(self):
        vm = _build_vm_stub()
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"].get("annotations", {})
        assert DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION not in annotations, (
            "Annotation set when no eviction strategy specified"
        )


class TestVirtualMachineForTestsLabel:
    def test_label_preserved_when_body_replaces_metadata(self):
        """Caller-provided label must survive generate_body() metadata overwrite."""
        vm = VirtualMachineForTests.__new__(VirtualMachineForTests)
        vm.name = "test-vm"
        body_labels = {"existing": "true"}
        vm.body = {
            "metadata": {"labels": body_labels},
            "spec": {"template": {"spec": {"domain": {}}}},
        }
        vm.label = {"changedBlockTracking": "true"}
        vm.annotations = None
        vm.res = {"metadata": {"name": "test-vm"}}

        vm.generate_body()

        assert vm.res["metadata"]["labels"]["changedBlockTracking"] == "true"
        assert vm.res["metadata"]["labels"]["existing"] == "true"
        assert body_labels == {"existing": "true"}
        assert vm.body["metadata"]["labels"] == {"existing": "true"}
        assert "name" not in vm.body["metadata"]
        assert vm.res["metadata"]["name"] == "test-vm"


class TestRunningVmDvStopStatusKwargs:
    @patch("utilities.virt.wait_for_running_vm")
    @patch("utilities.virt.assert_vm_not_error_status")
    @patch("utilities.virt.DataVolume")
    def test_progress_state_reset_per_datavolume(
        self,
        mock_data_volume_cls: MagicMock,
        mock_assert_vm_not_error_status: MagicMock,
        mock_wait_for_running_vm: MagicMock,
    ) -> None:
        vm = _running_vm_stub(volume_names=["dv-a", "dv-b"])
        caller_progress_state = {"progress": "50%", "updated_at": 1.0}
        stop_kwargs = {"progress_state": caller_progress_state, "no_progress_timeout": 60}
        stop_func = MagicMock(name="dv_stop_status_func")
        dv_a = MagicMock(name="dv-a-resource")
        dv_b = MagicMock(name="dv-b-resource")
        mock_data_volume_cls.side_effect = [dv_a, dv_b]

        running_vm(
            vm=vm,
            wait_for_interfaces=False,
            check_ssh_connectivity=False,
            dv_stop_status_func=stop_func,
            dv_stop_status_kwargs=stop_kwargs,
        )

        assert caller_progress_state == {"progress": "50%", "updated_at": 1.0}, (
            "Caller progress_state must remain unchanged"
        )
        assert stop_kwargs["progress_state"] is caller_progress_state, (
            "Caller kwargs dict must keep the original progress_state object"
        )
        first_kwargs = dv_a.wait_for_dv_success.call_args.kwargs
        second_kwargs = dv_b.wait_for_dv_success.call_args.kwargs
        assert first_kwargs["stop_status_func"] is stop_func, "First DV must receive the stop_status_func"
        assert first_kwargs["dv"] is dv_a, "First wait must use the first DataVolume instance"
        assert first_kwargs["timeout"] == TIMEOUT_30MIN, "First DV wait must use the default DV timeout"
        assert first_kwargs["no_progress_timeout"] == 60, "Other stop kwargs must be forwarded"
        assert first_kwargs["progress_state"] == {}, "First DV must get a fresh empty progress_state"
        assert first_kwargs["progress_state"] is not caller_progress_state, (
            "First DV progress_state must not reuse the caller's dict"
        )
        assert second_kwargs["dv"] is dv_b, "Second wait must use the second DataVolume instance"
        assert second_kwargs["progress_state"] == {}, "Second DV must get a fresh empty progress_state"
        assert second_kwargs["progress_state"] is not first_kwargs["progress_state"], (
            "Each DV must receive a distinct progress_state dict"
        )
        assert second_kwargs["progress_state"] is not caller_progress_state, (
            "Second DV progress_state must not reuse the caller's dict"
        )
        mock_assert_vm_not_error_status.assert_called_once_with(vm=vm)
        mock_wait_for_running_vm.assert_called_once()

    @patch("utilities.virt.wait_for_running_vm")
    @patch("utilities.virt.assert_vm_not_error_status")
    @patch("utilities.virt.DataVolume")
    def test_default_path_passes_no_progress_state(
        self,
        mock_data_volume_cls: MagicMock,
        mock_assert_vm_not_error_status: MagicMock,
        mock_wait_for_running_vm: MagicMock,
    ) -> None:
        vm = _running_vm_stub(volume_names=["dv-default"])
        dv = MagicMock(name="dv-default-resource")
        mock_data_volume_cls.return_value = dv

        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)

        dv.wait_for_dv_success.assert_called_once_with(
            timeout=TIMEOUT_30MIN,
            stop_status_func=None,
            dv=dv,
        )
        assert "progress_state" not in dv.wait_for_dv_success.call_args.kwargs, (
            "Default running_vm path must not inject progress_state"
        )
        mock_assert_vm_not_error_status.assert_called_once_with(vm=vm)
        mock_wait_for_running_vm.assert_called_once()
        assert mock_data_volume_cls.call_args_list == [
            call(name="dv-default", namespace="test-ns", client=vm.client),
        ], "DataVolume must be constructed with the VM namespace and client"
