import logging

import pytest
from kubernetes.dynamic.exceptions import BadRequestError
from ocp_resources.config_map import ConfigMap
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.secret import Secret
from ocp_resources.virtual_machine import VirtualMachine
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.product_uninstall.constants import BLOCK_REMOVAL_TEST_NODE_ID
from utilities.constants import CDI_SECRETS, DEFAULT_HCO_CONDITIONS, TIMEOUT_10MIN
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    get_hco_version,
    wait_for_hco_conditions,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

BLOCK_STRATEGY = "BlockUninstallIfWorkloadsExist"
REMOVE_STRATEGY = "RemoveWorkloads"
LOGGER = logging.getLogger(__name__)
DV_PARAMS = {
    "source": "blank",
    "dv_name": "test-hco-dv",
    "image": "",
    "dv_size": "64Mi",
    "storage_class": py_config["default_storage_class"],
}


def assert_expected_strategy(resource_objects, expected_strategy):
    incorrect_components = {
        component: resource_obj.instance.spec.uninstallStrategy
        for component, resource_obj in resource_objects.items()
        if resource_obj.instance.spec.uninstallStrategy != expected_strategy
    }

    assert not incorrect_components, (
        f"Incorrect uninstallStrategy found for following component(s) {incorrect_components}"
    )


def delete_cdi_configmap_and_secret(hco_namespace_name, client):
    cdi_configmaps = [
        "cdi-apiserver-signer-bundle",
        "cdi-uploadproxy-signer-bundle",
        "cdi-uploadserver-client-signer-bundle",
        "cdi-uploadserver-signer-bundle",
    ]
    secret_objects = [
        Secret(name=_secret, namespace=hco_namespace_name, client=client)
        for _secret in CDI_SECRETS
        if Secret(name=_secret, namespace=hco_namespace_name, client=client).exists
    ]
    configmap_objects = [
        ConfigMap(name=_cm, namespace=hco_namespace_name, client=client)
        for _cm in cdi_configmaps
        if ConfigMap(name=_cm, namespace=hco_namespace_name, client=client).exists
    ]

    for resource in secret_objects + configmap_objects:
        resource.clean_up()


def assert_mismatch_related_objects(actual, expected):
    mismatch_objects = []
    for idx, obj_record in enumerate(expected):
        if (
            obj_record["name"] != actual[idx]["name"]
            or obj_record["kind"] != actual[idx]["kind"]
            or (obj_record.get("namespace") and obj_record["namespace"] != actual[idx]["namespace"])
        ):
            mismatch_objects.append(obj_record)

    assert not mismatch_objects, (
        f"Related Objects missing after hco recreationList of missing related objects are: {mismatch_objects}"
    )


def recreate_hco(client, namespace, hco_resource):
    with HyperConverged(
        name=py_config["hco_cr_name"],
        namespace=namespace.name,
        client=client,
        teardown=False,
    ):
        wait_for_hco_conditions(
            admin_client=client,
            hco_namespace=namespace,
            consecutive_checks_count=10,
        )


def assert_missing_resources(resource_objects):
    missing_resources = {
        resource_object.kind: resource_object.name for resource_object in resource_objects if not resource_object.exists
    }

    assert not missing_resources, (
        f"Resource objects are expected to exist but missing.Missing objects are: {missing_resources}"
    )


def assert_hco_exists_after_delete(
    admin_client,
    hco_namespace,
    hco_resource,
    dv_resource,
):
    with pytest.raises(BadRequestError):
        hco_resource.delete(wait=True)

    actual_hco_status = {
        condition["type"]: condition["status"] for condition in hco_resource.instance.status.conditions
    }
    assert actual_hco_status == DEFAULT_HCO_CONDITIONS, (
        f"HCO condition is not stable. Actual HCO condition :{actual_hco_status}"
        f"expected condition is {DEFAULT_HCO_CONDITIONS}"
    )
    assert_missing_resources(
        resource_objects=[
            hco_resource,
            dv_resource,
        ],
    )


@pytest.fixture()
def hco_uninstall_strategy_remove_workloads(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"spec": {"uninstallStrategy": REMOVE_STRATEGY}}}
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            consecutive_checks_count=10,
        )
        yield


@pytest.fixture(scope="class")
def hco_fedora_vm(unprivileged_client, namespace):
    name = "cascade-delete-fedora-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.fixture(scope="class")
def stopped_fedora_vm(hco_fedora_vm):
    hco_fedora_vm.stop(wait=True)
    yield hco_fedora_vm
    hco_fedora_vm.start


@pytest.fixture(scope="function")
def removed_hco(admin_client, hco_namespace, hyperconverged_resource_scope_function):
    hyperconverged_resource_scope_function.delete(wait=True, timeout=TIMEOUT_10MIN)
    delete_cdi_configmap_and_secret(hco_namespace_name=hco_namespace.name, client=admin_client)
    yield

    # Recreate HCO, if it doesn't exist
    if not hyperconverged_resource_scope_function.exists:
        recreate_hco(
            client=admin_client,
            namespace=hco_namespace,
            hco_resource=hyperconverged_resource_scope_function,
        )


@pytest.fixture(scope="function")
def recreated_hco(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    removed_hco,
):
    # Recreate HCO
    recreate_hco(
        client=admin_client,
        namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_function,
    )


