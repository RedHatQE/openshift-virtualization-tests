from typing import Final

from utilities.constants.cluster import NODE_ROLE_KUBERNETES_IO

RHCOS9_WORKER_LABEL: Final[str] = f"{NODE_ROLE_KUBERNETES_IO}/worker-rhcos9"
