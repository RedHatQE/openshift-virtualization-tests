"""Unit tests for utilities.virt helpers."""

import importlib
import sys

# conftest.py mocks utilities.virt; clear and reload the real module for these tests.
if "utilities.virt" in sys.modules:
    del sys.modules["utilities.virt"]

import utilities.virt

importlib.reload(utilities.virt)

from utilities.constants.virt import ES_LIVE_MIGRATE_IF_POSSIBLE, ES_NONE, EVICTIONSTRATEGY
from utilities.virt import VirtualMachineForTests

PREFER_NO_EVICTION_ANNOTATION = "descheduler.alpha.kubernetes.io/prefer-no-eviction"


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
        assert annotations[PREFER_NO_EVICTION_ANNOTATION] == "true", "Annotation not set when explicitly requested"

    def test_explicit_false_does_not_override_eviction_strategy(self):
        # False is the default (do not force exclusion); it must NOT suppress the
        # eviction-strategy-driven auto-exclusion for ES_NONE / ES_LIVE_MIGRATE_IF_POSSIBLE.
        vm = _build_vm_stub(exclude_from_descheduler=False, eviction_strategy=ES_NONE)
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"]["annotations"]
        assert annotations[PREFER_NO_EVICTION_ANNOTATION] == "true", "Annotation not auto-set for ES_NONE when False"

    def test_auto_exclude_for_es_none(self):
        vm = _build_vm_stub(eviction_strategy=ES_NONE)
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"]["annotations"]
        assert annotations[PREFER_NO_EVICTION_ANNOTATION] == "true", "Annotation not auto-set for ES_NONE"

    def test_auto_exclude_for_es_live_migrate_if_possible(self):
        vm = _build_vm_stub(eviction_strategy=ES_LIVE_MIGRATE_IF_POSSIBLE)
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"]["annotations"]
        assert annotations[PREFER_NO_EVICTION_ANNOTATION] == "true", (
            "Annotation not auto-set for ES_LIVE_MIGRATE_IF_POSSIBLE"
        )

    def test_no_annotation_without_matching_eviction_strategy(self):
        vm = _build_vm_stub(eviction_strategy="LiveMigrate")
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"].get("annotations", {})
        assert PREFER_NO_EVICTION_ANNOTATION not in annotations, "Annotation set for non-excluded eviction strategy"

    def test_no_annotation_when_no_eviction_strategy(self):
        vm = _build_vm_stub()
        vm._set_descheduler_exclusion()
        annotations = vm.res["spec"]["template"]["metadata"].get("annotations", {})
        assert PREFER_NO_EVICTION_ANNOTATION not in annotations, "Annotation set when no eviction strategy specified"


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