@pytest.mark.destructive
@pytest.mark.parametrize("data_volume_scope_class", [pytest.param(DV_PARAMS)], indirect=True)
class TestAttemptRemoveHCO:
    @pytest.mark.polarion("CNV-8615")
    def test_remove_hco_with_dv_no_vms(
        self,
        admin_client,
        hco_namespace,
        hyperconverged_resource_scope_function,
        data_volume_scope_class,
    ):
        """
        This test validates the failure to remove HCO,
        when there is only DV exists with no VM
        """
        assert_hco_exists_after_delete(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            hco_resource=hyperconverged_resource_scope_function,
            dv_resource=data_volume_scope_class,
        )

    @pytest.mark.polarion("CNV-8613")
    def test_default_uninstall_strategy(
        self,
        hco_fedora_vm,
        hyperconverged_resource_scope_function,
        data_volume_scope_class,
        cdi_resource_scope_function,
        kubevirt_resource,
    ):
        """
        This test validates the default uninstallStrategy 'BlockUninstallIfWorkloadsExist'
        of HCO, KubeVirt, CDI CR
        """
        resource_objects = {
            "hco": hyperconverged_resource_scope_function,
            "cdi": cdi_resource_scope_function,
            "kubevirt": kubevirt_resource,
        }
        assert_expected_strategy(
            resource_objects=resource_objects,
            expected_strategy=BLOCK_STRATEGY,
        )

    @pytest.mark.polarion("CNV-8614")
    def test_hco_removal_with_block_strategy_with_vm_and_dv(
        self,
        admin_client,
        hco_namespace,
        hco_fedora_vm,
        data_volume_scope_class,
        hyperconverged_resource_scope_function,
    ):
        """
        This test validates failure of HCO removal when both VM and DV exists
        """
        assert_hco_exists_after_delete(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            hco_resource=hyperconverged_resource_scope_function,
            dv_resource=data_volume_scope_class,
        )

    @pytest.mark.polarion("CNV-8725")
    def test_hco_removal_with_block_strategy_with_stopped_vm(
        self,
        admin_client,
        hco_namespace,
        stopped_fedora_vm,
        hyperconverged_resource_scope_function,
        data_volume_scope_class,
    ):
        """
        This test validates that the removal of HCO fails when VM
        exists in stopped state
        """
        assert_hco_exists_after_delete(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            hco_resource=hyperconverged_resource_scope_function,
            dv_resource=data_volume_scope_class,
        )


@pytest.mark.destructive
class TestRemoveHCO:
    @pytest.mark.polarion("CNV-8726")
    @pytest.mark.dependency(name=BLOCK_REMOVAL_TEST_NODE_ID)
    def test_block_strategy_no_dv_and_no_vm(
        self,
        removed_hco,
        hyperconverged_resource_scope_function,
    ):
        """
        Remove HCO CR with default uninstallStrategy
        BlockUninstallIfWorkloadsExist
        """
        assert not hyperconverged_resource_scope_function.exists, "hco still exists after test removed it"

    @pytest.mark.polarion("CNV-8618")
    @pytest.mark.parametrize("data_volume_scope_function", [pytest.param(DV_PARAMS)], indirect=True)
    def test_remove_strategy_with_dv_no_vm(
        self,
        hco_uninstall_strategy_remove_workloads,
        data_volume_scope_function,
        hyperconverged_resource_scope_function,
        removed_hco,
    ):
        """
        Remove HCO when DV exists with no VMs
        """
        assert not hyperconverged_resource_scope_function.exists, "hco still exists after test removed it"
        LOGGER.info(f"Successfully removed HCO  with {REMOVE_STRATEGY} uninstallStrategy, with DV and no VM in cluster")

    @pytest.mark.polarion("CNV-8617")
    @pytest.mark.parametrize("data_volume_scope_function", [pytest.param(DV_PARAMS)], indirect=True)
    def test_remove_strategy_with_vm_and_dv(
        self,
        hco_fedora_vm,
        hco_uninstall_strategy_remove_workloads,
        data_volume_scope_function,
        hyperconverged_resource_scope_function,
        removed_hco,
    ):
        """
        Test HCO removal after setting uninstallStrategy to
        RemoveWorkloads, with VMs and DVs
        """
        assert not hyperconverged_resource_scope_function.exists, "hco still exists after test removed it"
        LOGGER.info(f"Successfully removed HCO with f{REMOVE_STRATEGY} uninstallStrategywith VM and DV in the cluster")

    @pytest.mark.polarion("CNV-8751")
    def test_recreate_hco(
        self,
        admin_client,
        hco_namespace,
        hco_version_scope_class,
        hco_status_related_objects,
        recreated_hco,
        hyperconverged_resource_scope_function,
        cdi_resource_scope_function,
        kubevirt_resource,
    ):
        """
        Validate the uninstallStrategy remains at BlockUninstallIfWorkloadsExists
        after removing and creating HCO again. Also make sure that related objects
        too remain the same
        """
        # Validate 'uninstallStrategy' is "BlockUninstallIfWorkloadsExists
        resource_objects = {
            "hco": hyperconverged_resource_scope_function,
            "cdi": cdi_resource_scope_function,
            "kubevirt": kubevirt_resource,
        }

        assert_expected_strategy(
            resource_objects=resource_objects,
            expected_strategy=BLOCK_STRATEGY,
        )

        # Validate related objects before HCO removal and after recreating HCO
        related_objects_after_hco_created = hyperconverged_resource_scope_function.instance.status.relatedObjects
        assert_mismatch_related_objects(
            actual=related_objects_after_hco_created,
            expected=hco_status_related_objects,
        )

        # validate hco version after HCO creation
        hco_version_updated = get_hco_version(
            client=admin_client,
            hco_ns_name=hco_namespace.name,
        )
        assert hco_version_scope_class == hco_version_updated, (
            f"HCO version mismatch, expected {hco_version_scope_class}, but found {hco_version_updated}"
        )
