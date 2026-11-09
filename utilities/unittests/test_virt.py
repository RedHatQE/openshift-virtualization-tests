"""Unit tests for utilities.virt helpers."""

import importlib
import sys
from json import JSONDecodeError
from unittest.mock import MagicMock, patch

from paramiko import SSHException
from pyhelper_utils.exceptions import CommandExecFailed
from pytest import mark, raises
from timeout_sampler import TimeoutExpiredError

# conftest.py mocks utilities.virt; clear and reload the real module for these tests.
if "utilities.virt" in sys.modules:
    del sys.modules["utilities.virt"]

virt = importlib.import_module("utilities.virt")
from utilities.constants.virt import (
    DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION,
    ES_LIVE_MIGRATE_IF_POSSIBLE,
    ES_NONE,
    EVICTIONSTRATEGY,
)
from utilities.virt import VirtualMachineForTests


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


@mark.unit
class TestWaitForWindowsVm:
    @mark.parametrize("version", ["2019", "2025"])
    def test_waits_for_expected_caption(self, mock_vm: MagicMock, version: str) -> None:
        samples = iter([
            {"Caption": None},
            {"Caption": ""},
            {"Caption": "Microsoft Windows Server 2016 Standard", "CSName": f"server-{version}"},
            {"Caption": f"Microsoft Windows Server {version} Standard"},
        ])
        with patch.object(target=virt, attribute="get_windows_os_properties") as cim_query:
            with patch.object(target=virt, attribute="TimeoutSampler", return_value=samples) as sampler:
                result = virt.wait_for_windows_vm(vm=mock_vm, version=version, timeout=30)

        assert result is True, "Expected Windows version was not recognized"
        with raises(StopIteration):
            next(samples)
        sampler.assert_called_once_with(
            wait_timeout=30,
            sleep=15,
            func=cim_query,
            exceptions_dict={CommandExecFailed: [], SSHException: [], OSError: [], JSONDecodeError: []},
            ssh_exec=mock_vm.ssh_exec,
        )

    @mark.parametrize(
        "error",
        [
            SSHException("Guest SSH is starting"),
            OSError("Connection refused"),
            CommandExecFailed(name="CIM query", err="Guest is starting"),
            JSONDecodeError(msg="Incomplete output", doc="", pos=0),
        ],
    )
    def test_retries_transient_query_failures(self, mock_vm: MagicMock, error: Exception) -> None:
        with (
            patch.object(
                target=virt,
                attribute="get_windows_os_properties",
                autospec=True,
                side_effect=[error, {"Caption": "Microsoft Windows Server 2025"}],
            ) as query,
            patch("time.sleep"),
        ):
            assert virt.wait_for_windows_vm(vm=mock_vm, version="2025", timeout=1) is True, (
                "Transient failure was not retried"
            )
        assert query.call_count == 2, "Expected a single retry before the guest became ready"

    @mark.parametrize("error", [ValueError("Unexpected format"), TypeError("Invalid query implementation")])
    def test_stops_on_unexpected_query_failure(self, mock_vm: MagicMock, error: Exception) -> None:
        with patch.object(
            target=virt, attribute="get_windows_os_properties", autospec=True, side_effect=error
        ) as query:
            with raises(TimeoutExpiredError) as failure:
                virt.wait_for_windows_vm(vm=mock_vm, version="2025", timeout=1)
        assert failure.value.last_exp is error, "Readiness failure lost the original exception"
        query.assert_called_once()

    @mark.parametrize("sample,error_type", [({}, KeyError), (None, TypeError), ([], TypeError)])
    def test_rejects_malformed_os_properties(
        self, mock_vm: MagicMock, sample: object, error_type: type[Exception]
    ) -> None:
        with patch.object(target=virt, attribute="TimeoutSampler", return_value=iter([sample])):
            with raises(error_type):
                virt.wait_for_windows_vm(vm=mock_vm, version="2025", timeout=1)

    def test_propagates_readiness_timeout(self, mock_vm: MagicMock) -> None:
        samples = MagicMock()
        samples.__iter__.side_effect = TimeoutExpiredError(value="Windows OS unavailable")
        with patch.object(target=virt, attribute="TimeoutSampler", return_value=samples):
            with raises(TimeoutExpiredError):
                virt.wait_for_windows_vm(vm=mock_vm, version="2025", timeout=30)
