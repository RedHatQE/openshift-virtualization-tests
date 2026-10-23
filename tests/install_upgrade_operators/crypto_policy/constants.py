from copy import deepcopy
from typing import Any

from ocp_resources.aaq import AAQ
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.mig_controller import MigController
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.ssp import SSP

from tests.install_upgrade_operators.constants import KEY_PATH_SEPARATOR
from utilities.constants.hco import (
    TLS_CUSTOM_POLICY,
    TLS_OLD_POLICY,
)

MANAGED_CRS_LIST = [KubeVirt, CDI, NetworkAddonsConfig, SSP]
MANAGED_CRS_LIST_WITH_AAQ = [*MANAGED_CRS_LIST, AAQ]

TLS_MODERN_POLICY = "modern"
TLS_INTERMEDIATE_POLICY = "intermediate"
TLS_INTERMEDIATE_PROFILE = {TLS_INTERMEDIATE_POLICY: {}, "type": "Intermediate"}

TLS_CUSTOM_CIPHERS = [
    "ECDHE-RSA-AES128-GCM-SHA256",
    "ECDHE-ECDSA-AES128-GCM-SHA256",
]
TLS_CUSTOM_VERSION = "VersionTLS12"

TLS_CUSTOM_PROFILE = {
    TLS_CUSTOM_POLICY: {
        "minTLSVersion": TLS_CUSTOM_VERSION,
        "ciphers": TLS_CUSTOM_CIPHERS,
    },
    "type": "Custom",
}
TLS_OLD_PROFILE = {TLS_OLD_POLICY: {}, "type": "Old"}
CRYPTO_POLICY_SPEC_DICT = {
    TLS_OLD_POLICY: TLS_OLD_PROFILE,
    TLS_CUSTOM_POLICY: TLS_CUSTOM_PROFILE,
}

KUBEVIRT_OLD_PROFILE = {
    "ciphers": [
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
        "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
        "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
        "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
        "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
        "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256",
        "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
        "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256",
        "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256",
        "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA",
        "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA",
        "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA",
        "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA",
        "TLS_RSA_WITH_AES_128_GCM_SHA256",
        "TLS_RSA_WITH_AES_256_GCM_SHA384",
        "TLS_RSA_WITH_AES_128_CBC_SHA256",
        "TLS_RSA_WITH_AES_128_CBC_SHA",
        "TLS_RSA_WITH_AES_256_CBC_SHA",
        "TLS_RSA_WITH_3DES_EDE_CBC_SHA",
    ],
    "minTLSVersion": "VersionTLS10",
}
KUBEVIRT_TLS_CONFIG_KEY = "tlsConfiguration"
KUBEVIRT_TLS_CONFIG_STR = f"configuration{KEY_PATH_SEPARATOR}{KUBEVIRT_TLS_CONFIG_KEY}"

TLS_INTERMEDIATE_CIPHERS_IANA_OPENSSL_SYNTAX = {
    "TLS_AES_128_GCM_SHA256": "TLS_AES_128_GCM_SHA256",
    "TLS_AES_256_GCM_SHA384": "TLS_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256": "TLS_CHACHA20_POLY1305_SHA256",
    "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256": "ECDHE-ECDSA-AES128-GCM-SHA256",
    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256": "ECDHE-RSA-AES128-GCM-SHA256",
    "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384": "ECDHE-ECDSA-AES256-GCM-SHA384",
    "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384": "ECDHE-RSA-AES256-GCM-SHA384",
    "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256": "ECDHE-ECDSA-CHACHA20-POLY1305",
    "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256": "ECDHE-RSA-CHACHA20-POLY1305",
}

# For Kubevirt need to convert from OPENSSL to IANA syntax and keep ciphers order same as in TLS_CUSTOM_PROFILE
TLS_CUSTOM_PROFILE_KUBEVIRT: dict[str, Any] = deepcopy(TLS_CUSTOM_PROFILE)
TLS_CUSTOM_PROFILE_KUBEVIRT[TLS_CUSTOM_POLICY]["ciphers"] = [
    key
    for cipher in TLS_CUSTOM_CIPHERS
    for key, value in TLS_INTERMEDIATE_CIPHERS_IANA_OPENSSL_SYNTAX.items()
    if value == cipher
]

CRYPTO_POLICY_EXPECTED_DICT = {
    TLS_INTERMEDIATE_POLICY: {
        KubeVirt: {
            "ciphers": list(TLS_INTERMEDIATE_CIPHERS_IANA_OPENSSL_SYNTAX.keys()),
            "minTLSVersion": "VersionTLS12",
        },
        SSP: TLS_INTERMEDIATE_PROFILE,
        CDI: TLS_INTERMEDIATE_PROFILE,
        NetworkAddonsConfig: TLS_INTERMEDIATE_PROFILE,
        MigController: TLS_INTERMEDIATE_PROFILE,
    },
    TLS_CUSTOM_POLICY: {
        KubeVirt: TLS_CUSTOM_PROFILE_KUBEVIRT[TLS_CUSTOM_POLICY],
        SSP: TLS_CUSTOM_PROFILE,
        CDI: TLS_CUSTOM_PROFILE,
        NetworkAddonsConfig: TLS_CUSTOM_PROFILE,
        MigController: TLS_CUSTOM_PROFILE,
    },
    TLS_OLD_POLICY: {
        KubeVirt: KUBEVIRT_OLD_PROFILE,
        SSP: TLS_OLD_PROFILE,
        CDI: TLS_OLD_PROFILE,
        NetworkAddonsConfig: TLS_OLD_PROFILE,
        MigController: TLS_OLD_PROFILE,
    },
}

