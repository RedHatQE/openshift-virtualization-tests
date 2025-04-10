from typing import Any

import pytest_testconfig

import utilities.constants
from utilities.constants import (
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    PREFERENCE_STR,
    S390X,
    Images,
)

Images.Fedora.FEDORA41_IMG = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2"
Images.Rhel.RHEL9_5_IMG = "rhel-95-s390x.qcow2"
Images.Fedora.FEDORA_CONTAINER_IMAGE = "quay.io/chandramerla/qe-cnv-tests-fedora:40-s390x"
EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{S390X}"
NET_UTIL_CONTAINER_IMAGE = "quay.io/chandramerla/qe-cnv-tests-net-util-container:centos-stream-9"

# No support for cirros on s390x.  Use Fedora instead
Images.Cirros.RAW_IMG = "Fedora-Cloud-Base-Generic-41-1.4.s390x.raw"
Images.Cirros.RAW_IMG_GZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.gz"
Images.Cirros.RAW_IMG_XZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.xz"
Images.Cirros.QCOW2_IMG = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2"
Images.Cirros.QCOW2_IMG_GZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2.gz"
Images.Cirros.QCOW2_IMG_XZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2.xz"
Images.Cirros.DIR = Images.Fedora.DIR
Images.Cirros.DEFAULT_DV_SIZE = Images.Fedora.DEFAULT_DV_SIZE
Images.Cirros.DEFAULT_MEMORY_SIZE = Images.Fedora.DEFAULT_MEMORY_SIZE
utilities.constants.OS_FLAVOR_CIRROS = "fedora"

Images.Cdi.QCOW2_IMG = Images.Fedora.FEDORA41_IMG
Images.Cdi.DIR = Images.Fedora.DIR
Images.Cdi.DEFAULT_DV_SIZE = Images.Fedora.DEFAULT_DV_SIZE

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
