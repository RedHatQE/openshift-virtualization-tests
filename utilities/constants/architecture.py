"""CPU architecture identifiers and multi-architecture support constants.

Covers architecture strings (AMD_64, ARM_64, S390X, X86_64), container platform
strings (LINUX_AMD_64), CPU vendor identifiers (INTEL, AMD), and supported
architecture sets.

Not here:
- Kubernetes architecture node label → ``cluster.py``
- CPU model exclusion lists → ``cpu_models.py``
- VM CPU topology counts (cores/sockets/threads) → ``virt.py``
- Image architecture variants → ``images.py``
"""

AMD_64 = "amd64"
ARM_64 = "arm64"
S390X = "s390x"
X86_64 = "x86_64"
MULTIARCH = "multiarch"
LINUX_AMD_64 = "linux/amd64"

INTEL = "Intel"
AMD = "AMD"

SUPPORTED_MULTIARCH_OPTIONS = {AMD_64, ARM_64}
SUPPORTED_CPU_ARCHITECTURES = {AMD_64, ARM_64, S390X}
