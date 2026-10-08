"""
Storage migration cleanup tests for storage migration plans.

Tests verify the retentionPolicy field functionality, which controls whether source DataVolumes/PVCs
are kept (keepSource) or deleted (deleteSource) after successful VM storage migration.

The retentionPolicy field can be configured at:
- Namespace level for MultiNamespaceVirtualMachineStorageMigrationPlan
- Plan level (spec) for MultiNamespaceVirtualMachineStorageMigrationPlan
- Combination of namespace and plan level for MultiNamespaceVirtualMachineStorageMigrationPlan
  (namespace-level overrides plan-level when both are configured)

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_cleanup.md
"""

import pytest
from pytest_testconfig import config as py_config

from tests.storage.constants import STORAGE_CLASS_A, STORAGE_CLASS_B
from tests.storage.storage_migration.constants import DELETE_SOURCE, KEEP_SOURCE
from tests.storage.storage_migration.utils import (
    verify_source_dvs_deleted,
    verify_source_dvs_exist,
    verify_vm_storage_class_updated,
)
from utilities.constants.pytest import QUARANTINED

