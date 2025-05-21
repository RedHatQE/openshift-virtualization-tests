import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.resource import ResourceEditor

from utilities.constants import MIGRATION_POLICY_VM_LABEL
from utilities.infra import label_project
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
)

NAMESPACE_LABEL = {"awesome-namespace-label": ""}

DEFAULT_MIGRATION_POLICY_PARAMETERS = {
    "allowAutoConverge": False,
    "allowPostCopy": False,
    "bandwidthPerMigration": "0Mi",
    "completionTimeoutPerGiB": 800,
}


def assert_applied_migration_policy(vmi, expected_policy):
    applied_policy = vmi.instance.status.migrationState.migrationPolicyName
    assert applied_policy == expected_policy, (
        f"Incorrect migration policy applied. Expected: {expected_policy}, applied: {applied_policy}"
    )


def assert_applied_migration_configuration(vmi, migration_policy):
    expected_params = DEFAULT_MIGRATION_POLICY_PARAMETERS.copy()
    expected_params.update(
        (param, value) for param, value in migration_policy.instance.spec.items() if param in expected_params
    )

    wrong_values = {}
    for key, expected_value in expected_params.items():
        applied_value = vmi.instance.status.migrationState.migrationConfiguration[key]
        if applied_value != expected_value:
            wrong_values[key] = {"expected": expected_value, "actual": applied_value}

    assert not wrong_values, f"Wrong values applied: \n{wrong_values}"


def create_migration_policy(request):
    with MigrationPolicy(
        name=request.param.get("name", "migration-policy"),
        allow_auto_converge=request.param.get("allowAutoConverge"),
        bandwidth_per_migration=request.param.get("bandwidthPerMigration"),
        completion_timeout_per_gb=request.param.get("completionTimeoutPerGiB"),
        allow_post_copy=request.param.get("allowPostCopy"),
        namespace_selector=request.param.get("namespaceSelector"),
        vmi_selector=request.param.get("virtualMachineInstanceSelector"),
    ) as mp:
        yield mp


def remove_spec_param_from_migration_policy(migration_policy, param):
    mp_spec = migration_policy.instance.to_dict()["spec"]
    del mp_spec[param]
    ResourceEditor({migration_policy: {"spec": mp_spec}}, action="replace").update()


@pytest.fixture()
def labeled_namespace(request, admin_client, namespace):
    label_project(name=namespace.name, label=request.param, admin_client=admin_client)


@pytest.fixture()
def migration_policy_a(request):
    yield from create_migration_policy(request=request)


@pytest.fixture()
def migration_policy_b(request):
    yield from create_migration_policy(request=request)


@pytest.fixture()
def vm_for_migration_policy_test(
    request,
    namespace,
    cpu_for_migration,
):
    name = "vm-for-migration-policy-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        additional_labels=request.param,
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_migrated_with_policy(vm_for_migration_policy_test):
    migrate_vm_and_verify(vm=vm_for_migration_policy_test)


@pytest.fixture()
def vm_re_migrated_after_updating_migration_policy(vm_for_migration_policy_test, migration_policy_a):
    assert_applied_migration_configuration(
        vmi=vm_for_migration_policy_test.vmi,
        migration_policy=migration_policy_a,
    )
    remove_spec_param_from_migration_policy(migration_policy=migration_policy_a, param="allowAutoConverge")
    migrate_vm_and_verify(vm=vm_for_migration_policy_test)


