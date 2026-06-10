"""Instance type and preference identifiers.

Name strings for KubeVirt instance types (U1_*), VM preferences (RHEL*_PREFERENCE,
CENTOS_*_PREFERENCE, WINDOWS_*_PREFERENCE), and the label structures built from them.

Not for OS test matrix parameter keys — those go in `os_matrix.py`.
"""

INSTANCE_TYPE_STR = "instance_type"
U1_MEDIUM_STR = "u1.medium"
U1_SMALL = "u1.small"
U1_LARGE = "u1.large"

PREFERENCE_STR = "preference"
FLAVOR_STR = "flavor"
OS_STR = "os"
LINUX_STR = "linux"
WORKLOAD_STR = "workload"

CENTOS_STREAM9_PREFERENCE = "centos.stream9"
CENTOS_STREAM10_PREFERENCE = "centos.stream10"
RHEL8_PREFERENCE = "rhel.8"
RHEL9_PREFERENCE = "rhel.9"
RHEL10_PREFERENCE = "rhel.10"

RHEL_WITH_INSTANCETYPE_AND_PREFERENCE = "rhel-with-instancetype-and-preference"

EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS = {
    INSTANCE_TYPE_STR: U1_MEDIUM_STR,
    PREFERENCE_STR: RHEL9_PREFERENCE,
    OS_STR: LINUX_STR,
}
