# Compatibility shim: re-exports `Images` only.
#
# `Images` is computed here (not in images.py) to avoid a circular import:
# get_cluster_architecture() is called at module level and historically imported
# from this package.  Placing the computation here keeps images.py free of
# utilities/ dependencies beyond libs/.
#
# All other constants must be imported from their submodule directly, e.g.:
#   from utilities.constants.cluster import KUBERNETES_ARCH_LABEL
#   from utilities.constants.timeouts import TIMEOUT_5MIN
#   from utilities.constants.images import ArchImages
import sys

from utilities.architecture import get_cluster_architecture as _get_cluster_architecture
from utilities.constants.images import ArchImages as _ArchImages

__all__ = ["Images"]


def _select_images_arch() -> str:
    """Select the architecture for the import-time `Images` alias.

    get_cluster_architecture() returns a set, so next(iter(...)) depends on PYTHONHASHSEED
    on multiarch clusters. A single `--cpu-arch` on the command line wins (py_config is not
    populated yet at import time); otherwise use the alphabetically first cluster arch.
    """
    cluster_archs = _get_cluster_architecture()
    for index, arg in enumerate(sys.argv):
        if arg == "--cpu-arch" and index + 1 < len(sys.argv):
            requested = sys.argv[index + 1]
        elif arg.startswith("--cpu-arch="):
            requested = arg.split("=", 1)[1]
        else:
            continue
        if requested in cluster_archs:
            return requested
    return min(cluster_archs)


Images = getattr(_ArchImages, _select_images_arch().upper())
