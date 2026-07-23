"""Unit tests for utilities.virt helpers."""

import os
import sys
from pathlib import Path

os.environ["OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH"] = "amd64"

# utilities/unittests is on sys.path via conftest; ensure repo root imports work.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utilities.architecture import get_cluster_architecture

get_cluster_architecture.cache_clear()

from utilities.virt import VirtualMachineForTests


class TestVirtualMachineForTestsLabel:
    def test_label_preserved_when_body_replaces_metadata(self):
        """Caller-provided label must survive generate_body() metadata overwrite."""
        vm = VirtualMachineForTests.__new__(VirtualMachineForTests)
        vm.name = "test-vm"
        vm.body = {
            "metadata": {"labels": {"existing": "true"}},
            "spec": {"template": {"spec": {"domain": {}}}},
        }
        vm.label = {"changedBlockTracking": "true"}
        vm.annotations = None
        vm.res = {"metadata": {"name": "test-vm"}}

        vm.generate_body()

        assert vm.res["metadata"]["labels"]["changedBlockTracking"] == "true"
        assert vm.res["metadata"]["labels"]["existing"] == "true"
