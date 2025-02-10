import logging

from ocp_resources.cluster_role_binding import ClusterRoleBinding

LOGGER = logging.getLogger(__name__)


def get_kubevirt_operator_role_binding_resource(admin_client):
    for crb in list(ClusterRoleBinding.get(dyn_client=admin_client)):
        subjects = crb.instance.subjects
        if subjects and subjects[0].name == "kubevirt-operator":
            return crb
