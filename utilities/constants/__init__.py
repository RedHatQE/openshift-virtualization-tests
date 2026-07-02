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
from utilities.architecture import get_cluster_architecture as _get_cluster_architecture
from utilities.constants.images import ArchImages as _ArchImages

__all__ = ["Images"]

Images = getattr(_ArchImages, next(iter(_get_cluster_architecture())).upper())
