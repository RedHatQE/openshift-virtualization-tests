import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    NP_INFRA_KEY,
    NP_INFRA_VALUE_CDI_CR,
    NP_INFRA_VALUE_HCO_CR,
    NP_WORKLOADS_KEY_CDI_CR,
    NP_WORKLOADS_KEY_HCO_CR,
    NP_WORKLOADS_VALUE_CDI_CR,
    NP_WORKLOADS_VALUE_HCO_CR,
    OBSOLETE_CPUS_KEY,
    OBSOLETE_CPUS_VALUE_HCO_CR,
    OBSOLETE_CPUS_VALUE_KUBEVIRT_CR,
    RESOURCE_REQUIREMENTS,
    SCRATCH_SPACE_STORAGE_CLASS_KEY,
    SCRATCH_SPACE_STORAGE_CLASS_VALUE,
    STORAGE_IMPORT_KEY_HCO_CR,
    STORAGE_IMPORT_VALUE,
)
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    compare_expected_with_cr,
)
from utilities.constants import (
    CDI_KUBEVIRT_HYPERCONVERGED,
    KUBEVIRT_HCO_NAME,
    RESOURCE_REQUIREMENTS_KEY_HCO_CR,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64]

LOGGER = logging.getLogger(__name__)


def get_resource_current_value(resource_spec, field_to_validate):
    current_value = None
    if field_to_validate == OBSOLETE_CPUS_KEY:
        current_value = resource_spec["configuration"]
    elif field_to_validate == RESOURCE_REQUIREMENTS_KEY_HCO_CR:
        current_value = resource_spec["config"]["podResourceRequirements"]
    elif field_to_validate == SCRATCH_SPACE_STORAGE_CLASS_KEY:
        current_value = resource_spec["config"][SCRATCH_SPACE_STORAGE_CLASS_KEY]
    elif field_to_validate == STORAGE_IMPORT_KEY_HCO_CR:
        current_value = resource_spec["config"]
    elif field_to_validate == NP_INFRA_KEY:
        current_value = resource_spec[NP_INFRA_KEY]
    elif field_to_validate == NP_WORKLOADS_KEY_HCO_CR:
        current_value = resource_spec[NP_WORKLOADS_KEY_CDI_CR]
    else:
        pytest.fail("Bad test configuration. This should never be reached.")
    return current_value


class TestHCONonDefaultFields:
    @pytest.mark.parametrize(
        (
            "deleted_stanza_on_hco_cr",
            "reconciled_cr_post_hco_update",
            "field_to_verify",
            "expected",
        ),
        [
            pytest.param(
                {
                    "rpatch": {
                        "spec": {RESOURCE_REQUIREMENTS_KEY_HCO_CR: RESOURCE_REQUIREMENTS},
                    },
                    "list_resource_reconcile": [CDI],
                },
                {"resource_class": CDI, "resource_name": CDI_KUBEVIRT_HYPERCONVERGED},
                RESOURCE_REQUIREMENTS_KEY_HCO_CR,
                RESOURCE_REQUIREMENTS["storageWorkloads"],
                marks=(pytest.mark.polarion("CNV-6541")),
                id="set_non_default_field_resourceRequirements",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            SCRATCH_SPACE_STORAGE_CLASS_KEY: SCRATCH_SPACE_STORAGE_CLASS_VALUE,
                        }
                    },
                    "list_resource_reconcile": [CDI],
                },
                {"resource_class": CDI, "resource_name": CDI_KUBEVIRT_HYPERCONVERGED},
                SCRATCH_SPACE_STORAGE_CLASS_KEY,
                SCRATCH_SPACE_STORAGE_CLASS_VALUE,
                marks=(pytest.mark.polarion("CNV-6542")),
                id="set_non_default_field_scratchSpaceStorageClass",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            OBSOLETE_CPUS_KEY: OBSOLETE_CPUS_VALUE_HCO_CR,
                        }
                    },
                    "list_resource_reconcile": [KubeVirt],
                },
                {"resource_class": KubeVirt, "resource_name": KUBEVIRT_HCO_NAME},
                OBSOLETE_CPUS_KEY,
                OBSOLETE_CPUS_VALUE_KUBEVIRT_CR,
                marks=(pytest.mark.polarion("CNV-6544")),
                id="set_non_default_field_obsoleteCPUs",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            STORAGE_IMPORT_KEY_HCO_CR: STORAGE_IMPORT_VALUE,
                        }
                    },
                    "list_resource_reconcile": [CDI],
                },
                {"resource_class": CDI, "resource_name": CDI_KUBEVIRT_HYPERCONVERGED},
                STORAGE_IMPORT_KEY_HCO_CR,
                STORAGE_IMPORT_VALUE,
                marks=(pytest.mark.polarion("CNV-6545")),
                id="set_non_default_field_storage_import",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            NP_INFRA_KEY: NP_INFRA_VALUE_HCO_CR,
                        }
                    },
                    "list_resource_reconcile": [CDI, KubeVirt],
                    "wait_for_reconcile": False,
                },
                {"resource_class": CDI, "resource_name": CDI_KUBEVIRT_HYPERCONVERGED},
                NP_INFRA_KEY,
                NP_INFRA_VALUE_CDI_CR,
                marks=(pytest.mark.polarion("CNV-6539")),
                id="set_non_default_field_infra",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            NP_WORKLOADS_KEY_HCO_CR: NP_WORKLOADS_VALUE_HCO_CR,
                        }
                    },
                    "list_resource_reconcile": [CDI, KubeVirt],
                    "wait_for_reconcile": False,
                },
                {"resource_class": CDI, "resource_name": CDI_KUBEVIRT_HYPERCONVERGED},
                NP_WORKLOADS_KEY_HCO_CR,
                NP_WORKLOADS_VALUE_CDI_CR,
                marks=(pytest.mark.polarion("CNV-6540")),
                id="set_non_default_field_workloads",
            ),
        ],
        indirect=["deleted_stanza_on_hco_cr", "reconciled_cr_post_hco_update"],
    )
    @pytest.mark.s390x
    def test_non_default_fields_cdi(
        self,
        hco_status_related_objects_scope_function,
        deleted_stanza_on_hco_cr,
        reconciled_cr_post_hco_update,
        field_to_verify,
        expected,
    ):
        LOGGER.info(f"Validating: {reconciled_cr_post_hco_update.name} for reconciliation.")
        current_value = get_resource_current_value(
            resource_spec=reconciled_cr_post_hco_update.instance.to_dict()["spec"],
            field_to_validate=field_to_verify,
        )

        assert not compare_expected_with_cr(
            expected=expected,
            actual=current_value,
        ), f"Expected value of {reconciled_cr_post_hco_update.name}: {expected}, actual value: {current_value}"
