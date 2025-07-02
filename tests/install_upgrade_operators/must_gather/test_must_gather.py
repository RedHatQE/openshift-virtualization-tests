# -*- coding: utf-8 -*-

import logging
import os
import re

import pytest
import yaml
from ocp_resources.api_service import APIService
from ocp_resources.cdi_config import CDIConfig
from ocp_resources.imagestreamtag import ImageStreamTag
from ocp_resources.mutating_webhook_config import MutatingWebhookConfiguration
from ocp_resources.namespace import Namespace
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource
from ocp_resources.template import Template
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.must_gather.utils import (
    VALIDATE_FIELDS,
    VALIDATE_UID_NAME,
    check_list_of_resources,
    check_logs,
    check_node_resource,
    check_resource,
    compare_resource_contents,
    compare_webhook_svc_contents,
)
from utilities.constants import (
    ALL_CNV_CRDS,
    BRIDGE_MARKER,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    KUBEMACPOOL_MAC_RANGE_CONFIG,
    VM_CRD,
    NamespacesNames,
)
from utilities.must_gather import get_must_gather_output_file

pytestmark = [pytest.mark.sno, pytest.mark.post_upgrade, pytest.mark.skip_must_gather_collection, pytest.mark.arm64]
LOGGER = logging.getLogger(__name__)


