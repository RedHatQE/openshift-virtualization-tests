from typing import NamedTuple


class RoleBindingSpec(NamedTuple):
    name: str
    subjects_kind: str
    subjects_name: str
    cluster_role_name: str
