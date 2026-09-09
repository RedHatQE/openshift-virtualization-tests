"""Unit tests for utilities.virt helpers."""

import importlib
import sys

# conftest.py mocks utilities.virt; clear and reload the real module for these tests.
if "utilities.virt" in sys.modules:
    del sys.modules["utilities.virt"]

import utilities.virt

importlib.reload(utilities.virt)

from utilities.virt import VirtualMachineForTests


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
