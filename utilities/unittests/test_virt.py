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


def _build_vm_stub(exclude_from_descheduler=None, eviction_strategy=None):
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
        assert vm.res["spec"]["template"]["metadata"]["annotations"][PREFER_NO_EVICTION_ANNOTATION] == "true"

    def test_explicit_false_skips_annotation(self):
        vm = _build_vm_stub(exclude_from_descheduler=False, eviction_strategy=ES_NONE)
        vm._set_descheduler_exclusion()
        assert PREFER_NO_EVICTION_ANNOTATION not in vm.res["spec"]["template"]["metadata"].get("annotations", {})

    def test_auto_exclude_for_es_none(self):
        vm = _build_vm_stub(eviction_strategy=ES_NONE)
        vm._set_descheduler_exclusion()
        assert vm.res["spec"]["template"]["metadata"]["annotations"][PREFER_NO_EVICTION_ANNOTATION] == "true"

    def test_auto_exclude_for_es_live_migrate_if_possible(self):
        vm = _build_vm_stub(eviction_strategy=ES_LIVE_MIGRATE_IF_POSSIBLE)
        vm._set_descheduler_exclusion()
        assert vm.res["spec"]["template"]["metadata"]["annotations"][PREFER_NO_EVICTION_ANNOTATION] == "true"

    def test_no_annotation_without_matching_eviction_strategy(self):
        vm = _build_vm_stub(eviction_strategy="LiveMigrate")
        vm._set_descheduler_exclusion()
        assert PREFER_NO_EVICTION_ANNOTATION not in vm.res["spec"]["template"]["metadata"].get("annotations", {})

    def test_no_annotation_when_no_eviction_strategy(self):
        vm = _build_vm_stub()
        vm._set_descheduler_exclusion()
        assert PREFER_NO_EVICTION_ANNOTATION not in vm.res["spec"]["template"]["metadata"].get("annotations", {})


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