MIN_TLS_VERSIONS = {
    # services can't connect with 1.0/1.1, so TLS_OLD_POLICY is set with "1.2"
    TLS_OLD_POLICY: "1.2",
    TLS_INTERMEDIATE_POLICY: "1.2",
    TLS_MODERN_POLICY: "1.3",
    TLS_CUSTOM_POLICY: str(float(TLS_CUSTOM_VERSION[-2:]) / 10),
}

TLS_MODERN_PROFILE = {TLS_MODERN_POLICY: {}, "type": "Modern"}
TLS_VERSION_1_2 = "1.2"
TLS_VERSION_1_3 = "1.3"

PQC_GROUP_SECP256R1_MLKEM768 = "SecP256r1MLKEM768"
PQC_GROUP_SECP384R1_MLKEM1024 = "SecP384r1MLKEM1024"
PQC_GROUP_X25519_MLKEM768 = "X25519MLKEM768"
PQC_HANDSHAKE_FAILURE_INDICATOR = "alert handshake failure"
OPENSSL_CONNECTION_SUCCESS_INDICATOR = "Certificate chain"

CONSOLE_PLUGIN_SERVICE_PORT = 9443
CONSOLE_PLUGIN_SERVICE_NAME = "kubevirt-console-plugin-service"

# Services whose backing component does not yet propagate configured TLS curves
# (their epic stories under CNV-82576 are still open). Mapped to the tracking Jira so
# is_jira_open gating tolerates current behavior now and auto-enables strict
# assertions once each story is resolved.
CURVE_PROPAGATION_PENDING = {
    "aaq-server": "CNV-85522",
    "aaq-prometheus-metrics": "CNV-85522",
    "cdi-api": "CNV-84876",
    "cdi-prometheus-metrics": "CNV-84876",
    "cdi-uploadproxy": "CNV-84876",
    "virt-api": "CNV-84875",
    "kubevirt-operator-webhook": "CNV-84875",
    "virt-exportproxy": "CNV-84875",
    "kubevirt-migration-prometheus": "CNV-84877",
    "virt-template-api-service": "CNV-85154",
    "virt-template-controller-manager-metrics-service": "CNV-85154",
    "virt-template-webhook-service": "CNV-85154",
    "hpp-prometheus-metrics": "CNV-84804",
    "hostpath-provisioner-operator-service": "CNV-84804",
    # console-plugin writes the configured curves to its nginx configmap, but HCO does
    # not roll the deployment, so the running pods keep serving stale curves until the
    # bug is fixed. Gated so it auto-asserts once CNV-99597 is resolved.
    CONSOLE_PLUGIN_SERVICE_NAME: "CNV-99597",
}

# Services whose TLS endpoint cannot be verified with an openssl s_client handshake:
# - kubevirt-apiserver-proxy-service: Go proxy that requires ALPN / a real proxied
#   request; a bare s_client handshake never completes (returns no cipher).
# - virt-observability-controller-metrics: controller-runtime mTLS metrics endpoint;
#   a client certificate is required to complete the handshake.
CURVE_PROBE_EXCLUDED = {
    "kubevirt-apiserver-proxy-service",
    "virt-observability-controller-metrics",
}

# Classical (non-PQC) curve names, as used by both the TLSSecurityProfile `groups`
# field and openssl's `-groups` argument.
TLS_GROUP_SECP256R1 = "secp256r1"
TLS_GROUP_SECP384R1 = "secp384r1"
TLS_GROUP_X25519 = "X25519"

# Curve set applied by the TLS-curve propagation test. It intentionally includes
# SecP256r1MLKEM768 - a NIST-paired PQC hybrid that is NOT in Go's default
# CurvePreferences - so that a service negotiating it proves the configured curve
# actually propagated, rather than merely matching a Go default.
TLS_PROPAGATION_CUSTOM_GROUPS = [
    TLS_GROUP_SECP256R1,
    TLS_GROUP_SECP384R1,
    PQC_GROUP_X25519_MLKEM768,
    PQC_GROUP_SECP256R1_MLKEM768,
]

# Curve deliberately omitted from the applied profile. Used as the negative probe:
# a service that enforces the profile must reject it.
TLS_PROPAGATION_OMITTED_GROUP = TLS_GROUP_X25519

# Custom TLS profile applied (HCO-direct) by the curve-propagation test. TLS 1.2 with
# dual-auth ciphers (RSA + ECDSA, avoiding cert/cipher mismatch) carrying the curated
# curve set. minTLSVersion 1.2 still permits 1.3, so the ML-KEM hybrid groups (which
# are TLS 1.3-only) are negotiated over 1.3. TLS 1.3 is avoided here because CDI
# requires custom.ciphers, which HCO forbids at 1.3 - that version behavior is covered
# by the separate tier3 profile-propagation test.
TLS_PROPAGATION_CUSTOM_PROFILE = {
    TLS_CUSTOM_POLICY: {
        "minTLSVersion": TLS_CUSTOM_VERSION,
        "ciphers": TLS_CUSTOM_CIPHERS,
        "groups": TLS_PROPAGATION_CUSTOM_GROUPS,
    },
    "type": "Custom",
}

# Curve25519-based groups that are not FIPS-approved (NIST SP 800-56Ar3). Go's TLS
# runtime drops them under FIPS, and the HCO console-plugin handler strips them
# unconditionally (GetFIPSCompliantGroups), so they are not expected to negotiate
# on Go services under FIPS, nor on the console-plugin on any cluster.
NON_FIPS_GROUPS = [TLS_GROUP_X25519, PQC_GROUP_X25519_MLKEM768]
