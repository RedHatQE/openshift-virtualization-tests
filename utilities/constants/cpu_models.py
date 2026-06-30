"""CPU model exclusion lists.

Lists of CPU model names that are unsupported or cause known failures in VM guests.
Used in tests to skip or filter out problematic CPU models.
"""

EXCLUDED_CPU_MODELS_S390X = [
    # Below are deprecated & usable models, but violate RHEL 9 ALS (min z14) causing guest to crash (disable-wait)
    # Ref: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/automatically_installing_rhel/preparing-a-rhel-installation-on-64-bit-ibm-z_rhel-installer#planning-for-installation-on-ibm-z_preparing-a-rhel-installation-on-64-bit-ibm-z
    "z114",
    "z114-base",
    "z13",
    "z13-base",
    "z13.2",
    "z13.2-base",
    "z13s",
    "z13s-base",
    "z196",
    "z196-base",
    "z196.2",
    "z196.2-base",
    "zBC12",
    "zBC12-base",
    "zEC12",
    "zEC12-base",
    "zEC12.2",
    "zEC12.2-base",
    # Below are usable (non-deprecated) models, but base models doesn't work on RHEL guests
    # unless required features are appended (ex: 'gen15b-base,vx=on,..'),
    "z14ZR1-base",
    "z14.2-base",
    "z14-base",
    "gen15a-base",
    "gen15b-base",
    "gen16a-base",
    "gen16b-base",
    "gen17a-base",
    "gen17b-base",
]
# Opteron - Windows image can't boot
# Penryn - does not support WSL2
EXCLUDED_CPU_MODELS = [*EXCLUDED_CPU_MODELS_S390X, "Opteron", "Penryn"]
# Latest windows can't boot with old cpu models
EXCLUDED_OLD_CPU_MODELS = [*EXCLUDED_CPU_MODELS, "Westmere", "SandyBridge", "Nehalem", "IvyBridge", "Skylake"]
