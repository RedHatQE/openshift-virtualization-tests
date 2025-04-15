from typing import Any

import pytest_testconfig

import utilities.constants
from utilities.constants import (
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    PREFERENCE_STR,
    S390X,
    Images,
)

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

# No support for cirros on s390x.  Use Fedora instead
class Cirros(Images.Cirros):
    RAW_IMG = "Fedora-Cloud-Base-Generic-41-1.4.s390x.raw"
    RAW_IMG_GZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.gz"
    RAW_IMG_XZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.xz"
    QCOW2_IMG = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2"
    QCOW2_IMG_GZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2.gz"
    QCOW2_IMG_XZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2.xz"
    DISK_DEMO = "fedora-cloud-registry-disk-demo"
    DIR = "cnv-tests/fedora-images"
    DEFAULT_DV_SIZE = "10Gi"
    DEFAULT_MEMORY_SIZE = "1Gi"

class Cdi(Images.Cdi):
    QCOW2_IMG = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2"
    DIR = "cnv-tests/fedora-images"
    DEFAULT_DV_SIZE = "10Gi"

Images.Cirros = Cirros
utilities.constants.OS_FLAVOR_CIRROS = "fedora"
Images.Cdi = Cdi
Images.Fedora.FEDORA41_IMG = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2"
Images.Rhel.RHEL9_5_IMG = "rhel-95-s390x.qcow2"
EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{S390X}"

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
