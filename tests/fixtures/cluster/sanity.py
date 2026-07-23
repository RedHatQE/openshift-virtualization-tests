"""Cluster sanity check fixtures."""

import pytest

from utilities.sanity import cluster_sanity


@pytest.fixture(scope="session")
def cluster_sanity_scope_session(
    request,
    nodes,
    cluster_storage_classes_names,
    admin_client,
    hco_namespace,
    junitxml_plugin,
    hyperconverged_resource_scope_session,
    installing_cnv,
):
    """
    Performs various cluster level checks, e.g.: storage class validation, node state, as well as all cnv pod
    check to ensure all are in 'Running' state, to determine current state of cluster
    """
    if not installing_cnv:
        cluster_sanity(
            request=request,
            admin_client=admin_client,
            cluster_storage_classes_names=cluster_storage_classes_names,
            nodes=nodes,
            hco_namespace=hco_namespace,
            junitxml_property=junitxml_plugin,
        )


@pytest.fixture(scope="module")
def cluster_sanity_scope_module(
    request,
    nodes,
    cluster_storage_classes_names,
    admin_client,
    hco_namespace,
    junitxml_plugin,
    hyperconverged_resource_scope_session,
    installing_cnv,
):
    """
    Performs various cluster level checks, e.g.: storage class validation, node state, as well as all cnv pod
    check to ensure all are in 'Running' state, to determine current state of cluster
    """
    if not installing_cnv:
        cluster_sanity(
            request=request,
            admin_client=admin_client,
            cluster_storage_classes_names=cluster_storage_classes_names,
            nodes=nodes,
            hco_namespace=hco_namespace,
            junitxml_property=junitxml_plugin,
        )
