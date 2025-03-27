import pytest_testconfig

from utilities.constants import (
    S390X,
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    PREFERENCE_STR,
    Images,
)

Images.Cirros.RAW_IMG_XZ = "Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.xz"   ## chnage for x86 and s390x also
Images.Fedora.FEDORA40_IMG = "Fedora-Cloud-Base-Generic.s390x-40-1.14.qcow2"
Images.Rhel.RHEL9_5_IMG = "rhel-95-s390x.qcow2"
Images.Fedora.FEDORA_CONTAINER_IMAGE = "quay.io/chandramerla/qe-cnv-tests-fedora:40-s390x"
EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{S390X}"
##  TODO  KIRK Add Cirros and Cdi Overrides  (cirros qcow2 url: "https://cnv-qe-artifactory.apps.int.prod-stable-spoke1-dc-iad2.itup.redhat.com/artifactory/cnv-qe-server-local/cnv-tests/fedora-images/Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2")
## TODO OS_FLAVOR_CIRROS = "fedora"

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

for _dir in dir():
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
