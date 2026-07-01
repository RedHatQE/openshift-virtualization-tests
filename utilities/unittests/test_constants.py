"""Unit tests for constants package."""

from utilities.constants.architecture import (
    AMD_64,
    ARM_64,
    MULTIARCH,
    S390X,
    SUPPORTED_CPU_ARCHITECTURES,
    SUPPORTED_MULTIARCH_OPTIONS,
    X86_64,
)
from utilities.constants.components import (
    BRIDGE_MARKER,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_CSI,
    HOSTPATH_PROVISIONER_OPERATOR,
    HYPERCONVERGED_CLUSTER,
)
from utilities.constants.hco import DATA_IMPORT_CRON_ENABLE
from utilities.constants.images import (
    OS_FLAVOR_CIRROS,
    OS_FLAVOR_FEDORA,
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WINDOWS,
    ArchImages,
)
from utilities.constants.instance_types import (
    CENTOS_STREAM9_PREFERENCE,
    RHEL9_PREFERENCE,
    U1_LARGE,
    U1_SMALL,
    WORKLOAD_STR,
)
from utilities.constants.monitoring import (
    KUBEVIRT_HYPERCONVERGED_OPERATOR_HEALTH_STATUS,
    PENDING_STR,
)
from utilities.constants.networking import (
    LINUX_BRIDGE,
    OVS_BRIDGE,
)
from utilities.constants.os_matrix import (
    DV_SIZE_STR,
    IMAGE_NAME_STR,
    OS_VERSION_STR,
)
from utilities.constants.timeouts import (
    TCP_TIMEOUT_30SEC,
    TIMEOUT_1MIN,
    TIMEOUT_1SEC,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    TIMEOUT_30MIN,
    TIMEOUT_60MIN,
)
from utilities.constants.virt import (
    FIVE_GI_MEMORY,
    FOUR_GI_MEMORY,
    ONE_CPU_CORE,
    ONE_CPU_THREAD,
    SIX_GI_MEMORY,
    TEN_GI_MEMORY,
    TWELVE_GI_MEMORY,
    TWO_CPU_CORES,
    TWO_CPU_SOCKETS,
    TWO_CPU_THREADS,
    WIN_10,
    WIN_11,
)


class TestConstants:
    """Test cases for constants package."""

    def test_architecture_constants(self):
        """Test architecture constants are defined."""
        assert AMD_64 == "amd64"
        assert ARM_64 == "arm64"
        assert S390X == "s390x"
        assert X86_64 == "x86_64"
        assert MULTIARCH == "multiarch"
        assert SUPPORTED_MULTIARCH_OPTIONS == {"amd64", "arm64"}
        assert SUPPORTED_CPU_ARCHITECTURES == {"amd64", "arm64", "s390x"}

    def test_timeout_constants(self):
        """Test timeout constants are defined."""
        assert TIMEOUT_1SEC == 1
        assert TIMEOUT_1MIN == 60
        assert TIMEOUT_5MIN == 5 * 60
        assert TIMEOUT_10MIN == 10 * 60
        assert TIMEOUT_30MIN == 30 * 60
        assert TIMEOUT_60MIN == 60 * 60

    def test_tcp_timeout_constants(self):
        """Test TCP timeout constants are defined."""
        assert TCP_TIMEOUT_30SEC == 30.0

    def test_memory_constants(self):
        """Test memory constants are defined."""
        assert FOUR_GI_MEMORY == "4Gi"
        assert FIVE_GI_MEMORY == "5Gi"
        assert SIX_GI_MEMORY == "6Gi"
        assert TEN_GI_MEMORY == "10Gi"
        assert TWELVE_GI_MEMORY == "12Gi"

    def test_cpu_constants(self):
        """Test CPU constants are defined."""
        assert ONE_CPU_CORE == 1
        assert ONE_CPU_THREAD == 1
        assert TWO_CPU_CORES == 2
        assert TWO_CPU_SOCKETS == 2
        assert TWO_CPU_THREADS == 2

    def test_state_constants(self):
        """Test state constants are defined."""
        assert PENDING_STR == "pending"

    def test_cnv_operator_constants(self):
        """Test CNV operator constants are defined."""
        assert HCO_OPERATOR == "hco-operator"
        assert HCO_WEBHOOK == "hco-webhook"
        assert HYPERCONVERGED_CLUSTER == "hyperconverged-cluster"

    def test_storage_classes(self):
        """Test storage classes are defined."""
        assert HOSTPATH_PROVISIONER == "hostpath-provisioner"
        assert HOSTPATH_PROVISIONER_CSI == "hostpath-provisioner-csi"
        assert HOSTPATH_PROVISIONER_OPERATOR == "hostpath-provisioner-operator"

    def test_operator_health_impact_values(self):
        """Test operator health impact values are defined."""
        assert KUBEVIRT_HYPERCONVERGED_OPERATOR_HEALTH_STATUS == "kubevirt_hyperconverged_operator_health_status"

    def test_images_class_exists(self):
        """Test that ArchImages class exists."""
        assert hasattr(ArchImages, "AMD64")

    def test_data_import_cron_constants(self):
        """Test data import cron related constants are defined."""
        assert DATA_IMPORT_CRON_ENABLE.startswith("metadata->annotations->")

    def test_os_related_constants(self):
        """Test OS related constants are defined."""
        assert OS_FLAVOR_RHEL == "rhel"
        assert OS_FLAVOR_FEDORA == "fedora"
        assert OS_FLAVOR_WINDOWS == "win"
        assert OS_FLAVOR_CIRROS == "cirros"

    def test_windows_os_constants(self):
        """Test Windows OS constants are defined."""
        assert WIN_10 == "win10"
        assert WIN_11 == "win11"

    def test_workload_constants(self):
        """Test workload constants are defined."""
        assert WORKLOAD_STR == "workload"

    def test_network_constants(self):
        """Test network constants are defined."""
        assert LINUX_BRIDGE == "linux-bridge"
        assert OVS_BRIDGE == "ovs-bridge"
        assert BRIDGE_MARKER == "bridge-marker"
        assert CLUSTER_NETWORK_ADDONS_OPERATOR == "cluster-network-addons-operator"

    def test_instance_type_constants(self):
        """Test instance type and preference constants are defined."""
        assert U1_SMALL == "u1.small"
        assert U1_LARGE == "u1.large"
        assert RHEL9_PREFERENCE == "rhel.9"
        assert CENTOS_STREAM9_PREFERENCE == "centos.stream9"

    def test_os_matrix_constants(self):
        """Test OS matrix parameter key constants are defined."""
        assert IMAGE_NAME_STR == "image_name"
        assert OS_VERSION_STR == "os_version"
        assert DV_SIZE_STR == "dv_size"