@pytest.mark.rwx_default_storage
@pytest.mark.arm64
class TestMigrationPolicies:
    @pytest.mark.gating
    @pytest.mark.parametrize(
        "migration_policy_a, vm_for_migration_policy_test, labeled_namespace",
        [
            pytest.param(
                {
                    "allowAutoConverge": True,
                    "namespaceSelector": NAMESPACE_LABEL,
                },
                MIGRATION_POLICY_VM_LABEL,
                NAMESPACE_LABEL,
                marks=pytest.mark.polarion("CNV-8241"),
                id="by_namespace_label_selector",
            ),
            pytest.param(
                {
                    "allowAutoConverge": True,
                    "virtualMachineInstanceSelector": MIGRATION_POLICY_VM_LABEL,
                },
                MIGRATION_POLICY_VM_LABEL,
                NAMESPACE_LABEL,
                marks=pytest.mark.polarion("CNV-8242"),
                id="by_vmi_label_selector",
            ),
        ],
        indirect=True,
    )
    def test_migration_policy_successfully_applied(
        self,
        migration_policy_a,
        labeled_namespace,
        vm_for_migration_policy_test,
        vm_migrated_with_policy,
    ):
        assert_applied_migration_policy(
            vmi=vm_for_migration_policy_test.vmi,
            expected_policy=migration_policy_a.name,
        )

    @pytest.mark.parametrize(
        "migration_policy_a, vm_for_migration_policy_test",
        [
            pytest.param(
                {
                    "allowAutoConverge": True,
                    "allowPostCopy": True,
                    "bandwidthPerMigration": "50Gi",
                    "completionTimeoutPerGiB": 50,
                    "virtualMachineInstanceSelector": MIGRATION_POLICY_VM_LABEL,
                },
                MIGRATION_POLICY_VM_LABEL,
                marks=pytest.mark.polarion("CNV-8308"),
            ),
        ],
        indirect=True,
    )
    def test_migration_policy_reverts_to_default_values(
        self,
        migration_policy_a,
        vm_for_migration_policy_test,
        vm_migrated_with_policy,
        vm_re_migrated_after_updating_migration_policy,
    ):
        assert_applied_migration_configuration(
            vmi=vm_for_migration_policy_test.vmi,
            migration_policy=migration_policy_a,
        )

    @pytest.mark.parametrize(
        "migration_policy_a, migration_policy_b, vm_for_migration_policy_test, labeled_namespace, "
        "expected_applied_policy",
        [
            pytest.param(
                {
                    "name": "migration-policy-a",
                    "allowAutoConverge": True,
                    "virtualMachineInstanceSelector": MIGRATION_POLICY_VM_LABEL,
                    "namespaceSelector": NAMESPACE_LABEL,
                },
                {
                    "name": "migration-policy-b",
                    "allowAutoConverge": True,
                    "virtualMachineInstanceSelector": MIGRATION_POLICY_VM_LABEL,
                    "namespaceSelector": NAMESPACE_LABEL,
                },
                MIGRATION_POLICY_VM_LABEL,
                NAMESPACE_LABEL,
                "migration-policy-a",
                marks=pytest.mark.polarion("CNV-8243"),
                id="with_identical_labels",
            ),
            pytest.param(
                {
                    "name": "migration-policy-a",
                    "allowAutoConverge": True,
                    "namespaceSelector": NAMESPACE_LABEL,
                },
                {
                    "name": "migration-policy-b",
                    "allowAutoConverge": True,
                    "virtualMachineInstanceSelector": MIGRATION_POLICY_VM_LABEL,
                },
                MIGRATION_POLICY_VM_LABEL,
                NAMESPACE_LABEL,
                "migration-policy-b",
                marks=pytest.mark.polarion("CNV-8247"),
                id="namespace_vs_vmi_selectors",
            ),
            pytest.param(
                {
                    "name": "migration-policy-a",
                    "allowAutoConverge": True,
                    "virtualMachineInstanceSelector": MIGRATION_POLICY_VM_LABEL,
                },
                {
                    "name": "migration-policy-b",
                    "allowAutoConverge": True,
                    "namespaceSelector": {"label-1": "", "label-2": ""},
                },
                MIGRATION_POLICY_VM_LABEL,
                {"label-1": "", "label-2": ""},
                "migration-policy-b",
                marks=pytest.mark.polarion("CNV-8248"),
                id="multiple_selectors_vs_one",
            ),
        ],
        indirect=[
            "migration_policy_a",
            "migration_policy_b",
            "vm_for_migration_policy_test",
            "labeled_namespace",
        ],
    )
    def test_migration_policy_priority(
        self,
        migration_policy_a,
        migration_policy_b,
        labeled_namespace,
        vm_for_migration_policy_test,
        vm_migrated_with_policy,
        expected_applied_policy,
    ):
        assert_applied_migration_policy(
            vmi=vm_for_migration_policy_test.vmi,
            expected_policy=expected_applied_policy,
        )

    @pytest.mark.parametrize(
        "migration_policy_a, vm_for_migration_policy_test",
        [
            pytest.param(
                {
                    "allowAutoConverge": True,
                    "virtualMachineInstanceSelector": MIGRATION_POLICY_VM_LABEL,
                    "namespaceSelector": {"namespace-fake-label": ""},
                },
                MIGRATION_POLICY_VM_LABEL,
                marks=pytest.mark.polarion("CNV-8249"),
            ),
        ],
        indirect=True,
    )
    def test_migration_policy_not_applied_when_selectors_not_match(
        self,
        migration_policy_a,
        vm_for_migration_policy_test,
        vm_migrated_with_policy,
    ):
        assert_applied_migration_policy(
            vmi=vm_for_migration_policy_test.vmi,
            expected_policy=None,
        )