@pytest.mark.usefixtures(
    "collected_cluster_must_gather", "collected_must_gather_all_images", "cnv_image_path_must_gather_all_images"
)
class TestMustGatherCluster:
    @pytest.mark.parametrize(
        ("resource_type", "resource_path", "checks"),
        [
            pytest.param(
                NodeNetworkState,
                f"cluster-scoped-resources/{NodeNetworkState.ApiGroup.NMSTATE_IO}/nodenetworkstates/{{name}}.yaml",
                VALIDATE_UID_NAME,
                marks=(pytest.mark.polarion("CNV-2707")),
                id="test_nodenetworkstate_resources",
            ),
            pytest.param(
                NetworkAddonsConfig,
                f"cluster-scoped-resources/"
                f"networkaddonsconfigs.{NetworkAddonsConfig.ApiGroup.NETWORKADDONSOPERATOR_NETWORK_KUBEVIRT_IO}/"
                "{name}.yaml",
                VALIDATE_UID_NAME,
                marks=(pytest.mark.polarion("CNV-3042")),
                id="test_networkaddonsoperator_resources",
            ),
            pytest.param(
                CDIConfig,
                f"cluster-scoped-resources/cdiconfigs.{CDIConfig.ApiGroup.CDI_KUBEVIRT_IO}/{{name}}.yaml",
                VALIDATE_FIELDS,
                marks=(pytest.mark.polarion("CNV-3373")),
                id="test_cdi_config_resources",
            ),
        ],
        indirect=["resource_type"],
    )
    @pytest.mark.s390x
    def test_resource_type(
        self,
        admin_client,
        must_gather_for_test,
        resource_type,
        resource_path,
        checks,
    ):
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=resource_type,
            temp_dir=must_gather_for_test,
            resource_path=resource_path,
            checks=checks,
        )

    @pytest.mark.polarion("CNV-2982")
    @pytest.mark.s390x
    def test_namespace(self, hco_namespace, must_gather_for_test):
        namespace_name = hco_namespace.name
        check_resource(
            resource=Namespace,
            resource_name=namespace_name,
            temp_dir=must_gather_for_test,
            resource_path=f"namespaces/{namespace_name}/{namespace_name}.yaml",
            checks=VALIDATE_FIELDS,
        )

    @pytest.mark.polarion("CNV-5885")
    @pytest.mark.s390x
    def test_no_upstream_only_namespaces(self, must_gather_for_test, sriov_namespace):
        """
        After running must-gather command on the cluster, there are some upstream-only namespaces
        present. We counter "POD Error from server (NotFound)" in the logs as there no upstream-only
        namespaces present. This test case will ensure that there is no logs showing "POD Error from
        server (NotFound)" in the must-gather command execution.
        """
        upstream_namespaces = [
            "kubevirt-hyperconverged",
            "cluster-network-addons",
            sriov_namespace.name,
            "kubevirt-web-ui",
            "cdi",
        ]
        with open(get_must_gather_output_file(must_gather_for_test)) as file_content:
            must_gather_output = file_content.read()
        match_output = re.findall(
            r"Error from server \(NotFound\): namespaces \"(\S+)\" not found",
            must_gather_output,
        )
        LOGGER.info(f"Matching: {match_output}")
        matching_upstream_namespaces = [namespace for namespace in match_output if namespace in upstream_namespaces]
        assert not matching_upstream_namespaces, (
            f"Found namespace errors in must-gather for the following namespaces {matching_upstream_namespaces}"
        )

    @pytest.mark.parametrize(
        "label_selector, resource_namespace",
        [
            pytest.param(
                f"app={BRIDGE_MARKER}",
                py_config["hco_namespace"],
                marks=(pytest.mark.polarion("CNV-2721")),
                id="test_bridge_marker_pods",
            ),
            pytest.param(
                f"name={KUBE_CNI_LINUX_BRIDGE_PLUGIN}",
                py_config["hco_namespace"],
                marks=(pytest.mark.polarion("CNV-2705")),
                id="test_kube_cni_pods",
            ),
            pytest.param(
                "kubemacpool-leader=true",
                py_config["hco_namespace"],
                marks=(pytest.mark.polarion("CNV-2983")),
                id=f"{KUBEMACPOOL_MAC_CONTROLLER_MANAGER}_pods",
            ),
            pytest.param(
                f"name={CLUSTER_NETWORK_ADDONS_OPERATOR}",
                py_config["hco_namespace"],
                marks=(pytest.mark.polarion("CNV-2985")),
                id=f"{CLUSTER_NETWORK_ADDONS_OPERATOR}_pods",
            ),
            pytest.param(
                "app=ovs-cni",
                py_config["hco_namespace"],
                marks=(pytest.mark.polarion("CNV-2986")),
                id="ovs-cni_pods",
            ),
            pytest.param(
                "app=kubemacpool",
                py_config["hco_namespace"],
                marks=(pytest.mark.polarion("CNV-8880")),
                id="kubemacpool_pods",
            ),
            pytest.param(
                "app=containerized-data-importer",
                py_config["hco_namespace"],
                marks=(pytest.mark.polarion("CNV-3369")),
                id="test_cdi_deployment_pods",
            ),
        ],
    )
    @pytest.mark.s390x
    def test_pods(
        self,
        admin_client,
        must_gather_for_test,
        label_selector,
        resource_namespace,
    ):
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=Pod,
            temp_dir=must_gather_for_test,
            resource_path="namespaces/{namespace}/pods/{name}/{name}.yaml",
            checks=VALIDATE_UID_NAME,
            namespace=resource_namespace,
            label_selector=label_selector,
        )

    @pytest.mark.polarion("CNV-2727")
    @pytest.mark.s390x
    def test_template_in_openshift_ns_data(self, admin_client, must_gather_for_test):
        template_resources = list(
            Template.get(dyn_client=admin_client, singular_name="template", namespace="openshift")
        )
        template_log = os.path.join(
            must_gather_for_test,
            "namespaces/openshift/templates/openshift.yaml",
        )
        with open(template_log, "r") as _file:
            data = _file.read()
        count_templates = data.count(f"kind: {template_resources[0].kind}")
        assert len(template_resources) == count_templates, (
            f"Expected templates: {[template.name for template in template_resources]}, actual number of templates"
            f"{count_templates}"
        )

    @pytest.mark.polarion("CNV-2809")
    @pytest.mark.s390x
    def test_node_nftables(self, collected_nft_files_must_gather, nftables_from_utility_pods):
        table_not_found_errors = []
        for node_name in collected_nft_files_must_gather:
            nftables = nftables_from_utility_pods[node_name]
            file_name = collected_nft_files_must_gather[node_name]
            with open(file_name) as _file:
                gathered_data = _file.read()
                not_found_tables = [table for table in nftables if table not in gathered_data]
                if not_found_tables:
                    table_not_found_errors.append(
                        f"File:{file_name} - does not contain follwowing nftables:{not_found_tables}"
                    )

        assert not table_not_found_errors, f"Following nftables were not collected: {table_not_found_errors}"

    @pytest.mark.parametrize(
        "cmd, results_file, compare_method",
        [
            pytest.param(
                ["ip", "-o", "link", "show", "type", "bridge"],
                "bridge",
                "simple_compare",
                marks=(pytest.mark.polarion("CNV-2730"),),
                id="test_nodes_bridge_data",
            ),
            pytest.param(
                ["/bin/bash", "-c", "ls -l /host/var/lib/cni/bin"],
                "var-lib-cni-bin",
                "simple_compare",
                marks=(pytest.mark.polarion("CNV-2810"),),
                id="test_nodes_cni_bin_data",
            ),
            pytest.param(
                ["ip", "a"],
                "ip.txt",
                "not_empty",
                marks=(pytest.mark.polarion("CNV-2732"),),
                id="test_nodes_ip_data",
            ),
        ],
    )
    @pytest.mark.s390x
    def test_node_resource(
        self,
        must_gather_for_test,
        workers_utility_pods,
        cmd,
        results_file,
        compare_method,
    ):
        for pod in workers_utility_pods:
            check_node_resource(
                temp_dir=must_gather_for_test,
                cmd=cmd,
                utility_pod=pod,
                results_file=results_file,
                compare_method=compare_method,
            )

    @pytest.mark.polarion("CNV-2801")
    @pytest.mark.s390x
    def test_nmstate_config_data(self, admin_client, must_gather_for_test):
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=NodeNetworkState,
            temp_dir=must_gather_for_test,
            resource_path=f"cluster-scoped-resources/{NodeNetworkState.ApiGroup.NMSTATE_IO}/"
            "nodenetworkstates/{name}.yaml",
            checks=(("metadata", "name"), ("metadata", "uid")),
        )

    @pytest.mark.parametrize(
        "label_selector",
        [pytest.param({"app": "cni-plugins"}, marks=(pytest.mark.polarion("CNV-2715")))],
    )
    @pytest.mark.s390x
    def test_logs_gathering(self, must_gather_for_test, running_hco_containers, label_selector):
        check_logs(
            cnv_must_gather=must_gather_for_test,
            running_hco_containers=running_hco_containers,
            label_selector=label_selector,
            namespace=py_config["hco_namespace"],
        )

    @pytest.mark.parametrize(
        "config_map_by_name, has_owner",
        [
            pytest.param(
                [KUBEMACPOOL_MAC_RANGE_CONFIG, py_config["hco_namespace"]],
                True,
                marks=(pytest.mark.polarion("CNV-2718")),
                id="test_config_map_kubemacpool-mac-range-config",
            ),
        ],
        indirect=["config_map_by_name"],
    )
    @pytest.mark.s390x
    def test_gathered_config_maps(
        self,
        must_gather_for_test,
        config_maps_file,
        config_map_by_name,
        has_owner,
    ):
        compare_resource_contents(
            resource=config_map_by_name,
            file_content=next(
                filter(
                    lambda resource: resource["metadata"]["name"] == config_map_by_name.name,
                    config_maps_file["items"],
                )
            ),
            checks=VALIDATE_UID_NAME + (("metadata", "ownerReferences"),),
        )

    @pytest.mark.polarion("CNV-2723")
    @pytest.mark.s390x
    def test_apiservice_resources(self, admin_client, must_gather_for_test):
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=APIService,
            temp_dir=must_gather_for_test,
            resource_path="apiservices/{name}.yaml",
            checks=VALIDATE_FIELDS,
            filter_resource="kubevirt",
        )

    @pytest.mark.polarion("CNV-2726")
    @pytest.mark.s390x
    def test_webhookconfig_resources(self, admin_client, must_gather_for_test):
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=ValidatingWebhookConfiguration,
            temp_dir=must_gather_for_test,
            resource_path="webhooks/validating/{name}/validatingwebhookconfiguration.yaml",
            checks=VALIDATE_UID_NAME,
        )
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=MutatingWebhookConfiguration,
            temp_dir=must_gather_for_test,
            resource_path="webhooks/mutating/{name}/mutatingwebhookconfiguration.yaml",
            checks=VALIDATE_UID_NAME,
        )

        for webhook_resources in [
            list(ValidatingWebhookConfiguration.get(dyn_client=admin_client)),
            list(MutatingWebhookConfiguration.get(dyn_client=admin_client)),
        ]:
            compare_webhook_svc_contents(
                webhook_resources=webhook_resources,
                cnv_must_gather=must_gather_for_test,
                dyn_client=admin_client,
                checks=VALIDATE_UID_NAME,
            )

    @pytest.mark.polarion("CNV-8508")
    @pytest.mark.s390x
    def test_no_new_cnv_crds(self, kubevirt_crd_names):
        new_crds = [crd for crd in kubevirt_crd_names if crd not in ALL_CNV_CRDS]
        assert not new_crds, f"Following crds are new: {new_crds}."

    @pytest.mark.polarion("CNV-2724")
    @pytest.mark.s390x
    def test_crd_resources(self, admin_client, must_gather_for_test, kubevirt_crd_by_type):
        crd_name = kubevirt_crd_by_type.name
        for version in kubevirt_crd_by_type.instance.spec.versions:
            if not version.served:
                LOGGER.warning(f"Skipping {version.name} for {crd_name} because it is not served")
                continue
            resource_objs = admin_client.resources.get(
                api_version=version.name,
                kind=kubevirt_crd_by_type.instance.spec.names.kind,
            )

            for resource_item in resource_objs.get().to_dict()["items"]:
                resource_metadata = resource_item["metadata"]
                name = resource_metadata["name"]
                if "namespace" in resource_metadata:
                    if crd_name == VM_CRD:
                        resource_file = os.path.join(
                            must_gather_for_test,
                            f"namespaces/{resource_metadata['namespace']}/{Resource.ApiGroup.KUBEVIRT_IO}"
                            f"/virtualmachines/custom/{name}.yaml",
                        )
                    else:
                        resource_file = os.path.join(
                            must_gather_for_test,
                            f"namespaces/{resource_metadata['namespace']}/crs/{crd_name}/{name}.yaml",
                        )
                else:
                    resource_file = os.path.join(
                        must_gather_for_test,
                        f"cluster-scoped-resources/{crd_name}/{name}.yaml",
                    )

                with open(resource_file) as resource_file:
                    file_content = yaml.safe_load(
                        resource_file.read(),
                    )
                resource_name_from_file = file_content["metadata"]["name"]
                resource_uid_from_file = file_content["metadata"]["uid"]
                actual_resource_uid = resource_metadata["uid"]
                assert name == resource_name_from_file, (
                    f"Actual resource name: {name}, must-gather collected resource name: {resource_name_from_file}"
                )

                assert actual_resource_uid == resource_uid_from_file, (
                    f"Resource uid: {actual_resource_uid} does not "
                    "match with must-gather data:"
                    f" {resource_uid_from_file}"
                )

    @pytest.mark.polarion("CNV-2939")
    @pytest.mark.s390x
    def test_image_stream_tag_resources(self, admin_client, must_gather_for_test):
        resource_path = (
            f"namespaces/{NamespacesNames.OPENSHIFT}/{ImageStreamTag.ApiGroup.IMAGE_OPENSHIFT_IO}/imagestreamtags"
        )
        istag_dir = os.path.join(
            must_gather_for_test,
            resource_path,
        )
        assert len(os.listdir(istag_dir)) == len(
            list(ImageStreamTag.get(dyn_client=admin_client, namespace=NamespacesNames.OPENSHIFT))
        )
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=ImageStreamTag,
            temp_dir=must_gather_for_test,
            resource_path=f"{resource_path}/{{name}}.yaml",
            checks=VALIDATE_UID_NAME,
            namespace=NamespacesNames.OPENSHIFT,
            filter_resource="redhat",
        )


@pytest.mark.special_infra
class TestSriovMustGather:
    @pytest.mark.polarion("CNV-3045")
    def test_node_sriov_resource(
        self,
        must_gather_for_test,
        workers_utility_pods,
    ):
        for pod in workers_utility_pods:
            check_node_resource(
                temp_dir=must_gather_for_test,
                cmd=["ls", "-al", "/host/dev/vfio"],
                utility_pod=pod,
                results_file="dev_vfio",
                compare_method="simple_compare",
            )


class TestCNVCollectsLogs:
    @pytest.mark.polarion("CNV-9906")
    @pytest.mark.s390x
    def test_kubevirt_logs_collected(self, gathered_kubevirt_logs, running_hco_containers, hco_namespace):
        LOGGER.info(f"Pod containers: {running_hco_containers}")
        check_logs(
            cnv_must_gather=gathered_kubevirt_logs,
            running_hco_containers=running_hco_containers,
            namespace=hco_namespace.name,
        )
