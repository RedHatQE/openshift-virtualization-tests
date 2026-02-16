# Generated using Claude cli

"""Unit tests for constants module"""

import sys
from pathlib import Path

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import constants


class TestConstants:
    """Test cases for constants module"""

    def test_architecture_constants(self):
        """Test architecture constants are defined"""
        assert constants.AMD_64 == "amd64"
        assert constants.ARM_64 == "arm64"
        assert constants.S390X == "s390x"
        assert constants.X86_64 == "x86_64"

    def test_timeout_constants(self):
        """Test timeout constants are defined"""
        assert constants.TIMEOUT_1SEC == 1
        assert constants.TIMEOUT_1MIN == 60
        assert constants.TIMEOUT_5MIN == 5 * 60
        assert constants.TIMEOUT_10MIN == 10 * 60
        assert constants.TIMEOUT_30MIN == 30 * 60
        assert constants.TIMEOUT_60MIN == 60 * 60
        assert constants.TIMEOUT_12HRS == 12 * 60 * 60

    def test_tcp_timeout_constants(self):
        """Test TCP timeout constants are defined"""
        assert constants.TCP_TIMEOUT_30SEC == 30.0

    def test_memory_constants(self):
        """Test memory constants are defined"""
        assert constants.FOUR_GI_MEMORY == "4Gi"
        assert constants.FIVE_GI_MEMORY == "5Gi"
        assert constants.SIX_GI_MEMORY == "6Gi"
        assert constants.TEN_GI_MEMORY == "10Gi"
        assert constants.TWELVE_GI_MEMORY == "12Gi"

    def test_cpu_constants(self):
        """Test CPU constants are defined"""
        assert constants.ONE_CPU_CORE == 1
        assert constants.ONE_CPU_THREAD == 1
        assert constants.TWO_CPU_CORES == 2
        assert constants.TWO_CPU_SOCKETS == 2
        assert constants.TWO_CPU_THREADS == 2

    def test_state_constants(self):
        """Test state constants are defined"""
        assert constants.PENDING_STR == "pending"

    def test_cnv_operator_constants(self):
        """Test CNV operator constants are defined"""
        # Check for CNV related namespaces/operators
        assert constants.HCO_OPERATOR == "hco-operator"
        assert constants.HCO_WEBHOOK == "hco-webhook"
        assert constants.HYPERCONVERGED_CLUSTER == "hyperconverged-cluster"

    def test_storage_classes(self):
        """Test storage classes are defined"""
        # Check if storage class constants exist
        assert constants.HOSTPATH_PROVISIONER == "hostpath-provisioner"
        assert constants.HOSTPATH_PROVISIONER_CSI == "hostpath-provisioner-csi"
        assert constants.HOSTPATH_PROVISIONER_OPERATOR == "hostpath-provisioner-operator"

    def test_operator_health_impact_values(self):
        """Test operator health impact values are defined"""
        # Check for operator health related metrics
        assert (
            constants.KUBEVIRT_HYPERCONVERGED_OPERATOR_HEALTH_STATUS == "kubevirt_hyperconverged_operator_health_status"
        )

    def test_images_class_exists(self):
        """Test that ArchImages class exists"""
        assert hasattr(constants, "ArchImages")
        assert hasattr(constants.ArchImages, "AMD64")

    def test_data_import_cron_constants(self):
        """Test data import cron related constants are defined"""
        # Check for any data import cron related constants
        assert hasattr(constants, "DataImportCron")

    def test_os_related_constants(self):
        """Test OS related constants are defined"""
        # Check for OS-specific images or constants
        assert hasattr(constants, "Fedora")
        assert hasattr(constants, "Rhel")
        assert hasattr(constants, "Windows")
        assert hasattr(constants, "Centos")

    def test_windows_os_constants(self):
        """Test Windows OS constants are defined"""
        assert hasattr(constants, "Windows")

    def test_workload_constants(self):
        """Test workload constants are defined"""
        # Check for workload related constants
        assert constants.WORKLOAD_STR == "workload"

    def test_network_constants(self):
        """Test network constants are defined"""
        assert constants.LINUX_BRIDGE == "linux-bridge"
        assert constants.OVS_BRIDGE == "ovs-bridge"
        assert constants.BRIDGE_MARKER == "bridge-marker"
        assert constants.CLUSTER_NETWORK_ADDONS_OPERATOR == "cluster-network-addons-operator"
